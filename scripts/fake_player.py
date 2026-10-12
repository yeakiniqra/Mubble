"""A stand-in MPRIS player, for working on Mubble without playing real music.

    .venv/bin/python scripts/fake_player.py [cover-image]

Appears on the session bus as a playing track, moves its position forward,
obeys PlayPause / Next / SetPosition and prints each call it receives.
"""

import sys
import time
from pathlib import Path

from jeepney import (DBusAddress, HeaderFields, MessageType, message_bus,
                     new_error, new_method_return, new_signal)
from jeepney.io.blocking import Proxy, open_dbus_connection

PATH   = "/org/mpris/MediaPlayer2"
TITLES = ["Midnight City (Extended Version With A Very Long Title)", "Second Song"]

cover = Path(sys.argv[1] if len(sys.argv) > 1
             else Path(__file__).parent.parent / "assets" / "logo.png").resolve()
conn = open_dbus_connection("SESSION")
Proxy(message_bus, conn).RequestName("org.mpris.MediaPlayer2.mubbletest")
state = {"playing": True, "track": 0, "base": 42.0, "since": time.time()}


def position():
    return state["base"] + (time.time() - state["since"] if state["playing"] else 0)


def properties():
    return {
        "PlaybackStatus": ("s", "Playing" if state["playing"] else "Paused"),
        "Position":       ("x", int(position() * 1e6)),
        "CanGoNext":      ("b", True),
        "CanGoPrevious":  ("b", False),
        "CanSeek":        ("b", True),
        "Metadata": ("a{sv}", {
            "xesam:title":   ("s", TITLES[state["track"] % len(TITLES)]),
            "xesam:artist":  ("as", ["M83", "Guest"]),
            "mpris:length":  ("x", 215_000_000),
            "mpris:trackid": ("o", "/track/1"),
            "mpris:artUrl":  ("s", cover.as_uri()),
        }),
    }


print("playing as org.mpris.MediaPlayer2.mubbletest — Ctrl+C to stop")
while True:
    msg = conn.receive()
    if msg.header.message_type != MessageType.method_call:
        continue
    member = msg.header.fields[HeaderFields.member]
    if member == "GetAll":
        conn.send(new_method_return(msg, "a{sv}", (properties(),)))
        continue
    if member == "PlayPause":
        state.update(base=position(), since=time.time(), playing=not state["playing"])
    elif member == "Next":
        state.update(track=state["track"] + 1, base=0.0, since=time.time())
    elif member == "SetPosition":
        state.update(base=msg.body[1] / 1e6, since=time.time())
    else:
        conn.send(new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod"))
        continue
    print(member, *msg.body, flush=True)
    conn.send(new_method_return(msg))
    conn.send(new_signal(DBusAddress(PATH, interface="org.freedesktop.DBus.Properties"),
                         "PropertiesChanged", "sa{sv}as",
                         ("org.mpris.MediaPlayer2.Player", {}, [])))
