// The app's shared state: the service's view of the game (one property per
// section, so a page redraws only when its own section changes), the
// Pip-Boy's colour as the game sets it, sizes, and calls to the service.
pragma Singleton
import QtQuick

QtObject {
    id: pip

    property var barry: null
    readonly property real s: barry ? barry.scale : 1

    // Sections of the view (service.py build_*); null until known.
    property var connection: null
    property var status: null
    property var player: null
    property var special: null
    property var perks: null
    property var effects: null
    property var inventory: null
    property var quests: null
    property var stats: null
    property var workshops: null
    property var radio: null
    property var world: null
    property var local: null
    readonly property bool connected: connection !== null && connection.state === "connected" && player !== null

    // The game's Pip-Boy colour (Settings > Display), the green by default.
    readonly property var rgb: status && status.color ? status.color : [0.08, 1.0, 0.09]
    readonly property color color: Qt.rgba(rgb[0], rgb[1], rgb[2], 1)
    readonly property color dim: Qt.rgba(rgb[0], rgb[1], rgb[2], 0.55)
    readonly property color faint: Qt.rgba(rgb[0], rgb[1], rgb[2], 0.18)
    readonly property color bg: Qt.rgba(rgb[0] * 0.05, rgb[1] * 0.05, rgb[2] * 0.05, 1)
    readonly property string font: "Noto Sans Mono"

    // Text sizes.
    readonly property real small: 24 * s
    readonly property real body: 30 * s
    readonly property real large: 38 * s
    readonly property real huge: 64 * s

    // A line for a few seconds at the bottom (main.qml).
    property string toast: ""
    property int toastSerial: 0
    function say(text) {
        toast = text
        toastSerial++
    }

    // Ask the service to do something in the game (service.py action);
    // a refusal is shown as a toast.
    function act(what, args, done) {
        if (!barry)
            return
        const body = Object.assign({ "do": what }, args || {})
        barry.request("POST", "action", body, function(status, reply) {
            if (status === 0)
                say("The Pip-Boy service is not answering.")
            else if (reply && !reply.ok && reply.error)
                say(reply.error)
            if (done)
                done(reply && reply.ok, reply)
        })
    }

    function take(sections) {
        for (const k in sections)
            if (k in pip)
                pip[k] = sections[k]
    }

    // "123/185"
    function pair(a, b) {
        return Math.round(a) + "/" + Math.round(b)
    }

    function clock(hour) {
        const h = Math.floor(hour)
        const m = Math.floor((hour - h) * 60)
        return (h % 12 || 12) + ":" + (m < 10 ? "0" : "") + m + (h < 12 ? " AM" : " PM")
    }
    function date(p) {
        return p.month + "." + p.day + "." + (2000 + p.year)  // the month counts from 1
    }
}
