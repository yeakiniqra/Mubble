"""Announce Bluetooth earbuds and headphones as they connect (Windows).

The Windows counterpart of bluetooth.py: a watcher over paired Bluetooth
devices, announcing one whose connected flag turns on.
"""

import asyncio
import logging
import threading

from PySide6.QtCore import QObject, Signal
from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothMajorClass
from winrt.windows.devices.enumeration import DeviceInformation, DeviceInformationKind

log = logging.getLogger("mubble")

CONNECTED = "System.Devices.Aep.IsConnected"


class Buds(QObject):
    connected = Signal(str, int)   # device name, battery percent or -1

    def start(self):
        threading.Thread(target=asyncio.run, args=(self._run(),), daemon=True).start()

    async def _run(self):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        known = {}   # device id -> connected, as last seen

        # WinRT calls these from its own threads.
        def added(_watcher, info):
            loop.call_soon_threadsafe(queue.put_nowait, (info.id, info.properties))

        def updated(_watcher, update):
            loop.call_soon_threadsafe(queue.put_nowait, (update.id, update.properties))

        watcher = DeviceInformation.create_watcher_with_kind_aqs_filter_and_additional_properties(
            BluetoothDevice.get_device_selector_from_pairing_state(True), [CONNECTED],
            DeviceInformationKind.ASSOCIATION_ENDPOINT)
        watcher.add_added(added)
        watcher.add_updated(updated)
        watcher.start()
        while True:
            device, props = await queue.get()
            if CONNECTED not in props:
                continue
            now = bool(props[CONNECTED])
            # The first sighting of each device is how it already was at start.
            was = known.get(device, now)
            known[device] = now
            if now and not was:
                try:
                    found = await describe(device)
                except Exception as e:   # gone again before it could be described
                    log.warning("Bluetooth device unreadable: %s", e)
                    continue
                if found:
                    self.connected.emit(*found)


async def describe(device_id):
    """(name, -1) for an audio device, None for anything else.
    ponytail: no battery; Windows keeps it in a PnP device property
    (DEVPKEY_Bluetooth_Battery) on a different node than this one."""
    device = await BluetoothDevice.from_id_async(device_id)
    if not device or device.class_of_device.major_class != BluetoothMajorClass.AUDIO_VIDEO:
        return None
    return device.name or "Headphones", -1
