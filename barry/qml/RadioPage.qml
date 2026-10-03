// RADIO: the stations the Pip-Boy knows; a tap turns one on or off. Those
// out of range are dim (the game plays only static on them).
import QtQuick

ListPage {
    id: page
    items: Pip.radio || []
    list.markOf: m => m.active ? "▶" : ""
    list.dimOf: m => !m.inRange
    list.rightOf: m => m.freq.toFixed(1)
    onTapped: m => Pip.act("radio", { id: m.id })

    readonly property var playing: (Pip.radio || []).find(r => r.active) || null

    Column {
        width: parent.width
        spacing: 24 * Pip.s
        PipText {
            width: parent.width
            text: page.playing ? page.playing.name : "Radio off"
            font.pixelSize: Pip.large
            font.weight: Font.Bold
            color: page.playing ? Pip.color : Pip.dim
        }
        PipText {
            text: page.playing ? page.playing.freq.toFixed(1) + " MHz" : "Tap a station to play it"
            color: Pip.dim
        }
    }

    // A wave while something plays.
    Canvas {
        id: wave
        anchors.bottom: parent.bottom
        width: parent.width
        height: parent.height * 0.5
        property real phase: 0
        property color ink: Pip.color
        property bool on: page.playing !== null
        onPhaseChanged: requestPaint()
        onOnChanged: requestPaint()
        onPaint: {
            const c = getContext("2d")
            c.reset()
            c.strokeStyle = Pip.faint
            c.lineWidth = 2 * Pip.s
            for (let gx = 0; gx <= width; gx += width / 8) {
                c.beginPath(); c.moveTo(gx, 0); c.lineTo(gx, height); c.stroke()
            }
            c.beginPath(); c.moveTo(0, height / 2); c.lineTo(width, height / 2); c.stroke()
            c.strokeStyle = ink
            c.lineWidth = 4 * Pip.s
            c.beginPath()
            for (let x = 0; x <= width; x += 4) {
                const t = x / width * Math.PI * 6
                const a = on ? (Math.sin(t + phase) * 0.6 + Math.sin(t * 2.7 - phase * 1.7) * 0.3) : 0
                const y = height / 2 + a * height * 0.4
                if (x === 0) c.moveTo(x, y); else c.lineTo(x, y)
            }
            c.stroke()
        }
        NumberAnimation on phase {
            running: wave.on && wave.visible
            from: 0
            to: Math.PI * 2
            duration: 1600
            loops: Animation.Infinite
        }
    }
}
