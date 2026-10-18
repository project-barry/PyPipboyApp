"""The game's own walking Vault Boy (STAT > STATUS), read from the Fallout 4
on this device.

The Pip-Boy draws him from Flash clips in "Fallout4 - Interface.ba2":
Interface\\Components\\ConditionClips\\Condition_Body_<BodyFlags>.swf (the walk,
with slings, crutches and bandages for crippled limbs) and Condition_Head.swf
(one frame per HeadFlags), the head put inside the body's Head_mc sprite
(Shared.AS3.ConditionBoy). The clips are Bethesda's, so the app doesn't carry
them: the first time they are wanted, this reads them from the game, turns
each pose into SVG paths (swf.py) and keeps them in the app's data folder.
Without the game here, there is no walk and STATUS shows the still picture.
"""
import json
import logging
import os
import struct
import threading
import zlib

import swf
from worldmap import game_data_dirs

log = logging.getLogger("pipboy.vaultboy")

ARCHIVE = "Fallout4 - Interface.ba2"
CLIPS = "interface\\components\\conditionclips\\"
BODIES = 17
CACHE_VERSION = 1


def read_general(path, names):
    """{name: bytes} of these (lower-case) names out of a general BA2 archive."""
    out = {}
    with open(path, "rb") as fh:
        magic, _version, kind, count, names_at = struct.unpack("<4sI4sIQ", fh.read(24))
        if magic != b"BTDX" or kind != b"GNRL":
            raise ValueError("not a general BA2 archive")
        records = [struct.unpack("<I4sIIQIII", fh.read(36)) for _ in range(count)]
        fh.seek(names_at)
        table = fh.read()
        at = 0
        for i in range(count):
            (n,) = struct.unpack_from("<H", table, at)
            name = table[at + 2:at + 2 + n].decode("latin-1").lower()
            at += 2 + n
            if name in names:
                offset, packed, full = records[i][4], records[i][5], records[i][6]
                fh.seek(offset)
                raw = fh.read(packed or full)
                out[name] = zlib.decompress(raw) if packed else raw
    return out


def bounds(elements, box):
    for el in elements:
        nums = [float(v) for v in el[1].replace("M", " ").replace("L", " ").replace("Q", " ").replace("Z", " ").split()]
        pad = el[4] / 2 if el[0] == "line" else 0
        for x, y in zip(nums[0::2], nums[1::2]):
            box[0], box[1] = min(box[0], x - pad), min(box[1], y - pad)
            box[2], box[3] = max(box[2], x + pad), max(box[3], y + pad)


def build(data):
    """The poses of every body (with where the head goes) and every head, from the game's clips."""
    wanted = {CLIPS + "condition_head.swf"} | {CLIPS + "condition_body_%d.swf" % n for n in range(BODIES)}
    files = read_general(os.path.join(data, ARCHIVE), wanted)
    missing = wanted - set(files)
    if missing:
        raise ValueError("missing %s" % ", ".join(sorted(missing)))
    head = swf.Movie(files[CLIPS + "condition_head.swf"])
    heads = [head.draw(head.frames, i) for i in range(len(head.frames))]
    box = [1e9, 1e9, -1e9, -1e9]
    bodies = []
    for n in range(BODIES):
        movie = swf.Movie(files[CLIPS + "condition_body_%d.swf" % n])
        poses = []
        for i in range(len(movie.frames)):
            place = []
            els = movie.draw(movie.frames, i, attach=lambda name, m, a, out: place.append(m) if name == "Head_mc" else None)
            where = [round(v, 4) for v in place[0]] if place else None
            if poses and poses[-1]["els"] == els and poses[-1]["head"] == where:
                poses[-1]["frames"] += 1
                continue
            poses.append({"els": els, "head": where, "frames": 1})
            bounds(els, box)
            if where:
                for h in heads:
                    for el in h:
                        bounds([(el[0], transformed(el[1], where)) + tuple(el[2:])], box)
        bodies.append({"poses": poses, "fps": movie.fps})
    return {"version": CACHE_VERSION, "box": box, "heads": heads, "bodies": bodies}


def transformed(d, m):
    """Path data moved by a Flash matrix (its translation in twips)."""
    a, b, c, dd, tx, ty = m
    out, nums, op = [], [], ""

    def flush():
        for x, y in zip(nums[0::2], nums[1::2]):
            out.append("%.2f %.2f" % (a * x + c * y + tx / 20.0, b * x + dd * y + ty / 20.0))
    for tok in d.replace("M", " M ").replace("L", " L ").replace("Q", " Q ").replace("Z", " Z ").split():
        if tok in ("M", "L", "Q", "Z"):
            flush()
            nums = []
            out.append(tok)
        else:
            nums.append(float(tok))
    flush()
    return " ".join(out)


class VaultBoy:
    """The walk, made once from the game (then kept in the data folder), as SVG in the Pip-Boy colour."""

    def __init__(self, data_dir):
        self.cache = os.path.join(data_dir, "vaultboy-v%d.json" % CACHE_VERSION)
        self.walk = None
        self.tried = False
        self.lock = threading.Lock()
        self.svgs = {}

    @property
    def ready(self):
        return self.walk is not None

    def load(self):
        with self.lock:
            if self.walk is not None or self.tried:
                return self.walk
            self.tried = True
            try:
                with open(self.cache, encoding="utf-8") as fh:
                    self.walk = json.load(fh)
                    return self.walk
            except (OSError, ValueError):
                pass
            for data in game_data_dirs():
                if not os.path.exists(os.path.join(data, ARCHIVE)):
                    continue
                try:
                    walk = build(data)
                except (OSError, ValueError, IndexError, KeyError, struct.error, zlib.error) as err:
                    log.warning("cannot read the Vault Boy from %s: %s", data, err)
                    continue
                try:
                    os.makedirs(os.path.dirname(self.cache), exist_ok=True)
                    with open(self.cache + ".tmp", "w", encoding="utf-8") as fh:
                        json.dump(walk, fh, separators=(",", ":"))
                    os.replace(self.cache + ".tmp", self.cache)
                except OSError as err:
                    log.warning("cannot keep the Vault Boy: %s", err)
                self.walk = walk
                log.info("Vault Boy read from %s", data)
                return walk
            log.info("no Fallout 4 here: STATUS shows the still Vault Boy")
            return None

    def info(self, body, head):
        """{"body", "head", "ms": [each pose's time]} for these flags, or None."""
        if self.walk is None:
            return None
        body = body if 0 <= body < len(self.walk["bodies"]) else 0
        head = head if 0 <= head < len(self.walk["heads"]) else 0
        b = self.walk["bodies"][body]
        return {"body": body, "head": head,
                "ms": [round(p["frames"] * 1000 / (b["fps"] or 30)) for p in b["poses"]]}

    def svg(self, body, head, pose, color):
        """One pose as SVG, light parts in the colour and dark ones dark; b"" if there is none."""
        if self.load() is None:
            return b""
        key = (body, head, pose, tuple(color))
        with self.lock:
            if key in self.svgs:
                return self.svgs[key]
        try:
            p = self.walk["bodies"][body]["poses"][pose]
            head_els = self.walk["heads"][head]
        except (IndexError, TypeError):
            return b""
        r, g, b = (max(0.0, min(1.0, c)) for c in color)

        def ink(rgb):
            k = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255.0
            return "#%02x%02x%02x" % (int(r * k * 255), int(g * k * 255), int(b * k * 255))

        def element(el, d=None):
            d = d or el[1]
            if el[0] == "fill":
                return '<path d="%s" fill="%s" fill-opacity="%s"/>' % (d, ink(el[2]), el[3])
            return ('<path d="%s" fill="none" stroke="%s" stroke-opacity="%s" stroke-width="%s" '
                    'stroke-linecap="round" stroke-linejoin="round"/>' % (d, ink(el[2]), el[3], el[4]))
        parts = [element(el) for el in p["els"]]
        if p["head"]:
            parts += [element(el, transformed(el[1], p["head"])) for el in head_els]
        x0, y0, x1, y1 = self.walk["box"]
        data = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="%.1f %.1f %.1f %.1f" width="%d" height="%d">%s</svg>'
                % (x0, y0, x1 - x0, y1 - y0, round(x1 - x0), round(y1 - y0), "".join(parts))).encode()
        with self.lock:
            if len(self.svgs) > 64:
                self.svgs.clear()
            self.svgs[key] = data
        return data
