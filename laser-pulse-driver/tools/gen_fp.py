#!/usr/bin/env python3
"""Generate the custom footprints in ../hardware/lib/ld405.pretty.

Convention for all panel parts: the part faces -X (towards the panel) and the
footprint origin is the reference point given in each docstring.  Dimensions
are taken from the manufacturer drawings (JLCPCB/LCSC datasheets).
"""
import os, sys, uuid
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sexp import dump, Sym as S

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(HERE, "..", "hardware", "lib", "ld405.pretty")
NS = uuid.UUID("2a8f4c61-0c55-4a3e-8f7e-5d2b1e7c9a03")


def U(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


class FP:
    def __init__(self, name, descr, tags, tht=True):
        self.name = name
        self.n = 0
        self.items = [S("footprint"), name, [S("version"), 20241229], [S("generator"), "pcbnew"],
                      [S("generator_version"), "9.0"], [S("layer"), "F.Cu"], [S("descr"), descr],
                      [S("tags"), tags]]
        self.is_tht = tht

    def _u(self):
        self.n += 1
        return U(self.name, self.n)

    def prop(self, k, v, x, y, layer, hide=False, size=1.0):
        e = [S("effects"), [S("font"), [S("size"), size, size], [S("thickness"), 0.15]]]
        node = [S("property"), k, v, [S("at"), x, y, 0]]
        if k not in ("Reference", "Value"):
            node.append([S("unlocked"), S("yes")])
        node.append([S("layer"), layer])
        if hide:
            node.append([S("hide"), S("yes")])
        node += [[S("uuid"), self._u()], e]
        self.items.append(node)

    def line(self, x1, y1, x2, y2, layer, w=0.12):
        self.items.append([S("fp_line"), [S("start"), x1, y1], [S("end"), x2, y2],
                           [S("stroke"), [S("width"), w], [S("type"), S("solid")]],
                           [S("layer"), layer], [S("uuid"), self._u()]])

    def rect(self, x1, y1, x2, y2, layer, w=0.12):
        self.items.append([S("fp_rect"), [S("start"), x1, y1], [S("end"), x2, y2],
                           [S("stroke"), [S("width"), w], [S("type"), S("solid")]],
                           [S("fill"), S("no")], [S("layer"), layer], [S("uuid"), self._u()]])

    def circle(self, cx, cy, r, layer, w=0.12):
        self.items.append([S("fp_circle"), [S("center"), cx, cy], [S("end"), cx + r, cy],
                           [S("stroke"), [S("width"), w], [S("type"), S("solid")]],
                           [S("fill"), S("no")], [S("layer"), layer], [S("uuid"), self._u()]])

    def text(self, s, x, y, layer, size=0.8):
        self.items.append([S("fp_text"), S("user"), s, [S("at"), x, y, 0], [S("layer"), layer],
                           [S("uuid"), self._u()],
                           [S("effects"), [S("font"), [S("size"), size, size], [S("thickness"), 0.12]]]])

    def tht(self, num, x, y, shape, size, drill, oval=None):
        sx, sy = size
        node = [S("pad"), num, S("thru_hole"), S(shape), [S("at"), x, y], [S("size"), sx, sy]]
        if oval:
            node.append([S("drill"), S("oval"), oval[0], oval[1]])
        else:
            node.append([S("drill"), drill])
        node += [[S("layers"), "*.Cu", "*.Mask"], [S("remove_unused_layers"), S("no")], [S("uuid"), self._u()]]
        self.items.append(node)

    def smd(self, num, x, y, sx, sy, paste=True):
        layers = ["F.Cu", "F.Mask"] + (["F.Paste"] if paste else [])
        self.items.append([S("pad"), num, S("smd"), S("roundrect"), [S("at"), x, y], [S("size"), sx, sy],
                           [S("layers")] + layers, [S("roundrect_rratio"), 0.15], [S("uuid"), self._u()]])

    def model(self, path, off=(0, 0, 0), rot=(0, 0, 0)):
        self.items.append([S("model"), path, [S("offset"), [S("xyz")] + list(off)],
                           [S("scale"), [S("xyz"), 1, 1, 1]], [S("rotate"), [S("xyz")] + list(rot)]])

    def save(self):
        self.items.insert(8, [S("attr"), S("through_hole") if self.is_tht else S("smd")])
        self.items.append([S("embedded_fonts"), S("no")])
        os.makedirs(LIB, exist_ok=True)
        with open(os.path.join(LIB, self.name + ".kicad_mod"), "w") as f:
            f.write(dump(self.items) + "\n")


def bnc():
    """DOSIN-801-0080 right-angle bulkhead BNC (M12x0.75, nut + washer).
    Origin = centre contact.  Ground posts on an 8 x 8 mm square, body 10 x 10 mm.
    The round Ø14 flange (panel stop) is 6.0 mm in front (-X) of the centre contact,
    axis 9.8 mm above the board, thread usable for panels <= 3.5 mm."""
    f = FP("BNC_DOSIN_801-0080_Horizontal",
           "Right-angle PCB BNC jack, bulkhead M12x0.75, Dosin 801-0080 (LCSC C521219); "
           "flange face 6.0 mm in front of the centre pin, axis 9.8 mm above PCB",
           "BNC coax right angle panel")
    f.prop("Reference", "REF**", 0, -7.5, "F.SilkS")
    f.prop("Value", "BNC_DOSIN_801-0080", 0, 7.5, "F.Fab")
    f.prop("Datasheet", "https://jlcpcb.com/partdetail/C521219", 0, 0, "F.Fab", hide=True)
    f.prop("Description", "Dosin 801-0080 BNC, right angle, panel nut", 0, 0, "F.Fab", hide=True)
    f.rect(-5.0, -5.0, 5.0, 5.0, "F.Fab", 0.1)
    f.rect(-6.0, -7.0, -5.0, 7.0, "F.Fab", 0.1)          # flange plate
    f.rect(-24.5, -5.5, -6.0, 5.5, "F.Fab", 0.1)         # thread + bayonet (off board)
    f.line(-5.11, -5.11, 5.11, -5.11, "F.SilkS"); f.line(-5.11, 5.11, 5.11, 5.11, "F.SilkS")
    f.line(5.11, -5.11, 5.11, 5.11, "F.SilkS")
    f.line(-6.1, -7.1, -6.1, 7.1, "F.SilkS")
    f.rect(-6.5, -7.5, 5.5, 7.5, "F.CrtYd", 0.05)
    f.text("PANEL", -7.5, 0, "F.Fab", 0.6)
    # Ø1.0 centre pin in a Ø1.2 hole; the Ø1.2 (-0.1) ground posts get Ø1.4 holes
    f.tht("1", 0, 0, "circle", (2.0, 2.0), 1.2)
    for x in (-4, 4):
        for y in (-4, 4):
            f.tht("2", x, y, "circle", (2.5, 2.5), 1.4)
    f.model("${KIPRJMOD}/lib/ld405.3dshapes/BNC_DOSIN_801-0080.wrl")
    f.save()


def toggle():
    """Dailywell 1MS1T2B4M7QES miniature toggle, SPDT, 'M7' vertical right-angle PCB.
    Origin = midpoint of the two bracket legs (front face of the switch body).
    Bushing (6.22 mm, unthreaded) axis 6.46 mm above the board, 7.31 mm long, pointing -X.
    Terminals 1-2-3 (2 = common) at 12.70 / 16.51 / 20.32 mm behind the bracket;
    terminal 1 leaves the body lowest, 3 highest, so lever up connects 2-1
    (datasheet: pos. 1 = 2-3, pos. 3 = 2-1)."""
    f = FP("Toggle_Dailywell_1MS1T2B4M7QES",
           "Miniature toggle switch SPDT, vertical right-angle PC mount (Dailywell 1M series 'M7'), "
           "LCSC C496157; bushing axis 6.46 mm above PCB", "toggle switch right angle")
    f.prop("Reference", "REF**", 10, -5, "F.SilkS")
    f.prop("Value", "1MS1T2B4M7QES", 10, 5, "F.Fab")
    f.prop("Datasheet", "https://jlcpcb.com/partdetail/C496157", 0, 0, "F.Fab", hide=True)
    f.prop("Description", "Toggle SPDT, terminal 2 = common", 0, 0, "F.Fab", hide=True)
    f.rect(0, -3.43, 21.3, 3.43, "F.Fab", 0.1)
    f.rect(-7.31, -3.11, 0, 3.11, "F.Fab", 0.1)
    f.rect(-0.2, -3.63, 21.5, 3.63, "F.SilkS")
    f.rect(-0.8, -4.2, 22.0, 4.2, "F.CrtYd", 0.05)
    f.text("PANEL", -2.5, 0, "F.Fab", 0.6)
    f.tht("MP", 0, -2.54, "circle", (3.0, 3.0), 1.9)
    f.tht("MP", 0, 2.54, "circle", (3.0, 3.0), 1.9)
    # 0.76 x 1.22 mm tab terminals: datasheet P.C. mounting holes are 1.85 mm
    f.tht("1", 12.70, 0, "rect", (2.6, 2.6), 1.85)
    f.tht("2", 16.51, 0, "circle", (2.6, 2.6), 1.85)
    f.tht("3", 20.32, 0, "circle", (2.6, 2.6), 1.85)
    f.model("${KIPRJMOD}/lib/ld405.3dshapes/Toggle_Dailywell_1MS1T2B4M7QES.wrl")
    f.save()


def led_side():
    """Lite-On LTST-S220 side-looking LED (2.15 x 0.6 x 1.0 mm), lens towards -X.
    Origin = body centre.  Lite-On's suggested land pattern: two 1.0 x 1.5 mm pads
    1.0 mm apart.  Pad 1 = cathode, pad 2 = anode (KiCad LED symbol).  With the lens
    towards -X the cathode mark is at +Y; Lite-On's package drawing and its tape
    drawing (lens to the right, CATHODE at the top) agree on this."""
    f = FP("LED_SideView_LiteOn_LTST-S220",
           "Side-looking LED 2.15x0.6x1.0 mm, Lite-On LTST-S220 series, emits towards -X; "
           "land pattern from the datasheet", "LED side view right angle", tht=False)
    f.prop("Reference", "REF**", 1.6, -2.6, "F.SilkS", size=0.8)
    f.prop("Value", "LTST-S220", 1.6, 2.6, "F.Fab", size=0.6)
    f.prop("Datasheet", "https://www.lcsc.com/datasheet/C284935.pdf", 0, 0, "F.Fab", hide=True)
    f.prop("Description", "", 0, 0, "F.Fab", hide=True)
    f.smd("2", 0, -1.25, 1.0, 1.5)
    f.smd("1", 0, 1.25, 1.0, 1.5)
    f.rect(-0.3, -1.075, 0.3, 1.075, "F.Fab", 0.1)                     # body
    f.line(-0.3, -0.85, -0.75, -0.45, "F.Fab", 0.1); f.line(-0.75, -0.45, -0.75, 0.45, "F.Fab", 0.1)
    f.line(-0.75, 0.45, -0.3, 0.85, "F.Fab", 0.1)                      # lens
    f.line(0.75, -2.1, 0.75, 2.1, "F.SilkS")       # rear edge marker
    f.line(-0.65, 2.25, 0.75, 2.25, "F.SilkS")     # cathode (pad 1) marker
    f.rect(-1.0, -2.25, 0.85, 2.25, "F.CrtYd", 0.05)
    f.model("${KIPRJMOD}/lib/ld405.3dshapes/LED_SideView_LTST-S220.wrl")
    f.save()


def dcjack():
    """DC-005 5.5/2.0 mm barrel jack, right angle (XKB DC-005-5A-2.0, LCSC C381116).
    Body 9.0 W x 11.0 H x 14.0 L, plug axis 7.0 mm above the board (4.0 below the top).
    Origin = centre of the front face on the board edge line, plug enters from -X.
    Pin 1 = centre (+) at x = 13.6, pin 2 = sleeve at x = 7.7, pin 3 = switch at x = 10.6,
    y = +/-4.7.  Pin 3 slot is provided on both sides; both are tied to pin 2 (GND)."""
    f = FP("BarrelJack_DC-005_Horizontal",
           "DC-005 barrel jack 5.5x2.0/2.1 mm, right angle, slotted pins (XKB DC-005-5A-2.0, LCSC C381116)",
           "DC power jack barrel DC-005")
    f.prop("Reference", "REF**", 7, -6.5, "F.SilkS")
    f.prop("Value", "DC-005", 7, 6.5, "F.Fab")
    f.prop("Datasheet", "https://jlcpcb.com/partdetail/C381116", 0, 0, "F.Fab", hide=True)
    f.prop("Description", "", 0, 0, "F.Fab", hide=True)
    f.rect(0, -4.5, 14.0, 4.5, "F.Fab", 0.1)
    f.line(-0.1, -4.6, 14.1, -4.6, "F.SilkS"); f.line(-0.1, 4.6, 14.1, 4.6, "F.SilkS")
    f.line(14.1, -4.6, 14.1, 4.6, "F.SilkS")
    f.rect(-0.5, -6.3, 15.4, 6.3, "F.CrtYd", 0.05)
    f.text("PANEL", -2.0, 0, "F.Fab", 0.6)
    # slots 1.2 x 3.6 mm (datasheet recommends 1.0 x 3.5 for the 0.35 mm terminals)
    f.tht("1", 13.6, 0, "oval", (2.4, 4.6), None, oval=(1.2, 3.6))
    f.tht("2", 7.7, 0, "oval", (2.4, 4.6), None, oval=(1.2, 3.6))
    f.tht("3", 10.6, 4.7, "oval", (4.6, 2.4), None, oval=(3.6, 1.2))
    f.tht("3", 10.6, -4.7, "oval", (4.6, 2.4), None, oval=(3.6, 1.2))
    f.model("${KIPRJMOD}/lib/ld405.3dshapes/BarrelJack_DC-005_Horizontal.wrl")
    f.save()


if __name__ == "__main__":
    bnc(); toggle(); led_side(); dcjack()
    print("footprints in", os.path.normpath(LIB), os.listdir(LIB))
