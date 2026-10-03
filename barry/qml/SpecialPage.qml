// STAT > SPECIAL: the seven attributes; the picked one's value and what it does.
import QtQuick

ListPage {
    id: page
    items: Pip.special || []
    list.keyOf: m => m.name
    list.rightOf: m => String(m.value + m.modifier)

    Column {
        width: parent.width
        spacing: 24 * Pip.s
        visible: page.picked !== null
        PipText {
            width: parent.width
            text: page.picked ? page.picked.name.toUpperCase() : ""
            font.pixelSize: Pip.large
            font.weight: Font.Bold
        }
        PipText {
            text: page.picked ? String(page.picked.value + page.picked.modifier) : ""
            font.pixelSize: Pip.huge * 2
            font.weight: Font.Bold
        }
        PipText {
            visible: page.picked !== null && page.picked.modifier !== 0
            text: page.picked ? page.picked.value + " base " + (page.picked.modifier > 0 ? "+ " : "− ")
                                + Math.abs(page.picked.modifier) + " from effects" : ""
            color: Pip.dim
        }
        PipText {
            width: parent.width
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            text: page.picked ? page.picked.desc : ""
        }
    }
}
