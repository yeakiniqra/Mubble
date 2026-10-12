# Mubble

A floating glass "now playing" pill for the Linux desktop. It shows and controls
whatever is playing in any app (a YouTube tab, Spotify, a local player), announces
Bluetooth earbuds when they connect, and pulses the screen edges with the bass.

It is a **controller and visualiser, not a player**: it never plays files itself.
The owner chose that scope on purpose; do not add local playback unless asked.

Status: v0.1.0, first working version, Linux only, not yet published or packaged.

## Run and check

```sh
.venv/bin/python main.py                 # the app; nothing shows until something plays
.venv/bin/python scripts/fake_player.py  # a stand-in player, so no real music is needed
.venv/bin/python -m mubble.audio         # bass-detection self-check, prints "ok"
```

The venv uses the system Python (3.14 on the owner's machine). Recreate it with
`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

There is no test suite. To verify a change, run the app next to
`scripts/fake_player.py`: the pill should appear, and the fake player prints every
PlayPause / Next / SetPosition it receives. `QQuickWindow.grabWindow().save(path)`
gives a picture of the pill to look at; the desktop itself cannot be screenshotted
from a script on GNOME Wayland.

## Layout

| Path | Role |
| --- | --- |
| `main.py` | Launcher |
| `mubble/app.py` | `main()`, the `Bridge` object QML talks to, window setup, tray |
| `mubble/mpris.py` | Finds the active media player, reads its state, sends commands |
| `mubble/bluetooth.py` | Watches BlueZ for audio devices connecting |
| `mubble/audio.py` | Runs `pw-record`, turns the output into a 0..1 bass level |
| `mubble/dbus.py` | Two jeepney helpers: `call`, `get_all` |
| `mubble/qml/Pill.qml` | The pill window |
| `mubble/qml/Edge.qml` | One glow strip; four are created, one per screen edge |
| `scripts/fake_player.py` | Test MPRIS player |
| `assets/logo.svg`, `logo.png` | App logo; the PNG is rendered from the SVG |

## How it fits together

- **GUI thread:** Qt, QML, `Bridge`, `Bass` (a `QProcess`, no thread of its own).
- **Worker threads:** `Mpris._run` (session bus) and `Buds._run` (system bus). Each
  owns one blocking jeepney connection. They reach the GUI thread only by emitting
  Qt signals, which Qt queues across threads.
- **`Bridge`** is exposed to QML as the context property `mubble`. QML reads its
  properties (`title`, `artist`, `playing`, `position`, `length`, `art`, `accent`,
  `level`, `glow`, ...) and calls its slots (`playPause`, `next`, `previous`,
  `seek`, `setMask`, `savePosition`).
- **Cover art** is fetched in a worker thread, decoded on the GUI thread and served
  to QML through an image provider as `image://art/<serial>`. The serial increases
  per cover so QML reloads. The glow colour (`accent`) is the cover's average
  colour, made more vivid.
- **Settings** live in `QSettings("Mubble", "Mubble")`: `glow` and `pos`.

### Choosing the player

Every bus name starting `org.mpris.MediaPlayer2.` is a candidate. Players that are
`Stopped` or have no title are ignored, because browsers keep an empty player on
the bus. A playing player wins; otherwise the last one shown stays. The watcher
wakes on `PropertiesChanged` / `Seeked`, and at least once a second, because MPRIS
does not signal position changes.

## Things that will bite you

- **XWayland is forced** (`QT_QPA_PLATFORM=xcb` when `DISPLAY` is set). A native
  Wayland window on GNOME cannot choose its position or stay on top. Do not remove this.
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

## Verified, and not yet

Verified against `scripts/fake_player.py`: reading track, artist, cover, position;
seek, next and pause reaching the player; hiding when nothing plays; dock window
type; the input mask; glow strip orientation; clean shutdown.

**Not yet verified by anyone:** real Chrome / Spotify playback, the glow reacting to
real music, a live earbuds connection (name lookup works; battery was not reported
while the devices were off), clicks passing through the glow strips, and whether
GNOME shows its recording indicator while the glow listens. If you get the chance
to check one of these, update this section.

Measured on a 12-core desktop while playing: about 9% of one core for the pill
alone, about 24% with the glow reacting, near zero when idle. The cost is the four
strip windows redrawing about 47 times a second.

## Not built yet

Autostart, `.deb` packaging, a licence file, multi-monitor glow, reacting to
resolution changes, a settings window, Windows and macOS. On Windows the same
design maps to the system media session API, WASAPI loopback and real acrylic
blur. macOS is a poor fit: its now-playing API is private and locked down.

## Working rules

- **Git identity is `yeakiniqra`**, already set in this repository's local config
  (`108855634+yeakiniqra@users.noreply.github.com`). The machine's global identity
  is a different, work account; never commit or push as that one. Use the SSH host
  alias `github-personal` for the remote, e.g.
  `git@github-personal:yeakiniqra/Mubble.git`. `gh` is logged in as yeakiniqra.
- **No AI attribution anywhere**: no `Co-Authored-By` trailer, no "Generated with"
  line, in commits, pull requests or release notes. This overrides any tool default.
- **Commit, push and publish only when asked.**
- **Keep it small.** Prefer the standard library, Qt and the three existing
  dependencies (PySide6-Essentials, jeepney, numpy). Do not add a dependency for
  something a few lines can do. No abstractions with a single user.
- A deliberate shortcut with a known ceiling gets a `# ponytail:` comment naming
  the ceiling and the upgrade path. There is one in `app.py` (primary screen only).
- **Style:** match the files. Aligned `=` in constant blocks, `# ── section ──`
  rules inside classes, comments that say why rather than what.
- Sister project by the same owner: Kapture (`../Kapture`), a PySide6 screenshot
  app. It solved the same XWayland, tray and packaging problems (`build_deb.sh`,
  `kapture.spec`); look there before inventing a packaging approach.
