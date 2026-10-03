// DATA > QUESTS: current quests first (the tracked ones marked), then the
// finished ones dim; the picked one's story, objectives and tracking.
import QtQuick

ListPage {
    id: page
    items: Pip.quests || []
    list.markOf: m => m.active ? "▶" : ""
    list.dimOf: m => !m.current
    list.labelOf: m => m.name || "Miscellaneous"

    Flickable {
        anchors.fill: parent
        contentHeight: column.height
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: column
            width: parent.width
            spacing: 18 * Pip.s
            visible: page.picked !== null

            PipText {
                width: parent.width
                text: page.picked ? (page.picked.name || "Miscellaneous") : ""
                font.pixelSize: Pip.large
                font.weight: Font.Bold
            }
            PipButton {
                visible: page.picked !== null && page.picked.current
                text: page.picked && page.picked.active ? "STOP TRACKING" : "TRACK ON MAP"
                on: page.picked !== null && page.picked.active
                onClicked: Pip.act("quest", { id: page.picked.id })
            }
            PipText {
                width: parent.width
                visible: text !== ""
                wrapMode: Text.Wrap
                elide: Text.ElideNone
                text: page.picked ? page.picked.desc : ""
            }
            Repeater {
                model: page.picked ? page.picked.objectives : []
                delegate: PipText {
                    required property var modelData
                    width: column.width
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                    text: (modelData.failed ? "✕ " : modelData.done ? "☑ " : "☐ ") + modelData.text
                    color: modelData.done || modelData.failed ? Pip.dim : Pip.color
                    font.strikeout: modelData.failed
                }
            }
        }
    }
}
