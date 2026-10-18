"""A small Flash (SWF) reader for the game's Vault Boy clips: vector shapes
(DefineShape 1-4, solid fills and lines), sprites, and the display list of
each frame (PlaceObject2/3, RemoveObject2). Frames come out as SVG paths, in
pixels, with their colours kept as numbers so they can be tinted later.
Standard library only."""
import struct
import zlib

IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


class Bits:
    def __init__(self, data, pos=0):
        self.data, self.pos, self.bit = data, pos, 0

    def ub(self, n):
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.data[self.pos] >> (7 - self.bit)) & 1)
            self.bit += 1
            if self.bit == 8:
                self.bit, self.pos = 0, self.pos + 1
        return v

    def sb(self, n):
        v = self.ub(n)
        return v - (1 << n) if n and v & (1 << (n - 1)) else v

    def fb(self, n):
        return self.sb(n) / 65536.0

    def align(self):
        if self.bit:
            self.bit, self.pos = 0, self.pos + 1

    def u8(self):
        self.align()
        self.pos += 1
        return self.data[self.pos - 1]

    def u16(self):
        self.align()
        self.pos += 2
        return struct.unpack_from("<H", self.data, self.pos - 2)[0]

    def string(self):
        self.align()
        end = self.data.index(b"\0", self.pos)
        s, self.pos = self.data[self.pos:end].decode("utf-8", "replace"), end + 1
        return s

    def rgb(self, alpha):
        r, g, b = self.u8(), self.u8(), self.u8()
        return (r, g, b, self.u8() if alpha else 255)

    def rect(self):
        self.align()
        n = self.ub(5)
        r = [self.sb(n) for _ in range(4)]
        self.align()
        return r

    def matrix(self):
        self.align()
        a = d = 1.0
        b = c = 0.0
        if self.ub(1):
            n = self.ub(5)
            a, d = self.fb(n), self.fb(n)
        if self.ub(1):
            n = self.ub(5)
            b, c = self.fb(n), self.fb(n)
        n = self.ub(5)
        tx, ty = self.sb(n), self.sb(n)
        self.align()
        return (a, b, c, d, float(tx), float(ty))

    def alpha_of_cxform(self):
        """A CXFORMWITHALPHA, as the alpha it leaves (colour changes are not kept)."""
        self.align()
        add, mult = self.ub(1), self.ub(1)
        n = self.ub(4)
        m = [self.sb(n) / 256.0 for _ in range(4)] if mult else [1.0] * 4
        a = [self.sb(n) for _ in range(4)] if add else [0] * 4
        self.align()
        return max(0.0, min(1.0, m[3] + a[3] / 255.0))


def tags(data, pos, end):
    while pos < end:
        (h,) = struct.unpack_from("<H", data, pos)
        pos += 2
        code, ln = h >> 6, h & 63
        if ln == 63:
            (ln,) = struct.unpack_from("<I", data, pos)
            pos += 4
        yield code, data[pos:pos + ln]
        pos += ln
        if code == 0:
            return


def mul(m, n):
    """The matrix that applies n, then m."""
    a, b, c, d, tx, ty = m
    a2, b2, c2, d2, tx2, ty2 = n
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * tx2 + c * ty2 + tx, b * tx2 + d * ty2 + ty)


def read_styles(bits, version, fills):
    out = []
    count = bits.u8()
    if count == 0xFF and version >= 2:
        count = bits.u16()
    for _ in range(count):
        if fills:
            kind = bits.u8()
            if kind == 0x00:
                out.append(bits.rgb(version >= 3))
            elif kind in (0x10, 0x12, 0x13):  # a gradient: its first colour
                bits.matrix()
                n = bits.u8() & 15
                cols = []
                for _ in range(n):
                    bits.u8()
                    cols.append(bits.rgb(version >= 3))
                if kind == 0x13:
                    bits.u16()
                out.append(cols[0] if cols else (255, 255, 255, 255))
            elif kind in (0x40, 0x41, 0x42, 0x43):  # a bitmap: not drawn
                bits.u16()
                bits.matrix()
                out.append(None)
            else:
                raise ValueError("fill type %#x" % kind)
        else:
            width = bits.u16()
            if version == 4:
                bits.align()
                bits.ub(2)
                join = bits.ub(2)
                has_fill = bits.ub(1)
                bits.ub(3)
                bits.ub(8)
                if join == 2:
                    bits.u16()
                if has_fill:
                    if bits.u8() != 0:
                        raise ValueError("a line with a gradient or bitmap")
                col = bits.rgb(True)
            else:
                col = bits.rgb(version >= 3)
            out.append((width, col))
    return out


def reverse(s):
    return (s[2], s[3], s[0], s[1]) if len(s) == 4 else (s[4], s[5], s[2], s[3], s[0], s[1])


def chain(segs):
    """One fill's edges joined into loops."""
    by_start = {}
    for s in segs:
        by_start.setdefault((s[0], s[1]), []).append(s)
    loops, used = [], set()
    for s in segs:
        if id(s) in used:
            continue
        loop = [s]
        used.add(id(s))
        start, end = (s[0], s[1]), (s[-2], s[-1])
        while end != start:
            nxt = next((t for t in by_start.get(end, ()) if id(t) not in used), None)
            if nxt is None:
                break
            loop.append(nxt)
            used.add(id(nxt))
            end = (nxt[-2], nxt[-1])
        loops.append(loop)
    return loops


def define_shape(data, version):
    """[("fill", rgba, loops) or ("line", (width, rgba), loops)]; a loop is a
    list of segments (x0, y0, x1, y1) or (x0, y0, cx, cy, x1, y1) in twips."""
    bits = Bits(data, 2)
    bits.rect()
    if version == 4:
        bits.rect()
        bits.u8()
    groups = [(read_styles(bits, version, True), read_styles(bits, version, False), {}, {})]
    bits.align()
    nfb, nlb = bits.ub(4), bits.ub(4)
    x = y = 0
    f0 = f1 = ln = 0
    while True:
        if bits.ub(1):
            straight = bits.ub(1)
            n = bits.ub(4) + 2
            if straight:
                if bits.ub(1):
                    dx, dy = bits.sb(n), bits.sb(n)
                elif bits.ub(1):
                    dx, dy = 0, bits.sb(n)
                else:
                    dx, dy = bits.sb(n), 0
                seg = (x, y, x + dx, y + dy)
            else:
                cdx, cdy, adx, ady = bits.sb(n), bits.sb(n), bits.sb(n), bits.sb(n)
                seg = (x, y, x + cdx, y + cdy, x + cdx + adx, y + cdy + ady)
            x, y = seg[-2], seg[-1]
            fills, lines = groups[-1][2], groups[-1][3]
            if f1:
                fills.setdefault(f1, []).append(seg)
            if f0:
                fills.setdefault(f0, []).append(reverse(seg))
            if ln:
                lines.setdefault(ln, []).append(seg)
        else:
            flags = bits.ub(5)
            if flags == 0:
                break
            if flags & 1:
                n = bits.ub(5)
                x, y = bits.sb(n), bits.sb(n)
            if flags & 2:
                f0 = bits.ub(nfb)
            if flags & 4:
                f1 = bits.ub(nfb)
            if flags & 8:
                ln = bits.ub(nlb)
            if flags & 16:
                groups.append((read_styles(bits, version, True), read_styles(bits, version, False), {}, {}))
                bits.align()
                nfb, nlb = bits.ub(4), bits.ub(4)
    out = []
    for fill_styles, line_styles, fills, lines in groups:
        for idx, segs in fills.items():
            if fill_styles[idx - 1] is not None:
                out.append(("fill", fill_styles[idx - 1], chain(segs)))
        for idx, segs in lines.items():
            out.append(("line", line_styles[idx - 1], [[s] for s in segs]))
    return out


def path(loops, m):
    """SVG path data, in pixels."""
    a, b, c, d, tx, ty = m

    def pt(x, y):
        return "%.2f %.2f" % ((a * x + c * y + tx) / 20.0, (b * x + d * y + ty) / 20.0)
    parts = []
    for loop in loops:
        parts.append("M" + pt(loop[0][0], loop[0][1]))
        for s in loop:
            parts.append("L" + pt(s[2], s[3]) if len(s) == 4 else "Q" + pt(s[2], s[3]) + " " + pt(s[4], s[5]))
        if (loop[-1][-2], loop[-1][-1]) == (loop[0][0], loop[0][1]):
            parts.append("Z")
    return "".join(parts)


class Movie:
    """An SWF's shapes, sprites and main timeline."""

    def __init__(self, data):
        if data[:3] == b"CWS":
            body = zlib.decompress(data[8:])
        elif data[:3] == b"FWS":
            body = data[8:]
        else:
            raise ValueError("not an SWF")
        bits = Bits(body)
        bits.rect()
        self.fps = body[bits.pos + 1] + body[bits.pos] / 256.0
        self.shapes, self.sprites = {}, {}
        self.frames = self.timeline(body, bits.pos + 4, len(body), top=True)

    def timeline(self, data, pos, end, top=False):
        """The display list after each frame: [{depth: (id, matrix, alpha, first frame, name)}]."""
        frames, current = [], {}
        for code, t in tags(data, pos, end):
            if top and code in (2, 22, 32, 83):
                (cid,) = struct.unpack_from("<H", t)
                self.shapes[cid] = define_shape(t, {2: 1, 22: 2, 32: 3, 83: 4}[code])
            elif top and code == 39:
                (sid,) = struct.unpack_from("<H", t)
                self.sprites[sid] = self.timeline(t, 4, len(t))
            elif code in (26, 70):
                b = Bits(t)
                flags = b.u8()
                flags2 = b.u8() if code == 70 else 0
                depth = b.u16()
                if code == 70 and (flags2 & 8 or (flags2 & 16 and flags & 2)):
                    b.string()  # class name
                old = current.get(depth)
                cid = b.u16() if flags & 2 else (old[0] if old else None)
                m = b.matrix() if flags & 4 else (old[1] if old else IDENTITY)
                alpha = b.alpha_of_cxform() if flags & 8 else (old[2] if old else 1.0)
                if flags & 16:
                    b.u16()  # ratio
                name = b.string() if flags & 32 else (old[4] if old else None)
                first = len(frames) if (flags & 2 or not old) else old[3]
                current[depth] = (cid, m, alpha, first, name)
            elif code == 28:
                current.pop(struct.unpack_from("<H", t)[0], None)
            elif code == 1:
                frames.append(dict(current))
        return frames

    def draw(self, frames, index, m=IDENTITY, alpha=1.0, out=None, attach=None):
        """The elements of a frame: ("fill", path, rgb, opacity) and
        ("line", path, rgb, opacity, width). attach(name, matrix, alpha, out)
        is called after each named sprite, to put more into it."""
        out = [] if out is None else out
        for depth in sorted(frames[index] if frames else ()):
            cid, cm, ca, first, name = frames[index][depth]
            mm, aa = mul(m, cm), alpha * ca
            if cid in self.shapes:
                for kind, style, loops in self.shapes[cid]:
                    if kind == "fill":
                        out.append(("fill", path(loops, mm), style[:3], round(aa * style[3] / 255.0, 3)))
                    else:
                        width, col = style
                        scale = abs(mm[0] * mm[3] - mm[1] * mm[2]) ** 0.5
                        out.append(("line", path(loops, mm), col[:3], round(aa * col[3] / 255.0, 3),
                                    round(max(width, 20) * scale / 20.0, 2)))
            elif cid in self.sprites:
                sub = self.sprites[cid]
                if sub:
                    self.draw(sub, (index - first) % len(sub), mm, aa, out, attach)
                if name and attach:
                    attach(name, mm, aa, out)
        return out
