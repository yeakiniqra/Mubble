// The floating now-playing pill. Collapsed it is one line; hovering opens the
// controls. The window is larger than the pill to leave room for its shadow and
// for the opened size; `mubble.setMask` keeps clicks outside the pill passing through.
import QtQuick
import QtQuick.Effects
import QtQuick.Shapes

Window {
    id: win

    width: 420
    height: 236
    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
    visible: shown || pill.opacity > 0.01

    property bool shown: ((mubble.hasTrack && !dismissed) || toast.running) && !mubble.covered
    property bool open: false
    // Sent away with the cross. It stays away until there is something new to
    // show: another track, or playback starting again.
    property bool dismissed: false
    readonly property string track: mubble.title
    readonly property bool playing: mubble.playing
    onTrackChanged: dismissed = false
    onPlayingChanged: if (playing) dismissed = false
    property string toastText: ""

    function clock(seconds) {
        const s = Math.max(0, Math.floor(seconds))
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0")
    }

    Timer { id: toast; interval: 4500 }
    Timer { id: opener; interval: 140; onTriggered: win.open = mubble.hasTrack }
    Connections {
        target: mubble
        function onToasted(text) { win.toastText = text; toast.restart() }
        function onStateChanged() { if (!mubble.hasTrack) win.open = false }
    }

    component Glide: NumberAnimation { duration: 320; easing.type: Easing.OutCubic }

    component IconButton: Item {
        id: button
        property string path            // SVG path on a 24 px grid
        property real size: 36
        signal tapped

        width: size
        height: size
        anchors.verticalCenter: parent.verticalCenter
        opacity: enabled ? 1 : 0.3
        scale: tap.pressed ? 0.86 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }

        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: "white"
            opacity: hover.hovered ? 0.16 : 0
            Behavior on opacity { NumberAnimation { duration: 120 } }
        }
        Shape {
            anchors.centerIn: parent
            width: 24
            height: 24
            scale: button.size / 36
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                fillColor: "white"
                strokeColor: "transparent"
                PathSvg { path: button.path }
            }
        }
        HoverHandler { id: hover }
        TapHandler { id: tap; onTapped: button.tapped() }
    }

    Item {
        id: pill

        property real radius: win.open ? 32 : 26
        // 0 closed, 1 open. Tied to the height, so what belongs to the open
        // pill never shows outside one that is still closing.
        readonly property real opened: Math.max(0, Math.min(1, (height - 110) / 56))

        x: (win.width - width) / 2
        y: 16
        width: win.open ? 380 : 300
        height: win.open ? 166 : 52
        opacity: win.shown ? 1 : 0
        scale: win.shown ? 1 : 0.92

        Behavior on width   { Glide {} }
        Behavior on height  { Glide {} }
        Behavior on radius  { Glide {} }
        Behavior on scale   { Glide {} }
        Behavior on opacity { Glide { duration: 200 } }

        function syncMask() { mubble.setMask(x, y, width, height) }
        onXChanged: syncMask()
        onWidthChanged: syncMask()
        onHeightChanged: syncMask()
        Component.onCompleted: syncMask()

        HoverHandler {
            onHoveredChanged: {
                if (hovered) {
                    opener.start()
                } else {
                    opener.stop()
                    win.open = false
                }
            }
        }

        // Dock-type windows are not moved by the window manager, so move by hand:
        // shift the window until the pointer is back over the spot it grabbed.
        DragHandler {
            target: null
            property point grab
            onActiveChanged: {
                if (active)
                    grab = centroid.scenePressPosition
                else
                    mubble.savePosition(win.x, win.y)
            }
            onCentroidChanged: {
                if (active) {
                    win.x += centroid.scenePosition.x - grab.x
                    win.y += centroid.scenePosition.y - grab.y
                }
            }
        }

        // ── glass ────────────────────────────────────────────────────────────
        // GNOME cannot blur what is behind a window, so the glass is the track's
        // own cover, blurred, under a dark tint, a top sheen and a hairline edge.
        Rectangle {
            anchors.fill: parent
            radius: pill.radius
            color: "#d916161c"
            layer.enabled: true
            layer.effect: MultiEffect {
                // Windows clips drawing to the input mask as well, which would
                // cut the shadow off square at the pill's edge.
                shadowEnabled: Qt.platform.os !== "windows"
                shadowColor: "black"
                shadowOpacity: 0.45
                shadowBlur: 0.9
                shadowVerticalOffset: 6
            }
        }
        Item {
            id: coverWash
            anchors.fill: parent
            visible: false
            layer.enabled: true
            Image {
                anchors.fill: parent
                source: mubble.art
                cache: false
                fillMode: Image.PreserveAspectCrop
            }
        }
        Rectangle {
            id: pillShape
            anchors.fill: parent
            radius: pill.radius
            visible: false
            layer.enabled: true
        }
        MultiEffect {
            anchors.fill: parent
            source: coverWash
            visible: mubble.art !== ""
            opacity: 0.85
            blurEnabled: true
            blur: 1
            blurMax: 64
            autoPaddingEnabled: false
            saturation: 0.35
            maskEnabled: true
            maskSource: pillShape
        }
        Rectangle { anchors.fill: parent; radius: pill.radius; color: "black"; opacity: 0.34 }
        Rectangle {
            anchors.fill: parent
            radius: pill.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#3dffffff" }
                GradientStop { position: 0.45; color: "#0dffffff" }
                GradientStop { position: 1.0; color: "#00ffffff" }
            }
        }
        Rectangle {
            anchors.fill: parent
            radius: pill.radius
            color: "transparent"
            border.width: 1
            border.color: "#47ffffff"
        }

        // ── always visible: cover, title, level bars ─────────────────────────
        Item {
            id: cover
            x: win.open ? 16 : 8
            y: x
            width: win.open ? 64 : 36
            height: width
            Behavior on x     { Glide {} }
            Behavior on width { Glide {} }

            Rectangle {
                id: coverShape
                anchors.fill: parent
                radius: parent.width * 0.26
                visible: false
                layer.enabled: true
            }
            Rectangle {
                anchors.fill: parent
                radius: coverShape.radius
                color: mubble.accent
                opacity: 0.45
                visible: mubble.art === ""
            }
            Image {
                anchors.fill: parent
                source: mubble.art
                cache: false
                fillMode: Image.PreserveAspectCrop
                visible: mubble.art !== ""
                layer.enabled: true
                layer.effect: MultiEffect { maskEnabled: true; maskSource: coverShape }
            }
        }
        Column {
            anchors.left: cover.right
            anchors.leftMargin: 12
            anchors.right: bars.left
            anchors.rightMargin: 12
            anchors.verticalCenter: cover.verticalCenter
            spacing: 1
            Item {
                id: titleBox
                width: parent.width
                height: title.implicitHeight
                clip: true
                Text {
                    id: title
                    // A title too long to fit slides through while it plays,
                    // and is cut short with an ellipsis while it does not.
                    readonly property real extra: Math.max(0, implicitWidth - titleBox.width)
                    property real slide: 0   // 0 shows the start, 1 the end
                    x: slider.running ? -extra * slide : 0
                    width: slider.running ? implicitWidth : titleBox.width
                    elide: Text.ElideRight
                    color: "white"
                    font.pixelSize: win.open ? 16 : 14
                    font.weight: Font.DemiBold
                    text: toast.running ? win.toastText : mubble.title
                    onTextChanged: if (slider.running) slider.restart()
                    SequentialAnimation on slide {
                        id: slider
                        running: title.extra > 0 && mubble.playing && win.visible
                        loops: Animation.Infinite
                        onRunningChanged: if (!running) title.slide = 0
                        PauseAnimation { duration: 3000 }
                        NumberAnimation { to: 1; duration: 600 + title.extra * 28 }
                        PauseAnimation { duration: 1500 }
                        NumberAnimation { to: 0; duration: 500; easing.type: Easing.InOutSine }
                    }
                }
            }
            Text {
                width: parent.width
                elide: Text.ElideRight
                color: "white"
                opacity: 0.65
                font.pixelSize: win.open ? 13 : 12
                text: mubble.artist
                visible: text !== "" && !toast.running
            }
        }
        Row {
            id: bars
            anchors.right: parent.right
            anchors.rightMargin: win.open ? 24 : 18
            anchors.verticalCenter: cover.verticalCenter
            height: 18
            spacing: 3
            visible: mubble.hasTrack
            Repeater {
                model: [520, 380, 640, 450]
                Rectangle {
                    id: bar
                    required property int modelData
                    anchors.verticalCenter: parent.verticalCenter
                    width: 3
                    height: 4
                    radius: 1.5
                    color: "white"
                    opacity: 0.9
                    SequentialAnimation on height {
                        running: mubble.playing && win.visible
                        loops: Animation.Infinite
                        NumberAnimation { to: 18; duration: bar.modelData; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 4; duration: bar.modelData; easing.type: Easing.InOutSine }
                    }
                }
            }
        }

        // Closed, the pill still says how far along the track is.
        Rectangle {
            x: pill.radius
            y: pill.height - 4
            width: (pill.width - 2 * pill.radius)
                   * Math.min(1, mubble.position / Math.max(1, mubble.length))
            height: 2
            radius: 1
            color: "white"
            opacity: 0.55 * (1 - pill.opened)
            visible: mubble.length > 0 && opacity > 0
            Behavior on width { enabled: mubble.playing; NumberAnimation { duration: 1000 } }
        }

        // ── opened: dismiss, progress and transport ──────────────────────────
        IconButton {
            size: 24
            path: "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"
            anchors.verticalCenter: undefined
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.margins: 8
            opacity: 0.7 * pill.opened
            visible: opacity > 0
            onTapped: { win.dismissed = true; win.open = false }
        }
        Item {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: cover.bottom
            anchors.leftMargin: 18
            anchors.rightMargin: 18
            anchors.topMargin: 12
            height: 60
            opacity: pill.opened
            visible: opacity > 0

            Item {
                id: progress
                width: parent.width
                height: 14
                visible: mubble.length > 0

                Text {
                    id: elapsed
                    width: 36
                    anchors.verticalCenter: parent.verticalCenter
                    color: "white"
                    opacity: 0.6
                    font.pixelSize: 11
                    text: win.clock(mubble.position)
                }
                Text {
                    id: total
                    width: 36
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    horizontalAlignment: Text.AlignRight
                    color: "white"
                    opacity: 0.6
                    font.pixelSize: 11
                    text: win.clock(mubble.length)
                }
                Rectangle {
                    id: track
                    anchors.left: elapsed.right
                    anchors.right: total.left
                    anchors.margins: 6
                    anchors.verticalCenter: parent.verticalCenter
                    height: 4
                    radius: 2
                    color: "#33ffffff"
                    Rectangle {
                        width: parent.width * Math.min(1, mubble.position / Math.max(1, mubble.length))
                        height: parent.height
                        radius: 2
                        color: "white"
                        // Position arrives once a second; slide between readings.
                        Behavior on width { enabled: mubble.playing; NumberAnimation { duration: 1000 } }
                    }
                    TapHandler {
                        enabled: mubble.canSeek
                        margin: 8
                        onTapped: (point) => mubble.seek(point.position.x / track.width)
                    }
                }
            }
            Row {
                y: 20
                height: 40
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 18
                IconButton {
                    path: "M6 6h2v12H6zm3.5 6l8.5 6V6z"
                    enabled: mubble.canPrev
                    onTapped: mubble.previous()
                }
                IconButton {
                    size: 40
                    path: mubble.playing ? "M6 19h4V5H6v14zm8-14v14h4V5h-4z" : "M8 5v14l11-7z"
                    onTapped: mubble.playPause()
                }
                IconButton {
                    path: "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"
                    enabled: mubble.canNext
                    onTapped: mubble.next()
                }
            }
        }
    }
}
