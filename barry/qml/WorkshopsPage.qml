// DATA > WORKSHOPS: the settlements, owned first; the picked one's numbers.
import QtQuick

ListPage {
    id: page
    items: Pip.workshops || []
    list.dimOf: m => !m.owned
    list.markOf: m => m.owned ? "■" : ""
    readonly property var names: [["WorkshopRatingPopulation", "People"], ["Food", "Food"], ["Water", "Water"],
                                  ["PowerGenerated", "Power"], ["Defense", "Defense"], ["Bed", "Beds"],
                                  ["Happiness", "Happiness"]]

    Column {
        width: parent.width
        spacing: 20 * Pip.s
        visible: page.picked !== null
        PipText {
            width: parent.width
            text: page.picked ? page.picked.name : ""
            font.pixelSize: Pip.large
            font.weight: Font.Bold
        }
        PipText {
            text: page.picked && page.picked.owned ? "Your settlement" : "Not your settlement"
            color: Pip.dim
        }
        Card {
            width: parent.width
            visible: page.picked !== null && page.picked.owned
            rows: {
                const d = page.picked ? page.picked.data : {}
                const r = []
                for (const [key, label] of page.names) {
                    if (!(key in d))
                        continue
                    // A negative rating: the game shows that number in red.
                    const low = d[key].rating < 0 ? "  ▼" : ""
                    r.push([label, d[key].value + (key === "Happiness" ? "%" : "") + low])
                }
                return r
            }
        }
    }
}
