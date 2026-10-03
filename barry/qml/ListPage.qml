// A list on the left and what is picked on the right: the layout of most
// Pip-Boy pages. The right side is the page's own content (default).
import QtQuick

Item {
    id: page
    property alias list: list
    property alias items: list.items
    property real split: 0.48
    default property alias detail: detailArea.data
    readonly property var picked: list.picked
    signal tapped(var item)

    SelectList {
        id: list
        onTapped: item => page.tapped(item)
        x: 16 * Pip.s
        y: 8 * Pip.s
        width: page.width * page.split - 24 * Pip.s
        height: page.height - 16 * Pip.s
    }

    Item {
        id: detailArea
        anchors.left: list.right
        anchors.leftMargin: 28 * Pip.s
        anchors.right: parent.right
        anchors.rightMargin: 24 * Pip.s
        y: 8 * Pip.s
        height: page.height - 16 * Pip.s
    }
}
