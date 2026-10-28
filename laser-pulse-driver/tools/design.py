"""Single source of truth for the LD405 pulse driver: parts, values, footprints,
LCSC numbers and pin-to-net connections.  gen_sch.py builds the KiCad schematic
from this file and gen_pcb.py builds the board, so the two always agree.

Net naming: power nets VIN (after reverse-polarity FET), +5V, VREF, GND.
A pin mapped to None is deliberately unconnected (gets a no-connect flag).
"""

PROJECT = "ld405-driver"
TITLE = "405 nm laser diode pulse driver (BDR-209)"
REV = "1.0"

FP_R0603 = "Resistor_SMD:R_0603_1608Metric"
FP_R0805 = "Resistor_SMD:R_0805_2012Metric"
FP_R2512 = "Resistor_SMD:R_2512_6332Metric"
FP_C0603 = "Capacitor_SMD:C_0603_1608Metric"
FP_C0805 = "Capacitor_SMD:C_0805_2012Metric"
FP_SOT23 = "Package_TO_SOT_SMD:SOT-23"
FP_SOT235 = "Package_TO_SOT_SMD:SOT-23-5"
FP_SOT236 = "Package_TO_SOT_SMD:SOT-23-6"
FP_SOIC8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
FP_SOIC14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"
FP_DPAK = "Package_TO_SOT_SMD:TO-252-2"
FP_SOD123 = "Diode_SMD:D_SOD-123"
FP_SOD323 = "Diode_SMD:D_SOD-323"
FP_SMA = "Diode_SMD:D_SMA"
FP_LEDSIDE = "ld405:LED_SideView_LiteOn_LTST-S220"

# LCSC part numbers (checked against the JLCPCB catalogue, 28 Oct 2026)
R_LCSC = {
    "10k": "C25804", "1k": "C21190", "100k": "C25803", "100": "C22775", "4.7k": "C23162",
    "47k": "C25819", "3.3k": "C22978", "2.2k": "C4190", "1M": "C22935", "20k": "C4184",
    "200k": "C25811", "3k": "C4211", "150": "C22808", "15k": "C22809", "18k": "C25810",
    "11k": "C25950", "300k": "C23024", "220": "C22962", "1.5k": "C22843", "4.02k": "C23040",
    "49.9": "C23185", "10": "C22859",
}
R_PREC = {  # 0.1 % thin film
    "10k": ("C95204", "RT0603BRD0710KL"), "40.2k": ("C667101", "TD03G4022BT"),
    "3k": ("C136963", "RT0603BRD073KL"), "150": ("C319859", "AR03BTCX1500"),
    "1k": ("C110776", "RT0603BRD071KL"),
}
C_LCSC = {
    "100nF": ("C14663", "CC0603KRX7R9BB104", FP_C0603),
    "1uF": ("C15849", "CL10A105KB8NNNC", FP_C0603),
    "10uF": ("C15850", "CL21A106KAYNNNE", FP_C0805),
    "220pF C0G": ("C388907", "GCM1885C2A221JA16D", FP_C0603),
    "100pF C0G": ("C14858", "CL10C101JB8NNNC", FP_C0603),
    "47nF": ("C1622", "CL10B473KB8NNNC", FP_C0603),
    "1nF": ("C1588", "CL10B102KB8NNNC", FP_C0603),
    "10nF": ("C57112", "0603B103K500NT", FP_C0603),
    "2.2uF": ("C23630", "CL10A225KO8NNNC", FP_C0603),
    "220nF": ("C21120", "CL10B224KA8NNNC", FP_C0603),
}

PARTS = []


def part(ref, lib, value, fp, pins, lcsc="", mpn="", block="", units=None, **kw):
    d = dict(ref=ref, lib=lib, value=value, fp=fp, pins=pins, lcsc=lcsc, mpn=mpn,
             block=block, units=units or {1: block})
    d.update(kw)
    PARTS.append(d)
    return d


def R(ref, value, a, b, block, prec=False, fp=FP_R0603, lcsc=None, mpn=None, note=""):
    if prec:
        lc, mp = R_PREC[value]
        val = value + " 0.1%"
    else:
        lc = lcsc or R_LCSC.get(value, "")
        mp = mpn or ""
        val = value
    return part(ref, "Device:R", val, fp, {"1": a, "2": b}, lc, mp, block, note=note)


def C(ref, value, a, b, block):
    lc, mp, fp = C_LCSC[value]
    return part(ref, "Device:C", value, fp, {"1": a, "2": b}, lc, mp, block)


# ---------------------------------------------------------------- power input
part("J1", "Connector:Barrel_Jack_Switch", "9V DC IN", "ld405:BarrelJack_DC-005_Horizontal",
     {"1": "VIN_RAW", "2": "GND", "3": "GND"}, "C381116", "DC-005-5A-2.0", "PWR")
part("F1", "Device:Polyfuse", "2A PTC", "Fuse:Fuse_1812_4532Metric",
     {"1": "VIN_RAW", "2": "VIN_F"}, "C960026", "BSMD1812-200-30V", "PWR")
part("Q1", "Transistor_FET:AO3401A", "AO3401A", FP_SOT23,
     {"1": "Q1_G", "2": "VIN", "3": "VIN_F"}, "C15127", "AO3401A", "PWR")
R("R1", "100k", "Q1_G", "GND", "PWR")
part("D1", "Diode:BZT52Bxx", "BZT52C10", FP_SOD123, {"1": "VIN", "2": "Q1_G"},
     "C19077408", "BZT52C10", "PWR")
part("D2", "Diode:SMAJ13A", "SMAJ13A", FP_SMA, {"1": "VIN", "2": "GND"},
     "C19077533", "SMAJ13A", "PWR")
for ref in ("C1", "C2"):
    part(ref, "Device:C_Polarized", "220uF 25V", "Capacitor_SMD:CP_Elec_8x10.5",
         {"1": "VIN", "2": "GND"}, "C72497", "RVT1E221M0810", "PWR")
C("C3", "10uF", "VIN", "GND", "PWR")
C("C4", "10uF", "VIN", "GND", "PWR")
C("C5", "100nF", "VIN", "GND", "PWR")
part("U1", "Regulator_Linear:LM78M05_TO252", "L78M05ABDT", FP_DPAK,
     {"1": "VIN", "2": "GND", "3": "+5V"}, "C58069", "L78M05ABDT-TR", "PWR")
C("C6", "1uF", "VIN", "GND", "PWR")
C("C7", "10uF", "+5V", "GND", "PWR")
C("C8", "100nF", "+5V", "GND", "PWR")
part("U2", "Reference_Voltage:REF3030", "REF3030", FP_SOT23,
     {"1": "+5V", "2": "VREF", "3": "GND"}, "C38423", "REF3030AIDBZR", "PWR")
C("C9", "1uF", "VREF", "GND", "PWR")
C("C10", "1uF", "+5V", "GND", "PWR")          # REF30xx: >= 0.47 uF on its supply
part("FLG1", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "VIN"}, block="PWR", virtual=True)
part("FLG2", "power:PWR_FLAG", "PWR_FLAG", "", {"1": "GND"}, block="PWR", virtual=True)

# ------------------------------------------------------- setpoint / soft start
R("R10", "10k", "VREF", "VFS_RAW", "SET", prec=True)
R("R11", "40.2k", "VFS_RAW", "GND", "SET", prec=True)
part("JP1", "Jumper:SolderJumper_2_Open", "I_MAX 700mA",
     "Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm", {"1": "VREF", "2": "JP1_B"},
     block="SET", nobom=True)
R("R12", "4.02k", "JP1_B", "VFS_RAW", "SET")
C("C11", "10uF", "VFS_RAW", "GND", "SET")
part("Q3", "Transistor_FET:2N7002", "2N7002", FP_SOT23,
     {"1": "DIS_LOOP", "2": "GND", "3": "SS_D"}, "C8545", "2N7002", "SET")
R("R13", "100", "SS_D", "VFS_RAW", "SET")
part("U3", "Amplifier_Operational:LM358", "TLV9062", FP_SOIC8,
     {"3": "VFS_RAW", "2": "VFS", "1": "VFS",
      "5": "VP_W", "6": "VP", "7": "VP",
      "8": "+5V", "4": "GND"}, "C398355", "TLV9062IDR", "SET",
     units={1: "SET", 2: "SET", 3: "PWRPINS"})
C("C13", "100nF", "+5V", "GND", "SET")
part("RV1", "Device:R_Potentiometer", "PULSE 20k", "Potentiometer_THT:Potentiometer_Alps_RK09L_Single_Horizontal",
     {"1": "GND", "2": "VP_W", "3": "VFS"}, "C470444", "RK09L112003P", "SET")
R("R15", "100k", "VFS", "IDLE_TOP", "SET")
part("RV2", "Device:R_Potentiometer", "IDLE 20k", "Potentiometer_THT:Potentiometer_Alps_RK09L_Single_Horizontal",
     {"1": "IDLE_BOT", "2": "VI_W", "3": "IDLE_TOP"}, "C470444", "RK09L112003P", "SET")
R("R16", "1k", "IDLE_BOT", "GND", "SET")
part("U4", "Amplifier_Operational:LM358", "TLV9062", FP_SOIC8,
     {"3": "VI_W", "2": "VI", "1": "VI",
      "5": "SM_DIV", "6": "SETMON_OUT", "7": "SETMON_OUT",
      "8": "+5V", "4": "GND"}, "C398355", "TLV9062IDR", "SET",
     units={1: "SET", 2: "MON", 3: "PWRPINS"})
C("C14", "100nF", "+5V", "GND", "SET")
part("U5", "74xGxx:74LVC1G3157", "SN74LVC1G3157", FP_SOT236,
     {"6": "GATE_N", "4": "VSP_MUX", "1": "VI", "3": "VP", "5": "+5V", "2": "GND"},
     "C10426", "SN74LVC1G3157DBVR", "SET", units={1: "SET", 2: "PWRPINS"})
C("C16", "100nF", "+5V", "GND", "SET")
R("R17", "1k", "VSP_MUX", "VSP", "SET")
C("C12", "220pF C0G", "VSP", "GND", "SET")

# ------------------------------------------------------------------ TTL input
part("J2", "Connector:Conn_Coaxial", "TTL IN", "ld405:BNC_DOSIN_801-0080_Horizontal",
     {"1": "TTL_BNC", "2": "GND"}, "C521219", "DOSIN-801-0080", "TTL")
R("R22", "10k", "TTL_BNC", "GND", "TTL")
R("R21", "220", "TTL_BNC", "TTL_PROT", "TTL")
C("C15", "100pF C0G", "TTL_PROT", "GND", "TTL")
part("D4", "Diode:BAT54S", "BAT54S", FP_SOT23, {"1": "GND", "2": "+5V", "3": "TTL_PROT"},
     "C7420333", "BAT54S", "TTL")
part("U14", "74xGxx:74AHCT1G14", "74AHCT1G14", FP_SOT235,
     {"2": "TTL_PROT", "4": "GATE_N", "5": "+5V", "3": "GND", "1": None},
     "C55250", "SN74AHCT1G14DBVR", "TTL")
C("C17", "100nF", "+5V", "GND", "TTL")

# ---------------------------------------------- current source (high side)
part("U7", "Amplifier_Operational:LM358", "OPA2192", FP_SOIC8,
     {"3": "REF_N", "2": "EA_N", "1": "EA_OUT",
      "5": "VSP", "6": "LS_S", "7": "LS_GO",
      "8": "VIN", "4": "GND"}, "C110074", "OPA2192IDR", "CS",
     units={1: "CS", 2: "CS", 3: "PWRPINS"})
C("C18", "100nF", "VIN", "GND", "CS")
C("C19", "1uF", "VIN", "GND", "CS")
R("R30", "100", "LS_GO", "LS_G", "CS")
part("Q4", "Transistor_FET:2N7002", "2N7002", FP_SOT23,
     {"1": "LS_G", "2": "LS_S", "3": "REF_N"}, "C8545", "2N7002", "CS")
R("R31", "3k", "LS_S", "GND", "CS", prec=True)
R("R32", "150", "VIN_SNS", "REF_N", "CS", prec=True)
C("C30", "100pF C0G", "VIN_SNS", "REF_N", "CS")
R("R33", "1k", "SRC_SNS", "EA_N", "CS")
C("C31", "220pF C0G", "EA_N", "EA_OUT", "CS")
R("R34", "100", "EA_OUT", "GATE", "CS")
R("R35", "10k", "GATE", "VIN", "CS")
part("Q5", "Transistor_FET:2N7002", "2N7002", FP_SOT23,
     {"1": "DIS_LOOP", "2": "GND", "3": "Q5_D"}, "C8545", "2N7002", "CS")
R("R36", "100k", "Q5_D", "EA_N", "CS")
part("Q6", "Transistor_FET:AO3401A", "AO3401A", FP_SOT23,
     {"1": "CLAMP_G", "2": "VIN", "3": "GATE"}, "C15127", "AO3401A", "CS")
R("R37", "100k", "VIN", "CLAMP_G", "CS")
R("R38", "47k", "CLAMP_G", "GND", "CS")
part("Q7", "Transistor_FET:AO3401A", "AO3401A", FP_SOT23,
     {"1": "REL_G", "2": "VIN", "3": "CLAMP_G"}, "C15127", "AO3401A", "CS")
R("R39", "100k", "VIN", "REL_G", "CS")
R("R48", "47k", "REL_G", "Q8_D", "CS")
part("Q8", "Transistor_FET:2N7002", "2N7002", FP_SOT23,
     {"1": "EN_LOOP", "2": "GND", "3": "Q8_D"}, "C8545", "2N7002", "CS")
part("Q2", "Transistor_FET:SUD08P06-155L", "IRFR9024N", FP_DPAK,
     {"1": "GATE", "2": "LD_OUT", "3": "SRC_D"}, "C2585", "IRFR9024NTRPBF", "CS")
R("R40", "0.2", "VIN", "SRC_K", "CS", fp=FP_R2512, lcsc="C459674", mpn="RLP25FEER200",
  note="current sense, 2 W, 1 %")
part("NT1", "Device:NetTie_2", "NetTie", "NetTie:NetTie-2_SMD_Pad0.5mm",
     {"1": "VIN", "2": "VIN_SNS"}, block="CS", nobom=True)
part("NT2", "Device:NetTie_2", "NetTie", "NetTie:NetTie-2_SMD_Pad0.5mm",
     {"1": "SRC_K", "2": "SRC_SNS"}, block="CS", nobom=True)
R("R41", "1.0", "SRC_K", "SRC_D", "CS", fp=FP_R2512, lcsc="C11254", mpn="25121WF100KT4E",
  note="source degeneration, 1 W")
part("U8", "Amplifier_Current:INA180A1", "INA180A1", FP_SOT235,
     {"3": "VIN_SNS", "4": "SRC_SNS", "5": "+5V", "2": "GND", "1": "IMON_INT"},
     "C122228", "INA180A1IDBVR", "CS")
C("C20", "100nF", "+5V", "GND", "CS")
part("RT1", "Device:Thermistor_NTC", "10k B3950", FP_R0603, {"1": "NTC_N", "2": "GND"},
     "C279936", "SDNT1608X103F3950FTF", "CS")

# ------------------------------------------------------------- output stage
# Omron G6K-2F-Y (datasheet "Terminal Arrangement", top view): coil 1(+)/8(-),
# COM 3 and 6, normally-closed 2 and 7, normally-open 4 and 5.  Both NC contacts
# short the laser output to ground while the relay is de-energised.
part("K1", "Relay:G6K-2", "G6K-2F-Y 5V", "Relay_SMD:Relay_DPDT_Omron_G6K-2F-Y",
     {"1": "+5V", "8": "RLY_N", "3": "LD_OUT", "6": "LD_OUT", "2": "GND", "7": "GND",
      "4": None, "5": None}, "C47190", "G6K-2F-Y-TR DC5", "OUT")
part("Q9", "Transistor_FET:2N7002", "2N7002", FP_SOT23,
     {"1": "EN_REQ", "2": "GND", "3": "RLY_N"}, "C8545", "2N7002", "OUT")
part("D5", "Diode:1N4148WS", "1N4148WS", FP_SOD323, {"1": "+5V", "2": "RLY_N"},
     "C2128", "1N4148WS", "OUT")
part("Q10", "Transistor_FET:AO3400A", "AO3400A", FP_SOT23,
     {"1": "CB_G", "2": "GND", "3": "LD_OUT"}, "C20917", "AO3400A", "OUT")
R("R42", "100", "DIS_LOOP", "CB_G", "OUT")
R("R43", "100k", "CB_G", "GND", "OUT")
part("D6", "Diode:SS34", "SS34", FP_SMA, {"1": "LD_OUT", "2": "GND"}, "C8678", "SS34", "OUT")
part("D7", "Diode:SMAJ12A", "SMAJ12A", FP_SMA, {"1": "LD_OUT", "2": "GND"},
     "C19077531", "SMAJ12A", "OUT")
R("R44", "22", "LD_OUT", "SNUB", "OUT", fp=FP_R0805, lcsc="C17561")
C("C32", "47nF", "SNUB", "GND", "OUT")
part("J5", "Connector:DE9_Socket_MountingHoles", "LD OUT",
     "Connector_Dsub:DSUB-9_Socket_Horizontal_P2.77x2.84mm_EdgePinOffset7.70mm_Housed_MountingHolesOffset9.12mm",
     {"1": "DB9_IL", "2": None, "3": "GND", "4": None, "5": "GND", "6": None, "7": None,
      "8": "LD_OUT", "9": None, "0": "GND"}, "C75749", "DS1037-09FNAKT74-0CC", "OUT")

# ---------------------------------------------------------------- monitors
R("R18", "3k", "VP", "SM_DIV", "MON", prec=True)
R("R19", "1k", "SM_DIV", "GND", "MON", prec=True)
R("R20", "49.9", "SETMON_OUT", "SETMON", "MON")
part("J3", "Connector:Conn_Coaxial", "SET MON", "ld405:BNC_DOSIN_801-0080_Horizontal",
     {"1": "SETMON", "2": "GND"}, "C521219", "DOSIN-801-0080", "MON")
R("R45", "3k", "IMON_INT", "IM_DIV", "MON", prec=True)
R("R46", "1k", "IM_DIV", "GND", "MON", prec=True)
part("U10", "Amplifier_Operational:LM358", "TLV9062", FP_SOIC8,
     {"3": "IM_DIV", "2": "IMON_OUT", "1": "IMON_OUT",
      "5": "GND", "6": "U10B_OUT", "7": "U10B_OUT",
      "8": "+5V", "4": "GND"}, "C398355", "TLV9062IDR", "MON",
     units={1: "MON", 2: "MON", 3: "PWRPINS"})
C("C21", "100nF", "+5V", "GND", "MON")
R("R47", "49.9", "IMON_OUT", "IMON", "MON")
part("J4", "Connector:Conn_Coaxial", "I MON", "ld405:BNC_DOSIN_801-0080_Horizontal",
     {"1": "IMON", "2": "GND"}, "C521219", "DOSIN-801-0080", "MON")

# ------------------------------------------------- protection comparators
part("U11", "Comparator:LM2901", "LM2901", FP_SOIC14,
     {"5": "OC_REF", "4": "IMON_INT", "2": "S_N",          # A: over-current
      "7": "G_DIV", "6": "CMP_REF", "1": "S_N",            # B: compliance / open LD
      "11": "NTC_N", "10": "CMP_REF", "13": "S_N",         # C: over-temperature
      "9": "EM_REF", "8": "IMON_INT", "14": "EMI_RC",      # D: emission detect
      "3": "+5V", "12": "GND"}, "C7932", "LM2901DR", "PROT",
     units={1: "PROT", 2: "PROT", 3: "PROT", 4: "PROT", 5: "PWRPINS"})
C("C22", "100nF", "+5V", "GND", "PROT")
R("R50", "10k", "+5V", "OC_REF", "PROT")
R("R51", "18k", "OC_REF", "GND", "PROT")
R("R54", "100k", "+5V", "CMP_REF", "PROT")
R("R55", "11k", "CMP_REF", "GND", "PROT")
C("C23", "100nF", "CMP_REF", "GND", "PROT")
R("R52", "300k", "GATE", "G_DIV", "PROT")
R("R53", "100k", "G_DIV", "GND", "PROT")
C("C33", "100pF C0G", "G_DIV", "GND", "PROT")
R("R56", "10k", "+5V", "NTC_N", "PROT")
C("C24", "100nF", "NTC_N", "GND", "PROT")
R("R59", "100k", "+5V", "EM_REF", "PROT")
R("R60", "1.5k", "EM_REF", "GND", "PROT")
R("R61", "1M", "+5V", "EMI_RC", "PROT")
C("C34", "100nF", "EMI_RC", "GND", "PROT")
part("Q11", "Transistor_FET:AO3401A", "AO3401A", FP_SOT23,
     {"1": "EMI_RC", "2": "+5V", "3": "Q11_D"}, "C15127", "AO3401A", "PROT")
R("R62", "1k", "Q11_D", "LED_EMI", "PROT")

# ------------------------------------------------------------------- logic
part("SW1", "Switch:SW_SPDT", "ENABLE", "ld405:Toggle_Dailywell_1MS1T2B4M7QES",
     {"2": "GND", "1": "EN_SW", "3": None}, "C496157", "1MS1T2B4M7QES", "LOGIC")
R("R70", "10k", "+5V", "EN_SW", "LOGIC")
C("C40", "100nF", "EN_SW", "GND", "LOGIC")
part("J6", "Connector_Audio:AudioJack2", "INTERLOCK", "Connector_Audio:Jack_3.5mm_KoreanHropartsElec_PJ-320D-4A_Horizontal",
     {"T": "REM_N", "S": "GND"}, "C431535", "PJ-320D", "LOGIC")
R("R72", "4.7k", "+5V", "REM_N", "LOGIC")
C("C41", "100nF", "REM_N", "GND", "LOGIC")
R("R77", "3.3k", "+5V", "DB9_IL", "LOGIC")
C("C42", "10nF", "DB9_IL", "GND", "LOGIC")
part("U12", "74xx:74HC14", "74HC14", FP_SOIC14,
     {"1": "EN_SW", "2": "EN_ON",          # A: enable switch
      "3": "REM_N", "4": "REM_OK",         # B: remote interlock
      "5": "DB9_IL", "6": "DB9_OK",        # C: DB9 interlock loop
      "9": "EN_DLY", "8": "DIS_LOOP",      # D: delayed enable
      "11": "DIS_LOOP", "10": "EN_LOOP",   # E
      "13": "GND", "12": None,             # F: unused
      "14": "+5V", "7": "GND"}, "C5605", "74HC14D", "LOGIC",
     units={1: "LOGIC", 2: "LOGIC", 3: "LOGIC", 4: "LOGIC", 5: "LOGIC", 6: "LOGIC", 7: "PWRPINS"})
C("C25", "100nF", "+5V", "GND", "LOGIC")
part("D10", "Diode:BAT54A", "BAT54A", FP_SOT23, {"3": "S_N", "1": "REM_OK", "2": "DB9_OK"},
     "C7502690", "BAT54A", "LOGIC")
R("R73", "10k", "+5V", "S_N", "LOGIC")
C("C44", "1nF", "S_N", "GND", "LOGIC")
R("R78", "100k", "+5V", "POR_RC", "LOGIC")
C("C43", "2.2uF", "POR_RC", "GND", "LOGIC")
part("D13", "Diode:1N4148WS", "1N4148WS", FP_SOD323, {"1": "+5V", "2": "POR_RC"},
     "C2128", "1N4148WS", "LOGIC")
part("D14", "Diode:1N4148WS", "1N4148WS", FP_SOD323, {"1": "POR_RC", "2": "S_N"},
     "C2128", "1N4148WS", "LOGIC")
part("U13", "74xx:74LS132", "74HC132", FP_SOIC14,
     {"1": "S_N", "2": "FAULT_N", "3": "FAULT",          # A: latch set side
      "4": "EN_ON", "5": "FAULT", "6": "FAULT_N",        # B: latch reset side
      "9": "EN_ON", "10": "FAULT_N", "8": "EN_REQ_N",    # C: enable request
      "12": "EN_REQ_N", "13": "EN_REQ_N", "11": "EN_REQ",  # D: inverter
      "14": "+5V", "7": "GND"}, "C350560", "SN74HC132DR", "LOGIC",
     units={1: "LOGIC", 2: "LOGIC", 3: "LOGIC", 4: "LOGIC", 5: "PWRPINS"})
C("C26", "100nF", "+5V", "GND", "LOGIC")
R("R79", "100k", "EN_REQ", "EN_DLY", "LOGIC")
C("C45", "220nF", "EN_DLY", "GND", "LOGIC")
part("D15", "Diode:1N4148WS", "1N4148WS", FP_SOD323, {"1": "EN_REQ", "2": "EN_DLY"},
     "C2128", "1N4148WS", "LOGIC")

# ---------------------------------------------------------- front-panel LEDs
part("D3", "Device:LED", "POWER green", FP_LEDSIDE, {"1": "GND", "2": "LED_PWR"},
     "C160470", "LTST-S220TGKT", "FP")
R("R2", "2.2k", "+5V", "LED_PWR", "FP")
part("D12", "Device:LED", "FAULT red", FP_LEDSIDE, {"1": "GND", "2": "LED_FLT"},
     "C284935", "LTST-S220KRKT", "FP")
R("R81", "1k", "FAULT", "LED_FLT", "FP")
part("D16", "Device:LED", "ARMED yellow", FP_LEDSIDE, {"1": "GND", "2": "LED_ARM"},
     "C160468", "LTST-S220KSKT", "FP")
R("R82", "1k", "EN_REQ", "LED_ARM", "FP")
part("D8", "Device:LED", "EMISSION blue", FP_LEDSIDE, {"1": "GND", "2": "LED_EMI"},
     "C160471", "LTST-S220TBKT", "FP")

# ------------------------------------------------------------- mechanical
for i in range(1, 5):
    part(f"H{i}", "Mechanical:MountingHole_Pad", "M3", "MountingHole:MountingHole_3.2mm_M3_Pad_Via",
         {"1": "GND"}, block="MECH", nobom=True)


def nets():
    """Return {net: [(ref, pin), ...]}."""
    out = {}
    for p in PARTS:
        for pin, net in p["pins"].items():
            if net is None:
                continue
            out.setdefault(net, []).append((p["ref"], pin))
    return out


if __name__ == "__main__":
    n = nets()
    for k in sorted(n):
        print(f"{k:12s} {len(n[k]):3d}  " + " ".join(f"{r}.{p}" for r, p in n[k]))
    # sanity: nets with a single connection are almost always mistakes
    lonely = [k for k, v in n.items() if len(v) < 2]
    print("\nsingle-pin nets:", lonely)
    print("parts:", len(PARTS))
