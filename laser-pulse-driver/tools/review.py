#!/usr/bin/env python3
"""Review renders for a human check of the design (written to ../docs/review/).

Each function draws one thing that is easy to get wrong and hard to see in a
3D render: footprints to scale with pad numbers, nets and hole sizes; where pin
1 / the cathode / + of every polarised part sits on the board; close-ups of
the critical copper; enclosure cross-sections through every panel connector;
panel faces; the cable wiring.

  python3 review.py [name ...]     (no names: everything)
"""
import math, os, re, subprocess, sys, tempfile
import numpy as np
import pcbnew
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Circle, Rectangle, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import placement, design

HW = os.path.normpath(os.path.join(HERE, "..", "hardware"))
OUT = os.path.normpath(os.path.join(HERE, "..", "docs", "review"))
PCB = os.path.join(HW, design.PROJECT + ".kicad_pcb")
FPDIR = "/usr/share/kicad/footprints"
LOCAL = os.path.join(HW, "lib", "ld405.pretty")

CU, CU_TH, HOLE = "#c99a3b", "#b5862b", "#ffffff"
INK, MUTED, ACCENT, WARN = "#1d2733", "#6b7685", "#c0392b", "#d35400"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": MUTED})

_board = None


def board():
    global _board
    if _board is None:
        _board = pcbnew.LoadBoard(PCB)
    return _board


def fp_by_ref(ref):
    for fp in board().GetFootprints():
        if fp.GetReference() == ref:
            return fp
    raise KeyError(ref)


def polys(sps):
    out = []
    for k in range(sps.OutlineCount()):
        ol = sps.Outline(k)
        out.append([(ol.CPoint(i).x / 1e6, ol.CPoint(i).y / 1e6) for i in range(ol.PointCount())])
    return out


def lib_fp(fpid):
    lib, name = fpid.split(":")
    path = LOCAL if lib == "ld405" else os.path.join(FPDIR, lib + ".pretty")
    return pcbnew.FootprintLoad(path, name)


def save(fig, name, tight=True):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name + ".png")
    fig.savefig(p, dpi=130, bbox_inches="tight" if tight else None, facecolor="white")
    plt.close(fig)
    print("  ", os.path.relpath(p, OUT))
    return p


# ------------------------------------------------------------------ footprints
def shape_line(g):
    """Centre line of an outline graphic (mm), or None for polygons."""
    sh = g.GetShape()
    mm = lambda v: (v.x / 1e6, v.y / 1e6)
    if sh == pcbnew.SHAPE_T_SEGMENT:
        return [mm(g.GetStart()), mm(g.GetEnd())]
    if sh in (pcbnew.SHAPE_T_RECT, pcbnew.SHAPE_T_RECTANGLE):
        c = [mm(v) for v in g.GetRectCorners()]
        return c + c[:1]
    if sh in (pcbnew.SHAPE_T_CIRCLE, pcbnew.SHAPE_T_ARC):
        cx, cy = mm(g.GetCenter())
        r = g.GetRadius() / 1e6
        if sh == pcbnew.SHAPE_T_CIRCLE:
            a0, sweep = 0.0, 2 * math.pi
        else:
            ang = lambda p: math.atan2(p[1] - cy, p[0] - cx)
            a0, am, a1 = ang(mm(g.GetStart())), ang(mm(g.GetArcMid())), ang(mm(g.GetEnd()))
            sweep = (a1 - a0) % (2 * math.pi)
            if (am - a0) % (2 * math.pi) > sweep:          # the arc runs the other way round
                sweep -= 2 * math.pi
        return [(cx + r * math.cos(a0 + sweep * k / 48), cy + r * math.sin(a0 + sweep * k / 48)) for k in range(49)]
    return None


def draw_footprint(ax, ref, rot=0.0, labels=True, nets=True, dims=True, fab=True, title=None):
    """Draw the library footprint used for `ref` in its library orientation
    (optionally rotated by `rot` degrees, counter-clockwise on screen), with
    pad numbers, net names from the board and drill sizes."""
    bfp = fp_by_ref(ref)
    fpid = bfp.GetFPID()
    fp = lib_fp(f"{fpid.GetLibNickname()}:{fpid.GetLibItemName()}")
    fp.SetOrientationDegrees(rot)
    netof = {}
    for p in bfp.Pads():
        netof.setdefault(p.GetNumber(), p.GetNetname())
    ext = []                                    # every drawn point, for the axis limits
    for g in fp.GraphicalItems():
        ly = g.GetLayer()
        if g.GetClass() == "PCB_TEXT" or ly not in (pcbnew.F_Fab, pcbnew.F_CrtYd, pcbnew.F_SilkS):
            continue
        if ly == pcbnew.F_Fab and not fab:
            continue
        col = {pcbnew.F_Fab: "#8a94a3", pcbnew.F_CrtYd: "#d7dbe0", pcbnew.F_SilkS: "#2f3d4c"}[ly]
        lw = {pcbnew.F_Fab: 0.8, pcbnew.F_CrtYd: 0.6, pcbnew.F_SilkS: 1.2}[ly]
        ls = "--" if ly == pcbnew.F_CrtYd else "-"
        line = shape_line(g)
        if line is not None and not g.IsFilled():
            ax.plot([p[0] for p in line], [p[1] for p in line], color=col, lw=lw, ls=ls, zorder=1)
            ext += line
        else:
            ps = pcbnew.SHAPE_POLY_SET()
            g.TransformShapeToPolygon(ps, ly, 0, pcbnew.FromMM(0.01), pcbnew.ERROR_INSIDE)
            for pts in polys(ps):
                ext += pts
                ax.add_patch(Polygon(pts, closed=True, fc=col, ec="none", alpha=0.5, zorder=1))
    pads = [p for p in fp.Pads() if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.B_Cu)
            or p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH]
    centres = [(p.GetPosition().x / 1e6, p.GetPosition().y / 1e6) for p in pads]
    # two columns of numbered pads (SOT-23, SOIC, DPAK, relay): net names go outwards
    numbered = [p for p in pads if p.GetNumber()[:1].isdigit()]
    cols = sorted(set(round(p.GetPosition().x / 1e6, 1) for p in numbered))
    columns = len(cols) == 2 and len(numbered) >= 3
    xmid = (cols[0] + cols[-1]) / 2 if cols else 0.0
    texts = []

    def crowded(x, y, w, dy):
        """another pad centre within the label's slot above (dy < 0) or below (dy > 0)?"""
        return any(abs(cx - x) < w and 0 < (cy - y) * dy / abs(dy) < abs(dy) for cx, cy in centres
                   if (cx, cy) != (x, y))

    for p in pads:
        ps = pcbnew.SHAPE_POLY_SET()
        p.TransformShapeToPolygon(ps, pcbnew.F_Cu, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
        tht = p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        npth = p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
        for pts in polys(ps):
            ext += pts
            if not npth:
                ax.add_patch(Polygon(pts, closed=True, fc=CU_TH if tht else CU, ec="#7a5a12", lw=0.4, zorder=2))
        pos = p.GetPosition()
        x, y = pos.x / 1e6, pos.y / 1e6
        bb = p.GetBoundingBox()
        pw, ph = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
        if p.HasHole():
            d = p.GetDrillSize()
            dx, dy = d.x / 1e6, d.y / 1e6
            if abs(dx - dy) < 1e-6:
                ax.add_patch(Circle((x, y), dx / 2, fc=HOLE, ec="#555", lw=0.5, zorder=3))
            else:
                hs = pcbnew.SHAPE_POLY_SET()
                p.TransformHoleToPolygon(hs, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
                for pts in polys(hs):
                    ax.add_patch(Polygon(pts, closed=True, fc=HOLE, ec="#555", lw=0.5, zorder=3))
            if dims:
                txt = f"Ø{dx:g}" if abs(dx - dy) < 1e-6 else f"{dx:g}×{dy:g}"
                if crowded(x, y, pw, ph / 2 + 2.2):          # no room below: put it on the left
                    t = ax.text(x - pw / 2 - 0.2, y, txt, ha="right", va="center", fontsize=6.5, color=MUTED, zorder=5)
                else:
                    t = ax.text(x, y + ph / 2 + 0.2, txt, ha="center", va="top", fontsize=6.5, color=MUTED, zorder=5)
                texts.append(t)
        num = p.GetNumber()
        if labels and num:
            ax.text(x, y, num, ha="center", va="center", fontsize=8.5, weight="bold", color=INK, zorder=6)
        if nets and num in netof and netof[num]:
            n = netof[num]
            n = "NC" if n.startswith("unconnected") else n
            kw = dict(fontsize=6.5, color="#1f5fa8" if n != "NC" else MUTED, zorder=6,
                      bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.85))
            if columns and x < xmid:
                t = ax.text(x - pw / 2 - 0.3, y, n, ha="right", va="center", **kw)
            elif columns:
                t = ax.text(x + pw / 2 + 0.3, y, n, ha="left", va="center", **kw)
            elif crowded(x, y, pw, -(ph / 2 + 2.2)):           # no room above: put it on the right
                t = ax.text(x + pw / 2 + 0.25, y, n, ha="left", va="center", **kw)
            else:
                t = ax.text(x, y - 0.32 - ph / 2, n, ha="center", va="bottom", **kw)
            texts.append(t)
    e = np.array(ext)
    m = 1.2
    x0, x1, y0, y1 = e[:, 0].min() - m, e[:, 0].max() + m, e[:, 1].min() - m, e[:, 1].max() + m
    ax.set_xlim(x0, x1)
    ax.set_ylim(y1, y0)
    ax.set_aspect("equal")
    # widen the view until every label fits inside the frame
    for _ in range(2):
        ax.figure.canvas.draw()
        r = ax.figure.canvas.get_renderer()
        inv = ax.transData.inverted()
        for t in texts:
            b = t.get_window_extent(r).transformed(inv)
            x0, x1 = min(x0, b.x0 - 0.3), max(x1, b.x1 + 0.3)
            y0, y1 = min(y0, min(b.y0, b.y1) - 0.3), max(y1, max(b.y0, b.y1) + 0.3)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y1, y0)
    ax.grid(True, color="#eef0f3", lw=0.5, zorder=0)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("mm (footprint coordinates, top view)", fontsize=7, color=MUTED)
    if title:
        ax.set_title(title, fontsize=10, color=INK, loc="left")
    return fp


def card_footprints():
    specs = [
        ("fp_relay_K1", "K1", 0, "K1 relay G6K-2F-Y: pads and nets (after fix)"),
        ("fp_toggle_SW1", "SW1", 0, "SW1 toggle 1MS1T2B4M7QES: pads, holes, nets"),
        ("fp_led_D3", "D3", 0, "D3 side-view LED Lite-On LTST-S220 (lens towards -X): pads and nets"),
        ("fp_bnc_J2", "J2", 0, "J2 BNC DOSIN-801-0080: pads and holes"),
        ("fp_dcjack_J1", "J1", 0, "J1 DC jack DC-005: slots and nets"),
        ("fp_jack35_J6", "J6", 0, "J6 3.5 mm jack PJ-320D: pads and nets"),
        ("fp_dsub_J5", "J5", 0, "J5 DE-9 socket (CONNFLY DS1037): pins Ø1.0, board locks Ø3.2"),
        ("fp_pot_RV1", "RV1", 0, "RV1 pot Alps RK09L horizontal: pads, lugs, nets"),
    ]
    for name, ref, rot, title in specs:
        fig, ax = plt.subplots(figsize=(6.4, 5.2))
        draw_footprint(ax, ref, rot, title=title, dims=ref != "J5")
        save(fig, name)


def card_smd_pinouts():
    """Small multiples: every polarised SMD part type with pad numbers and nets."""
    groups = [("SOT-23 MOSFETs (1 = G, 2 = S, 3 = D)", ["Q1", "Q6", "Q10", "Q4"]),
              ("SOT-23 diodes and reference", ["D4", "D10", "U2"]),
              ("SOT-23-5/6 ICs", ["U8", "U14", "U5"]),
              ("DPAK (tab = pad 2)", ["Q2", "U1"])]
    for gi, (gt, refs) in enumerate(groups):
        fig, axs = plt.subplots(1, len(refs), figsize=(3.3 * len(refs), 3.6))
        for ax, ref in zip(np.atleast_1d(axs), refs):
            fp = fp_by_ref(ref)
            p = next(x for x in design.PARTS if x["ref"] == ref)
            draw_footprint(ax, ref, 0, dims=False, title=f"{ref}  {p['value']}")
            ax.set_xlabel("")
        fig.suptitle(gt, x=0.01, ha="left", fontsize=11, color=INK)
        fig.tight_layout()
        save(fig, f"fp_smd_{gi + 1}")



# ------------------------------------------------------------------ board views
def mm(v):
    return v.x / 1e6, v.y / 1e6


def item_lines(items, layer):
    """(line, filled_polys) for the graphic items on `layer` (board coordinates)."""
    lines, fills = [], []
    for g in items:
        if g.GetLayer() != layer or g.GetClass() in ("PCB_TEXT", "PCB_FIELD", "PCB_TEXTBOX"):
            continue
        ln = shape_line(g)
        if ln is not None and not g.IsFilled():
            lines.append(ln)
        else:
            ps = pcbnew.SHAPE_POLY_SET()
            g.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(0.01), pcbnew.ERROR_INSIDE)
            fills += polys(ps)
    return lines, fills


def board_axes(box, width_in=10.0, strip_in=0.0):
    """Axes showing `box` (board mm) to scale, with an optional strip below for a legend."""
    x0, y0, x1, y1 = box
    h = width_in * (y1 - y0) / (x1 - x0)
    fig = plt.figure(figsize=(width_in, h + strip_in))
    ax = fig.add_axes([0, strip_in / (h + strip_in), 1, h / (h + strip_in)])
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal"); ax.axis("off")
    return fig, ax, width_in * 72 / (x1 - x0)          # points per mm


def draw_outline(ax):
    ps = pcbnew.SHAPE_POLY_SET()
    board().GetBoardPolygonOutlines(ps)
    for pts in polys(ps):
        ax.add_patch(Polygon(pts, closed=True, fc="#f4f1e8", ec=INK, lw=1.2, zorder=0))


def pad_polys(p, layer=None):
    layer = layer if layer is not None else (pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
    ps = pcbnew.SHAPE_POLY_SET()
    p.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
    return polys(ps)


def fpname(fp):
    return str(fp.GetFPID().GetLibItemName())


def polarity_kind(fp):
    """What pad 1 means for a polarised part, or None."""
    ref, name = fp.GetReference(), fpname(fp)
    if re.match(r"^CP_Elec", name):
        return "+"
    if ref[0] == "D":
        return "1" if name.startswith("SOT-23") else "K"
    if ref[0] in "UQK":
        return "1"
    return None


def pad_centre(fp):
    pts = [mm(p.GetPosition()) for p in fp.Pads() if p.GetNumber() not in ("", "0", "MP")]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def compass(dx, dy):
    a = math.degrees(math.atan2(-dy, dx)) % 360
    names = ["right", "upper right", "top", "upper left", "left", "lower left", "bottom", "lower right"]
    return names[int(((a + 22.5) % 360) // 45)]


def cpl_rotations():
    import csv
    rot = {}
    with open(os.path.join(HW, "fab", design.PROJECT + "_cpl_jlcpcb.csv")) as f:
        for r in csv.DictReader(f):
            rot[r["Designator"]] = float(r["Rotation"])
    return rot


def polarity_table():
    cpl = cpl_rotations()
    rows = []
    for fp in board().GetFootprints():
        kind = polarity_kind(fp)
        if not kind:
            continue
        pad1 = next(p for p in fp.Pads() if p.GetNumber() == "1")
        cx, cy = pad_centre(fp)
        px, py = mm(pad1.GetPosition())
        part = next(x for x in design.PARTS if x["ref"] == fp.GetReference())
        rows.append(dict(ref=fp.GetReference(), value=part["value"], package=fpname(fp),
                         kicad_rot=fp.GetOrientationDegrees() % 360, cpl_rot=cpl.get(fp.GetReference()),
                         mark={"1": "pin 1", "K": "cathode", "+": "+ terminal"}[kind],
                         where=compass(px - cx, py - cy), x=round(px, 2), y=round(py, 2)))
    rows.sort(key=lambda r: (r["ref"][0], int(re.sub(r"\D", "", r["ref"]))))
    return rows


def draw_polarity(ax, box, ptmm, label_all=True):
    draw_outline(ax)
    b = board()
    sl, sf = item_lines(b.GetDrawings(), pcbnew.F_SilkS)
    for ln in sl:
        ax.plot(*zip(*ln), color="#9aa3ad", lw=0.6, zorder=1)
    x0, y0, x1, y1 = box
    for fp in b.GetFootprints():
        fx, fy = mm(fp.GetPosition())
        if not (x0 - 15 < fx < x1 + 15 and y0 - 15 < fy < y1 + 15):
            continue
        kind = polarity_kind(fp)
        lines, fills = item_lines(fp.GraphicalItems(), pcbnew.F_SilkS)
        for ln in lines:
            ax.plot(*zip(*ln), color="#9aa3ad", lw=0.6, zorder=1)
        for pts in fills:
            ax.add_patch(Polygon(pts, closed=True, fc="#9aa3ad", ec="none", zorder=1))
        lines, _ = item_lines(fp.GraphicalItems(), pcbnew.F_Fab)
        for ln in lines:
            ax.plot(*zip(*ln), color=INK if kind else "#b7bec7", lw=0.9 if kind else 0.5, zorder=2)
        for p in fp.Pads():
            if not (p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.B_Cu)):
                continue
            one = kind and p.GetNumber() == "1"
            for pts in pad_polys(p, pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu):
                ax.add_patch(Polygon(pts, closed=True, fc=ACCENT if one else ("#d9b56a" if kind else "#e6d3a8"),
                                     ec="#7a5a12" if kind else "none", lw=0.3, zorder=3))
            if p.HasHole():
                d = p.GetDrillSize()
                if d.x == d.y:
                    ax.add_patch(Circle(mm(p.GetPosition()), d.x / 2e6, fc="white", ec="none", zorder=4))
        ref = fp.GetReference()
        if kind:
            pad1 = next(p for p in fp.Pads() if p.GetNumber() == "1")
            px, py = mm(pad1.GetPosition())
            cx, cy = pad_centre(fp)
            dx, dy = px - cx, py - cy
            L = math.hypot(dx, dy) or 1
            bb = pad1.GetBoundingBox()
            r = max(bb.GetWidth(), bb.GetHeight()) / 2e6 + 0.35
            ax.add_patch(Circle((px, py), r, fill=False, ec=ACCENT, lw=1.6, zorder=5))
            tx, ty = px + dx / L * (r + 0.9), py + dy / L * (r + 0.9)
            ax.text(tx, ty, kind if kind != "1" else "1", color=ACCENT, fontsize=8, weight="bold",
                    ha="center", va="center", zorder=6)
            ax.text(cx - dx / L * 0.2, cy - dy / L * 0.2, ref, color="#1f5fa8", fontsize=8.5, weight="bold",
                    ha="center", va="center", zorder=6,
                    bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.75))
        elif label_all and not ref.startswith(("H", "NT", "kibuzzard", "REF")):
            ax.text(fx, fy, ref, color="#8a94a3", fontsize=5.5, ha="center", va="center", zorder=6)


QUADS = [("front left", (98, 98, 184, 154)), ("front right", (176, 98, 262, 154)),
         ("rear left", (98, 146, 184, 202)), ("rear right", (176, 146, 262, 202))]


def card_polarity():
    """Pin 1 / cathode / + of every polarised part, as on the JLCPCB placement preview."""
    import json
    fig, ax, ptmm = board_axes((96, 96, 264, 204), 12)
    draw_polarity(ax, (96, 96, 264, 204), ptmm, label_all=False)
    for x in (180,):
        ax.plot([x, x], [99, 201], color=MUTED, lw=1.0, ls=(0, (6, 4)), zorder=7)
    ax.plot([99, 261], [150, 150], color=MUTED, lw=1.0, ls=(0, (6, 4)), zorder=7)
    for i, (name, (x0, y0, x1, y1)) in enumerate(QUADS):
        ax.text((x0 + x1) / 2, 97.6 if i < 2 else 202.4, f"{i + 1}: {name}", color=INK, fontsize=10, weight="bold",
                ha="center", va="center", zorder=8)
    save(fig, "polarity_overview", tight=False)
    for i, (name, box) in enumerate(QUADS):
        fig, ax, ptmm = board_axes(box, 11)
        draw_polarity(ax, box, ptmm)
        ax.text(box[0] + 1, box[1] + 1.5, f"{i + 1}  {name}   (top view, front panel edge at the top)",
                fontsize=10, color=INK, va="top", zorder=9, bbox=dict(fc="white", ec="none", alpha=0.8))
        save(fig, f"polarity_{i + 1}", tight=False)
    rows = polarity_table()
    with open(os.path.join(OUT, "polarity.json"), "w") as f:
        json.dump(rows, f, indent=1)
    print("  ", len(rows), "polarised parts")


# ------------------------------------------------------------------ copper close-ups
MUTED_TOP, MUTED_BOT = "#d39a9a", "#9db1d6"
LAYER_COL = {pcbnew.F_Cu: MUTED_TOP, pcbnew.B_Cu: MUTED_BOT, pcbnew.In1_Cu: "#27ae60", pcbnew.In2_Cu: "#d4a017"}


def draw_copper(ax, box, ptmm, hl, layers=(pcbnew.B_Cu, pcbnew.F_Cu), zones=True, note=None):
    """Tracks, pads, vias and filled zones; nets in `hl` (name -> colour) stand out."""
    b = board()
    x0, y0, x1, y1 = box
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#fbfaf6", ec="none", zorder=0))
    draw_outline(ax)
    inside = lambda x, y: x0 - 3 < x < x1 + 3 and y0 - 3 < y < y1 + 3
    for li, layer in enumerate(layers):
        top = layer == pcbnew.F_Cu
        if zones:
            for z in b.Zones():
                if not z.IsOnLayer(layer) or not z.IsFilled():
                    continue
                net = z.GetNetname()
                fps = z.GetFilledPolysList(layer)
                for pts in polys(fps):
                    if net in hl:
                        ax.add_patch(Polygon(pts, closed=True, fc=hl[net], ec=hl[net], alpha=0.35, lw=0.5, zorder=1 + li))
                    else:
                        ax.add_patch(Polygon(pts, closed=True, fc=LAYER_COL[layer], ec="none",
                                             alpha=0.07 if top else 0.05, zorder=1 + li))
        for t in b.GetTracks():
            if t.GetClass() != "PCB_TRACK" or t.GetLayer() != layer:
                continue
            (sx, sy), (ex, ey) = mm(t.GetStart()), mm(t.GetEnd())
            if not (inside(sx, sy) or inside(ex, ey)):
                continue
            net = t.GetNetname()
            col = hl.get(net, LAYER_COL[layer])
            ax.plot([sx, ex], [sy, ey], color=col, lw=t.GetWidth() / 1e6 * ptmm, solid_capstyle="round",
                    alpha=0.95 if net in hl else (0.6 if top else 0.45), zorder=4 + li)
    for fp in b.GetFootprints():
        fx, fy = mm(fp.GetPosition())
        if not inside(fx, fy) and not any(inside(*mm(p.GetPosition())) for p in fp.Pads()):
            continue
        for p in fp.Pads():
            if not (p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.B_Cu)):
                continue
            net = p.GetNetname()
            for pts in pad_polys(p, pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu):
                ax.add_patch(Polygon(pts, closed=True, fc=hl.get(net, "#cfae6c"), ec="#6b5320", lw=0.3,
                                     alpha=1.0 if net in hl else 0.7, zorder=8))
            if p.HasHole():
                d = p.GetDrillSize()
                if d.x == d.y:
                    ax.add_patch(Circle(mm(p.GetPosition()), d.x / 2e6, fc="white", ec="#555", lw=0.3, zorder=9))
        lines, _ = item_lines(fp.GraphicalItems(), pcbnew.F_Fab)
        for ln in lines:
            ax.plot(*zip(*ln), color="#59636e", lw=0.5, zorder=10)
        if inside(fx, fy) and not fp.GetReference().startswith(("H", "kibuzzard")):
            cx, cy = pad_centre(fp) if len(fp.Pads()) else (fx, fy)
            ax.text(cx, cy, fp.GetReference(), fontsize=7, color=INK, ha="center", va="center", zorder=12,
                    bbox=dict(fc="white", ec="none", pad=0.3, alpha=0.6))
    for t in b.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        x, y = mm(t.GetPosition())
        if not inside(x, y):
            continue
        net = t.GetNetname()
        ax.add_patch(Circle((x, y), t.GetWidth(pcbnew.F_Cu) / 2e6, fc=hl.get(net, "#7f8c8d"), ec="#333", lw=0.3,
                            alpha=1.0 if net in hl else 0.6, zorder=11))
        ax.add_patch(Circle((x, y), t.GetDrillValue() / 2e6, fc="white", ec="none", zorder=11))
    # legend in the strip below the board view
    items = [(c, n) for n, c in hl.items()] + [(MUTED_TOP, "other nets, top copper"),
                                               (MUTED_BOT, "other nets, bottom copper")]
    fig = ax.figure
    per_row = 4
    for k, (c, n) in enumerate(items):
        col, row = k % per_row, k // per_row
        x, y = 0.015 + col * 0.245, 1 - (0.35 + row * 0.3)          # strip-relative
        fy = y * ax.get_position().y0
        fig.patches.append(Rectangle((x, fy - 0.012), 0.025, 0.024 * 11 / fig.get_figheight(),
                                     transform=fig.transFigure, fc=c, ec="none"))
        fig.text(x + 0.032, fy, n, fontsize=8.5, va="center", color=INK)
    if note:
        ax.text(0.012, 0.985, note, transform=ax.transAxes, fontsize=8.5, va="top", color=INK, zorder=13,
                bbox=dict(fc="white", ec="#ccd", pad=3, alpha=0.9))


def card_layout():
    views = [
        ("layout_current_path", (140, 158, 228, 199),
         {"VIN": "#e67e22", "SRC_K": "#8e44ad", "SRC_D": "#e84393", "LD_OUT": "#16a085", "GATE": "#1e3799"},
         "Laser current: VIN -> R40 (0.2 ohm sense) -> R41 (1 ohm) -> Q2 -> LD_OUT -> K1 -> J5 pin 8"),
        ("layout_kelvin", (206, 164, 227, 181),
         {"VIN": "#e67e22", "SRC_K": "#8e44ad", "VIN_SNS": "#27ae60", "SRC_SNS": "#1e3799", "IMON_INT": "#636e72"},
         "Kelvin sense: NT1/NT2 tap R40's pads; U8 (INA180) sees only the shunt voltage"),
        ("layout_ttl_input", (178, 100, 222, 150),
         {"TTL_BNC": "#e84393", "TTL_PROT": "#e67e22", "GATE_N": "#8e44ad", "VSP_MUX": "#16a085", "VSP": "#1e3799"},
         "TTL path: J2 -> R21/C15/D4 clamp -> U14 Schmitt -> U5 analogue switch -> VSP"),
    ]
    for name, box, hl, note in views:
        w = 11 if box[2] - box[0] > 40 else 8
        fig, ax, ptmm = board_axes(box, w, strip_in=0.7)
        draw_copper(ax, box, ptmm, hl, note=note)
        save(fig, name, tight=False)


# ------------------------------------------------------------------ enclosure fit
import gen_3d, gen_enclosure as GE

ENC = os.path.normpath(os.path.join(HERE, "..", "enclosure", "ld405_enclosure.scad"))
Z_PCB = 3.0 + 6.0 + 1.6            # top of the PCB in the enclosure (floor_t + so_h + pcb_t)
Z_LID = Z_PCB + 19.0               # underside of the lid
PANEL_T = 2.5
PART_COL = {"enclosure": "#5b6573", "panel": "#2a5d8f", "lid": "#7d8794", "pcb": "#2f7d4f"}


def dsub_prims():
    """CONNFLY DS1037-09F (datasheet): pin 1 origin, mating side +y.  Flange front
    10.94 mm from the 1-5 row, 30.8 x 12.5 mm; shell 16.33 x 7.9, 5.9 mm long."""
    c, z = -5.54, 6.25
    P = [("box", (0.25, 0.25, 0.27), c - 15.4, -1.46, 0.0, c + 15.4, 10.14, 12.5),     # housing
         ("box", gen_3d.SILVER, c - 15.4, 10.14, 0.0, c + 15.4, 10.94, 12.5),          # steel flange
         ("dsub", gen_3d.SILVER, c, z, 16.33, 7.9, 10.94, 16.84)]                       # D shell
    for dx in (-12.495, 12.495):
        P.append(("cyl", gen_3d.SILVER, (c + dx, 10.94, z), (c + dx, 15.74, z), 2.9))   # 4-40 hex posts
    return P


def fab_bbox(fp):
    """F.Fab (else courtyard) extent of a footprint in footprint coordinates."""
    lib = lib_fp(f"{fp.GetFPID().GetLibNickname()}:{fp.GetFPID().GetLibItemName()}")
    for layer in (pcbnew.F_Fab, pcbnew.F_CrtYd):
        pts = []
        for g in lib.GraphicalItems():
            if g.GetLayer() == layer and g.GetClass() not in ("PCB_TEXT", "PCB_FIELD"):
                ln = shape_line(g)
                if ln:
                    pts += ln
        if pts:
            xs, ys = [q[0] for q in pts], [q[1] for q in pts]
            return min(xs), min(ys), max(xs), max(ys)
    return None


def generic_prims(fp):
    name = fpname(fp)
    m = re.match(r"CP_Elec_(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)", name)
    if m:
        d, h = float(m.group(1)), float(m.group(2))
        return [("cyl", (0.75, 0.76, 0.78), (0, 0, 0), (0, 0, h), d / 2)]
    if name.startswith("DSUB-9"):
        return dsub_prims()
    bb = fab_bbox(fp)
    if not bb:
        return []
    h = 5.2 if "G6K" in name else 2.4 if "TO-252" in name else 2.3 if "D_SMA" in name else 1.75 if "SOIC" in name else 1.1
    return [("box", (0.15, 0.15, 0.16), bb[0], bb[1], 0, bb[2], bb[3], h)]


MODEL_FN = {fn().name: fn for fn in gen_3d.ALL}


def board_prims():
    """Every part as boxes / cylinders in enclosure coordinates: (ref, kind, rgb, geometry)."""
    out = []
    for fp in board().GetFootprints():
        ms = fp.Models()
        prims = None
        if len(ms):
            base = os.path.splitext(os.path.basename(ms[0].m_Filename))[0]
            if base in MODEL_FN:
                prims = MODEL_FN[base]().prims
        if prims is None:
            prims = generic_prims(fp)
        fx, fy = mm(fp.GetPosition())
        th = math.radians(fp.GetOrientationDegrees())
        ct, st = round(math.cos(th), 9), round(math.sin(th), 9)

        def T(x, y, z):          # footprint -> board (KiCad: y down, + angle = CCW on screen) -> enclosure
            bx, by = fx + x * ct + y * st, fy - x * st + y * ct
            return GE.X(bx), GE.Y(by), Z_PCB + z
        for pr in prims:
            if pr[0] == "box":
                _, rgb, x0, y0, z0, x1, y1, z1 = pr
                a, b = T(x0, y0, z0), T(x1, y1, z1)
                out.append((fp.GetReference(), "box", rgb, (min(a[0], b[0]), min(a[1], b[1]), a[2],
                                                            max(a[0], b[0]), max(a[1], b[1]), b[2])))
            elif pr[0] == "cyl":
                _, rgb, p0, p1, r = pr
                out.append((fp.GetReference(), "cyl", rgb, (T(*p0), T(*p1), r)))
            elif pr[0] == "dsub":
                _, rgb, c, z, w, h, y0, y1 = pr
                a, b = T(c, y0, z), T(c, y1, z)
                out.append((fp.GetReference(), "dsub", rgb, (a[0], a[2], w, h, min(a[1], b[1]), max(a[1], b[1]))))
    # check the transform against KiCad for a rotated part: J2 pin 1 must be the BNC centre contact
    j2 = fp_by_ref("J2")
    p1 = next(p for p in j2.Pads() if p.GetNumber() == "1")
    px, py = mm(p1.GetPosition())
    bnc = [o for o in out if o[0] == "J2" and o[1] == "cyl"][0][3]
    assert abs(GE.X(px) - bnc[0][0]) < 0.01, (GE.X(px), bnc[0])
    return out


STL_CACHE = os.environ.get("LD405_ENC_CACHE") or os.path.join(tempfile.gettempdir(), "ld405_enclosure_stl")
_meshes = {}


def enclosure_mesh(part):
    """Triangles (N, 3, 3) of an enclosure part in assembly position (OpenSCAD export, cached)."""
    if part in _meshes:
        return _meshes[part]
    os.makedirs(STL_CACHE, exist_ok=True)
    path = os.path.join(STL_CACHE, part + ".stl")
    if not os.path.exists(path) or os.path.getmtime(path) < os.path.getmtime(ENC):
        print("   exporting", part, "(OpenSCAD, takes a minute)")
        subprocess.run(["openscad", "--export-format", "binstl", "-D", f'part="{part}"', "-o", path, ENC],
                       check=True, capture_output=True)
    with open(path, "rb") as f:
        f.read(80)
        n = int(np.frombuffer(f.read(4), "<u4")[0])
        rec = np.frombuffer(f.read(n * 50), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    _meshes[part] = rec["v"].astype(float)
    return _meshes[part]


def mesh_section(part, plane, c):
    """Cut an enclosure part with X = c ("x") or Y = c ("y"): closed loops in (Y, Z)
    or (X, Z), outer loops counter-clockwise and holes clockwise."""
    from matplotlib.path import Path
    tris = enclosure_mesh(part)
    k = 0 if plane == "x" else 1
    u, v = (1, 2) if plane == "x" else (0, 2)
    d = tris[:, :, k] - c
    d = np.where(np.abs(d) < 1e-7, 1e-7, d)
    pos = d > 0
    hit = (pos.sum(1) == 1) | (pos.sum(1) == 2)
    segs = []
    for t, dd, ss in zip(tris[hit], d[hit], pos[hit]):
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            if ss[i] != ss[j]:
                q = t[i] + dd[i] / (dd[i] - dd[j]) * (t[j] - t[i])
                pts.append((round(q[u], 4), round(q[v], 4)))
        if len(pts) == 2 and pts[0] != pts[1]:
            segs.append(pts)
    ends = {}
    for i, (p0, p1) in enumerate(segs):
        ends.setdefault(p0, []).append(i)
        ends.setdefault(p1, []).append(i)
    used, loops = set(), []
    for i0 in range(len(segs)):
        if i0 in used:
            continue
        used.add(i0)
        loop = [segs[i0][0], segs[i0][1]]
        while True:
            nxt = [j for j in ends.get(loop[-1], []) if j not in used]
            if not nxt:
                break
            j = nxt[0]
            used.add(j)
            p0, p1 = segs[j]
            q = p1 if p0 == loop[-1] else p0
            if q == loop[0]:
                break
            loop.append(q)
        if len(loop) > 2:
            loops.append(loop)
    area = lambda L: 0.5 * sum(L[i][0] * L[i - 1][1] - L[i - 1][0] * L[i][1] for i in range(len(L)))
    paths = [Path(L) for L in loops]
    out = []
    for i, L in enumerate(loops):
        depth = sum(1 for j, P in enumerate(paths) if j != i and P.contains_point(L[0]))
        if (area(L) > 0) != (depth % 2 == 0):
            L = L[::-1]
        out.append(L)
    return out


def scad_section(module, plane, c):
    part = {"front_panel": "front", "rear_panel": "rear"}.get(module, module)
    return mesh_section(part, plane, c)


def prim_section(kind, g, plane, c):
    """Section of one primitive with X = c (returns shapes in (Y, Z)) or Y = c ((X, Z))."""
    ia, ib = (1, 2) if plane == "x" else (0, 2)          # in-plane axes
    ic = 0 if plane == "x" else 1                         # normal axis
    if kind == "box":
        lo, hi = g[:3], g[3:]
        if lo[ic] <= c <= hi[ic]:
            return [("rect", lo[ia], lo[ib], hi[ia], hi[ib])]
        return []
    if kind == "cyl":
        p0, p1, r = g
        d = [p1[i] - p0[i] for i in range(3)]
        L = math.sqrt(sum(v * v for v in d))
        ax = [abs(v) / L for v in d]
        if ax[ic] > 0.999:                                 # axis normal to the plane: a disc
            if min(p0[ic], p1[ic]) <= c <= max(p0[ic], p1[ic]):
                return [("circle", p0[ia], p0[ib], r)]
            return []
        if ax[ic] < 1e-6:                                  # axis parallel to the plane
            off = abs(c - p0[ic])
            if off > r:
                return []
            h = math.sqrt(r * r - off * off)
            ua, ub = d[ia] / L, d[ib] / L
            na, nb = -ub * h, ua * h
            return [("poly", [(p0[ia] + na, p0[ib] + nb), (p1[ia] + na, p1[ib] + nb),
                              (p1[ia] - na, p1[ib] - nb), (p0[ia] - na, p0[ib] - nb)])]
        return []                                          # oblique to the plane: not drawn
    if kind == "dsub":
        x, z, w, h, y0, y1 = g
        if plane == "x" and abs(c - x) <= w / 2:
            return [("rect", y0, z - h / 2, y1, z + h / 2)]
        return []
    return []


def prim_projection(kind, g):
    """Outline of one primitive seen along Y (in (X, Z))."""
    if kind == "box":
        return [("rect", g[0], g[2], g[3], g[5])]
    if kind == "cyl":
        p0, p1, r = g
        d = [p1[i] - p0[i] for i in range(3)]
        L = math.sqrt(sum(v * v for v in d))
        if abs(d[1]) / L > 0.999:
            return [("circle", p0[0], p0[2], r)]
        xs, zs = (p0[0], p1[0]), (p0[2], p1[2])
        return [("rect", min(xs) - (r if abs(d[0]) / L < 0.999 else 0), min(zs) - (r if abs(d[2]) / L < 0.999 else 0),
                 max(xs) + (r if abs(d[0]) / L < 0.999 else 0), max(zs) + (r if abs(d[2]) / L < 0.999 else 0))]
    if kind == "dsub":
        x, z, w, h, y0, y1 = g
        wb = w - 2 * h * math.tan(math.radians(10))
        return [("poly", [(x - w / 2, z + h / 2), (x + w / 2, z + h / 2), (x + wb / 2, z - h / 2), (x - wb / 2, z - h / 2)])]
    return []


def draw_shape(ax, sh, fc, ec, lw=0.8, alpha=1.0, z=3, flipx=False):
    f = (lambda v: -v) if flipx else (lambda v: v)
    if sh[0] == "rect":
        _, a0, b0, a1, b1 = sh
        x0, x1 = sorted((f(a0), f(a1)))
        ax.add_patch(Rectangle((x0, b0), x1 - x0, b1 - b0, fc=fc, ec=ec, lw=lw, alpha=alpha, zorder=z))
    elif sh[0] == "circle":
        ax.add_patch(Circle((f(sh[1]), sh[2]), sh[3], fc=fc, ec=ec, lw=lw, alpha=alpha, zorder=z))
    elif sh[0] == "poly":
        ax.add_patch(Polygon([(f(x), y) for x, y in sh[1]], closed=True, fc=fc, ec=ec, lw=lw, alpha=alpha, zorder=z))


def hexcol(rgb):
    return "#%02x%02x%02x" % tuple(int(255 * v) for v in rgb)


def draw_scad(ax, polys_, fc, z=1, flipx=False, ec=None):
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch
    if not polys_:
        return
    verts, codes = [], []
    for pts in polys_:
        pts = [(-x if flipx else x, y) for x, y in pts]
        verts += pts + [pts[0]]
        codes += [Path.MOVETO] + [Path.LINETO] * (len(pts) - 1) + [Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), fc=fc, ec=ec or fc, lw=0.6, zorder=z))


def ycyl(x, y0, y1, z, r):
    """A cylinder along Y in enclosure coordinates (for nuts, knobs and plugs)."""
    return ((x, y0, z), (x, y1, z), r)


def section_x(c, title, yr, zr, prims, name, labels=(), extras=(), ghosts=(), note=None):
    """Side section through X = c: enclosure parts sliced from the STLs, the PCB, the
    parts at datasheet dimensions, `extras` (nuts, washers: solid) and `ghosts` (a
    typical mating plug or knob: dashed).  `labels` = (text, (Y, Z) pointed at, (Y, Z) of the text)."""
    fig, ax = plt.subplots(figsize=(9.5, 9.5 * (zr[1] - zr[0]) / (yr[1] - yr[0]) + 0.9))
    for mod, col in (("base", PART_COL["enclosure"]), ("front_panel", PART_COL["panel"]),
                     ("rear_panel", PART_COL["panel"]), ("lid", PART_COL["lid"])):
        draw_scad(ax, scad_section(mod, "x", c), col, 1)
    ax.add_patch(Rectangle((0, Z_PCB - 1.6), 100, 1.6, fc=PART_COL["pcb"], ec="none", zorder=2))
    for ref, kind, rgb, g in prims:
        for sh in prim_section(kind, g, "x", c):
            draw_shape(ax, sh, hexcol(rgb), "#222", lw=0.6, z=3)
    for kind, rgb, g in extras:
        for sh in prim_section(kind, g, "x", c):
            draw_shape(ax, sh, hexcol(rgb), "#222", lw=0.6, z=4)
    for kind, g in ghosts:
        for sh in prim_section(kind, g, "x", c):
            if sh[0] == "rect":
                _, a0, b0, a1, b1 = sh
                ax.add_patch(Rectangle((a0, b0), a1 - a0, b1 - b0, fill=False, ec=ACCENT, lw=1.0, ls=(0, (4, 3)), zorder=5))
            elif sh[0] == "poly":
                ax.add_patch(Polygon(sh[1], closed=True, fill=False, ec=ACCENT, lw=1.0, ls=(0, (4, 3)), zorder=5))
    ax.axhline(Z_LID, color=ACCENT, lw=0.8, ls=":", zorder=6)
    for t, (px, py), (tx, ty) in labels:
        ax.annotate(t, (px, py), xytext=(tx, ty), textcoords="data", fontsize=8, color=INK, zorder=9,
                    ha="center", va="center",
                    arrowprops=dict(arrowstyle="-", color="#4b5864", lw=0.7, shrinkA=0, shrinkB=0),
                    bbox=dict(fc="white", ec="#c9d0d6", pad=2.2, alpha=0.95))
    ax.set_xlim(*yr); ax.set_ylim(*zr); ax.set_aspect("equal")
    ax.grid(True, color="#e3e6ea", lw=0.5, zorder=0)
    ax.set_xlabel("Y (mm): 0 = rear panel inner face, 100 = front panel inner face", fontsize=8, color=MUTED)
    ax.set_ylabel("Z (mm) above the base underside", fontsize=8, color=MUTED)
    ax.set_title(title, fontsize=10, color=INK, loc="left")
    if note:
        ax.text(0.01, 0.015, note, transform=ax.transAxes, fontsize=7.5, color=MUTED, va="bottom", zorder=9,
                bbox=dict(fc="white", ec="none", pad=1.5, alpha=0.9))
    ax.tick_params(labelsize=7)
    save(fig, name)


def card_enclosure():
    prims = board_prims()
    F, R = GE.front, GE.rear
    zp, yf = Z_PCB, 100.0
    pt = PANEL_T
    STEEL, BRASS = (0.72, 0.74, 0.77), (0.80, 0.68, 0.38)
    common_f = [("front panel", (yf + pt / 2, 27.5), (yf + 9, 32.2)), ("lid", (84, Z_LID + 1.2), (80, 32.2)),
                ("base", (84, 1.5), (80, 4.5)), ("PCB", (84, zp - 0.8), (80, zp - 3.6))]
    common_r = [("rear panel", (-pt / 2, 27.5), (-10, 32.2)), ("lid", (12, Z_LID + 1.2), (16, 32.2)),
                ("base", (12, 1.5), (16, 4.5)), ("PCB", (12, zp - 0.8), (16, zp - 3.6))]
    note = "Solid: printed parts, PCB and parts at datasheet dimensions.  Dashed red: a typical mating plug or knob."

    # --- J2 (BNC)
    x = F["bnc"][0][0]; z = zp + GE.H_BNC
    section_x(x, "J2 (TTL IN) BNC: flange inside the panel, nut and washer outside", (72, 124), (0, 34), prims,
              "sec_front_bnc",
              common_f + [("BNC body", (94, zp + 6), (86, zp + 3)),
                          ("Ø14 flange", (99.5, z + 6.5), (93, 28.4)),
                          ("M12 thread through Ø12.4 hole", (101.2, z + 6.0), (110, 31.3)),
                          ("washer + nut", (104, z - 7.0), (106, 5.6)),
                          ("bayonet", (114, z - 4.8), (113, 8.0)),
                          ("cable plug (typical)", (118, z + 7.5), (118, 31.3))],
              extras=[("cyl", STEEL, ycyl(x, yf + pt, yf + pt + 0.5, z, 6.9)),
                      ("cyl", BRASS, ycyl(x, yf + pt + 0.5, yf + pt + 2.5, z, 7.6))],
              ghosts=[("cyl", ycyl(x, yf + pt + 9.5, yf + pt + 30, z, 7.5))], note=note)
    # --- RV1 (pot)
    x = F["pot"][0][0]; z = zp + GE.H_POT
    section_x(x, "RV1 (PULSE) pot: M9 bushing through Ø9.5, nut in the 0.5 mm spot face", (72, 124), (0, 34), prims,
              "sec_front_pot",
              common_f + [("pot body", (95, zp + 5), (86, zp + 3)),
                          ("M9 bushing", (103.5, z + 4.5), (105, 28.4)),
                          ("6 mm shaft", (112, z + 3), (116, 25.5)),
                          ("washer + nut", (103.3, z - 6.5), (109, 6.2)),
                          ("anti-rotation lug notch (through)", (yf + pt / 2, zp + 0.1), (90, 8.4)),
                          ("knob (typical)", (113, z - 7.5), (119, 12.5))],
              extras=[("cyl", STEEL, ycyl(x, yf + pt - 0.5, yf + pt, z, 5.6)),
                      ("cyl", BRASS, ycyl(x, yf + pt, yf + pt + 2.0, z, 6.5))],
              ghosts=[("cyl", ycyl(x, yf + 5.5, yf + 16, z, 7.5))], note=note)
    # --- SW1 (toggle)
    x = F["toggle"][0][0]; z = zp + GE.H_TOGGLE
    section_x(x, "SW1 (ENABLE) toggle: bushing through a Ø7.4 hole, lever up = ENABLE", (72, 124), (0, 34), prims,
              "sec_front_toggle",
              common_f + [("switch body", (92, zp + 9), (86, zp + 14.5)),
                          ("bracket, soldered to the PCB", (98.3, zp - 0.5), (90, 6.0)),
                          ("¼\" bushing (no nut)", (103, z - 3.1), (108, 8.4)),
                          ("lever, up = ENABLE", (107.5, z + 1.6), (113, 22.5)),
                          ("terminals 1 (low) - 2 - 3 (high)\nbend down into the PCB", (80.6, zp + 10.9), (79.5, 27.0))],
              note=note)
    # --- D3 (LED)
    x = F["led"][0][0]
    section_x(x, "D3 (POWER) side-view LED behind its 3.2 × 1.9 mm window", (72, 124), (0, 34), prims,
              "sec_front_led",
              common_f + [("LED, lens facing the window", (99.6, zp + 0.5), (93, zp + 6)),
                          ("window", (yf + pt / 2, zp + 0.65), (110, zp + 6)),
                          ("standoff + M3 screw", (85.5, 5), (92, 5.2))],
              note=note)
    # --- J5 (DE-9)
    x = R["dsub"][0]; z = zp + GE.H_DSUB
    section_x(x, "J5 (LD OUT) DE-9 centre: flange in its recess; a mating plug's shell slides over the socket shell",
              (-30, 22), (0, 34), prims, "sec_rear_dsub",
              common_r + [("socket body", (6, zp + 6), (10, zp + 15.5)),
                          ("steel flange in 0.6 mm recess", (0, zp + 11.5), (-9, 29.0)),
                          ("socket shell", (-4, z - 3.0), (-6, 6.6)),
                          ("plug (typical): its flange stops ~6 mm out", (-16, z + 6.6), (-14, 25.6))],
              ghosts=[("cyl", ycyl(x, -0.4, -6.5, z, 4.75)),
                      ("box", (x - 15.5, -7.5, z - 6.25, x + 15.5, -6.5, z + 6.25)),
                      ("box", (x - 16, -30, z - 7.8, x + 16, -7.5, z + 7.8))], note=note)
    section_x(x + 12.495, "J5 jack post: 4-40 hex post through a Ø6.3 hole; the plug's jack screw threads into it",
              (-30, 22), (0, 34), prims, "sec_rear_dsub_post",
              common_r + [("hex jack post", (-3, z + 2.9), (-6, 24.5)),
                          ("jack screw (typical)", (-14, z), (-18, 8.0))],
              ghosts=[("cyl", ycyl(x + 12.495, -2.0, -30, z, 1.42))], note=note)
    # --- J6 (3.5 mm)
    x = R["jack35"][0]; z = zp + GE.H_JACK35
    section_x(x, "J6 (INTERLOCK) 3.5 mm jack: plug through an Ø8.6 hole with an Ø12 counterbore", (-30, 22), (0, 34),
              prims, "sec_rear_jack35",
              common_r + [("jack", (8, zp + 4), (10, zp + 9.5)),
                          ("plug (typical): Ø3.5 into the jack, body Ø6", (-12, z + 3), (-12, 22.0))],
              ghosts=[("cyl", ycyl(x, 0, 14, z, 1.75)), ("cyl", ycyl(x, 0, -20, z, 3.0))], note=note)
    # --- J1 (DC)
    x = R["dcjack"][0]; z = zp + GE.H_DCJACK
    section_x(x, "J1 (9V DC) jack: plug axis 7.0 mm above the PCB, Ø11 hole on the same axis", (-30, 22), (0, 34),
              prims, "sec_rear_dc",
              common_r + [("jack (axis 4.0 below its top)", (10, zp + 9), (11, 25.8)),
                          ("plug (typical): Ø5.5 barrel, body Ø10", (-12, z + 5), (-12, 26.5))],
              ghosts=[("cyl", ycyl(x, 0, 9.5, z, 2.75)), ("cyl", ycyl(x, 0, -22, z, 5.0))], note=note)
    panel_face("front", prims)
    panel_face("rear", prims)
    lid_clearance(prims)


def panel_face(which, prims):
    """Panel as seen from outside: through-holes (mid-plane cut), engraving and spot
    faces (cut 0.3 mm under the outer face), and the connectors behind it."""
    front = which == "front"
    mid = 100 + PANEL_T / 2 if front else -PANEL_T / 2
    face = 100 + PANEL_T - 0.3 if front else -PANEL_T + 0.3
    mod = "front_panel" if front else "rear_panel"
    fig, ax = plt.subplots(figsize=(13, 4.6))
    # outside view: from the front, +X points to the viewer's left
    # mid-plane cut (light) under the cut just below the outer face (dark): engraving and
    # recesses show light, through-holes white
    draw_scad(ax, scad_section(mod, "y", mid), "#9fc0e0", z=1, flipx=front)
    draw_scad(ax, scad_section(mod, "y", face), PART_COL["panel"], z=2, flipx=front)
    # connectors: everything that reaches within 1 mm of the panel inner face
    for ref, kind, rgb, g in prims:
        if kind == "box":
            near = g[4] >= 99.0 if front else g[1] <= 1.0
        elif kind == "cyl":
            ys = (g[0][1], g[1][1])
            near = max(ys) >= 99.0 if front else min(ys) <= 1.0
        else:
            near = (g[5] >= 99.0) if front else (g[4] <= 1.0)
        if not near:
            continue
        for sh in prim_projection(kind, g):
            draw_shape(ax, sh, "none", "#c3c9d1", lw=0.8, alpha=0.9, z=4, flipx=front)
    ax.set_aspect("equal")
    ax.autoscale_view()
    xl = ax.get_xlim()
    ax.set_xlim(xl[0] - 2, xl[1] + 2)
    ax.axhline(Z_PCB, color=PART_COL["pcb"], lw=0.8, ls="--", zorder=5)
    ax.text(ax.get_xlim()[0] + 1, Z_PCB + 0.3, "PCB top", fontsize=7, color=PART_COL["pcb"], zorder=5)
    ax.grid(True, color="#e3e6ea", lw=0.5, zorder=0)
    ax.set_title(f"{which.capitalize()} panel seen from outside (light blue = engraving and recesses, white = through; "
                 "grey outlines = parts behind)", fontsize=10, color=INK, loc="left")
    ax.set_xlabel("mm (enclosure X, increasing to the " + ("left" if front else "right") + " in this view)",
                  fontsize=8, color=MUTED)
    if front:
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{-v:g}"))
    ax.tick_params(labelsize=7)
    save(fig, f"panel_{which}")


def lid_clearance(prims):
    fig, ax = plt.subplots(figsize=(13, 4.2))
    ax.add_patch(Rectangle((0, Z_PCB - 1.6), 160, 1.6, fc=PART_COL["pcb"], ec="none", zorder=1))
    tops = {}
    for ref, kind, rgb, g in prims:
        for sh in prim_projection(kind, g):
            draw_shape(ax, sh, hexcol(rgb), "#333", lw=0.4, alpha=0.55, z=2)
            top = sh[4] if sh[0] == "rect" else (sh[2] + sh[3]) if sh[0] == "circle" else max(p[1] for p in sh[1])
            tops[ref] = max(tops.get(ref, 0), top)
    ax.axhline(Z_LID, color=ACCENT, lw=1.2, zorder=5)
    ax.text(1, Z_LID + 0.4, f"lid underside (PCB top + 19.0 mm)", color=ACCENT, fontsize=8, zorder=6)
    groups = {}
    for ref, top in tops.items():
        groups.setdefault(round(top - Z_PCB, 1), []).append(ref)
    for k, (h, refs) in enumerate(sorted(groups.items(), reverse=True)[:5]):
        refs.sort()
        xs = [GE.X(mm(fp_by_ref(r).GetPosition())[0]) for r in refs]
        x = sum(xs) / len(xs)
        ax.annotate(f"{'/'.join(refs)}: {h:.1f} mm, gap {Z_LID - Z_PCB - h:.1f} mm", (x, Z_PCB + h),
                    xytext=(0, -14 - 15 * (k % 3)), textcoords="offset points", ha="center", fontsize=7.5,
                    color=INK, zorder=7, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.6),
                    bbox=dict(fc="white", ec="#ccd", pad=1.5, alpha=0.95))
    ax.set_xlim(-12, 172); ax.set_ylim(Z_PCB - 3, Z_LID + 3); ax.set_aspect("equal")
    ax.grid(True, color="#e3e6ea", lw=0.5, zorder=0)
    ax.set_title("Heights of all parts (seen from the front, simplified bodies) against the lid", fontsize=10,
                 color=INK, loc="left")
    ax.tick_params(labelsize=7)
    save(fig, "lid_clearance")


# ------------------------------------------------------------------ diagrams
def dsub_pins(ax, cx, cy, mirror, s=1.0, hl=None, sockets=False):
    """DE-9 face: wide row (1-5) on top.  mirror=False: pin 1 at the top left
    (plug front / socket rear); mirror=True: pin 1 at the top right."""
    hl = hl or {}
    w_top, w_bot, h, r = 16.33 * s, 13.54 * s, 7.9 * s, 1.2 * s
    ax.add_patch(Polygon([(cx - w_top / 2 - 1.2 * s, cy + h / 2 + 1.0 * s), (cx + w_top / 2 + 1.2 * s, cy + h / 2 + 1.0 * s),
                          (cx + w_bot / 2 + 1.2 * s, cy - h / 2 - 1.0 * s), (cx - w_bot / 2 - 1.2 * s, cy - h / 2 - 1.0 * s)],
                         closed=True, fc="#d5d8dc", ec="#555", lw=1.0, zorder=1))
    pos = {}
    for k in range(5):
        pos[k + 1] = (k - 2) * 2.77 * s
    for k in range(4):
        pos[k + 6] = (k - 1.5) * 2.77 * s
    for n, dx in pos.items():
        x = cx + (-dx if mirror else dx)
        y = cy + (1.42 * s if n <= 5 else -1.42 * s)
        col = hl.get(n, "white")
        ax.add_patch(Circle((x, y), 0.95 * s, fc=col, ec="#333", lw=0.8, zorder=3))
        ax.text(x, y, str(n), ha="center", va="center", fontsize=8 * s ** 0.5, weight="bold",
                color="white" if col not in ("white", "#f1c40f") else INK, zorder=4)
    return {n: (cx + (-dx if mirror else dx), cy + (1.42 * s if n <= 5 else -1.42 * s)) for n, dx in pos.items()}


def card_diagrams():
    # --- diode cable: DE-9 male plug, solder side
    fig, ax = plt.subplots(figsize=(10, 5.6))
    P = dsub_pins(ax, 0, 0, mirror=True, s=2.2, hl={8: "#c0392b", 3: "#222222", 1: "#f1c40f", 5: "#f1c40f"})
    top, bot = 7.6, -7.6
    ax.plot([P[1][0], P[1][0], P[5][0], P[5][0]], [P[1][1] + 2.1, top + 2.0, top + 2.0, P[5][1] + 2.1],
            color="#f39c12", lw=2.5, zorder=5, solid_capstyle="round")
    ax.text(P[5][0] - 1.2, top + 2.0, "wire link 1-5\n(cable interlock)", ha="right", va="center", fontsize=8.5,
            color="#b9770e")
    ax.plot([P[3][0], P[3][0], 40], [P[3][1] + 2.1, top + 5.0, top + 5.0], color="#222", lw=3, zorder=6)
    ax.plot([P[8][0], P[8][0], 40], [P[8][1] - 2.1, bot - 2.5, bot - 2.5], color="#c0392b", lw=3, zorder=6)
    ax.add_patch(Rectangle((40, bot - 5.0), 9, top + 12.5 - bot, fc="#c58b4b", ec="#7a5225", lw=1, zorder=2))
    ax.add_patch(Circle((49, (top + bot) / 2 + 1.2), 2.4, fc="#9b59b6", ec="#5b2c6f", lw=1, zorder=3))
    ax.text(44.5, bot - 5.8, "BDR-209 diode\n(copper module)", ha="center", va="top", fontsize=8.5, color=INK)
    ax.text(16, top + 5.6, "pin 3 -> diode cathode (-, black)", fontsize=9, color="#222", va="bottom")
    ax.text(16, bot - 3.1, "pin 8 -> diode anode (+, red)", fontsize=9, color="#c0392b", va="top")
    ax.text(0, bot - 6.8, "DE-9 MALE solder plug seen from the SOLDER-CUP side (rear):\n"
            "wide row on top, 5 4 3 2 1 from left to right", ha="center", va="top", fontsize=9.5, color=INK)
    ax.text(-30, bot - 13.0, "cable screen (if any): to the metal hood at this end only; keep the pair twisted",
            fontsize=8.5, color=MUTED)
    ax.set_xlim(-31, 55); ax.set_ylim(bot - 14.5, top + 8.5); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("Diode cable (you make this): DE-9 male solder plug -> laser diode leads", fontsize=11, color=INK,
                 loc="left")
    save(fig, "cable_de9")

    # --- J5 as seen from the rear of the box (female, pin 1 top right)
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    dsub_pins(ax, 0, 0, mirror=True, s=2.0, hl={8: "#c0392b", 3: "#222222", 1: "#f1c40f", 5: "#f1c40f"})
    ax.text(0, -12.5, "J5 'LD OUT' socket seen from behind the box\n8 = anode (+), 3 = cathode / ground, 1 & 5 = interlock",
            ha="center", va="top", fontsize=8.5, color=INK)
    ax.set_xlim(-20, 20); ax.set_ylim(-17, 10); ax.set_aspect("equal"); ax.axis("off")
    save(fig, "j5_face")

    # --- toggle: lever direction and contacts (geometry from the Dailywell M7 drawing)
    fig, ax = plt.subplots(figsize=(10, 4.8))
    z = GE.H_TOGGLE
    ax.add_patch(Rectangle((-8, -1.6), 40, 1.6, fc=PART_COL["pcb"], ec="none"))
    ax.text(31.5, -0.8, "PCB", color="white", fontsize=8, ha="right", va="center")
    ax.add_patch(Rectangle((-4.5, -1.6), 2.5, 17.5, fc=PART_COL["panel"], ec="none", alpha=0.85, zorder=3))
    ax.text(-3.25, 16.2, "front\npanel", ha="center", va="bottom", fontsize=8, color=PART_COL["panel"])
    ax.add_patch(Rectangle((-0.76, -2.6), 0.76, 15.3, fc="#bdc3c7", ec="#7f8c8d"))          # bracket and legs
    ax.add_patch(Rectangle((0, 0), 10.1, 12.7, fc="#c0392b", ec="#7b241c"))
    ax.add_patch(Rectangle((-7.31, z - 3.11), 7.31, 6.22, fc="#bdc3c7", ec="#7f8c8d", zorder=4))
    a = math.radians(18)
    for sgn, ls, al in ((1, "-", 1.0), (-1, "--", 0.5)):
        ax.plot([-6.5, -7.31 - 6.46], [z, z + sgn * 6.46 * math.tan(a) * 1.0], color="#7f8c8d", lw=4.5,
                ls=ls, alpha=al, solid_capstyle="round", zorder=5)
    ax.text(-20.5, z + 4.6, "lever UP = ENABLE", fontsize=9.5, color=INK, weight="bold", ha="left")
    ax.text(-20.5, z - 5.4, "lever down = off", fontsize=9, color=MUTED, ha="left")
    for n, x, h in ((1, 12.70, 2.3), (2, 16.51, 6.5), (3, 20.32, 10.9)):
        ax.plot([10.1, x, x], [h, h, -3.18], color="#7f8c8d", lw=2.2)
        ax.text(x + 0.6, h + 0.5, str(n), fontsize=10, weight="bold", color=INK)
    ax.text(22.5, 12.0, "terminals leave the back of the body,\n1 lowest and 3 highest, and bend down\n"
            "at 12.70, 16.51 and 20.32 mm (pads 1, 2, 3)", fontsize=8.5, color=INK, va="top")
    ax.text(22.5, 4.4, "lever up: 2-1 closed -> EN_SW to GND -> enabled\nlever down: 2-3 closed (3 unused) -> off",
            fontsize=8.5, color=INK, va="top")
    ax.set_xlim(-21, 46); ax.set_ylim(-4, 19.5); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("SW1 toggle seen from the side (panel on the left): which way is ENABLE", fontsize=11, color=INK, loc="left")
    save(fig, "toggle_function")

    # --- pot direction
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw=dict(width_ratios=[1, 1.25]))
    ax = axs[0]
    ax.add_patch(Circle((0, 0), 8.5, fc="#c9d6e3", ec="none"))
    ax.add_patch(Circle((0, 0), 6.5, fc="#2d3436", ec="#111"))
    th0, th1 = math.radians(240), math.radians(-60)          # 300 degree travel, CCW end at lower left
    ax.plot([0, 5.5 * math.cos(th0)], [0, 5.5 * math.sin(th0)], color="white", lw=2.5)
    arc = np.linspace(th0, th1, 60)
    ax.plot(10.5 * np.cos(arc), 10.5 * np.sin(arc), color=ACCENT, lw=1.6)
    ax.annotate("", xy=(10.5 * math.cos(th1), 10.5 * math.sin(th1)),
                xytext=(10.5 * math.cos(th1 + 0.12), 10.5 * math.sin(th1 + 0.12)),
                arrowprops=dict(arrowstyle="-|>", color=ACCENT, lw=1.6))
    ax.text(-7.0, -8.9, "0", fontsize=11, ha="center", color=INK, weight="bold")
    ax.text(8.0, -8.9, "MAX", fontsize=11, ha="center", color=INK, weight="bold")
    ax.text(0, 12.2, "clockwise = more current", ha="center", fontsize=9.5, color=ACCENT)
    ax.set_xlim(-14, 14); ax.set_ylim(-12, 14); ax.set_aspect("equal"); ax.axis("off")
    ax.set_title("PULSE / IDLE knob, front view", fontsize=10, color=INK, loc="left")
    ax = axs[1]
    ax.plot([0, 0], [4, -4], color=INK, lw=1.5)
    ax.add_patch(Rectangle((-0.6, -2.5), 1.2, 5, fc="white", ec=INK, lw=1.5))
    ax.annotate("", xy=(0.65, 0.6), xytext=(3.5, 0.6), arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.3))
    ax.text(0, 4.3, "3  VFS (full-scale setpoint) / IDLE_TOP", ha="center", va="bottom", fontsize=8.5, color=INK)
    ax.text(0, -4.3, "1  GND / IDLE_BOT", ha="center", va="top", fontsize=8.5, color=INK)
    ax.text(3.7, 0.6, "2  wiper -> VP_W / VI_W", ha="left", va="center", fontsize=8.5, color=INK)
    ax.text(-6.5, -7.0, "Alps RK09L: turning the shaft clockwise (seen from the\nshaft end) moves the wiper from terminal 1 towards 3",
            fontsize=8.5, color=MUTED, va="top")
    ax.set_xlim(-7, 11); ax.set_ylim(-9.5, 6.5); ax.axis("off")
    ax.set_title("RV1 / RV2 wiring", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    save(fig, "pot_direction")


def card_schematic():
    pdf = os.path.join(HW, "fab", design.PROJECT + "_schematic.pdf")
    tmp = tempfile.mkdtemp()
    subprocess.run(["pdftoppm", "-r", "80", "-png", "-singlefile", pdf, os.path.join(tmp, "sch")], check=True)
    import shutil
    shutil.copy(os.path.join(tmp, "sch.png"), os.path.join(OUT, "schematic.png"))
    print("   schematic.png")


def card_3d():
    pcb = PCB
    for name, rot, zoom, pan, persp in (("board_3d_top", "0,0,0", 1.4, "", False),
                                        ("board_3d_front", "-58,0,180", 1.45, "", False),
                                        ("board_3d_rear", "-58,0,0", 1.45, "", False)):
        cmd = ["kicad-cli", "pcb", "render", "-o", os.path.join(OUT, name + ".png"), "--width", "1800",
               "--height", "1100", "--side", "top", "--background", "opaque", "--quality", "high",
               "--rotate", rot, "--zoom", str(zoom)]
        if pan:
            cmd += ["--pan", pan]
        if persp:
            cmd += ["--perspective"]
        subprocess.run(cmd + [pcb], check=True, capture_output=True)
        print("  ", name + ".png")


# ------------------------------------------------------------------ JLCPCB preview markers
JLC_PINK = "#e600e6"


def jlc_marks(fp):
    """Where JLCPCB's placement preview draws its pink markers on a correctly placed part:
    a dot on pin 1 (ICs, transistors, relay, SOT-23 diodes), '+' on the anode and '-' on
    the cathode (diodes, LEDs), '+' and '-' on the electrolytics."""
    kind = polarity_kind(fp)
    if not kind:
        return []
    pads = {p.GetNumber(): mm(p.GetPosition()) for p in fp.Pads() if p.GetNumber()}
    if kind == "1":
        return [("dot", pads["1"])]
    if kind == "+":                                   # electrolytic: pad 1 = +
        return [("+", pads["1"]), ("-", pads["2"])]
    return [("+", pads["2"]), ("-", pads["1"])]       # diode / LED: pad 1 = cathode


def draw_jlc_marks(ax, fp, size=0.55):
    for kind, (x, y) in jlc_marks(fp):
        if kind == "dot":
            ax.add_patch(Circle((x, y), size * 0.55, fc=JLC_PINK, ec="white", lw=0.6, zorder=8))
        elif kind == "+":
            ax.plot([x - size, x + size], [y, y], color=JLC_PINK, lw=2.6, zorder=8, solid_capstyle="butt")
            ax.plot([x, x], [y - size, y + size], color=JLC_PINK, lw=2.6, zorder=8, solid_capstyle="butt")
        else:
            ax.plot([x - size, x + size], [y, y], color=JLC_PINK, lw=2.6, zorder=8, solid_capstyle="butt")


def draw_jlc_board(ax, box):
    draw_outline(ax)
    b = board()
    x0, y0, x1, y1 = box
    for fp in b.GetFootprints():
        fx, fy = mm(fp.GetPosition())
        if not (x0 - 15 < fx < x1 + 15 and y0 - 15 < fy < y1 + 15):
            continue
        kind = polarity_kind(fp)
        lines, _ = item_lines(fp.GraphicalItems(), pcbnew.F_SilkS)
        for ln in lines:
            ax.plot(*zip(*ln), color="#9aa3ad", lw=0.6, zorder=1)
        lines, _ = item_lines(fp.GraphicalItems(), pcbnew.F_Fab)
        for ln in lines:
            ax.plot(*zip(*ln), color=INK if kind else "#b7bec7", lw=0.9 if kind else 0.5, zorder=2)
        for p in fp.Pads():
            if not (p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.B_Cu)):
                continue
            for pts in pad_polys(p, pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu):
                ax.add_patch(Polygon(pts, closed=True, fc="#d9b56a" if kind else "#e9dcc0", ec="#7a5a12" if kind else "none",
                                     lw=0.3, zorder=3))
            if p.HasHole():
                d = p.GetDrillSize()
                if d.x == d.y:
                    ax.add_patch(Circle(mm(p.GetPosition()), d.x / 2e6, fc="white", ec="none", zorder=4))
        if kind:
            draw_jlc_marks(ax, fp)
            cx, cy = pad_centre(fp)
            bbx = fp.GetBoundingBox(False, False)
            ax.text(cx, bbx.GetBottom() / 1e6 + 0.6, fp.GetReference(), color="#1f5fa8", fontsize=8, weight="bold",
                    ha="center", va="top", zorder=9, bbox=dict(fc="white", ec="none", pad=0.4, alpha=0.8))


def card_jlc_markers():
    """Reference for JLCPCB's placement preview: where each pink marker belongs."""
    full = (96, 96, 264, 204)
    fig, ax, _ = board_axes(full, 12)
    draw_jlc_board(ax, full)
    ax.text(180, 97.6, "JLCPCB 2D view, Top: pink dot = pin 1;  + / - = anode / cathode (diodes, LEDs) or + / - terminal (C1, C2)",
            ha="center", va="center", fontsize=9.5, color=INK, zorder=9)
    save(fig, "jlc_markers_overview", tight=False)
    for i, (name, box) in enumerate(QUADS):
        fig, ax, _ = board_axes(box, 11)
        draw_jlc_board(ax, box)
        ax.text(box[0] + 1, box[1] + 1.5, f"{i + 1}  {name}: where JLCPCB's pink markers belong", fontsize=10,
                color=INK, va="top", zorder=9, bbox=dict(fc="white", ec="none", alpha=0.85))
        save(fig, f"jlc_markers_{i + 1}", tight=False)

if __name__ == "__main__":
    names = sys.argv[1:]
    for fn in [card_footprints, card_smd_pinouts, card_polarity, card_layout, card_enclosure, card_diagrams,
               card_schematic, card_3d, card_jlc_markers]:
        if not names or fn.__name__ in names:
            print(fn.__name__)
            fn()
