#!/usr/bin/env python3
"""Back-of-envelope estimates for the MSc project
"Experimental demonstration of reduced fibre solarisation in an oxygen-free atmosphere".

Every number quoted in Appendix A of the proposal is printed by this script, so the
student can check them, change the assumptions and re-derive them for their own set-up.

    python3 calc/estimates.py

Only the Python standard library is needed. All inputs are collected in the
PARAMETERS block; each carries a comment saying where it comes from. Values marked
"assumption" are order-of-magnitude choices that the student should replace with
measured numbers (e.g. the mode-field diameter of the actual fibre batch).
"""

import math

# ----------------------------------------------------------------------------------
# Physical constants (SI)
# ----------------------------------------------------------------------------------
H = 6.62607015e-34        # Planck constant, J s
C = 2.99792458e8          # speed of light, m/s
KB = 1.380649e-23         # Boltzmann constant, J/K
R_GAS = 8.314462618       # gas constant, J/(mol K)
AMU = 1.66053906660e-27   # atomic mass unit, kg
P_ATM = 101325.0          # standard atmosphere, Pa
MOL_PER_SCCM_S = 1.0 / 22414.0 / 60.0   # mol/s carried by 1 sccm (0 degC, 1 atm)
BARRER_SI = 3.35e-16      # 1 Barrer in mol m / (m^2 s Pa)

# ----------------------------------------------------------------------------------
# PARAMETERS
# ----------------------------------------------------------------------------------
WAVELENGTH = 369.5e-9     # Yb+ S1/2-P1/2 cooling/detection wavelength, m
MFD = 2.4e-6              # mode-field diameter at 369.5 nm, m: PM-S350-HP data sheet gives 2.3 um at
                          # 350 nm; scaled to 369.5 nm with Marcuse's formula (measure it!)
POWERS_MW = (1.0, 3.0, 10.0)   # guided powers to tabulate, mW
T_LAB = 295.0             # lab temperature, K

# Gas-phase contaminant (generic organic, e.g. a siloxane or plasticiser fragment)
CONTAMINANT_MASS_AMU = 150.0      # assumption
CONTAMINANT_FRACTIONS = (1e-9, 1e-8, 1e-7)   # 1, 10, 100 ppb (mole fraction)
MONOLAYER_PER_M2 = 1e19           # ~1e15 molecules/cm^2

# Optical constants of a hypothetical deposit (assumption: polymer-like to graphitic a-C:H)
DEPOSIT_N = 1.5                   # real refractive index of a transparent deposit
DEPOSIT_K_VALUES = (0.03, 0.1, 0.3)   # extinction coefficients of absorbing deposits

# Thermal conductivity of fused silica, W/(m K)
KAPPA_SILICA = 1.38

# Gas diffusion in silica glass (Arrhenius D = D0 exp(-Ea / R T)); name, D0 (cm^2/s), Ea (kJ/mol)
EV_TO_KJ_MOL = 96.485
DIFFUSION = (
    ("H2 (Lemaire, Opt. Eng. 30, 780 (1991))", 2.83e-4, 40.19),
    ("H2 (Shang et al., GCA 73, 5435 (2009))", 7.0e-4, 44.59),
    # O2 data were measured at 800-1200 degC; extrapolating to room temperature is an order-of-magnitude
    # estimate only.
    ("O2 (Kajihara et al., MSE B 173, 158 (2010), low-OH)", 4.5e-5, 0.93 * EV_TO_KJ_MOL),
    ("O2 (Norton, Nature 191, 701 (1961))", 2.7e-4, 1.17 * EV_TO_KJ_MOL),
)
FIBRE_RADIUS = 62.5e-6            # cladding radius, m

# Gas cell / purge
CELL_VOLUME_CM3 = 30.0            # internal free volume of one end-face cell (assumption)
PURGE_SCCM = (5.0, 20.0)          # purge flows to tabulate
O2_FEED_PPM = 2.0                 # O2 in the feed gas (N2 5.0 grade, typical spec)
O2_TARGETS_PPM = (100.0, 10.0)
MIXING_PENALTY = 3.0              # real cells are not perfectly mixed (assumption)

# Wall permeation: printed wall, O2 permeability in Barrer (assumption, see Table in proposal)
WALL_AREA_CM2 = 60.0
WALL_THICKNESS_MM = 3.0
WALL_P_O2_BARRER = (0.1, 1.0)     # PETG-like ... PC/ABS-like

# Tubing permeation (6 mm OD x 4 mm ID, 1 m long)
TUBE_OD_MM, TUBE_ID_MM, TUBE_LENGTH_M = 6.0, 4.0, 1.0
TUBE_P_O2_BARRER = {"polyurethane (assumption ~3 Barrer)": 3.0,
                    "PTFE/FEP (assumption ~3 Barrer)": 3.0,
                    "nylon/PA (assumption ~0.1 Barrer)": 0.1,
                    "stainless steel / copper": 0.0}

# Outlet back-diffusion: O2 in N2 binary diffusion coefficient (~0.2 cm^2/s at 295 K)
D_O2_N2 = 2.0e-5                  # m^2/s
OUTLET_ID_MM, OUTLET_LENGTH_M = 2.0, 0.3

# Static oxygen-absorber cell
ABSORBER_CAPACITY_CM3 = 20.0      # mL O2 the sachet can bind (vendor rating; assumption)
LEAK_RATES_MBAR_L_S = (1e-6, 1e-5, 1e-4)   # air leak rates to tabulate
PREPURGE_O2 = 0.01                # 1 % O2 left after a quick N2 pre-purge
PRESSURE_SENSOR_RES_MBAR = 0.1    # pressure-decay leak test: sensor resolution
LEAK_TEST_DURATION_H = 12.0

# Statistics: daily averaged transmission readings
NOISE_REL = 0.003                 # 0.3 % relative scatter of a daily average (assumption)
RUN_DAYS = (21, 42)


def header(title):
    print("\n" + title)
    print("-" * len(title))


def gaussian_peak_intensity(power_w, mfd):
    """Peak intensity of a Gaussian mode, I0 = 2P / (pi w^2), w = MFD / 2."""
    w = mfd / 2.0
    return 2.0 * power_w / (math.pi * w * w)


def arrhenius(d0, ea_kj_mol, temp):
    return d0 * math.exp(-ea_kj_mol * 1e3 / (R_GAS * temp))


def main():
    photon_energy = H * C / WAVELENGTH
    w = MFD / 2.0

    header("A1  End-face intensity and photon flux")
    print(f"photon energy at {WAVELENGTH*1e9:.1f} nm: {photon_energy/1.602176634e-19:.3f} eV"
          f" (two photons: {2*photon_energy/1.602176634e-19:.2f} eV)")
    print(f"mode-field radius w = {w*1e6:.2f} um, mode area pi w^2 = {math.pi*w*w*1e12:.2f} um^2")
    for p_mw in POWERS_MW:
        i0 = gaussian_peak_intensity(p_mw * 1e-3, MFD)
        flux = i0 / photon_energy
        print(f"  P = {p_mw:5.1f} mW: peak I0 = {i0*1e-4/1e3:7.0f} kW/cm^2,"
              f" photon flux = {flux*1e-4:.1e} photons cm^-2 s^-1,"
              f" dose per day = {i0*1e-4*86400:.1e} J/cm^2")

    header("A2  Arrival rate of a gas-phase contaminant at the end face (kinetic theory)")
    m = CONTAMINANT_MASS_AMU * AMU
    for x in CONTAMINANT_FRACTIONS:
        p = x * P_ATM
        flux = p / math.sqrt(2.0 * math.pi * m * KB * T_LAB)
        print(f"  {x*1e9:6.0f} ppb of a {CONTAMINANT_MASS_AMU:.0f} u molecule: impingement"
              f" {flux:.1e} m^-2 s^-1 = {flux/MONOLAYER_PER_M2:.1e} monolayers/s;"
              f" with sticking x photo-fixation probability 1e-6 ->"
              f" one monolayer every {MONOLAYER_PER_M2/(flux*1e-6)/86400:.1f} days")

    header("A3  How thick must a deposit on the core be to cost 10 % of the light?")
    for k in DEPOSIT_K_VALUES:
        alpha = 4.0 * math.pi * k / WAVELENGTH
        d10 = -math.log(0.9) / alpha
        print(f"  absorbing film, k = {k:4.2f}: alpha = {alpha*1e-2:.1e} cm^-1, 10 % absorption at"
              f" d = {d10*1e9:5.1f} nm")
    # Pure phase deposit whose thickness follows the Gaussian intensity profile:
    # coupling efficiency eta = sinc^2(phi0 / 2) (exact for this profile, thin-element model).
    lo, hi = 0.0, math.pi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        x = mid / 2.0
        eta = (math.sin(x) / x) ** 2
        lo, hi = (mid, hi) if eta > 0.9 else (lo, mid)
    phi0 = 0.5 * (lo + hi)
    h0 = phi0 * WAVELENGTH / (2.0 * math.pi * (DEPOSIT_N - 1.0))
    print(f"  transparent film (n = {DEPOSIT_N}) with a Gaussian thickness profile: 10 % coupling"
          f" loss at a peak phase of {phi0:.2f} rad, i.e. a peak thickness of {h0*1e9:.0f} nm")

    header("A4  Steady-state heating of the end face by an absorbing film (Lax 1977)")
    print("  dT = P_abs / (sqrt(2 pi) kappa w), semi-infinite silica, surface absorption")
    for p_mw in POWERS_MW:
        for a in (0.01, 0.1, 0.3):
            dT = a * p_mw * 1e-3 / (math.sqrt(2.0 * math.pi) * KAPPA_SILICA * w)
            print(f"  P = {p_mw:5.1f} mW, film absorbs {a*100:4.0f} %: dT = {dT:6.1f} K")

    header("A5  Can atmospheric gases reach the glass? Diffusion in silica at room temperature")
    for name, d0, ea in DIFFUSION:
        d = arrhenius(d0, ea, T_LAB) * 1e-4   # m^2/s
        tau = FIBRE_RADIUS ** 2 / (5.78 * d)  # first-mode time constant of a cylinder
        print(f"  {name}: D({T_LAB:.0f} K) = {d*1e4:.1e} cm^2/s")
        print(f"      depth sqrt(Dt) after 1 day / 1 month / 1 year ="
              f" {math.sqrt(d*86400)*1e9:.3g} / {math.sqrt(d*30*86400)*1e9:.3g} /"
              f" {math.sqrt(d*365*86400)*1e9:.3g} nm;"
              f" time constant for a 125 um fibre = {tau/86400:.3g} days")

    header("A6  Continuous purge of an end-face cell")
    for q in PURGE_SCCM:
        tau_min = CELL_VOLUME_CM3 / q
        for target in O2_TARGETS_PPM:
            t = tau_min * math.log((0.209e6 - O2_FEED_PPM) / (target - O2_FEED_PPM))
            print(f"  V = {CELL_VOLUME_CM3:.0f} cm^3, Q = {q:4.1f} sccm: exchange time {tau_min:4.1f} min;"
                  f" ideal time to {target:5.0f} ppm = {t:5.1f} min"
                  f" (x{MIXING_PENALTY:.0f} for imperfect mixing: {MIXING_PENALTY*t/60:.1f} h)")
    dp_o2 = 0.209 * P_ATM
    for perm in WALL_P_O2_BARRER:
        j = perm * BARRER_SI * (WALL_AREA_CM2 * 1e-4) * dp_o2 / (WALL_THICKNESS_MM * 1e-3)
        for q in PURGE_SCCM:
            ppm = j / (q * MOL_PER_SCCM_S) * 1e6
            print(f"  intact printed wall, {perm:4.1f} Barrer, {WALL_AREA_CM2:.0f} cm^2 x"
                  f" {WALL_THICKNESS_MM:.0f} mm: O2 influx {j/MOL_PER_SCCM_S:.1e} sccm ->"
                  f" {ppm:6.2f} ppm at {q:4.1f} sccm purge")
    # cylindrical wall: J = P * 2 pi L * dp / ln(r_out / r_in)
    geometry = 2.0 * math.pi * TUBE_LENGTH_M / math.log(TUBE_OD_MM / TUBE_ID_MM)
    for name, perm in TUBE_P_O2_BARRER.items():
        j = perm * BARRER_SI * geometry * dp_o2
        ppm = j / (PURGE_SCCM[0] * MOL_PER_SCCM_S) * 1e6
        print(f"  {TUBE_LENGTH_M:.0f} m of {TUBE_OD_MM:.0f}x{TUBE_ID_MM:.0f} mm tube, {name}:"
              f" adds {ppm:7.2f} ppm O2 at {PURGE_SCCM[0]:.0f} sccm")
    a_out = math.pi * (OUTLET_ID_MM * 1e-3 / 2.0) ** 2
    for q in (0.5,) + PURGE_SCCM:
        pe = (q * 1e-6 / 60.0) * OUTLET_LENGTH_M / (a_out * D_O2_N2)
        print(f"  outlet {OUTLET_LENGTH_M*100:.0f} cm x {OUTLET_ID_MM:.0f} mm ID at {q:4.1f} sccm:"
              f" Peclet number {pe:7.1f}, back-diffusion suppressed by exp(-Pe) = {math.exp(-pe):.1e}")

    header("A7  Static cell with an oxygen absorber")
    o2_air = 0.209 * CELL_VOLUME_CM3
    print(f"  O2 in {CELL_VOLUME_CM3:.0f} cm^3 of air: {o2_air:.1f} cm^3; removing it from a rigid,"
          f" sealed cell lowers the pressure by {0.209*1013:.0f} mbar (drives air in through leaks)")
    print(f"  after an N2 pre-purge to {PREPURGE_O2*100:.0f} % O2: {PREPURGE_O2*CELL_VOLUME_CM3:.2f} cm^3"
          f" O2 to absorb, pressure drop only {PREPURGE_O2*1013:.0f} mbar")
    for leak in LEAK_RATES_MBAR_L_S:
        air_cm3_per_day = leak / 1013.25 * 1e3 * 86400   # cm^3(STP)/day at ~1 atm driving force
        o2_per_day = 0.209 * air_cm3_per_day
        life = (ABSORBER_CAPACITY_CM3 - PREPURGE_O2 * CELL_VOLUME_CM3) / o2_per_day
        print(f"  air leak {leak:.0e} mbar L/s: {o2_per_day:.2e} cm^3 O2/day ->"
              f" {ABSORBER_CAPACITY_CM3:.0f} cm^3 absorber lasts {life:.3g} days")
    v_l = CELL_VOLUME_CM3 * 1e-3
    q_min = v_l * PRESSURE_SENSOR_RES_MBAR / (LEAK_TEST_DURATION_H * 3600.0)
    print(f"  pressure-decay test ({PRESSURE_SENSOR_RES_MBAR} mbar resolution over"
          f" {LEAK_TEST_DURATION_H:.0f} h): detects leaks down to ~{q_min:.0e} mbar L/s")
    print(f"  ...but a 0.1 K temperature change alone shifts the pressure by"
          f" {1013.25*0.1/T_LAB:.2f} mbar: log T and correct, or test at constant temperature")

    header("A8  Coupling optics: mode matching and the cell window")
    w_f = MFD / 2.0
    for f_mm in (4.5, 5.0, 8.0):
        w_in = f_mm * 1e-3 * WAVELENGTH / (math.pi * w_f)
        print(f"  asphere f = {f_mm:3.1f} mm: collimated input beam diameter (1/e^2) for mode matching"
              f" = {2*w_in*1e3:.2f} mm")
    n_fs = 1.4739          # fused silica at 369.5 nm (Malitson, JOSA 55, 1205 (1965))
    for t_mm, na in ((1.0, 0.10), (1.0, 0.12), (2.0, 0.12)):
        w040 = t_mm * 1e-3 * (n_fs ** 2 - 1.0) * na ** 4 / (8.0 * n_fs ** 3)
        rms = w040 / (6.0 * math.sqrt(5.0))          # balanced primary spherical aberration
        strehl = math.exp(-(2.0 * math.pi * rms / WAVELENGTH) ** 2)
        print(f"  {t_mm:.0f} mm window at NA {na:.2f}: W040 = {w040*1e9:.1f} nm, Strehl = {strehl:.5f},"
              f" focus shift = {t_mm*(1-1/n_fs):.2f} mm")
    r_fresnel = ((n_fs - 1.0) / (n_fs + 1.0)) ** 2
    print(f"  Fresnel reflection of a bare silica end face: {r_fresnel*100:.1f} %")
    theta_in = math.degrees(math.asin(n_fs * math.sin(math.radians(8.0))))
    print(f"  FC/APC (8 deg) face: beam must arrive {theta_in - 8.0:.1f} deg off the fibre axis; the face"
          f" reflection leaves {2*theta_in:.1f} deg away from the incoming beam (does not retrace it)")
    # Coreless end cap: the beam diffracts inside the cap before reaching the air-glass face
    z_r = math.pi * w_f ** 2 * n_fs / WAVELENGTH
    print(f"  end cap (coreless silica): Rayleigh range in glass z_R = {z_r*1e6:.0f} um")
    for cap_um in (100, 200, 300, 500):
        w_cap = w_f * math.sqrt(1.0 + (cap_um * 1e-6 / z_r) ** 2)
        print(f"    {cap_um:3d} um cap: spot diameter {2*w_cap*1e6:5.1f} um, face intensity reduced"
              f" x{(w_cap/w_f)**2:5.0f}")

    header("A9  How well can a 'zero degradation' claim be bounded?")
    for days in RUN_DAYS:
        n = days
        std_t = days / math.sqrt(12.0)
        sigma_b = NOISE_REL / (math.sqrt(n) * std_t)   # per day
        print(f"  {days} daily points, {NOISE_REL*100:.1f} % scatter: slope uncertainty"
              f" {sigma_b*100:.3f} %/day -> 95 % upper limit ~{1.96*sigma_b*100*1000/24:.2f} % per 1000 h")


if __name__ == "__main__":
    main()
