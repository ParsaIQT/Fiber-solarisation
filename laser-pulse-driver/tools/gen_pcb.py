#!/usr/bin/env python3
"""Build ../hardware/ld405-driver.kicad_pcb from design.py + placement.py.

Steps: create a 4-layer board, load and place footprints, assign nets, link
footprints to schematic symbols (deterministic UUIDs shared with gen_sch.py),
draw the outline, add planes, then (optionally) route with router.py and fill
zones.  Usage:  python3 gen_pcb.py [--route]
"""
import os, sys, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import design, placement
from gen_sch import U as SCH_U

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.normpath(os.path.join(HERE, "..", "hardware"))
OUT = os.path.join(HW, design.PROJECT + ".kicad_pcb")
FPDIR = "/usr/share/kicad/footprints"
LOCAL = os.path.join(HW, "lib", "ld405.pretty")
MM = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def load_fp(fpid):
    lib, name = fpid.split(":")
    path = LOCAL if lib == "ld405" else os.path.join(FPDIR, lib + ".pretty")
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise SystemExit("cannot load " + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def setup_board(board):
    ds = board.GetDesignSettings()
    board.SetCopperLayerCount(4)
    ds.SetCopperLayerCount(4)
    ds.m_MinClearance = MM(0.15)
    ds.m_TrackMinWidth = MM(0.15)
    ds.m_ViasMinSize = MM(0.6)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_CopperEdgeClearance = MM(0.3)
    ds.m_HoleClearance = MM(0.25)
    ds.m_HoleToHoleMin = MM(0.25)
    # inner layer names
    board.SetLayerName(pcbnew.In1_Cu, "In1.Cu")
    board.SetLayerName(pcbnew.In2_Cu, "In2.Cu")
    b = placement.BOARD
    tb = board.GetTitleBlock()
    tb.SetTitle(design.TITLE)
    tb.SetRevision(design.REV)
    tb.SetDate("2026-10-28")
    tb.SetCompany("Ion-trap lab photoionisation 405 nm driver")


def outline(board):
    b = placement.BOARD
    x0, y0, x1, y1, r = b["x0"], b["y0"], b["x1"], b["y1"], b["corner_r"]
    def seg(ax, ay, bx, by):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(V(ax, ay)); s.SetEnd(V(bx, by))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1))
        board.Add(s)
    def arc(cx, cy, sx, sy, ang):
        s = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        s.SetCenter(V(cx, cy)); s.SetStart(V(sx, sy))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T), True)
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(MM(0.1))
        board.Add(s)
    seg(x0 + r, y0, x1 - r, y0); seg(x1, y0 + r, x1, y1 - r)
    seg(x1 - r, y1, x0 + r, y1); seg(x0, y1 - r, x0, y0 + r)
    arc(x1 - r, y0 + r, x1 - r, y0, 90)
    arc(x1 - r, y1 - r, x1, y1 - r, 90)
    arc(x0 + r, y1 - r, x0 + r, y1, 90)
    arc(x0 + r, y0 + r, x0, y0 + r, 90)


def place_parts(board):
    netinfo = {}
    def net(name):
        if name not in netinfo:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            netinfo[name] = n
        return netinfo[name]
    net("GND")
    fps = {}
    for p in design.PARTS:
        if not p["fp"]:
            continue
        ref = p["ref"]
        if ref not in placement.P:
            raise SystemExit("no placement for " + ref)
        fp = load_fp(p["fp"])
        fp.SetReference(ref)
        fp.SetValue(p["value"])
        x, y, rot, side = placement.P[ref]
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        first_unit = min(p["units"].keys())
        fp.SetPath(pcbnew.KIID_PATH("/" + SCH_U("sym", ref, first_unit)))
        fp.SetSheetname("Root")
        fp.SetSheetfile(design.PROJECT + ".kicad_sch")
        for k in ("LCSC", "MPN"):
            v = p.get(k.lower(), "")
            if v:
                fp.SetField(k, v)
                f = fp.GetFieldByName(k)
                f.SetVisible(False)
                f.SetLayer(pcbnew.F_Fab)
        if p.get("nobom"):
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        for pad in fp.Pads():
            num = pad.GetNumber()
            if num in p["pins"] and p["pins"][num] is not None:
                pad.SetNet(net(p["pins"][num]))
        board.Add(fp)
        fps[ref] = fp
    return fps, netinfo


def main(route=False):
    board = pcbnew.CreateEmptyBoard()
    setup_board(board)
    outline(board)
    fps, nets = place_parts(board)
    if route:
        import router
        router.route_board(board, fps, nets)
    board.Save(OUT)
    print("saved", OUT, "footprints:", len(fps), "nets:", len(nets))
    return board


if __name__ == "__main__":
    main(route="--route" in sys.argv)


def check_overlaps(board):
    """Report courtyard overlaps (front side) without running full DRC."""
    items = []
    for fp in board.GetFootprints():
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount() == 0:
            continue
        items.append((fp.GetReference(), cy))
    bad = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i][1], items[j][1]
            if not a.BBox().Intersects(b.BBox()):
                continue
            inter = a.Collide(b.Outline(0), 0) if False else None
            sa = pcbnew.SHAPE_POLY_SET(a); sa.BooleanIntersection(b)
            if sa.OutlineCount() and sa.Area() > MM(0.05) * MM(0.05):
                bad.append((items[i][0], items[j][0], pcbnew.ToMM(1) * pcbnew.ToMM(1) * sa.Area()))
    return bad
