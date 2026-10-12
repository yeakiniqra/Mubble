// One glow strip along a screen edge. Clicks pass straight through it.
import QtQuick

Window {
    id: edge

    required property string side   // top | right | bottom | left
    readonly property bool flat: side === "top" || side === "bottom"

    color: "transparent"
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
           | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput
    visible: mubble.glow && mubble.playing && !mubble.covered

    // Drawn as the top strip, then turned to face inwards from its own edge.
    Rectangle {
        anchors.centerIn: parent
        width: edge.flat ? edge.width : edge.height
        height: edge.flat ? edge.height : edge.width
        rotation: ({ top: 0, right: 90, bottom: 180, left: 270 })[edge.side]
        opacity: 0.1 + 0.9 * mubble.level
        gradient: Gradient {
            GradientStop { position: 0.0;  color: mubble.accent }
            GradientStop { position: 0.06; color: Qt.alpha(mubble.accent, 0.5) }
            GradientStop { position: 1.0;  color: Qt.alpha(mubble.accent, 0) }
        }
    }
}
