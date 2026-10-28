#!/usr/bin/env python3
"""ngspice testbench for the LD405 current source (see docs/design-notes.md).

High-side P-FET current source with direct shunt sensing:

  VIN -- RS -- src -- Q1(IRFR9024N) -- drn -- cable -- LD -- cable -- GND
  Error amp UE (OPA2192 @ VIN): +in = ref, -in = src (via RF), CF from out to -in, out -RG- gate
  Level shifter UL (OPA2192 @ VIN): +in = sp, out -RLG- 2N7002 gate, source -> RSET -> GND, drain = ref
  RREF from VIN to ref  =>  I_LD = Vsp * (RREF/RSET) / RS
"""
import subprocess, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "models")       # filled by get_models.sh

DEF = dict(
    VIN=9.0, RS=0.2, RDEG=1.0, RREF=150.0, RSET=3000.0, RF=1e3, CF=220e-12, RZ=0, RG=100, RGP=10e3,
    RLG=100, CSP=220e-12, RSP=1e3, LCAB=0.35e-6, RCAB=0.15, CCAB=150e-12,
    VLO=0.02, VHI=2.4, TW=100e-6, LD_N=12, LD_IS=6.2e-9, LD_RS=1.0, LD_CJ=100e-12,
    VTO=-3.5587, KP=2.59702, COUT=47e-9, RCOUT=22, CGD_EXTRA=0, CFF=0,
    OPAMP="OPAx192", T0=40e-6, TRAMP=5e-6,
)


def fet_model(p):
    m = open(os.path.join(MODELS, "irfr9024n.lib")).read()
    m = m.replace("VTO=-3.5587", f"VTO={p['VTO']}").replace("KP=2.59702", f"KP={p['KP']}")
    m = m.replace(".SUBCKT irfr9024n", ".SUBCKT q1var").replace(".ENDS irfr9024n", ".ENDS q1var")
    return m


def netlist(p, analysis="tran"):
    s = f"""* topology D testbench ({analysis})
.include models/OPAx192.LIB
.include models/ina180a1.lib
{fet_model(p)}
.options method=trap reltol=1e-3 abstol=1e-10 vntol=1e-5 itl4=200 rshunt=1e12
.subckt OPLIN inp inn vcc vee out
* linear op-amp: Aol=1e6, GBW=10MHz (pole 10Hz), 2nd pole 40MHz, Rout 60 ohm (OPA2192-like)
G1 0 n1 inp inn 1e-3
R1 n1 0 1e9
C1 n1 0 15.9p
E2 n2 0 n1 0 1
R2 n2 n3 1k
C2 n3 0 3.98p
E3 n4 0 n3 0 1
RO n4 out 60
.ends
.model DSCH D(IS=5e-7 RS=0.05 N=1.05 CJO=200p BV=40)
.model LDM D(IS={p['LD_IS']} N={p['LD_N']} RS={p['LD_RS']} CJO={p['LD_CJ']})
.model N7002 NMOS(LEVEL=1 VTO=1.8 KP=0.3 RD=1 RS=1 CGSO=20p CGDO=5p LAMBDA=0.01)
VINS vin_raw 0 {p['VIN']}
RSRC vin_raw vin 0.05
CBULK vin cb 470u IC={p['VIN']}
RESR cb 0 0.05
CMLCC vin 0 10u IC={p['VIN']}
V5 v5 0 5
RSNS vin src {p['RS']}
RDEG src fs {p['RDEG']}
XQ1 drn gate fs q1var
RGP vin gate {p['RGP']}
RG og gate {p['RG']}
"""
    if p.get("CGSX"):
        s += f"CGSX gate fs {p['CGSX']}\n"
    if p["CGD_EXTRA"]:
        s += f"CGDX gate drn {p['CGD_EXTRA']}\n"
    if p["COUT"]:
        s += f"COUT drn co {p['COUT']}\nRCOUT co 0 {p['RCOUT']}\n"
    s += f"""DREV 0 drn DSCH
VC drn drn_m 0
LC1 drn_m c1 {p['LCAB']}
RLC1 drn_m c1 100
RC1 c1 lda {p['RCAB']}
CCAB lda ldk {p['CCAB']}
DLD lda_s ldk LDM
SOPEN lda lda_s sw_ctl 0 SWOPEN
VSWC sw_ctl 0 PWL(0 1 {p.get('TOPEN',1)} 1 {p.get('TOPEN',1)+1e-9} 0 {p.get('TCLOSE',2)} 0 {p.get('TCLOSE',2)+1e-9} 1)
.model SWOPEN SW(VT=0.5 VH=0.1 RON=1e-3 ROFF=1e8)
LC2 ldk c2 {p['LCAB']}
RLC2 ldk c2 100
RC2 c2 0 {p['RCAB']}
XINA vin src v5 0 imon INA180A1
* level shifter
RREF vin ref {p['RREF']}
M2 ref lg ls ls N7002
RSET ls 0 {p['RSET']}
XUL sp ls vin 0 lgo {p['OPAMP']}
RLG lgo lg {p['RLG']}
* error amplifier
"""
    if analysis == "ac":
        s += "VINJ og og_amp DC 0 AC 1\n"
    else:
        s += "VINJ og og_amp 0\n"
    s += f"""XUE ref inm vin 0 og_amp {p['OPAMP']}
RF src inm {p['RF']}
"""
    if p["RZ"]:
        s += f"CF inm cz {p['CF']}\nRZ cz og_amp {p['RZ']}\n"
    else:
        s += f"CF inm og_amp {p['CF']}\n"
    if p["CFF"]:
        s += f"CFF src inm {p['CFF']}\n"
    if analysis == "tran":
        s += f"VSP sp_raw 0 PULSE({p['VLO']} {p['VHI']} {p['T0']} 5n 5n {p['TW']} 1)\n"
    else:
        s += f"VSP sp_raw 0 DC {p['VHI']}\n"
    s += f"""RSP sp_raw sp {p['RSP']}
CSP sp 0 {p['CSP']}
{'*' if analysis=='tran' else ''}.nodeset v(src)={p['VIN']-0.003} v(ref)={p['VIN']-0.003} v(gate)={p['VIN']-3.7} v(og_amp)={p['VIN']-3.7} v(og)={p['VIN']-3.7} v(inm)={p['VIN']-0.003} v(drn)=4.6 v(lda)=4.6 v(ls)={p['VLO'] if analysis=='tran' else p['VHI']} v(lg)=2.2 v(lgo)=2.2 v(sp)={p['VLO'] if analysis=='tran' else p['VHI']}
.end
"""
    return s


def run(p, analysis="tran", tstop=None, tstep=5e-9, fstart=1e3, fstop=1e8, keep=False):
    q = dict(DEF); q.update(p)
    if tstop is None:
        tstop = q["T0"] + q["TW"] + 20e-6
    net = netlist(q, analysis)
    tag = f"tbd_{analysis}_{os.getpid()}_{abs(hash(str(sorted(q.items()))))%100000}"
    cir = os.path.join(HERE, tag + ".cir")
    out = os.path.join(HERE, tag + ".dat")
    if analysis == "tran":
        ctl = f"""
.control
tran {tstep} {tstop} 0 {tstep} uic
wrdata {out} v(sp) i(VC) v(og_amp) v(gate) v(drn) v(lda,ldk) v(imon) v(ref) v(src)
.endc
"""
    elif analysis == "ac":
        ctl = f"""
.control
op
print i(VC) v(og_amp) v(gate)
ac dec 40 {fstart} {fstop}
let T = -v(og_amp)/v(og)
wrdata {out} T
.endc
"""
    net = net.replace(".end\n", ctl + ".end\n")
    open(cir, "w").write(net)
    r = subprocess.run(["ngspice", "-b", cir], cwd=HERE, capture_output=True, text=True)
    if not os.path.exists(out):
        if not keep:
            os.remove(cir)
        raise RuntimeError("sim failed: " + "\n".join(l for l in r.stdout.splitlines() if "rror" in l or "trouble" in l)[-800:])
    d = np.loadtxt(out)
    os.remove(out)
    if not keep:
        os.remove(cir)
    if analysis == "ac":
        op = {}
        for l in r.stdout.splitlines():
            if "=" in l and ("i(vc)" in l.lower() or "v(og_amp)" in l.lower() or "v(gate)" in l.lower()):
                k, v = l.split("=", 1)
                op[k.strip()] = float(v.split()[0])
        return d, op
    return d


COLS = ["sp", "i", "og", "gate", "drn", "vld", "imon", "ref", "src"]


def col(d, name):
    return d[:, 2 * COLS.index(name) + 1]


def tran_metrics(d, ihi, t0=40e-6, tw=100e-6):
    t = d[:, 0]
    i = col(d, "i")
    m = t >= t0
    tt, ii = t[m], i[m]
    def cross(level):
        idx = np.where(ii >= level)[0]
        return tt[idx[0]] if len(idx) else float("nan")
    t10 = cross(0.1 * ihi); t90 = cross(0.9 * ihi); t99 = float("nan")
    win = (tt < t0 + tw)
    pk = ii[win].max()
    late = ii[(tt > t0 + 0.6 * tw) & (tt < t0 + 0.99 * tw)].mean()
    # 1% settling
    err = np.abs(ii[win] - late) > 0.01 * late
    idx = np.where(err)[0]
    ts = (tt[win][idx[-1]] - t0) if len(idx) else 0.0
    m2 = t >= t0 + tw
    tf, iff = t[m2], i[m2]
    idx = np.where(iff <= 0.1 * ihi)[0]
    tfall = (tf[idx[0]] - (t0 + tw)) if len(idx) else float("nan")
    undershoot = iff.min()
    return dict(delay=t10 - t0, rise=t90 - t10, peak=pk, over=(pk / late - 1) * 100, final=late,
                settle=ts, fall=tfall, under=undershoot)


def ac_metrics(d):
    f = d[:, 0]
    T = d[:, 1] + 1j * d[:, 2]
    mag = 20 * np.log10(np.abs(T))
    ph = np.degrees(np.unwrap(np.angle(T)))
    idx = np.where((mag[:-1] > 0) & (mag[1:] <= 0))[0]
    if not len(idx):
        return dict(fc=float("nan"), pm=float("nan"), gm=float("nan"), dc=mag[0])
    k = idx[-1]
    fc = f[k]
    pm = (ph[k] + 180 + 180) % 360 - 180
    phw = (ph + 180) % 360 - 180
    j = np.where((np.abs(phw[:-1]) < 30) & (np.sign(phw[:-1]) != np.sign(phw[1:])) & (f[:-1] > fc))[0]
    gmg = -mag[j[0]] if len(j) else float("nan")
    return dict(fc=fc, pm=pm, gm=gmg, dc=mag[0])
