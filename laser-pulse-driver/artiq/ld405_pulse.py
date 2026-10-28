"""ARTIQ experiments for the LD405 pulsed 405 nm photo-ionisation laser driver.

Wiring: a Kasli TTL output (DIO-BNC or DIO-SMA) -> LD405 "TTL IN".
TTL high = pulse current (PULSE knob), low = idle current (IDLE knob).

Add aliases to device_db.py so the experiments do not hard-code channels, e.g.

    device_db["ttl_ld405"] = "ttl4"        # LD405 TTL IN
    device_db["ttl_ablation"] = "ttl5"     # ablation laser trigger (Q-switch / flash lamp)

Driver timing (simulated, see ../docs/design-notes.md): the current starts
rising ~1 us after the TTL edge, reaches 90 % after ~5 us and is within 1 % of
the setpoint after ~10 us; it falls back to the idle level ~7 us after the
TTL goes low.  Start the pulse a little before the ionising light is needed.
"""
from artiq.experiment import *


class LD405AblationLoad(EnvExperiment):
    """LD405: ablation shots inside a 405 nm REMPI pulse"""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl_ld405")
        self.setattr_device("ttl_ablation")
        # length of the 405 nm pulse
        self.setattr_argument("pulse_width", NumberValue(100 * us, unit="us", step=10 * us,
                                                         min=1 * us, max=2 * ms))
        # the 405 nm pulse starts this long before the ablation trigger
        self.setattr_argument("lead", NumberValue(15 * us, unit="us", step=1 * us,
                                                  min=0 * us, max=1 * ms))
        self.setattr_argument("ablation_width", NumberValue(10 * us, unit="us", step=1 * us,
                                                            min=100 * ns, max=1 * ms))
        self.setattr_argument("shots", NumberValue(20, step=1, min=1, max=100000, ndecimals=0))
        # time between shots - keep the duty cycle low for the diode
        self.setattr_argument("period", NumberValue(100 * ms, unit="ms", step=10 * ms,
                                                    min=1 * ms, max=10 * s))

    def prepare(self):
        self.shots = int(self.shots)
        if self.lead >= self.pulse_width:
            raise ValueError("the ablation trigger must fall inside the 405 nm pulse")
        if self.pulse_width / self.period > 0.1:
            raise ValueError("duty cycle above 10 % - check the diode rating before doing this")

    @kernel
    def run(self):
        self.core.reset()
        self.ttl_ld405.output()
        self.ttl_ablation.output()
        delay(10 * us)
        self.ttl_ld405.off()
        self.ttl_ablation.off()
        delay(1 * ms)
        for _ in range(self.shots):
            with parallel:
                self.ttl_ld405.pulse(self.pulse_width)          # 405 nm, second REMPI step
                with sequential:
                    delay(self.lead)                            # let the current settle first
                    self.ttl_ablation.pulse(self.ablation_width)
            delay(self.period - self.pulse_width)


class LD405PulseTrain(EnvExperiment):
    """LD405: pulse train for set-up and power calibration (no ablation)"""

    def build(self):
        self.setattr_device("core")
        self.setattr_device("ttl_ld405")
        self.setattr_argument("pulse_width", NumberValue(100 * us, unit="us", step=10 * us,
                                                         min=1 * us, max=2 * ms))
        # 100 us every 10 ms = 1 % duty cycle: a thermal power meter reads 1 % of the peak power
        self.setattr_argument("period", NumberValue(10 * ms, unit="ms", step=1 * ms,
                                                    min=100 * us, max=10 * s))
        self.setattr_argument("duration", NumberValue(10 * s, unit="s", step=1 * s,
                                                      min=1 * ms, max=600 * s))

    def prepare(self):
        if self.pulse_width >= self.period:
            raise ValueError("pulse_width must be shorter than period")
        self.n = int(self.duration / self.period)

    @kernel
    def run(self):
        self.core.reset()
        self.ttl_ld405.output()
        delay(10 * us)
        self.ttl_ld405.off()
        delay(1 * ms)
        for _ in range(self.n):
            self.ttl_ld405.pulse(self.pulse_width)
            delay(self.period - self.pulse_width)
