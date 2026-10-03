// MAP > WORLD: the places the game has shown you, the player, quest
// targets, your marker and your power armor, on a grid (the game's map
// picture is Bethesda's, so it is not here). Drag to move, pinch (or the
// mouse wheel) to zoom; tap a place to fast travel there, or an empty spot
// to put your marker there.
import QtQuick

Item {
    id: map
    clip: true
    readonly property var w: Pip.world
    readonly property var ext: w ? w.extents : null

    // The view: the map point (0-1 across, 0-1 down) at the middle, and zoom
    // (1: the whole map fits the height).
    property real cx: 0.5
    property real cy: 0.5
    property real zoom: 2.5
    readonly property real span: height * zoom  // pixels across the whole map
    property bool followed: false

    // Map coordinates (the game's) to 0-1, and to pixels here.
    function u(x) { return ext ? (x - ext.nw[0]) / (ext.ne[0] - ext.nw[0]) : 0.5 }
    function v(y) { return ext ? (y - ext.nw[1]) / (ext.sw[1] - ext.nw[1]) : 0.5 }
    function px(x) { return (u(x) - cx) * span + width / 2 }
    function py(y) { return (v(y) - cy) * span + height / 2 }
    function gameX(sx) { return ext.nw[0] + ((sx - width / 2) / span + cx) * (ext.ne[0] - ext.nw[0]) }
    function gameY(sy) { return ext.nw[1] + ((sy - height / 2) / span + cy) * (ext.sw[1] - ext.nw[1]) }
    function center() {
        if (w && w.player) {
            cx = u(w.player.x)
            cy = v(w.player.y)
        }
    }
    function clampZoom(z) { return Math.max(0.8, Math.min(16, z)) }

    // Centred on the player when the map first arrives.
    // (Later: ext follows w, after this handler.)
    onWChanged: if (w && !followed) { followed = true; Qt.callLater(center) }

    property var pickedPlace: null     // a location tapped
    property var pendingMarker: null   // {x, y}: where a tap would put the marker
    readonly property var places: w ? w.locations : []

    // The grid.
    Canvas {
        id: grid
        anchors.fill: parent
        property real cx: map.cx
        property real cy: map.cy
        property real span: map.span
        property color ink: Pip.faint
        onCxChanged: requestPaint()
        onCyChanged: requestPaint()
        onSpanChanged: requestPaint()
        onInkChanged: requestPaint()
        onPaint: {
            const c = getContext("2d")
            c.reset()
            c.strokeStyle = ink
            c.lineWidth = 1.5
            const step = span / 16
            const ox = (width / 2 - cx * span)
            const oy = (height / 2 - cy * span)
            for (let i = 0; i <= 16; i++) {
                const gx = ox + i * step, gy = oy + i * step
                c.beginPath(); c.moveTo(gx, Math.max(0, oy)); c.lineTo(gx, Math.min(height, oy + span)); c.stroke()
                c.beginPath(); c.moveTo(Math.max(0, ox), gy); c.lineTo(Math.min(width, ox + span), gy); c.stroke()
            }
        }
    }

    // Touch: drag, pinch, tap on empty ground. Places take their own taps.
    DragHandler {
        id: drag
        target: null
        property real startX
        property real startY
        onActiveChanged: if (active) { startX = map.cx; startY = map.cy }
        onTranslationChanged: {
            map.cx = startX - translation.x / map.span
            map.cy = startY - translation.y / map.span
        }
    }
    PinchHandler {
        target: null
        property real startZoom
        onActiveChanged: if (active) startZoom = map.zoom
        onActiveScaleChanged: map.zoom = map.clampZoom(startZoom * activeScale)
    }
    WheelHandler {
        onWheel: event => map.zoom = map.clampZoom(map.zoom * (event.angleDelta.y > 0 ? 1.15 : 1 / 1.15))
    }
    TapHandler {
        onTapped: (point) => {
            map.pickedPlace = null
            if (map.ext)
                map.pendingMarker = { x: map.gameX(point.position.x), y: map.gameY(point.position.y) }
        }
    }

    // Places: filled once discovered; a ring for the cleared ones.
    Repeater {
        model: map.places
        delegate: Item {
            id: place
            required property var modelData
            readonly property real r: (modelData.discovered ? 14 : 10) * Pip.s
            x: map.px(modelData.x) - width / 2
            y: map.py(modelData.y) - height / 2
            width: 64 * Pip.s
            height: 64 * Pip.s
            visible: x > -width && y > -height && x < map.width && y < map.height
            readonly property bool isPicked: map.pickedPlace !== null && map.pickedPlace.id === modelData.id

            Rectangle {
                anchors.centerIn: parent
                width: place.r * 2
                height: width
                radius: place.modelData.type === 13 ? 2 * Pip.s : width / 2  // settlements square
                rotation: place.modelData.type === 15 ? 45 : 0  // vaults a diamond
                color: place.modelData.discovered ? Pip.color : "transparent"
                border.color: Pip.color
                border.width: 3 * Pip.s
            }
            Rectangle {
                anchors.centerIn: parent
                visible: place.isPicked
                width: 56 * Pip.s
                height: width
                radius: width / 2
                color: "transparent"
                border.color: Pip.color
                border.width: 3 * Pip.s
            }
            PipText {
                anchors.top: parent.bottom
                anchors.topMargin: -12 * Pip.s
                anchors.horizontalCenter: parent.horizontalCenter
                visible: place.isPicked || (place.modelData.discovered && map.zoom >= 4)
                text: place.modelData.name
                font.pixelSize: Pip.small
                style: Text.Outline
                styleColor: Pip.bg
            }
            TapHandler {
                gesturePolicy: TapHandler.ReleaseWithinBounds  // not the map's tap too
                onTapped: {
                    map.pendingMarker = null
                    map.pickedPlace = place.modelData
                }
            }
        }
    }

    // Quest targets.
    Repeater {
        model: map.w ? map.w.quests : []
        delegate: PipText {
            required property var modelData
            x: map.px(modelData.x) - width / 2
            y: map.py(modelData.y) - height
            text: "▼"
            font.pixelSize: Pip.large
            style: Text.Outline
            styleColor: Pip.bg
        }
    }
    // Your marker, your power armor.
    PipText {
        visible: map.w !== null && map.w.custom !== null
        x: map.w && map.w.custom ? map.px(map.w.custom.x) - width / 2 : 0
        y: map.w && map.w.custom ? map.py(map.w.custom.y) - height / 2 : 0
        text: "✚"
        font.pixelSize: Pip.large
        style: Text.Outline
        styleColor: Pip.bg
    }
    PipText {
        visible: map.w !== null && map.w.powerArmor !== null
        x: map.w && map.w.powerArmor ? map.px(map.w.powerArmor.x) - width / 2 : 0
        y: map.w && map.w.powerArmor ? map.py(map.w.powerArmor.y) - height / 2 : 0
        text: "PA"
        font.pixelSize: Pip.small
        font.weight: Font.Bold
        style: Text.Outline
        styleColor: Pip.bg
    }
    // Where a tap would put the marker.
    PipText {
        visible: map.pendingMarker !== null
        x: map.pendingMarker ? map.px(map.pendingMarker.x) - width / 2 : 0
        y: map.pendingMarker ? map.py(map.pendingMarker.y) - height / 2 : 0
        text: "✚"
        color: Pip.dim
        font.pixelSize: Pip.large
    }

    // The player: an arrow, pointing where they face.
    PlayerArrow {
        visible: map.w !== null && map.w.player !== null
        x: map.w && map.w.player ? map.px(map.w.player.x) - width / 2 : 0
        y: map.w && map.w.player ? map.py(map.w.player.y) - height / 2 : 0
        rotation: map.w && map.w.player && map.w.player.rot !== null ? map.w.player.rot : 0
    }

    // What a tap picked, and the buttons for it.
    Rectangle {
        id: panel
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 16 * Pip.s
        height: 120 * Pip.s
        color: Pip.bg
        border.color: Pip.color
        border.width: 2 * Pip.s
        radius: 6 * Pip.s
        TapHandler { gesturePolicy: TapHandler.ReleaseWithinBounds }  // a tap here is not on the map

        PipText {
            anchors.left: parent.left
            anchors.leftMargin: 20 * Pip.s
            anchors.right: buttons.left
            anchors.rightMargin: 16 * Pip.s
            height: parent.height
            wrapMode: Text.Wrap
            maximumLineCount: 2
            text: map.pickedPlace ? map.pickedPlace.name + (map.pickedPlace.cleared ? " (cleared)" : "")
                                    + (map.pickedPlace.discovered ? "" : " — not discovered")
                : map.pendingMarker ? "Put your marker here?"
                : (Pip.player ? Pip.player.world : "") + " · drag, pinch, tap"
            color: map.pickedPlace || map.pendingMarker ? Pip.color : Pip.dim
        }
        Row {
            id: buttons
            anchors.right: parent.right
            anchors.rightMargin: 16 * Pip.s
            anchors.verticalCenter: parent.verticalCenter
            spacing: 12 * Pip.s
            PipButton {
                visible: map.pickedPlace !== null && map.pickedPlace.discovered
                text: "FAST TRAVEL"
                onClicked: {
                    const place = map.pickedPlace
                    Pip.act("travel", { id: place.id }, ok => {
                        if (ok) {
                            Pip.say("Traveling to " + place.name)
                            map.pickedPlace = null
                        }
                    })
                }
            }
            PipButton {
                visible: map.pickedPlace !== null || map.pendingMarker !== null
                text: "MARK"
                onClicked: {
                    const at = map.pickedPlace || map.pendingMarker
                    Pip.act("marker", { x: at.x, y: at.y })
                    map.pickedPlace = null
                    map.pendingMarker = null
                }
            }
            PipButton {
                visible: map.pickedPlace === null && map.pendingMarker === null && map.w !== null && map.w.custom !== null
                text: "CLEAR MARK"
                onClicked: Pip.act("unmarker")
            }
            PipButton {
                text: "◎"
                fontSize: Pip.large
                onClicked: { map.pickedPlace = null; map.pendingMarker = null; map.center() }
            }
            PipButton {
                text: "+"
                fontSize: Pip.large
                implicitWidth: 84 * Pip.s
                onClicked: map.zoom = map.clampZoom(map.zoom * 1.5)
            }
            PipButton {
                text: "−"
                fontSize: Pip.large
                implicitWidth: 84 * Pip.s
                onClicked: map.zoom = map.clampZoom(map.zoom / 1.5)
            }
        }
    }
}
