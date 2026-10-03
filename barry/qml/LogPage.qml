// DATA > STATS: the game's statistics, by group.
import QtQuick

ListPage {
    id: page
    split: 0.36
    items: Pip.stats || []

    ListView {
        anchors.fill: parent
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: page.picked ? page.picked.rows : []
        spacing: 4 * Pip.s
        delegate: Rectangle {
            required property var modelData
            width: ListView.view.width
            height: 58 * Pip.s
            color: Pip.faint
            PipText {
                x: 16 * Pip.s
                width: parent.width * 0.75
                height: parent.height
                text: parent.modelData.text
            }
            PipText {
                anchors.right: parent.right
                anchors.rightMargin: 16 * Pip.s
                height: parent.height
                text: parent.modelData.value
            }
        }
    }
}
