// Before a game is connected: what the service is doing, where it looks
// (this device by default), games found on the network, and how to switch
// on the game's side.
import QtQuick

Rectangle {
    id: page
    color: Pip.bg
    readonly property var c: Pip.connection
    property var found: []
    property bool searching: false

    function search() {
        searching = true
        found = []
        Pip.barry.request("GET", "discover", null, function(status, reply) {
            searching = false
            found = reply && reply.hosts ? reply.hosts : []
            if (found.length === 0)
                Pip.say("No games answered. Is the Pip-Boy app on in the game's settings?")
        })
    }

    Column {
        anchors.centerIn: parent
        width: parent.width * 0.8
        spacing: 28 * Pip.s

        PipText {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: "PIP-BOY"
            font.pixelSize: Pip.huge * 1.4
            font.weight: Font.Black
            font.letterSpacing: 12 * Pip.s
        }
        PipText {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            font.pixelSize: Pip.large
            text: !Pip.barry || !Pip.barry.serviceUrl ? "This Barry Launcher is too old for this app: update PB-OS."
                : !page.c ? "Starting…"
                : page.c.state === "connected" ? "Connected. Waiting for the game's data…"
                : page.c.state === "waiting" && page.c.error === "" ? "Not connected."
                : "Looking for Fallout 4 at " + page.c.host + "…"
        }
        PipText {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            visible: page.c !== null && page.c.error !== ""
            text: page.c ? page.c.error : ""
            color: Pip.dim
        }

        // Where to look.
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 16 * Pip.s
            Rectangle {
                width: 520 * Pip.s
                height: 84 * Pip.s
                color: "transparent"
                border.color: host.activeFocus ? Pip.color : Pip.dim
                border.width: 3 * Pip.s
                radius: 6 * Pip.s
                TextInput {
                    id: host
                    anchors.fill: parent
                    anchors.leftMargin: 20 * Pip.s
                    anchors.rightMargin: 20 * Pip.s
                    verticalAlignment: TextInput.AlignVCenter
                    color: Pip.color
                    selectionColor: Pip.color
                    selectedTextColor: Pip.bg
                    font.family: Pip.font
                    font.pixelSize: Pip.body
                    inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhPreferNumbers
                    text: page.c ? page.c.host : "127.0.0.1"
                    onAccepted: Pip.act("connect", { host: text })
                }
            }
            PipButton {
                text: "CONNECT"
                onClicked: Pip.act("connect", { host: host.text })
            }
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 16 * Pip.s
            PipButton {
                text: "THIS DEVICE"
                onClicked: { host.text = "127.0.0.1"; Pip.act("connect", { host: "127.0.0.1" }) }
            }
            PipButton {
                text: page.searching ? "SEARCHING…" : "FIND GAMES"
                enabled: !page.searching
                onClicked: page.search()
            }
        }
        Repeater {
            model: page.found
            delegate: PipButton {
                required property var modelData
                anchors.horizontalCenter: parent.horizontalCenter
                width: 640 * Pip.s
                text: modelData.addr + " · " + (modelData.machine || "game") + (modelData.busy ? " · busy" : "")
                onClicked: { host.text = modelData.addr; Pip.act("connect", { host: modelData.addr }) }
            }
        }

        PipText {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            font.pixelSize: Pip.small
            color: Pip.dim
            text: "In Fallout 4, turn on Settings › Gameplay › Pip-Boy App, and load a save. "
                  + "A game on this device is at 127.0.0.1; one on another PC, at its address on your network "
                  + "(port 27000). Only one Pip-Boy app can be connected to a game at a time."
        }
    }
}
