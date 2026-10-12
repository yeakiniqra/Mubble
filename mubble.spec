# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Mubble: one self-contained binary, dist/mubble.
#
# The `mubble` package is found through main.py's imports; the QML files are
# data and have to be named. PyInstaller's PySide6 hooks bring Qt's own QML
# modules (QtQuick, QtQuick.Effects, QtQuick.Shapes) along.

import os
import struct
import sys

from PySide6.QtCore import QBuffer, Qt
from PySide6.QtGui import QImage


def windows_icon(png, out, sizes=(16, 20, 24, 32, 40, 48, 64, 128, 256)):
    """The .exe icon, made from the PNG logo at build time. Windows wants an
    .ico holding every size it draws, or the small ones come out blurred."""
    logo = QImage(png)
    images = []
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.WriteOnly)
        logo.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation).save(buffer, "PNG")
        images.append(bytes(buffer.data()))
    # ICONDIR, one 16-byte entry per image, then the PNGs (allowed since Vista).
    offset = 6 + 16 * len(images)
    head = struct.pack("<HHH", 0, 1, len(images))
    for size, data in zip(sizes, images):
        head += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(head + b"".join(images))
    return out


a = Analysis(
    ['main.py'],
    datas=[('mubble/qml', 'mubble/qml')],
    excludes=['PyQt5', 'PyQt6', 'PySide2'],   # never bundle a second Qt
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='mubble',
    upx=False,       # compressed Qt libraries have a history of not loading
    console=False,   # tray app, no terminal window
    # Linux has no icon in the binary; the .deb installs the logo instead.
    icon=windows_icon('assets/logo.png', 'build/mubble.ico') if sys.platform == 'win32' else None,
)
