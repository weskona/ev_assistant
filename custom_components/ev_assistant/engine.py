"""
engine.py — Fremdlade- und Fahrten-Erkennung (reine Logik, KEINE HA-Abhaengigkeiten).

Per pytest testbar. Dieselbe Datei kann auch in ev_profile genutzt werden.

Erkennung: "Fremdladen" = SoC steigt, waehrend die Heim-Wallbox NICHT laedt
(Korrelationssignal `home_charging` aus evcc/Warp). Kein GPS noetig.

Fahrtenbuch (TripDetector weiter unten): eine Fahrt = Zeitraum zwischen zwei
Standzeiten des monoton steigenden Kilometerstands. Ebenfalls kein GPS noetig.

Energie (aussagekraeftig = AC am Ladepunkt, inkl. Ladeverluste):
  - `power_kw` je Sample vorhanden -> ueber Session integriert (~Zaehlerwert):
      power_is_ac=True  : AC-seitig (OBC-Input) -> energy_ac = Integral
      power_is_ac=False : DC-seitig (Pack V*I)  -> energy_batt = Integral
  - ohne Leistung: SoC-Delta -> Batterie-netto -> /charge_efficiency = AC-Schaetzung
  energy_kwh      = AC, inkl. Verluste (abgerechnet)
  energy_batt_kwh = Batterie-netto
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass(frozen=True)
class ChargeSample:
    ts: float
    soc: float
    home_charging: bool
    power_kw: Optional[float] = None
    # Optional, ueber SignalDebouncer gefiltert (siehe dort): True/False nur
    # bei einem ueber debounce_s bestaetigten Steckerstatus, sonst None
    # (kein Steckersensor konfiguriert, oder Bestaetigung steht noch aus) --
    # ChargeDetector faellt bei None auf die idle_timeout_s-Heuristik zurueck.
    plugged_in: Optional[bool] = None


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
        regen_implausible_delta_pct: float = 15.0,
    ):
        self.usable_kwh = usable_kwh
        self.charge_efficiency = charge_efficiency
        self.power_is_ac = power_is_ac
        self.start_delta = start_delta
        self.noise = noise
        self.idle_timeout_s = idle_timeout_s
        self.drop_ends = drop_ends
        # Ab dieser SoC-Sprunghoehe gilt ein Anstieg bei bestaetigt
        # ausgestecktem Fahrzeug NICHT mehr als plausible Rekuperation,
        # sondern als waehrend einer Erkennungsluecke verpasste Fremdladung
        # (siehe _update_idle()) -- Default identisch zu const.py::
        # IMPLAUSIBLE_REGEN_DELTA_PCT.
        self.regen_implausible_delta_pct = regen_implausible_delta_pct

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

    @property
    def active(self) -> bool:
        """Ob aktuell eine Fremdladung erkannt/laeuft (fuer Signale, die von
        aussen auf diesen Zustand reagieren muessen, z.B. SoC-Schwellenwert-
        Benachrichtigungen -- siehe coordinator.py::_check_soc_thresholds())."""
        return self._active

    def get_state(self) -> dict:
        """Momentaufnahme des Zustandsautomaten (Anker, laufende Session,
        Peak, ...) zum Persistieren -- siehe load_state(). Ohne das wuerde
        ein HA-Neustart eine gerade laufende (noch nicht abgeschlossene)
        Erkennung stillschweigend verwerfen, da diese Werte sonst nur im
        Arbeitsspeicher existieren."""
        return {
            "active": self._active,
            "anchor_soc": self._anchor_soc,
            "anchor_ts": self._anchor_ts,
            "start_ts": self._start_ts,
            "start_soc": self._start_soc,
            "peak_soc": self._peak_soc,
            "last_rise_ts": self._last_rise_ts,
            "e_power_kwh": self._e_power_kwh,
            "have_power": self._have_power,
            "last_power": self._last_power,
            "last_power_ts": self._last_power_ts,
        }

    def load_state(self, state: Optional[dict]) -> None:
        """Stellt einen zuvor per get_state() gesicherten Zustand wieder
        her. Ohne gespeicherten Zustand (None/leer) bleibt der frische
        __init__-Zustand unveraendert."""
        if not state:
            return
        self._active = state.get("active", False)
        self._anchor_soc = state.get("anchor_soc")
        self._anchor_ts = state.get("anchor_ts")
        self._start_ts = state.get("start_ts", 0.0)
        self._start_soc = state.get("start_soc", 0.0)
        self._peak_soc = state.get("peak_soc", 0.0)
        self._last_rise_ts = state.get("last_rise_ts", 0.0)
        self._e_power_kwh = state.get("e_power_kwh", 0.0)
        self._have_power = state.get("have_power", False)
        self._last_power = state.get("last_power")
        self._last_power_ts = state.get("last_power_ts")

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
            delta = s.soc - self._anchor_soc
            if s.plugged_in is False and delta < self.regen_implausible_delta_pct:
                # Bestaetigt AUSGESTECKT (siehe SignalDebouncer) UND ein fuer
                # Rekuperation (Bremsenergie-Rueckgewinnung waehrend der
                # Fahrt) plausibler, kleiner Anstieg -- keine Fremdladung.
                # Anker trotzdem auf den neuen (hoeheren) Wert nachfuehren,
                # sonst wuerde derselbe Anstieg bei der naechsten Messung
                # erneut ausgewertet. Kein Steckersensor konfiguriert
                # (plugged_in bleibt immer None): unveraendertes Verhalten,
                # ein SoC-Anstieg startet weiterhin eine Erkennung.
                #
                # Ein SEHR GROSSER Anstieg trotz "ausgesteckt"
                # (>= regen_implausible_delta_pct) ist dagegen mit
                # ueberwiegender Wahrscheinlichkeit keine Rekuperation,
                # sondern eine waehrend einer Erkennungsluecke (z.B.
                # Telemetrie-Ausfall der Quell-Integration ueber mehrere
                # Tage) verpasste Fremdladung -- die unten trotzdem als
                # Ladungs-Start gewertet wird, statt still verworfen zu
                # werden.
                self._anchor_soc = s.soc
                self._anchor_ts = s.ts
                return None
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
        # Bestaetigt ausgesteckt (siehe SignalDebouncer) -> sofort beenden,
        # unabhaengig von idle_timeout_s -- das Fahrzeug meldet den SoC bei
        # manchen Herstellern nur grob/langsam, idle_timeout_s waere sonst
        # entweder zu kurz (faelschlich gesplittete Ladung, siehe
        # merge_pending()) oder zu lang (Ladeende verzoegert erkannt).
        if s.plugged_in is False:
            return self._finalize(s)
        # Bestaetigt noch eingesteckt -> idle_timeout_s NICHT anwenden, sonst
        # wuerde eine durchgehende Ladung mit grob/langsam gemeldetem SoC
        # trotz vorhandenem Steckersensor weiterhin faelschlich gesplittet.
        # Kein Steckersensor konfiguriert (plugged_in bleibt immer None):
        # unveraendertes Verhalten, idle_timeout_s bleibt die einzige Instanz.
        if s.plugged_in is None and s.ts - self._last_rise_ts >= self.idle_timeout_s:
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


class SignalDebouncer:
    """Filtert kurze Flacker-/Aussetzer-Zustaende eines Stecker-
    (Connectivity-)Sensors heraus, bevor sie als ChargeSample.plugged_in in
    den ChargeDetector einfliessen.

    Hersteller-/Dongle-APIs melden den Steckerstatus teils kurzzeitig
    fehlerhaft oder verzoegert (z.B. MQTT-Reconnects mit
    unavailable/unknown/off fuer 1-3s, ohne dass tatsaechlich ausgesteckt
    wurde) -- ein einzelner abweichender Rohwert darf daher nicht sofort
    durchschlagen. Ein unbekannter Rohwert (None, z.B. unavailable/unknown)
    wird ignoriert und haelt den zuletzt bestaetigten Wert; ein
    abweichender on/off-Wert muss `debounce_s` lang DURCHGEHEND anliegen
    (jede Unterbrechung durch einen erneut abweichenden oder unbekannten
    Wert setzt die Wartezeit zurueck), bevor er uebernommen wird."""

    def __init__(self, debounce_s: float = 300.0):
        self.debounce_s = debounce_s
        self._debounced: Optional[bool] = None
        self._pending: Optional[bool] = None
        self._pending_since: Optional[float] = None

    def update(self, ts: float, raw: Optional[bool]) -> Optional[bool]:
        if raw is None or raw == self._debounced:
            self._pending = None
            self._pending_since = None
            return self._debounced
        if raw != self._pending:
            self._pending = raw
            self._pending_since = ts
            return self._debounced
        if ts - self._pending_since >= self.debounce_s:
            self._debounced = raw
            self._pending = None
            self._pending_since = None
        return self._debounced

    def get_state(self) -> dict:
        """Momentaufnahme zum Persistieren, analog ChargeDetector.get_state()
        -- ohne das wuerde ein HA-Neustart einen gerade laufenden (noch
        nicht ueber debounce_s bestaetigten) Steckerstatus-Wechsel
        verwerfen."""
        return {
            "debounced": self._debounced,
            "pending": self._pending,
            "pending_since": self._pending_since,
        }

    def load_state(self, state: Optional[dict]) -> None:
        if not state:
            return
        self._debounced = state.get("debounced")
        self._pending = state.get("pending")
        self._pending_since = state.get("pending_since")


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


@dataclass(frozen=True)
class TripSample:
    ts: float
    odo_km: float
    # Optional, ueber SignalDebouncer gefiltert (siehe dort): True/False nur
    # bei einem ueber debounce_s bestaetigten Motor-/Fahr-Status, sonst None
    # (kein Motor-Sensor konfiguriert, oder Bestaetigung steht noch aus) --
    # TripDetector faellt bei None auf den reinen Odometer-Vergleich zurueck.
    # Der Odometer bleibt in jedem Fall die einzige Quelle fuer die Strecke.
    driving: Optional[bool] = None


@dataclass
class TripEvent:
    start_ts: float
    end_ts: float
    odo_start: float
    odo_end: float

    @property
    def km(self) -> float:
        return round(self.odo_end - self.odo_start, 2)

    @property
    def duration_min(self) -> float:
        return round((self.end_ts - self.start_ts) / 60.0, 1)

    def as_dict(self) -> dict:
        return {
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "odo_start": round(self.odo_start, 2),
            "odo_end": round(self.odo_end, 2),
            "km": self.km,
            "duration_min": self.duration_min,
        }


class TripDetector:
    """Segmentiert einen monoton steigenden Kilometerstand in einzelne
    Fahrten, getrennt durch Standzeiten -- kein GPS noetig. Anders als
    ChargeDetector (SoC kann fallen/schwanken) braucht es kein Peak-
    Tracking/drop_ends: der Kilometerstand steigt nur, daher trennt hier
    eine Standzeit >= idle_timeout_s zwei Fahrten.

    Optionales TripSample.driving (siehe dort) ersetzt "Odometer gestiegen"
    als Bewegungssignal, wenn eine Hersteller-API den Kilometerstand zu grob
    oder selten aktualisiert, um Fahrtbeginn/-ende direkt daraus abzuleiten.
    idle_timeout_s bleibt dieselbe Kulanzzeit fuer kurze Fahrpausen (z.B.
    Stopp-Start-Automatik an der Ampel) -- ein bestaetigtes "Motor aus" endet
    die Fahrt NICHT sofort, anders als plugged_in=False bei ChargeDetector,
    weil ein kurzes Motor-Aus mitten in der Fahrt normal ist. Der Odometer
    bleibt in jedem Fall die einzige Quelle fuer odo_start/odo_end/km."""

    def __init__(self, min_km: float = 0.5, idle_timeout_s: float = 300.0):
        self.min_km = min_km
        self.idle_timeout_s = idle_timeout_s

        self._anchor_odo: Optional[float] = None
        self._anchor_ts: Optional[float] = None
        self._active = False
        self._start_ts = 0.0
        self._start_odo = 0.0
        self._last_odo = 0.0
        self._last_move_ts = 0.0

    @property
    def active(self) -> bool:
        """Ob gerade eine Fahrt laeuft -- oeffentlich lesbar, damit der
        Coordinator den idle->aktiv-Uebergang erkennen kann (z.B. um beim
        Fahrtbeginn einen GPS-/Zonen-Schnappschuss als Start-Ort-Vorschlag
        zu speichern, siehe coordinator.py::_run_trip_detection)."""
        return self._active

    def update(self, s: TripSample) -> Optional[TripEvent]:
        if self._anchor_odo is None:
            self._anchor_odo = s.odo_km
            self._anchor_ts = s.ts
            self._last_odo = s.odo_km
            self._last_move_ts = s.ts
            return None
        if not self._active:
            return self._update_idle(s)
        return self._update_driving(s)

    def get_state(self) -> dict:
        """Momentaufnahme zum Persistieren, analog ChargeDetector.get_state()
        -- ohne das wuerde eine gerade laufende (noch nicht abgeschlossene)
        Fahrt einen HA-Neustart nicht ueberleben."""
        return {
            "anchor_odo": self._anchor_odo,
            "anchor_ts": self._anchor_ts,
            "active": self._active,
            "start_ts": self._start_ts,
            "start_odo": self._start_odo,
            "last_odo": self._last_odo,
            "last_move_ts": self._last_move_ts,
        }

    def load_state(self, state: Optional[dict]) -> None:
        if not state:
            return
        self._anchor_odo = state.get("anchor_odo")
        self._anchor_ts = state.get("anchor_ts")
        self._active = state.get("active", False)
        self._start_ts = state.get("start_ts", 0.0)
        self._start_odo = state.get("start_odo", 0.0)
        self._last_odo = state.get("last_odo", 0.0)
        self._last_move_ts = state.get("last_move_ts", 0.0)

    def _moved(self, s: TripSample) -> bool:
        """Bewegungssignal: Odometer-Anstieg ODER bestaetigter Motor-/Fahr-
        Status (falls konfiguriert) -- eine Quelle ersetzt die andere nicht
        vollstaendig, ein echter Odometer-Sprung zaehlt daher immer, selbst
        wenn driving zufaellig False meldet."""
        if s.odo_km > self._last_odo:
            return True
        return bool(s.driving)

    def _update_idle(self, s: TripSample) -> Optional[TripEvent]:
        if self._moved(s):
            self._active = True
            self._start_ts = self._anchor_ts
            self._start_odo = self._anchor_odo
            self._last_odo = max(self._last_odo, s.odo_km)
            self._last_move_ts = s.ts
            return None
        # Keine Bewegung -> Anker (letzter bekannter Ruhepunkt, Zeit UND
        # Kilometerstand) nachfuehren, damit eine spaeter beginnende Fahrt ab
        # dem Ende der tatsaechlichen Standzeit gezaehlt wird statt ab deren
        # Anfang -- bei reinem Odometer-Vergleich ist odo_km hier ohnehin
        # unveraendert, bei motor-basierter Erkennung haelt das den Anker
        # trotz ggf. verzoegert eintreffender Odometer-Werte aktuell.
        # max() statt s.odo_km direkt (analog zur aktiven Fahrt oben):
        # _moved() hat bereits ausgeschlossen, dass s.odo_km > _last_odo ist,
        # ein niedrigerer Wert hier kann also nur ein kurzer Sensor-Glitch
        # im Stand sein -- ohne die Schranke wuerde der Anker auf den
        # Glitch-Wert absinken und die naechste echte Fahrt faelschlich viel
        # zu lang aussehen lassen (start_odo kommt aus dem Anker).
        self._anchor_ts = s.ts
        self._anchor_odo = max(self._last_odo, s.odo_km)
        return None

    def _update_driving(self, s: TripSample) -> Optional[TripEvent]:
        if self._moved(s):
            self._last_odo = max(self._last_odo, s.odo_km)
            self._last_move_ts = s.ts
            return None
        if s.ts - self._last_move_ts >= self.idle_timeout_s:
            return self._finalize(s)
        return None

    def _finalize(self, s: TripSample) -> Optional[TripEvent]:
        ev = TripEvent(
            start_ts=self._start_ts,
            end_ts=self._last_move_ts,
            odo_start=self._start_odo,
            odo_end=self._last_odo,
        )
        self._active = False
        self._anchor_odo = self._last_odo
        self._anchor_ts = s.ts
        return ev if ev.km >= self.min_km else None


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


def merge_pending(pending_list: list, new: dict, drop_tolerance: float = 0.5) -> None:
    """Haengt `new` an `pending_list` an (in-place) -- ausser die letzte
    offene Ladung geht ohne SoC-Abfall direkt in `new` ueber, dann wird
    stattdessen mit ihr zusammengefuehrt.

    Grund: der ChargeDetector finalisiert rein ueber idle_timeout_s. Meldet
    ein Fahrzeug seinen SoC nur grob/langsam (z.B. alle 10-20 Minuten in
    ganzen Prozent), reisst eine tatsaechlich durchgehende Fremdladung
    dadurch faelschlich in mehrere "offene Ladungen" (siehe Coordinator
    _handle_pending). Ein SoC-Abfall zwischen zwei Ladungen bedeutet
    dagegen, dass dazwischen gefahren wurde -- das bleibt ein
    zuverlaessiges, vom Meldeintervall unabhaengiges Signal fuer zwei
    tatsaechlich getrennte Ladestopps (z.B. auf einem Roadtrip) und wird
    nicht zusammengefuehrt."""
    if pending_list:
        last = pending_list[-1]
        if new["soc_start"] >= last["soc_end"] - drop_tolerance:
            last["end_ts"] = new["end_ts"]
            last["soc_end"] = new["soc_end"]
            last["delta_soc"] = round(last["soc_end"] - last["soc_start"], 1)
            last["energy_kwh"] = round(last["energy_kwh"] + new["energy_kwh"], 2)
            last["energy_batt_kwh"] = round(last["energy_batt_kwh"] + new["energy_batt_kwh"], 2)
            last["losses_kwh"] = round(last["energy_kwh"] - last["energy_batt_kwh"], 2)
            last["duration_min"] = round((last["end_ts"] - last["start_ts"]) / 60.0, 1)
            if last["energy_source"] != new["energy_source"]:
                last["energy_source"] = "mixed"
            return
    pending_list.append(new)


def calculate_savings(
    km_driven: Optional[float],
    home_kwh: Optional[float],
    home_price_kwh: Optional[float],
    fremdladen_kosten: float,
    verbrenner_l_100km: Optional[float],
    verbrenner_price_per_liter: Optional[float],
    home_cost: Optional[float] = None,
) -> Optional[dict]:
    """Gesamtkosten der EV-Nutzung (Heimladen + Fremdladen) gegen einen
    Vergleichs-Verbrenner (Verbrauch x Kraftstoffpreis auf derselben
    Strecke). Gibt None zurueck, wenn eine der zwingend noetigen Groessen
    fehlt (km_driven, verbrenner_l_100km, verbrenner_price_per_liter) --
    home_kwh/home_price_kwh sind einzeln optional: fehlen sie, wird nur
    mit den (immer vorhandenen) Fremdladungskosten gerechnet.
    home_cost: wenn angegeben, wird dieser Wert direkt verwendet statt
    home_kwh * home_price_kwh (z.B. wenn evcc die Kosten pro Fahrzeug
    bereits korrekt berechnet hat)."""
    if km_driven is None or verbrenner_l_100km is None or verbrenner_price_per_liter is None:
        return None
    heimladen_kosten = 0.0
    if home_cost is not None:
        heimladen_kosten = round(home_cost, 2)
    elif home_kwh is not None and home_price_kwh is not None:
        heimladen_kosten = round(home_kwh * home_price_kwh, 2)
    kosten_ev_gesamt = round(heimladen_kosten + fremdladen_kosten, 2)
    kosten_verbrenner = round((km_driven / 100.0) * verbrenner_l_100km * verbrenner_price_per_liter, 2)
    return {
        "heimladen_kosten": heimladen_kosten,
        "kosten_ev_gesamt": kosten_ev_gesamt,
        "kosten_verbrenner_geschaetzt": kosten_verbrenner,
        "ersparnis": round(kosten_verbrenner - kosten_ev_gesamt, 2),
    }


def calculate_co2_savings(
    km_driven: Optional[float],
    ev_kwh_total: Optional[float],
    co2_per_kwh_kg: Optional[float],
    verbrenner_l_100km: Optional[float],
    co2_per_liter_kg: float,
) -> Optional[dict]:
    """CO2-Bilanz der EV-Nutzung (aus der Strommenge seit Einrichtung)
    gegen einen Vergleichs-Verbrenner (Verbrauch x CO2-Faktor auf derselben
    Strecke) -- analog calculate_savings(), nur CO2 (kg) statt EUR. Gibt
    None zurueck, wenn eine der noetigen Groessen fehlt (km_driven,
    ev_kwh_total, co2_per_kwh_kg, verbrenner_l_100km); co2_per_liter_kg hat
    immer einen Wert (Fallback-Konstante, siehe const.py)."""
    if km_driven is None or ev_kwh_total is None or co2_per_kwh_kg is None or verbrenner_l_100km is None:
        return None
    co2_ev_kg = round(ev_kwh_total * co2_per_kwh_kg, 2)
    co2_verbrenner_kg = round((km_driven / 100.0) * verbrenner_l_100km * co2_per_liter_kg, 2)
    return {
        "co2_ev_kg": co2_ev_kg,
        "co2_verbrenner_kg": co2_verbrenner_kg,
        "co2_ersparnis_kg": round(co2_verbrenner_kg - co2_ev_kg, 2),
    }


def weekday_usage_profile(
    daily_kwh: dict, first_date: str, last_date: str, min_days: int = 7
) -> Optional[dict]:
    """Durchschnittlicher kWh-Bedarf pro Wochentag (0=Montag..6=Sonntag),
    aus taeglich aufsummierten Fahrtenbuch-kWh (siehe coordinator.py fuer
    die Aggregation aus den einzelnen Fahrten).

    `daily_kwh` (ISO-Datum -> kWh) enthaelt nur Tage mit mindestens einer
    Fahrt. Tage OHNE Fahrt fehlen darin, zaehlen aber trotzdem mit 0 kWh in
    den Durchschnitt -- sonst wuerde z.B. "faehrt nie sonntags" faelschlich
    ignoriert statt den Sonntags-Schnitt korrekt niedrig zu halten. Dafuer
    wird ueber JEDEN Kalendertag zwischen first_date und last_date
    (inklusive) iteriert, nicht nur ueber die Tage in daily_kwh.

    first_date/last_date (ISO, inklusive) legen den Beobachtungszeitraum
    fest. Gibt None zurueck, wenn der Zeitraum kuerzer als `min_days` ist
    (zu wenig Historie fuer ein aussagekraeftiges Profil) -- min_days=7
    garantiert dabei automatisch, dass jeder Wochentag mindestens einmal
    vorkommt (jede zusammenhaengende Folge von >=7 Tagen deckt alle 7
    Wochentage ab)."""
    start = date.fromisoformat(first_date)
    end = date.fromisoformat(last_date)
    total_days = (end - start).days + 1
    if total_days < min_days:
        return None
    totals = [0.0] * 7
    counts = [0] * 7
    d = start
    while d <= end:
        wd = d.weekday()
        counts[wd] += 1
        totals[wd] += daily_kwh.get(d.isoformat(), 0.0)
        d += timedelta(days=1)
    return {wd: round(totals[wd] / counts[wd], 2) for wd in range(7)}


def charge_cost(
    kwh: float, price_kwh: float, start_fee: float = 0.0, block_fee: float = 0.0, time_fee: float = 0.0,
) -> float:
    """Gesamtkosten einer Fremdladung: kWh x Preis/kWh plus bis zu drei
    optionale pauschale Zusatzgebuehren -- getrennte Felder, da manche
    Ladenetze/Ladepunkte auf demselben Beleg mehrere gleichzeitig
    berechnen: Startgebuehr (fester Betrag je Ladevorgang), Blockiergebuehr
    (fuer zu langes Stehenlassen nach Ladeende) und Zeitgebuehr (nach
    Ladedauer statt/zusaetzlich zu kWh abgerechnet, z.B. bei manchen
    Schnelllade-Netzen). Alle drei sind unabhaengig von der geladenen
    Menge."""
    return round(kwh * price_kwh + start_fee + block_fee + time_fee, 2)


def charge_before_pv_decision(
    available_kwh: float, needed_kwh: float, pv_forecast_kwh: Optional[float] = None
) -> bool:
    """True heisst: jetzt laden (z.B. aus dem Netz) statt auf morgige PV zu
    warten.

    Ohne pv_forecast_kwh (keine PV-Prognose-Entitaet konfiguriert): einfacher
    Vergleich, ob der aktuelle Akkustand allein fuer den morgigen Bedarf
    reicht.

    Mit pv_forecast_kwh: die morgen erwartete PV-Erzeugung darf eine Luecke
    schliessen, die der aktuelle Akkustand allein nicht abdeckt -- das ist
    der eigentliche Sinn der Empfehlung ("heute ohne PV nachladen, oder
    reicht es, bis zur PV von morgen zu warten"). Rohe Ertragsprognose ohne
    Abzug fuer den Haus-Eigenverbrauch, siehe coordinator.py fuer die
    Einheitenumrechnung und Dokumentation dieser Vereinfachung."""
    if pv_forecast_kwh is None:
        return available_kwh < needed_kwh
    return (available_kwh + pv_forecast_kwh) < needed_kwh


def rolling_consumption_kwh_per_100km(
    fahrten: list, now_ts: float, window_days: float, min_km: float,
) -> Optional[float]:
    """Realverbrauch (kWh/100km) nur aus Fahrtenbuch-Eintraegen der letzten
    `window_days` Tage -- bildet den aktuellen Fahrstil/die Jahreszeit ab,
    statt sie im Lebenszeit-Durchschnitt seit Einrichtung zu verwaschen
    (siehe coordinator.py::_vehicle_avg_consumption_kwh_per_100km()).

    Nur Fahrten mit BEIDEN Werten (km und verbrauch_kwh) zaehlen in Zaehler
    UND Nenner -- eine Fahrt ohne verbrauch_kwh (z.B. importiert ohne
    SoC-Delta und ohne mitgeliefertem Wert) darf die km nicht mitzaehlen,
    ohne die zugehoerige Energie zu kennen, sonst waere das Ergebnis zu
    niedrig verzerrt.

    None, wenn im Fenster weniger als `min_km` zusammenkommen (zu wenig
    frische Fahrten fuer einen belastbaren Wert, z.B. direkt nach
    Einrichtung oder nach laengerer Standzeit/Urlaub) -- der Aufrufer faellt
    dann auf den Lebenszeit-Durchschnitt zurueck."""
    cutoff = now_ts - window_days * 86400
    km_sum = 0.0
    kwh_sum = 0.0
    for t in fahrten:
        ts = t.get("start_ts")
        km = t.get("km")
        kwh = t.get("verbrauch_kwh")
        if ts is None or km is None or kwh is None or ts < cutoff:
            continue
        km_sum += km
        kwh_sum += kwh
    if km_sum < min_km:
        return None
    return round(kwh_sum / km_sum * 100.0, 2)


def rolling_km_per_day(fahrten: list, now_ts: float, window_days: float) -> Optional[float]:
    """Rollierendes Fahrtempo (km/Tag) nur aus Fahrtenbuch-Eintraegen der
    letzten `window_days` Tage -- analog rolling_consumption_kwh_per_100km(),
    fuer eine Leasing-Hochrechnung (siehe leasing_status()), die sich
    schneller an zuletzt geaendertes Fahrverhalten anpasst als die lineare
    Basis seit Vertragsbeginn. None ohne jede Fahrt im Fenster (der
    Aufrufer verzichtet dann auf die rollierende Hochrechnung und zeigt
    nur die lineare)."""
    cutoff = now_ts - window_days * 86400
    km_sum = 0.0
    for t in fahrten:
        ts = t.get("start_ts")
        km = t.get("km")
        if ts is None or km is None or ts < cutoff:
            continue
        km_sum += km
    if km_sum <= 0:
        return None
    return round(km_sum / window_days, 2)


def calculate_range_km(
    soc_pct: Optional[float], usable_kwh: float, consumption_kwh_per_100km: Optional[float],
) -> Optional[float]:
    """Geschaetzte Restreichweite in km: aktueller Akkustand (SoC% * nutzbare
    kWh) ueber den tatsaechlichen Verbrauch statt eines werksseitig
    pauschalen Bordanzeige-Wertes. None ohne SoC oder ohne jeden
    Verbrauchswert (weder rollierend noch Lebenszeit-Fallback verfuegbar,
    siehe rolling_consumption_kwh_per_100km())."""
    if soc_pct is None or consumption_kwh_per_100km is None or consumption_kwh_per_100km <= 0:
        return None
    battery_kwh = soc_pct / 100.0 * usable_kwh
    return round(battery_kwh / consumption_kwh_per_100km * 100.0, 1)


def is_plausible_trip_consumption(
    verbrauch_kwh: Optional[float],
    km: Optional[float],
    min_kwh_per_100km: float = 8.0,
    max_kwh_per_100km: float = 40.0,
    min_km: float = 5.0,
) -> bool:
    """Grobe Plausibilitaetspruefung fuer einen aus SoC-Delta geschaetzten
    Fahrt-Verbrauch (siehe coordinator.py::_build_trip_record). Diese
    Schaetzung ist komplett von der Genauigkeit von start_soc/end_soc
    abhaengig -- faellt eine der beiden Ablesungen in eine WiCAN-
    Verbindungsluecke (siehe soc.yaml-Historie), liefert der eingefrorene
    SoC-Wert einen viel zu kleinen oder grossen delta_soc und damit einen
    physikalisch unplausiblen Verbrauch (beobachtet: 5,5 statt ~29 kWh auf
    derselben 147km-Fahrt). True ohne km/verbrauch_kwh (nichts zu pruefen,
    z.B. bei importierten Fahrten ohne SoC-Daten), km <= 0, oder km <
    min_km -- SoC wird nur in ganzen Prozent gemeldet, auf sehr kurzen
    Strecken verzerrt allein diese Quantisierung den kWh/100km-Wert massiv
    (1km/1% SoC ergibt rechnerisch 50 kWh/100km, voellig unabhaengig vom
    echten Verbrauch), ohne dass ein Sensor-Problem vorliegt."""
    if verbrauch_kwh is None or not km or km <= 0 or km < min_km:
        return True
    per_100km = verbrauch_kwh / km * 100.0
    return min_kwh_per_100km <= per_100km <= max_kwh_per_100km


def battery_capacity_samples(history: list, min_soc_delta: float = 20.0) -> list[dict]:
    """Leitet aus abgeschlossenen Fremdladungen (coordinator.py "history")
    mit ausreichend grossem SoC-Hub eine implizite Akku-Gesamtkapazitaet ab:
    kwh / (|delta_soc| / 100). WICHTIG: "kwh" ist die vom Ladepunkt
    gemeldete/abgerechnete Energie, NICHT 1:1 die tatsaechlich in der
    Batterie gespeicherte -- auch DC-Schnellladung hat reale Ladeverluste
    (Innenwiderstand, BMS-Balancing, ueblich ~10-15%), die hier NICHT
    herausgerechnet werden (anders als bei Heim-Sessions, siehe
    home_capacity_sample(), gibt es fuer Fremdladungen keinen unabhaengigen
    zweiten Messwert, aus dem sich ein DC-Wirkungsgrad kalibrieren liesse).
    Das Ergebnis liegt deshalb typischerweise ueber der echten Kapazitaet --
    als Momentaufnahme unbrauchbar, aber als TREND ueber Monate/Jahre (faellt
    der Wert?) immer noch aussagekraeftig, da der unbekannte Verlustfaktor
    fuer ein bestimmtes Fahrzeug/Ladeverhalten ueber die Zeit ungefaehr
    konstant bleiben sollte. Ein zu kleiner Hub wird ausgeschlossen, weil die
    Ganzprozent-SoC-Quantisierung das Ergebnis sonst zusaetzlich dominiert.
    Rueckgabe: Liste von {"value": kWh, "ts": erfasst_ts} -- ungeordnet
    bezueglich Zeit sind nur Eintraege ohne erfasst_ts (uebersprungen);
    siehe estimate_battery_capacity_kwh() fuers zeitliche Zusammenfuehren
    mit anderen Quellen (z.B. Heim-Sessions)."""
    samples: list[dict] = []
    for rec in history:
        delta = rec.get("delta_soc")
        kwh = rec.get("kwh")
        ts = rec.get("erfasst_ts")
        if delta is None or kwh is None or ts is None or abs(delta) < min_soc_delta:
            continue
        samples.append({"value": round(kwh / (abs(delta) / 100.0), 2), "ts": ts})
    return samples


def home_capacity_sample(
    anchor_soc: Optional[float],
    anchor_wallbox_kwh: Optional[float],
    soc: Optional[float],
    wallbox_kwh: Optional[float],
    efficiency: Optional[float],
    min_soc_delta: float = 20.0,
) -> Optional[float]:
    """Analog battery_capacity_samples(), aber fuer eine einzelne
    abgeschlossene Heim-Ladesession: battery_kwh = wallbox_delta *
    efficiency (AC->Batterie-Wirkungsgrad, siehe EfficiencyCalibrator/
    measured_efficiency); implizite Kapazitaet = battery_kwh /
    (|delta_soc| / 100). Anders als bei Fremdladungen gibt es hier also
    tatsaechlich eine Wirkungsgradkorrektur -- der Ladepunkt (Wallbox)
    misst AC-Energie, nicht das, was am Ende in der Batterie ankommt.
    None ohne Anker/aktuelle Werte/Wirkungsgrad, oder wenn der SoC-Hub zu
    klein ist bzw. die Wallbox-Energie nicht gestiegen ist (z.B. Session
    zu kurz fuer eine belastbare Messung)."""
    if (
        anchor_soc is None or anchor_wallbox_kwh is None
        or soc is None or wallbox_kwh is None
        or efficiency is None or efficiency <= 0
    ):
        return None
    soc_delta = soc - anchor_soc
    wallbox_delta = wallbox_kwh - anchor_wallbox_kwh
    if abs(soc_delta) < min_soc_delta or wallbox_delta <= 0:
        return None
    battery_kwh = wallbox_delta * efficiency
    return round(battery_kwh / (abs(soc_delta) / 100.0), 2)


def estimate_battery_capacity_kwh(
    samples: list[dict], max_samples: int = 5, min_samples: int = 2
) -> Optional[float]:
    """Rollierender Schnitt der `max_samples` zeitlich neuesten Kapazitaets-
    Stichproben aus `samples` (Liste von {"value":..., "ts":...}, beliebige
    Quellen/Reihenfolge -- z.B. Fremdladungen aus battery_capacity_samples()
    gemischt mit Heim-Sessions aus home_capacity_sample(); wird hier explizit
    nach ts absteigend sortiert, damit die tatsaechlich neuesten Werte
    unabhaengig von der jeweiligen Quellen-Reihenfolge gewinnen). None unter
    `min_samples` -- eine einzelne Stichprobe kann ein Ausreisser sein, erst
    mehrere gemeinsam sind ein verlaessliches Signal fuer den tatsaechlichen
    Alterungstrend."""
    ordered = sorted(samples, key=lambda s: s["ts"], reverse=True)
    recent = ordered[:max_samples]
    if len(recent) < min_samples:
        return None
    values = [s["value"] for s in recent]
    return round(sum(values) / len(values), 2)


def temperature_bucket(temp_c: Optional[float], boundaries: tuple = (0.0, 10.0, 20.0)) -> Optional[str]:
    """Ordnet eine Aussentemperatur (°C) einem Band zu, z.B. fuer
    boundaries=(0, 10, 20): "<0°C", "0-10°C", "10-20°C", ">20°C" (untere
    Grenze eines Bands ist inklusiv). None ohne Temperatur."""
    if temp_c is None:
        return None
    sorted_b = sorted(boundaries)
    for i, b in enumerate(sorted_b):
        if temp_c < b:
            return f"<{b:g}°C" if i == 0 else f"{sorted_b[i - 1]:g}-{b:g}°C"
    return f">{sorted_b[-1]:g}°C"


def consumption_by_temp_bucket(
    fahrten: list, boundaries: tuple = (0.0, 10.0, 20.0), min_samples: int = 3
) -> dict:
    """Durchschnittlicher Verbrauch (kWh/100km) je Temperaturband, aus
    Fahrten mit bekanntem Verbrauch, km und Start-Temperatur (Feld
    "temp_start", siehe coordinator.py::_run_trip_detection()/
    _build_trip_record()). Baender mit weniger als `min_samples` Fahrten
    werden ausgelassen -- zu wenige Datenpunkte waeren kein verlaesslicher
    Schnitt und wuerden range_estimate_km() eher verschlechtern als
    verbessern."""
    buckets: dict[str, list[float]] = {}
    for rec in fahrten:
        verbrauch = rec.get("verbrauch_kwh")
        km = rec.get("km")
        temp = rec.get("temp_start")
        if verbrauch is None or not km or km <= 0 or temp is None:
            continue
        bucket = temperature_bucket(temp, boundaries)
        buckets.setdefault(bucket, []).append(verbrauch / km * 100.0)
    return {
        bucket: round(sum(values) / len(values), 2)
        for bucket, values in buckets.items()
        if len(values) >= min_samples
    }


def equivalent_full_cycles(fahrten: list, history: list, home_charge_pct_total: float = 0.0) -> float:
    """Aequivalente Vollzyklen (0%->100%->0% waere 1 Zyklus) aus der SoC-
    Delta-Historie: Entladung aus `fahrten` (Fahrtenbuch, |delta_soc| je
    Fahrt) plus Ladung aus `history` (Fremdladungen, delta_soc je Ladung,
    auf >= 0 geklemmt) plus `home_charge_pct_total` (Summe der SoC-Zuwaechse
    aller Heim-Ladesessions, siehe coordinator.py::_set_home()/
    _record_home_charge_pct() -- anders als bei battery_capacity_kwh() zaehlt
    hier JEDE Heim-Session, unabhaengig von SoC-Hub-Schwelle oder kalibriertem
    Wirkungsgrad, da fuer die reine Prozentpunkt-Summe kein kWh-Wert noetig
    ist). Jeder volle Zyklus zeigt sich als je ein Lade- UND ein Entlade-
    Ereignis mit zusammen 200 Prozentpunkten, daher die Summe durch 200
    statt 100."""
    discharge_pct = sum(
        abs(rec["delta_soc"]) for rec in fahrten if rec.get("delta_soc") is not None
    )
    charge_pct = sum(
        max(0.0, rec["delta_soc"]) for rec in history if rec.get("delta_soc") is not None
    )
    charge_pct += max(0.0, home_charge_pct_total)
    return round((discharge_pct + charge_pct) / 200.0, 2)


def home_session_solar_and_cost(sessions: list) -> dict:
    """Wertet evcc-eigene Heim-Ladesessions aus (siehe coordinator.py::
    _set_home(), Feld "home_sessions" -- je Eintrag {"kwh", "solar_pct"?,
    "kosten"?}, "solar_pct"/"kosten" fehlen, wenn die jeweilige evcc-
    Session-Entity beim Session-Ende nicht konfiguriert/verfuegbar war).

    - "solar_pct": kWh-gewichteter Solaranteil (%) ueber alle Sessions mit
      bekanntem solar_pct -- eine 2-kWh-Session mit 100% Solar soll den
      Schnitt nicht genauso stark ziehen wie eine 20-kWh-Session mit 0%.
    - "kosten_gesamt": reine Summe aus "kosten" -- das ist bereits der
      evcc-Gesamtpreis der jeweiligen Session (siehe _set_home()-Kommentar:
      evccs "sessionPrice" ist Waehrung, nicht Waehrung/kWh), daher KEINE
      Multiplikation mit kWh, nur Aufsummieren.
    - "preis_je_kwh": aus kosten_gesamt / kwh-Summe der bepreisten Sessions
      abgeleitet (nicht direkt aus evcc) -- praktischer Vergleichswert,
      aber nur so genau wie das Sample.

    Fehlende Werte werden ausgelassen, nicht als 0 gewertet -- eine
    Session ohne solar_pct/kosten darf den jeweils anderen Schnitt nicht
    verzerren. Ein Schluessel fehlt in der Rueckgabe ganz, wenn keine
    einzige Session dafuer Daten hat (bzw. die kWh-Summe 0 waere)."""
    result: dict = {}

    solar_kwh_sum = 0.0
    solar_weighted_sum = 0.0
    for s in sessions:
        solar_pct = s.get("solar_pct")
        kwh = s.get("kwh")
        if solar_pct is None or kwh is None or kwh <= 0:
            continue
        solar_kwh_sum += kwh
        solar_weighted_sum += solar_pct * kwh
    if solar_kwh_sum > 0:
        result["solar_pct"] = round(solar_weighted_sum / solar_kwh_sum, 1)

    kosten_gesamt = 0.0
    priced_kwh_sum = 0.0
    has_kosten = False
    for s in sessions:
        kosten = s.get("kosten")
        kwh = s.get("kwh")
        if kosten is None or kwh is None or kwh <= 0:
            continue
        has_kosten = True
        kosten_gesamt += kosten
        priced_kwh_sum += kwh
    if has_kosten:
        result["kosten_gesamt"] = round(kosten_gesamt, 2)
        if priced_kwh_sum > 0:
            result["preis_je_kwh"] = round(kosten_gesamt / priced_kwh_sum, 4)

    return result


def charging_location_breakdown(
    home_kwh: Optional[float],
    home_cost: Optional[float],
    extern_kwh: Optional[float],
    extern_cost: Optional[float],
    km_driven: Optional[float],
    home_solar_pct: Optional[float] = None,
) -> dict:
    """"So verteilt sich deine Ladung" -- Heim vs. Fremd, aus bereits an
    anderer Stelle berechneten Aggregaten (siehe coordinator.py::
    charging_location_stats()): kein eigenes Preis-/PV-/Tarif-Wissen hier,
    nur Zusammenfuehren. Rueckgabe je Ladeort ("heim"/"fremd", nur wenn
    ueberhaupt etwas bekannt ist):
      - "kwh"/"kosten": die uebergebenen Werte, gerundet (2 Nachkommastellen).
      - "kwh_anteil_pct"/"kosten_anteil_pct": Anteil an der jeweiligen
        Gesamtsumme (nur ueber die tatsaechlich bekannten Werte gebildet,
        siehe unten) -- NUR wenn dieser Ladeort selbst > 0 ist. Ein Ladeort
        mit exakt 0 kWh/Kosten bekommt bewusst KEINEN Anteil (kein "0%"),
        da das nichts Neues gegenueber dem anderen Ladeort aussagt.
      - "preis_je_kwh": Kosten/kWh dieses Ladeorts, nur wenn beide bekannt
        UND kWh > 0.
      - "solar_pct" (nur "heim"): unveraendert uebernommen (siehe
        home_session_solar_and_cost()).
    Zusaetzlich top-level "eur_je_100km": Gesamtkosten (Heim+Fremd, nur
    die bekannten Anteile summiert -- analog calculate_savings(), das
    fehlende Heimladen-Daten genauso behandelt) durch gefahrene km * 100.
    WICHTIG: es gibt KEIN €/100km je Ladeort -- man faehrt mit gemischtem
    Strom, Kilometer lassen sich nicht ursaechlich einem Ladeort zuordnen,
    nur die Gesamtstrecke gegen die Gesamtkosten ist eine sinnvolle Zahl.

    Fehlende Werte (None) werden konsequent ausgelassen, nie als 0
    gewertet -- ein Ladeort ganz ohne Daten fehlt komplett im Ergebnis,
    ein leeres/None-Eingabe-Set liefert ein leeres dict."""
    result: dict = {}

    kwh_by_loc = {"heim": home_kwh, "fremd": extern_kwh}
    cost_by_loc = {"heim": home_cost, "fremd": extern_cost}
    total_kwh = sum(v for v in kwh_by_loc.values() if v is not None)
    total_cost = sum(v for v in cost_by_loc.values() if v is not None)

    for key, kwh in kwh_by_loc.items():
        cost = cost_by_loc[key]
        loc: dict = {}
        if kwh is not None:
            loc["kwh"] = round(kwh, 2)
        if cost is not None:
            loc["kosten"] = round(cost, 2)
        if kwh is not None and kwh > 0:
            if total_kwh > 0:
                loc["kwh_anteil_pct"] = round(kwh / total_kwh * 100.0, 1)
            if cost is not None:
                loc["preis_je_kwh"] = round(cost / kwh, 4)
        if cost is not None and cost > 0 and total_cost > 0:
            loc["kosten_anteil_pct"] = round(cost / total_cost * 100.0, 1)
        if key == "heim" and home_solar_pct is not None:
            loc["solar_pct"] = round(home_solar_pct, 1)
        if loc:
            result[key] = loc

    if km_driven is not None and km_driven > 0 and (home_cost is not None or extern_cost is not None):
        result["eur_je_100km"] = round(total_cost / km_driven * 100.0, 2)

    return result


def _leasing_projection(
    gefahrene_vertrags_km: float,
    tempo_km_pro_tag: Optional[float],
    verbleibende_tage: int,
    inkl_gesamt_km: float,
    preis_mehr_km: Optional[float],
    preis_minder_km: Optional[float],
) -> Optional[dict]:
    """Eine einzelne Hochrechnung (linear ODER rollierend, siehe
    leasing_status()) aufs Vertragsende: bei unveraendertem `tempo_km_pro_tag`
    bis zum Vertragsende weitergefahren, ausgehend vom heutigen Stand. None
    ohne Tempo (z.B. linear an Tag 0 des Vertrags, oder kein rollierendes
    Tempo uebergeben)."""
    if tempo_km_pro_tag is None:
        return None
    erwartete_end_km = round(gefahrene_vertrags_km + tempo_km_pro_tag * verbleibende_tage, 1)
    mehr_bzw_minder_km = round(erwartete_end_km - inkl_gesamt_km, 1)
    projektion = {
        "tempo_km_pro_tag": round(tempo_km_pro_tag, 2),
        "erwartete_end_km": erwartete_end_km,
        "erwartete_mehr_bzw_minder_km": mehr_bzw_minder_km,
    }
    if mehr_bzw_minder_km > 0 and preis_mehr_km is not None:
        projektion["mehrkosten_eur"] = round(mehr_bzw_minder_km * preis_mehr_km, 2)
    elif mehr_bzw_minder_km < 0 and preis_minder_km is not None:
        projektion["gutschrift_eur"] = round(-mehr_bzw_minder_km * preis_minder_km, 2)
    return projektion


def leasing_status(
    aktueller_km: Optional[float],
    vertrag_start_km: Optional[float],
    vertrag_start_datum: Optional[str],
    vertrag_end_datum: Optional[str],
    inkl_gesamt_km: Optional[float],
    heute: str,
    preis_mehr_km: Optional[float] = None,
    preis_minder_km: Optional[float] = None,
    rollierendes_tempo_km_pro_tag: Optional[float] = None,
    knapp_schwelle_pct: float = 90.0,
    toleranz_pct: float = 2.0,
) -> dict:
    """Leasing-Kilometerbudget: wo stehe ich gegenueber der linearen
    Soll-Linie, und wohin laeuft es hoch- bzw. rollierend gerechnet zum
    Vertragsende. Datumsfelder als ISO-String (wie CONF_ERSTZULASSUNG),
    `heute` wird vom Aufrufer uebergeben (Testbarkeit, siehe coordinator.py)
    statt hier live ermittelt.

    Pflichtfelder: aktueller_km, vertrag_start_km, vertrag_start_datum,
    vertrag_end_datum, inkl_gesamt_km (plus ein gueltiger Vertragszeitraum,
    Ende nach Start) -- fehlt eines oder ist ein Datum nicht parsbar, liefert
    diese Funktion ein leeres dict statt zu raten oder abzustuerzen.
    preis_mehr_km/preis_minder_km/rollierendes_tempo_km_pro_tag sind
    einzeln optional: fehlen sie, fehlen nur die davon abhaengigen Felder
    (Kosten/Gutschrift bzw. die rollierende Hochrechnung), der Rest wird
    trotzdem berechnet.

    Vor Vertragsbeginn/nach Vertragsende: vergangene_tage/verbleibende_tage
    werden auf [0, vertrag_tage] geklemmt (Soll-Linie ist dann 0 bzw. voll) --
    kein Sonderfall noetig, ergibt sich direkt aus der Klemmung.

    "km_vor_ruecklauf" = Ist - Soll (gefahrene_vertrags_km -
    soll_km_bis_heute): POSITIV = schon mehr gefahren als die lineare
    Soll-Linie erlaubt (Warnsignal), NEGATIV = im Polster.

    Zwei Hochrechnungen aufs Vertragsende (siehe _leasing_projection()):
    "linear" (Tempo seit Vertragsstart -- stabile Referenz, an Tag 0 ohne
    Aussage) und "rollierend" (das vom Aufrufer uebergebene aktuelle
    Fahrtempo -- reagiert schneller auf zuletzt geaendertes Fahrverhalten,
    nur vorhanden wenn rollierendes_tempo_km_pro_tag uebergeben wurde).

    "status" (im_budget/knapp/ueber) basiert auf der LINEAREN Hochrechnung
    gegen `inkl_gesamt_km`, mit `toleranz_pct` als Puffer um 100 % herum
    (verhindert Statuswechsel durch reines Rundungsrauschen). Ohne lineare
    Hochrechnung (Tag 0) gilt "im_budget" -- an Tag 0 ist noch nichts
    gefahren, wovor man warnen koennte.

    "verbleibendes_tagesbudget_km": wie viele km/Tag fuer den Rest der
    Laufzeit noch drin sind, um exakt auf inkl_gesamt_km zu landen -- nur
    wenn noch Tage uebrig sind (kann negativ sein, wenn schon jetzt mehr
    verbraucht ist als insgesamt zusteht).

    Die Vertrags-Eingaben (vertrag_start_km/-_datum, vertrag_end_datum,
    inkl_gesamt_km, sowie preis_mehr_km/preis_minder_km falls gesetzt) werden
    unveraendert ins Ergebnis gespiegelt -- macht das Ergebnis-Dict fuer die
    Anzeige (Panel) selbsterklaerend, ohne dass der Aufrufer die Rohwerte
    separat mitfuehren muss. "resterlaubte_km"
    (inkl_gesamt_km - gefahrene_vertrags_km) ist die insgesamt noch erlaubte
    Reststrecke bis Vertragsende, unabhaengig von den verbleibenden Tagen
    (kann wie verbleibendes_tagesbudget_km negativ sein)."""
    if (
        aktueller_km is None or vertrag_start_km is None
        or vertrag_start_datum is None or vertrag_end_datum is None
        or inkl_gesamt_km is None or not inkl_gesamt_km
    ):
        return {}
    try:
        start_date = date.fromisoformat(vertrag_start_datum)
        end_date = date.fromisoformat(vertrag_end_datum)
        heute_date = date.fromisoformat(heute)
    except (TypeError, ValueError):
        return {}

    vertrag_tage = (end_date - start_date).days
    if vertrag_tage <= 0:
        return {}

    vergangene_tage = max(0, min((heute_date - start_date).days, vertrag_tage))
    verbleibende_tage = vertrag_tage - vergangene_tage

    gefahrene_vertrags_km = round(aktueller_km - vertrag_start_km, 1)
    soll_km_bis_heute = round(inkl_gesamt_km * (vergangene_tage / vertrag_tage), 1)
    km_vor_ruecklauf = round(gefahrene_vertrags_km - soll_km_bis_heute, 1)

    linear_tempo = gefahrene_vertrags_km / vergangene_tage if vergangene_tage > 0 else None
    linear = _leasing_projection(
        gefahrene_vertrags_km, linear_tempo, verbleibende_tage,
        inkl_gesamt_km, preis_mehr_km, preis_minder_km,
    )
    rollierend = _leasing_projection(
        gefahrene_vertrags_km, rollierendes_tempo_km_pro_tag, verbleibende_tage,
        inkl_gesamt_km, preis_mehr_km, preis_minder_km,
    )

    if linear is None:
        status = "im_budget"
    else:
        ratio_pct = linear["erwartete_end_km"] / inkl_gesamt_km * 100.0
        if ratio_pct > 100.0 + toleranz_pct:
            status = "ueber"
        elif ratio_pct >= knapp_schwelle_pct:
            status = "knapp"
        else:
            status = "im_budget"

    resterlaubte_km = round(inkl_gesamt_km - gefahrene_vertrags_km, 1)

    result = {
        "vertrag_start_km": vertrag_start_km,
        "vertrag_start_datum": vertrag_start_datum,
        "vertrag_end_datum": vertrag_end_datum,
        "vertrag_inkl_km": inkl_gesamt_km,
        "preis_mehr_km": preis_mehr_km,
        "preis_minder_km": preis_minder_km,
        "gefahrene_vertrags_km": gefahrene_vertrags_km,
        "resterlaubte_km": resterlaubte_km,
        "vertrag_tage": vertrag_tage,
        "vergangene_tage": vergangene_tage,
        "verbleibende_tage": verbleibende_tage,
        "soll_km_bis_heute": soll_km_bis_heute,
        "km_vor_ruecklauf": km_vor_ruecklauf,
        "status": status,
        "linear": linear,
        "rollierend": rollierend,
    }
    if verbleibende_tage > 0:
        result["verbleibendes_tagesbudget_km"] = round(
            (inkl_gesamt_km - gefahrene_vertrags_km) / verbleibende_tage, 1
        )
    return {k: v for k, v in result.items() if v is not None}
