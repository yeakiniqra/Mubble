# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Mubble: one self-contained binary, dist/mubble.
#
# The `mubble` package is found through main.py's imports; the QML files are
# data and have to be named. PyInstaller's PySide6 hooks bring Qt's own QML
# modules (QtQuick, QtQuick.Effects, QtQuick.Shapes) along.

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
)
