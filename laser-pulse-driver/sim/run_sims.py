#!/usr/bin/env python3
"""Corner simulations of the LD405 current source (ngspice + vendor models).

  ./get_models.sh          # once: OPA2192, INA180A1, IRFR9024N models
  python3 run_sims.py      # prints the tables, writes ../docs/img/sim_*.png

Large signal: 100 us pulses from the idle current to the full-scale setpoint,
over pass-FET transconductance (KP x0.5 .. x2), cable inductance (0.35 and
2 uH, i.e. ~0.5 m and ~2.5 m of twisted pair), supply and setpoint.
Small signal: 5 % setpoint steps at 600 mA; their overshoot shows the loop's
phase margin (no slew limiting).
"""
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ld_driver_tb as L

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.normpath(os.path.join(HERE, "..", "docs", "img"))
T0 = 400e-6      # long enough for the idle current to settle after the UIC start


def tran(c):
    try:
        d = L.run(c, "tran", tstep=5e-9)
        m = L.tran_metrics(d, c.get("VHI", 2.4) / 4.0, t0=T0)
        t, i = d[:, 0], L.col(d, "i")
        m["idle"] = float(i[np.argmin(abs(t - (T0 - 1e-6)))])
        return c, m
    except Exception as e:                      # noqa: BLE001 - report and carry on
        return c, str(e)[:300]


def small_step(c):
    """5 % setpoint step at 570 -> 600 mA: the overshoot of a small step shows
    the loop's phase margin without slew-rate limiting hiding it."""
    try:
        d = L.run(c, "tran", tstep=5e-9)
        t, i = d[:, 0], L.col(d, "i")
        i0 = i[np.argmin(abs(t - (T0 - 1e-6)))]
        w = (t > T0) & (t < T0 + 60e-6)
        i1 = i[(t > T0 + 50e-6) & (t < T0 + 60e-6)].mean()
        over = (i[w].max() - i1) / (i1 - i0) * 100
        bad = np.where(np.abs(i[w] - i1) > 0.02 * (i1 - i0))[0]
        settle = t[w][bad[-1]] - T0 if len(bad) else 0.0
        return c, dict(i0=i0, i1=i1, over=over, settle=settle)
    except Exception as e:                      # noqa: BLE001
        return c, str(e)[:300]


def cases():
    out = []
    for kp in (1.3, 2.6, 5.2):
        for lc in (0.35e-6, 2e-6):
            out.append(dict(KP=kp, LCAB=lc, VHI=2.4, VLO=0.08, T0=T0))         # 20 mA -> 600 mA
    out.append(dict(KP=2.6, LCAB=2e-6, VHI=2.4, VLO=0.02, T0=T0))            # 5 mA idle
    out.append(dict(KP=2.6, LCAB=2e-6, VHI=2.8, VLO=0.08, T0=T0))            # 700 mA (JP1)
    out.append(dict(KP=2.6, LCAB=0.35e-6, VHI=2.8, VLO=0.08, T0=T0, VIN=8.5))  # low supply
    out.append(dict(KP=2.6, LCAB=0.35e-6, VHI=0.4, VLO=0.08, T0=T0))          # 100 mA pulse
    out.append(dict(KP=2.6, LCAB=0.35e-6, VHI=2.4, VLO=0.40, T0=T0))          # 100 mA idle
    return out


def plots(c_nom):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(IMG, exist_ok=True)
    d = L.run(c_nom, "tran", tstep=5e-9)
    t = (d[:, 0] - T0) * 1e6
    fig, ax = plt.subplots(2, 1, figsize=(9, 6.5), sharex=False)
    for a, (lo, hi) in zip(ax, ((-10, 120), (-1, 8))):
        a.plot(t, L.col(d, "i") * 1e3, label="laser diode current")
        a.plot(t, L.col(d, "imon") / 4 * 1e3, label="I MON (INA180) / 4 V/A", alpha=0.8)
        a.plot(t, L.col(d, "sp") / 4 * 1e3, "--", label="setpoint")
        a.set_xlim(lo, hi); a.set_ylabel("mA"); a.grid(alpha=0.3)
    ax[0].set_title("100 us pulse, 20 mA idle -> 600 mA, 2 uH cable (nominal FET)")
    ax[1].set_title("leading edge")
    ax[1].set_xlabel("time from TTL edge (us)"); ax[0].legend(loc="center right")
    fig.tight_layout(); fig.savefig(os.path.join(IMG, "sim_pulse.png"), dpi=90)
    plt.close(fig)


if __name__ == "__main__":
    os.chdir(HERE)
    cs = cases()
    with ProcessPoolExecutor(4) as ex:
        tr = list(ex.map(tran, cs))
        ss = list(ex.map(small_step, [dict(KP=kp, LCAB=lc, VLO=2.28, VHI=2.4, T0=T0, TW=60e-6)
                                       for kp in (1.3, 2.6, 5.2) for lc in (0.35e-6, 2e-6)]))
    print("| KP | L cable | Vin | idle -> pulse | delay | 10-90% rise | overshoot | 1% settle | fall |")
    print("|---|---|---|---|---|---|---|---|---|")
    for c, m in tr:
        if isinstance(m, str):
            print("|", c, "| FAILED", m, "|")
            continue
        print(f"| {c['KP']:g} | {c['LCAB'] * 1e6:.2g} uH | {c.get('VIN', 9.0):g} V | {m['idle'] * 1e3:.1f} -> "
              f"{m['final'] * 1e3:.0f} mA | {m['delay'] * 1e6:.2f} us | {m['rise'] * 1e6:.2f} us | "
              f"{m['over']:.1f} % | {m['settle'] * 1e6:.1f} us | {m['fall'] * 1e6:.2f} us |")
    print()
    print("| KP | L cable | step | overshoot | 2 % settle |")
    print("|---|---|---|---|---|")
    for c, m in ss:
        if isinstance(m, str):
            print("|", c, "| FAILED |")
            continue
        print(f"| {c['KP']:g} | {c['LCAB'] * 1e6:.2g} uH | {m['i0'] * 1e3:.0f} -> {m['i1'] * 1e3:.0f} mA | "
              f"{m['over']:.1f} % | {m['settle'] * 1e6:.1f} us |")
    if "--no-plots" not in sys.argv:
        plots(dict(KP=2.6, LCAB=2e-6, VHI=2.4, VLO=0.08, T0=T0))
