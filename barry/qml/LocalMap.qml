// MAP > LOCAL: the game's own picture of the area around the player
// (asked for every second while this shows), with doors, quest targets,
// your marker and the player on it.
import QtQuick

Item {
    id: local
    clip: true
    readonly property var l: Pip.local
    readonly property var img: l ? l.image : null

    Timer {
        interval: 1000
        repeat: true
        triggeredOnStart: true
        running: local.visible && Pip.connected
        onTriggered: Pip.act("localmap")
    }

    Image {
        id: picture
        anchors.fill: parent
        fillMode: Image.PreserveAspectFit
        cache: false
        smooth: true
        source: local.img && Pip.barry ? Pip.barry.serviceUrl + "localmap.png?token=" + Pip.barry.serviceToken
                                         + "&n=" + local.img.serial : ""
        // The last picture stays while the next loads.
        asynchronous: true
    }

    // Game coordinates to pixels on the picture, from its corners.
    readonly property real pw: picture.paintedWidth
    readonly property real ph: picture.paintedHeight
    readonly property real ox: (width - pw) / 2
    readonly property real oy: (height - ph) / 2
    function px(x, y) {
        if (!img) return -1000
        const ux = img.ne[0] - img.nw[0], uy = img.ne[1] - img.nw[1]
        const vx = img.sw[0] - img.nw[0], vy = img.sw[1] - img.nw[1]
        const dx = x - img.nw[0], dy = y - img.nw[1]
        const det = ux * vy - uy * vx
        return ox + (dx * vy - dy * vx) / det * pw
    }
    function py(x, y) {
        if (!img) return -1000
        const ux = img.ne[0] - img.nw[0], uy = img.ne[1] - img.nw[1]
        const vx = img.sw[0] - img.nw[0], vy = img.sw[1] - img.nw[1]
        const dx = x - img.nw[0], dy = y - img.nw[1]
        const det = ux * vy - uy * vx
        return oy + (ux * dy - uy * dx) / det * ph
    }

    Repeater {
        model: local.l ? local.l.doors : []
        delegate: Item {
            required property var modelData
            x: local.px(modelData.x, modelData.y)
            y: local.py(modelData.x, modelData.y)
            visible: local.img !== null && modelData.visible
            Rectangle {
                anchors.centerIn: parent
                width: 18 * Pip.s
                height: 18 * Pip.s
                rotation: 45
                color: Pip.color
                border.color: Pip.bg
                border.width: 2 * Pip.s
            }
            PipText {
                x: 16 * Pip.s
                y: -height / 2
                text: parent.modelData.name
                font.pixelSize: Pip.small
                style: Text.Outline
                styleColor: Pip.bg
            }
        }
    }
    Repeater {
        model: local.l ? local.l.quests : []
        delegate: PipText {
            required property var modelData
            visible: local.img !== null
            x: local.px(modelData.x, modelData.y) - width / 2
            y: local.py(modelData.x, modelData.y) - height
            text: "▼"
            font.pixelSize: Pip.large
            style: Text.Outline
            styleColor: Pip.bg
        }
    }
    PipText {
        visible: local.img !== null && local.l.custom !== null
        x: local.l && local.l.custom ? local.px(local.l.custom.x, local.l.custom.y) - width / 2 : 0
        y: local.l && local.l.custom ? local.py(local.l.custom.x, local.l.custom.y) - height / 2 : 0
        text: "✚"
        font.pixelSize: Pip.large
        style: Text.Outline
        styleColor: Pip.bg
    }
    PlayerArrow {
        visible: local.img !== null && local.l.player !== null
        x: local.l && local.l.player ? local.px(local.l.player.x, local.l.player.y) - width / 2 : 0
        y: local.l && local.l.player ? local.py(local.l.player.x, local.l.player.y) - height / 2 : 0
        rotation: local.l && local.l.player && local.l.player.rot !== null ? local.l.player.rot : 0
    }

    PipText {
        anchors.centerIn: parent
        visible: local.img === null
        text: Pip.connected ? "Waiting for the game's local map…" : ""
        color: Pip.dim
    }
}
