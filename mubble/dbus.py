"""Blocking jeepney helpers. A connection belongs to the thread that opened it."""

from jeepney import DBusAddress, new_method_call
from jeepney.wrappers import unwrap_msg

PROPS = "org.freedesktop.DBus.Properties"


def call(conn, dest, path, iface, member, sig=None, body=(), timeout=2.0):
    """Call a method and return its reply body; raises on a D-Bus error reply."""
    msg = new_method_call(DBusAddress(path, bus_name=dest, interface=iface),
                          member, sig, tuple(body))
    return unwrap_msg(conn.send_and_get_reply(msg, timeout=timeout))


def get_all(conn, dest, path, iface):
    """Every property of one interface, with the outer variant removed."""
    (props,) = call(conn, dest, path, PROPS, "GetAll", "s", (iface,))
    return {key: value[1] for key, value in props.items()}
