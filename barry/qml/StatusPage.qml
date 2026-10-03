// STAT > STATUS: limb condition around a figure, Stimpak and RadAway,
// damage and resistances, and the active effects.
import QtQuick

Item {
    id: page
    readonly property var p: Pip.player
    readonly property var limbs: p ? p.limbs : ({})

    // The figure: a plain outline drawn here (the game's Vault Boy is
    // Bethesda's), with each limb's condition beside it.
    Item {
        id: body
        width: parent.width * 0.5
        height: parent.height

        Canvas {
            id: figure
            anchors.centerIn: parent
            width: 300 * Pip.s
            height: 520 * Pip.s
            property var limbs: page.limbs
            property color ink: Pip.color
            property color hurt: Pip.faint
            onLimbsChanged: requestPaint()
            onInkChanged: requestPaint()
            onPaint: {
                const c = getContext("2d")
                const w = width, h = height, k = Pip.s
                c.reset()
                c.lineCap = "round"
                c.lineWidth = 16 * k
                function limb(name, x1, y1, x2, y2) {
                    c.strokeStyle = (limbs[name] !== undefined && limbs[name] <= 0) ? hurt : ink
                    c.beginPath()
                    c.moveTo(x1, y1)
                    c.lineTo(x2, y2)
                    c.stroke()
                }
                // Head
                c.lineWidth = 10 * k
                c.strokeStyle = (limbs.Head !== undefined && limbs.Head <= 0) ? hurt : ink
                c.beginPath()
                c.arc(w / 2, 70 * k, 52 * k, 0, Math.PI * 2)
                c.stroke()
                c.lineWidth = 16 * k
                limb("Torso", w / 2, 135 * k, w / 2, 300 * k)
                limb("LArm", w / 2 - 10 * k, 160 * k, 40 * k, 300 * k)
                limb("RArm", w / 2 + 10 * k, 160 * k, w - 40 * k, 300 * k)
                limb("LLeg", w / 2 - 6 * k, 305 * k, 70 * k, 500 * k)
                limb("RLeg", w / 2 + 6 * k, 305 * k, w - 70 * k, 500 * k)
            }
        }

        component LimbMeter: Column {
            property string limb
            property string label
            readonly property real value: page.limbs[limb] !== undefined ? page.limbs[limb] : 100
            width: 170 * Pip.s
            spacing: 4 * Pip.s
            PipText {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: Pip.small
                text: parent.value <= 0 ? parent.label + " ✕" : parent.label
                color: parent.value <= 0 ? Pip.dim : Pip.color
            }
            Meter {
                width: parent.width
                value: parent.value / 100
            }
        }

        LimbMeter { limb: "Head"; label: "HEAD"; x: (body.width - width) / 2; y: figure.y - 80 * Pip.s }
        LimbMeter { limb: "LArm"; label: "L ARM"; x: figure.x - width * 0.6; y: figure.y + 150 * Pip.s }
        LimbMeter { limb: "RArm"; label: "R ARM"; x: figure.x + figure.width - width * 0.4; y: figure.y + 150 * Pip.s }
        LimbMeter { limb: "Torso"; label: "TORSO"; x: (body.width - width) / 2; y: figure.y + figure.height + 60 * Pip.s }
        LimbMeter { limb: "LLeg"; label: "L LEG"; x: figure.x - width * 0.5; y: figure.y + figure.height - 30 * Pip.s }
        LimbMeter { limb: "RLeg"; label: "R LEG"; x: figure.x + figure.width - width * 0.5; y: figure.y + figure.height - 30 * Pip.s }
    }

    Column {
        id: side
        anchors.left: body.right
        anchors.right: parent.right
        anchors.rightMargin: 24 * Pip.s
        y: 24 * Pip.s
        spacing: 20 * Pip.s

        Row {
            spacing: 20 * Pip.s
            PipButton {
                width: (side.width - 20 * Pip.s) / 2
                height: 110 * Pip.s
                text: "STIMPAK (" + (page.p ? page.p.stimpaks : 0) + ")"
                enabled: page.p !== null && page.p.stimpakOk && page.p.stimpaks > 0
                onClicked: Pip.act("stimpak")
            }
            PipButton {
                width: (side.width - 20 * Pip.s) / 2
                height: 110 * Pip.s
                text: "RADAWAY (" + (page.p ? page.p.radaways : 0) + ")"
                enabled: page.p !== null && page.p.radawayOk && page.p.radaways > 0
                onClicked: Pip.act("radaway")
            }
        }

        Card {
            width: side.width
            rows: {
                if (!page.p)
                    return []
                const r = []
                const names = { phys: "Damage", energy: "Energy damage", rad: "Radiation damage", poison: "Poison damage" }
                for (const d of page.p.damage)
                    r.push([names[d.type] || "Damage", d.value])
                const res = { phys: "Damage resist", energy: "Energy resist", rad: "Radiation resist", poison: "Poison resist" }
                for (const d of page.p.resist)
                    r.push([res[d.type] || "Resist", d.value])
                return r
            }
        }

        PipText {
            text: "EFFECTS"
            font.pixelSize: Pip.large
            font.weight: Font.Bold
        }
        ListView {
            width: side.width
            height: page.height - y - 24 * Pip.s
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: Pip.effects || []
            spacing: 6 * Pip.s
            delegate: Column {
                id: effect
                required property var modelData
                width: ListView.view.width
                PipText {
                    width: parent.width
                    text: effect.modelData.source
                    font.weight: Font.DemiBold
                }
                PipText {
                    width: parent.width
                    x: 24 * Pip.s
                    color: Pip.dim
                    font.pixelSize: Pip.small
                    text: effect.modelData.lines.map(l => l.name + " " + (String(l.value).startsWith("-") ? "" : "+")
                                                       + l.value + (l.duration > 0 ? " (" + l.duration + " s)" : "")).join("   ")
                }
            }
            PipText {
                visible: parent.count === 0
                text: "None"
                color: Pip.dim
            }
        }
    }
}
