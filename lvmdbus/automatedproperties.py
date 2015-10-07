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
import cfg
from utils import get_properties, add_properties, get_object_property_diff


# noinspection PyPep8Naming
class AutomatedProperties(dbus.service.Object):
    """
    This class implements the needed interfaces for:
    org.freedesktop.DBus.Properties

    Other classes inherit from it to get the same behavior
    """

    DBUS_INTERFACE = ''

    def __init__(self, object_path, interface, search_method=None):
        dbus.service.Object.__init__(self, cfg.bus, object_path)
        self._ap_interface = interface
        self._ap_o_path = object_path
        self._ap_search_method = search_method

    def dbus_object_path(self):
        return self._ap_o_path

    def emit_data(self):
        props = {}

        for i in self.interface():
            props[i] = self.GetAll(i)

        return self._ap_o_path, props

    def interface(self, all_interfaces=False):
        rc = []
        if all_interfaces:
            rc = self._dbus_interface_table.keys()
        else:
            for k in self._dbus_interface_table.keys():
                if not k.startswith('org.freedesktop.DBus'):
                    rc.append(k)
        return rc

    # Properties
    # noinspection PyUnusedLocal
    @dbus.service.method(dbus_interface=dbus.PROPERTIES_IFACE,
                         in_signature='ss', out_signature='v')
    def Get(self, interface_name, property_name):
        value = getattr(self, property_name)
        # Note: If we get an exception in this handler we won't know about it,
        # only the side effect of no returned value!
        print 'Get (%s), type (%s), value(%s)' % \
              (property_name, str(type(value)), str(value))
        return value

    @dbus.service.method(dbus_interface=dbus.PROPERTIES_IFACE,
                         in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface_name):
        if interface_name in self.interface():
            # Using introspection, lets build this dynamically
            return get_properties(self, interface_name)[1]
        raise dbus.exceptions.DBusException(
            self._ap_interface,
            'The object %s does not implement the %s interface'
            % (self.__class__, interface_name))

    @dbus.service.method(dbus_interface=dbus.PROPERTIES_IFACE,
                         in_signature='ssv')
    def Set(self, interface_name, property_name, new_value):
        setattr(self, property_name, new_value)
        self.PropertiesChanged(interface_name,
                               {property_name: new_value}, [])

    # As dbus-python does not support introspection for properties we will
    # get the autogenerated xml and then add our wanted properties to it.
    @dbus.service.method(dbus_interface=dbus.INTROSPECTABLE_IFACE,
                         out_signature='s')
    def Introspect(self):
        r = dbus.service.Object.Introspect(self, self._ap_o_path, cfg.bus)
        # Look at the properties in the class
        return add_properties(r, self._ap_interface, get_properties(self)[0])

    @dbus.service.signal(dbus_interface=dbus.PROPERTIES_IFACE,
                         signature='sa{sv}as')
    def PropertiesChanged(self, interface_name, changed_properties,
                          invalidated_properties):
        print('SIGNAL: PropertiesChanged(%s, %s, %s)' %
              (str(interface_name), str(changed_properties),
               str(invalidated_properties)))

    def refresh(self, search_key=None, object_ctor=None, object_state=None):
        """
        Take this object, go out and fetch the latest LVM copy and replace the
        one registered with dbus.  Not sure if there is a better way to do
        this, instead of resorting to removing the existing object and
        inserting a new one... One possible way to handle this is to separate
        the state of lvm from the dbus object representation.  Thus the
        dbus object would contain an object which represents lvm state, one
        that we could swap out whenever it was needed.

        WARNING: Once you call into this method, "self" is removed
        from the dbus API and thus you cannot call any dbus methods upon it.

        """
        num_changed = 0

        # If we can't do a lookup, bail now, this happens if we blindly walk
        # through all dbus objects as some don't have a search method, like
        # 'Manager' object.
        if not self._ap_search_method:
            return

        with cfg.om.locked():
            # We want the remove & subsequent add to be atomic, would be better
            # if we could move this into the object manager class itself...
            # The bigger question is we typically refresh a number of different
            # objects together, as part of a change.  As lvm does locking at
            # the VG layer one would think that these related changes would not
            # need locking in the object manager.  We may find that we need
            # to be able to refresh a sequence of changes atomically, esp. when
            # we start supporting nested LVM (LVs that are PVs).

            search = self.lvm_id
            if search_key:
                search = search_key

            cfg.om.remove_object(self)

            if object_ctor and object_state:
                # We were passed the new state so we will just create the
                # object here
                found = [object_ctor(self.dbus_object_path(), object_state)]
            else:
                # Go out and fetch the latest version of this object, eg.
                # pvs, vgs, lvs
                found = self._ap_search_method(
                    [search], self.dbus_object_path())[0]
            for i in found:
                cfg.om.register_object(i)
                changed = get_object_property_diff(self, i)

                if changed:
                    # Use the instance that is registered with dbus API as self
                    # has been removed, calls to it will make no difference
                    # with regards to the dbus API.
                    i.PropertiesChanged(self._ap_interface, changed, [])
                    num_changed += 1
        return num_changed

    @property
    def lvm_id(self):
        """
        Intended to be overridden by classes that inherit
        """
        return str(id(self))

    @property
    def uuid(self):
        """
        Intended to be overridden by classes that inherit
        """
        import uuid
        return uuid.uuid1()
