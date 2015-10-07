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
import cfg
import dbus
from cfg import PV_INTERFACE
import cmdhandler
from utils import thin_pool_obj_path_generate, lv_obj_path_generate, \
    vg_obj_path_generate, pv_obj_path_generate, n
from loader import common
from request import RequestEntry


def pvs_hash_to_object(path, p):
    # This object is unknown, lets add it to the model
    if not path:
        path = cfg.om.get_object_path_by_lvm_id(
            p['pv_uuid'], p['pv_name'], pv_obj_path_generate)

    return Pv(path,
              p["pv_name"], p["pv_uuid"], p["pv_name"], p["pv_fmt"],
              n(p["pv_size"]),
              n(p["pv_free"]), n(p["pv_used"]), n(p["dev_size"]),
              n(p["pv_mda_size"]), n(p["pv_mda_free"]),
              long(p["pv_ba_start"]), n(p["pv_ba_size"]),
              n(p["pe_start"]), long(p["pv_pe_count"]),
              long(p["pv_pe_alloc_count"]),
              p["pv_attr"], p["pv_tags"], p["vg_name"], p["vg_uuid"])


def pvs_hash_to_ids(p):
    return p['pv_uuid'], p['pv_name']


def pvs_hash_retrieve(selection):
    _pvs = cmdhandler.pv_retrieve(selection)
    return sorted(_pvs, key=lambda pk: pk['pv_name'])


def load_pvs(device=None, object_path=None, refresh=False):
    return common(pvs_hash_retrieve, pvs_hash_to_ids, pvs_hash_to_object,
                       (Pv,), device, object_path, refresh)


# noinspection PyPep8Naming
@utils.dbus_property('Uuid', 's')               # PV UUID/pv_uuid
@utils.dbus_property('Name', 's')               # PV/pv_name
@utils.dbus_property('Fmt', 's')                # Fmt/pv_fmt
@utils.dbus_property('SizeBytes', 't', 0)       # PSize/pv_size
@utils.dbus_property('FreeBytes', 't', 0)       # PFree/pv_free
@utils.dbus_property('UsedBytes', 't', 0)       # Used/pv_used
@utils.dbus_property('DevSizeBytes', 't', 0)    # DevSize/dev_size
@utils.dbus_property('MdaSizeBytes', 't', 0)    # PMdaSize/pv_mda_size
@utils.dbus_property('MdaFreeBytes', 't', 0)    # PMdaFree/pv_mda_free
@utils.dbus_property('BaStart', 't', 0)         # BA start/pv_ba_start
@utils.dbus_property('BaSizeBytes', 't', 0)     # BA size/pv_ba_size
@utils.dbus_property('PeStart', 't', 0)         # 1st PE/pe_start
@utils.dbus_property('PeCount', 't', 0)         # PE/pv_pe_count
@utils.dbus_property('PeAllocCount', 't', 0)    # Alloc/pv_pe_alloc_count
class Pv(AutomatedProperties):
    DBUS_INTERFACE = PV_INTERFACE

    # For properties that we need custom handlers we need these, otherwise
    # we won't get our introspection data
    _Tags_type = "as"
    _PeSegments_type = "a(tt)"
    _Exportable_type = "b"
    _Allocatable_type = "b"
    _Missing_type = "b"
    _Lv_type = "a(oa(tt))"
    _Vg_type = "o"

    def _lv_object_list(self, vg_name):
        rc = []
        if vg_name:
            for lv in sorted(cmdhandler.pv_contained_lv(self.lvm_id)):
                full_name = "%s/%s" % (vg_name, lv[0])
                segs = lv[1]
                attrib = lv[2]
                lv_uuid = lv[3]

                if attrib[0] == 't':
                    lv_path = cfg.om.get_object_path_by_lvm_id(
                        lv_uuid, full_name, thin_pool_obj_path_generate)
                else:
                    lv_path = cfg.om.get_object_path_by_lvm_id(
                        lv_uuid, full_name, lv_obj_path_generate)
                rc.append((lv_path, segs))
        return dbus.Array(rc, signature="(oa(tt))")

    # noinspection PyUnusedLocal,PyPep8Naming
    def __init__(self, object_path, lvm_path, Uuid, Name,
                 Fmt, SizeBytes, FreeBytes, UsedBytes, DevSizeBytes,
                 MdaSizeBytes, MdaFreeBytes, BaStart, BaSizeBytes,
                 PeStart, PeCount, PeAllocCount, attr, Tags, vg_name,
                 vg_uuid):
        super(Pv, self).__init__(object_path, PV_INTERFACE, load_pvs)
        utils.init_class_from_arguments(self)
        self._pe_segments = cmdhandler.pv_segments(lvm_path)
        self._lv = self._lv_object_list(vg_name)

        if vg_name:
            self._vg_path = cfg.om.get_object_path_by_lvm_id(
                vg_uuid, vg_name, vg_obj_path_generate)
        else:
            self._vg_path = '/'

    @staticmethod
    def _remove(pv_uuid, pv_name, remove_options):
        # Remove the PV, if successful then remove from the model
        # Make sure we have a dbus object representing it
        dbo = cfg.om.get_by_uuid_lvm_id(pv_uuid, pv_name)

        if dbo:
            rc, out, err = cmdhandler.pv_remove(pv_name, remove_options)
            if rc == 0:
                cfg.om.remove_object(dbo, True)
            else:
                # Need to work on error handling, need consistent
                raise dbus.exceptions.DBusException(
                    PV_INTERFACE,
                    'Exit code %s, stderr = %s' % (str(rc), err))
        else:
            raise dbus.exceptions.DBusException(
                PV_INTERFACE, 'PV with uuid %s and name %s not present!' %
                (pv_uuid, pv_name))
        return '/'

    @dbus.service.method(dbus_interface=PV_INTERFACE,
                         in_signature='ia{sv}',
                         out_signature='o',
                         async_callbacks=('cb', 'cbe'))
    def Remove(self, tmo, remove_options, cb, cbe):
        r = RequestEntry(tmo, Pv._remove,
                         (self.uuid, self.lvm_id, remove_options),
                         cb, cbe, return_tuple=False)
        cfg.worker_q.put(r)

    @staticmethod
    def _resize(pv_uuid, pv_name, new_size_bytes, resize_options):
        # Make sure we have a dbus object representing it
        dbo = cfg.om.get_by_uuid_lvm_id(pv_uuid, pv_name)

        if dbo:
            rc, out, err = cmdhandler.pv_resize(pv_name, new_size_bytes,
                                                resize_options)
            if rc == 0:
                dbo.refresh()
            else:
                raise dbus.exceptions.DBusException(
                    PV_INTERFACE,
                    'Exit code %s, stderr = %s' % (str(rc), err))
        else:
            raise dbus.exceptions.DBusException(
                PV_INTERFACE, 'PV with uuid %s and name %s not present!' %
                (pv_uuid, pv_name))
        return '/'

    @dbus.service.method(dbus_interface=PV_INTERFACE,
                         in_signature='tia{sv}',
                         out_signature='o',
                         async_callbacks=('cb', 'cbe'))
    def ReSize(self, new_size_bytes, tmo, resize_options, cb, cbe):
        r = RequestEntry(tmo, Pv._resize,
                         (self.uuid, self.lvm_id, new_size_bytes,
                          resize_options), cb, cbe, False)
        cfg.worker_q.put(r)

    @staticmethod
    def _allocation_enabled(pv_uuid, pv_name, yes_no, allocation_options):
        # Make sure we have a dbus object representing it
        dbo = cfg.om.get_by_uuid_lvm_id(pv_uuid, pv_name)

        if dbo:
            rc, out, err = cmdhandler.pv_allocatable(pv_name, yes_no,
                                                     allocation_options)
            if rc == 0:
                dbo.refresh()
            else:
                raise dbus.exceptions.DBusException(
                    PV_INTERFACE, 'Exit code %s, stderr = %s' % (str(rc), err))
        else:
            raise dbus.exceptions.DBusException(
                PV_INTERFACE, 'PV with uuid %s and name %s not present!' %
                (pv_uuid, pv_name))
        return '/'

    @dbus.service.method(dbus_interface=PV_INTERFACE,
                         in_signature='bia{sv}',
                         out_signature='o',
                         async_callbacks=('cb', 'cbe'))
    def AllocationEnabled(self, yes, tmo, allocation_options, cb, cbe):
        r = RequestEntry(tmo, Pv._allocation_enabled,
                         (self.uuid, self.lvm_id, yes, allocation_options),
                         cb, cbe, False)
        cfg.worker_q.put(r)

    @property
    def Tags(self):
        return utils.parse_tags(self._Tags)

    @property
    def PeSegments(self):
        if len(self._pe_segments):
            return self._pe_segments
        return dbus.Array([], '(tt)')

    @property
    def Exportable(self):
        if self._attr[1] == 'x':
            return True
        return False

    @property
    def Allocatable(self):
        if self._attr[0] == 'a':
            return True
        return False

    @property
    def Missing(self):
        if self._attr[2] == 'm':
            return True
        return False

    def object_path(self):
        return self._object_path

    @property
    def lvm_id(self):
        return self._lvm_path

    @property
    def Lv(self):
        return self._lv

    @property
    def Vg(self):
        return self._vg_path
