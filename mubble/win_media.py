"""Follow whichever Windows media session is making sound: a browser tab, Spotify, anything.

The Windows counterpart of mpris.py, over the system media transport controls,
the same sessions the volume flyout shows. Same signals, same commands.
"""

import asyncio
import logging
import threading
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as Manager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status)
from winrt.windows.storage.streams import Buffer, InputStreamOptions

log = logging.getLogger("mubble")

ART_LIMIT = 8 << 20   # bytes; cover art comes from whichever app owns the session
COMMANDS  = {"PlayPause": "try_toggle_play_pause_async",
             "Next":      "try_skip_next_async",
             "Previous":  "try_skip_previous_async"}
EVENTS    = ("media_properties_changed", "playback_info_changed", "timeline_properties_changed")


class Player(QObject):
    changed = Signal(object)   # dict for the session being shown, {} when there is none
    art     = Signal(object)   # cover image bytes for the current track, b"" when none

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loop    = None
        self._active  = None   # app id of the session being shown
        self._session = None
        self._state   = {}
        self._art_key = None
        self._refused = set()   # sessions already reported as not answering

    def start(self):
        """Begin watching. Connect the signals first: state is only sent when it changes."""
        threading.Thread(target=asyncio.run, args=(self._run(),), daemon=True).start()

    # ── watcher thread ───────────────────────────────────────────────────────
    async def _run(self):
        self._loop = asyncio.get_running_loop()
        wake = asyncio.Event()

        def poke(*_):   # WinRT calls this from its own threads
            self._loop.call_soon_threadsafe(wake.set)

        manager = await Manager.request_async()
        manager.add_sessions_changed(poke)
        manager.add_current_session_changed(poke)
        hooked, tokens = None, ()   # the session whose own events wake us
        while True:
            try:
                await self._refresh(manager)
            except Exception:
                log.exception("could not read media sessions")
            # Track and play/pause changes are the session's own events, so the
            # one on screen is followed. Each refresh brings new wrappers; == is
            # the same session underneath.
            if self._session != hooked:
                try:
                    if hooked:
                        for event, token in zip(EVENTS, tokens):
                            getattr(hooked, "remove_" + event)(token)
                except Exception:
                    pass   # that session is gone, and its handlers with it
                hooked = self._session
                tokens = [getattr(hooked, "add_" + event)(poke) for event in EVENTS] if hooked else ()
            wake.clear()
            try:
                # Position is not signalled as it moves, so wake once a second regardless.
                await asyncio.wait_for(wake.wait(), 1.0)
                await asyncio.sleep(0.05)   # let a burst of changes land together
            except TimeoutError:
                pass

    async def _refresh(self, manager):
        sessions = {}
        for session in manager.get_sessions():
            app = session.source_app_user_model_id
            try:
                props = await session.try_get_media_properties_async()
                info = session.get_playback_info()
            except Exception as e:
                if app not in self._refused:
                    self._refused.add(app)
                    log.warning("%s is not answering: %s", app, e)
                continue
            status = info.playback_status
            if status in (Status.CLOSED, Status.STOPPED) or not props.title:
                continue
            # One app can hold several sessions (browser tabs); a playing one wins.
            if app not in sessions or status == Status.PLAYING:
                sessions[app] = session, props, info

        playing = [a for a, (_, _, i) in sessions.items() if i.playback_status == Status.PLAYING]
        if self._active not in playing:
            self._active = (playing[0] if playing
                            else self._active if self._active in sessions
                            else next(iter(sessions), None))

        state, art_key, thumbnail, self._session = {}, None, None, None
        if self._active:
            session, props, info = sessions[self._active]
            self._session = session
            controls = info.controls
            position, length = _timeline(session.get_timeline_properties(),
                                         info.playback_status == Status.PLAYING)
            state = {
                "title":    props.title,
                "artist":   props.artist,
                "playing":  info.playback_status == Status.PLAYING,
                "position": position,
                "length":   length,
                "canNext":  controls.is_next_enabled,
                "canPrev":  controls.is_previous_enabled,
                "canSeek":  controls.is_playback_position_enabled and length > 0,
            }
            # There is no cover URL to key on. Some apps attach the cover a
            # moment after the title, so its arrival counts as a change.
            art_key = self._active, props.title, props.artist, bool(props.thumbnail)
            thumbnail = props.thumbnail

        if state != self._state:
            self._state = state
            self.changed.emit(state)
        if art_key != self._art_key:
            self._art_key = art_key
            asyncio.create_task(self._fetch(art_key, thumbnail))

    async def _fetch(self, key, thumbnail):
        data = b""
        try:
            if thumbnail:
                stream = await thumbnail.open_read_async()
                size = min(stream.size, ART_LIMIT)
                buffer = Buffer(size)
                await stream.read_async(buffer, size, InputStreamOptions.READ_AHEAD)
                data = bytes(buffer)
        except Exception as e:
            log.info("cover art unavailable: %s", e)
        if key == self._art_key:   # still the track on screen
            self.art.emit(data)

    # ── commands (any thread) ────────────────────────────────────────────────
    def send(self, member):
        self._go(lambda session: getattr(session, COMMANDS[member])())

    def seek(self, seconds):
        def to(session):
            start = session.get_timeline_properties().start_time.total_seconds()
            return session.try_change_playback_position_async(int((start + seconds) * 1e7))
        self._go(to)

    def _go(self, command):
        """Run `command(session)` on the watcher's thread and wait for the reply there."""
        async def go():
            if self._session:
                try:
                    await command(self._session)
                except Exception as e:
                    log.warning("media command failed: %s", e)
        if self._loop:
            asyncio.run_coroutine_threadsafe(go(), self._loop)


def _timeline(timeline, playing):
    """(position, length) in seconds. Apps report the position only now and then,
    stamped with the time they did; carry it forward to now while playing."""
    start = timeline.start_time.total_seconds()
    length = timeline.end_time.total_seconds() - start
    if length <= 0:
        return 0.0, 0.0
    position = timeline.position.total_seconds() - start
    if playing:
        position += (datetime.now(timezone.utc) - timeline.last_updated_time).total_seconds()
    return min(max(0.0, position), length), length
