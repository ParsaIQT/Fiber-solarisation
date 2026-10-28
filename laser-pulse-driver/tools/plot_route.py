#!/usr/bin/env python3
"""Plot tracks, vias and pads of the board with matplotlib (zones as outlines
only) - easier to review routing than a filled Gerber view.

  python3 plot_route.py OUT.png [x0 y0 x1 y1] [--nets]
"""
import os, sys
import pcbnew
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Circle

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.normpath(os.path.join(HERE, "..", "hardware", "ld405-driver.kicad_pcb"))
COL = {pcbnew.F_Cu: "#d03030", pcbnew.B_Cu: "#3060d0"}


def poly_xy(sps):
    out = []
    for k in range(sps.OutlineCount()):
        ol = sps.Outline(k)
        out.append([(ol.CPoint(i).x / 1e6, ol.CPoint(i).y / 1e6) for i in range(ol.PointCount())])
    return out


def main(out, box=None, nets=False, pcb=PCB):
    b = pcbnew.LoadBoard(pcb)
    x0, y0, x1, y1 = box or (99, 99, 261, 201)
    scale = 1600 / max(x1 - x0, y1 - y0)
    fig = plt.figure(figsize=((x1 - x0) * scale / 100, (y1 - y0) * scale / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(x0, x1); ax.set_ylim(y1, y0); ax.set_aspect("equal"); ax.axis("off")
    for z in b.Zones():
        for pts in poly_xy(z.Outline()):
            ax.add_patch(Polygon(pts, closed=True, fill=False, ec="#999999", lw=0.5, ls="--"))
    for fp in b.GetFootprints():
        for p in fp.Pads():
            for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
                if not p.IsOnLayer(layer):
                    continue
                ps = pcbnew.SHAPE_POLY_SET()
                p.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(0.01), pcbnew.ERROR_INSIDE)
                for pts in poly_xy(ps):
                    ax.add_patch(Polygon(pts, closed=True, fc="#c8a050" if layer == pcbnew.F_Cu else "#a0a0c0",
                                         ec="none", alpha=0.9, zorder=1))
                break
        pos = fp.GetPosition()
        ax.text(pos.x / 1e6, pos.y / 1e6, fp.GetReference(), fontsize=6 if box else 3.5,
                ha="center", va="center", color="black", zorder=5)
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            c = t.GetPosition()
            ax.add_patch(Circle((c.x / 1e6, c.y / 1e6), t.GetWidth(pcbnew.F_Cu) / 2e6, fc="#40a040", ec="none", zorder=4))
            continue
        s, e = t.GetStart(), t.GetEnd()
        w = t.GetWidth() / 1e6
        ax.plot([s.x / 1e6, e.x / 1e6], [s.y / 1e6, e.y / 1e6], color=COL.get(t.GetLayer(), "k"),
                lw=w * scale * 0.72, solid_capstyle="round", alpha=0.75, zorder=3)
        if nets:
            ax.text((s.x + e.x) / 2e6, (s.y + e.y) / 2e6, t.GetNetname(), fontsize=4, color="#004400", zorder=6)
    fig.savefig(out)


if __name__ == "__main__":
    a = sys.argv[1:]
    nets = "--nets" in a
    a = [x for x in a if x != "--nets"]
    box = tuple(float(v) for v in a[1:5]) if len(a) >= 5 else None
    main(a[0], box, nets)
