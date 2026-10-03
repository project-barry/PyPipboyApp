// The player on a map: an arrow pointing up at rotation 0 (north).
import QtQuick

Canvas {
    width: 52 * Pip.s
    height: 52 * Pip.s
    property color ink: Pip.color
    onInkChanged: requestPaint()
    onPaint: {
        const c = getContext("2d")
        const w = width, h = height
        c.reset()
        c.fillStyle = ink
        c.strokeStyle = Pip.bg
        c.lineWidth = 4 * Pip.s
        c.beginPath()
        c.moveTo(w / 2, 2)
        c.lineTo(w - 6, h - 4)
        c.lineTo(w / 2, h * 0.7)
        c.lineTo(6, h - 4)
        c.closePath()
        c.stroke()
        c.fill()
    }
}
