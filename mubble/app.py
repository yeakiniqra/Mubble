"""Application wiring: Qt objects on the GUI thread, D-Bus watchers on their own."""

import logging
import math
import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import (Property, QLockFile, QObject, QPoint, QSettings,
                            QStandardPaths, Qt, QUrl, Signal, Slot)
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPixmap, QRegion
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickImageProvider, QQuickWindow
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import APP_NAME
from .audio import Bass
from .bluetooth import Buds
from .mpris import Mpris

log = logging.getLogger("mubble")

ACCENT   = "#8ab4ff"   # glow colour when the cover has none to offer
EDGE     = 64          # thickness of each glow strip, px
TOP_GAP  = 36          # default distance from the top of the screen, clears the GNOME bar
XCB_DOCK = 0x4         # QXcbWindow::WindowType::Dock


def _dock(window):
    """Ask the X11 window manager to treat `window` as a panel: on every
    workspace, above normal windows, below fullscreen ones, out of Alt-Tab.
    Must run before the native window exists; other platforms ignore it."""
    window.setProperty("_q_xcb_wm_window_type", XCB_DOCK)
    window.create()


def _autostart():
    config = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    return Path(config) / "autostart" / "mubble.desktop"


def _set_autostart(on):
    """Start with the desktop session, or stop. The file itself is the setting."""
    entry = _autostart()
    if not on:
        entry.unlink(missing_ok=True)
        return
    # A packaged build is its own program; from source it is this python and main.py.
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        command.append(str(Path(sys.argv[0]).resolve()))
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\n"
                     % (APP_NAME, " ".join('"%s"' % part for part in command)))


def _accent_of(image):
    """A vivid version of the cover's average colour."""
    c = image.scaled(1, 1, Qt.AspectRatioMode.IgnoreAspectRatio,
                     Qt.TransformationMode.SmoothTransformation).pixelColor(0, 0)
    if c.hsvHue() < 0 or c.hsvSaturationF() < 0.08:
        return QColor(ACCENT)   # greyscale cover
    return QColor.fromHsvF(c.hsvHueF(), min(1.0, max(0.45, c.hsvSaturationF() * 1.6)), 0.95)


def _tray_icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(Qt.GlobalColor.white)
    for i, height in enumerate((22, 44, 32, 14)):
        p.drawRoundedRect(8 + i * 13, (64 - height) // 2, 8, height, 4, 4)
    p.end()
    return QIcon(pixmap)


class ArtProvider(QQuickImageProvider):
    """Serves the current cover to QML as image://art/<serial>."""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.image = QImage()

    def requestImage(self, _id, _size, _requested):
        return self.image


class Bridge(QObject):
    """Everything the QML needs, as the context property `mubble`."""

    stateChanged = Signal()
    artChanged   = Signal()
    levelChanged = Signal()
    glowChanged  = Signal()
    toasted      = Signal(str)

    def __init__(self, provider):
        super().__init__()
        self._provider = provider
        self._settings = QSettings(APP_NAME, APP_NAME)
        self._glow     = self._settings.value("glow", True, type=bool)
        self._state    = {}
        self._serial   = 0
        self._has_art  = False
        self._accent   = QColor(ACCENT)
        self._level    = 0.0
        self._window   = None
        self._mask     = QRegion()

        self.bass = Bass(self)
        self.bass.level.connect(self._on_level)
        self.mpris = Mpris(self)
        self.mpris.changed.connect(self._on_state)
        self.mpris.art.connect(self._on_art)
        self.mpris.start()
        self.buds = Buds(self)
        self.buds.connected.connect(self._on_buds)
        self.buds.start()

    # ── state for QML ────────────────────────────────────────────────────────
    hasTrack = Property(bool,  lambda s: bool(s._state),                 notify=stateChanged)
    title    = Property(str,   lambda s: s._state.get("title", ""),      notify=stateChanged)
    artist   = Property(str,   lambda s: s._state.get("artist", ""),     notify=stateChanged)
    playing  = Property(bool,  lambda s: s._state.get("playing", False), notify=stateChanged)
    position = Property(float, lambda s: s._state.get("position", 0.0),  notify=stateChanged)
    length   = Property(float, lambda s: s._state.get("length", 0.0),    notify=stateChanged)
    canNext  = Property(bool,  lambda s: s._state.get("canNext", False), notify=stateChanged)
    canPrev  = Property(bool,  lambda s: s._state.get("canPrev", False), notify=stateChanged)
    canSeek  = Property(bool,  lambda s: s._state.get("canSeek", False), notify=stateChanged)
    art      = Property(str,   lambda s: f"image://art/{s._serial}" if s._has_art else "",
                        notify=artChanged)
    accent   = Property(QColor, lambda s: s._accent, notify=artChanged)
    level    = Property(float,  lambda s: s._level,  notify=levelChanged)

    def _get_glow(self):
        return self._glow

    def set_glow(self, on):
        if on != self._glow:
            self._glow = on
            self._settings.setValue("glow", on)
            self.glowChanged.emit()
            self._sync_capture()

    glow = Property(bool, _get_glow, set_glow, notify=glowChanged)

    def _sync_capture(self):
        # Listen only while there is something to react to.
        self.bass.set_running(self._glow and self._state.get("playing", False))

    def _on_state(self, state):
        self._state = state
        self.stateChanged.emit()
        self._sync_capture()

    def _on_art(self, data):
        image = QImage.fromData(data) if data else QImage()
        if image.width() > 512:
            image = image.scaledToWidth(512, Qt.TransformationMode.SmoothTransformation)
        self._provider.image = image
        self._has_art = not image.isNull()
        self._accent = _accent_of(image) if self._has_art else QColor(ACCENT)
        self._serial += 1   # new URL, so QML reloads
        self.artChanged.emit()

    def _on_level(self, level):
        self._level = level
        self.levelChanged.emit()

    def _on_buds(self, name, battery):
        self.toasted.emit(f"{name} · {battery}%" if battery >= 0 else f"{name} connected")

    # ── actions from QML ─────────────────────────────────────────────────────
    @Slot()
    def playPause(self):
        self.mpris.send("PlayPause")

    @Slot()
    def next(self):
        self.mpris.send("Next")

    @Slot()
    def previous(self):
        self.mpris.send("Previous")

    @Slot(float)
    def seek(self, fraction):
        self.mpris.seek(min(1.0, max(0.0, fraction)) * self._state.get("length", 0.0))

    @Slot(float, float, float, float)
    def setMask(self, x, y, width, height):
        """Only the pill takes clicks; the rest of its window lets them through."""
        self._mask = QRegion(math.floor(x), math.floor(y), math.ceil(width), math.ceil(height))
        if self._window:
            self._window.setMask(self._mask)

    @Slot(int, int)
    def savePosition(self, x, y):
        self._settings.setValue("pos", QPoint(x, y))

    # ── the pill window ──────────────────────────────────────────────────────
    def attach(self, window):
        self._window = window
        window.setMask(self._mask)
        pos = self._settings.value("pos")
        centre = pos + QPoint(window.width() // 2, 40) if isinstance(pos, QPoint) else None
        if centre is not None and QGuiApplication.screenAt(centre):
            window.setPosition(pos)
        else:
            self.reset_position()

    def reset_position(self):
        screen = QGuiApplication.primaryScreen().geometry()
        pos = QPoint(screen.x() + (screen.width() - self._window.width()) // 2,
                     screen.y() + TOP_GAP)
        self._window.setPosition(pos)
        self._settings.remove("pos")


def main():
    # GNOME Wayland gives a native client no say over where its window sits or
    # how it stacks. Under XWayland the pill stays where it is put, above windows.
    if os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    QQuickWindow.setDefaultAlphaBuffer(True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    runtime = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.RuntimeLocation)
    lock = QLockFile(os.path.join(runtime, "mubble.lock"))
    if not lock.tryLock(0):
        log.info("already running")
        return 0

    provider = ArtProvider()
    bridge = Bridge(provider)
    app.aboutToQuit.connect(bridge.bass.stop)

    engine = QQmlApplicationEngine()
    engine.addImageProvider("art", provider)
    engine.rootContext().setContextProperty("mubble", bridge)
    qml = Path(__file__).parent / "qml"
    engine.load(QUrl.fromLocalFile(str(qml / "Pill.qml")))
    if not engine.rootObjects():
        return 1
    pill = engine.rootObjects()[0]
    _dock(pill)
    bridge.attach(pill)

    # Four thin strips instead of one screen-sized window: the compositor only
    # has to blend the edges, and nothing sits over the middle of the screen.
    # ponytail: primary screen only, geometry read once; rebuild on QScreen
    # signals when multi-monitor or resolution changes matter.
    screen = app.primaryScreen().geometry()
    strip = QQmlComponent(engine, QUrl.fromLocalFile(str(qml / "Edge.qml")))
    edges = []
    for side, rect in {
        "top":    (screen.x(), screen.y(), screen.width(), EDGE),
        "bottom": (screen.x(), screen.bottom() + 1 - EDGE, screen.width(), EDGE),
        "left":   (screen.x(), screen.y(), EDGE, screen.height()),
        "right":  (screen.right() + 1 - EDGE, screen.y(), EDGE, screen.height()),
    }.items():
        window = strip.createWithInitialProperties({"side": side})
        if not window:
            log.error("edge glow unavailable: %s", strip.errorString())
            break
        _dock(window)
        window.setGeometry(*rect)
        edges.append(window)

    tray = QSystemTrayIcon(_tray_icon())
    menu = QMenu()
    glow = menu.addAction("Edge glow")
    glow.setCheckable(True)
    glow.setChecked(bridge.glow)
    glow.toggled.connect(bridge.set_glow)
    login = menu.addAction("Start at login")
    login.setCheckable(True)
    login.setChecked(_autostart().exists())
    login.toggled.connect(_set_autostart)
    menu.addAction("Reset position", bridge.reset_position)
    menu.addSeparator()
    menu.addAction("Quit", app.quit)
    tray.setContextMenu(menu)
    tray.setToolTip(APP_NAME)
    tray.show()

    code = app.exec()
    # QML objects go before the Python objects they are bound to.
    edges.clear()
    del strip, engine
    return code
