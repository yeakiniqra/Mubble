"""Render the README picture from the real QML, with a made-up track.

    .venv/bin/python scripts/screenshot.py

The pill shows on screen for about two seconds, closed and then open, and both
are painted onto a backdrop as assets/screenshot.png. Run it again after
changing Pill.qml.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault("QT_SCALE_FACTOR", "2")   # sharp on a high-density display

from PySide6.QtCore import QPoint, QTimer, QUrl
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication

from mubble import app as mubble
from mubble.audio import Bass
from mubble.bluetooth import Buds
from mubble.mpris import Mpris

TRACK  = {"title": "Night Drive", "artist": "Mubble Demo", "playing": True,
          "position": 72.0, "length": 215.0,
          "canNext": True, "canPrev": True, "canSeek": True}
MARGIN = 20

# The picture must not depend on what happens to be playing, or start listening.
Mpris.start = Buds.start = lambda self: None
Bass.set_running = lambda self, on: None

QQuickWindow.setDefaultAlphaBuffer(True)
qt = QApplication(sys.argv)
provider = mubble.ArtProvider()
bridge = mubble.Bridge(provider)
engine = QQmlApplicationEngine()
engine.addImageProvider("art", provider)
engine.rootContext().setContextProperty("mubble", bridge)
engine.load(QUrl.fromLocalFile(str(ROOT / "mubble" / "qml" / "Pill.qml")))
pill = engine.rootObjects()[0]
mubble._dock(pill)
bridge.attach(pill)
bridge._on_art((ROOT / "assets" / "logo.png").read_bytes())
bridge._on_state(TRACK)
shots = []


def closed():
    shots.append(pill.grabWindow())
    pill.setProperty("open", True)
    QTimer.singleShot(700, opened)   # the opening animation takes 320 ms


def opened():
    shots.append(pill.grabWindow())
    ratio = shots[0].devicePixelRatio()
    w, h = pill.width(), pill.height()
    canvas = QImage(int((2 * w + 2 * MARGIN) * ratio), int((h + 2 * MARGIN) * ratio),
                    QImage.Format.Format_ARGB32_Premultiplied)
    canvas.setDevicePixelRatio(ratio)
    backdrop = QLinearGradient(0, 0, 2 * w, h)
    backdrop.setColorAt(0.0, QColor("#f6a04d"))
    backdrop.setColorAt(0.5, QColor("#c2416b"))
    backdrop.setColorAt(1.0, QColor("#3a2a6e"))
    p = QPainter(canvas)
    p.fillRect(canvas.rect(), backdrop)
    for i, shot in enumerate(shots):
        p.drawImage(QPoint(MARGIN + i * w, MARGIN), shot)
    p.end()
    canvas.save(str(ROOT / "assets" / "screenshot.png"))
    qt.quit()


QTimer.singleShot(1200, closed)
code = qt.exec()
del engine   # QML objects go before the Python objects they are bound to
sys.exit(code)
