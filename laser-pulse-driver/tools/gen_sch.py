#!/usr/bin/env python3
"""Generate the KiCad 9 schematic (../hardware/ld405-driver.kicad_sch) from design.py.

Every symbol pin gets a short wire stub ending in a global label (or a GND
symbol), so connectivity is explicit and identical to design.py.  Symbols are
grouped by functional block with a heading and short notes for each block.
UUIDs are deterministic (uuid5 of the reference) so that the PCB generator
can link footprints to symbols for schematic-parity checks.
"""
import math, os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design
from sexp import dump, Sym, find, first
from symlib import get_symbol, pins as sym_pins

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "hardware", design.PROJECT + ".kicad_sch")
NS = uuid.UUID("6f1d0c2e-3b6a-4f53-9a51-2f8a7c0b4d11")
ROOT_UUID = str(uuid.uuid5(NS, "root-sheet"))
GRID = 1.27


def U(*key):
    return str(uuid.uuid5(NS, "/".join(str(k) for k in key)))


def snap(v):
    return round(round(v / GRID) * GRID, 4)


S = Sym


def font(size=1.27, bold=False):
    f = [S("font"), [S("size"), size, size]]
    if bold:
        f.append([S("bold"), S("yes")])
    return f


def eff(size=1.27, hide=False, justify=None, bold=False):
    e = [S("effects"), font(size, bold)]
    if justify:
        e.append([S("justify")] + [S(j) for j in justify])
    if hide:
        e.append([S("hide"), S("yes")])
    return e


BLOCKS = [
    # name, title, notes, origin (x, y), columns
    ("PWR", "1  POWER INPUT, 5 V AND 3.000 V REFERENCE",
     ["9 V / >=1.5 A desktop adapter (5.5/2.1 mm, centre +).",
      "Q1 = reverse-polarity protection, F1 = resettable fuse, D2 = TVS."], (20, 30), 6),
    ("SET", "2  SETPOINT, SOFT START AND TTL GATING (scale 4 V/A)",
     ["VFS = 2.40 V = 600 mA full scale (JP1 closed: 2.80 V = 700 mA).",
      "C11 + R10||R11 give an 80 ms soft start; Q3 discharges it when disabled.",
      "U5 selects PULSE (TTL high) or IDLE (TTL low, 5..104 mA)."], (20, 160), 6),
    ("TTL", "3  TTL INPUT (BNC, 10 k to GND, 3.3/5 V logic)",
     ["Schmitt trigger with TTL thresholds; unconnected input = IDLE."], (300, 30), 4),
    ("CS", "4  HIGH-SIDE CURRENT SOURCE (laser cathode at GND)",
     ["I_LD = VSP x (R32/R31) / R40 = VSP / 4 V/A.",
      "U7A error amp senses R40 directly (Kelvin via NT1/NT2); R41 degenerates Q2.",
      "Q6 clamps Q2 off unless EN_LOOP is high (fail-safe, Q7/Q8 release it).",
      "Q5 forces U7A high while disabled so the integrator cannot wind up."], (300, 120), 6),
    ("OUT", "5  OUTPUT, SHORTING RELAY AND CROWBAR",
     ["K1 NC contacts short the laser whenever the driver is not armed or unpowered.",
      "Q10 crowbar shorts it within 1 us of a fault; D6/D7 reverse and surge clamp.",
      "DB9 follows Thorlabs LD-driver 'CG' pinout: 8 = anode, 3 = cathode/GND, 1-5 interlock."], (580, 30), 5),
    ("MON", "6  CURRENT AND SETPOINT MONITORS (1 V/A into high-Z)",
     ["I MON from INA180 (4 V/A) / 4; SET MON shows the PULSE setpoint / 4."], (580, 190), 4),
    ("PROT", "7  PROTECTION COMPARATORS",
     ["A: over-current > 800 mA.  B: compliance / open laser (gate < 2 V for > 10 us).",
      "C: Q2 heatsink > 85 C (NTC RT1).  D: emission > 19 mA lights the EMISSION LED for ~0.15 s."], (580, 300), 6),
    ("LOGIC", "8  INTERLOCKS, FAULT LATCH AND ENABLE SEQUENCING",
     ["Any fault, open interlock or power-up sets the FAULT latch; reset by switching ENABLE off.",
      "EN_REQ arms relay K1 at once; EN_LOOP releases the current source ~17 ms later."], (20, 330), 7),
    ("FP", "9  FRONT-PANEL INDICATORS", [], (300, 330), 4),
    ("PWRPINS", "10  IC POWER PINS", [], (300, 430), 7),
    ("MECH", "11  MOUNTING HOLES", [], (580, 480), 4),
]

CELL_W = 52.07   # horizontal pitch of symbol cells
CELL_H_MIN = 30.48


def lib_symbol_entry(lib_id):
    s = get_symbol(lib_id)
    s[1] = lib_id
    return s


def sym_bbox(lib_id, unit):
    ps = [p for p in sym_pins(lib_id) if p["unit"] in (unit, 0) and p["style"] in (0, 1)]
    if not ps:
        return (-2.54, -2.54, 2.54, 2.54)
    xs = [p["x"] for p in ps]; ys = [p["y"] for p in ps]
    return (min(xs), min(ys), max(xs), max(ys))


class Sheet:
    def __init__(self):
        self.items = []
        self.libs = {}
        self.pwr_n = 0
        self.flg_n = 0

    def add_lib(self, lib_id):
        if lib_id not in self.libs:
            self.libs[lib_id] = lib_symbol_entry(lib_id)

    def wire(self, x1, y1, x2, y2):
        self.items.append([S("wire"), [S("pts"), [S("xy"), x1, y1], [S("xy"), x2, y2]],
                           [S("stroke"), [S("width"), 0], [S("type"), S("default")]],
                           [S("uuid"), U("w", x1, y1, x2, y2)]])

    def glabel(self, name, x, y, ang):
        just = {0: ["left"], 180: ["right"], 90: ["left"], 270: ["right"]}[ang]
        self.items.append([S("global_label"), name, [S("shape"), S("passive")],
                           [S("at"), x, y, ang], [S("fields_autoplaced"), S("yes")],
                           eff(1.27, justify=just), [S("uuid"), U("gl", name, x, y)],
                           [S("property"), "Intersheetrefs", "${INTERSHEET_REFS}",
                            [S("at"), x, y, 0], eff(1.27, hide=True)]])

    def noconn(self, x, y):
        self.items.append([S("no_connect"), [S("at"), x, y], [S("uuid"), U("nc", x, y)]])

    def text(self, s, x, y, size=1.27, bold=False):
        self.items.append([S("text"), s, [S("exclude_from_sim"), S("no")], [S("at"), x, y, 0],
                           eff(size, justify=["left", "bottom"], bold=bold), [S("uuid"), U("t", s, x, y)]])

    def rect(self, x1, y1, x2, y2):
        self.items.append([S("rectangle"), [S("start"), x1, y1], [S("end"), x2, y2],
                           [S("stroke"), [S("width"), 0.254], [S("type"), S("dash")]],
                           [S("fill"), [S("type"), S("none")]], [S("uuid"), U("r", x1, y1)]])

    def symbol(self, lib_id, ref, value, x, y, unit, props, pins_of_unit, in_bom=True, on_board=True):
        self.add_lib(lib_id)
        key = (ref, unit)
        node = [S("symbol"), [S("lib_id"), lib_id], [S("at"), x, y, 0], [S("unit"), unit],
                [S("exclude_from_sim"), S("no")], [S("in_bom"), S("yes" if in_bom else "no")],
                [S("on_board"), S("yes" if on_board else "no")], [S("dnp"), S("no")],
                [S("fields_autoplaced"), S("yes")], [S("uuid"), U("sym", ref, unit)]]
        bx0, by0, bx1, by1 = sym_bbox(lib_id, unit)
        right_mid = any(abs(q["y"]) < 1.3 and q["ang"] == 180 and q["unit"] in (unit, 0)
                        for q in sym_pins(lib_id))
        if right_mid:
            # a pin leaves the right side at mid-height: put the fields above the symbol
            ytop = y - max(by1, 5.08) - 3.81
            node.append([S("property"), "Reference", ref, [S("at"), x, ytop, 0],
                         eff(1.27, justify=["left"])])
            node.append([S("property"), "Value", value, [S("at"), x, ytop + 1.9, 0],
                         eff(1.27, justify=["left"])])
        else:
            node.append([S("property"), "Reference", ref, [S("at"), x + bx1 + 2.54, y - 1.27, 0],
                         eff(1.27, justify=["left"])])
            node.append([S("property"), "Value", value, [S("at"), x + bx1 + 2.54, y + 1.27, 0],
                         eff(1.27, justify=["left"])])
        for k, v in props:
            node.append([S("property"), k, v, [S("at"), x, y, 0], eff(1.27, hide=True)])
        for pn in pins_of_unit:
            node.append([S("pin"), pn, [S("uuid"), U("pin", ref, pn)]])
        node.append([S("instances"), [S("project"), design.PROJECT,
                     [S("path"), "/" + ROOT_UUID, [S("reference"), ref], [S("unit"), unit]]]])
        self.items.append(node)

    def power(self, lib_id, net, x, y, ang):
        self.add_lib(lib_id)
        if lib_id == "power:PWR_FLAG":
            self.flg_n += 1
            ref = "#FLG%02d" % self.flg_n
        else:
            self.pwr_n += 1
            ref = "#PWR%03d" % self.pwr_n
        self.items.append([S("symbol"), [S("lib_id"), lib_id], [S("at"), x, y, ang], [S("unit"), 1],
                           [S("exclude_from_sim"), S("no")], [S("in_bom"), S("yes")], [S("on_board"), S("yes")],
                           [S("dnp"), S("no")], [S("fields_autoplaced"), S("yes")], [S("uuid"), U("pwr", ref)],
                           [S("property"), "Reference", ref, [S("at"), x, y + 6, 0], eff(1.27, hide=True)],
                           [S("property"), "Value", net, [S("at"), x, y + 3.8, 0], eff(1.27)],
                           [S("property"), "Footprint", "", [S("at"), x, y, 0], eff(1.27, hide=True)],
                           [S("property"), "Datasheet", "", [S("at"), x, y, 0], eff(1.27, hide=True)],
                           [S("property"), "Description", "", [S("at"), x, y, 0], eff(1.27, hide=True)],
                           [S("pin"), "1", [S("uuid"), U("pwrpin", ref)]],
                           [S("instances"), [S("project"), design.PROJECT,
                            [S("path"), "/" + ROOT_UUID, [S("reference"), ref], [S("unit"), 1]]]]])


def outward(ang):
    # pin angle points from the connection point towards the body (symbol coords, y up)
    a = math.radians(ang)
    ox, oy = -math.cos(a), -math.sin(a)
    return round(ox), round(-oy)  # schematic coords (y down)


def label_angle(dx, dy):
    if dx < 0: return 180
    if dx > 0: return 0
    if dy < 0: return 90
    return 270


def gnd_angle(dx, dy):
    # GND symbol drawn pointing down; rotate so it points outward
    if dy > 0: return 0
    if dx > 0: return 90
    if dy < 0: return 180
    return 270


PAGE_W, PAGE_H = 1189.0, 841.0   # A0 landscape
MARGIN = 20.0


def layout_block(members, ncols, notes):
    """Return (cells, width, height) in block-local coordinates."""
    y0 = 4 + 2.54 * len(notes) + 10
    cells = []
    col = 0
    row_y = y0
    row_h = 0
    for p, u in members:
        bx0, by0, bx1, by1 = sym_bbox(p["lib"], u)
        h = max(CELL_H_MIN, (by1 - by0) + 15)
        cells.append((p, u, 25 + col * CELL_W, row_y + by1 + 6))
        row_h = max(row_h, h)
        col += 1
        if col >= ncols:
            col = 0
            row_y += row_h
            row_h = 0
    height = row_y + row_h + 4
    width = min(ncols, len(members)) * CELL_W + 10
    return cells, width, height


def build():
    sh = Sheet()
    units = []  # (block, part, unit)
    for p in design.PARTS:
        for u, blk in p["units"].items():
            units.append((blk, p, u))
    laid = []
    for blk, title, notes, _origin, ncols in BLOCKS:
        members = [(p, u) for b, p, u in units if b == blk]
        if members:
            cells, w, h = layout_block(members, ncols, notes)
            laid.append((title, notes, cells, w, h))
    # shelf packing, left to right, top to bottom
    x = MARGIN + 5
    y = MARGIN + 6
    shelf_h = 0
    for title, notes, cells, w, h in laid:
        if x + w > PAGE_W - MARGIN:
            x = MARGIN + 5
            y += shelf_h + 14
            shelf_h = 0
        ox, oy = snap(x), snap(y)
        sh.text(title, ox, oy, size=2.0, bold=True)
        ty = oy + 4
        for n in notes:
            sh.text(n, ox, ty, size=1.27)
            ty += 2.54
        for p, u, cx, cy in cells:
            place_unit(sh, p, u, snap(ox + cx), snap(oy + cy))
        sh.rect(ox - 5, oy - 6, ox + w, oy + h)
        x += w + 12
        shelf_h = max(shelf_h, h)
    if y + shelf_h > PAGE_H - 60:
        print("WARNING: schematic content exceeds the page height", y + shelf_h)
    return sh


def place_unit(sh, p, u, x, y):
    lib = p["lib"]
    ref = p["ref"]
    allpins = [q for q in sym_pins(lib) if q["unit"] in (u, 0) and q["style"] in (0, 1)]
    seen = set()
    pins_u = []
    for q in allpins:
        if q["num"] in seen:
            continue
        seen.add(q["num"])
        pins_u.append(q)
    if lib == "power:PWR_FLAG":
        net = p["pins"]["1"]
        # flag + a stub + label
        sh.power("power:PWR_FLAG", "PWR_FLAG", x, y, 0)
        sh.wire(x, y, x, y + 5.08)
        if net == "GND":
            sh.power("power:GND", "GND", x, y + 5.08, 0)
        else:
            sh.glabel(net, x, y + 5.08, 270)
        return
    props = [("Footprint", p["fp"]), ("Datasheet", ""), ("Description", p.get("note", "")),
             ("LCSC", p.get("lcsc", "")), ("MPN", p.get("mpn", ""))]
    nobom = p.get("nobom", False)
    sh.symbol(lib, ref, p["value"], x, y, u, props, [q["num"] for q in pins_u], in_bom=not nobom)
    for q in pins_u:
        if q["num"] not in p["pins"]:
            raise SystemExit(f"{ref}: pin {q['num']} ({q['name']}) has no net in design.py")
        net = p["pins"][q["num"]]
        px, py = snap(x + q["x"]), snap(y - q["y"])
        if q["etype"] == "no_connect" and net is None:
            continue
        if net is None:
            sh.noconn(px, py)
            continue
        dx, dy = outward(q["ang"])
        L = 2.54
        ex, ey = snap(px + dx * L), snap(py + dy * L)
        sh.wire(px, py, ex, ey)
        if net == "GND":
            sh.power("power:GND", "GND", ex, ey, gnd_angle(dx, dy))
        else:
            sh.glabel(net, ex, ey, label_angle(dx, dy))


def main():
    sh = build()
    tb = [S("title_block"), [S("title"), design.TITLE], [S("date"), "2026-10-28"], [S("rev"), design.REV],
          [S("company"), "Ion-trap lab photoionisation 405 nm driver"],
          [S("comment"), 1, "Generated from tools/design.py by tools/gen_sch.py"],
          [S("comment"), 2, "Laser: DTR BDR-209 405 nm (500 mA nominal, 600 mA max), CATHODE AT GND"],
          [S("comment"), 3, "CLASS 4 LASER - read README safety section before use"]]
    sch = [S("kicad_sch"), [S("version"), 20250114], [S("generator"), "eeschema"],
           [S("generator_version"), "9.0"], [S("uuid"), ROOT_UUID], [S("paper"), "A0"], tb,
           [S("lib_symbols")] + [sh.libs[k] for k in sorted(sh.libs)]]
    sch += sh.items
    sch.append([S("sheet_instances"), [S("path"), "/", [S("page"), "1"]]])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(dump(sch) + "\n")
    print("wrote", OUT, "items:", len(sh.items))


if __name__ == "__main__":
    main()
