// A row of Pip-Boy tabs: the current one framed, the others dim.
import QtQuick

Row {
    id: row
    property var tabs: []
    property int current: 0
    property real fontSize: Pip.large
    property real tabHeight: 84 * Pip.s
    signal picked(int index)

    spacing: 8 * Pip.s

    Repeater {
        model: row.tabs
        delegate: Item {
            id: tab
            required property int index
            required property string modelData
            readonly property bool isCurrent: index === row.current
            width: label.implicitWidth + 44 * Pip.s
            height: row.tabHeight

            Rectangle {
                anchors.fill: parent
                anchors.margins: 4 * Pip.s
                color: tabTap.pressed ? Pip.faint : "transparent"
                border.color: Pip.color
                border.width: tab.isCurrent ? 3 * Pip.s : 0
                radius: 4 * Pip.s
            }
            PipText {
                id: label
                anchors.centerIn: parent
                text: tab.modelData
                font.pixelSize: row.fontSize
                font.weight: tab.isCurrent ? Font.Bold : Font.Normal
                color: tab.isCurrent ? Pip.color : Pip.dim
            }
            TapHandler {
                id: tabTap
                onTapped: row.picked(tab.index)
            }
        }
    }
}
