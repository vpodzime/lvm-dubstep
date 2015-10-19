#!/usr/bin/env python2

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
# Copyright 2015, Tony Asleson <tasleson@redhat.com>

import dbus
from dbus.mainloop.glib import DBusGMainLoop
import unittest
import sys
import random
import string
import functools


BUSNAME = "com.redhat.lvmdbus1"
MANAGER_INT = BUSNAME + '.Manager'
MANAGER_OBJ = '/' + BUSNAME.replace('.', '/') + 'Manager'
PV_INT = BUSNAME + ".Pv"
VG_INT = BUSNAME + ".Vg"
LV_INT = BUSNAME + ".Lv"
THINPOOL_INT = BUSNAME + ".Thinpool"
JOB_INT = BUSNAME + ".Job"


def rs(length, suffix):
    return ''.join(random.choice(string.ascii_lowercase)
                   for _ in range(length)) + suffix


class RemoteObject(object):

    def __init__(self, bus, object_path, interface, properties=None):
        self.object_path = object_path
        self.interface = interface

        self.dbus_method = dbus.Interface(bus.get_object(
            BUSNAME, self.object_path), self.interface)

        if not properties:
            #print 'Fetching properties'
            prop_fetch = dbus.Interface(bus.get_object(
                BUSNAME, self.object_path), 'org.freedesktop.DBus.Properties')
            properties = prop_fetch.GetAll(self.interface)
            #print str(properties)

        if properties:
            for kl, vl in properties.items():
                setattr(self, kl, vl)

    def __getattr__(self, item):
        if hasattr(self.dbus_method, item):
            return functools.partial(self._wrapper, item)
        else:
            return functools.partial(self, item)

    def _wrapper(self, _method_name, *args, **kwargs):
        return getattr(self.dbus_method, _method_name)(*args, **kwargs)


def get_objects():
    rc = {MANAGER_INT: [], PV_INT: [], VG_INT: [], LV_INT: [],
          THINPOOL_INT: [], JOB_INT: []}

    bus = dbus.SystemBus(mainloop=DBusGMainLoop())
    manager = dbus.Interface(bus.get_object(
        BUSNAME, "/com/redhat/lvmdbus1"),
        "org.freedesktop.DBus.ObjectManager")

    objects = manager.GetManagedObjects()

    for object_path, val in objects.items():
        for interface, props in val.items():
            o = RemoteObject(bus, object_path, interface, props)
            rc[interface].append(o)

    return rc, bus


class TestDbusService(unittest.TestCase):
    def setUp(self):
        # Because of the sensitive nature of running LVM tests we will only
        # run if we have PVs and nothing else, so that we can be confident that
        # we are not mucking with someones data on their system
        self.objs, self.bus = get_objects()
        if len(self.objs[PV_INT]) == 0:
            print 'No PVs present exiting!'
            sys.exit(1)
        if len(self.objs[MANAGER_INT]) != 1:
            print 'Expecting a manager object!'
            sys.exit(1)

        if len(self.objs[VG_INT]) != 0:
            print 'Expecting no VGs to exist!'
            sys.exit(1)

        self.pvs = []
        for p in self.objs[PV_INT]:
            self.pvs.append(p.Name)

    def tearDown(self):
        # If we get here it means we passed setUp, so lets remove anything
        # and everything that remains, besides the PVs themselves
        self.objs, self.bus = get_objects()
        for v in self.objs[VG_INT]:
            #print "DEBUG: Removing VG= ", v.Uuid, v.Name
            v.Remove(-1, {})

        # Check to make sure the PVs we had to start exist, else re-create
        # them
        if len(self.pvs) != len(self.objs[PV_INT]):
            for p in self.pvs:
                found = False
                for pc in self.objs[PV_INT]:
                    if pc.Name == p:
                        found = True
                        break

                if not found:
                    print 'Re-creating PV=', p
                    self._pv_create(p)

    def _pv_create(self, device):
        pv_path = self.objs[MANAGER_INT][0].PvCreate(device, -1, {})[0]
        self.assertTrue(pv_path is not None and len(pv_path) > 0)
        return pv_path

    def _refresh(self):
        return self.objs[MANAGER_INT][0].Refresh()

    def test_refresh(self):
        rc = self._refresh()
        self.assertEqual(rc, 0)

    def test_version(self):
        rc = self.objs[MANAGER_INT][0].Version
        self.assertTrue(rc is not None and len(rc) > 0)
        self.assertEqual(self._refresh(), 0)

    def _vg_create(self, pv_paths=None):

        if not pv_paths:
            pv_paths = [self.objs[PV_INT][0].object_path]

        vg_name = rs(8, '_vg')

        vg_path = self.objs[MANAGER_INT][0].VgCreate(
            vg_name,
            pv_paths,
            -1,
            {})[0]
        self.assertTrue(vg_path is not None and len(vg_path) > 0)
        return RemoteObject(self.bus, vg_path, VG_INT)

    def test_vg_create(self):
        self._vg_create()
        self.assertEqual(self._refresh(), 0)

    def test_vg_delete(self):
        vg = self._vg_create()
        vg.Remove(-1, {})
        self.assertEqual(self._refresh(), 0)

    def _pv_remove(self, pv):
        rc = pv.Remove(-1, {})
        return rc

    def test_pv_remove_add(self):
        target = self.objs[PV_INT][0]

        # Remove the PV
        rc = self._pv_remove(target)
        self.assertTrue(rc == '/')
        self.assertEqual(self._refresh(), 0)

        # Add it back
        rc = self._pv_create(target.Name)[0]
        self.assertTrue(rc == '/')
        self.assertEqual(self._refresh(), 0)

    def _lookup(self, lvm_id):
        return self.objs[MANAGER_INT][0].LookUpByLvmId(lvm_id)

    def test_lookup_by_lvm_id(self):
        # For the moment lets just lookup what we know about which is PVs
        # When we start testing VGs and LVs we will test lookups for those
        # during those unit tests
        for p in self.objs[PV_INT]:
            rc = self._lookup(p.Name)
            self.assertTrue(rc is not None and rc != '/')

        # Search for something which doesn't exist
        rc = self._lookup('/dev/null')
        self.assertTrue(rc == '/')

    def test_vg_extend(self):
        # Create a VG
        self.assertTrue(len(self.objs[PV_INT]) >= 2)

        if len(self.objs[PV_INT]) >= 2:
            pv_initial = self.objs[PV_INT][0]
            pv_next = self.objs[PV_INT][1]

            vg = self._vg_create([pv_initial.object_path])
            path = vg.Extend([pv_next.object_path], -1, {})
            self.assertTrue(path == '/')
            self.assertEqual(self._refresh(), 0)

    # noinspection PyUnresolvedReferences
    def test_vg_reduce(self):
        self.assertTrue(len(self.objs[PV_INT]) >= 2)

        if len(self.objs[PV_INT]) >= 2:
            vg = self._vg_create(
                [self.objs[PV_INT][0].object_path,
                 self.objs[PV_INT][1].object_path])

            path = vg.Reduce(False, [vg.Pvs[0]], -1, {})
            self.assertTrue(path == '/')
            self.assertEqual(self._refresh(), 0)

    # noinspection PyUnresolvedReferences
    def test_vg_rename(self):
        vg = self._vg_create()
        path = vg.Rename('renamed_' + vg.Name, -1, {})
        self.assertTrue(path == '/')
        self.assertEqual(self._refresh(), 0)

    def _test_lv_create(self, method, params, vg, thinpool=False):
        lv = None
        path = method(*params)[0]

        self.assertTrue(vg)

        if path:
            if thinpool:
                lv = RemoteObject(self.bus, path, THINPOOL_INT)
            else:
                lv = RemoteObject(self.bus, path, LV_INT)
            # TODO verify object properties

        self.assertEqual(self._refresh(), 0)
        return lv

    def test_lv_create_linear(self):

        vg = self._vg_create()
        self._test_lv_create(vg.LvCreateLinear,
                             (rs(8, '_lv'), 1024 * 1024 * 4, False, -1, {}),
                             vg)

    def test_lv_create_striped(self):
        pv_paths = []
        for pp in self.objs[PV_INT]:
            pv_paths.append(pp.object_path)

        vg = self._vg_create(pv_paths)
        self._test_lv_create(vg.LvCreateStriped,
                             (rs(8, '_lv'), 1024 * 1024 * 4, 2, 8, False,
                              -1, {}), vg)

    def test_lv_create_mirror(self):
        pv_paths = []
        for pp in self.objs[PV_INT]:
            pv_paths.append(pp.object_path)

        vg = self._vg_create(pv_paths)
        self._test_lv_create(vg.LvCreateMirror,
                             (rs(8, '_lv'), 1024 * 1024 * 4, 2, -1, {}), vg)

    def test_lv_create_raid(self):
        pv_paths = []
        for pp in self.objs[PV_INT]:
            pv_paths.append(pp.object_path)

        vg = self._vg_create(pv_paths)
        self._test_lv_create(vg.LvCreateRaid,
                             (rs(8, '_lv'), 'raid4',
                              1024 * 1024 * 16, 2, 8, False, -1, {}), vg)

    def _create_lv(self, thinpool=False):
        pv_paths = []
        for pp in self.objs[PV_INT]:
            pv_paths.append(pp.object_path)

        vg = self._vg_create(pv_paths)
        return self._test_lv_create(
            vg.LvCreateLinear,
            (rs(8, '_lv'), 1024 * 1024 * 128, thinpool, -1, {}), vg, thinpool)

    def test_lv_create_thin_pool(self):
        self._create_lv(True)

    def test_lv_rename(self):
        # Rename a regular LV
        lv = self._create_lv()
        lv.Rename('renamed_' + lv.Name, -1, {})
        self.assertEqual(self._refresh(), 0)

    def test_lv_thinpool_rename(self):
        # Rename a thin pool
        thin_pool = self._create_lv(True)
        thin_pool.Rename('renamed_' + thin_pool.Name, -1, {})
        self.assertEqual(self._refresh(), 0)

    # noinspection PyUnresolvedReferences
    def test_lv_on_thin_pool_rename(self):
        # Rename a LV on a thin Pool
        thin_pool = self._create_lv(True)

        thin_path = thin_pool.LvCreate(
            rs(10, '_thin_lv'), 1024 * 1024 * 10, -1, {})[0]

        lv = RemoteObject(self.bus, thin_path, LV_INT)

        rc = lv.Rename('rename_test' + lv.Name, -1, {})
        self.assertTrue(rc == '/')
        self.assertEqual(self._refresh(), 0)

    def test_lv_remove(self):
        lv = self._create_lv()
        rc = lv.Remove(-1, {})
        self.assertTrue(rc == '/')
        self.assertEqual(self._refresh(), 0)

    def test_lv_snapshot(self):
        lv = self._create_lv()
        rc = lv.Snapshot('ss_' + lv.Name, -1, 0, {})[0]
        self.assertTrue(rc == '/')
        self.assertEqual(self._refresh(), 0)

    # noinspection PyUnresolvedReferences
    def _wait_for_job(self, j_path):
        import time
        while True:
            j = RemoteObject(self.bus, j_path, JOB_INT)
            if j.Complete:
                print 'Done!'
                j.Remove()
                break

            print 'Percentage = ', j.Percent
            time.sleep(1)

    def test_lv_move(self):
        lv = self._create_lv()

        pv_path_move = str(lv.Devices[0][0])

        print pv_path_move

        job = lv.Move(pv_path_move, (0, 0), '/', (0, 0), {})
        self._wait_for_job(job)
        self.assertEqual(self._refresh(), 0)

if __name__ == '__main__':
    unittest.main()
