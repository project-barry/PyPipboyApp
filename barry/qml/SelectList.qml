// A Pip-Boy list: one row picked (filled), the rest outlined on touch.
// The model is a JS array from the service; it is replaced whenever the
// game changes it, so the pick is kept by key (keyOf) and the scroll
// position is kept too.
import QtQuick

ListView {
    id: list
    property var items: []
    property var keyOf: function(m) { return m.id !== undefined ? m.id : m.name }
    property var labelOf: function(m) { return m.name }
    property var rightOf: function(m) { return "" }
    property var dimOf: function(m) { return false }
    property var markOf: function(m) { return "" }  // a sign before the name ("■" equipped)
    property var pickedKey: undefined
    readonly property var picked: {
        const a = items || []
        for (let i = 0; i < a.length; i++)
            if (keyOf(a[i]) === pickedKey)
                return a[i]
        return a.length ? a[0] : null
    }
    property real rowHeight: 72 * Pip.s
    signal tapped(var item)

    clip: true
    boundsBehavior: Flickable.StopAtBounds
    model: items || []

    // A new array would scroll back to the top: stay where we were.
    property real keptY: 0
    onMovementEnded: keptY = contentY
    onModelChanged: Qt.callLater(function() {
        list.contentY = Math.max(0, Math.min(list.keptY, list.contentHeight - list.height))
    })

    delegate: Rectangle {
        id: row
        required property var modelData
        readonly property bool isPicked: list.picked !== null && list.keyOf(modelData) === list.keyOf(list.picked)
        width: list.width
        height: list.rowHeight
        color: isPicked ? Pip.color : (rowTap.pressed ? Pip.faint : "transparent")

        PipText {
            id: mark
            x: 12 * Pip.s
            width: 36 * Pip.s
            height: parent.height
            text: list.markOf(row.modelData)
            color: row.isPicked ? Pip.bg : Pip.color
        }
        PipText {
            anchors.left: mark.right
            anchors.right: right.left
            anchors.rightMargin: 12 * Pip.s
            height: parent.height
            text: list.labelOf(row.modelData)
            color: row.isPicked ? Pip.bg : (list.dimOf(row.modelData) ? Pip.dim : Pip.color)
        }
        PipText {
            id: right
            anchors.right: parent.right
            anchors.rightMargin: 16 * Pip.s
            height: parent.height
            text: list.rightOf(row.modelData)
            color: row.isPicked ? Pip.bg : Pip.color
        }
        TapHandler {
            id: rowTap
            onTapped: {
                list.pickedKey = list.keyOf(row.modelData)
                list.tapped(row.modelData)
            }
        }
    }

    // A slim bar while there is more than fits.
    Rectangle {
        visible: list.contentHeight > list.height
        anchors.right: parent.right
        width: 4 * Pip.s
        y: list.visibleArea.yPosition * list.height
        height: list.visibleArea.heightRatio * list.height
        color: Pip.dim
    }

    PipText {
        anchors.centerIn: parent
        visible: list.count === 0
        text: "Nothing here"
        color: Pip.dim
    }
}
