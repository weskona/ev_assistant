"""
engine.py — Fremdlade-Erkennung (reine Logik, KEINE HA-Abhaengigkeiten).

Per pytest testbar. Dieselbe Datei kann auch in ev_profile genutzt werden.

Erkennung: "Fremdladen" = SoC steigt, waehrend die Heim-Wallbox NICHT laedt
(Korrelationssignal `home_charging` aus evcc/Warp). Kein GPS noetig.

Energie (aussagekraeftig = AC am Ladepunkt, inkl. Ladeverluste):
  - `power_kw` je Sample vorhanden -> ueber Session integriert (~Zaehlerwert):
      power_is_ac=True  : AC-seitig (OBC-Input) -> energy_ac = Integral
      power_is_ac=False : DC-seitig (Pack V*I)  -> energy_batt = Integral
  - ohne Leistung: SoC-Delta -> Batterie-netto -> /charge_efficiency = AC-Schaetzung
  energy_kwh      = AC, inkl. Verluste (abgerechnet)
  energy_batt_kwh = Batterie-netto
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChargeSample:
    ts: float
    soc: float
    home_charging: bool
    power_kw: Optional[float] = None


@dataclass
class ChargeEvent:
    start_ts: float
    end_ts: float
    soc_start: float
    soc_end: float
    energy_kwh: float
    energy_batt_kwh: float
    energy_source: str
    kind: str = "extern"

    @property
    def delta_soc(self) -> float:
        return round(self.soc_end - self.soc_start, 1)

    @property
    def duration_s(self) -> float:
        return round(self.end_ts - self.start_ts, 0)

    @property
    def losses_kwh(self) -> float:
        return round(self.energy_kwh - self.energy_batt_kwh, 2)

    def as_dict(self) -> dict:
        return {
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "soc_start": round(self.soc_start, 1),
            "soc_end": round(self.soc_end, 1),
            "delta_soc": self.delta_soc,
            "energy_kwh": round(self.energy_kwh, 2),
            "energy_batt_kwh": round(self.energy_batt_kwh, 2),
            "losses_kwh": self.losses_kwh,
            "energy_source": self.energy_source,
            "duration_min": round(self.duration_s / 60.0, 1),
            "kind": self.kind,
        }


class ChargeDetector:
    """Zustandsautomat. Samples per update() einspeisen; liefert bei
    Session-Ende ein ChargeEvent, sonst None."""

    def __init__(
        self,
        usable_kwh: float = 45.0,
        charge_efficiency: float = 0.88,
        power_is_ac: bool = True,
        start_delta: float = 3.0,
        noise: float = 0.5,
        idle_timeout_s: float = 600.0,
        drop_ends: float = 1.0,
    ):
        self.usable_kwh = usable_kwh
        self.charge_efficiency = charge_efficiency
        self.power_is_ac = power_is_ac
        self.start_delta = start_delta
        self.noise = noise
        self.idle_timeout_s = idle_timeout_s
        self.drop_ends = drop_ends

        self._active = False
        self._anchor_soc: Optional[float] = None
        self._anchor_ts: Optional[float] = None
        self._start_ts = 0.0
        self._start_soc = 0.0
        self._peak_soc = 0.0
        self._last_rise_ts = 0.0
        self._e_power_kwh = 0.0
        self._have_power = False
        self._last_power: Optional[float] = None
        self._last_power_ts: Optional[float] = None

    def update(self, s: ChargeSample) -> Optional[ChargeEvent]:
        if self._anchor_soc is None:
            self._anchor_soc = s.soc
            self._anchor_ts = s.ts
        if not self._active:
            return self._update_idle(s)
        return self._update_charging(s)

    def _update_idle(self, s: ChargeSample) -> Optional[ChargeEvent]:
        if s.home_charging:
            self._anchor_soc = s.soc
            self._anchor_ts = s.ts
            return None
        if s.soc <= self._anchor_soc:
            self._anchor_soc = s.soc
            self._anchor_ts = s.ts
            return None
        if s.soc - self._anchor_soc >= self.start_delta:
            self._active = True
            self._start_ts = self._anchor_ts
            self._start_soc = self._anchor_soc
            self._peak_soc = s.soc
            self._last_rise_ts = s.ts
            self._e_power_kwh = 0.0
            self._have_power = s.power_kw is not None
            self._last_power = s.power_kw
            self._last_power_ts = s.ts
        return None

    def _integrate_power(self, s: ChargeSample) -> None:
        if s.power_kw is None:
            return
        if self._last_power is not None and self._last_power_ts is not None:
            dt_h = (s.ts - self._last_power_ts) / 3600.0
            if dt_h > 0:
                self._e_power_kwh += 0.5 * (self._last_power + s.power_kw) * dt_h
                self._have_power = True
        self._last_power = s.power_kw
        self._last_power_ts = s.ts

    def _update_charging(self, s: ChargeSample) -> Optional[ChargeEvent]:
        self._integrate_power(s)
        if s.home_charging:
            return self._finalize(s)
        if s.soc > self._peak_soc + self.noise:
            self._peak_soc = s.soc
            self._last_rise_ts = s.ts
            return None
        if s.soc < self._peak_soc - self.drop_ends:
            return self._finalize(s)
        if s.ts - self._last_rise_ts >= self.idle_timeout_s:
            return self._finalize(s)
        return None

    def _energy(self, delta_soc: float):
        if self._have_power and self._e_power_kwh > 0:
            if self.power_is_ac:
                e_ac = self._e_power_kwh
                return e_ac, e_ac * self.charge_efficiency, "power_ac"
            e_batt = self._e_power_kwh
            return e_batt / self.charge_efficiency, e_batt, "power_dc"
        e_batt = delta_soc / 100.0 * self.usable_kwh
        return e_batt / self.charge_efficiency, e_batt, "soc"

    def _finalize(self, s: ChargeSample) -> Optional[ChargeEvent]:
        delta = self._peak_soc - self._start_soc
        e_ac, e_batt, source = self._energy(delta)
        ev = ChargeEvent(
            start_ts=self._start_ts,
            end_ts=self._last_rise_ts,
            soc_start=self._start_soc,
            soc_end=self._peak_soc,
            energy_kwh=e_ac,
            energy_batt_kwh=e_batt,
            energy_source=source,
        )
        self._active = False
        self._anchor_soc = s.soc
        self._anchor_ts = s.ts
        self._e_power_kwh = 0.0
        self._have_power = False
        self._last_power = None
        self._last_power_ts = None
        return ev if delta >= self.start_delta else None
