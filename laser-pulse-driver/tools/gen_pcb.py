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
import design, placement, symlib
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
    ds.m_TentViasFront = True
    ds.m_TentViasBack = True
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
        names = {q["num"]: q["name"] for q in symlib.pins(p["lib"])}
        for pad in fp.Pads():
            num = pad.GetNumber()
            if num not in p["pins"]:
                continue
            if p["pins"][num] is not None:
                pad.SetNet(net(p["pins"][num]))
            else:
                # same name KiCad gives a no-connect pin, so the parity check agrees
                nm = names.get(num, "~")
                tag = "" if nm in ("~", "", num) else "-" + nm
                pad.SetNet(net(f"unconnected-({ref}{tag}-Pad{num})"))
        board.Add(fp)
        fps[ref] = fp
    return fps, netinfo


def tidy_silk(board):
    import silk
    b = placement.BOARD
    box = (b["x0"], b["y0"], b["x1"], b["y1"])
    silk.clip_silk(board, *box)
    silk.trim_silk_at_pads(board)
    hidden = silk.place_refs(board, *box)
    for s, x, y, size in placement.SILK_TEXT:
        silk.add_text(board, s, x, y, size)
    if hidden:
        print("references on fab layer only:", " ".join(sorted(hidden)))


def add_zones(board):
    """Inner planes (In1 GND, In2 +5V), GND pours on both outer layers and the
    LD_OUT heat spreader (filled later by fill_zones)."""
    b = placement.BOARD
    rect = [(b["x0"], b["y0"]), (b["x1"], b["y0"]), (b["x1"], b["y1"]), (b["x0"], b["y1"])]

    def zone(netname, layer, pts, prio, conn, name):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(board.FindNet(netname))
        z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(MM(x), MM(y))
        z.SetLocalClearance(MM(0.3))
        z.SetMinThickness(MM(0.25))
        z.SetPadConnection(conn)
        z.SetThermalReliefGap(MM(0.3))
        z.SetThermalReliefSpokeWidth(MM(0.5))
        z.SetAssignedPriority(prio)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        z.SetHatchStyle(pcbnew.ZONE_BORDER_DISPLAY_STYLE_DIAGONAL_EDGE)
        board.Add(z)
        return z

    zone("GND", pcbnew.In1_Cu, rect, 0, pcbnew.ZONE_CONNECTION_THERMAL, "GND plane")
    zone("+5V", pcbnew.In2_Cu, rect, 0, pcbnew.ZONE_CONNECTION_THERMAL, "+5V plane")
    zone("GND", pcbnew.F_Cu, rect, 0, pcbnew.ZONE_CONNECTION_THERMAL, "GND top")
    zone("GND", pcbnew.B_Cu, rect, 0, pcbnew.ZONE_CONNECTION_THERMAL, "GND bottom")
    for net, layers, poly in placement.ZONES:
        for ln in layers:
            zone(net, pcbnew.F_Cu if ln == "F.Cu" else pcbnew.B_Cu, poly, 2,
                 pcbnew.ZONE_CONNECTION_FULL, net + " spreader")


def fill_zones(path):
    """Fill all zones.  The filler needs a board loaded from disk (with its
    project and DRC engine), so this reloads the saved file."""
    board = pcbnew.LoadBoard(path)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(path)
    return board


def route(board):
    import router, time
    b = placement.BOARD
    t0 = time.time()
    r = router.Router(board, b["x0"], b["y0"], b["x1"], b["y1"], b["corner_r"], zones=placement.ZONES)
    failed = r.run(thermal_vias=placement.THERMAL_VIAS)
    nt, nv = r.emit()
    for line in r.log:
        print("  ", line)
    print(f"routed in {time.time() - t0:.0f} s: {nt} track segments, {nv} vias, {len(failed)} failed")
    return r


def project_settings():
    """Settings pcbnew does not expose: written into the .kicad_pro after the
    board has been saved (saving rewrites the project file)."""
    import json
    pro = os.path.join(HW, design.PROJECT + ".kicad_pro")
    d = json.load(open(pro))
    sev = d["board"]["design_settings"]["rule_severities"]
    # reference fields and silk are re-placed/trimmed on purpose (silk.py), so
    # every footprint differs from its library copy
    sev["lib_footprint_mismatch"] = "ignore"
    json.dump(d, open(pro, "w"), indent=2)


def main(do_route=False):
    board = pcbnew.CreateEmptyBoard()
    setup_board(board)
    outline(board)
    fps, nets = place_parts(board)
    tidy_silk(board)
    if do_route:
        route(board)
        add_zones(board)
    board.Save(OUT)
    if do_route:
        board = fill_zones(OUT)
    project_settings()
    print("saved", OUT, "footprints:", len(fps), "nets:", len(nets))
    return board


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
            sa = pcbnew.SHAPE_POLY_SET(a); sa.BooleanIntersection(b)
            if sa.OutlineCount() and sa.Area() > MM(0.05) * MM(0.05):
                bad.append((items[i][0], items[j][0], pcbnew.ToMM(1) * pcbnew.ToMM(1) * sa.Area()))
    return bad


if __name__ == "__main__":
    main(do_route="--route" in sys.argv)
