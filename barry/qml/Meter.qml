// A bar filled to value (0 to 1).
import QtQuick

Rectangle {
    property real value: 0
    implicitHeight: 22 * Pip.s
    color: "transparent"
    border.color: Pip.color
    border.width: 2 * Pip.s

    Rectangle {
        x: 5 * Pip.s
        anchors.verticalCenter: parent.verticalCenter
        height: parent.height - 10 * Pip.s
        width: Math.max(0, (parent.width - 10 * Pip.s) * Math.max(0, Math.min(1, parent.value)))
        color: Pip.color
    }
}
