<img src="assets/logo.png" width="96" alt="Mubble logo">

# Mubble

A floating glass pill for Linux that shows what is playing, from any app.

YouTube in Chrome, Spotify, Firefox, a local player: if it plays sound and
announces itself to the desktop, Mubble shows it. No per-app setup.

- **Now playing.** Cover, title, artist. Hover to open progress and
  previous / play / next. Click the progress bar to seek. Drag to move.
- **Earbuds.** A short notice when Bluetooth headphones connect, with battery
  level when the device reports one.
- **Edge glow.** The screen edges pulse with the bass, in the colour of the
  cover. Turn it off from the tray icon.

## Run

Needs Python 3.10+, PipeWire (`pw-record`, for the glow) and BlueZ (for earbuds).
Both are standard on current Ubuntu and Fedora.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

Nothing appears until something plays. The tray icon has **Edge glow**,
**Reset position** and **Quit**.

## How it works

| Part | Source |
| --- | --- |
| Track and controls | MPRIS over the session D-Bus (`mubble/mpris.py`) |
| Earbuds | BlueZ over the system D-Bus (`mubble/bluetooth.py`) |
| Bass level | `pw-record` on the default output, FFT of 47-141 Hz (`mubble/audio.py`) |
| Interface | Qt Quick (`mubble/qml/`) |

The glow listens to the sound going **out** to your speakers, never the
microphone, and only while something is playing with the glow turned on.
GNOME may still show its "recording" indicator during that time.

## Limits

- GNOME cannot blur what is behind a window, so the glass is the blurred cover
  with a tint, not a true see-through blur.
- The glow covers the primary screen only.
- On Wayland, Mubble runs through XWayland so it can stay on top and keep its position.
- Linux only for now.

## Develop

`scripts/fake_player.py` is a stand-in media player, so the pill can be worked on
without playing real music. `python -m mubble.audio` runs the bass-detection self-check.
