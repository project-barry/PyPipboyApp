// Rows of [label, value], as on the Pip-Boy's item cards.
import QtQuick

Column {
    id: card
    property var rows: []
    spacing: 4 * Pip.s

    Repeater {
        model: card.rows || []
        delegate: Rectangle {
            required property var modelData
            width: card.width
            height: 58 * Pip.s
            color: Pip.faint
            PipText {
                x: 16 * Pip.s
                width: parent.width * 0.5
                height: parent.height
                text: parent.modelData[0]
            }
            PipText {
                anchors.right: parent.right
                anchors.rightMargin: 16 * Pip.s
                width: parent.width * 0.5 - 32 * Pip.s
                height: parent.height
                horizontalAlignment: Text.AlignRight
                text: parent.modelData[1]
            }
        }
    }
}
