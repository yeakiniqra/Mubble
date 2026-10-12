# Mubble

A floating glass "now playing" pill for the Linux and Windows desktop. It shows and controls
whatever is playing in any app (a YouTube tab, Spotify, a local player), announces
Bluetooth earbuds when they connect, and pulses the screen edges with the bass.

It is a **controller and visualiser, not a player**: it never plays files itself.
The owner chose that scope on purpose; do not add local playback unless asked.

Status: v0.1.0, first working version, Linux and Windows (ported 2026-10-12).
`build_deb.sh` makes a `.deb`, `pyinstaller mubble.spec` on Windows makes
`dist/mubble.exe`; nothing is published yet.

The owner works on both machines: Linux keeps its venv in `.venv/`, Windows in
`venv/` (`venv\Scripts\python.exe`). Commands below are written the Linux way.

## Run and check

```sh
.venv/bin/python main.py                 # the app; nothing shows until something plays
.venv/bin/python scripts/fake_player.py  # a stand-in player, so no real music is needed
.venv/bin/python -m mubble.audio         # bass-detection self-check, prints "ok"
```

The venv uses the system Python (3.14 on the owner's machine). Recreate it with
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

```sh
bash build_deb.sh                        # mubble_<version>_<arch>.deb, about a minute
.venv/bin/python scripts/screenshot.py   # redraws assets/screenshot.png for the README
```

On Windows:

```sh
venv/Scripts/python main.py                      # the app
venv/Scripts/python scripts/fake_player_win.py   # stand-in session; plays a quiet kick
venv/Scripts/python -m PyInstaller --noconfirm mubble.spec   # dist/mubble.exe, ~2 minutes
```

`build_deb.sh` needs PyInstaller in the venv (`.venv/bin/pip install pyinstaller`).
It is a build tool, so it stays out of `requirements.txt`. To try a package without
installing it: `dpkg-deb -x mubble_*.deb <dir>` and run `<dir>/usr/bin/mubble`.

There is no test suite. To verify a change, run the app next to
`scripts/fake_player.py`: the pill should appear, and the fake player prints every
PlayPause / Next / SetPosition it receives. `QQuickWindow.grabWindow().save(path)`
gives a picture of the pill to look at; the desktop itself cannot be screenshotted
from a script on GNOME Wayland.

On Windows the stand-in is `scripts/fake_player_win.py` (its docstring lists four
extra winrt packages it needs). It really plays: a quiet 70 Hz kick through the
speakers, which is what the glow listens to. There the whole desktop can be
grabbed with `QGuiApplication.primaryScreen().grabWindow(0)`; crop the image
afterwards, since the x/y arguments of `grabWindow` miss on a two-monitor layout.
`WindowFromPoint` (ctypes) says which window would take a click at a point,
which checks the input mask without moving the owner's mouse.

## Layout

| Path | Role |
| --- | --- |
| `main.py` | Launcher |
| `mubble/app.py` | `main()`, the `Bridge` object QML talks to, window setup, tray |
| `mubble/mpris.py` | Finds the active media player, reads its state, sends commands |
| `mubble/bluetooth.py` | Watches BlueZ for audio devices connecting |
| `mubble/audio.py` | Runs `pw-record`, turns the output into a 0..1 bass level |
| `mubble/dbus.py` | Two jeepney helpers: `call`, `get_all` |
| `mubble/win_media.py` | Windows `mpris.py`: system media sessions, same signals and commands |
| `mubble/win_bluetooth.py` | Windows `bluetooth.py`: paired devices whose connected flag turns on |
| `mubble/win_audio.py` | Windows audio: WASAPI loopback via ctypes, feeding `audio.Bass` |
| `mubble/qml/Pill.qml` | The pill window |
| `mubble/qml/Edge.qml` | One glow strip; four are created, one per screen edge |
| `scripts/fake_player.py` | Test MPRIS player |
| `scripts/fake_player_win.py` | Test Windows media session, playing a quiet kick |
| `scripts/screenshot.py` | Renders `assets/screenshot.png` from the real QML |
| `mubble.spec` | PyInstaller recipe: one binary, QML files bundled as data; on Windows also builds the `.exe` icon from `logo.png` |
| `build_deb.sh` | Runs PyInstaller, then assembles and builds the `.deb` |
| `assets/logo.svg`, `logo.png` | App logo; the PNG is rendered from the SVG |

## How it fits together

- **GUI thread:** Qt, QML, `Bridge`, `Bass` (a `QProcess`, no thread of its own).
- **Worker threads:** `Mpris._run` (session bus) and `Buds._run` (system bus). Each
  owns one blocking jeepney connection. They reach the GUI thread only by emitting
  Qt signals, which Qt queues across threads.
- **One platform per run.** `app.py` imports either the Linux trio (`mpris`,
  `bluetooth`, `audio`) or the Windows one (`win_media`, `win_bluetooth`,
  `win_audio`) under the same names, `Player`, `Buds`, `Bass`, with the same
  signals and methods. `Bridge` never asks which it got.
- **On Windows** the two watchers each run an asyncio loop in their thread, since
  pywinrt's calls are awaitables; WinRT event callbacks arrive on WinRT's own
  threads and only wake that loop. Commands from the GUI are handed to the
  watcher's loop with `run_coroutine_threadsafe`. `win_audio.Bass` subclasses
  `audio.Bass` and only swaps the source: on each tick it reads what WASAPI has
  captured instead of what `pw-record` printed.
- **`Bridge`** is exposed to QML as the context property `mubble`. QML reads its
  properties (`title`, `artist`, `playing`, `position`, `length`, `art`, `accent`,
  `level`, `glow`, ...) and calls its slots (`playPause`, `next`, `previous`,
  `seek`, `setMask`, `savePosition`).
- **Cover art** is fetched in a worker thread, decoded on the GUI thread and served
  to QML through an image provider as `image://art/<serial>`. The serial increases
  per cover so QML reloads. The glow colour (`accent`) is the cover's average
  colour, made more vivid.
- **Settings** live in `QSettings("Mubble", "Mubble")`: `glow` and `pos`.
  **Start at login** is not one of them: the setting is whether
  `~/.config/autostart/mubble.desktop` exists (on Windows: a `Mubble` value under
  `HKCU\...\CurrentVersion\Run`). Its command is the packaged binary, or this
  python (`pythonw.exe` on Windows) plus `main.py` when run from source, so it
  goes stale if the source folder moves.
- **The glow level** is read every `TICK` (33 ms) by a timer in `Bass`, not each
  time `pw-record` delivers sound. The two decay factors in `_measure` are per
  tick; change `TICK` and they need rescaling.

### Choosing the player

Every bus name starting `org.mpris.MediaPlayer2.` is a candidate. Players that are
`Stopped` or have no title are ignored, because browsers keep an empty player on
the bus. A playing player wins; otherwise the last one shown stays. The watcher
wakes on `PropertiesChanged` / `Seeked`, and at least once a second, because MPRIS
does not signal position changes.

Windows follows the same rules over media sessions, keyed by the app's id
(`source_app_user_model_id`); several sessions of one app (browser tabs) count
as one, the playing one preferred. It wakes on the manager's session changes and
on the shown session's own events. An app reports its position only now and then,
with the time it did; `_timeline` carries it forward to now while playing.

## Things that will bite you

- **XWayland is forced** (`QT_QPA_PLATFORM=xcb` when `DISPLAY` is set). A native
  Wayland window on GNOME cannot choose its position or stay on top. Do not remove this.
- **Do not launch from the VS Code terminal when testing against a snap player.**
  VS Code is a snap, so anything started from its terminal carries the AppArmor
  label `snap.code.code`, and snap players such as Spotify refuse its D-Bus calls
  (`AccessDenied`). `_refresh` treats that as a player that is not answering, so the
  pill just stays hidden; the log names the player once. Start it unconfined instead:
  `systemd-run --user --unit=mubble-test --collect --working-directory="$PWD" "$PWD/.venv/bin/python" main.py`
  (logs: `journalctl --user -u mubble-test -f`). Check a process with
  `cat /proc/<pid>/attr/current`.
- **Windows are X11 "dock" type.** `_dock()` sets the dynamic property
  `_q_xcb_wm_window_type` to `0x4` and it must run **before** the native window is
  created, so each QML `Window` must start invisible. Dock type is what gives: every
  workspace, above normal windows, below fullscreen ones, absent from Alt-Tab.
  Check with `xprop -id <winId> _NET_WM_WINDOW_TYPE`.
- **The window manager will not move a dock window.** Dragging is done by hand in
  `Pill.qml`'s `DragHandler`; `startSystemMove()` does nothing here.
- **The pill's window is bigger than the pill** (room for the shadow and the opened
  size). `Bridge.setMask` restricts input to the pill's rectangle; without it the
  transparent margin swallows clicks meant for the app underneath.
- **Call `start()` only after connecting signals.** `Mpris` emits state only when it
  changes, so a first emission that nobody receives is never repeated.
- **jeepney returns variants as `(signature, value)` tuples.** `get_all` strips the
  outer one; `Metadata` values need `[1]` again. PySide6's own QtDBus cannot decode
  `a{sv}`, which is why jeepney is used.
- **One jeepney connection per thread.** Commands from the GUI open a short-lived
  connection in their own thread rather than share the watcher's.
- **`QLockFile.tryLock` needs an argument** in PySide6: `tryLock(0)`.
- **Stop `pw-record` with `Bass.stop()` at exit.** It waits for the process; a bare
  `kill()` leaves Qt warning that the process was destroyed while running.
- **`pw-record` flags that matter:** `-P '{ stream.capture.sink = true }'` taps the
  speakers instead of the microphone, and `--raw ... -` writes headerless PCM to stdout.
- **No real blur on GNOME.** Mutter offers apps no way to blur what is behind them.
  The glass look is the blurred cover (`MultiEffect`) under a tint, a sheen and a
  hairline border. Do not spend time looking for a blur API.
- **`MultiEffect` sources and masks** must be `visible: false` with
  `layer.enabled: true`.
- **The primary screen may not start at x = 0.** On the owner's machine it is the
  right-hand monitor at x = 1920. Always add the screen's origin.

On Windows:

- **Import Qt before winrt.** winrt ships an older `msvcp140.dll` (14.29) than
  PySide6 (14.44); whichever loads first is used by both, and Qt segfaults on the
  old one. `app.py` imports Qt at the top, so the app is safe; a test script that
  imports a `win_*` module or winrt first is not.
- **pywinrt 3 keeps static methods on the metaclass.** `dir(BluetoothDevice)`
  does not list `from_id_async`; `dir(type(BluetoothDevice))` does. Overloads get
  long names, e.g. `create_watcher_with_kind_aqs_filter_and_additional_properties`.
- **Session wrappers are new objects on every `get_sessions()`;** `==` compares the
  session underneath, `is` never matches. Events are hooked on the shown session
  only, and moved when it changes, so handlers do not pile up.
- **`setMask` clips drawing on Windows,** not only input as on X11, and a layered
  Qt window catches clicks on its transparent pixels too (checked with
  `WindowFromPoint`), so the mask is still needed. The pill's drop shadow is
  turned off there; the mask would cut it off square.
- **Topmost is above fullscreen video on Windows**, unlike a GNOME dock. `Bridge`
  polls `SHQueryUserNotificationState` once a second and sets `covered`, which
  hides the pill and the strips and stops listening.
- **COM through ctypes uses `CFUNCTYPE`, not `WINFUNCTYPE`:** a `WINFUNCTYPE`
  prototype rejects extra arguments, and 64-bit Windows has one calling
  convention anyway. Flags above `0x7fffffff` must be wrapped (`DWORD(...)`).
- **WASAPI loopback delivers nothing while nothing plays.** `win_audio.Bass` treats
  an empty read as a frame of silence, or the glow would freeze at its last level.
  It reopens when the default output changes (checked every `RECHECK` ticks).
- **Qt's `RuntimeLocation` is the home folder on Windows,** so the lock file goes
  in Temp there.

## Verified, and not yet

Verified against `scripts/fake_player.py`: reading track, artist, cover, position;
seek, next and pause reaching the player; hiding when nothing plays; dock window
type; the input mask; glow strip orientation; clean shutdown; the packaged binary
from the `.deb` starting, finding the player and starting the recorder.

The owner tried it with real Spotify (the snap) on 2026-10-12 and was satisfied
overall; which of the items below that covered was not recorded.

**Not yet verified by anyone:** real Chrome / Spotify playback, the glow reacting to
real music, a live earbuds connection (name lookup works; battery was not reported
while the devices were off), clicks passing through the glow strips, and whether
GNOME shows its recording indicator while the glow listens. If you get the chance
to check one of these, update this section.

Measured on a 12-core desktop while playing: about 9% of one core for the pill
alone, about 24% with the glow reacting, near zero when idle. The cost is the four
strip windows redrawing about 47 times a second. Readings have since been cut to
30 a second (`TICK`); the cost has not been measured again.

**Windows, verified on 2026-10-12** (Windows 11, two monitors) against
`scripts/fake_player_win.py`: track, artist, cover and position; PlayPause, Next
and seek reaching the session; the loopback level jumping on each kick and
decaying between; the strips pulsing on the real desktop; the pill hiding behind
a fullscreen window and returning; clicks outside the pill's rectangle reaching
the window below; the second-instance lock; the Run key written and removed;
`pyinstaller mubble.spec` building a `dist/mubble.exe` that shows the pill and
drives the glow; `requirements.txt` alone installing into a fresh venv. About 1.6%
of one core while playing with the glow reacting.

**Windows, not yet verified:** real Spotify / browser sessions, a live earbuds
connection (that machine had no paired devices; battery is never reported, see the
`ponytail` in `win_bluetooth.py`), the tray icon on a light taskbar, hover and
dragging by a real mouse, and the Linux build after the port. The Linux code paths
changed only by renaming `Bridge.mpris` to `Bridge.player` and the imports in
`app.py` and `scripts/screenshot.py`; run it there once.

## Not built yet

Multi-monitor glow, reacting to resolution changes, a settings window and macOS.
Installing the `.deb` with `apt` has not been tried, only running the binary
inside it. macOS is a poor fit: its now-playing API is private and locked down.

For Windows: an installer, code signing (unsigned, the exe meets SmartScreen's
"Windows protected your PC" on first run), a release build on a GitHub Actions Windows runner as Kapture
does (PyInstaller cannot build an `.exe` from Linux), the earbuds battery level,
and real acrylic blur, which DWM offers only for a whole window, not the pill
inside one.

## Working rules

- **Git identity is `yeakiniqra`**, already set in this repository's local config
  (`108855634+yeakiniqra@users.noreply.github.com`). The machine's global identity
  is a different, work account; never commit or push as that one. Use the SSH host
  alias `github-personal` for the remote, e.g.
  `git@github-personal:yeakiniqra/Mubble.git`. `gh` is logged in as yeakiniqra.
- **No AI attribution anywhere**: no `Co-Authored-By` trailer, no "Generated with"
  line, in commits, pull requests or release notes. This overrides any tool default.
- **Commit, push and publish only when asked.**
- **Keep it small.** Prefer the standard library, Qt and the existing
  dependencies (PySide6-Essentials, numpy, jeepney on Linux, the winrt packages on
  Windows, pinned together at one version). Do not add a dependency for something
  a few lines can do. No abstractions with a single user.
- A deliberate shortcut with a known ceiling gets a `# ponytail:` comment naming
  the ceiling and the upgrade path. There are two: `app.py` (primary screen only)
  and `win_bluetooth.py` (no battery level).
- **Style:** match the files. Aligned `=` in constant blocks, `# ── section ──`
  rules inside classes, comments that say why rather than what.
- Sister project by the same owner: Kapture (`../Kapture`), a PySide6 screenshot
  app. It solved the same XWayland, tray and packaging problems (`build_deb.sh`,
  `kapture.spec`); look there before inventing a packaging approach.
