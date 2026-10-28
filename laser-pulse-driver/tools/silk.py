"""Silkscreen tidy-up for the generated board.

* footprint silk lines that leave the board (panel connectors overhang the
  edges) are removed;
* reference designators are re-placed next to their part where they clear all
  pads, silk lines, other references and the board edge; a reference that
  cannot be placed legibly is moved to the fab layer only;
* a few board labels are added.
"""
import pcbnew

MM = pcbnew.FromMM
EDGE_GAP = 0.5      # silk to board edge (mm)
PAD_GAP = 0.2       # silk to exposed copper
SILK_GAP = 0.15     # silk to silk
SIZES = (1.0, 0.8)  # preferred text heights (mm), tried in order


def _bb(item, grow=0.0):
    b = item.GetBoundingBox()
    g = MM(grow)
    return (b.GetLeft() - g, b.GetTop() - g, b.GetRight() + g, b.GetBottom() + g)


def _hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def clip_silk(board, x0, y0, x1, y1):
    """Move footprint silk graphics that come within EDGE_GAP of the edge to
    the fab layer (deleting items through the Python API is not safe)."""
    lo_x, lo_y, hi_x, hi_y = MM(x0 + EDGE_GAP), MM(y0 + EDGE_GAP), MM(x1 - EDGE_GAP), MM(y1 - EDGE_GAP)
    n = 0
    for fp in board.GetFootprints():
        dead = []
        for g in fp.GraphicalItems():
            if g.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                continue
            b = _bb(g)
            if b[0] < lo_x or b[1] < lo_y or b[2] > hi_x or b[3] > hi_y:
                dead.append(g)
        for g in dead:
            g.SetLayer(pcbnew.F_Fab)
            n += 1
    return n


def _clip_seg(ax, ay, bx, by, boxes):
    """Parts of segment a-b outside all axis-aligned boxes (Liang-Barsky)."""
    keep = [(0.0, 1.0)]
    dx, dy = bx - ax, by - ay
    for (l, t, r, b) in boxes:
        t0, t1 = 0.0, 1.0
        ok = True
        for p, q in ((-dx, ax - l), (dx, r - ax), (-dy, ay - t), (dy, b - ay)):
            if p == 0:
                if q < 0:
                    ok = False
                    break
                continue
            u = q / p
            if p < 0:
                t0 = max(t0, u)
            else:
                t1 = min(t1, u)
        if not ok or t0 >= t1:
            continue
        nk = []
        for (s0, s1) in keep:
            if t1 <= s0 or t0 >= s1:
                nk.append((s0, s1))
                continue
            if t0 > s0:
                nk.append((s0, t0))
            if t1 < s1:
                nk.append((t1, s1))
        keep = nk
    return [(ax + dx * s0, ay + dy * s0, ax + dx * s1, ay + dy * s1) for s0, s1 in keep]


def trim_silk_at_pads(board):
    """Shorten footprint silk lines where they cross exposed copper (the
    longest remaining piece is kept); other silk shapes that touch copper go
    to the fab layer."""
    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(pcbnew.F_Mask) or p.IsOnLayer(pcbnew.F_Cu):
                pads.append(_bb(p, PAD_GAP + 0.1))
    n = 0
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetLayer() != pcbnew.F_SilkS or g.GetClass() == "PCB_TEXT":
                continue
            b = _bb(g)
            near = [p for p in pads if _hit(b, p)]
            if not near:
                continue
            n += 1
            if g.GetShape() != pcbnew.SHAPE_T_SEGMENT:
                g.SetLayer(pcbnew.F_Fab)
                continue
            a, e = g.GetStart(), g.GetEnd()
            pieces = _clip_seg(a.x, a.y, e.x, e.y, near)
            pieces = [q for q in pieces if abs(q[2] - q[0]) + abs(q[3] - q[1]) >= MM(0.3)]
            if not pieces:
                g.SetLayer(pcbnew.F_Fab)
                continue
            x1, y1, x2, y2 = max(pieces, key=lambda q: abs(q[2] - q[0]) + abs(q[3] - q[1]))
            g.SetStart(pcbnew.VECTOR2I(int(x1), int(y1)))
            g.SetEnd(pcbnew.VECTOR2I(int(x2), int(y2)))
    return n


def place_refs(board, x0, y0, x1, y1, skip=()):
    lim = (MM(x0 + EDGE_GAP), MM(y0 + EDGE_GAP), MM(x1 - EDGE_GAP), MM(y1 - EDGE_GAP))
    obst = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.F_Mask):
                obst.append(_bb(p, PAD_GAP))
        for g in fp.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS and g.GetClass() != "PCB_TEXT":
                obst.append(_bb(g, SILK_GAP))
    placed = []
    fps = sorted(board.GetFootprints(), key=lambda f: -f.GetBoundingBox(False).GetArea())
    hidden = []
    for fp in fps:
        ref = fp.Reference()
        if fp.GetReference() in skip or fp.IsExcludedFromBOM() and fp.GetReference()[0] in "HN":
            ref.SetVisible(False)
            continue
        ref.SetLayer(pcbnew.F_SilkS)
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        cb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
        L, T, R, B = cb.GetLeft(), cb.GetTop(), cb.GetRight(), cb.GetBottom()
        cx, cyy = (L + R) // 2, (T + B) // 2
        done = False
        for size in SIZES:
            ref.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
            ref.SetTextThickness(MM(0.15))
            ref.SetKeepUpright(True)
            gap = MM(0.25)
            cands = []
            for ang in (0, 90):
                ref.SetTextAngleDegrees(ang)
                ref.SetPosition(pcbnew.VECTOR2I(cx, cyy))
                tb = _bb(ref)
                hw, hh = (tb[2] - tb[0]) // 2, (tb[3] - tb[1]) // 2
                for dx in (0, -1, 1, -2, 2):
                    sx = dx * (R - L) // 4
                    cands.append((ang, cx + sx, T - gap - hh))          # above
                    cands.append((ang, cx + sx, B + gap + hh))          # below
                for dy in (0, -1, 1):
                    sy = dy * (B - T) // 4
                    cands.append((ang, L - gap - hw, cyy + sy))         # left
                    cands.append((ang, R + gap + hw, cyy + sy))         # right
            # prefer the footprint's own orientation first
            rot = round(fp.GetOrientationDegrees()) % 180
            cands.sort(key=lambda c: 0 if c[0] == rot else 1)
            for ang, x, y in cands:
                ref.SetTextAngleDegrees(ang)
                ref.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
                tb = _bb(ref)
                if tb[0] < lim[0] or tb[1] < lim[1] or tb[2] > lim[2] or tb[3] > lim[3]:
                    continue
                if any(_hit(tb, o) for o in obst) or any(_hit(tb, o) for o in placed):
                    continue
                placed.append(_bb(ref, SILK_GAP))
                done = True
                break
            if done:
                break
        if not done:
            ref.SetLayer(pcbnew.F_Fab)
            ref.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
            ref.SetPosition(pcbnew.VECTOR2I(cx, cyy))
            hidden.append(fp.GetReference())
    return hidden


def add_text(board, s, x, y, size=1.5, angle=0, layer=pcbnew.F_SilkS, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(MM(size), MM(size)))
    t.SetTextThickness(MM(max(0.15, size * 0.15)))
    t.SetBold(bold)
    t.SetTextAngleDegrees(angle)
    t.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
    board.Add(t)
    return t
