// A Pip-Boy button: an outlined label, filled while pressed or when on.
import QtQuick

Rectangle {
    id: button
    property string text: ""
    property bool on: false
    property bool enabled: true
    property real fontSize: Pip.body
    signal clicked

    implicitWidth: Math.max(label.implicitWidth + 48 * Pip.s, 120 * Pip.s)
    implicitHeight: 84 * Pip.s
    radius: 6 * Pip.s
    color: (tap.pressed || on) && enabled ? Pip.color : "transparent"
    border.color: enabled ? Pip.color : Pip.faint
    border.width: 3 * Pip.s
    opacity: enabled ? 1 : 0.5

    PipText {
        id: label
        anchors.centerIn: parent
        width: Math.min(implicitWidth, parent.width - 16 * Pip.s)
        horizontalAlignment: Text.AlignHCenter
        text: button.text
        font.pixelSize: button.fontSize
        font.weight: Font.DemiBold
        color: (tap.pressed || button.on) && button.enabled ? Pip.bg : (button.enabled ? Pip.color : Pip.dim)
    }

    TapHandler {
        id: tap
        enabled: button.enabled
        // Its own: a tap here is not also a tap on what is behind it.
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: button.clicked()
    }
}
