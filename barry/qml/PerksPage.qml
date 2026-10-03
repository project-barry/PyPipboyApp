// STAT > PERKS: the perks taken, their rank, what they do and what the
// next rank adds.
import QtQuick

ListPage {
    id: page
    items: Pip.perks || []
    list.keyOf: m => m.name
    list.rightOf: m => "★".repeat(Math.min(m.rank, 5)) + (m.rank > 5 ? "+" : "")

    Column {
        width: parent.width
        spacing: 20 * Pip.s
        PipText {
            visible: Pip.player !== null && Pip.player.perkPoints > 0
            text: "PERK POINTS: " + (Pip.player ? Pip.player.perkPoints : 0)
            font.weight: Font.Bold
        }
        PipText {
            width: parent.width
            text: page.picked ? page.picked.name.toUpperCase() : ""
            font.pixelSize: Pip.large
            font.weight: Font.Bold
        }
        PipText {
            text: page.picked ? "Rank " + page.picked.rank + " of " + page.picked.max : ""
            color: Pip.dim
        }
        PipText {
            width: parent.width
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            text: page.picked ? page.picked.desc : ""
        }
        PipText {
            width: parent.width
            visible: page.picked !== null && page.picked.next !== ""
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            color: Pip.dim
            text: page.picked ? "Next rank: " + page.picked.next : ""
        }
    }
}
