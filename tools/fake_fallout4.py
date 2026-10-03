#!/usr/bin/env python3
"""A stand-in for Fallout 4's Pip-Boy app interface, to try the Barry app
(barry/) without the game: it listens on TCP 27000 and answers discovery on
UDP 28000 as the game does, sends a made-up character's data, and acts on
the app's commands (use and drop items, radio, quests, map marker, fast
travel, local map snapshots). The clock runs and AP refills.

  python3 tools/fake_fallout4.py [--port 27000] [--capture FILE]

--capture sends a recorded DATA_UPDATE payload (a game's first message, as
saved by other Pip-Boy tools) in place of the made-up data; commands then
only answer, they change nothing.

Everything here is invented; nothing is taken from the game.
"""
import argparse
import json
import math
import os
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "barry"))
from pypipboy.dataencoder import DataUpdateEncoder  # noqa: E402
from pypipboy.types import eMessageType, eRequestType, eValueType  # noqa: E402


class Tree:
    """The game's data as nodes with fixed ids; changes go out as records."""

    def __init__(self):
        self.next_id = 0
        self.nodes = {}  # id -> [type, value, parent]; value: primitive, [ids], or {key: id}

    def add(self, value):
        """Ids for value and everything in it; the root gets 0 when added first."""
        if isinstance(value, dict):
            node_id = self._new(eValueType.OBJECT, None)
            self.nodes[node_id][1] = {k: self.add(v) for k, v in value.items()}
        elif isinstance(value, list):
            node_id = self._new(eValueType.ARRAY, None)
            self.nodes[node_id][1] = [self.add(v) for v in value]
        else:
            if isinstance(value, bool):
                kind = eValueType.BOOL
            elif isinstance(value, int):
                kind = eValueType.INT_32 if -2**31 <= value < 2**31 else eValueType.UINT_32
            elif isinstance(value, float):
                kind = eValueType.FLOAT
            else:
                kind = eValueType.STRING
                value = str(value)
            node_id = self._new(kind, value)
        return node_id

    def _new(self, kind, value):
        node_id = self.next_id
        self.next_id += 1
        self.nodes[node_id] = [kind, value]
        return node_id

    def records(self, node_id):
        """node_id and all under it, children first (as the game sends)."""
        out = []
        kind, value = self.nodes[node_id]
        if kind == eValueType.OBJECT:
            for c in value.values():
                out += self.records(c)
            out.append((node_id, kind, (list(value.items()), [])))
        elif kind == eValueType.ARRAY:
            for c in value:
                out += self.records(c)
            out.append((node_id, kind, list(value)))
        else:
            out.append((node_id, kind, value))
        return out

    def get(self, *path, node_id=0):
        for key in path:
            value = self.nodes[node_id][1]
            node_id = value[key]
        return node_id

    def value(self, *path, node_id=0):
        return self.nodes[self.get(*path, node_id=node_id)][1]

    def set(self, *path, value, node_id=0):
        nid = self.get(*path, node_id=node_id)
        self.nodes[nid][1] = value
        return [(nid, self.nodes[nid][0], value)]


LOCATIONS = [
    ("Sanctuary", 13, -80000, 90000), ("Red Rocket Truck Stop", 27, -76000, 84000),
    ("Concord", 49, -62000, 72000), ("Vault 111", 15, -86000, 98000),
    ("Lexington", 49, -40000, 62000), ("Corvega Assembly Plant", 4, -37000, 56000),
    ("Diamond City", 2, 2000, -8000), ("Goodneighbor", 29, 26000, 6000),
    ("Bunker Hill", 17, 24000, 22000), ("The Castle", 53, 44000, -40000),
    ("Abernathy Farm", 26, -70000, 70000), ("Starlight Drive In", 23, -58000, 60000),
    ("Drumlin Diner", 8, -54000, 54000), ("Museum of Freedom", 5, -62500, 72500),
    ("Super Duper Mart", 11, -41000, 63000), ("Back Street Apparel", 9, -6000, 4000),
    ("Quincy Ruins", 10, 64000, -110000), ("Sunshine Tidings Co-op", 13, -60000, 40000),
    ("Tenpines Bluff", 13, -46000, 88000), ("Oberland Station", 13, -80000, 40000),
    ("Hangman's Alley", 13, -2000, 2000), ("Weston Water Treatment", 32, -96000, -6000),
    ("Lake Quannapowitt", 39, 0, 90000), ("Medford Memorial Hospital", 31, 20000, 60000),
    ("Fort Hagen", 7, -98000, 26000), ("Saugus Ironworks", 33, 50000, 76000),
    ("Jamaica Plain", 49, 0, -60000), ("Mass Fusion Building", 54, 18000, 8000),
    ("USS Constitution", 64, 40000, 26000), ("The Glowing Sea", 41, -100000, -120000),
]

ITEMS = [
    # name, filterFlag, count, equipped, card
    ("10mm Pistol", 2, 1, True, [("$dmg", 18, 1), ("10mm", 120, 10), ("$ROF", 46.0), ("$rng", 83.0), ("$acc", 60.0), ("$wt", 4.2), ("$val", 53)]),
    ("Pipe Rifle", 2, 1, False, [("$dmg", 9, 1), (".38", 34, 10), ("$ROF", 16.0), ("$rng", 152.0), ("$acc", 72.0), ("$wt", 6.5), ("$val", 32)]),
    ("Laser Musket", 2, 1, False, [("$dmg", 30, 4), ("Fusion Cell", 40, 10), ("$ROF", 3.0), ("$rng", 191.0), ("$acc", 75.0), ("$wt", 12.6), ("$val", 57)]),
    ("Baseball Bat", 2, 1, False, [("$dmg", 12, 1), ("$speed", "$MEDIUM"), ("$wt", 3.0), ("$val", 25)]),
    ("Frag Grenade", 2, 4, False, [("$dmg", 151, 1), ("$ROF", 0.0), ("$rng", 93.6), ("$wt", 0.5), ("$val", 50)]),
    ("Vault 111 Jumpsuit", 4, 1, True, [("$dr", 5, 1), ("$dr", 5, 4), ("$dr", 10, 6), ("$wt", 1.0), ("$val", 20)]),
    ("Leather Chest Piece", 4, 1, True, [("$dr", 12, 1), ("$dr", 8, 4), ("$wt", 5.0), ("$val", 25)]),
    ("Combat Armor Left Arm", 4, 1, False, [("$dr", 9, 1), ("$dr", 9, 4), ("$wt", 3.0), ("$val", 38)]),
    ("Road Leathers", 4, 1, False, [("$dr", 2, 1), ("$wt", 2.0), ("$val", 10)]),
    ("Stimpak", 8, 9, False, [("HP", 40.0, None, 0.0), ("$wt", 0.1), ("$val", 50)]),
    ("RadAway", 8, 3, False, [("Rads", -300.0, None, 0.0), ("$wt", 0.1), ("$val", 80)]),
    ("Purified Water", 8, 6, False, [("HP", 4.0, None, 10.0), ("$wt", 1.0), ("$val", 20)]),
    ("Nuka-Cola", 8, 2, False, [("AP", 10.0, None, 0.0), ("HP", 10.0, None, 0.0), ("$wt", 1.0), ("$val", 20)]),
    ("Mutfruit", 8, 5, False, [("HP", 10.0, None, 0.0), ("$wt", 0.1), ("$val", 8)]),
    ("Psycho", 8, 1, False, [("DMG", 25.0, True, 120.0), ("$wt", 0.1), ("$val", 50)]),
    ("Bobby Pin", 512, 14, False, [("$wt", 0.0), ("$val", 1)]),
    ("Holotape: Recipes", 512 | 8192, 1, False, [("$wt", 0.0), ("$val", 0)]),
    ("Grognak the Barbarian", 512 | 128, 1, False, [("$wt", 0.0), ("$val", 50)]),
    ("Desk Fan", 1024, 2, False, [("$wt", 3.0), ("$val", 12)]),
    ("Tin Can", 1024, 7, False, [("$wt", 0.5), ("$val", 1)]),
    ("Duct Tape", 1024, 3, False, [("$wt", 0.1), ("$val", 10)]),
    ("Pistol Scope Mod", 2048, 1, False, [("$wt", 1.0), ("$val", 20)]),
    ("10mm Round", 4096, 212, False, [("$wt", 0.0), ("$val", 1)]),
    (".38 Round", 4096, 64, False, [("$wt", 0.0), ("$val", 1)]),
    ("Fusion Cell", 4096, 40, False, [("$wt", 0.0), ("$val", 3)]),
]


def card_entries(card):
    out = []
    for c in card:
        if len(c) == 3 and c[2] == 10:  # a gun's ammo
            out.append({"text": c[0], "Value": c[1], "damageType": 10, "ValueType": 0,
                        "difference": 0.0, "diffRating": 0})
        elif c[0] in ("$dmg", "$dr"):
            out.append({"text": c[0], "Value": float(c[1]), "damageType": c[2], "ValueType": 2,
                        "difference": 0.0, "diffRating": 0})
        elif c[0] == "$val":
            out.append({"text": "$val", "Value": c[1], "ValueType": 0, "difference": 0.0, "diffRating": 0})
        elif c[0] == "$speed":
            out.append({"text": "$speed", "Value": c[1], "ValueType": 1, "difference": 0.0, "diffRating": 0})
        elif c[0].startswith("$"):
            out.append({"text": c[0], "Value": float(c[1]), "ValueType": 2, "precision": 1,
                        "difference": 0.0, "diffRating": 0})
        else:
            out.append({"text": c[0], "Value": float(c[1]), "ValueType": 2, "showAsPercent": bool(c[2]),
                        "duration": float(c[3]), "scaleWithDuration": c[3] > 0, "difference": 0.0, "diffRating": 0})
    return out


def make_data():
    inventory = {"Version": 1, "SortMode": 0, "HolotapePlaying": False, "UnderwearType": 0,
                 "InvComponents": [{"text": t, "count": n, "componentFormID": 1000 + i, "taggedForSearch": False,
                                    "componentOwners": []}
                                   for i, (t, n) in enumerate([("Steel", 24), ("Adhesive", 3), ("Copper", 6),
                                                               ("Screw", 9), ("Wood", 31)])]}
    by_cat = {}
    for i, (name, flags, count, equipped, card) in enumerate(ITEMS):
        by_cat.setdefault(str(29 + i % 20), []).append({
            "text": name, "filterFlag": flags, "count": count, "equipState": 1 if equipped else 0,
            "HandleID": 4207600000 + i, "StackID": [0], "formID": 50000 + i, "favorite": 0 if name == "10mm Pistol" else -2,
            "canFavorite": True, "isLegendary": name == "Laser Musket", "isPowerArmorItem": False,
            "taggedForSearch": False, "FavIconType": 0, "itemCardInfoList": card_entries(card)})
    inventory.update(by_cat)
    special = [(n, v, d) for n, v, d in [
        ("Strength", 4, "Strength is a measure of your raw physical power."),
        ("Perception", 6, "Perception is your environmental awareness and sixth sense."),
        ("Endurance", 3, "Endurance is a measure of your overall physical fitness."),
        ("Charisma", 5, "Charisma is your ability to charm and convince others."),
        ("Intelligence", 7, "Intelligence is a measure of your overall mental acuity."),
        ("Agility", 6, "Agility is a measure of your overall finesse and reflexes."),
        ("Luck", 4, "Luck is a measure of your general good fortune.")]]
    perks = [{"Name": n, "Rank": r, "MaxRank": m, "ListVisible": True, "Clip": 0, "SWFFile": "",
              "Perks": [{"Description": f"{n} rank {k + 1}: {d}"} for k in range(m)]}
             for n, r, m, d in [("Gunslinger", 2, 5, "Pistols do more damage."),
                                ("Hacker", 1, 4, "Hack harder terminals."),
                                ("Local Leader", 1, 2, "Build supply lines between settlements."),
                                ("Lone Wanderer", 0, 4, "Take less damage when alone."),
                                ("Science!", 1, 4, "Build better mods.")]]
    quests = [
        {"text": "Unlikely Valentine", "desc": "A detective in Diamond City may help me find my son.",
         "formID": 9001, "instance": 1, "type": 1, "enabled": True, "active": True, "sortval": 4294967290,
         "SWFFile": "", "objectives": [{"text": "Find Nick Valentine", "enabled": True, "completed": False, "failed": False, "or": False},
                                       {"text": "Talk to Ellie", "enabled": False, "completed": True, "failed": False, "or": False}]},
        {"text": "Sanctuary", "desc": "Help the settlers make Sanctuary a home.", "formID": 9002, "instance": 1,
         "type": 7, "enabled": True, "active": False, "sortval": 4294967291, "SWFFile": "",
         "objectives": [{"text": "Build beds 2/5", "enabled": True, "completed": False, "failed": False, "or": False},
                        {"text": "Build a water pump", "enabled": True, "completed": False, "failed": False, "or": False}]},
        {"text": "Miscellaneous", "desc": "", "formID": 9003, "instance": 1, "type": 6, "enabled": True,
         "active": False, "sortval": 4294967295, "SWFFile": "",
         "objectives": [{"text": "Find the missing caravan", "enabled": True, "completed": False, "failed": False, "or": False}]},
        {"text": "Out of Time", "desc": "I left the vault.", "formID": 9004, "instance": 1, "type": 1,
         "enabled": False, "active": False, "sortval": 4294967200, "SWFFile": "",
         "objectives": [{"text": "Exit the vault", "enabled": False, "completed": True, "failed": False, "or": False}]},
    ]
    locations = [{"Name": n, "type": t, "X": float(x), "Y": float(y), "Discovered": i < 18, "Visible": i < 24,
                  "ClearedStatus": i % 4 == 0, "LocationFormId": 70000 + i, "LocationMarkerFormId": 80000 + i}
                 for i, (n, t, x, y) in enumerate(LOCATIONS)]
    player_pos = {"X": -80000.0, "Y": 90000.0, "Rotation": 90.0}
    quest_marker = [{"Name": "Find Nick Valentine", "X": 2000.0, "Y": -8000.0, "Height": 0, "OnDoor": False,
                     "Shared": False, "QuestId": [9001]}]
    extents = {"NWX": -135168.0, "NWY": 102400.0, "NEX": 114688.0, "NEY": 102400.0,
               "SWX": -135168.0, "SWY": -147456.0}
    data = {
        "Inventory": inventory,
        "Log": [{"text": "$General", "statArray": [
            {"text": "Locations Discovered", "Value": 18, "showIfZero": True},
            {"text": "Days Passed", "Value": 6, "showIfZero": True},
            {"text": "Caps Found", "Value": 1240, "showIfZero": True},
            {"text": "Items Crafted", "Value": 0, "showIfZero": False}]},
                {"text": "$Combat", "statArray": [{"text": "People Killed", "Value": 31, "showIfZero": True},
                                                  {"text": "Creatures Killed", "Value": 55, "showIfZero": True}]}],
        "Map": {"CurrCell": "", "CurrWorldspace": "Commonwealth",
                "World": {"Extents": extents, "Player": dict(player_pos), "Locations": locations,
                          "Custom": {"X": 0.0, "Y": 0.0, "Height": 0, "Visible": False},
                          "PowerArmor": {"X": -76000.0, "Y": 84000.0, "Height": 0, "Visible": True},
                          "Quests": quest_marker},
                "Local": {"Extents": {"NWX": -86000.0, "NWY": 96000.0, "NEX": -74000.0, "NEY": 96000.0,
                                      "SWX": -86000.0, "SWY": 84000.0},
                          "Player": dict(player_pos), "Doors": [{"Name": "Root Cellar", "X": -79000.0, "Y": 91000.0, "Visible": True}],
                          "Custom": {"X": 0.0, "Y": 0.0, "Height": 0, "Visible": False},
                          "PowerArmor": {"X": -76000.0, "Y": 84000.0, "Height": 0, "Visible": False},
                          "Quests": []}},
        "Perks": perks,
        "PlayerInfo": {"PlayerName": "Sole Survivor", "XPLevel": 9, "XPProgressPct": 0.42, "PerkPoints": 1,
                       "CurrHP": 140.0, "MaxHP": 185.0, "CurrentHPGain": 0.0, "CurrAP": 70.0, "MaxAP": 90.0,
                       "CurrWeight": 112.5, "MaxWeight": 240.0, "Caps": 1240, "TimeHour": 13.5,
                       "DateDay": 29, "DateMonth": 9, "DateYear": 287,
                       "TotalDamages": [{"type": 1, "Value": 18.0}, {"type": 4, "Value": 0.0}],
                       "TotalResists": [{"type": 1, "Value": 17.0}, {"type": 4, "Value": 13.0}, {"type": 6, "Value": 10.0}],
                       "SlotResists": []},
        "Quests": quests,
        "Radio": [{"text": "Diamond City Radio", "frequency": 98.0, "active": True, "inRange": True},
                  {"text": "Classical Radio", "frequency": 91.0, "active": False, "inRange": True},
                  {"text": "Radio Freedom", "frequency": 87.5, "active": False, "inRange": True},
                  {"text": "Distress Signal", "frequency": 102.3, "active": False, "inRange": False}],
        "Special": [{"Name": n, "Value": v, "Modifier": 1 if n == "Agility" else 0, "Description": d}
                    for n, v, d in special],
        "Stats": {"HeadCondition": 100.0, "TorsoCondition": 85.0, "LArmCondition": 100.0, "RArmCondition": 40.0,
                  "LLegCondition": 0.0, "RLegCondition": 100.0, "HeadFlags": 0, "BodyFlags": 0,
                  "StimpakCount": 9, "RadawayCount": 3,
                  "ActiveEffects": [{"Source": "Psycho", "type": 54, "Effects": [
                      {"Name": "DMG", "Value": 25.0, "showAsPercent": True, "duration": 120.0, "IsActive": True}]},
                      {"Source": "Well Rested", "type": 54, "Effects": [
                          {"Name": "XP", "Value": 10.0, "showAsPercent": True, "duration": 0.0, "IsActive": True}]}]},
        "Status": {"EffectColor": [0.08, 1.0, 0.09], "IsDataUnavailable": False, "IsInAnimation": False,
                   "IsInAutoVanity": False, "IsInVats": False, "IsInVatsPlayback": False, "IsLoading": False,
                   "IsMenuOpen": False, "IsPipboyNotEquipped": False, "IsPlayerDead": False,
                   "IsPlayerInDialogue": False, "IsPlayerMovementLocked": False, "IsPlayerPipboyLocked": False,
                   "MinigameFormIds": []},
        "Workshop": [{"text": "Sanctuary", "owned": True, "rating": 0, "mapMarkerID": 80000, "workshopData": [
            {"text": "WorkshopRatingPopulation", "Value": 6, "rating": 0}, {"text": "Food", "Value": 8, "rating": 0},
            {"text": "Water", "Value": 10, "rating": 0}, {"text": "PowerGenerated", "Value": 4, "rating": 0},
            {"text": "Defense", "Value": 12, "rating": 0}, {"text": "Bed", "Value": 4, "rating": -1},
            {"text": "Happiness", "Value": 61, "rating": 0}]},
                     {"text": "Red Rocket Truck Stop", "owned": False, "rating": 0, "mapMarkerID": 80001,
                      "workshopData": []}],
    }
    return data


class Game:
    def __init__(self, capture=None):
        self.lock = threading.Lock()
        self.capture = capture
        self.tree = Tree()
        self.tree.add(make_data())
        self.clients = []
        # The inventory's list of item ids, and its Stimpak and RadAway.
        t = self.tree
        inv = t.get("Inventory")
        ids = [item for _, _, item in self.items()]
        t.nodes[inv][1]["sortedIDS"] = t.add(ids)
        for name, key in (("Stimpak", "stimpak"), ("RadAway", "radaway")):
            item = next(i for i in ids if t.value("text", node_id=i) == name)
            t.nodes[inv][1][f"{key}ObjectID"] = t.add(item)
            t.nodes[inv][1][f"{key}ObjectIDIsValid"] = t.add(True)

    def first_message(self):
        if self.capture:
            return self.capture
        with self.lock:
            return DataUpdateEncoder().encode(self.tree.records(0))

    def broadcast(self, records):
        if self.capture or not records:
            return
        payload = DataUpdateEncoder().encode(records)
        for c in list(self.clients):
            c.send(eMessageType.DATA_UPDATE, payload)

    def tick(self):
        """The game's clock runs, AP refills."""
        while True:
            time.sleep(1)
            if self.capture:
                continue
            with self.lock:
                t = self.tree
                hour = (t.value("PlayerInfo", "TimeHour") + 0.05) % 24
                recs = t.set("PlayerInfo", "TimeHour", value=hour)
                ap, max_ap = t.value("PlayerInfo", "CurrAP"), t.value("PlayerInfo", "MaxAP")
                if ap < max_ap:
                    recs += t.set("PlayerInfo", "CurrAP", value=min(max_ap, ap + 3.0))
            self.broadcast(recs)

    def items(self):
        t = self.tree
        inv = t.nodes[0][1]["Inventory"]
        for key, nid in t.nodes[inv][1].items():
            if key.isdigit():
                for item in t.nodes[nid][1]:
                    yield key, nid, item

    def find_item(self, handle):
        for key, arr, item in self.items():
            if self.tree.value("HandleID", node_id=item) == handle:
                return arr, item
        return None, None

    def command(self, req):
        """The answer to one of the app's commands, and records to send."""
        kind, args = req.get("type"), req.get("args", [])
        t = self.tree
        recs = []
        answer = {"id": req.get("id"), "allowed": True, "success": True}
        if self.capture:
            return answer, recs
        if kind == eRequestType.UseItem:
            arr, item = self.find_item(args[0])
            if item is not None:
                flags = t.value("filterFlag", node_id=item)
                name = t.value("text", node_id=item)
                if flags & 8:  # aid: one used up
                    count = t.value("count", node_id=item) - 1
                    hp, max_hp = t.value("PlayerInfo", "CurrHP"), t.value("PlayerInfo", "MaxHP")
                    if name == "Stimpak":
                        recs += t.set("PlayerInfo", "CurrHP", value=min(max_hp, hp + 40.0))
                        recs += t.set("Stats", "StimpakCount", value=max(0, count))
                        for limb in ("Head", "Torso", "LArm", "RArm", "LLeg", "RLeg"):
                            recs += t.set("Stats", f"{limb}Condition", value=100.0)
                    elif name == "RadAway":
                        recs += t.set("Stats", "RadawayCount", value=max(0, count))
                    else:
                        recs += t.set("PlayerInfo", "CurrHP", value=min(max_hp, hp + 10.0))
                    recs += self.set_count(arr, item, count)
                elif flags & (2 | 4):
                    state = t.value("equipState", node_id=item)
                    recs += t.set("equipState", node_id=item, value=0 if state else 1)
            recs += t.set("Inventory", "Version", value=t.value("Inventory", "Version") + 1)
        elif kind == eRequestType.DropItem:
            arr, item = self.find_item(args[0])
            if item is not None:
                recs += self.set_count(arr, item, t.value("count", node_id=item) - int(args[1]))
                recs += t.set("Inventory", "Version", value=t.value("Inventory", "Version") + 1)
        elif kind == eRequestType.ToggleRadioStation:
            for nid in t.value("Radio"):
                on = nid == args[0] and not t.value("active", node_id=nid)
                recs += t.set("active", node_id=nid, value=on)
        elif kind == eRequestType.ToggleQuestActive:
            for nid in t.value("Quests"):
                if t.value("formID", node_id=nid) == args[0]:
                    recs += t.set("active", node_id=nid, value=not t.value("active", node_id=nid))
        elif kind == eRequestType.SetCustomMapMarker:
            for where in ("World", "Local"):
                recs += t.set("Map", where, "Custom", "X", value=float(args[0]))
                recs += t.set("Map", where, "Custom", "Y", value=float(args[1]))
                recs += t.set("Map", where, "Custom", "Visible", value=True)
        elif kind == eRequestType.RemoveCustomMapMarker:
            for where in ("World", "Local"):
                recs += t.set("Map", where, "Custom", "Visible", value=False)
        elif kind == eRequestType.FastTravel:
            loc = args[0]
            if loc in t.nodes and t.value("Discovered", node_id=loc):
                x, y = t.value("X", node_id=loc), t.value("Y", node_id=loc)
                for where in ("World", "Local"):
                    recs += t.set("Map", where, "Player", "X", value=x)
                    recs += t.set("Map", where, "Player", "Y", value=y)
                recs += t.set("PlayerInfo", "TimeHour", value=(t.value("PlayerInfo", "TimeHour") + 2) % 24)
            else:
                answer["allowed"] = False
                answer["success"] = False
        return answer, recs

    def set_count(self, arr, item, count):
        t = self.tree
        if count > 0:
            return t.set("count", node_id=item, value=count)
        t.nodes[arr][1] = [i for i in t.nodes[arr][1] if i != item]
        sorted_ids = t.get("Inventory", "sortedIDS")
        t.nodes[sorted_ids][1] = [r for r in t.nodes[sorted_ids][1] if t.nodes[r][1] != item]
        return [(arr, eValueType.ARRAY, t.nodes[arr][1])] + t.records(sorted_ids)

    def local_map(self):
        """A made-up 512 x 512 local map around the player."""
        w = h = 512
        with self.lock:
            px = self.tree.value("Map", "World", "Player", "X")
            py = self.tree.value("Map", "World", "Player", "Y")
        pixels = bytearray(w * h)
        for y in range(h):
            for x in range(w):
                wx, wy = px + (x - w / 2) * 8, py - (y - h / 2) * 8
                v = 60 + 40 * math.sin(wx / 900) * math.cos(wy / 700) + 30 * math.sin((wx + wy) / 300)
                if int(wx / 2000) % 3 == 0 and abs(wy % 2000) < 120:
                    v = 200  # roads
                pixels[y * w + x] = max(0, min(255, int(v)))
        half = w / 2 * 8
        head = struct.pack("<II", w, h) + struct.pack("<6f", px - half, py + half, px + half, py + half,
                                                       px - half, py - half)
        return head + bytes(pixels)


class Client:
    def __init__(self, game, sock, addr):
        self.game = game
        self.sock = sock
        self.addr = addr
        self.send_lock = threading.Lock()

    def send(self, kind, payload=b""):
        try:
            with self.send_lock:
                self.sock.sendall(struct.pack("<IB", len(payload), kind) + payload)
        except OSError:
            pass

    def recv_exact(self, n):
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError("closed")
            data += chunk
        return data

    def run(self):
        print(f"app connected from {self.addr[0]}")
        self.send(eMessageType.CONNECTION_ACCEPTED, json.dumps({"lang": "en", "version": "1.10.163.0"}).encode())
        self.send(eMessageType.DATA_UPDATE, self.game.first_message())
        self.game.clients.append(self)
        threading.Thread(target=self.keep_alive, daemon=True).start()
        try:
            while True:
                size, kind = struct.unpack("<IB", self.recv_exact(5))
                payload = self.recv_exact(size) if size else b""
                if kind == eMessageType.COMMAND:
                    req = json.loads(payload)
                    print(f"command {req}")
                    if req.get("type") == eRequestType.RequestLocalMapSnapshot:
                        self.send(eMessageType.LOCAL_MAP_UPDATE, self.game.local_map())
                        continue
                    with self.game.lock:
                        answer, recs = self.game.command(req)
                    self.game.broadcast(recs)
                    self.send(eMessageType.COMMAND_RESULT, json.dumps(answer).encode())
        except (ConnectionError, OSError):
            pass
        finally:
            self.game.clients.remove(self)
            self.sock.close()
            print(f"app from {self.addr[0]} left")

    def keep_alive(self):
        while self in self.game.clients:
            self.send(eMessageType.KEEP_ALIVE)
            time.sleep(1)


def discovery(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", port))
    while True:
        data, addr = s.recvfrom(1024)
        try:
            if json.loads(data).get("cmd") == "autodiscover":
                s.sendto(json.dumps({"IsBusy": False, "MachineType": "PC"}).encode(), addr)
        except ValueError:
            pass


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--port", type=int, default=27000)
    p.add_argument("--discovery-port", type=int, default=28000)
    p.add_argument("--capture", help="a recorded DATA_UPDATE payload to send instead")
    a = p.parse_args()
    capture = open(a.capture, "rb").read() if a.capture else None
    game = Game(capture)
    threading.Thread(target=game.tick, daemon=True).start()
    try:
        threading.Thread(target=discovery, args=(a.discovery_port,), daemon=True).start()
    except OSError as err:
        print(f"no discovery: {err}")
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", a.port))
    srv.listen()
    print(f"fake Fallout 4 on port {a.port}")
    while True:
        sock, addr = srv.accept()
        threading.Thread(target=Client(game, sock, addr).run, daemon=True).start()


if __name__ == "__main__":
    main()
