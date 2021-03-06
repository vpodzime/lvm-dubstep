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

from automatedproperties import AutomatedProperties

import utils
from cfg import MANAGER_INTERFACE
import dbus
import cfg
import cmdhandler
from fetch import load_pvs, load_vgs, load
from request import RequestEntry
from refresh import event_add


# noinspection PyPep8Naming
class Manager(AutomatedProperties):
    DBUS_INTERFACE = MANAGER_INTERFACE
    _Version_type = "t"

    def __init__(self, object_path):
        super(Manager, self).__init__(object_path, MANAGER_INTERFACE)

    @property
    def Version(self):
        return '1.0.0'

    @staticmethod
    def _pv_create(device, create_options):

        # Check to see if we are already trying to create a PV for an existing
        # PV
        pv = cfg.om.get_object_path_by_lvm_id(
            device, device, None, False)
        if pv:
            raise dbus.exceptions.DBusException(
                MANAGER_INTERFACE, "PV Already exists!")

        created_pv = []
        rc, out, err = cmdhandler.pv_create(create_options, [device])
        if rc == 0:
            pvs = load_pvs([device])[0]
            for p in pvs:
                cfg.om.register_object(p, True)
                created_pv = p.dbus_object_path()
        else:
            raise dbus.exceptions.DBusException(
                MANAGER_INTERFACE,
                'Exit code %s, stderr = %s' % (str(rc), err))

        return created_pv

    @dbus.service.method(dbus_interface=MANAGER_INTERFACE,
                         in_signature='sia{sv}',
                         out_signature='(oo)',
                         async_callbacks=('cb', 'cbe'))
    def PvCreate(self, device, tmo, create_options, cb, cbe):
        r = RequestEntry(tmo, Manager._pv_create,
                         (device, create_options), cb, cbe)
        cfg.worker_q.put(r)

    @staticmethod
    def _create_vg(name, pv_object_paths, create_options):
        pv_devices = []

        for p in pv_object_paths:
            pv = cfg.om.get_by_path(p)
            if pv:
                pv_devices.append(pv.Name)
            else:
                raise dbus.exceptions.DBusException(
                    MANAGER_INTERFACE, 'object path = %s not found' % p)

        rc, out, err = cmdhandler.vg_create(create_options, pv_devices, name)
        created_vg = "/"

        if rc == 0:
            vgs = load_vgs([name])[0]
            for v in vgs:
                cfg.om.register_object(v, True)
                created_vg = v.dbus_object_path()

            # For each PV that was involved in this VG create we need to
            # signal the property changes, make sure to do this *after* the
            # vg is available on the bus
            for p in pv_object_paths:
                pv = cfg.om.get_by_path(p)
                pv.refresh()
        else:
            raise dbus.exceptions.DBusException(
                MANAGER_INTERFACE,
                'Exit code %s, stderr = %s' % (str(rc), err))
        return created_vg

    @dbus.service.method(dbus_interface=MANAGER_INTERFACE,
                         in_signature='saoia{sv}',
                         out_signature='(oo)',
                         async_callbacks=('cb', 'cbe'))
    def VgCreate(self, name, pv_object_paths, tmo, create_options, cb, cbe):
        r = RequestEntry(tmo, Manager._create_vg,
                         (name, pv_object_paths, create_options,),
                         cb, cbe)
        cfg.worker_q.put(r)

    @dbus.service.method(dbus_interface=MANAGER_INTERFACE,
                         out_signature='t')
    def Refresh(self):
        """
        Take all the objects we know about and go out and grab the latest
        more of a test method at the moment to make sure we are handling object
        paths correctly.

        Returns the number of changes, object add/remove/properties changed
        """
        #cfg.om.refresh_all()
        utils.pprint('Manager.Refresh - entry',
                     'bg_black', 'fg_light_red')
        rc = load(refresh=True)
        utils.pprint('Manager.Refresh - exit %d' % (rc),
                     'bg_black', 'fg_light_red')
        return rc

    @dbus.service.method(dbus_interface=MANAGER_INTERFACE,
                         in_signature='s',
                         out_signature='o')
    def LookUpByLvmId(self, key):
        """
        Given a lvm id in one of the forms:

        /dev/sda
        some_vg
        some_vg/some_lv
        Oe1rPX-Pf0W-15E5-n41N-ZmtF-jXS0-Osg8fn

        return the object path in O(1) time.

        :param key: The lookup value
        :return: Return the object path.  If object not found you will get '/'
        """
        p = cfg.om.get_object_path_by_lvm_id(
            key, key, gen_new=False)
        if p:
            return p
        return '/'

    @dbus.service.method(dbus_interface=MANAGER_INTERFACE,
                         in_signature='b')
    def UseLvmShell(self, yes_no):
        """
        Allow the client to enable/disable lvm shell, used for testing
        :param yes_no:
        :return: Nothing
        """
        cmdhandler.set_execution(yes_no)

    @dbus.service.method(dbus_interface=MANAGER_INTERFACE,
                         in_signature='sssu', out_signature='i')
    def ExternalEvent(self, event, lvm_id, lvm_uuid, seqno):

        event_add((event, lvm_id, lvm_uuid, seqno))
        return dbus.Int32(0)

    @property
    def lvm_id(self):
        """
        Intended to be overridden by classes that inherit
        """
        return str(id(self))

    @property
    def Uuid(self):
        """
        Intended to be overridden by classes that inherit
        """
        import uuid
        return uuid.uuid1()
