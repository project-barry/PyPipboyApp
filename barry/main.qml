// Pip-Boy: Fallout 4's Pip-Boy on Barry Launcher's screen, ported from
// PyPipboyApp. The game talks to service.py (this app's service, see
// barry-app.json), which serves this window what changed; this asks for it
// a few times a second and draws it in the game's Pip-Boy colour.
//
// STAT (status, S.P.E.C.I.A.L., perks), INV (by category; equip, use, drop),
// DATA (quests and tracking, workshops, statistics), MAP (world: fast
// travel and your marker; local: the game's own map), RADIO.
pragma ComponentBehavior: Bound
import QtQuick
import QtCore
import "qml"

Rectangle {
    id: app
    required property var barry  // from Barry Launcher (AppHost.qml)

    color: Pip.bg
    Component.onCompleted: Pip.barry = barry

    Settings {
        id: saved
        location: app.barry.dataDirUrl + "pipboy.ini"
        property int tab: 0
        property var sub: [0, 0, 0, 0, 0]
    }

    // The service's view: only the sections that changed since the last
    // answer come back.
    property int rev: 0
    property bool asking: false
    Timer {
        interval: 300
        repeat: true
        running: app.barry.serviceUrl !== ""
        triggeredOnStart: true
        onTriggered: {
            if (app.asking)
                return
            app.asking = true
            app.barry.request("GET", "view?since=" + app.rev, null, function(status, reply) {
                app.asking = false
                if (status === 200 && reply) {
                    Pip.take(reply.sections)
                    app.rev = reply.rev
                } else if (status === 0) {
                    Pip.connection = null  // the service is gone; it may come back
                    app.rev = 0
                }
            })
        }
    }

    readonly property var tabs: ["STAT", "INV", "DATA", "MAP", "RADIO"]
    readonly property var subTabs: [["STATUS", "SPECIAL", "PERKS"],
                                    ["WEAPONS", "APPAREL", "AID", "MISC", "JUNK", "MODS", "AMMO"],
                                    ["QUESTS", "WORKSHOPS", "STATS"],
                                    ["WORLD", "LOCAL"],
                                    []]
    readonly property int tab: saved.tab
    readonly property int sub: saved.sub[tab] || 0
    function pickSub(i) {
        const s = saved.sub.slice()
        s[tab] = i
        saved.sub = s
    }
    // Go to a tab and one of its own (for tests and screenshots).
    function show(t, s) {
        saved.tab = t
        pickSub(s)
    }

    // A faint scanline texture, like the Pip-Boy's screen.
    Canvas {
        anchors.fill: parent
        opacity: 0.35
        property color ink: Pip.faint
        onInkChanged: requestPaint()
        onPaint: {
            const c = getContext("2d")
            c.reset()
            c.fillStyle = ink
            for (let y = 0; y < height; y += 6 * Pip.s)
                c.fillRect(0, y, width, 2 * Pip.s)
        }
    }

    // Top: the tabs, the game's date and time, close.
    Item {
        id: top
        width: parent.width
        height: 104 * Pip.s

        TabRow {
            x: 16 * Pip.s
            anchors.verticalCenter: parent.verticalCenter
            tabs: app.tabs
            current: app.tab
            fontSize: Pip.large * 1.1
            onPicked: i => saved.tab = i
        }
        PipText {
            anchors.right: close.left
            anchors.rightMargin: 24 * Pip.s
            anchors.verticalCenter: parent.verticalCenter
            visible: Pip.player !== null
            text: Pip.player ? Pip.date(Pip.player) + "   " + Pip.clock(Pip.player.hour) : ""
            color: Pip.dim
            font.pixelSize: Pip.small
        }
        PipButton {
            id: close
            anchors.right: parent.right
            anchors.rightMargin: 16 * Pip.s
            anchors.verticalCenter: parent.verticalCenter
            implicitWidth: 84 * Pip.s
            text: "✕"
            fontSize: Pip.large
            onClicked: app.barry.close()
        }
        Rectangle {
            anchors.bottom: parent.bottom
            x: 16 * Pip.s
            width: parent.width - 32 * Pip.s
            height: 3 * Pip.s
            color: Pip.color
        }
    }

    // The tab's own tabs.
    Flickable {
        id: subBar
        anchors.top: top.bottom
        x: 16 * Pip.s
        width: parent.width - 32 * Pip.s
        height: app.subTabs[app.tab].length ? 76 * Pip.s : 0
        contentWidth: subRow.width
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true
        TabRow {
            id: subRow
            tabs: app.subTabs[app.tab]
            current: app.sub
            fontSize: Pip.body
            tabHeight: 76 * Pip.s
            onPicked: i => app.pickSub(i)
        }
    }

    // The game is busy: what the Pip-Boy would show instead.
    readonly property var flags: Pip.status ? Pip.status.flags : ({})
    readonly property string gameNote: flags.IsPlayerDead ? "YOU ARE DEAD"
        : flags.IsLoading ? "LOADING…"
        : flags.IsDataUnavailable ? "THE GAME IS NOT SENDING DATA RIGHT NOW"
        : flags.IsInVats || flags.IsInVatsPlayback ? "V.A.T.S."
        : flags.IsPlayerInDialogue ? "IN CONVERSATION"
        : ""

    Item {
        id: content
        anchors.top: subBar.bottom
        anchors.topMargin: 8 * Pip.s
        anchors.bottom: bottom.top
        width: parent.width

        StatusPage { anchors.fill: parent; visible: app.tab === 0 && app.sub === 0 }
        SpecialPage { anchors.fill: parent; visible: app.tab === 0 && app.sub === 1 }
        PerksPage { anchors.fill: parent; visible: app.tab === 0 && app.sub === 2 }
        InventoryPage {
            anchors.fill: parent
            visible: app.tab === 1
            category: ["weapons", "apparel", "aid", "misc", "junk", "mods", "ammo"][app.sub] || "weapons"
        }
        QuestsPage { anchors.fill: parent; visible: app.tab === 2 && app.sub === 0 }
        WorkshopsPage { anchors.fill: parent; visible: app.tab === 2 && app.sub === 1 }
        LogPage { anchors.fill: parent; visible: app.tab === 2 && app.sub === 2 }
        WorldMap { anchors.fill: parent; visible: app.tab === 3 && app.sub === 0 }
        LocalMap { anchors.fill: parent; visible: app.tab === 3 && app.sub === 1 }
        RadioPage { anchors.fill: parent; visible: app.tab === 4 }

        Rectangle {
            visible: app.gameNote !== "" && Pip.connected
            anchors.horizontalCenter: parent.horizontalCenter
            y: 8 * Pip.s
            width: note.implicitWidth + 48 * Pip.s
            height: 64 * Pip.s
            color: Pip.color
            radius: 4 * Pip.s
            PipText {
                id: note
                anchors.centerIn: parent
                text: app.gameNote
                color: Pip.bg
                font.weight: Font.Bold
            }
        }
    }

    // Bottom: HP, level, AP; weight and caps in the inventory.
    Item {
        id: bottom
        anchors.bottom: parent.bottom
        width: parent.width
        height: 96 * Pip.s
        readonly property var p: Pip.player

        Rectangle {
            x: 16 * Pip.s
            width: parent.width - 32 * Pip.s
            height: 3 * Pip.s
            color: Pip.color
        }
        Row {
            anchors.verticalCenter: parent.verticalCenter
            x: 24 * Pip.s
            spacing: 36 * Pip.s
            visible: bottom.p !== null
            PipText {
                text: bottom.p ? "HP " + Pip.pair(bottom.p.hp, bottom.p.maxHp) : ""
                font.weight: Font.Bold
            }
            Row {
                spacing: 16 * Pip.s
                anchors.verticalCenter: parent.verticalCenter
                PipText {
                    text: bottom.p ? "LEVEL " + bottom.p.level : ""
                    font.weight: Font.Bold
                }
                Meter {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 220 * Pip.s
                    value: bottom.p ? bottom.p.xp : 0
                }
            }
            PipText {
                text: bottom.p ? "AP " + Pip.pair(bottom.p.ap, bottom.p.maxAp) : ""
                font.weight: Font.Bold
            }
        }
        PipText {
            anchors.right: parent.right
            anchors.rightMargin: 24 * Pip.s
            anchors.verticalCenter: parent.verticalCenter
            visible: bottom.p !== null
            text: bottom.p ? "⚖ " + Pip.pair(bottom.p.weight, bottom.p.maxWeight) + "   ₵ " + bottom.p.caps : ""
        }
    }

    ConnectPage {
        anchors.fill: parent
        visible: !Pip.connected
    }

    // A line about what just happened (Pip.say).
    Rectangle {
        id: toast
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 120 * Pip.s
        width: Math.min(parent.width - 64 * Pip.s, toastText.implicitWidth + 64 * Pip.s)
        height: toastText.implicitHeight + 32 * Pip.s
        radius: 6 * Pip.s
        color: Pip.bg
        border.color: Pip.color
        border.width: 3 * Pip.s
        opacity: 0
        PipText {
            id: toastText
            anchors.centerIn: parent
            width: Math.min(implicitWidth, app.width - 128 * Pip.s)
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            horizontalAlignment: Text.AlignHCenter
            text: Pip.toast
        }
        Connections {
            target: Pip
            function onToastSerialChanged() { toastShow.restart() }
        }
        SequentialAnimation {
            id: toastShow
            NumberAnimation { target: toast; property: "opacity"; to: 1; duration: 120 }
            PauseAnimation { duration: 3000 }
            NumberAnimation { target: toast; property: "opacity"; to: 0; duration: 400 }
        }
    }
}
