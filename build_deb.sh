#!/usr/bin/env bash
# build_deb.sh: builds mubble_<version>_<arch>.deb
# Usage: bash build_deb.sh        (needs: .venv/bin/pip install pyinstaller)
set -euo pipefail
umask 022   # package files must not be group-writable
cd "$(dirname "$0")"

# ─── Config (VERSION is read from mubble/__init__.py) ─────────────────────────
PKG_NAME="mubble"
VERSION=$(grep -oP 'VERSION\s*=\s*"\K[^"]+' mubble/__init__.py)
DEVELOPER="Yeakin Iqra"
SUMMARY="Floating glass now-playing pill for whatever is making sound"
HOMEPAGE="https://github.com/yeakiniqra/Mubble"
# Reverse-DNS AppStream id. The desktop file, the icons and the metainfo file are
# all named after it; that is how App Center ties them together.
APP_ID="io.github.yeakiniqra.Mubble"
ARCH=$(dpkg --print-architecture)
DEB_DIR="${PKG_NAME}_${VERSION}_${ARCH}"

# ─── Step 1: binary ───────────────────────────────────────────────────────────
echo "[1/3] Building dist/mubble with PyInstaller..."
.venv/bin/python -m PyInstaller --noconfirm mubble.spec

# ─── Step 2: package tree ─────────────────────────────────────────────────────
echo "[2/3] Assembling ${DEB_DIR}..."
rm -rf "${DEB_DIR}"
install -D -m 755 dist/mubble     "${DEB_DIR}/usr/bin/${PKG_NAME}"
install -D -m 644 assets/logo.png "${DEB_DIR}/usr/share/icons/hicolor/512x512/apps/${APP_ID}.png"
install -D -m 644 assets/logo.svg "${DEB_DIR}/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
mkdir -p "${DEB_DIR}/DEBIAN" "${DEB_DIR}/usr/share/applications" \
         "${DEB_DIR}/usr/share/metainfo" "${DEB_DIR}/usr/share/doc/${PKG_NAME}"

# App menu entry. Starting at login is the user's choice, made from the tray
# menu, so no autostart entry is installed here.
cat > "${DEB_DIR}/usr/share/applications/${APP_ID}.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Mubble
GenericName=Now Playing
Comment=${SUMMARY}
Exec=${PKG_NAME}
Icon=${APP_ID}
Categories=AudioVideo;Audio;
Keywords=music;now playing;media;mpris;spotify;
Terminal=false
StartupNotify=false
EOF

# AppStream metainfo: what App Center shows for the icon, developer and licence.
cat > "${DEB_DIR}/usr/share/metainfo/${APP_ID}.metainfo.xml" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>${APP_ID}</id>
  <metadata_license>MIT</metadata_license>
  <project_license>MIT</project_license>
  <name>Mubble</name>
  <summary>${SUMMARY}</summary>
  <developer id="io.github.yeakiniqra">
    <name>${DEVELOPER}</name>
  </developer>
  <description>
    <p>
      Mubble is a floating glass pill that shows what is playing in any app:
      a browser tab, Spotify, a local player. It controls the player, it does
      not play anything itself.
    </p>
    <ul>
      <li>Cover, title and artist; hover for progress, previous, play and next</li>
      <li>A short notice when Bluetooth headphones connect</li>
      <li>Screen edges that pulse with the bass, in the colour of the cover</li>
    </ul>
  </description>
  <launchable type="desktop-id">${APP_ID}.desktop</launchable>
  <categories>
    <category>AudioVideo</category>
    <category>Audio</category>
  </categories>
  <url type="homepage">${HOMEPAGE}</url>
  <url type="bugtracker">${HOMEPAGE}/issues</url>
  <content_rating type="oars-1.1"/>
  <releases>
    <release version="${VERSION}" date="$(date +%Y-%m-%d)"/>
  </releases>
</component>
EOF

# Debian machine-readable copyright, with the licence text indented as it requires.
{
    cat << EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: ${PKG_NAME}
Source: ${HOMEPAGE}

Files: *
Copyright: $(date +%Y) ${DEVELOPER}
License: MIT
EOF
    tail -n +5 LICENSE | sed -e 's/^$/./' -e 's/^/ /'
} > "${DEB_DIR}/usr/share/doc/${PKG_NAME}/copyright"

# Depends: the system libraries Qt's xcb plugin loads at run time. PyInstaller
# does not bundle them, and without one Qt dies with "could not load the Qt
# platform plugin xcb" instead of apt naming what is missing.
# Recommends: the edge glow needs pw-record, the earbuds notice needs BlueZ.
# Mubble runs without either.
cat > "${DEB_DIR}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Maintainer: ${DEVELOPER} <108855634+yeakiniqra@users.noreply.github.com>
Installed-Size: $(du -sk --exclude=DEBIAN "${DEB_DIR}" | cut -f1)
Depends: libc6, libxcb-xinerama0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-cursor0, libxcb-shape0, libxcb-xkb1, libxkbcommon-x11-0, libfontconfig1, libegl1, libgl1, libdbus-1-3
Recommends: pipewire-bin, bluez
Homepage: ${HOMEPAGE}
Description: ${SUMMARY}
 Mubble shows and controls what is playing in any app that announces itself
 over MPRIS: a browser tab, Spotify, a local player. It is a controller and
 visualiser, not a player.
 .
 It also announces Bluetooth headphones as they connect, and can pulse the
 screen edges with the bass in the colour of the cover.
EOF

cat > "${DEB_DIR}/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    gtk-update-icon-cache -f -t /usr/share/icons/hicolor 2>/dev/null || true
    update-desktop-database /usr/share/applications 2>/dev/null || true
fi
EOF

# Stop a running copy first, or the old binary keeps running after an upgrade.
cat > "${DEB_DIR}/DEBIAN/prerm" << 'EOF'
#!/bin/sh
set -e
pkill -x mubble 2>/dev/null || true
EOF
chmod 755 "${DEB_DIR}/DEBIAN/postinst" "${DEB_DIR}/DEBIAN/prerm"

# ─── Step 3: .deb ─────────────────────────────────────────────────────────────
echo "[3/3] Building ${DEB_DIR}.deb..."
dpkg-deb --build --root-owner-group "${DEB_DIR}"
rm -rf "${DEB_DIR}"

echo ""
echo "Done: ${DEB_DIR}.deb"
echo "Install with: sudo apt install ./${DEB_DIR}.deb"
