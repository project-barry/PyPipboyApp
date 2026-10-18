// A picture from art/ in the Pip-Boy's color. The pictures are white masks
// made at build time by tools/fetch-art.py; this paints them in Pip.color,
// fitted and centered. Without the picture (art/ missing, or no picture by
// that name) it shows nothing and ready is false.
import QtQuick

Canvas {
    id: art
    property string name: ""  // "vaultboy", "special/luck", "weapons/combat-rifle"
    property color ink: Pip.color
    readonly property url source: name ? Qt.resolvedUrl("../art/" + name + ".png") : ""
    readonly property bool ready: probe.status === Image.Ready

    // Tells whether the picture is there, and its size.
    Image {
        id: probe
        visible: false
        source: art.source
        onStatusChanged: if (status === Image.Ready) art.loadImage(art.source)
    }

    onImageLoaded: requestPaint()
    onInkChanged: requestPaint()
    onReadyChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        const c = getContext("2d")
        c.reset()
        if (!ready || !isImageLoaded(source))
            return
        const k = Math.min(width / probe.sourceSize.width, height / probe.sourceSize.height)
        const w = probe.sourceSize.width * k, h = probe.sourceSize.height * k
        c.drawImage(source, (width - w) / 2, (height - h) / 2, w, h)
        c.globalCompositeOperation = "source-in"
        c.fillStyle = ink
        c.fillRect(0, 0, width, height)
    }
}
