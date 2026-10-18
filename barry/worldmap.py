"""The game's own world map picture, read from the Fallout 4 on this device.

The picture is Bethesda's, so the app doesn't carry it: the first time it is
wanted, this finds Fallout 4 in the Steam libraries here, takes the Pip-Boy's
world map texture (Textures\\Interface\\Pip-Boy\\WorldMap_d.DDS) out of the
game's archives, and keeps it as a grey picture in the app's data folder.
Without the game here (a game on another computer), there is no picture and
the map stays a grid.

The texture is 2048 x 2048 and the world's extents (Map.World.Extents) sit at
texels (69, 69), (1979, 69) and (69, 1979) of it: the corners PyPipboyApp
uses for its map pictures, and where Sanctuary, Red Rocket and the game's own
local map pictures land on it.
"""
import glob
import logging
import os
import re
import struct
import threading
import zlib

log = logging.getLogger("pipboy.worldmap")

TEXTURE = "textures\\interface\\pip-boy\\worldmap_d.dds"
SIZE = 2048
CORNER = 69                       # the extents' NW corner, in texels
SPAN = 1979 - 69                  # the extents' width and height, in texels
# The Commonwealth's extents; other worlds (Far Harbor, Nuka-World) have
# their own textures, which aren't placed yet.
COMMONWEALTH = {"nw": [-135168.0, 102400.0], "ne": [114688.0, 102400.0], "sw": [-135168.0, -147456.0]}
CACHE_VERSION = 2


def steam_roots():
    home = os.path.expanduser("~")
    for root in (os.path.join(home, ".local", "share", "Steam"), os.path.join(home, ".steam", "steam")):
        if os.path.isdir(os.path.join(root, "steamapps")):
            yield root


def game_data_dirs():
    """Fallout 4's Data folders in this device's Steam libraries."""
    if os.environ.get("PIPBOY_FALLOUT4_DATA"):
        yield os.environ["PIPBOY_FALLOUT4_DATA"]
    seen = set()
    for root in steam_roots():
        libraries = [root]
        try:
            with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8",
                      errors="replace") as fh:
                libraries += re.findall(r'"path"\s+"([^"]+)"', fh.read())
        except OSError:
            pass
        for lib in libraries:
            data = os.path.realpath(os.path.join(lib.replace("\\\\", "\\"), "steamapps", "common",
                                                 "Fallout 4", "Data"))
            if data not in seen and os.path.isdir(data):
                seen.add(data)
                yield data


def find_texture(data):
    """(archive, record) of the world map texture in a Data folder, or None."""
    for path in sorted(glob.glob(os.path.join(data, "Fallout4 - Textures*.ba2"))):
        try:
            with open(path, "rb") as fh:
                magic, _version, kind, count, names_at = struct.unpack("<4sI4sIQ", fh.read(24))
                if magic != b"BTDX" or kind != b"DX10":
                    continue
                fh.seek(names_at)
                names = fh.read()
            at = 0
            for index in range(count):
                (n,) = struct.unpack_from("<H", names, at)
                if names[at + 2:at + 2 + n].decode("latin-1").lower() == TEXTURE:
                    return path, index
                at += 2 + n
        except (OSError, struct.error) as err:
            log.warning("cannot read %s: %s", path, err)
    return None


def read_texture(path, index):
    """(width, height, DXGI format, top mip level's bytes) of a DX10 archive record."""
    with open(path, "rb") as fh:
        fh.seek(24)
        for i in range(index + 1):
            head = struct.unpack("<IIIBBHHHBBBB", fh.read(24))
            chunks = [struct.unpack("<QIIHHI", fh.read(24)) for _ in range(head[4])]
        height, width, fmt = head[6], head[7], head[9]
        offset, packed, full, first_mip, _last_mip, _ = chunks[0]
        if first_mip != 0:
            raise ValueError("no top mip level")
        fh.seek(offset)
        raw = fh.read(packed or full)
    return width, height, fmt, zlib.decompress(raw) if packed else raw


def bc1_grey(width, height, data):
    """The grey levels of a BC1 (DXT1) picture, one byte a pixel."""
    out = bytearray(width * height)
    blocks_x = width // 4
    lum = [0] * 4
    for b in range(blocks_x * (height // 4)):
        c0, c1, bits = struct.unpack_from("<HHI", data, b * 8)
        l0 = (((c0 >> 11) & 31) * 527 * 77 + ((c0 >> 5) & 63) * 259 * 150 + (c0 & 31) * 527 * 29) >> 14
        l1 = (((c1 >> 11) & 31) * 527 * 77 + ((c1 >> 5) & 63) * 259 * 150 + (c1 & 31) * 527 * 29) >> 14
        lum[0], lum[1] = l0, l1
        if c0 > c1:
            lum[2], lum[3] = (2 * l0 + l1) // 3, (l0 + 2 * l1) // 3
        else:
            lum[2], lum[3] = (l0 + l1) // 2, 0
        x0, y0 = (b % blocks_x) * 4, (b // blocks_x) * 4
        for row in range(4):
            at = (y0 + row) * width + x0
            out[at] = lum[bits & 3]
            out[at + 1] = lum[(bits >> 2) & 3]
            out[at + 2] = lum[(bits >> 4) & 3]
            out[at + 3] = lum[(bits >> 6) & 3]
            bits >>= 8
    return out


def stretch(grey, top=150):
    """Levels spread over 0-top (the texture is dark grey): bright enough to
    read, dim enough for the markers in the full colour to stand out."""
    counts = [0] * 256
    for v in grey:
        counts[v] += 1
    total, low, high, seen = len(grey), 0, 255, 0
    for v in range(256):
        seen += counts[v]
        if seen > total * 0.01:
            low = v
            break
    seen = 0
    for v in range(255, -1, -1):
        seen += counts[v]
        if seen > total * 0.002:
            high = v
            break
    scale = top / max(1, high - low)
    table = bytes(max(0, min(top, int((v - low) * scale))) for v in range(256))
    return grey.translate(table)


class WorldMap:
    """The grey picture (made once, then kept in the data folder) and its
    PNG in the Pip-Boy colour."""

    def __init__(self, data_dir):
        self.cache = os.path.join(data_dir, "worldmap-v%d.idat" % CACHE_VERSION)
        self.idat = None    # zlib-compressed PNG rows, made once
        self.tried = False
        self.png = b""
        self.color = None
        self.lock = threading.Lock()

    @property
    def ready(self):
        return self.idat is not None

    def load(self):
        """The compressed rows, from the data folder or made from the game; None without the game."""
        with self.lock:
            return self._load()

    def _load(self):
        if self.idat is not None or self.tried:
            return self.idat
        self.tried = True
        try:
            with open(self.cache, "rb") as fh:
                self.idat = fh.read()
                return self.idat
        except OSError:
            pass
        for data in game_data_dirs():
            found = find_texture(data)
            if not found:
                continue
            try:
                width, height, fmt, top = read_texture(*found)
                if (width, height) != (SIZE, SIZE) or fmt not in (70, 71, 72):  # BC1
                    log.warning("world map texture is %dx%d format %d, not used", width, height, fmt)
                    return None
                grey = stretch(bc1_grey(width, height, top))
            except (OSError, ValueError, struct.error, zlib.error) as err:
                log.warning("cannot read the world map from %s: %s", found[0], err)
                continue
            rows = b"".join(b"\x00" + bytes(grey[y * SIZE:(y + 1) * SIZE]) for y in range(SIZE))
            self.idat = zlib.compress(rows, 6)
            try:
                os.makedirs(os.path.dirname(self.cache), exist_ok=True)
                with open(self.cache + ".tmp", "wb") as fh:
                    fh.write(self.idat)
                os.replace(self.cache + ".tmp", self.cache)
            except OSError as err:
                log.warning("cannot keep the world map: %s", err)
            log.info("world map read from %s", found[0])
            return self.idat
        log.info("no Fallout 4 here: the world map stays a grid")
        return None

    def picture(self, color):
        """The PNG in this colour (black to colour), or b"" without the game."""
        if self.load() is None:
            return b""
        with self.lock:
            return self._picture(color)

    def _picture(self, color):
        if color != self.color:
            r, g, b = (max(0.0, min(1.0, c)) for c in color)
            palette = bytes(int(c * i) for i in range(256) for c in (r, g, b))

            def chunk(kind, data):
                return (struct.pack(">I", len(data)) + kind + data
                        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
            self.png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 3, 0, 0, 0))
                        + chunk(b"PLTE", palette) + chunk(b"IDAT", self.idat) + chunk(b"IEND", b""))
            self.color = color
        return self.png


def placement(extents):
    """Where the picture goes, in the map's 0-1 units (the extents' NW corner
    is 0, 0 and SE is 1, 1), for these world extents; None if it isn't the
    Commonwealth's."""
    if extents != COMMONWEALTH:
        return None
    return {"u0": -CORNER / SPAN, "v0": -CORNER / SPAN, "size": SIZE / SPAN}
