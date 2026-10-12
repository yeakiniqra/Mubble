"""Follow whichever MPRIS player is making sound: a browser tab, Spotify, anything."""

import logging
import threading
import time
import urllib.request
from collections import deque
from urllib.parse import unquote, urlparse

from jeepney import MatchRule, message_bus
from jeepney.io.blocking import Proxy, open_dbus_connection
from PySide6.QtCore import QObject, Signal

from .dbus import PROPS, call, get_all

log = logging.getLogger("mubble")

PREFIX    = "org.mpris.MediaPlayer2."
PATH      = "/org/mpris/MediaPlayer2"
PLAYER    = "org.mpris.MediaPlayer2.Player"
ART_LIMIT = 8 << 20   # bytes; cover art comes from whoever is on the bus


def _seconds(value):
    """MPRIS times are microseconds, but players disagree on the type."""
    try:
        return max(0.0, float(value) / 1e6)
    except (TypeError, ValueError):
        return 0.0


class Mpris(QObject):
    changed = Signal(object)   # dict for the player being shown, {} when there is none
    art     = Signal(object)   # cover image bytes for the current track, b"" when none

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active  = None   # bus name of the player being shown
        self._trackid = ""
        self._state   = {}
        self._art_key = None

    def start(self):
        """Begin watching. Connect the signals first: state is only sent when it changes."""
        threading.Thread(target=self._run, daemon=True).start()

    # ── watcher thread ───────────────────────────────────────────────────────
    def _run(self):
        conn = open_dbus_connection("SESSION")
        bus = Proxy(message_bus, conn)
        queue = deque(maxlen=64)
        for iface, member in ((PROPS, "PropertiesChanged"), (PLAYER, "Seeked")):
            rule = MatchRule(type="signal", interface=iface, member=member, path=PATH)
            bus.AddMatch(rule)
            conn.filter(rule, queue=queue).__enter__()   # kept for the thread's life
        while True:
            try:
                self._refresh(conn, bus)
            except Exception:
                log.exception("could not read media players")
            queue.clear()
            try:
                # Position is never signalled, so wake once a second regardless.
                conn.recv_until_filtered(queue, timeout=1.0)
                time.sleep(0.05)   # let a burst of property changes land together
            except TimeoutError:
                pass

    def _refresh(self, conn, bus):
        players = {}
        for name in bus.ListNames()[0]:
            if not name.startswith(PREFIX) or name.endswith(".playerctld"):
                continue
            try:
                props = get_all(conn, name, PATH, PLAYER)
            except Exception:
                continue   # quit since ListNames, or not answering
            meta = {k: v[1] for k, v in props.get("Metadata", {}).items()}
            # Browsers keep an empty, stopped player on the bus between tabs.
            if props.get("PlaybackStatus") != "Stopped" and meta.get("xesam:title"):
                players[name] = props, meta

        playing = [n for n, (p, _) in players.items() if p.get("PlaybackStatus") == "Playing"]
        if self._active not in playing:
            self._active = (playing[0] if playing
                            else self._active if self._active in players
                            else next(iter(players), None))

        state, art_key = {}, None
        if self._active:
            props, meta = players[self._active]
            artist = meta.get("xesam:artist") or ""
            self._trackid = meta.get("mpris:trackid", "")
            state = {
                "title":    str(meta["xesam:title"]),
                "artist":   ", ".join(artist) if isinstance(artist, list) else str(artist),
                "playing":  props.get("PlaybackStatus") == "Playing",
                "position": _seconds(props.get("Position")),
                "length":   _seconds(meta.get("mpris:length")),
                "canNext":  bool(props.get("CanGoNext")),
                "canPrev":  bool(props.get("CanGoPrevious")),
                "canSeek":  bool(props.get("CanSeek")) and bool(self._trackid),
            }
            # Title is part of the key: some players reuse one file for every cover.
            art_key = meta.get("mpris:artUrl", ""), state["title"]

        if state != self._state:
            self._state = state
            self.changed.emit(state)
        if art_key != self._art_key:
            self._art_key = art_key
            threading.Thread(target=self._fetch, args=(art_key,), daemon=True).start()

    def _fetch(self, key):
        data = b""
        url = key[0] if key else ""
        try:
            scheme = urlparse(url).scheme
            if scheme == "file":
                with open(unquote(urlparse(url).path), "rb") as f:
                    data = f.read(ART_LIMIT)
            elif scheme in ("http", "https", "data"):
                with urllib.request.urlopen(url, timeout=5) as reply:
                    data = reply.read(ART_LIMIT)
        except Exception as e:
            log.info("cover art unavailable: %s", e)
        if key == self._art_key:   # still the track on screen
            self.art.emit(data)

    # ── commands (any thread) ────────────────────────────────────────────────
    def send(self, member, sig=None, body=()):
        name = self._active
        if not name:
            return

        def go():
            try:
                with open_dbus_connection("SESSION") as conn:
                    call(conn, name, PATH, PLAYER, member, sig, body)
            except Exception as e:
                log.warning("%s failed: %s", member, e)
        threading.Thread(target=go, daemon=True).start()

    def seek(self, seconds):
        if self._trackid:
            self.send("SetPosition", "ox", (self._trackid, int(seconds * 1e6)))
