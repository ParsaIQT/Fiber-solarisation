#!/usr/bin/env python3
"""Figures for the design-review PDF (make_review_pack.py): the block diagram
(hand-placed SVG) and the arming/disarming timing diagram (matplotlib SVG)."""
import math
from html import escape

INK, MUTED = "#1f2933", "#52606d"
LANES = {"power": ("#fff4e0", "#d97706"), "path": ("#e8f1fb", "#2563eb"),
         "prot": ("#fdecec", "#c2410c"), "mon": ("#e9f7ef", "#15803d")}


def _box(x, y, w, h, title, lines, lane):
    fill, edge = LANES[lane]
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="white" stroke="{edge}" stroke-width="1.6"/>',
         f'<text x="{x + 9}" y="{y + 19}" font-size="14.5" font-weight="650" fill="{INK}">{escape(title)}</text>']
    for i, ln in enumerate(lines):
        s.append(f'<text x="{x + 9}" y="{y + 37 + 15.5 * i}" font-size="12" fill="{MUTED}">{escape(ln)}</text>')
    return "\n".join(s)


def _arrow(pts, label=None, lx=0, ly=0, dashed=False, color="#374151", anchor="start"):
    d = "M " + " L ".join(f"{x},{y}" for x, y in pts)
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    s = f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.5"{dash} marker-end="url(#ah)"/>'
    if label:
        s += (f'<text x="{lx}" y="{ly}" font-size="11.5" fill="{color}" text-anchor="{anchor}" '
              f'font-style="italic">{escape(label)}</text>')
    return s


def block_diagram():
    W, H = 1008, 716
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="Inter, sans-serif">',
           '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#374151"/></marker></defs>']
    for y0, y1, lane, name in ((8, 128, "power", "POWER"), (138, 430, "path", "SETPOINT AND CURRENT SOURCE"),
                               (440, 712, "prot", "PROTECTION, ARMING, MONITORS")):
        fill, edge = LANES[lane]
        out.append(f'<rect x="4" y="{y0}" width="{W - 8}" height="{y1 - y0}" rx="10" fill="{fill}" stroke="none"/>')
        out.append(f'<text transform="translate(19,{(y0 + y1) / 2}) rotate(-90)" text-anchor="middle" font-size="10.5" '
                   f'font-weight="700" letter-spacing="1.2" fill="{edge}">{name}</text>')
    # power lane
    out.append(_box(30, 34, 126, 80, "9 V DC in", ["J1, mains adapter", "≥ 1.5 A"], "power"))
    out.append(_box(180, 34, 206, 80, "Input protection", ["F1 2 A PTC", "Q1 reverse-polarity P-FET", "D2 SMAJ13A TVS"], "power"))
    out.append(_box(410, 34, 170, 80, "VIN ≈ 9 V", ["2 × 220 µF bulk:", "supplies the pulses"], "power"))
    out.append(_box(604, 34, 170, 80, "+5 V (U1 L78M05)", ["logic, comparators,", "relay coil, monitors"], "power"))
    out.append(_box(798, 34, 196, 80, "3.000 V ref (U2)", ["REF3030, ±0.2 %:", "sets the current scale"], "power"))
    for x0, x1 in ((156, 180), (386, 410), (580, 604), (774, 798)):
        out.append(_arrow([(x0, 74), (x1 - 2, 74)]))
    out.append(_arrow([(840, 114), (840, 142), (140, 142), (140, 164)], "VREF", 846, 134))
    # setpoint row
    out.append(_box(30, 166, 222, 96, "Full scale VFS", ["R10/R11 0.1 %: 2.40 V = 600 mA", "JP1 bridged: 2.80 V = 700 mA",
                                                        "soft start: C11, τ = 80 ms"], "path"))
    out.append(_box(276, 166, 214, 96, "PULSE and IDLE levels", ["RV1 → U3B: VP = 0–600 mA", "RV2 → U4A: VI = 5–104 mA",
                                                                 "(both scale with VFS)"], "path"))
    out.append(_box(514, 166, 222, 96, "TTL select (U5 switch)", ["J2 TTL IN → R21, D4 clamps,", "C15 → U14 Schmitt trigger",
                                                                  "high = VP, low/open = VI"], "path"))
    out.append(_box(760, 166, 234, 96, "Level shifter (U7B, Q4)", ["R31 3.00 k / R32 150 Ω, 0.1 %:", "V(VIN) − V(REF) = VSP / 20",
                                                                   "R17/C12 filter on VSP"], "path"))
    for x0, x1 in ((252, 276), (490, 514), (736, 760)):
        out.append(_arrow([(x0, 214), (x1 - 2, 214)]))
    # current path row, right to left
    out.append(_box(760, 292, 234, 120, "Error amplifier (U7A)", ["OPA2192 on VIN, ±25 µV offset", "integrator R33 1 k / C31 220 p",
                                                                  "→ R34 100 Ω → Q2 gate", "holds I·R40 = VSP / 20"], "path"))
    out.append(_box(476, 292, 260, 120, "Pass stage (high side)", ["VIN → R40 0.2 Ω shunt (Kelvin)", "→ R41 1 Ω → Q2 IRFR9024N",
                                                                   "I_LD = 0.25 A/V × VSP", "Q2 tab: 12 × 8 mm copper",
                                                                   "with NTC RT1 beside it"], "path"))
    out.append(_box(196, 292, 256, 120, "Output protection", ["K1 NC contacts short LD_OUT", "whenever disarmed or unpowered",
                                                              "Q10 crowbar, on when disarmed", "D6 reverse clamp, D7 SMAJ12A",
                                                              "R44/C32 22 Ω / 47 nF snubber"], "path"))
    out.append(_box(30, 292, 142, 120, "LD OUT (J5)", ["DE-9 socket:", "8 = anode", "3 = cathode, GND", "1–5 = cable loop",
                                                       "→ BDR-209 diode"], "path"))
    out.append(_arrow([(877, 262), (877, 290)], "VSP / 20", 884, 282))
    for x0, x1 in ((760, 736), (476, 452), (196, 172)):
        out.append(_arrow([(x0, 352), (x1 + 2, 352)]))
    # protection lane
    out.append(_box(30, 468, 236, 112, "Monitors", ["U8 INA180 on the Kelvin taps", "→ I MON BNC, 1 V/A",
                                                    "VP ÷ 4 → SET MON BNC, 1 V/A", "(both into high impedance)"], "mon"))
    out.append(_box(290, 468, 252, 112, "Fault comparators (U11)", ["over-current: > 804 mA", "compliance: gate < 1.98 V ≥ 10 µs",
                                                                     "over-temperature: RT1 ≥ 85 °C", "(+ EMISSION LED > 18 mA)"], "prot"))
    out.append(_box(290, 598, 252, 102, "Interlocks", ["J6 3.5 mm: closed = OK", "DE-9 pins 1–5 linked in the",
                                                       "diode cable (unplug = fault)"], "prot"))
    out.append(_box(566, 468, 200, 232, "Fault latch (U13, U12)", ["any fault → FAULT, latched", "power-up: held in FAULT",
                                                                    "for 0.2 s (R78/C43)", "re-arm: ENABLE off → on",
                                                                    "with no fault present", "", "SW1 ENABLE switch",
                                                                    "EN_REQ = ENABLE ∧ ¬FAULT"], "prot"))
    out.append(_box(790, 468, 204, 232, "Arming outputs", ["EN_REQ → Q9 → K1 coil:", "opens the output short", "",
                                                           "EN_LOOP 20 ms later", "(R79/C45; no delay on the", "way down, D15) turns off",
                                                           "Q10 and the gate clamp", "(Q6–Q8), releases the", "integrator (Q5) and the",
                                                           "soft start (Q3)"], "prot"))
    out.append(_arrow([(560, 412), (560, 446), (150, 446), (150, 466)], "Kelvin sense", 566, 432))
    out.append(_arrow([(650, 412), (650, 454), (416, 454), (416, 466)], "gate voltage, RT1", 656, 444))
    out.append(_arrow([(266, 524), (288, 524)]))
    out.append(_arrow([(542, 524), (564, 524)]))
    out.append(_arrow([(542, 649), (554, 649), (554, 548), (564, 548)]))
    out.append(_arrow([(766, 584), (788, 584)]))
    out.append(_arrow([(900, 468), (900, 414)], "gate clamp", 906, 446, dashed=True, color="#c2410c"))
    out.append("</svg>")
    return "\n".join(out)


def timing_diagram(path):
    """Arming at t = 0 and disarming at t = 300 ms (schematic time scale)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams["font.family"] = "Inter"
    plt.rcParams["svg.fonttype"] = "none"
    t = np.linspace(-40, 360, 4001)
    on, off, d_rly, d_loop, tau = 0.0, 300.0, 4.0, 20.0, 80.0
    ena = ((t >= on) & (t < off)).astype(float)
    short = 1 - ((t >= on + d_rly) & (t < off + d_rly)).astype(float)
    loop = ((t >= on + d_loop) & (t < off)).astype(float)
    vfs = np.where((t >= on + d_loop) & (t < off), 1 - np.exp(-(t - on - d_loop) / tau), 0.0)
    cur = 0.18 * vfs
    for tp in (150.0, 250.0):              # two TTL pulses (100 us: drawn wider to be visible)
        k = (t >= tp) & (t < tp + 2.0)
        cur[k] = vfs[k]
    rows = [("ENABLE (SW1)\n= EN_REQ, K1 coil", ena, "#374151"),
            ("K1 output short\n(NC contacts)", short, "#b45309"),
            ("EN_LOOP\n(+20 ms)", loop, "#2563eb"),
            ("Q10 crowbar,\ngate clamp", 1 - loop, "#c2410c"),
            ("setpoint VFS\n(soft start)", vfs, "#7c3aed"),
            ("diode current\n(idle + 2 pulses)", cur, "#15803d")]
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for i, (name, y, c) in enumerate(rows):
        base = (len(rows) - 1 - i) * 1.5
        ax.fill_between(t, base, base + y, step=None, color=c, alpha=0.18, lw=0)
        ax.plot(t, base + y, color=c, lw=1.4)
        ax.text(-46, base + 0.45, name, ha="right", va="center", fontsize=8, color="#1f2933")
    for x, lab, ha in ((on, "ENABLE on\n(no fault)", "right"), (on + d_loop, "+20 ms", "left"),
                       (off, "ENABLE off\nor any fault", "center")):
        ax.axvline(x, color="#9aa5b1", lw=0.8, ls="--", zorder=0)
        ax.text(x + (-3 if ha == "right" else 3 if ha == "left" else 0), len(rows) * 1.5 - 0.15, lab, ha=ha,
                va="bottom", fontsize=7.5, color="#52606d")
    ax.annotate("relay contacts open after\nits operate time (a few ms)", (on + d_rly, 1.5 * 4 + 0.05), (55, 1.5 * 4 + 0.6),
                fontsize=7, color="#b45309", arrowprops=dict(arrowstyle="-", color="#b45309", lw=0.6))
    ax.text(294, 1.5 * 2 + 0.5, "crowbar and gate clamp act at once;\nthe relay recloses a few ms later", fontsize=7,
            color="#c2410c", ha="right", va="center")
    ax.text(203, 0.62, "pulses fired during\nthe soft start reach\nonly part of PULSE", fontsize=7, color="#15803d",
            ha="center", va="center")
    ax.set_xlim(-40, 360)
    ax.set_ylim(-0.3, len(rows) * 1.5 + 0.9)
    ax.set_yticks([])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("time (ms) - schematic: delays from R79/C45 and C11; relay timing not to scale", fontsize=8, color="#52606d")
    ax.tick_params(labelsize=7.5)
    fig.subplots_adjust(left=0.2, right=0.98, top=0.93, bottom=0.12)
    fig.savefig(path)
    plt.close(fig)
