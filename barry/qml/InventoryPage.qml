// INV: one tab of the inventory (category), the picked item's card, and
// what can be done with it in the game.
import QtQuick

ListPage {
    id: page
    property string category: "weapons"
    readonly property var item: picked
    readonly property bool wearable: category === "weapons" || category === "apparel"

    items: Pip.inventory ? Pip.inventory[category] : []
    list.labelOf: m => m.name + (m.count > 1 ? " (" + m.count + ")" : "")
    list.markOf: m => m.equipped ? "■" : ""
    list.rightOf: m => (m.legendary ? "★" : "") + (m.fav !== null ? " " + (m.fav + 1) : "")

    // A drop asks first: it cannot be taken back from here.
    property bool confirmDrop: false
    onItemChanged: confirmDrop = false

    Column {
        id: detail
        width: parent.width
        spacing: 16 * Pip.s
        visible: page.item !== null

        PipText {
            id: title
            width: parent.width
            text: page.item ? page.item.name : ""
            font.pixelSize: Pip.large
            font.weight: Font.Bold
        }
        PipText {
            id: flags
            text: page.item ? [page.item.equipped ? "Equipped" : "",
                               page.item.legendary ? "Legendary" : "",
                               page.item.fav !== null ? "Favorite " + (page.item.fav + 1) : "",
                               page.item.count > 1 ? page.item.count + " carried" : ""].filter(t => t).join(" · ") : ""
            color: Pip.dim
            font.pixelSize: Pip.small
        }
        // The weapon's picture, in the room the rest leaves.
        PipArt {
            width: parent.width
            height: Math.max(90 * Pip.s, Math.min(220 * Pip.s, detail.parent.height - title.height - flags.height
                                                               - itemCard.height - buttons.height - 4 * detail.spacing))
            visible: ready
            name: page.item && page.item.picture ? page.item.picture : ""  // service.py weapon_picture
        }
        Card {
            id: itemCard
            width: parent.width
            rows: page.item ? page.item.card : []
        }
        Row {
            id: buttons
            spacing: 16 * Pip.s
            PipButton {
                visible: page.wearable || page.category === "aid" || (page.item !== null && page.item.holotape)
                text: page.wearable ? (page.item && page.item.equipped ? "UNEQUIP" : "EQUIP")
                                    : page.category === "aid" ? "USE" : "PLAY"
                onClicked: Pip.act("use", { id: page.item.id })
            }
            PipButton {
                text: page.confirmDrop ? "DROP: SURE?" : (page.item && page.item.count > 1 ? "DROP 1" : "DROP")
                on: page.confirmDrop
                onClicked: {
                    if (!page.confirmDrop) {
                        page.confirmDrop = true
                        return
                    }
                    page.confirmDrop = false
                    Pip.act("drop", { id: page.item.id, count: 1 })
                }
            }
        }
    }
}
