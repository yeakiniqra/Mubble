"""Announce Bluetooth earbuds and headphones as they connect (BlueZ, system bus)."""

import logging
import threading
import time
from collections import deque

from jeepney import HeaderFields, MatchRule, message_bus
from jeepney.io.blocking import Proxy, open_dbus_connection
from PySide6.QtCore import QObject, Signal

from .dbus import PROPS, get_all

log = logging.getLogger("mubble")

BLUEZ = "org.bluez"


def describe(conn, path):
    """(name, battery percent or -1) for an audio device, None for anything else."""
    device = get_all(conn, BLUEZ, path, "org.bluez.Device1")
    if not str(device.get("Icon", "")).startswith("audio"):
        return None
    try:
        battery = int(get_all(conn, BLUEZ, path, "org.bluez.Battery1")["Percentage"])
    except Exception:
        battery = -1   # many buds never report one
    return str(device.get("Alias") or "Headphones"), battery


class Buds(QObject):
    connected = Signal(str, int)   # device name, battery percent or -1

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        # One bad event must not end the watching: a device that drops out again
        # before it can be described raises, and so does a lost connection.
        while True:
            try:
                self._watch()
            except Exception as e:
                log.warning("Bluetooth watcher restarting: %s", e)
            time.sleep(5)

    def _watch(self):
        with open_dbus_connection("SYSTEM") as conn:
            rule = MatchRule(type="signal", sender=BLUEZ, interface=PROPS,
                             member="PropertiesChanged")
            rule.add_arg_condition(0, "org.bluez.Device1")
            Proxy(message_bus, conn).AddMatch(rule)
            queue = deque(maxlen=16)
            with conn.filter(rule, queue=queue):
                while True:
                    msg = conn.recv_until_filtered(queue)
                    if not msg.body[1].get("Connected", ("b", False))[1]:
                        continue
                    time.sleep(2)   # the battery interface shows up after the audio profiles
                    found = describe(conn, msg.header.fields[HeaderFields.path])
                    if found:
                        self.connected.emit(*found)
