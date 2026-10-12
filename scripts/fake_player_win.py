"""A stand-in media session for Windows, for working on Mubble without real music.

    venv\\Scripts\\python scripts\\fake_player_win.py [cover-image]

Plays a quiet 70 Hz kick, twice a second, so the edge glow has something to
react to. Shows up in the system media controls as a playing track, and prints
every play, pause, next and seek it receives. Needs, beyond requirements.txt:

    pip install winrt-Windows.Media winrt-Windows.Media.Playback
                winrt-Windows.Media.Core winrt-Windows.Storage
"""

import asyncio
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from winrt.windows.media import MediaPlaybackType
from winrt.windows.media.core import MediaSource
from winrt.windows.media.playback import MediaPlaybackItem, MediaPlayer, MediaCommandEnablingRule
from winrt.windows.storage import StorageFile
from winrt.windows.storage.streams import RandomAccessStreamReference

RATE   = 48000
TITLES = ["Midnight City (Extended Version With A Very Long Title)", "Second Song"]
VOLUME = 0.15


def kick_loop():
    """Twenty seconds of sound with a decaying 70 Hz kick every half second."""
    t = np.arange(RATE // 2) / RATE
    kick = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 9)
    pcm = (np.tile(kick, 40) * 20000).astype(np.int16)
    path = Path(tempfile.gettempdir()) / "mubble-kick.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


async def main():
    cover = Path(sys.argv[1] if len(sys.argv) > 1
                 else Path(__file__).parent.parent / "assets" / "logo.png").resolve()
    audio = await StorageFile.get_file_from_path_async(str(kick_loop()))
    thumb = RandomAccessStreamReference.create_from_file(
        await StorageFile.get_file_from_path_async(str(cover)))

    player = MediaPlayer()
    player.volume = VOLUME
    player.is_looping_enabled = True
    track = 0

    def show():
        item = MediaPlaybackItem(MediaSource.create_from_storage_file(audio))
        props = item.get_display_properties()
        props.type = MediaPlaybackType.MUSIC
        props.music_properties.title = TITLES[track % len(TITLES)]
        props.music_properties.artist = "M83, Guest"
        props.thumbnail = thumb
        item.apply_display_properties(props)
        player.source = item
        player.play()

    def on_next(_manager, _args):
        nonlocal track
        track += 1
        print("Next", flush=True)
        loop.call_soon_threadsafe(show)

    loop = asyncio.get_running_loop()
    commands = player.command_manager
    commands.next_behavior.enabling_rule = MediaCommandEnablingRule.ALWAYS
    commands.add_next_received(on_next)
    commands.add_play_received(lambda *_: print("Play", flush=True))
    commands.add_pause_received(lambda *_: print("Pause", flush=True))
    commands.add_position_received(
        lambda _m, args: print("SetPosition", args.position, flush=True))
    show()
    print("playing as a Windows media session - Ctrl+C to stop", flush=True)
    await asyncio.Event().wait()


asyncio.run(main())
