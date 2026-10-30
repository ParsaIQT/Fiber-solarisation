#!/usr/bin/env python3
"""Build the package for an outside design review:

  review_package/LD405_design_review.pdf   the review document (+ schematic, assembly drawing)
  review_package/LD405_review_pack.zip     the PDF plus KiCad project, JLCPCB files, layer plots,
                                           ERC/DRC reports, simulation, enclosure, review renders

Usage: python3 make_review_pack.py [--no-sims]
Needs kicad-cli, node with Playwright (Chromium), pypdf and matplotlib; the corner
simulations also need ngspice and the vendor models (sim/get_models.sh).
"""
import csv, datetime, html, os, re, shutil, subprocess, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design, review_figs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
HW = os.path.join(ROOT, "hardware")
FAB = os.path.join(HW, "fab")
OUT = os.path.join(ROOT, "review_package")
PDF_NAME = "LD405_design_review.pdf"
ZIP_NAME = "LD405_review_pack.zip"
DATE = datetime.date.today()
E = html.escape


def run(*cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(cmd)}\n{r.stdout}\n{r.stderr}")
    return r.stdout


def img(rel):
    return "file://" + os.path.join(ROOT, rel)


# ------------------------------------------------------------------ inputs
def kicad_outputs(tmp):
    sch, pcb = (os.path.join(HW, design.PROJECT + ext) for ext in (".kicad_sch", ".kicad_pcb"))
    out = {}
    out["schematic"] = os.path.join(tmp, "ld405-driver_schematic.pdf")
    run("kicad-cli", "sch", "export", "pdf", "-o", out["schematic"], sch)
    layers_dir = os.path.join(tmp, "layers")
    run("kicad-cli", "pcb", "export", "pdf", "--mode-multipage", "--layers",
        "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Silkscreen,B.Silkscreen,F.Fab,B.Fab", "--common-layers", "Edge.Cuts",
        "--include-border-title", "-o", layers_dir, pcb)
    out["layers"] = os.path.join(tmp, "ld405-driver_layers.pdf")
    shutil.move(os.path.join(layers_dir, design.PROJECT + ".pdf"), out["layers"])
    out["erc"] = os.path.join(tmp, "erc_report.txt")
    run("kicad-cli", "sch", "erc", "--severity-all", "--format", "report", "-o", out["erc"], sch)
    out["drc"] = os.path.join(tmp, "drc_report.txt")
    run("kicad-cli", "pcb", "drc", "--schematic-parity", "--severity-all", "--format", "report", "-o", out["drc"], pcb)
    erc = open(out["erc"]).read()
    drc = open(out["drc"]).read()
    m = re.search(r"ERC messages: (\d+)\s+Errors (\d+)\s+Warnings (\d+)", erc)
    out["erc_counts"] = tuple(int(v) for v in m.groups())
    out["drc_counts"] = tuple(int(re.search(rf"Found (\d+) {k}", drc).group(1))
                              for k in ("DRC violations", "unconnected pads", "Footprint errors"))
    out["kicad"] = run("kicad-cli", "version").strip()
    import pcbnew
    b = pcbnew.LoadBoard(pcb)
    tracks = list(b.GetTracks())
    out["vias"] = sum(1 for t in tracks if t.GetClass() == "PCB_VIA")
    out["segments"] = sum(1 for t in tracks if t.GetClass() == "PCB_TRACK")
    return out


def simulations(tmp, skip):
    """Corner simulations (sim/run_sims.py): returns (large-signal rows, small-signal rows, raw text)."""
    path = os.path.join(tmp, "sim_results.txt")
    have_models = os.path.exists(os.path.join(ROOT, "sim", "models", "irfr9024n.lib"))
    if skip or not have_models:
        return None, None, None
    txt = run(sys.executable, "run_sims.py", "--no-plots", cwd=os.path.join(ROOT, "sim"))
    open(path, "w").write(txt)
    big, small = [], []
    for ln in txt.splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) == 9 and c[0][:1].isdigit():
            big.append(c)
        elif len(c) == 5 and c[0][:1].isdigit():
            small.append(c)
    return big, small, path


def git_info():
    h = run("git", "rev-parse", "--short", "HEAD", cwd=ROOT).strip()
    br = run("git", "rev-parse", "--abbrev-ref", "HEAD", cwd=ROOT).strip()
    return h, br


# ------------------------------------------------------------------ html helpers
def table(head, rows, cls="", widths=None):
    cols = "".join(f'<col style="width:{w}">' for w in widths) if widths else ""
    th = "".join(f"<th>{h}</th>" for h in head)
    thead = f"<thead><tr>{th}</tr></thead>" if any(head) else ""
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="{cls}"><colgroup>{cols}</colgroup>{thead}<tbody>{body}</tbody></table>'


def fig(src, cap, width="100%", cls=""):
    return (f'<figure class="{cls}"><img src="{src}" style="width:{width}"><figcaption>{cap}</figcaption></figure>')


CSS = """
@page { size: A4; }
* { box-sizing: border-box; }
body { font-family: Inter, sans-serif; font-size: 9.4pt; line-height: 1.45; color: #1f2933; margin: 0; }
h1 { font-size: 16pt; font-weight: 700; margin: 20pt 0 8pt; padding-top: 2pt; letter-spacing: -0.2pt; break-after: avoid; }
h1.sec { break-before: page; margin-top: 0; }
h1.top { margin-top: 0; }
h2 { font-size: 11.5pt; font-weight: 650; margin: 14pt 0 4pt; break-after: avoid; }
h3 { font-size: 10pt; font-weight: 650; margin: 10pt 0 3pt; break-after: avoid; }
p { margin: 0 0 6pt; }
ul, ol { margin: 0 0 7pt; padding-left: 15pt; }
li { margin: 0 0 2.5pt; }
code, .mono { font-family: 'JetBrains Mono', monospace; font-size: 8.2pt; }
table { border-collapse: collapse; width: 100%; font-size: 8.3pt; margin: 5pt 0 10pt; line-height: 1.35; }
thead { display: table-header-group; }
tr { break-inside: avoid; }
th, td { border-bottom: 0.5pt solid #d5dbe1; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #eef2f6; font-weight: 650; }
table.num td:not(:first-child), table.num th:not(:first-child) { text-align: right; white-space: nowrap; }
table.small { font-size: 7.6pt; }
figure { margin: 6pt 0 12pt; break-inside: avoid; text-align: center; }
figure img, figure svg { display: block; margin: 0 auto; }
figcaption { font-size: 8pt; color: #52606d; margin-top: 4pt; text-align: left; }
.lead { font-size: 10.2pt; color: #323f4b; }
.note, .warn { break-inside: avoid; }
.note { background: #f6f8fa; border-left: 3pt solid #9aa5b1; padding: 6pt 9pt; margin: 6pt 0 10pt; font-size: 8.8pt; }
.warn { background: #fff7ed; border-left: 3pt solid #ea580c; padding: 6pt 9pt; margin: 6pt 0 10pt; font-size: 8.8pt; }
.q { break-inside: avoid; border: 0.6pt solid #cbd2d9; border-radius: 4pt; padding: 6pt 9pt; margin: 0 0 6pt; }
.q b.n { color: #2563eb; margin-right: 4pt; }
.q .see { color: #52606d; font-size: 8pt; }
.cover { height: 262mm; display: flex; flex-direction: column; }
.cover .kicker { font-size: 9pt; font-weight: 650; letter-spacing: 1.5pt; color: #2563eb; text-transform: uppercase; margin-top: 10mm; }
.cover h1 { font-size: 30pt; margin: 4pt 0 2pt; letter-spacing: -0.6pt; }
.cover .sub { font-size: 13pt; color: #323f4b; margin-bottom: 10pt; }
.cover .meta { font-size: 9.2pt; color: #52606d; }
.cover .status { display: inline-block; margin-top: 8pt; padding: 4pt 9pt; border-radius: 4pt; background: #fff7ed;
                 color: #9a3412; font-weight: 600; font-size: 9pt; }
.cover table { font-size: 8.8pt; margin-top: auto; }
.toc { columns: 2; column-gap: 12mm; font-size: 9pt; margin: 4pt 0 10pt; }
.toc div { break-inside: avoid; padding: 1.5pt 0; border-bottom: 0.4pt dotted #cbd2d9; }
.two { display: flex; gap: 6mm; align-items: flex-start; }
.two > * { flex: 1; min-width: 0; }
.eq { font-family: 'JetBrains Mono', monospace; font-size: 8.4pt; background: #f6f8fa; padding: 6pt 9pt; margin: 4pt 0 8pt;
      white-space: pre; line-height: 1.5; }
"""


# ------------------------------------------------------------------ document
def document(k, sims, git, tmp):
    big, small, _ = sims
    h, branch = git
    P = {p["ref"]: p for p in design.PARTS}
    bom = list(csv.DictReader(open(os.path.join(FAB, design.PROJECT + "_bom_full.csv"))))
    n_lines, n_parts = len(bom), sum(int(r["Qty"]) for r in bom)
    n_cpl = sum(1 for _ in csv.DictReader(open(os.path.join(FAB, design.PROJECT + "_cpl_jlcpcb.csv"))))
    timing = os.path.join(tmp, "timing.svg")
    review_figs.timing_diagram(timing)
    s = []
    a = s.append

    # ---------------------------------------------------------------- cover
    a(f"""<section class="cover">
<div class="kicker">Design review package</div>
<h1>LD405 pulse driver</h1>
<div class="sub">TTL-gated constant-current driver for a 405 nm laser diode (BDR-209), the second, ionising step of
two-photon REMPI during ablation loading of an ion trap</div>
<div class="meta">Board revision {E(design.REV)} &nbsp;·&nbsp; {DATE:%d %B %Y} &nbsp;·&nbsp; built from commit <span class="mono">{h}</span>
of <span class="mono">ParsaIQT/Fiber-solarisation</span>, folder <span class="mono">laser-pulse-driver/</span></div>
<div><span class="status">Pre-production: nothing has been built yet. Boards to be assembled by JLCPCB.</span></div>
<figure style="margin:8mm 0 4mm"><img src="{img('hardware/fab/ld405-driver_iso.png')}" style="width:88%"></figure>
{table(["", ""], [
    ["Output", "high-side current source into the diode anode; cathode at ground (Thorlabs CG DE-9 pin-out)"],
    ["Pulse current", "0–600 mA (PULSE knob), 0–700 mA with solder jumper JP1; selected while TTL IN is high"],
    ["Idle current", "5–104 mA (IDLE knob) while TTL IN is low or open"],
    ["Timing (simulated)", "~0.7 µs delay, 4–6 µs 10–90 % rise, no overshoot, within 1 % after ≤ 12 µs"],
    ["Protection", "relay short + MOSFET crowbar when disarmed, soft start, over-current / compliance / 85 °C trips, "
                   "two interlocks, latched fault, no automatic start"],
    ["Hardware", f"160 × 100 mm 4-layer PCB, {n_parts} parts ({n_lines} BOM lines), JLCPCB assembly; 9 V adapter; 3D-printed case"],
    ["This package", "this PDF and LD405_review_pack.zip (KiCad project, JLCPCB files, layer plots, check reports, "
                     "simulation, enclosure, review renders; see Appendix B)"],
])}
</section>""")

    # ---------------------------------------------------------------- 1. review
    toc = [("1", "What we would like reviewed"), ("2", "Requirements and specification"), ("3", "Architecture"),
           ("4", "Circuit description"), ("5", "Protection and arming"), ("6", "Simulation"), ("7", "PCB"),
           ("8", "Connectors, cable, enclosure, grounding"), ("9", "Manufacturing"), ("10", "Verification status"),
           ("11", "Bring-up and test plan"), ("12", "Known limitations"), ("A", "Bill of materials"),
           ("B", "Contents of the zip file"), ("C", "Schematic and assembly drawing (A0, appended)")]
    a('<h1 class="sec">Contents</h1><div class="toc">' +
      "".join(f"<div><b>{n}</b>&nbsp;&nbsp;{E(t)}</div>" for n, t in toc) + "</div>")
    a("""<h1>1. What we would like reviewed</h1>
<p class="lead">This driver fires a ~0.9 W, 405 nm laser diode for ~100 µs per ablation shot, gated by an ARTIQ
TTL output. The diode has no published datasheet and is not cheap to replace, so the design puts the diode's
safety first: the output is shorted whenever the driver is not armed, every fault latches, and the current
source is linear and slow enough to stay stable with any reasonable cable.</p>
<p>Nothing has been built yet. Before the order goes to JLCPCB we would value a second opinion, above all on the
points below. Section 10 lists what has and has not been verified so far.</p>""")
    qs = [
        ("Diode safety in every state", "Is there any sequence in which the diode could see a current spike, a reverse "
         "voltage or ESD? Consider power-up, power-down, the adapter unplugged or plugged in, ENABLE toggled, an "
         "interlock opened, the cable hot-plugged and the TTL lost.", "§4.5, §5"),
        ("Arm/disarm order", "K1 is meant never to switch current. On disarm, the crowbar and the gate clamp act before "
         "K1 recloses. On arm, the loop starts 20 ms after K1 is energised. Is this robust, including relay bounce "
         "and the 74HC logic while the 5 V rail ramps?", "§5.2"),
        ("Loop stability", "The current source was simulated with vendor models over FET transconductance ×0.5…×2 and "
         "0.35–2 µH of cable. Are the margins convincing? Is anything important missing from the model, such as the "
         "real diode impedance, the op-amp output stage near the rail, or longer cables?", "§6"),
        ("Limits for an unspecified diode", "The BDR-209 has no datasheet. Are these choices sensible?<br>"
         "• current ranges of 0–600 and 0–700 mA;<br>"
         "• a fixed 804 mA over-current trip that does not follow JP1;<br>"
         "• the compliance trip;<br>"
         "• no limit on pulse length (a stuck-high TTL gives CW).", "§2, §5"),
        ("Layout", "The laser current path, the Kelvin sense at R40, the plane and return-current strategy, and Q2's "
         "heat sinking into board copper. The board was routed by a custom script and is DRC-clean.", "§7"),
        ("Grounding", "Board ground is the diode cathode (DE-9 pin 3), the BNC shells and the DC-jack negative. Once "
         "ARTIQ and a scope are connected, it is tied to lab earth. Is there a ground-loop or common-mode concern, "
         "for example if the diode mount touches the optical table?", "§8.4"),
        ("TTL input", "The input is high impedance: 10 kΩ to ground, 220 Ω in series with Schottky clamps, then a "
         "74AHCT1G14 Schmitt trigger. It is driven from a Kasli DIO-BNC at 3.3 V or 5 V. Should there be a 50 Ω "
         "option?", "§4.3"),
        ("Anything else", "Anything that would stop you ordering: part choices, footprints, JLCPCB assembly, "
         "the enclosure.", ""),
    ]
    for i, (t, q, see) in enumerate(qs, 1):
        a(f'<div class="q"><b class="n">Point {i}</b><b>{t}.</b> {q} <span class="see">{see}</span></div>')

    # ---------------------------------------------------------------- 2. requirements
    a("""<h1>2. Requirements and specification</h1>
<h2>2.1 Requirements</h2>
<ul>
<li>Second (ionising) step of a two-photon REMPI scheme during ablation loading: a BDR-209 405 nm Blu-ray diode
run at roughly 0.9 W optical for ~100 µs per ablation shot, timed by an ARTIQ TTL output.</li>
<li>“Plug and play”: fully assembled by a PCB house, in a box, mains powered (UK socket within 2 m of the diode).</li>
<li>The diode must survive mistakes: hot-plugging, open or shorted cables, a lost TTL cable, power cycling and
over-temperature.</li>
</ul>
<h2>2.2 Design choices that follow</h2>
<ul>
<li><b>Constant current, cathode grounded, high-side source.</b> The diode module's case/cathode can sit at ground,
and the DE-9 pin-out matches Thorlabs CG mounts (pin 8 anode, pin 3 cathode, pins 1–5 interlock loop).</li>
<li><b>Idle current between pulses</b> instead of switching the current fully off. The loop never leaves
regulation, so pulses start within ~1 µs without the overshoot a saturated loop would produce. An idle current
just above threshold doubles as a weak alignment beam.</li>
<li><b>Two independent setpoints</b> (PULSE, IDLE) selected by the TTL input through an analogue switch, so the TTL
only has to switch, not shape the pulse.</li>
<li><b>Nothing digital in the current path</b>; the protection is hard-wired logic.</li>
</ul>
<h2>2.3 Specification</h2>""")
    a(table(["", "value"], [
        ["Output", "high-side current source, diode cathode at ground (Thorlabs “CG” DE-9 pin-out)"],
        ["Pulse current", "0–600 mA (PULSE knob); 0–700 mA with JP1 bridged; over-current trip at ~800 mA"],
        ["Idle current", "5–104 mA (IDLE knob) whenever TTL IN is low or unconnected"],
        ["Timing (simulated, 0.5–2.5 m cable)", "~0.7 µs delay, 4–6 µs 10–90 % rise, no overshoot, 1 % settled in "
                                                "≤ 12 µs, ~7 µs fall"],
        ["TTL input", "BNC, 10 kΩ to ground, Schmitt trigger: high ≥ 2.0 V, low ≤ 0.5 V; 220 Ω + Schottky clamps to "
                      "the rails; 3.3 V or 5 V TTL from ARTIQ (Kasli DIO-BNC / DIO-SMA)"],
        ["Monitors", "I MON (measured diode current) and SET MON (pulse setpoint), 1 V/A into high impedance "
                     "(0.5 V/A into 50 Ω)"],
        ["Compliance", "≥ 7 V across the diode at 700 mA (the BDR-209 is reported to need ~5–6 V)"],
        ["Protection", "output shorted by a relay and a MOSFET crowbar whenever disarmed; soft start (τ = 80 ms); "
                       "over-current, open-circuit/compliance and over-temperature (85 °C) trips; two interlocks "
                       "(3.5 mm jack, DE-9 loop); latched fault that needs a deliberate re-arm; no start after power-up"],
        ["Supply", "9 V DC ≥ 1.5 A (5.5/2.1 mm, centre positive; Mean Well GST25A09-P1J suggested); "
                   "reverse-polarity, over-voltage and PTC protection"],
        ["Board, case", "160 × 100 mm 4-layer PCB; 3D-printed case 181 × 108 × 32 mm (MJF PA12)"],
        ["Diode", "BDR-209 (DTR's Laser Shop, copper module). No datasheet; users report ~0.8–1 W at ~500–650 mA "
                  "and ~5–6 V. The driver's limits are set from these reports."],
    ], widths=["28%", "72%"]))

    # ---------------------------------------------------------------- 3. architecture
    a('<h1>3. Architecture</h1>')
    a(f'<figure>{review_figs.block_diagram()}<figcaption>Block diagram. Reference designators match the schematic '
      '(Appendix C). Dashed: the gate clamp released by the arming logic; K1 and Q10 are driven by the same logic '
      '(see §5.2).</figcaption></figure>')
    a("""<p>The pass element is a P-MOSFET (Q2) between the 9 V rail and the diode anode, with the 0.2 Ω shunt R40 and
a 1 Ω degeneration resistor R41 in its source. An OPA2192 error amplifier, powered from VIN so its rail-to-rail
inputs can sit at the shunt, compares the shunt voltage with a reference that a second OPA2192 section sets to
VSP/20 below VIN. The setpoint VSP is either PULSE or IDLE, chosen by the TTL input through an analogue switch.
Hard-wired logic latches every fault and controls three independent ways of keeping current out of the diode:
the relay K1 (normally closed across the output), the crowbar Q10, and a clamp that holds Q2's gate at VIN.</p>""")

    # ---------------------------------------------------------------- 4. circuit
    a("""<h1>4. Circuit description</h1>
<p>Reference designators refer to the schematic (Appendix C). Values come from <span class="mono">tools/design.py</span>,
which generates both the schematic and the PCB, so the two always agree.</p>
<h2>4.1 Power (J1, F1, Q1, D1, D2, U1, U2)</h2>
<p>9 V from a mains adapter → 2 A PTC (F1) → reverse-polarity P-FET Q1 (AO3401A; R1 holds its gate at 0 V and the
Zener D1 limits V<sub>GS</sub> to −10 V) → <span class="mono">VIN</span>. The SMAJ13A TVS D2 clamps
<span class="mono">VIN</span>, and 2 × 220 µF plus ceramics buffer it and supply the pulse current. U1 (L78M05) makes
<span class="mono">+5V</span> for the logic, comparators, monitors and relay. U2 (REF3030) makes the 3.000 V
reference. The current-source op-amp (OPA2192) runs from <span class="mono">VIN</span>, so its rail-to-rail inputs
see the shunt directly.</p>
<h2>4.2 Setpoints (U2, R10/R11, JP1, RV1, RV2, U3, U4A, U5)</h2>
<p><span class="mono">VFS</span> = 3.000 V × 40.2 k / (10 k + 40.2 k) = 2.402 V, which corresponds to 600 mA
(0.1 % resistors). Bridging JP1 puts R12 (4.02 k) in parallel with R10, giving <span class="mono">VFS</span> =
2.80 V, or 700 mA. <span class="mono">VFS</span> also charges C11 (10 µF) through R10 ∥ R11 = 8 k. That is an
80 ms <b>soft start</b> whenever Q3 (driven by <span class="mono">DIS_LOOP</span>) releases it.</p>
<ul><li>PULSE: RV1 across 0…<span class="mono">VFS</span>, buffered by U3B → <span class="mono">VP</span> (0–600 mA).</li>
<li>IDLE: R15 (100 k) – RV2 (20 k) – R16 (1 k) divider from <span class="mono">VFS</span>, buffered by U4A →
<span class="mono">VI</span> = 19.8–417 mV ↔ 5–104 mA.</li>
<li>U5 (SN74LVC1G3157) connects <span class="mono">VP</span> (TTL high) or <span class="mono">VI</span> (TTL low) to
<span class="mono">VSP</span>, filtered by R17/C12 (1 k / 220 pF, 0.22 µs).</li></ul>
<h2>4.3 TTL input (J2, R21, R22, C15, D4, U14)</h2>
<p>R22 (10 k) holds the input low when nothing is plugged in, which gives the idle current. R21 (220 Ω) and the
BAT54S D4 clamp the input to the 5 V rails, and C15 removes glitches shorter than ~20 ns. U14 (74AHCT1G14
Schmitt trigger, thresholds 0.9–2.0 V rising and 0.5–1.6 V falling) drives the switch's select line. The input is not
terminated; ARTIQ's DIO-BNC drives it directly.</p>
<h2>4.4 Current source (U7, Q2, Q4, R30–R41, NT1, NT2)</h2>
<div class="eq">VIN ── R40 0.2 Ω ──┬── R41 1.0 Ω ── S  Q2 IRFR9024N  D ── LD_OUT ── DE-9 pin 8 → diode → pin 3 ── GND
     (Kelvin NT1)  └ (Kelvin NT2)      G ← R34 100 Ω ← U7A (integrator R33 / C31)</div>
<ul>
<li><b>Level shifter</b> (U7B + Q4) forces <span class="mono">VSP</span> across R31 (3.00 k), and the same current
flows through R32 (150 Ω) from the Kelvin <span class="mono">VIN</span> tap, so
<span class="mono">V(VIN) − V(REF) = VSP/20</span>.</li>
<li><b>Error amplifier</b> U7A (OPA2192, rail-to-rail, ±25 µV maximum offset) integrates
<span class="mono">REF − SRC_SNS</span> with R33 = 1 k and C31 = 220 pF, and drives the P-FET gate through
R34 = 100 Ω. In regulation <span class="mono">I · 0.2 Ω = VSP/20</span>, so
<b>I<sub>LD</sub> = VSP × 0.25 A/V</b>.</li>
<li><b>R41 (1 Ω) source degeneration</b> makes the pass stage's transconductance nearly independent of the MOSFET.
The spread in FET g<sub>m</sub> and the cable inductance made earlier topologies ring. R41 costs 0.7 V of headroom at
700 mA, which the 9 V supply has (compliance ≥ 7 V).</li>
<li><b>Kelvin connections</b>: net ties NT1/NT2 take the sense voltage from the inner edges of R40's pads, so the
error amplifier and the INA180 see only the shunt.</li>
<li><b>Accuracy</b>: shunt ±1 %, reference ±0.2 % and dividers 0.1 % keep the setpoint scale within ±1.5 %; offset
&lt; 0.2 mA.</li>
</ul>
<h2>4.5 Output protection (K1, Q10, D6, D7, R44/C32)</h2>
<ul>
<li><b>K1</b> (Omron G6K-2F-Y): both normally-closed contacts short <span class="mono">LD_OUT</span> to ground unless
the driver is armed. The diode is therefore shorted whenever the unit is off, unpowered or faulted, which makes
hot-plugging and ESD on the cable harmless.</li>
<li><b>Q10</b> (AO3400A crowbar) shorts the output within microseconds of a disarm or fault, before the relay
contacts move.</li>
<li>D6 (SS34) clamps reverse voltage, D7 (SMAJ12A) clamps forward over-voltage, and R44/C32 (22 Ω / 47 nF) damp
the cable.</li>
</ul>
<h2>4.6 Gate clamp and loop enable (Q5–Q8, Q3)</h2>
<p>The pass FET is <b>off unless explicitly released</b>. Q6 pulls the gate to <span class="mono">VIN</span>, and
R37/R38 bias it on from <span class="mono">VIN</span> alone. Only when <span class="mono">EN_LOOP</span> is high
does Q8 turn on Q7, which turns Q6 off, so losing the 5 V rail turns the current off. While disabled, Q5 pulls the
integrator input so its output sits at the “off” rail (anti-windup), and Q3 discharges the soft-start
capacitor.</p>
<h2>4.7 Monitors (U8, U10A, U4B)</h2>
<ul>
<li>I MON: INA180A1 (gain 20) on the Kelvin taps gives 4 V/A, which a 0.1 % divider reduces to 1 V/A. A buffer then
drives the BNC through 49.9 Ω: <b>1 V/A</b> into high impedance.</li>
<li>SET MON: the PULSE setpoint <span class="mono">VP</span> ÷ 4 → buffer → 49.9 Ω → BNC: 1 V/A. It shows the pulse
level before firing.</li>
</ul>""")

    # ---------------------------------------------------------------- 5. protection
    a("""<h1>5. Protection and arming</h1>
<h2>5.1 Fault sources</h2>
<p>LM2901 open-collector comparators share the active-low fault line <span class="mono">S_N</span> (R73 pull-up,
C44 filter). The interlocks join <span class="mono">S_N</span> through the BAT54A D10: the 3.5 mm jack
(<span class="mono">REM_N</span>, closed = OK) and the DE-9 loop (<span class="mono">DB9_IL</span>, pins 1–5 linked
in the cable). At power-up R78/C43 hold <span class="mono">S_N</span> low for ~0.2 s through D14.</p>""")
    a(table(["source", "trips when", "threshold"], [
        ["U11A over-current", "I MON (4 V/A) &gt; <span class='mono'>OC_REF</span> 3.21 V", "804 mA"],
        ["U11B compliance / open diode", "gate &lt; 1.98 V (loop saturated) for ≳ 10 µs (R52/R53/C33)", "—"],
        ["U11C over-temperature", "NTC RT1 (10 k, B3950, beside Q2's tab) &lt; 1.09 k", "≈ 85 °C"],
        ["Interlock, 3.5 mm jack J6", "tip–sleeve open", "—"],
        ["Interlock, DE-9 loop", "pins 1–5 not linked (cable unplugged)", "—"],
        ["Power-up hold", "R78/C43 after +5 V appears", "~0.2 s"],
        ["(U11D emission, not a fault)", "I MON &gt; 74 mV: lights EMISSION, stretched to 0.1 s", "≈ 18 mA"],
    ], widths=["30%", "52%", "18%"]))
    a("""<p>U13A/B form a NAND SR latch. Any fault sets <span class="mono">FAULT</span>, and it clears only when the ENABLE
switch is turned off while no fault is present. <span class="mono">EN_REQ = ENABLE ∧ ¬FAULT</span> energises the
relay at once. R79/C45 delay <span class="mono">EN_LOOP</span> by ~20 ms, until the relay contacts are open, and D15
removes the delay on the way down, so disarming is immediate. The loop then soft-starts with τ = 80 ms.</p>
<h2>5.2 Arming and disarming</h2>""")
    a(fig("file://" + timing, "Arm/disarm sequence (schematic time scale). Arming opens K1's short first and "
          "releases the loop 20 ms later. Disarming, by the switch or by any fault, turns on the crowbar and the gate "
          "clamp at once, and K1 recloses a few ms later. The current never flows through a switching relay contact. "
          "Pulses fired in the first ~0.3 s after arming are reduced by the soft start."))
    a("<h2>5.3 Designed response to abnormal conditions</h2>")
    a(table(["condition", "designed response"], [
        ["Power applied", "FAULT forced by the power-up hold (~0.2 s) and latched. K1 de-energised, so the output is "
                          "shorted, and the gate clamp holds Q2 off. No automatic start."],
        ["ENABLE off → on, no fault", "EN_REQ energises K1, which removes the short. 20 ms later EN_LOOP turns off the "
                                      "crowbar and the gate clamp and releases the integrator and soft start. The "
                                      "current ramps to the idle level (τ = 80 ms)."],
        ["ENABLE switched off", "EN_LOOP falls at once (D15). The crowbar and the gate clamp turn on, the integrator "
                                "and soft start reset, and K1 releases and recloses its short a few ms later."],
        ["Interlock opened, or the DE-9 unplugged", "S_N pulled low, FAULT latched, then as ENABLE off. Re-arming needs "
                                                    "ENABLE off → on with the interlocks closed."],
        ["Open diode or broken cable while armed", "The loop saturates and the gate falls below 1.98 V; after ~10 µs "
                                                   "U11B trips → FAULT."],
        ["Over-current (&gt; 804 mA)", "U11A trips → FAULT. This is a backstop for a loop failure: normally the "
                                       "setpoint (≤ 700 mA) limits the current."],
        ["Q2 copper &gt; ~85 °C", "U11C (RT1) trips → FAULT."],
        ["TTL cable unplugged, or ARTIQ output high-Z", "R22 pulls the input low → idle current."],
        ["TTL stuck high", "Continuous current at the PULSE setting, with no time limit. Only Q2's 85 °C trip acts; the "
                           "diode's own duty-cycle limit is not enforced (review point 4)."],
        ["9 V adapter unplugged while armed", "VIN and +5 V decay. K1 releases (output shorted), and the gate clamp, "
                                              "biased from VIN alone, holds Q2 off once EN_LOOP is lost. "
                                              "<i>To confirm on the bench: no current step while the rails collapse.</i>"],
        ["+5 V lost, VIN still present", "K1 releases (short); EN_LOOP low → Q6 clamps the gate from VIN."],
        ["Supply reversed / over-voltage", "Q1 blocks reverse polarity; D2 (SMAJ13A) clamps VIN; F1 (2 A PTC) limits "
                                           "a sustained fault current."],
        ["Output shorted while armed", "The source keeps regulating at the set current; Q2 then sees almost all of VIN "
                                       "(~5–6 W during a pulse). In pulsed use this is harmless; continuous operation "
                                       "ends with the 85 °C trip. A short is not flagged as a fault."],
        ["Q2 fails short", "The current is no longer controlled: the over-current trip → FAULT → Q10 and K1 short the "
                           "output, which protects the diode. The supply then feeds R40/R41/Q2/Q10 until F1 or the "
                           "adapter's limit acts, and R41 may be overstressed."],
        ["Reverse voltage or ESD on the DE-9", "Disarmed: shorted by K1. Armed: D6 (reverse) and D7 (12 V TVS) clamp; "
                                               "R44/C32 damp the cable."],
    ], widths=["27%", "73%"]))
    a('<p class="note">None of these sequences has been simulated at system level or tried on hardware. The bring-up '
      'plan (§11) exercises the main ones with a dummy load and a scope before the diode is connected.</p>')

    # ---------------------------------------------------------------- 6. simulation
    a("""<h1>6. Simulation</h1>
<p><span class="mono">sim/run_sims.py</span> runs the current source in ngspice with the vendor models (TI OPA2192
and INA180A1, Infineon IRFR9024N). The laser diode is modelled as a diode with 5–6 V at 0.6 A (N = 12,
R<sub>S</sub> = 1 Ω, C<sub>J</sub> = 100 pF); it is not a measured BDR-209 model. The cable is 0.35 µH or 2 µH
in <i>each</i> conductor (each with 0.15 Ω, and 100 Ω in parallel to model losses) and 150 pF across the diode,
with the 22 Ω / 47 nF snubber at the driver. The testbench's component values were checked against
<span class="mono">design.py</span> (R31, R32, R33, C31, R34, R35, R30, R40, R41, R17/C12, R44/C32).
Corners: FET transconductance KP ×0.5…×2 (1.3, 2.6, 5.2), cable 0.35 µH and 2 µH per conductor (generous for
0.5 m and 2.5 m of twisted pair), supply 8.5–9 V, idle 5–100 mA, pulse 100–700 mA. The parallel 100 Ω adds damping
that a real cable may not have; review point 3.</p>""")
    if big:
        rows = []
        for c in big:
            kp, lc, vin, ip, dl, rise, ov, st, fall = c
            if dl.startswith("0.00") or "nan" in fall:
                dl, fall = "—", "—"
            rows.append([kp, lc.replace("uH", "µH"), vin, ip.replace("->", "→"), dl.replace("us", "µs"),
                         rise.replace("us", "µs"), ov, st.replace("us", "µs"), fall.replace("us", "µs")])
        a(f"<h2>6.1 Large-signal 100 µs pulses (re-run {DATE:%d %b %Y})</h2>")
        a(table(["KP", "L cable", "VIN", "idle → pulse", "delay", "10–90 % rise", "overshoot", "1 % settle", "fall to 10 %"],
                rows, cls="num"))
        a("<p>Delay is from the TTL edge to 10 % of the pulse current. “—”: not defined when the idle current is "
          "above 10 % of the pulse (the last two rows).</p>")
    if small:
        a("<h2>6.2 Small-signal 5 % steps at 600 mA</h2>")
        a(table(["KP", "L cable", "step", "overshoot", "2 % settle"],
                [[c[0], c[1].replace("uH", "µH"), c[2].replace("->", "→"), c[3], c[4].replace("us", "µs")]
                 for c in small], cls="num"))
        a("<p>A small step is not slew-limited, so its overshoot shows the phase margin: 0.0 % overshoot at every "
          "corner indicates a well-damped loop (more than ~70° phase margin).</p>")
    if not big:
        a('<p class="warn">Simulation results were not regenerated for this build (no vendor models); see '
          '<span class="mono">docs/design-notes.md</span> §3 for the last results.</p>')
    a(fig(img("docs/img/sim_pulse.png"), "Simulated 100 µs pulse, 20 mA idle → 600 mA, 2 µH cable, nominal FET: "
          "diode current, I MON and the setpoint.", width="82%"))
    a("""<p>The bandwidth (~80 kHz) is deliberately modest. It is fast enough for 100 µs pulses, with ~10 µs to full
power, and slow enough to stay stable with any reasonable cable and FET. For much shorter pulses, reduce C31 and
re-check stability with <span class="mono">run_sims.py</span>.</p>
<p class="note"><b>Not simulated:</b> the protection and arming logic (comparators, latch, relay, crowbar, power-up
and power-down); thermal behaviour; the TTL front end (U14, U5) beyond an ideal setpoint edge; a measured diode model;
cables longer than ~2.5 m.</p>""")

    # ---------------------------------------------------------------- 7. pcb
    a('<h1>7. PCB</h1><h2>7.1 Stack-up and rules</h2>')
    a(table(["item", "value"], [
        ["Size, layers", "160 × 100 mm, 4 layers, 1.6 mm, JLC04161H-7628 stack-up; outer copper 1 oz, inner 0.5 oz"],
        ["Layer use", "F.Cu signals + GND pour · <b>In1 solid GND</b> · <b>In2 solid +5 V</b> · B.Cu signals + GND pour"],
        ["Rules", "0.15 mm minimum track and clearance; vias 0.3 mm drill / 0.6 mm pad, plugged; copper to edge 0.3 mm"],
        ["Tracks", f"{k['segments']} segments, {k['vias']} vias; widths 0.25–0.5 mm for signals, 1.5 mm for the laser "
                   "current path"],
        ["Planes", "every GND/+5 V SMD pad has its own via to its plane; GND stitching vias every ~7.5 mm"],
        ["Thermal", "Q2's drain tab sits in a 12 × 8 mm LD_OUT copper area on both outer layers, joined by 15 thermal "
                    "vias; the NTC RT1 is beside it"],
    ], widths=["18%", "82%"]))
    a("""<h2>7.2 Layout features</h2>
<p>The laser current path runs from the input through the bulk capacitors, R40, R41, Q2 and the relay/clamps to the
DE-9. It is 1.5 mm copper on F.Cu, necked only at the pads, directly above the GND plane that carries the return
current. All panel connectors sit on the board edges. BNCs, pots, LEDs and the toggle are on the front edge, with
their flanges or mounting faces on the edge line. The DE-9, DC jack and interlock jack are on the rear edge. M3
holes H1–H4 match the enclosure standoffs.</p>""")
    a(fig(img("hardware/fab/ld405-driver_top.png"), "Top view (3D render; BNCs, pots, switch, jacks and side LEDs use "
          "simplified models).", width="92%"))
    a(fig(img("docs/review/layout_current_path.png"), "Copper carrying the laser current, top and bottom layers."))
    a('<div class="two">' +
      fig(img("docs/review/layout_kelvin.png"), "R40 and its Kelvin sense pair to U8 and the error amplifier: net ties "
          "NT1/NT2 sit on R40's own pads, so the sense pair carries no load current.") +
      fig(img("docs/review/layout_ttl_input.png"), "TTL input path from J2 through R21/D4/C15 to U14 and U5.") +
      "</div>")
    ec, dc = k["erc_counts"], k["drc_counts"]
    a(f"""<h2>7.3 Checks (run {DATE:%d %b %Y}, KiCad {E(k['kicad'])})</h2>
<ul>
<li>ERC: {ec[1]} errors, {ec[2]} warnings.</li>
<li>DRC with schematic parity: {dc[0]} violations, {dc[1]} unconnected pads, {dc[2]} footprint errors, no parity
issues. The <span class="mono">lib_footprint_mismatch</span> check is set to <i>ignore</i>. The generator re-places
reference designators and trims footprint silkscreen at the board edge, so no footprint is byte-identical to its
library copy.</li>
</ul>
<h2>7.4 How the board was generated</h2>
<p>The schematic and the board are generated by scripts from one parts-and-nets file
(<span class="mono">tools/design.py</span>) and a placement file. Routing was done by a purpose-written two-layer A* maze
router on a 0.1 mm grid with clearance-inflated obstacle maps from the real pad shapes. It uses tapered power tracks,
pre-routed Kelvin taps, plane fan-outs and rip-up-and-retry. Zones are then filled by KiCad. The result is checked only
by KiCad's DRC and parity check and by the renders in this document. A human eye on the routing is therefore
particularly welcome (review point 5).</p>""")

    # ---------------------------------------------------------------- 8. connectors etc.
    a('<h1>8. Connectors, cable, enclosure, grounding</h1><h2>8.1 Panels</h2>')
    a(table(["front", "function"], [
        ["TTL IN (BNC)", "high = pulse current, low/unconnected = idle current"],
        ["I MON (BNC)", "measured diode current, 1 V/A (high-Z scope input)"],
        ["SET MON (BNC)", "pulse setpoint, 1 V/A; shows what a pulse will deliver before firing"],
        ["PULSE, IDLE (knobs)", "pulse current 0 → full scale (600 or 700 mA); idle current 5 → 104 mA"],
        ["ENABLE (toggle)", "arm/disarm, and reset after a fault (off → on)"],
        ["LEDs", "POWER (green); ARMED (yellow: relay open, source enabled); EMISSION (blue: &gt; ~18 mA, stretched so "
                 "100 µs pulses are visible); FAULT (red, latched)"],
    ], widths=["24%", "76%"]))
    a(table(["rear", "function"], [
        ["LD OUT (DE-9 female)", "8 = anode, 3 = cathode/ground, 1–5 = interlock loop (Thorlabs CG compatible)"],
        ["INTERLOCK (3.5 mm)", "must be closed (tip–sleeve shorted) to arm"],
        ["9V DC", "9 V, ≥ 1.5 A, centre positive"],
    ], widths=["24%", "76%"]))
    a(fig(img("docs/review/panel_front.png"), "Front panel from outside (white: through; light blue: engraving and "
          "recesses; grey: the parts behind)."))
    a(fig(img("docs/review/panel_rear.png"), "Rear panel from outside."))
    a("<h2>8.2 Diode cable</h2>")
    a(fig(img("docs/review/cable_de9.png"), "The diode cable, made by the user: DE-9 male, pin 8 → anode, pin 3 → "
          "cathode, wire link 1–5 inside the hood (unplugging trips the driver); screen, if any, to pin 3 at the driver "
          "end only.", width="86%"))
    a("""<h2>8.3 Enclosure</h2>
<p>The OpenSCAD model is generated from the board placement, with connector axis heights from the datasheets. The
front and rear panels are 2.5 mm plates held in grooves by the base and lid, so they are fitted to the board's
connectors before the board goes into the base. To be printed in MJF PA12 at JLC3DP. JLC3DP's thin-wall heatmap
flagged the lid posts, so all four parts were reworked and checked for walls under 1.2 mm; only the ridges between
engraved letters remain. Hardware: 4 × M3×16 countersunk with nuts (PCB), 4 × M3×10 countersunk with nuts (lid).</p>""")
    a('<div class="two">' + fig(img("enclosure/preview_front.png"), "Assembly preview, front.") +
      fig(img("enclosure/preview_rear.png"), "Assembly preview, rear.") + "</div>")
    a("""<h2>8.4 Grounding</h2>
<p>Board GND is common to the diode cathode (DE-9 pins 3 and 5 and the shell), the shells of the three BNCs, the
3.5 mm jack sleeve and the DC-jack negative. The 9 V adapter output is SELV-isolated from the mains; whether its
negative is tied to mains earth depends on the adapter. In use, the BNC shells connect the board to ARTIQ and to the
scope, and so to lab earth. The instructions say the diode module's case must not touch anything except through the
cable, because the cathode is ground. This is review point 6.</p>""")

    # ---------------------------------------------------------------- 9. manufacturing
    a('<h1>9. Manufacturing</h1>')
    a(table(["item", "choice"], [
        ["PCB", "JLCPCB: 4 layers, 1.6 mm, 1 oz outer / 0.5 oz inner, lead-free HASL (or ENIG), vias plugged, "
                "min via 0.3 mm"],
        ["Assembly", "JLCPCB Standard PCBA, top side only. The through-hole connectors, pots and toggle are "
                     "hand-soldered by JLCPCB. JP1 is left open (600 mA range)."],
        ["BOM", f"{n_lines} lines, {n_parts} parts ({n_cpl} placements), all with LCSC part numbers; BOM and CPL "
                "uploaded to JLCPCB and checked in its placement preview on 29 Oct 2026"],
        ["Placement", "CPL rotations include the usual KiCad → JLC offsets (SOT-23 +180°, SOIC +270°), offsets for "
                      "the panel parts (BNCs +90°; pots, toggle and DE-9 +270°) and per-part corrections found in "
                      "JLCPCB's placement preview (C1/C2 0° rather than the usual +180° for electrolytics, K1 +270°, "
                      "Q2 +90°, D10 +270°)"],
        ["Enclosure", "JLC3DP, MJF PA12 (black): base, lid, front and rear panels (STL in print orientation)"],
        ["Off-board", "Mean Well GST25A09-P1J 9 V adapter; DE-9 male plug + hood; 3.5 mm mono plug; knobs for 6 mm D "
                      "shafts; M3 screws and nuts; rubber feet"],
    ], widths=["16%", "84%"]))
    a(fig(img("docs/review/jlc_markers_overview.png"), "Where JLCPCB's placement-preview markers must land: a dot on "
          "pin 1, and + / − on anodes, cathodes and the electrolytics' terminals. The owner compared JLCPCB's preview "
          "with this map; the rotation corrections in the table above came out of that check.", width="96%"))

    # ---------------------------------------------------------------- 10. verification
    a('<h1>10. Verification status</h1>')
    a(table(["check", "how", "result"], [
        ["Electrical rules", f"KiCad ERC ({DATE:%d %b %Y})", f"{ec[1]} errors, {ec[2]} warnings"],
        ["Layout rules, connectivity", f"KiCad DRC with schematic parity ({DATE:%d %b %Y})",
         f"{dc[0]} violations, {dc[1]} unconnected, parity clean"],
        ["Current source", "ngspice with vendor models, 11 large-signal + 6 small-signal corners (§6)",
         "no overshoot, settles in ≤ 12 µs at all corners; re-run for this package with identical results"],
        ["Pinouts of active parts", "renders of every footprint with pad numbers and nets, compared with the "
         "manufacturers' drawings by the project owner (review items A1–A7)",
         "A1–A3, A5, A6 confirmed. A4 (REF3030 drawing labels) and A7 (side LEDs: the original part's datasheet "
         "contradicted itself, so the part was replaced) were flagged and fixed, not yet re-confirmed."],
        ["Panel-part footprints", "hole sizes and pin positions vs datasheets (B1–B6)", "confirmed"],
        ["Polarity / pin 1 of 40 parts", "polarity map and CPL rotations (A2), then JLCPCB's placement preview",
         "confirmed; rotation corrections for C1/C2, K1, Q2 and D10 made after the preview (§9)"],
        ["Enclosure fit", "cross-sections through every panel hole, panel faces, lid clearance (C1–C5)",
         "C1, C3, C5 confirmed. C2 (toggle hole, redrawn and widened) and C4 (DC jack hole 0.5 mm low) were flagged "
         "and fixed, not yet re-confirmed."],
        ["Schematic, current path, Kelvin sense, TTL input, diode cable", "owner's review of renders (D1–D4, E1)",
         "confirmed"],
        ["3D-print printability", "JLC3DP thin-wall heatmap + own voxel thickness checks", "no wall under 1.2 mm except "
                                                                                          "the ridges between engraved letters"],
    ], widths=["22%", "40%", "38%"]))
    a("""<p class="warn"><b>Not verified:</b> no hardware has been built; there is no measured diode data or datasheet;
the protection and arming logic, the power-up and power-down transients and the thermal behaviour are reasoned, not
simulated or measured; EMC has not been assessed; and the routing is checked only by DRC and the renders above.
It is also inferred, not confirmed, that “lever up” on the ENABLE toggle (Dailywell M7) is the 2–1 (ENABLE)
position. The bench plan below covers most of this before the diode is connected.</p>""")

    # ---------------------------------------------------------------- 11. bring-up
    a("""<h1>11. Bring-up and test plan</h1>
<ol>
<li><b>Without the diode.</b> Plug in the DE-9 cable with a <b>dummy load</b> instead of the diode (5 × 1N5408 in
series plus 1 Ω 2 W, ≈ 5–6 V at 0.6 A; pulsed use only) and the interlock plug. Turn both knobs fully anticlockwise.</li>
<li>Power up: POWER on, FAULT on. ENABLE off → on: ARMED on, FAULT off.</li>
<li>Scope on I MON (1 V/A). Turn IDLE: the trace moves between ~5 and ~104 mV.</li>
<li>Drive TTL IN with 100 µs pulses at ≤ 10 Hz. Turn PULSE up: I MON shows the pulses, and SET MON shows the level
a pulse will reach. Check that the pulse at full scale (≈ 600 mV on I MON) is flat with no ringing.</li>
<li>Optional 700 mA range: bridge JP1 (near U2).</li>
<li>Disconnect one lead of the dummy load at the far end with the DE-9 still plugged in: FAULT must latch
(open-circuit detection). Unplugging the DE-9 must also latch FAULT (cable interlock).</li>
<li><b>Suggested additions for this review:</b> with a second scope channel directly across the dummy load, capture
LD_OUT during arm, disarm, an interlock opening, the 9 V adapter being unplugged while armed and while pulsing, and
plugging the adapter back in. No step or spike should appear beyond the set current. Check that I MON agrees with a
current probe or shunt, and that Q2's copper stays cool at the intended duty cycle.</li>
<li>Set both knobs to minimum, <b>disarm</b>, connect the diode, then arm. Calibrate optical power with a thermal
power meter at a known duty cycle (P̄ ≈ P<sub>peak</sub> · D) or with a fast photodiode. Increase PULSE slowly while
reading I MON, and do not exceed the diode's current rating.</li>
</ol>
<h1>12. Known limitations</h1>
<ul>
<li>Pulse length is unlimited (CW works), but at 600–700 mA continuous the pass transistor dissipates ~2 W and will
eventually trip the 85 °C sensor; use a low duty cycle as intended.</li>
<li>The minimum idle current is ~5 mA (the diode glows faintly). For a darker idle, replace R16 (1 k) with 0 Ω (IDLE
then spans 0–100 mA).</li>
<li>The 3.5 mm interlock input expects a closed contact; the DE-9 interlock requires pins 1 and 5 linked in the diode
cable.</li>
<li>The relay is rated 1 A. Do not raise the current range above ~800 mA without re-checking K1, R40/R41 dissipation
and Q2's SOA.</li>
<li>The ENABLE toggle is held by the board only (its bushing passes through the panel without a nut).</li>
</ul>""")

    # ---------------------------------------------------------------- appendices
    a('<h1 class="sec">Appendix A. Bill of materials</h1>')
    a(f"<p>{n_lines} lines, {n_parts} parts; JLCPCB/LCSC part numbers as uploaded. File: "
      "<span class='mono'>manufacturing/ld405-driver_bom_full.csv</span>.</p>")
    rows = []
    for r in bom:
        rows.append([r["Qty"], E(r["Value"]), E(r["Designators"]), E(r["Manufacturer part"]), E(r["LCSC"])])
    a(table(["qty", "value", "designators", "manufacturer part", "LCSC"], rows, cls="small",
            widths=["5%", "18%", "41%", "24%", "12%"]))
    a('<h1>Appendix B. Contents of LD405_review_pack.zip</h1>')
    a(table(["folder", "contents"], [[f"<span class='mono'>{E(f)}</span>", E(d)] for f, d in PACK_INDEX],
            widths=["26%", "74%"]))
    a("""<h1>Appendix C. Schematic and assembly drawing</h1>
<p>The next page is the complete schematic as one A0 sheet (vector: zoom in). It is followed by the assembly
drawing (top fab layer). Both are also in the zip as separate files.</p>
<p>The schematic is generated from <span class="mono">design.py</span>. It is drawn as functional blocks in which
parts connect through net labels rather than wires, so the block diagram (§3) and the net names used in §4–§5 are
the map to it. KiCad's net highlighting in the project (zip: <span class="mono">kicad/</span>) or
<span class="mono">source/tools/design.py</span>, which lists every pin's net, may be quicker to follow.</p>""")
    return "\n".join(s)


PACK_INDEX = [
    ("00_README.txt", "what this package is and where to start"),
    ("LD405_design_review.pdf", "the review document: start here"),
    ("schematic/", "ld405-driver_schematic.pdf (A0, vector)"),
    ("pcb/", "layer plots (F.Cu, In1.Cu, In2.Cu, B.Cu, silkscreen, fab), assembly drawing, 3D renders"),
    ("manufacturing/", "the files uploaded to JLCPCB: Gerber/drill zip, BOM, CPL (with rotation offsets), full BOM"),
    ("kicad/", "KiCad 9 project (schematic, PCB, project file, custom footprints and 3D models)"),
    ("checks/", "KiCad ERC and DRC reports from this build"),
    ("simulation/", "ngspice testbench and corner script, results of this build, simulated pulse plot; vendor "
                    "models are fetched by get_models.sh"),
    ("enclosure/", "OpenSCAD source, STL files (print orientation), previews"),
    ("review_renders/", "the review renders: footprints vs datasheets, polarity and JLC marker maps, copper "
                        "close-ups, panel cross-sections, diode cable (index in README.md)"),
    ("docs/", "design notes, ordering and assembly guide (README), ARTIQ example"),
    ("source/", "the generator scripts (design.py holds every part, value, LCSC number and connection)"),
]


# ------------------------------------------------------------------ pdf + zip
def build_pdf(body, k, tmp, h):
    page = (f"<!doctype html><html><head><meta charset='utf-8'><title>LD405 design review</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")
    src = os.path.join(tmp, "review.html")
    open(src, "w").write(page)
    main = os.path.join(tmp, "body.pdf")
    footer = f"LD405 pulse driver · design review · rev {design.REV} · {DATE:%d %b %Y} · commit {h}"
    run("node", os.path.join(HERE, "html2pdf.js"), src, main, footer)
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for f in (main, k["schematic"], os.path.join(FAB, design.PROJECT + "_assembly.pdf")):
        w.append(PdfReader(f))
    w.add_metadata({"/Title": "LD405 pulse driver - design review package",
                    "/Subject": "405 nm laser diode pulse driver (BDR-209), board rev " + design.REV,
                    "/Keywords": "laser diode driver, REMPI, ARTIQ, design review"})
    out = os.path.join(OUT, PDF_NAME)
    with open(out, "wb") as f:
        w.write(f)
    return out


README_TXT = """LD405 pulse driver - design review package
=========================================

A TTL-gated constant-current driver for a 405 nm laser diode (BDR-209, ~0.9 W),
used as the second, ionising step of two-photon REMPI during ablation loading
of an ion trap. Board revision {rev}; package built {date} from commit {h}
of ParsaIQT/Fiber-solarisation (folder laser-pulse-driver/).

Status: pre-production. Nothing has been built yet; the boards are to be
assembled by JLCPCB.

Start with LD405_design_review.pdf. Section 1 lists the questions we would most
like answered; section 10 lists what has and has not been verified.

To open the design: kicad/ld405-driver.kicad_pro in KiCad 9 (the custom
footprints and 3D models are in kicad/lib/ and are found through the project's
fp-lib-table; everything else is KiCad's standard library).

To re-run the simulations: install ngspice and numpy, then in simulation/
run ./get_models.sh (downloads the TI and Infineon models) and
python3 run_sims.py.

Folders:
{index}
"""


def build_zip(k, sims, pdf, h):
    root = "LD405_review_pack/"
    out = os.path.join(OUT, ZIP_NAME)
    z = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9)

    def add(src, dst):
        z.write(src, root + dst)

    def add_tree(src_dir, dst_dir, skip=()):
        for d, _, files in sorted(os.walk(src_dir)):
            if "__pycache__" in d:
                continue
            for f in sorted(files):
                if any(re.search(p, f) for p in skip):
                    continue
                p = os.path.join(d, f)
                add(p, os.path.join(dst_dir, os.path.relpath(p, src_dir)))

    index = "\n".join(f"  {f:26s} {d}" for f, d in PACK_INDEX)
    z.writestr(root + "00_README.txt", README_TXT.format(rev=design.REV, date=DATE, h=h, index=index))
    add(pdf, PDF_NAME)
    add(k["schematic"], "schematic/ld405-driver_schematic.pdf")
    add(k["layers"], "pcb/ld405-driver_layers.pdf")
    for f in ("assembly.pdf", "top.png", "bottom.png", "iso.png"):
        add(os.path.join(FAB, f"{design.PROJECT}_{f}"), f"pcb/{design.PROJECT}_{f}")
    for f in ("gerbers_jlcpcb.zip", "bom_jlcpcb.csv", "cpl_jlcpcb.csv", "bom_full.csv"):
        add(os.path.join(FAB, f"{design.PROJECT}_{f}"), f"manufacturing/{design.PROJECT}_{f}")
    add(os.path.join(FAB, "README.md"), "manufacturing/README.md")
    for f in (".kicad_pro", ".kicad_sch", ".kicad_pcb"):
        add(os.path.join(HW, design.PROJECT + f), "kicad/" + design.PROJECT + f)
    add(os.path.join(HW, "fp-lib-table"), "kicad/fp-lib-table")
    add_tree(os.path.join(HW, "lib"), "kicad/lib")
    add(k["erc"], "checks/erc_report.txt")
    add(k["drc"], "checks/drc_report.txt")
    sim = os.path.join(ROOT, "sim")
    for f in ("run_sims.py", "ld_driver_tb.py", "get_models.sh", ".spiceinit"):
        add(os.path.join(sim, f), "simulation/" + f)
    if sims[2]:
        add(sims[2], f"simulation/results_{DATE:%Y-%m-%d}.txt")
    add(os.path.join(ROOT, "docs", "img", "sim_pulse.png"), "simulation/sim_pulse.png")
    add(os.path.join(ROOT, "enclosure", "ld405_enclosure.scad"), "enclosure/ld405_enclosure.scad")
    add_tree(os.path.join(ROOT, "enclosure", "stl"), "enclosure/stl")
    for f in ("preview_front.png", "preview_rear.png"):
        add(os.path.join(ROOT, "enclosure", f), "enclosure/" + f)
    add_tree(os.path.join(ROOT, "docs", "review"), "review_renders")
    add(os.path.join(ROOT, "docs", "design-notes.md"), "docs/design-notes.md")
    add(os.path.join(ROOT, "README.md"), "docs/README.md")
    add(os.path.join(ROOT, "artiq", "ld405_pulse.py"), "docs/artiq/ld405_pulse.py")
    add_tree(HERE, "source/tools", skip=(r"\.pyc$", r"\.so$", r"\.o$"))
    z.close()
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    h, branch = git_info()
    with tempfile.TemporaryDirectory() as tmp:
        print("KiCad exports and checks")
        k = kicad_outputs(tmp)
        print("   ERC", k["erc_counts"], "DRC", k["drc_counts"])
        print("simulations" + (" (skipped)" if "--no-sims" in sys.argv else ""))
        sims = simulations(tmp, "--no-sims" in sys.argv)
        print("review document")
        pdf = build_pdf(document(k, sims, (h, branch), tmp), k, tmp, h)
        print("  ", os.path.relpath(pdf, ROOT))
        z = build_zip(k, sims, pdf, h)
        print("  ", os.path.relpath(z, ROOT))


if __name__ == "__main__":
    main()
