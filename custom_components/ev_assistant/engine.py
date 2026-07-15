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


class EfficiencyCalibrator:
    """Kalibriert den Ladewirkungsgrad (AC->Batterie) aus echten
    Heim-Ladesessions: SoC-Delta * usable_kwh (Batterie-Energie) gegen die
    von einem Wallbox-Energiezaehler gemessene AC-Energie derselben Session.

    Rein ereignisgetrieben ueber Home-Charging-Uebergaenge (start()/end()
    bei True<->False-Wechsel des Heim-Laden-Signals) -- kein SoC-Sampling
    noetig wie bei ChargeDetector, daher bewusst als eigene, minimale
    Zustandsmaschine statt Erweiterung von ChargeDetector.
    """

    def __init__(
        self,
        usable_kwh: float,
        min_soc_delta: float = 5.0,
        min_efficiency: float = 0.5,
        max_efficiency: float = 1.0,
    ):
        self.usable_kwh = usable_kwh
        self.min_soc_delta = min_soc_delta
        self.min_efficiency = min_efficiency
        self.max_efficiency = max_efficiency
        self._anchor_soc: Optional[float] = None
        self._anchor_wallbox_kwh: Optional[float] = None

    def start(self, soc: float, wallbox_kwh: Optional[float]) -> None:
        self._anchor_soc = soc
        self._anchor_wallbox_kwh = wallbox_kwh

    def end(self, soc: float, wallbox_kwh: Optional[float]) -> Optional[float]:
        """Schliesst die Session ab und liefert eine neue Effizienz-
        Stichprobe (0..1), oder None wenn die Session nicht auswertbar war
        (zu kurz / Wallbox-Wert fehlt(e) / unplausibles Ergebnis)."""
        anchor_soc = self._anchor_soc
        anchor_wallbox_kwh = self._anchor_wallbox_kwh
        self._anchor_soc = None
        self._anchor_wallbox_kwh = None

        if anchor_soc is None or anchor_wallbox_kwh is None or wallbox_kwh is None:
            return None
        soc_delta = soc - anchor_soc
        wallbox_delta = wallbox_kwh - anchor_wallbox_kwh
        if soc_delta < self.min_soc_delta or wallbox_delta <= 0:
            return None

        battery_kwh = soc_delta / 100.0 * self.usable_kwh
        efficiency = battery_kwh / wallbox_delta
        if not (self.min_efficiency <= efficiency <= self.max_efficiency):
            return None
        return round(efficiency, 4)


def average_efficiency(samples: list[float], max_samples: int = 10) -> Optional[float]:
    """Gleitender Durchschnitt der letzten `max_samples` Effizienz-Stichproben."""
    recent = samples[-max_samples:]
    return round(sum(recent) / len(recent), 4) if recent else None


def pop_pending(pending_list: list, start_ts: Optional[float]) -> Optional[dict]:
    """Entfernt und liefert die passende offene Ladung aus `pending_list`
    (in-place): bei angegebenem `start_ts` die mit exakt passendem Start,
    sonst die aelteste (FIFO, die Liste ist append-only chronologisch
    sortiert). Gibt None zurueck, wenn nichts (passendes) offen ist.

    Mehrere Fremdladungen koennen gleichzeitig offen sein (z.B. zwei
    Ladestopps auf einem Roadtrip vor dem ersten Bestaetigen) — diese
    Funktion waehlt aus, welche log_charge/discard_pending gerade meint."""
    if not pending_list:
        return None
    if start_ts is not None:
        for i, p in enumerate(pending_list):
            if p.get("start_ts") == start_ts:
                return pending_list.pop(i)
        return None
    return pending_list.pop(0)


def calculate_savings(
    km_driven: Optional[float],
    home_kwh: Optional[float],
    home_price_kwh: Optional[float],
    fremdladen_kosten: float,
    verbrenner_l_100km: Optional[float],
    verbrenner_price_per_liter: Optional[float],
) -> Optional[dict]:
    """Gesamtkosten der EV-Nutzung (Heimladen + Fremdladen) gegen einen
    Vergleichs-Verbrenner (Verbrauch x Kraftstoffpreis auf derselben
    Strecke). Gibt None zurueck, wenn eine der zwingend noetigen Groessen
    fehlt (km_driven, verbrenner_l_100km, verbrenner_price_per_liter) --
    home_kwh/home_price_kwh sind einzeln optional: fehlen sie, wird nur
    mit den (immer vorhandenen) Fremdladungskosten gerechnet."""
    if km_driven is None or verbrenner_l_100km is None or verbrenner_price_per_liter is None:
        return None
    heimladen_kosten = 0.0
    if home_kwh is not None and home_price_kwh is not None:
        heimladen_kosten = round(home_kwh * home_price_kwh, 2)
    kosten_ev_gesamt = round(heimladen_kosten + fremdladen_kosten, 2)
    kosten_verbrenner = round((km_driven / 100.0) * verbrenner_l_100km * verbrenner_price_per_liter, 2)
    return {
        "heimladen_kosten": heimladen_kosten,
        "kosten_ev_gesamt": kosten_ev_gesamt,
        "kosten_verbrenner_geschaetzt": kosten_verbrenner,
        "ersparnis": round(kosten_verbrenner - kosten_ev_gesamt, 2),
    }
