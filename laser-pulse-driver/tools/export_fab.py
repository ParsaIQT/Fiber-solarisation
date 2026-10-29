#!/usr/bin/env python3
"""Manufacturing outputs in ../hardware/fab/ for JLCPCB PCB + assembly:

  ld405-driver_gerbers_jlcpcb.zip   Gerbers (4 layers) + Excellon drill files
  ld405-driver_bom_jlcpcb.csv       BOM in JLCPCB format (Comment, Designator, Footprint, LCSC)
  ld405-driver_cpl_jlcpcb.csv       placement file in JLCPCB format
  ld405-driver_bom_full.csv         BOM with manufacturer part numbers and quantities
  ld405-driver_schematic.pdf        schematic
  ld405-driver_assembly.pdf         assembly drawing (fab layer, top)
  ld405-driver_top.png / _bottom.png / _iso.png   3D renders

Usage:  python3 export_fab.py
"""
import csv, os, re, shutil, subprocess, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.normpath(os.path.join(HERE, "..", "hardware"))
FAB = os.path.join(HW, "fab")
NAME = design.PROJECT
PCB = os.path.join(HW, NAME + ".kicad_pcb")
SCH = os.path.join(HW, NAME + ".kicad_sch")
LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"

# JLCPCB's placement machines use the LCSC/EasyEDA footprint orientation; these
# offsets map KiCad's library orientation onto it (the first three as in the widely
# used KiCad->JLC plugins; the panel parts read off JLCPCB's placement preview, where
# they came out a quarter-turn off).  Always confirm in JLCPCB's placement preview.
JLC_ROT = [(r"^SOT-23", 180), (r"^SOIC-", 270), (r"^CP_Elec_", 180),
           (r"^BNC_DOSIN_801-0080", 90), (r"^Potentiometer_Alps_RK09L", 270),
           (r"^Toggle_Dailywell", 270), (r"^DSUB-9_Socket", 270)]


def run(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def gerbers():
    tmp = tempfile.mkdtemp()
    run("kicad-cli", "pcb", "export", "gerbers", "-o", tmp + "/", "-l", LAYERS, PCB)
    run("kicad-cli", "pcb", "export", "drill", "-o", tmp + "/", "--format", "excellon",
        "--excellon-units", "mm", "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2", PCB)
    out = os.path.join(FAB, NAME + "_gerbers_jlcpcb.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(tmp)):
            z.write(os.path.join(tmp, f), f)
    files = sorted(os.listdir(tmp))
    shutil.rmtree(tmp)
    return out, files


def bom_rows():
    groups = {}
    for p in design.PARTS:
        if p.get("virtual") or p.get("nobom") or not p["fp"]:
            continue
        fpname = p["fp"].split(":")[1]
        key = (p["value"], fpname, p["lcsc"], p["mpn"])
        groups.setdefault(key, []).append(p["ref"])

    def refkey(r):
        m = re.match(r"([A-Z]+)(\d+)", r)
        return (m.group(1), int(m.group(2)))
    rows = []
    for (val, fpname, lcsc, mpn), refs in groups.items():
        refs.sort(key=refkey)
        rows.append((val, refs, fpname, lcsc, mpn))
    rows.sort(key=lambda r: refkey(r[1][0]))
    return rows


def bom():
    rows = bom_rows()
    missing = [r for r in rows if not r[3]]
    if missing:
        sys.exit("parts without LCSC number: " + ", ".join(",".join(r[1]) for r in missing))
    p1 = os.path.join(FAB, NAME + "_bom_jlcpcb.csv")
    with open(p1, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for val, refs, fpname, lcsc, mpn in rows:
            w.writerow([val, ",".join(refs), fpname, lcsc])
    p2 = os.path.join(FAB, NAME + "_bom_full.csv")
    with open(p2, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Qty", "Value", "Designators", "Footprint", "Manufacturer part", "LCSC"])
        for val, refs, fpname, lcsc, mpn in rows:
            w.writerow([len(refs), val, " ".join(refs), fpname, mpn, lcsc])
    return p1, p2, rows


def cpl():
    tmp = tempfile.mkdtemp()
    pos = os.path.join(tmp, "pos.csv")
    run("kicad-cli", "pcb", "export", "pos", "-o", pos, "--format", "csv", "--units", "mm", "--side", "both", PCB)
    out = os.path.join(FAB, NAME + "_cpl_jlcpcb.csv")
    n = 0
    with open(pos) as fi, open(out, "w", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for r in csv.DictReader(fi):
            rot = float(r["Rot"])
            for pat, off in JLC_ROT:
                if re.search(pat, r["Package"]):
                    rot += off
                    break
            rot %= 360
            w.writerow([r["Ref"], f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm",
                        "Top" if r["Side"] == "top" else "Bottom", f"{rot:g}"])
            n += 1
    shutil.rmtree(tmp)
    return out, n


def pdfs():
    sch = os.path.join(FAB, NAME + "_schematic.pdf")
    run("kicad-cli", "sch", "export", "pdf", "-o", sch, SCH)
    asm = os.path.join(FAB, NAME + "_assembly.pdf")
    run("kicad-cli", "pcb", "export", "pdf", "-o", asm, "-l", "F.Fab,Edge.Cuts", "--ibt",
        "--mode-single", PCB)
    return sch, asm


def renders():
    out = []
    for tag, args in (("top", ["--side", "top"]), ("bottom", ["--side", "bottom"]),
                      ("iso", ["--side", "top", "--rotate", "-40,0,30", "--perspective", "--zoom", "0.9"])):
        p = os.path.join(FAB, f"{NAME}_{tag}.png")
        run("kicad-cli", "pcb", "render", "-o", p, "-w", "1800", "-h", "1200", "--quality", "high",
            "--background", "opaque", *args, PCB)
        out.append(p)
    return out


if __name__ == "__main__":
    os.makedirs(FAB, exist_ok=True)
    z, files = gerbers()
    print("gerbers:", os.path.basename(z), len(files), "files:", " ".join(files))
    b1, b2, rows = bom()
    print("bom:", os.path.basename(b1), len(rows), "lines,", sum(len(r[1]) for r in rows), "parts")
    c, n = cpl()
    print("cpl:", os.path.basename(c), n, "placements")
    for p in pdfs():
        print("pdf:", os.path.basename(p))
    if "--no-render" not in sys.argv:
        for p in renders():
            print("render:", os.path.basename(p))
