#!/usr/bin/env python3
"""Pip-Boy for Barry Launcher: the service.

Barry Launcher starts this with the app (barry-app.json "service") and
stops it when the app closes. It connects to Fallout 4's Pip-Boy app
interface (TCP 27000) with pypipboy, keeps the game's data tree, and serves
the app (main.qml) on 127.0.0.1:BARRY_SERVICE_PORT. Every request must
carry BARRY_SERVICE_TOKEN (X-Barry-Token header, or ?token= for images).

  GET  /view?since=REV   the sections of the view that changed after REV:
                         {"rev": N, "sections": {"player": {...}, ...}}
  GET  /localmap.png     the last local map snapshot, tinted
  GET  /discover         games that answer on the network (UDP 28000)
  POST /action {"do": ...}  connect {host}, disconnect, stimpak, radaway,
                         use {id}, drop {id, count}, radio {id},
                         quest {id}, travel {id}, marker {x, y},
                         unmarker, localmap

The view is built from the tree at most every BUILD_S seconds, section by
section (build_*); a section's rev changes only when its JSON does, so the
app downloads and redraws only what changed.

To try it without Barry Launcher:
  BARRY_SERVICE_PORT=47900 BARRY_SERVICE_TOKEN=dev python3 service.py
"""
import json
import logging
import os
import signal
import struct
import sys
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pypipboy.datamanager import PipboyDataManager, ePipboyValueType  # noqa: E402
from pypipboy.network import NetworkChannel  # noqa: E402

PORT = int(os.environ.get("BARRY_SERVICE_PORT") or 0)
TOKEN = os.environ.get("BARRY_SERVICE_TOKEN", "")
DATA = os.environ.get("BARRY_APP_DATA") or os.path.join(HERE, ".data")
SETTINGS = os.path.join(DATA, "pipboy.json")
GAME_PORT = NetworkChannel.PIPBOYAPP_PORT
RETRY_S = 3          # between connection attempts while waiting for the game
BUILD_S = 0.25       # the view is rebuilt at most this often
TRAVEL_WAIT_S = 4    # how long a fast travel waits for the game's answer
DEFAULT_COLOR = [0.08, 1.0, 0.09]  # the Pip-Boy's own green

# Inventory filterFlag bits, in the order an item is put in a tab.
CATEGORIES = [("weapons", 1 << 1), ("apparel", 1 << 2), ("aid", 1 << 3), ("junk", 1 << 10),
              ("mods", 1 << 11), ("ammo", 1 << 12), ("misc", 1 << 9 | 1 << 7 | 1 << 13)]
DAMAGE_TYPES = {1: "phys", 2: "poison", 3: "unknown", 4: "energy", 5: "unknown", 6: "rad", 10: "ammo"}
CARD_LABELS = {"$val": "Value", "$wt": "Weight", "$acc": "Accuracy", "$rng": "Range",
               "$ROF": "Rate of fire", "$speed": "Speed"}

log = logging.getLogger("pipboy")


def plain(v):
    """A pypipboy value as plain Python (dicts keyed as the game spells them)."""
    if v is None:
        return None
    if v.pipType == ePipboyValueType.OBJECT:
        return {v.child(i).pipParentKey: plain(v.child(i)) for i in range(v.childCount())}
    if v.pipType == ePipboyValueType.ARRAY:
        return [plain(c) for c in v.value()]
    return v.value()


def child(v, *path):
    """The value at path under v (keys are case-insensitive), or None."""
    for key in path:
        if v is None:
            return None
        v = v.child(key)
    return v


def val(v, *path, default=None):
    v = child(v, *path)
    if v is None or v.pipType != ePipboyValueType.PRIMITIVE:
        return default
    return v.value()


def items(v):
    """The children of an array value."""
    return v.value() if v is not None and v.pipType == ePipboyValueType.ARRAY else []


def num(x, digits=1):
    """A number for a label: no ".0", at most digits decimals."""
    if isinstance(x, float):
        x = round(x, digits)
        if x == int(x):
            return str(int(x))
        return str(x)
    return str(x)


def png(width, height, pixels, color):
    """An 8-bit palette PNG of a grey local map, black to color."""
    stride = len(pixels) // height if height else 0
    rows = b"".join(b"\x00" + bytes(pixels[y * stride:y * stride + width]) for y in range(height))
    r, g, b = (max(0.0, min(1.0, c)) for c in color)
    palette = bytes(int(c * i) for i in range(256) for c in (r, g, b))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", palette) + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


class DataManager(PipboyDataManager):
    """pypipboy's, with the tree changed only under lock (the view is built
    from another thread), and a flag for "something changed"."""

    def __init__(self, on_change):
        super().__init__()
        self.lock = threading.RLock()
        self._on_change = on_change

    def _onMessageReceived(self, msg):
        with self.lock:
            super()._onMessageReceived(msg)
        self._on_change()


class Pipboy:
    def __init__(self):
        self.dm = DataManager(self.changed)
        self.dm.networkchannel.registerConnectionListener(self.on_connection)
        self.dm.registerLocalMapListener(self.on_local_map)
        self.settings = self.load_settings()
        self.host = self.settings.get("host") or "127.0.0.1"
        self.want = True             # keep trying to connect
        self.state = "connecting"    # connecting | waiting | refused | connected
        self.error = ""
        self.attempt = threading.Event()  # wakes the connector early
        self.dirty = threading.Event()
        self.view_lock = threading.Lock()
        self.rev = 0
        self.sections = {}           # name -> (rev, json text)
        self.map_png = b""
        self.map_info = None
        self.map_serial = 0
        self.dirty.set()

    # Settings ----------------------------------------------------------

    def load_settings(self):
        try:
            with open(SETTINGS, encoding="utf-8") as fh:
                s = json.load(fh)
            return s if isinstance(s, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_settings(self):
        os.makedirs(DATA, exist_ok=True)
        tmp = SETTINGS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.settings, fh, indent=1)
        os.replace(tmp, SETTINGS)

    # Connection --------------------------------------------------------

    def changed(self):
        self.dirty.set()

    def on_connection(self, connected, errstatus, errmsg):
        if connected:
            self.state = "connected"
            self.error = ""
            log.info("connected to %s (game %s, %s)", self.host,
                     self.dm.networkchannel.hostVersion, self.dm.networkchannel.hostLang)
        else:
            self.state = "connecting" if self.want else "waiting"
            if errstatus:
                self.error = "The game closed the connection."
                log.info("connection lost: %s", errmsg)
            self.attempt.set()
        self.changed()

    def connector(self):
        """Connect, and connect again whenever the connection is lost, while
        the app wants a game: the game may start after the app."""
        while True:
            if self.want and not self.dm.networkchannel.isConnected:
                host = self.host
                self.state = "connecting"
                self.changed()
                try:
                    ok = self.dm.connect(host, GAME_PORT)
                    if not ok and host == self.host:
                        self.state = "refused"
                        self.error = "The game turned the connection down: is another Pip-Boy app connected?"
                except (OSError, Exception) as err:  # noqa: B014 - pypipboy raises bare Exception
                    if host == self.host and self.want:
                        self.state = "waiting"
                        self.error = (f"No game at {host}." if isinstance(err, ConnectionRefusedError)
                                      else f"Cannot reach {host}: {err}")
                self.changed()
            self.attempt.wait(RETRY_S)
            self.attempt.clear()

    def connect(self, host):
        host = str(host or "").strip() or "127.0.0.1"
        if self.dm.networkchannel.isConnected:
            if host == self.host:
                return {"ok": True}
            self.dm.disconnect()
        self.dm.cancelConnectionAttempt()
        self.host = host
        self.want = True
        self.error = ""
        self.settings["host"] = host
        self.save_settings()
        self.attempt.set()
        return {"ok": True}

    def disconnect(self):
        self.want = False
        self.dm.cancelConnectionAttempt()
        self.dm.disconnect()
        self.state = "waiting"
        self.error = ""
        self.changed()
        return {"ok": True}

    # Local map ---------------------------------------------------------

    def on_local_map(self, lmap):
        color = self.color()
        try:
            data = png(lmap.width, lmap.height, lmap.pixels, color)
        except (ValueError, ZeroDivisionError) as err:
            log.warning("bad local map: %s", err)
            return
        with self.view_lock:
            self.map_png = data
            self.map_serial += 1
            self.map_info = {"serial": self.map_serial, "width": lmap.width, "height": lmap.height,
                             "nw": list(lmap.nw), "ne": list(lmap.ne), "sw": list(lmap.sw)}
        self.changed()

    # The view ----------------------------------------------------------

    def color(self):
        with self.dm.lock:
            c = plain(child(self.dm.rootObject, "Status", "EffectColor"))
        return c if isinstance(c, list) and len(c) == 3 else DEFAULT_COLOR

    def builder(self):
        while True:
            self.dirty.wait()
            self.dirty.clear()
            try:
                self.build()
            except Exception:  # noqa: BLE001 - a bad tree must not stop the view
                log.exception("cannot build the view")
            time.sleep(BUILD_S)

    def build(self):
        root = self.dm.rootObject if self.state == "connected" else None
        out = {"connection": self.build_connection()}
        with self.dm.lock:
            for name, fn in (("status", build_status), ("player", build_player), ("special", build_special),
                             ("perks", build_perks), ("effects", build_effects), ("inventory", build_inventory),
                             ("quests", build_quests), ("stats", build_stats), ("workshops", build_workshops),
                             ("radio", build_radio), ("world", build_world), ("local", build_local)):
                out[name] = fn(root) if root is not None else None
        with self.view_lock:
            if out["local"] is not None:
                out["local"]["image"] = self.map_info
            changed = False
            for name, section in out.items():
                text = json.dumps(section, separators=(",", ":"))
                old = self.sections.get(name)
                if old is None or old[1] != text:
                    if not changed:
                        self.rev += 1
                        changed = True
                    self.sections[name] = (self.rev, text)

    def build_connection(self):
        ch = self.dm.networkchannel
        return {"state": self.state, "host": self.host, "error": self.error,
                "version": ch.hostVersion if ch.isConnected else None,
                "lang": ch.hostLang if ch.isConnected else None}

    def view(self, since):
        with self.view_lock:
            parts = [f'"{n}":{t}' for n, (r, t) in self.sections.items() if r > since]
            return '{"rev":%d,"sections":{%s}}' % (self.rev, ",".join(parts))

    # Actions -----------------------------------------------------------

    def item(self, pip_id):
        try:
            v = self.dm.getPipValueById(int(pip_id))
        except (TypeError, ValueError):
            v = None
        if v is None:
            raise ValueError("That is gone from the game.")
        return v

    def action(self, body):
        what = body.get("do")
        if what == "connect":
            return self.connect(body.get("host"))
        if what == "disconnect":
            return self.disconnect()
        if not self.dm.networkchannel.isConnected:
            return {"ok": False, "error": "Not connected to the game."}
        dm = self.dm
        try:
            with dm.lock:
                if what == "stimpak":
                    dm.rpcUseStimpak()
                elif what == "radaway":
                    dm.rpcUseRadAway()
                elif what == "use":
                    dm.rpcUseItem(self.item(body.get("id")))
                elif what == "drop":
                    dm.rpcDropItem(self.item(body.get("id")), max(1, int(body.get("count", 1))))
                elif what == "radio":
                    dm.rpcToggleRadioStation(self.item(body.get("id")))
                elif what == "quest":
                    dm.rpcToggleQuestActive(self.item(body.get("id")))
                elif what == "marker":
                    dm.rpcSetCustomMarker(float(body["x"]), float(body["y"]))
                elif what == "unmarker":
                    dm.rpcRemoveCustomMarker()
                elif what == "localmap":
                    dm.rpcRequestLocalMapSnapshot()
                elif what == "travel":
                    return self.travel(self.item(body.get("id")))
                else:
                    return {"ok": False, "error": f"no action {what!r}"}
        except (KeyError, TypeError, ValueError, OSError) as err:
            return {"ok": False, "error": str(err)}
        except Exception as err:  # noqa: BLE001 - pypipboy raises bare Exception
            return {"ok": False, "error": str(err)}
        return {"ok": True}

    def travel(self, location):
        answer = {}
        done = threading.Event()

        def result(resp):
            answer.update(resp)
            done.set()
        self.dm.rpcFastTravel(location, result)
        # The lock is held by action(): let the reply in while waiting.
        self.dm.lock.release()
        try:
            done.wait(TRAVEL_WAIT_S)
        finally:
            self.dm.lock.acquire()
        if not done.is_set():
            return {"ok": True, "result": None}
        if not answer.get("allowed", True):
            return {"ok": False, "error": "You can't fast travel right now."}
        return {"ok": bool(answer.get("success", True)), "result": answer,
                "error": "" if answer.get("success", True) else "Fast travel failed."}


# Section builders: root is the game's tree (never None), under the lock. ---

def build_status(root):
    s = child(root, "Status")
    color = plain(child(s, "EffectColor"))
    flags = {k: bool(val(s, k, default=False)) for k in (
        "IsDataUnavailable", "IsLoading", "IsPlayerDead", "IsInVats", "IsInVatsPlayback", "IsPlayerInDialogue",
        "IsPipboyNotEquipped", "IsPlayerPipboyLocked", "IsMenuOpen", "IsInAnimation", "IsPlayerMovementLocked")}
    return {"color": color if isinstance(color, list) and len(color) == 3 else DEFAULT_COLOR, "flags": flags}


def build_player(root):
    p = child(root, "PlayerInfo")
    st = child(root, "Stats")
    inv = child(root, "Inventory")
    return {
        "name": val(p, "PlayerName", default=""), "level": val(p, "XPLevel", default=0),
        "xp": val(p, "XPProgressPct", default=0.0), "perkPoints": val(p, "PerkPoints", default=0),
        "hp": val(p, "CurrHP", default=0.0), "maxHp": val(p, "MaxHP", default=0.0),
        "hpGain": val(p, "CurrentHPGain", default=0.0),
        "ap": val(p, "CurrAP", default=0.0), "maxAp": val(p, "MaxAP", default=0.0),
        "weight": val(p, "CurrWeight", default=0.0), "maxWeight": val(p, "MaxWeight", default=0.0),
        "caps": val(p, "Caps", default=0),
        "hour": val(p, "TimeHour", default=0.0), "day": val(p, "DateDay", default=1),
        "month": val(p, "DateMonth", default=0), "year": val(p, "DateYear", default=287),
        "limbs": {k: val(st, f"{k}Condition", default=100.0) for k in ("Head", "Torso", "LArm", "RArm", "LLeg", "RLeg")},
        "stimpaks": val(st, "StimpakCount", default=0), "radaways": val(st, "RadawayCount", default=0),
        "stimpakOk": bool(val(inv, "stimpakObjectIDIsValid", default=False)),
        "radawayOk": bool(val(inv, "radawayObjectIDIsValid", default=False)),
        "damage": damage_list(child(p, "TotalDamages")),
        "resist": damage_list(child(p, "TotalResists")),
        "world": val(root, "Map", "CurrWorldspace", default=""),
        "cell": val(root, "Map", "CurrCell", default=""),
    }


def damage_list(v):
    out = []
    for d in items(v):
        value = val(d, "Value", default=0)
        if value:
            out.append({"type": DAMAGE_TYPES.get(val(d, "type"), "unknown"), "value": num(value, 0)})
    return out


def build_special(root):
    return [{"name": val(s, "Name", default=""), "value": val(s, "Value", default=0),
             "modifier": val(s, "Modifier", default=0), "desc": val(s, "Description", default="")}
            for s in items(child(root, "Special"))]


def build_perks(root):
    out = []
    for p in items(child(root, "Perks")):
        rank = val(p, "Rank", default=0)
        name = val(p, "Name", default="")
        if rank <= 0 or not name or not val(p, "ListVisible", default=True):
            continue
        ranks = [val(r, "Description", default="") for r in items(child(p, "Perks"))]
        out.append({"name": name, "rank": rank, "max": val(p, "MaxRank", default=rank),
                    "desc": ranks[rank - 1] if 0 < rank <= len(ranks) else "",
                    "next": ranks[rank] if rank < len(ranks) and ranks[rank] != ranks[rank - 1] else ""})
    out.sort(key=lambda p: p["name"].lower())
    return out


def build_effects(root):
    out = []
    for e in items(child(root, "Stats", "ActiveEffects")):
        lines = {}
        for x in items(child(e, "Effects")):
            if not val(x, "IsActive", default=False) or val(x, "CustomDesc", default=False):
                continue
            name = val(x, "Name", default="")
            line = lines.setdefault(name, {"name": name, "value": 0.0, "pct": bool(val(x, "showAsPercent")),
                                           "duration": 0.0})
            line["value"] += val(x, "Value", default=0.0) or 0.0
            line["duration"] = max(line["duration"], val(x, "duration", default=0.0) or 0.0)
        shown = [dict(l, value=num(l["value"]) + ("%" if l["pct"] else ""),
                      duration=int(l["duration"])) for l in lines.values() if l["value"]]
        if shown:
            out.append({"source": val(e, "Source", default=""), "lines": shown})
    return out


def card(item):
    """An item's card: [[label, text]], damage and resistances first."""
    dmg, dr, ammo, rows = [], [], [], []
    for c in items(child(item, "itemCardInfoList")):
        text = val(c, "text", default="")
        value = val(c, "Value")
        if isinstance(value, str) and value.startswith("$"):
            value = value[1:].capitalize()  # "$MEDIUM": the game's own label
        if val(c, "damageType") == 10:
            ammo.append(f"{text} ({num(value, 0)})")  # a gun's ammo: its name and how many
        elif text == "$dmg":
            kind = DAMAGE_TYPES.get(val(c, "damageType"), "unknown")
            if value:
                dmg.append(f"{num(value, 0)} {kind}" if kind != "phys" else num(value, 0))
        elif text == "$dr":
            if value:
                kind = DAMAGE_TYPES.get(val(c, "damageType"), "unknown")
                dr.append(f"{num(value, 0)} {kind}" if kind != "phys" else num(value, 0))
        elif text in CARD_LABELS:
            if value or text in ("$val", "$wt"):
                rows.append([CARD_LABELS[text], num(value, val(c, "precision", default=1))])
        elif text and isinstance(value, str):
            rows.append([text.lstrip("$").capitalize(), value])  # "health": "50/50"
        elif text and value:
            # An effect (aid, apparel): "HP +4 over 10 s", "Rads -100".
            v = num(value) + ("%" if val(c, "showAsPercent") else "")
            dur = val(c, "duration", default=0.0)
            if val(c, "scaleWithDuration") and dur:
                v += f" over {int(dur)} s"
            elif dur:
                v += f" for {int(dur)} s"
            rows.append([text.lstrip("$"), ("+" if isinstance(value, (int, float)) and value > 0 else "") + v])
    head = []
    if dmg:
        head.append(["Damage", ", ".join(dmg)])
    if dr:
        head.append(["Damage resist", ", ".join(dr)])
    if ammo:
        head.append(["Ammo", ", ".join(ammo)])
    return head + rows


def category(flags):
    for name, bits in CATEGORIES:
        if flags & bits:
            return name
    return "misc"


def build_inventory(root):
    inv = child(root, "Inventory")
    dm = root.datamanager
    out = {name: [] for name, _ in CATEGORIES}
    seen = set()
    for ref in items(child(inv, "sortedIDS")):
        item = dm.getPipValueById(ref.value())
        if item is None or item.pipId in seen or item.pipType != ePipboyValueType.OBJECT:
            continue
        seen.add(item.pipId)
        flags = val(item, "filterFlag", default=0)
        fav = val(item, "favorite", default=-2)
        out[category(flags)].append({
            "id": item.pipId, "name": (val(item, "text", default="") or "").strip(),
            "count": val(item, "count", default=1), "equipped": (val(item, "equipState", default=0) or 0) > 0,
            "legendary": bool(val(item, "isLegendary", default=False)),
            "holotape": bool(flags & 1 << 13),
            "fav": fav if isinstance(fav, int) and fav >= 0 else None,
            "card": card(item)})
    out["components"] = [{"name": val(c, "text", default=""), "count": val(c, "count", default=0)}
                         for c in items(child(inv, "InvComponents"))]
    return out


def build_quests(root):
    out = []
    for q in items(child(root, "Quests")):
        current = bool(val(q, "enabled", default=False))
        objectives = []
        for o in items(child(q, "objectives")):
            done = bool(val(o, "completed", default=False))
            if not (val(o, "enabled", default=False) or done):
                continue
            objectives.append({"text": val(o, "text", default=""), "done": done,
                               "failed": bool(val(o, "failed", default=False))})
        out.append({"id": q.pipId, "name": val(q, "text", default=""), "desc": val(q, "desc", default=""),
                    "current": current, "active": bool(val(q, "active", default=False)),
                    "misc": val(q, "sortval", default=0) == 0xFFFFFFFF, "objectives": objectives})
    # Current ones first (tracked at the top), then the finished.
    out.sort(key=lambda q: (not q["current"], not q["active"]))
    return out


def build_stats(root):
    out = []
    for group in items(child(root, "Log")):
        rows = [{"text": val(r, "text", default=""), "value": num(val(r, "Value", default=0))}
                for r in items(child(group, "statArray"))
                if val(r, "showIfZero", default=False) or val(r, "Value", default=0)]
        out.append({"name": (val(group, "text", default="") or "").lstrip("$"), "rows": rows})
    return out


def build_workshops(root):
    out = []
    for w in items(child(root, "Workshop")):
        data = {val(d, "text", default=""): {"value": val(d, "Value", default=0), "rating": val(d, "rating", default=0)}
                for d in items(child(w, "workshopData"))}
        out.append({"id": w.pipId, "name": val(w, "text", default=""), "owned": bool(val(w, "owned", default=False)),
                    "rating": val(w, "rating", default=0), "data": data})
    out.sort(key=lambda w: (not w["owned"], w["name"].lower()))
    return out


def build_radio(root):
    return [{"id": r.pipId, "name": val(r, "text", default=""), "freq": round(val(r, "frequency", default=0.0) or 0.0, 1),
             "active": bool(val(r, "active", default=False)), "inRange": bool(val(r, "inRange", default=False))}
            for r in items(child(root, "Radio"))]


def point(v):
    if v is None:
        return None
    return {"x": val(v, "X", default=0.0), "y": val(v, "Y", default=0.0),
            "rot": val(v, "Rotation"), "visible": val(v, "Visible", default=True)}


def extents(v):
    e = plain(v) or {}
    try:
        return {"nw": [e["NWX"], e["NWY"]], "ne": [e["NEX"], e["NEY"]], "sw": [e["SWX"], e["SWY"]]}
    except KeyError:
        return None


def markers(m):
    custom = point(child(m, "Custom"))
    power = point(child(m, "PowerArmor"))
    return {
        "extents": extents(child(m, "Extents")),
        "player": point(child(m, "Player")),
        "custom": custom if custom and custom["visible"] else None,
        "powerArmor": power if power and power["visible"] else None,
        "quests": [dict(point(q), name=val(q, "Name", default="")) for q in items(child(m, "Quests"))],
    }


def build_world(root):
    w = child(root, "Map", "World")
    out = markers(w)
    out["locations"] = [
        {"id": l.pipId, "name": val(l, "Name", default=""), "x": val(l, "X", default=0.0),
         "y": val(l, "Y", default=0.0), "type": val(l, "type", default=-1),
         "discovered": bool(val(l, "Discovered", default=False)), "cleared": bool(val(l, "ClearedStatus", default=False))}
        for l in items(child(w, "Locations")) if val(l, "Visible", default=False) or val(l, "Discovered", default=False)]
    return out


def build_local(root):
    m = child(root, "Map", "Local")
    out = markers(m)
    out["doors"] = [dict(point(d), name=val(d, "Name", default="")) for d in items(child(m, "Doors"))]
    return out


# HTTP --------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    pipboy = None  # set in main
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet: the app polls
        pass

    def allowed(self, query):
        token = self.headers.get("X-Barry-Token") or (query.get("token") or [""])[0]
        if TOKEN and token == TOKEN:
            return True
        self.send(403, b'{"error":"no token"}')
        return False

    def send(self, code, body, kind="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if not self.allowed(query):
            return
        if url.path == "/view":
            try:
                since = int((query.get("since") or ["0"])[0])
            except ValueError:
                since = 0
            self.send(200, self.pipboy.view(since).encode())
        elif url.path == "/localmap.png":
            with self.pipboy.view_lock:
                data = self.pipboy.map_png
            if data:
                self.send(200, data, "image/png")
            else:
                self.send(404, b'{"error":"no map yet"}')
        elif url.path == "/discover":
            hosts = discover()
            self.send(200, json.dumps({"hosts": hosts}).encode())
        else:
            self.send(404, b'{"error":"not found"}')

    def do_POST(self):
        url = urlparse(self.path)
        if not self.allowed(parse_qs(url.query)):
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
            if not isinstance(body, dict):
                raise ValueError("not an object")
        except ValueError:
            self.send(400, b'{"ok":false,"error":"bad JSON"}')
            return
        if url.path == "/action":
            reply = self.pipboy.action(body)
            self.send(200 if reply.get("ok") else 400, json.dumps(reply).encode())
        else:
            self.send(404, b'{"error":"not found"}')


def discover():
    """The games that answer Fallout 4's discovery broadcast, this device's
    first (a game here may not hear its own broadcast)."""
    found = {}
    for addr in ("127.0.0.1", NetworkChannel.AUTODISCOVER_ADDR):
        try:
            for h in NetworkChannel.discoverHosts(addr, timeout=1.5 if addr == "127.0.0.1" else 2.5):
                found.setdefault(h.get("addr"), {"addr": h.get("addr"), "busy": bool(h.get("IsBusy")),
                                                 "machine": h.get("MachineType", "")})
        except OSError as err:
            log.info("discovery to %s failed: %s", addr, err)
    return list(found.values())


def main():
    logging.basicConfig(level=logging.INFO, format="pipboy: %(message)s", stream=sys.stdout)
    if not PORT or not TOKEN:
        print("pipboy: run by Barry Launcher (BARRY_SERVICE_PORT, BARRY_SERVICE_TOKEN)", file=sys.stderr)
        return 2
    pipboy = Pipboy()
    Handler.pipboy = pipboy
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
    threading.Thread(target=pipboy.connector, daemon=True).start()
    threading.Thread(target=pipboy.builder, daemon=True).start()
    log.info("serving the app on 127.0.0.1:%d; game at %s", PORT, pipboy.host)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
