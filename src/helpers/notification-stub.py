#!/usr/bin/env python3
"""Minimal D-Bus notification stub - holds org.freedesktop.Notifications during AGS restart.
Responds to GetCapabilities/GetServerInformation so apps don't get errors.
Auto-exits when another process (AGS) claims the name, or after 10s timeout."""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from gi.repository import GLib, Gio

notification_id_counter = 0

INTROSPECTION_XML = """
<node>
  <interface name="org.freedesktop.Notifications">
    <method name="GetCapabilities">
      <arg direction="out" type="as" name="capabilities"/>
    </method>
    <method name="GetServerInformation">
      <arg direction="out" type="s" name="name"/>
      <arg direction="out" type="s" name="vendor"/>
      <arg direction="out" type="s" name="version"/>
      <arg direction="out" type="s" name="spec_version"/>
    </method>
    <method name="Notify">
      <arg direction="in" type="s" name="app_name"/>
      <arg direction="in" type="u" name="replaces_id"/>
      <arg direction="in" type="s" name="app_icon"/>
      <arg direction="in" type="s" name="summary"/>
      <arg direction="in" type="s" name="body"/>
      <arg direction="in" type="as" name="actions"/>
      <arg direction="in" type="a{sv}" name="hints"/>
      <arg direction="in" type="i" name="expire_timeout"/>
      <arg direction="out" type="u" name="id"/>
    </method>
    <method name="CloseNotification">
      <arg direction="in" type="u" name="id"/>
    </method>
  </interface>
</node>
"""

def handle_method_call(connection, sender, path, iface, method, params, invocation):
    global notification_id_counter
    if method == "GetCapabilities":
        invocation.return_value(GLib.Variant("(as)", [["body", "actions"]]))
    elif method == "GetServerInformation":
        invocation.return_value(GLib.Variant("(ssss)", ["ags-stub", "zepos", "0.1", "1.2"]))
    elif method == "Notify":
        notification_id_counter += 1
        invocation.return_value(GLib.Variant("(u)", [notification_id_counter]))
    elif method == "CloseNotification":
        invocation.return_value(None)

def on_bus_acquired(connection, name):
    node_info = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML)
    connection.register_object(
        "/org/freedesktop/Notifications",
        node_info.interfaces[0],
        handle_method_call,
    )

def on_name_acquired(connection, name):
    pass

def on_name_lost(connection, name):
    # AGS claimed the name - our job is done
    loop.quit()

loop = GLib.MainLoop()
owner_id = Gio.bus_own_name(
    Gio.BusType.SESSION,
    "org.freedesktop.Notifications",
    Gio.BusNameOwnerFlags.REPLACE | Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
    on_bus_acquired,
    on_name_acquired,
    on_name_lost,
)

# Safety timeout - exit after 10 seconds regardless
GLib.timeout_add_seconds(10, loop.quit)

try:
    loop.run()
except KeyboardInterrupt:
    pass

Gio.bus_unown_name(owner_id)
