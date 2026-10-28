"""Grid maze router for the LD405 board (used by gen_pcb.py --route).

GND and +5V live on the inner planes (In1 = GND, In2 = +5V): every SMD pad on
those nets gets a short fan-out track and a via.  All other nets are routed on
F.Cu and B.Cu by an A* search (router_core.c) on a 0.1 mm grid.

Obstacles are the real pad / track / via shapes inflated by the clearance plus
half the default track width, rasterised by cell centre, so a centre line that
only visits free cells is clearance-clean.  Wider tracks and vias use the
distance-to-obstacle map with one cell of extra margin.  Power nets taper:
each cell takes the widest width that fits there, so the track necks down only
where it has to (at fine-pitch pads).

Connections grow Prim-style from a root pad: the nearest unconnected island
joins the routed tree.  A connection that cannot be made rips up the nets
whose tracks are in its way; those nets are routed again afterwards.
"""
import ctypes, math, os, subprocess
import numpy as np
from scipy import ndimage
from matplotlib.path import Path
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))


def MM(v):
    return pcbnew.FromMM(float(v))


G = 0.1             # grid pitch (mm)
CLR = 0.2           # copper clearance
MARGIN = 0.03       # rasterisation margin
W_SIG = 0.25        # default track width
HW0 = W_SIG / 2
INFL = CLR + HW0 + MARGIN
VIA_D, VIA_DRILL = 0.6, 0.3
EDGE_CLR = 0.3
HOLE_CLR = 0.25
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
PLANES = {"GND": pcbnew.In1_Cu, "+5V": pcbnew.In2_Cu}

# net -> (track width, pads joined at full width ("REF.PAD"), width for the rest)
POWER = {
    "VIN_RAW": (1.5, None, 1.5),
    "VIN_F": (1.5, None, 1.5),
    "VIN": (1.5, ["Q1.2", "D2.1", "C1.1", "C2.1", "C3.1", "C4.1", "C5.1", "R40.1"], 0.4),
    "SRC_K": (1.5, ["R40.2", "R41.1"], W_SIG),
    "SRC_D": (1.5, None, 1.5),
    "LD_OUT": (1.5, ["Q2.2", "D7.1", "D6.1", "K1.3", "K1.6", "Q10.3", "J5.8"], 0.5),
    "RLY_N": (0.4, None, 0.4),
    "CB_G": (0.3, None, 0.3),
}
ROOT = {"VIN": "Q1.2", "LD_OUT": "Q2.2", "SRC_K": "R40.2"}
TAPER = (1.5, 1.0, 0.8, 0.6, 0.4, 0.3, W_SIG)
# Kelvin taps of the sense resistor: (net, start pad, end point inside the R40 pad)
PREROUTES = [("VIN", "NT1.1", (219.75, 174.75)), ("SRC_K", "NT2.1", (213.25, 174.75))]
NO_TARGET = {"NT1.1", "NT2.1"}     # never join other copper to the Kelvin taps
# routed first, in this order: the high-current path, then the analogue loop
ORDER_FIRST = ("VIN_RAW", "VIN_F", "VIN", "SRC_K", "SRC_D", "LD_OUT", "GATE", "EA_N", "EA_OUT",
               "REF_N", "VIN_SNS", "SRC_SNS", "LS_S", "LS_G", "LS_GO", "VSP")

COST_VIA = 25.0        # cells (2.5 mm of track)
COST_VIA_POWER = 400.0
T45, T90 = 0.4, 2.5
NEAR_COST = 0.6        # per cell next to another net's copper
RIP_COST = 20.0        # per cell through another net's track when ripping up
MAX_RIPS = 4           # times a net may be ripped up


def _lib():
    src = os.path.join(HERE, "router_core.c")
    so = os.path.join(HERE, "__pycache__", "router_core.so")
    if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
        os.makedirs(os.path.dirname(so), exist_ok=True)
        subprocess.run(["gcc", "-O2", "-shared", "-fPIC", "-o", so, src], check=True)
    lib = ctypes.CDLL(so)
    u8 = np.ctypeslib.ndpointer(np.uint8, flags="C_CONTIGUOUS")
    f32 = np.ctypeslib.ndpointer(np.float32, flags="C_CONTIGUOUS")
    i32 = np.ctypeslib.ndpointer(np.int32, flags="C_CONTIGUOUS")
    lib.astar.argtypes = [ctypes.c_int, ctypes.c_int, u8, u8, f32, u8, i32, ctypes.c_int,
                          ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float,
                          i32, ctypes.c_int, ctypes.c_long]
    lib.astar.restype = ctypes.c_int
    return lib


def clearance_map(base):
    """Distance (mm) from each free cell centre to the nearest blocked cell
    centre, per layer.  Cells outside the window count as blocked."""
    out = np.empty(base.shape, np.float32)
    for li in range(base.shape[0]):
        padded = np.pad(base[li], 1, constant_values=False)
        out[li] = ndimage.distance_transform_edt(padded)[1:-1, 1:-1] * G
    return out


def fits(dist, width):
    """Cells where a track (or via) of this width keeps its clearance."""
    if width <= W_SIG + 1e-9:
        return dist > 0
    return dist > (width / 2 - HW0) + G


def sps_outlines(sps):
    out = []
    for k in range(sps.OutlineCount()):
        ol = sps.Outline(k)
        n = ol.PointCount()
        out.append(np.array([[ol.CPoint(i).x, ol.CPoint(i).y] for i in range(n)], float) / 1e6)
    return out


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return np.hypot(px - ax, py - ay)
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(pts):
    """Drop interior points that lie on a straight line."""
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        ax, ay = out[-1]; bx, by = pts[k]; cx, cy = pts[k + 1]
        cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        dot = (bx - ax) * (cx - bx) + (by - ay) * (cy - by)
        if abs(cross) < 1e-9 and dot >= 0:
            continue
        out.append(pts[k])
    out.append(pts[-1])
    return out


class PadInfo:
    def __init__(self, key, net, netname, pad, x, y, tht, cells, layers):
        self.key, self.net, self.netname, self.pad = key, net, netname, pad
        self.x, self.y, self.tht, self.cells, self.layers = x, y, tht, cells, layers
        self.cellset = set(cells)
        self.via_keepout = []


class Item:
    """A track (polyline on one layer) or via, kept for rasterisation / rip-up."""
    def __init__(self, net, kind, layer, pts, width, fixed=False, conn=None):
        self.net, self.kind, self.layer = net, kind, layer
        self.pts = simplify(pts) if kind == "track" else pts
        self.width, self.fixed, self.conn = width, fixed, conn
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        r = width / 2 + INFL
        self.bbox = (min(xs) - r, min(ys) - r, max(xs) + r, max(ys) + r)


class Router:
    def __init__(self, board, x0, y0, x1, y1, corner_r=2.0, zones=()):
        self.board = board
        self.bx = (x0, y0, x1, y1, corner_r)
        self.x0, self.y0 = x0, y0
        self.W = int(round((x1 - x0) / G)) + 1
        self.H = int(round((y1 - y0) / G)) + 1
        self.static = np.full((2, self.H, self.W), -1, np.int32)
        self.dynfix = np.full((2, self.H, self.W), -1, np.int32)   # fixed items
        self.dyn = np.full((2, self.H, self.W), -1, np.int32)      # routed items
        self.zones = zones
        self.items = []
        self.lib = _lib()
        self.pads = {}           # key -> PadInfo
        self.net_pads = {}       # netcode -> [PadInfo]
        self.netnames = {}
        self.parent = {}         # union-find over pad keys / connection ids
        self.unions = []         # every union made, so the forest can be rebuilt
        self.failed = []
        self.log = []
        self.junctions = set()   # (net, layer, x, y): T-junctions to keep as vertices
        self.rips = {}
        self.nconn = 0
        self.protected = set()

    # ------------------------------------------------------------ grid helpers
    def ij(self, x, y):
        return int(round((x - self.x0) / G)), int(round((y - self.y0) / G))

    def xy(self, i, j):
        return self.x0 + i * G, self.y0 + j * G

    def win_of_bbox(self, xa, ya, xb, yb, clip=None):
        i0 = max(0, int(math.floor((xa - self.x0) / G)))
        j0 = max(0, int(math.floor((ya - self.y0) / G)))
        i1 = min(self.W, int(math.ceil((xb - self.x0) / G)) + 1)
        j1 = min(self.H, int(math.ceil((yb - self.y0) / G)) + 1)
        if clip:
            j0, j1 = max(j0, clip[0]), min(j1, clip[1])
            i0, i1 = max(i0, clip[2]), min(i1, clip[3])
        return j0, j1, i0, i1

    def grid(self, win):
        j0, j1, i0, i1 = win
        return np.meshgrid(self.x0 + np.arange(i0, i1) * G, self.y0 + np.arange(j0, j1) * G)

    @staticmethod
    def mark(owner, li, win, mask, net):
        j0, j1, i0, i1 = win
        sub = owner[li, j0:j1, i0:i1]
        cur = sub[mask]
        sub[mask] = np.where((cur == -1) | (cur == net), net, -2)

    def raster_polys(self, polys, clip=None, grow=0.0):
        """Cells inside the polygons, or within `grow` mm of them."""
        allp = np.vstack(polys)
        win = self.win_of_bbox(allp[:, 0].min() - grow, allp[:, 1].min() - grow,
                               allp[:, 0].max() + grow, allp[:, 1].max() + grow, clip)
        j0, j1, i0, i1 = win
        if j1 <= j0 or i1 <= i0:
            return win, None
        X, Y = self.grid(win)
        pts = np.column_stack([X.ravel(), Y.ravel()])
        m = np.zeros(len(pts), bool)
        for p in polys:
            m |= Path(p).contains_points(pts)
        m = m.reshape(j1 - j0, i1 - i0)
        if grow > 0:
            for p in polys:
                q = np.vstack([p, p[:1]])
                for (ax, ay), (bx, by) in zip(q[:-1], q[1:]):
                    m |= seg_dist(X, Y, ax, ay, bx, by) < grow
        return win, m

    def raster_item(self, it, clip=None):
        owner = self.dynfix if it.fixed else self.dyn
        if it.kind == "via":
            x, y = it.pts[0]
            r = VIA_D / 2 + INFL
            win = self.win_of_bbox(x - r, y - r, x + r, y + r, clip)
            if win[1] <= win[0] or win[3] <= win[2]:
                return
            X, Y = self.grid(win)
            m = np.hypot(X - x, Y - y) < r
            for li in (0, 1):
                self.mark(owner, li, win, m, it.net)
            return
        r = it.width / 2 + INFL
        for (ax, ay), (bx, by) in zip(it.pts[:-1], it.pts[1:]):
            win = self.win_of_bbox(min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r, clip)
            if win[1] <= win[0] or win[3] <= win[2]:
                continue
            X, Y = self.grid(win)
            m = seg_dist(X, Y, ax, ay, bx, by) < r
            self.mark(owner, it.layer, win, m, it.net)

    def add_item(self, it):
        self.items.append(it)
        self.raster_item(it)

    def remove_items(self, dead):
        ids = set(id(d) for d in dead)
        self.items = [it for it in self.items if id(it) not in ids]
        for it in dead:
            xa, ya, xb, yb = it.bbox
            win = self.win_of_bbox(xa, ya, xb, yb)
            j0, j1, i0, i1 = win
            self.dyn[:, j0:j1, i0:i1] = -1
            for o in self.items:
                if o.fixed:
                    continue
                oa = o.bbox
                if oa[0] <= xb and oa[2] >= xa and oa[1] <= yb and oa[3] >= ya:
                    self.raster_item(o, clip=win)

    # ------------------------------------------------------------ union-find
    def find(self, a):
        while self.parent.setdefault(a, a) != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a, b, log=True):
        if log:
            self.unions.append((a, b))
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def rebuild_forest(self):
        self.parent = {}
        for a, b in self.unions:
            self.union(a, b, log=False)

    # ------------------------------------------------------------ obstacles
    def build_static(self):
        x0, y0, x1, y1, cr = self.bx
        e = EDGE_CLR + HW0 + MARGIN
        X, Y = self.grid((0, self.H, 0, self.W))
        bad = (X < x0 + e) | (X > x1 - e) | (Y < y0 + e) | (Y > y1 - e)
        for cx, cy in ((x0 + cr, y0 + cr), (x1 - cr, y0 + cr), (x0 + cr, y1 - cr), (x1 - cr, y1 - cr)):
            inc = ((X - cx) * np.sign(cx - (x0 + x1) / 2) > 0) & ((Y - cy) * np.sign(cy - (y0 + y1) / 2) > 0)
            bad |= inc & (np.hypot(X - cx, Y - cy) > cr - e)
        self.static[:, bad] = -2

        self.holes = []
        for fp in self.board.GetFootprints():
            for p in fp.Pads():
                if p.HasHole():
                    d = p.GetDrillSize()
                    pos = p.GetPosition()
                    self.holes.append((pos.x / 1e6, pos.y / 1e6, max(d.x, d.y) / 2e6))
        for fp in self.board.GetFootprints():
            ref = fp.GetReference()
            tie_net = None
            if fp.GetNetTiePadGroups():
                for p in fp.Pads():
                    if p.GetNumber() == "2":
                        tie_net = p.GetNetCode()
            for gi in fp.GraphicalItems():
                for li, layer in enumerate(LAYERS):
                    if gi.GetLayer() != layer:
                        continue
                    ps = pcbnew.SHAPE_POLY_SET()
                    gi.TransformShapeToPolygon(ps, layer, MM(INFL), MM(0.005), pcbnew.ERROR_OUTSIDE)
                    win, m = self.raster_polys(sps_outlines(ps))
                    if m is not None:
                        # a net tie's bridge belongs to its sense-side pad
                        self.mark(self.static, li, win, m, tie_net if tie_net else -2)
            for p in fp.Pads():
                pos = p.GetPosition()
                px, py = pos.x / 1e6, pos.y / 1e6
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                    d = p.GetDrillSize()
                    r = max(d.x, d.y) / 2e6 + HOLE_CLR + HW0 + MARGIN
                    win = self.win_of_bbox(px - r, py - r, px + r, py + r)
                    Xs, Ys = self.grid(win)
                    m = np.hypot(Xs - px, Ys - py) < r
                    for li in (0, 1):
                        self.mark(self.static, li, win, m, -2)
                    continue
                key = f"{ref}.{p.GetNumber()}"
                k2 = 1
                while key in self.pads:
                    k2 += 1
                    key = f"{ref}.{p.GetNumber()}#{k2}"
                net = p.GetNetCode()
                owner = net if net > 0 else -2
                cells, layers = [], []
                for li, layer in enumerate(LAYERS):
                    if not p.IsOnLayer(layer):
                        continue
                    layers.append(li)
                    ps = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps, layer, MM(INFL), MM(0.005), pcbnew.ERROR_OUTSIDE)
                    win, m = self.raster_polys(sps_outlines(ps))
                    self.mark(self.static, li, win, m, owner)
                    ps0 = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps0, layer, MM(-0.02), MM(0.005), pcbnew.ERROR_INSIDE)
                    if ps0.OutlineCount() == 0:
                        continue
                    win0, m0 = self.raster_polys(sps_outlines(ps0))
                    jj, ii = np.nonzero(m0)
                    cells += [(li, j + win0[0], i + win0[2]) for j, i in zip(jj, ii)]
                if not layers or net <= 0 or not p.GetNumber():
                    continue
                if not cells:
                    i, j = self.ij(px, py)
                    cells = [(li, j, i) for li in layers]
                info = PadInfo(key, net, p.GetNetname(), p, px, py,
                               p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH, cells, layers)
                if not info.tht:
                    ps1 = pcbnew.SHAPE_POLY_SET()
                    p.TransformShapeToPolygon(ps1, pcbnew.F_Cu, MM(VIA_D / 2 + 0.1), MM(0.005),
                                              pcbnew.ERROR_OUTSIDE)
                    win1, m1 = self.raster_polys(sps_outlines(ps1))
                    jj, ii = np.nonzero(m1)
                    info.via_keepout = [(j + win1[0], i + win1[2]) for j, i in zip(jj, ii)]
                self.pads[key] = info
                self.net_pads.setdefault(net, []).append(info)
                self.netnames[net] = p.GetNetname()

        # copper areas reserved for zones (heat spreaders)
        for name, layers, poly in self.zones:
            net = self.board.FindNet(name).GetNetCode()
            win, m = self.raster_polys([np.array(poly, float)], grow=INFL)
            for lname in layers:
                li = 0 if lname == "F.Cu" else 1
                self.mark(self.static, li, win, m, net)

    # ------------------------------------------------------------ masks
    def base_pass(self, net, win, soft=False):
        """Free cells for `net`.  With soft=True, tracks of other routed nets
        are ignored (returned separately as the second value)."""
        j0, j1, i0, i1 = win
        st = self.static[:, j0:j1, i0:i1]
        fx = self.dynfix[:, j0:j1, i0:i1]
        dy = self.dyn[:, j0:j1, i0:i1]
        hard = ((st == -1) | (st == net)) & ((fx == -1) | (fx == net))
        dyn_ok = (dy == -1) | (dy == net)
        if soft:
            prot = np.isin(dy, list(self.protected - {net}))
            return hard & ~prot, dyn_ok
        return hard & dyn_ok

    def via_ok(self, dist, net, win):
        ok = fits(dist[0], VIA_D) & fits(dist[1], VIA_D)
        j0, j1, i0, i1 = win
        for pi in self.net_pads.get(net, []):     # no vias in or touching own SMD pads
            if pi.tht:
                continue
            for (j, i) in pi.via_keepout:
                if j0 <= j < j1 and i0 <= i < i1:
                    ok[j - j0, i - i0] = False
        # drill-to-drill spacing to every hole, whatever its net
        X, Y = self.grid(win)
        xa, xb = X[0, 0] - 3, X[0, -1] + 3
        ya, yb = Y[0, 0] - 3, Y[-1, 0] + 3
        holes = [(x, y, r) for (x, y, r) in self.holes if xa <= x <= xb and ya <= y <= yb]
        holes += [(it.pts[0][0], it.pts[0][1], VIA_DRILL / 2) for it in self.items
                  if it.kind == "via" and xa <= it.pts[0][0] <= xb and ya <= it.pts[0][1] <= yb]
        for (x, y, r) in holes:
            ok &= np.hypot(X - x, Y - y) >= r + VIA_DRILL / 2 + HOLE_CLR + 0.05
        return ok

    # ------------------------------------------------------------ search
    def search(self, net, src_cells, tgt_cells, win, width=W_SIG, via_cost=COST_VIA,
               taper=None, soft=False, maxexp=8_000_000):
        j0, j1, i0, i1 = win
        h, w = j1 - j0, i1 - i0
        if soft:
            base, dyn_ok = self.base_pass(net, win, soft=True)
        else:
            base = self.base_pass(net, win)
        dist = clearance_map(base)
        cost = np.zeros((2, h, w), np.float32)
        cost += NEAR_COST * (base & (dist <= 2.01 * G))
        if soft:
            # crossing another net's track is allowed at a price (it will be ripped up)
            cost += RIP_COST * (~dyn_ok)
        masks = None
        if taper:
            masks = [(wd, fits(dist, wd)) for wd in taper]
            for wd, m in masks[:-1]:
                cost += 0.8 * (~m)       # discourage necking down where it is not needed
            passm = base.copy()
        else:
            passm = fits(dist, width)
        tgt = np.zeros((2, h, w), np.uint8)
        for (li, j, i) in tgt_cells:
            if j0 <= j < j1 and i0 <= i < i1:
                tgt[li, j - j0, i - i0] = 1
        src = []
        for (li, j, i) in src_cells:
            if j0 <= j < j1 and i0 <= i < i1:
                src.append((li * h + (j - j0)) * w + (i - i0))
        for (li, j, i) in list(src_cells) + list(tgt_cells):   # own pad copper is enterable
            if j0 <= j < j1 and i0 <= i < i1 and base[li, j - j0, i - i0]:
                passm[li, j - j0, i - i0] = True
        if not src or not tgt.any():
            return None
        viaok = self.via_ok(dist, net, win)
        out = np.zeros(2 * h * w + 16, np.int32)
        n = self.lib.astar(w, h, np.ascontiguousarray(passm, np.uint8), np.ascontiguousarray(viaok, np.uint8),
                           np.ascontiguousarray(cost), tgt, np.array(src, np.int32), len(src),
                           via_cost, T45, T90, 1.0, out, len(out), maxexp)
        if n <= 0:
            return None
        path = []
        for c in out[:n]:
            li, rem = divmod(int(c), h * w)
            j, i = divmod(rem, w)
            wd = width
            if masks:
                wd = masks[-1][0]
                for mw, m in masks:
                    if m[li, j, i]:
                        wd = mw
                        break
            path.append((li, j + j0, i + i0, wd))
        return path

    # ------------------------------------------------------------ geometry out
    def path_items(self, net, path, start_xy=None, end_xy=None):
        """Cell path -> per-layer polylines (split where the width changes) + vias."""
        items, runs, cur = [], [], [path[0]]
        for a, b in zip(path[:-1], path[1:]):
            if a[0] != b[0]:
                runs.append(cur)
                items.append(Item(net, "via", -1, [self.xy(b[2], b[1])], VIA_D))
                cur = [b]
            else:
                cur.append(b)
        runs.append(cur)
        for k, run in enumerate(runs):
            pts = [(self.xy(c[2], c[1]), c[3]) for c in run]
            if k == 0 and start_xy is not None:
                pts.insert(0, (start_xy, run[0][3]))
            if k == len(runs) - 1 and end_xy is not None:
                pts.append((end_xy, run[-1][3]))
            if len(pts) < 2:
                continue
            li = run[0][0]
            chain, cw = [pts[0][0]], None
            for (p, wa), (q, wb) in zip(pts[:-1], pts[1:]):
                sw = min(wa, wb)
                if cw is None:
                    cw = sw
                if sw != cw:
                    items.append(Item(net, "track", li, chain, cw))
                    chain, cw = [p], sw
                chain.append(q)
            items.append(Item(net, "track", li, chain, cw))
        return items

    # ------------------------------------------------------------ net routing
    def tree_cells(self, net, root):
        cells = []
        for pi in self.net_pads.get(net, []):
            if pi.key not in NO_TARGET and self.find(pi.key) == root:
                cells += pi.cells
        for it in self.items:
            if it.net != net or it.conn is None or self.find(it.conn) != root:
                continue
            if it.kind == "via":
                i, j = self.ij(*it.pts[0])
                cells += [(0, j, i), (1, j, i)]
                continue
            for (ax, ay), (bx, by) in zip(it.pts[:-1], it.pts[1:]):
                n = max(1, int(round(max(abs(bx - ax), abs(by - ay)) / G)))
                for t in range(n + 1):
                    x = ax + (bx - ax) * t / n
                    y = ay + (by - ay) * t / n
                    i, j = self.ij(x, y)
                    gx, gy = self.xy(i, j)
                    if abs(gx - x) < 1e-6 and abs(gy - y) < 1e-6:
                        cells.append((it.layer, j, i))
        return cells

    def blockers(self, net, path):
        """Nets whose (non-fixed) routed copper conflicts with a cell path."""
        hit = set()
        for (li, j, i, wd) in path:
            v = self.dyn[li, j, i]
            if v == -1 or v == net:
                continue
            x, y = self.xy(i, j)
            for it in self.items:
                if it.fixed or it.net == net or it.net in hit:
                    continue
                xa, ya, xb, yb = it.bbox
                if not (xa <= x <= xb and ya <= y <= yb):
                    continue
                r = it.width / 2 + INFL
                if it.kind == "via":
                    if math.hypot(x - it.pts[0][0], y - it.pts[0][1]) < VIA_D / 2 + INFL:
                        hit.add(it.net)
                elif it.layer == li:
                    for (ax, ay), (bx, by) in zip(it.pts[:-1], it.pts[1:]):
                        if seg_dist(x, y, ax, ay, bx, by) < r:
                            hit.add(it.net)
                            break
        return hit

    def rip(self, net):
        dead = [it for it in self.items if it.net == net and not it.fixed]
        self.remove_items(dead)
        self.unions = [(a, b) for (a, b) in self.unions
                       if not (isinstance(a, tuple) and a[0] == "c" and a[1] == net)]
        self.junctions = {jn for jn in self.junctions if jn[0] != net}
        self.rebuild_forest()
        self.rips[net] = self.rips.get(net, 0) + 1
        self.log.append(f"rip-up {self.netnames[net]}")

    def connect(self, net, src_pads, tgt_key, width, taper, via_cost, ripped):
        """Route from the island holding src_pads to the component of tgt_key."""
        src_root = self.find(src_pads[0].key)
        tgt_root = self.find(tgt_key)
        src_cells = []
        for pi in src_pads:
            src_cells += pi.cells
        src_cells += self.tree_cells(net, src_root)
        tgt_cells = self.tree_cells(net, tgt_root)
        if not tgt_cells or not src_cells:
            return False
        sa = np.array([(j, i) for (_, j, i) in src_cells])
        ta = np.array([(j, i) for (_, j, i) in tgt_cells])
        d = np.hypot(*(ta - sa.mean(0)).T)
        near = ta[d <= d.min() + 80]

        def window(m):
            ja = min(sa[:, 0].min(), near[:, 0].min()) - m
            jb = max(sa[:, 0].max(), near[:, 0].max()) + m
            ia = min(sa[:, 1].min(), near[:, 1].min()) - m
            ib = max(sa[:, 1].max(), near[:, 1].max()) + m
            return (max(0, ja), min(self.H, jb + 1), max(0, ia), min(self.W, ib + 1))

        path = None
        for m in (40, 120, 400):
            path = self.search(net, src_cells, tgt_cells, window(m), width, via_cost, taper)
            if path:
                break
        if not path and ripped is not None:
            soft = self.search(net, src_cells, tgt_cells, window(120), width, via_cost, taper, soft=True)
            if soft:
                victims = [v for v in self.blockers(net, soft)
                           if self.rips.get(v, 0) < MAX_RIPS and v not in self.protected]
                if victims:
                    for v in victims:
                        self.rip(v)
                        ripped.append(v)
                    for m in (40, 120, 400):
                        path = self.search(net, src_cells, tgt_cells, window(m), width, via_cost, taper)
                        if path:
                            break
        if not path:
            return False

        def pad_at(cell):
            for pi in self.net_pads[net]:
                if (cell[0], cell[1], cell[2]) in pi.cellset:
                    return pi
            return None
        a, b = path[0], path[-1]
        pa, pb = pad_at(a), pad_at(b)
        for c, pp in ((a, pa), (b, pb)):
            if pp is None:
                x, y = self.xy(c[2], c[1])
                self.junctions.add((net, c[0], round(x, 4), round(y, 4)))
        start = (pa.x, pa.y) if pa is not None else None
        end = (pb.x, pb.y) if pb is not None else None
        self.nconn += 1
        conn = ("c", net, self.nconn)
        for it in self.path_items(net, path, start, end):
            it.conn = conn
            self.add_item(it)
        self.union(conn, src_pads[0].key)
        self.union(conn, tgt_key)
        return True

    def route_net(self, net, ripped, stage=0):
        """stage 1: only the full-width power pads, 2: the rest, 0: everything."""
        name = self.netnames[net]
        pads = self.net_pads[net]
        if len(pads) < 2:
            return True
        full_w, full_pads, rest_w = POWER.get(name, (W_SIG, None, W_SIG))
        root_key = ROOT.get(name)
        root = self.pads[root_key] if root_key else None
        if root is None:
            cx = np.mean([p.x for p in pads]); cy = np.mean([p.y for p in pads])
            root = min(pads, key=lambda p: (p.x - cx) ** 2 + (p.y - cy) ** 2)
        stages = []
        if full_pads:
            if stage in (0, 1):
                stages.append(([p for p in pads if p.key in full_pads], full_w))
            if stage in (0, 2):
                stages.append((pads, rest_w))
        else:
            stages.append((pads, full_w))
        ok = True
        for group, wd in stages:
            taper = tuple(t for t in TAPER if t <= wd) if wd > 0.45 else None
            vc = COST_VIA_POWER if wd > 0.45 else COST_VIA
            skip = set()
            while True:
                tree = self.find(root.key)
                todo = {}
                for p in group:
                    r = self.find(p.key)
                    if r != tree and r not in skip:
                        todo.setdefault(r, []).append(p)
                if not todo:
                    break
                tree_pads = [p for p in pads if self.find(p.key) == tree]
                best = None
                for r, ps in todo.items():
                    dd = min(math.hypot(a.x - b.x, a.y - b.y) for a in ps for b in tree_pads)
                    if best is None or dd < best[0]:
                        best = (dd, r, ps)
                _, r, ps = best
                if not self.connect(net, ps, root.key, wd, taper, vc, ripped):
                    self.failed.append((name, [p.key for p in ps]))
                    self.log.append(f"FAIL {name}: {[p.key for p in ps]}")
                    skip.add(r)
                    ok = False
        return ok

    # ------------------------------------------------------------ planes
    def fanout(self, pi, nvia=1, fan_w=0.3):
        """Via(s) next to an SMD pad of a plane net, joined by a short track."""
        net, pad = pi.net, pi.pad
        bb = pad.GetBoundingBox()
        ext = max(bb.GetWidth(), bb.GetHeight()) / 2e6
        R = ext + 1.8
        win = self.win_of_bbox(pi.x - R - 1, pi.y - R - 1, pi.x + R + 1, pi.y + R + 1)
        j0, j1, i0, i1 = win
        fpc = pad.GetParentFootprint().GetPosition()
        ox, oy = pi.x - fpc.x / 1e6, pi.y - fpc.y / 1e6
        on = math.hypot(ox, oy)
        ox, oy = (ox / on, oy / on) if on > 0.2 else (0.0, 0.0)
        placed = []
        for _ in range(nvia):
            base = self.base_pass(net, win)
            dist = clearance_map(base)
            viaok = self.via_ok(dist, net, win)
            tmask = dist[0] > max(fan_w / 2 - HW0, 0) + G
            for (li, j, i) in pi.cells:
                if li == 0 and j0 <= j < j1 and i0 <= i < i1:
                    tmask[j - j0, i - i0] = True
            cand = []
            for j, i in zip(*np.nonzero(viaok)):
                x, y = self.xy(i + i0, j + j0)
                dx, dy = x - pi.x, y - pi.y
                d = math.hypot(dx, dy)
                if d > R or any(math.hypot(x - px, y - py) < VIA_D + 0.35 for px, py in placed):
                    continue
                cosang = (dx * ox + dy * oy) / d if d > 0 else 0
                cand.append((d + 0.8 * (1 - cosang), x, y))
            cand.sort()
            done = False
            for score, x, y in cand:
                n = max(2, int(math.hypot(x - pi.x, y - pi.y) / (G / 2)))
                good = True
                for t in range(n + 1):
                    ci, cj = self.ij(pi.x + (x - pi.x) * t / n, pi.y + (y - pi.y) * t / n)
                    ci -= i0; cj -= j0
                    if not (0 <= cj < tmask.shape[0] and 0 <= ci < tmask.shape[1]) or not tmask[cj, ci]:
                        good = False
                        break
                if not good:
                    continue
                placed.append((x, y))
                conn = ("f", net, pi.key, len(placed))
                self.add_item(Item(net, "via", -1, [(x, y)], VIA_D, fixed=True, conn=conn))
                self.add_item(Item(net, "track", 0, [(pi.x, pi.y), (x, y)], fan_w, fixed=True, conn=conn))
                self.union(conn, pi.key)
                self.union(conn, ("plane", net))
                done = True
                break
            if not done:
                break
        return len(placed)

    def plane_nets(self):
        self.unfanned = []
        for name in PLANES:
            net = self.board.FindNet(name).GetNetCode()
            for pi in self.net_pads.get(net, []):
                if pi.tht:
                    self.union(pi.key, ("plane", net))
            smd = [pi for pi in self.net_pads.get(net, []) if not pi.tht]
            smd.sort(key=lambda p: -p.pad.GetSize().x * p.pad.GetSize().y)
            for pi in smd:
                sz = pi.pad.GetSize()
                area = sz.x * sz.y / 1e12
                nv = 3 if area > 6 else (2 if area > 2.5 else 1)
                fw = 0.5 if area > 2.5 else 0.3
                if self.fanout(pi, nv, fw) == 0:
                    self.log.append(f"no fanout for {pi.key} ({name})")
                    self.unfanned.append(pi)

    def route_unfanned(self):
        """Pads that could not get a via: route them to plane-connected copper."""
        for pi in self.unfanned:
            net = pi.net
            if not self.connect(net, [pi], ("plane", net), 0.3, None, COST_VIA, []):
                self.failed.append((self.netnames[net], [pi.key]))
                self.log.append(f"FAIL plane pad {pi.key}")

    def place_vias(self, name, points, margin=0.0, pad_gap=0.0):
        """Fixed vias of a net at the given points where they fit.  pad_gap
        keeps them that far (mm) from the copper of any pad, own net included."""
        net = self.board.FindNet(name).GetNetCode()
        n = 0
        for x, y in points:
            win = self.win_of_bbox(x - 2, y - 2, x + 2, y + 2)
            base = self.base_pass(net, win)
            dist = clearance_map(base)
            ok = self.via_ok(dist, net, win) & fits(dist[0], VIA_D + 2 * margin) & fits(dist[1], VIA_D + 2 * margin)
            if pad_gap > 0:
                j0, j1, i0, i1 = win
                free = clearance_map(self.static[:, j0:j1, i0:i1] == -1)
                ok &= (free[0] > VIA_D / 2 + pad_gap) & (free[1] > VIA_D / 2 + pad_gap)
            i, j = self.ij(x, y)
            if ok[j - win[0], i - win[2]]:
                gx, gy = self.xy(i, j)
                conn = ("v", net, n)
                self.add_item(Item(net, "via", -1, [(gx, gy)], VIA_D, fixed=True, conn=conn))
                if name in PLANES:
                    self.union(conn, ("plane", net))
                n += 1
        return n

    def stitch(self, name, pitch=7.5, margin=0.3):
        """GND stitching vias on a regular grid wherever they fit."""
        x0, y0, x1, y1, _ = self.bx
        pts = [(x, y) for x in np.arange(x0 + 3, x1 - 2, pitch) for y in np.arange(y0 + 3, y1 - 2, pitch)]
        return self.place_vias(name, pts, margin, pad_gap=0.6)

    # ------------------------------------------------------------ prerouting
    def preroute(self):
        for name, padkey, (ex, ey) in PREROUTES:
            pi = self.pads[padkey]
            net = pi.net
            it = Item(net, "track", 0, [(pi.x, pi.y), (ex, ey)], W_SIG, fixed=True, conn=None)
            self.add_item(it)
            for q in self.net_pads[net]:
                if q.key != padkey and q.pad.HitTest(pcbnew.VECTOR2I(MM(ex), MM(ey))):
                    self.union(padkey, q.key)

    # ------------------------------------------------------------ main
    def run(self, thermal_vias=()):
        self.build_static()
        self.preroute()
        for name, pts in thermal_vias:
            self.place_vias(name, pts)
        self.plane_nets()
        self.route_unfanned()
        nets = [n for n in self.net_pads if self.netnames[n] not in PLANES
                and not self.netnames[n].startswith("unconnected-")]

        def span(n):
            ps = self.net_pads[n]
            xs = [p.x for p in ps]; ys = [p.y for p in ps]
            return (max(xs) - min(xs)) + (max(ys) - min(ys))
        first = [self.board.FindNet(nm).GetNetCode() for nm in ORDER_FIRST]
        self.protected = set(self.board.FindNet(nm).GetNetCode() for nm in POWER)
        # full-width power paths first, then the analogue loop, then the power
        # nets' low-current branches, then everything else (shortest first)
        queue = [(n, 1 if POWER.get(self.netnames[n], (0, None))[1] else 0) for n in first]
        queue += [(n, 2) for n in first if POWER.get(self.netnames[n], (0, None))[1]]
        queue += [(n, 0) for n in sorted([n for n in nets if n not in first], key=span)]
        while queue:
            net, stage = queue.pop(0)
            ripped = []
            if stage != 1:
                self.failed = [f for f in self.failed if f[0] != self.netnames[net]]
            self.route_net(net, ripped, stage)
            for v in ripped:
                if (v, 0) not in queue:
                    queue.append((v, 0))
        self.stitch("GND")
        return self.failed

    def emit(self):
        board = self.board
        n_t = n_v = 0
        for it in self.items:
            ni = board.FindNet(self.netnames[it.net])
            if it.kind == "via":
                v = pcbnew.PCB_VIA(board)
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetPosition(pcbnew.VECTOR2I(MM(it.pts[0][0]), MM(it.pts[0][1])))
                v.SetWidth(MM(VIA_D)); v.SetDrill(MM(VIA_DRILL))
                v.SetNet(ni)
                board.Add(v)
                n_v += 1
                continue
            # split segments at T-junctions so every joint is a shared end point
            jx = [(x, y) for (n, l, x, y) in self.junctions if n == it.net and l == it.layer]
            pts = [it.pts[0]]
            for (ax, ay), (bx, by) in zip(it.pts[:-1], it.pts[1:]):
                L = math.hypot(bx - ax, by - ay)
                mids = []
                for (x, y) in jx:
                    if L > 0 and seg_dist(x, y, ax, ay, bx, by) < 1e-4:
                        t = ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (L * L)
                        if 1e-6 < t < 1 - 1e-6:
                            mids.append((t, (x, y)))
                pts += [p for _, p in sorted(mids)] + [(bx, by)]
            for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
                if abs(ax - bx) < 1e-9 and abs(ay - by) < 1e-9:
                    continue
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(MM(ax), MM(ay)))
                t.SetEnd(pcbnew.VECTOR2I(MM(bx), MM(by)))
                t.SetWidth(MM(it.width))
                t.SetLayer(LAYERS[it.layer])
                t.SetNet(ni)
                board.Add(t)
                n_t += 1
        return n_t, n_v
