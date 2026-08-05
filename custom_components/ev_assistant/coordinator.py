"""Coordinator: Quellen (Entity), Erkennung, Persistenz, Services."""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from homeassistant.util import dt as dt_util
from typing import Callable, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DROP_ENDS, CONF_EFFICIENCY, CONF_EVCC_STAT_AVG_PRICE, CONF_EVCC_STAT_TOTAL_KWH,
    CONF_EVCC_VEHICLE_NAME, CONF_GPS_ENTITY, CONF_HOME_ENTITY,
    CONF_HOME_PRICE_ENTITY, CONF_HOME_PRICE_KWH, CONF_HOME_TEMPLATE,
    CONF_IDLE_TIMEOUT, CONF_MOTOR_DEBOUNCE, CONF_MOTOR_ENTITY, CONF_NOISE, CONF_NOTIFY_SERVICE,
    CONF_PLUG_DEBOUNCE, CONF_PLUG_ENTITY,
    CONF_POWER_ENTITY, CONF_POWER_IS_AC, CONF_POWER_TEMPLATE,
    CONF_ODO_ENTITY, CONF_SOC_ENTITY, CONF_SOC_TEMPLATE,
    CONF_START_DELTA, CONF_TRIP_AUTO_CONFIRM, CONF_TRIP_IDLE_TIMEOUT, CONF_TRIP_MIN_KM, CONF_USABLE_KWH,
    CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL,
    CONF_VERBRENNER_L_100KM, CONF_VERBRENNER_PRICE_ENTITY,
    CONF_VERBRENNER_PRICE_PER_LITER, CONF_TANKERKOENIG_FUEL_TYPE, CONF_WALLBOX_ENERGY_ENTITY,
    CONF_WALLBOX_ENERGY_TEMPLATE,
    DEFAULT_DROP_ENDS, DEFAULT_EFFICIENCY,
    DEFAULT_IDLE_TIMEOUT, DEFAULT_MOTOR_DEBOUNCE, DEFAULT_NOISE, DEFAULT_PLUG_DEBOUNCE, DEFAULT_POWER_IS_AC,
    DEFAULT_START_DELTA, DEFAULT_TEMPLATE,
    DEFAULT_TRIP_AUTO_CONFIRM, DEFAULT_TRIP_IDLE_TIMEOUT, DEFAULT_TRIP_MIN_KM,
    DEFAULT_USABLE_KWH, DOMAIN, EFF_MAX_SAMPLES, EFF_MIN_EFFICIENCY,
    EFF_MAX_EFFICIENCY, EFF_MIN_SAMPLES, EFF_MIN_SOC_DELTA,
    EVENT_DELETED, EVENT_EDITED, EVENT_LOGGED, EVENT_PENDING, EVENT_TRIP_DELETED,
    EVENT_TRIP_EDITED, EVENT_TRIP_IMPORTED, EVENT_TRIP_LOGGED, EVENT_TRIP_PENDING,
    MILES_TO_KM, NOTIFY_TAG, STORAGE_KEY, STORAGE_VERSION,
)
from .engine import (
    ChargeDetector, ChargeSample, EfficiencyCalibrator, SignalDebouncer, TripDetector, TripSample,
    average_efficiency, calculate_savings, merge_pending, pop_pending,
)

_LOGGER = logging.getLogger(__name__)

_HOME_TRUE = ("on", "true", "1", "yes", "charging", "charge")
_INVALID = ("unknown", "unavailable", "none", "", None)
# Ab dieser Leistung (kW) gilt eine Power-Entitaet als "laedt". Der
# Home-Entitaet-Picker im Config Flow filtert auf device_class: power (z.B.
# eine Wallbox-Ladeleistung von evcc/Warp), daher muss ein numerischer Wert
# als Schwellwert statt als Text-Vergleich ausgewertet werden.
_HOME_POWER_THRESHOLD_KW = 0.1


def _empty_data() -> dict:
    return {
        "history": [],
        "totals": {"kwh": 0.0, "kosten": 0.0, "count": 0},
        "last_price": 0.0,
        "pending": [],
        "efficiency_samples": [],
        "measured_efficiency": None,
        "odo": None,
        "odo_unit": None,
        "odo_start": None,
        "odo_start_source": None,
        "wallbox_energy_start": None,
        "wallbox_energy_start_source": None,
        "evcc_vehicle_kwh_start": None,
        "evcc_stat_total_kwh_start": None,
        "evcc_vehicle_cost_start": None,
        "savings_home_kwh_start": None,
        "savings_home_cost_start": None,
        "detector_state": None,
        "plug_debounce_state": None,
        "motor_debounce_state": None,
        "verbrenner_price_last": None,
        "home_price_last": None,
        # Zeitgewichtete Durchschnittsbildung fuer den schwankenden
        # Kraftstoffpreis (siehe _price_average()/savings()): Summe(Preis *
        # Dauer) und Gesamtdauer seit Einrichtung, plus wann der aktuell
        # gueltige Wert zu gelten begann. Zeitgewichtung passt hier, weil
        # Fahren nicht systematisch mit Preisschwankungen korreliert.
        "verbrenner_price_weighted_sum": 0.0,
        "verbrenner_price_weighted_seconds": 0.0,
        "verbrenner_price_interval_start_ts": None,
        # kWh-gewichtete Durchschnittsbildung fuer den Heimstrompreis (siehe
        # _home_price_average()): Summe(Preis * geladene kWh) und geladene
        # Gesamt-kWh seit Einrichtung, plus Wallbox-Zaehlerstand, ab dem der
        # aktuell gueltige Preis zu gelten begann. Gewichtung nach geladener
        # Energie statt nach Zeit, weil Heimladen (z.B. per evcc-Tarif-
        # steuerung) gezielt in Guenstigpreis-Fenster gelegt wird -- eine
        # Zeitgewichtung wuerde den effektiv gezahlten Preis systematisch
        # ueberschaetzen.
        "home_price_weighted_energy_sum": 0.0,
        "home_price_weighted_kwh": 0.0,
        "home_price_interval_start_wallbox_energy": None,
        "fahrten": [],
        "pending_trips": [],
        "trip_totals": {"km": 0.0, "count": 0},
        "trip_detector_state": None,
        "trip_start_zone": None,
        "trip_start_soc": None,
        "odo_periods": {},
        "odo_lts": {},
    }


class EvAssistantCoordinator(DataUpdateCoordinator):
    """Haelt Detector + Zustand, feuert Events, persistiert.

    Jedes Signal wird aus einer HA-Entitaet gespeist -> funktioniert mit
    Hersteller-Integrationen (Stellantis, VW, ...) genauso wie mit z.B.
    WiCAN Pro, sofern dessen Werte als HA-Entitaet vorliegen.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._notify_tag = f"{NOTIFY_TAG}_{entry.entry_id}"
        self._unsub: list[Callable] = []
        self._soc: Optional[float] = None
        self._home: bool = False
        self._power: Optional[float] = None
        # Optional: debounced Steckerstatus (siehe engine.py::SignalDebouncer)
        # -- bleibt None ohne konfigurierten CONF_PLUG_ENTITY, ChargeDetector
        # faellt dann auf die idle_timeout_s-Heuristik zurueck.
        self._plugged_in: Optional[bool] = None
        self._plug_debouncer: Optional[SignalDebouncer] = None
        # Optional: debounced Motor-/Fahr-Status (siehe engine.py::
        # SignalDebouncer) -- bleibt None ohne konfigurierten
        # CONF_MOTOR_ENTITY, TripDetector faellt dann auf den reinen
        # Odometer-Vergleich zurueck.
        self._driving: Optional[bool] = None
        self._motor_debouncer: Optional[SignalDebouncer] = None
        self._wallbox_energy: Optional[float] = None
        self._verbrenner_price_live: Optional[float] = None
        self._home_price_live: Optional[float] = None
        # Fahrtenbuch-GPS-Vorschlag: aktuelle Zone der optionalen person-/
        # device_tracker-Entitaet, sowie die Zone, die beim Start der gerade
        # laufenden Fahrt zuletzt bekannt war (siehe _run_trip_detection()).
        self._person_zone: Optional[str] = None
        self._trip_start_zone: Optional[str] = None
        self._trip_start_soc: Optional[float] = None
        # Ob gerade eine "Tankerkoenig nicht verfuegbar"-Benachrichtigung
        # aktiv ist -- verhindert wiederholte create/dismiss-Serviceaufrufe
        # bei jedem einzelnen _recompute()-Tick (siehe _wire_tankerkoenig_price()).
        self._tankerkoenig_notified: bool = False
        self._detector: Optional[ChargeDetector] = None
        self._calibrator: Optional[EfficiencyCalibrator] = None
        self._trip_detector: Optional[TripDetector] = None
        self.data = _empty_data()

    def _opt(self, key, default=None):
        return self.entry.options.get(key, self.entry.data.get(key, default))

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            base = _empty_data()
            base.update(stored)
            self.data = base
        # Migration: "pending" war vor Mehrfach-Unterstuetzung ein einzelnes
        # Dict oder None statt einer Liste.
        pending = self.data.get("pending")
        if isinstance(pending, dict):
            self.data["pending"] = [pending]
        elif pending is None:
            self.data["pending"] = []
        # Letzter bekannter Kraftstoff-/Heimstrompreis der jeweiligen
        # Live-Entitaet als Fallback, bevor sich die Entitaet nach dem Start
        # ueberhaupt zum ersten Mal wieder meldet (siehe
        # _set_verbrenner_price/_set_home_price/savings()).
        self._verbrenner_price_live = self.data.get("verbrenner_price_last")
        self._home_price_live = self.data.get("home_price_last")
        # Zone bei Fahrtbeginn ueberlebt einen HA-Neustart waehrend einer
        # laufenden Fahrt, aus demselben Grund wie detector_state/trip_detector_state.
        self._trip_start_zone = self.data.get("trip_start_zone")
        self._trip_start_soc = self.data.get("trip_start_soc")
        self._build_detector()
        self._build_trip_detector()
        await self._setup_sources()
        # Periodischer Re-Check zusaetzlich zu den SoC-/Kilometerstand-
        # getriebenen Updates: idle_timeout_s wird nur ausgewertet, wenn
        # _run_detection()/_run_trip_detection() laufen, was normalerweise
        # nur bei einer NEUEN Messung passiert. Bleibt der Wert laenger
        # unveraendert stehen (z.B. Akku voll bzw. Auto parkt, Sensor meldet
        # sich nur bei Aenderung), wuerde eine aktive Session sonst nie per
        # Idle-Timeout abgeschlossen werden, da es kein Ereignis gibt, das
        # die Pruefung anstoesst.
        self._unsub.append(
            async_track_time_interval(self.hass, self._periodic_check, timedelta(seconds=60))
        )
        self._unsub.append(
            async_track_time_change(self.hass, self._daily_lts_refresh, hour=0, minute=5, second=0)
        )
        self.hass.async_create_task(self.async_refresh_lts_data())
        self.async_set_updated_data(self.data)

    def _build_detector(self) -> None:
        usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        manual_efficiency = float(self._opt(CONF_EFFICIENCY, DEFAULT_EFFICIENCY))
        measured_efficiency = self.data.get("measured_efficiency")
        self._detector = ChargeDetector(
            usable_kwh=usable_kwh,
            charge_efficiency=measured_efficiency if measured_efficiency is not None else manual_efficiency,
            power_is_ac=bool(self._opt(CONF_POWER_IS_AC, DEFAULT_POWER_IS_AC)),
            start_delta=float(self._opt(CONF_START_DELTA, DEFAULT_START_DELTA)),
            noise=float(self._opt(CONF_NOISE, DEFAULT_NOISE)),
            idle_timeout_s=float(self._opt(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)),
            drop_ends=float(self._opt(CONF_DROP_ENDS, DEFAULT_DROP_ENDS)),
        )
        # Stellt eine ggf. laufende (noch nicht abgeschlossene) Fremdladung
        # ueber einen HA-Neustart hinweg wieder her -- ohne das wuerde jeder
        # Neustart den Anker-/Peak-Zustand stillschweigend verwerfen und
        # eine echte, aber noch nicht fertige Erkennung verlieren.
        self._detector.load_state(self.data.get("detector_state"))
        self._calibrator = EfficiencyCalibrator(
            usable_kwh=usable_kwh,
            min_soc_delta=EFF_MIN_SOC_DELTA,
            min_efficiency=EFF_MIN_EFFICIENCY,
            max_efficiency=EFF_MAX_EFFICIENCY,
        )
        self._plug_debouncer = SignalDebouncer(
            debounce_s=float(self._opt(CONF_PLUG_DEBOUNCE, DEFAULT_PLUG_DEBOUNCE))
        )
        # Analog detector_state oben: ein gerade laufender (noch nicht ueber
        # debounce_s bestaetigter) Steckerstatus-Wechsel ueberlebt so einen
        # HA-Neustart.
        self._plug_debouncer.load_state(self.data.get("plug_debounce_state"))

    def _build_trip_detector(self) -> None:
        self._trip_detector = TripDetector(
            min_km=float(self._opt(CONF_TRIP_MIN_KM, DEFAULT_TRIP_MIN_KM)),
            idle_timeout_s=float(self._opt(CONF_TRIP_IDLE_TIMEOUT, DEFAULT_TRIP_IDLE_TIMEOUT)),
        )
        # Stellt eine ggf. laufende (noch nicht abgeschlossene) Fahrt ueber
        # einen HA-Neustart hinweg wieder her, aus demselben Grund wie bei
        # ChargeDetector.load_state() oben.
        self._trip_detector.load_state(self.data.get("trip_detector_state"))
        self._motor_debouncer = SignalDebouncer(
            debounce_s=float(self._opt(CONF_MOTOR_DEBOUNCE, DEFAULT_MOTOR_DEBOUNCE))
        )
        # Analog plug_debounce_state: ein gerade laufender (noch nicht
        # bestaetigter) Motor-Status-Wechsel ueberlebt so einen HA-Neustart.
        self._motor_debouncer.load_state(self.data.get("motor_debounce_state"))

    # ----- Quellen-Verdrahtung -------------------------------------------
    async def _setup_sources(self) -> None:
        self._wire(CONF_SOC_ENTITY, CONF_SOC_TEMPLATE, self._set_soc)
        self._wire(CONF_WALLBOX_ENERGY_ENTITY, CONF_WALLBOX_ENERGY_TEMPLATE, self._set_wallbox_energy)
        self._wire(CONF_HOME_ENTITY, CONF_HOME_TEMPLATE, self._set_home)
        self._wire(CONF_POWER_ENTITY, CONF_POWER_TEMPLATE, self._set_power)
        self._wire_odo()
        self._wire_plug()
        # tankerkoenig_fuel_type hat Vorrang vor verbrenner_price_entity (siehe
        # const.py-Kommentar bei CONF_TANKERKOENIG_FUEL_TYPE) -- daher exklusiv,
        # nie beide gleichzeitig verdrahten (sonst koennten sich beide
        # Listener gegenseitig ueberschreiben).
        if self._opt(CONF_TANKERKOENIG_FUEL_TYPE):
            self._wire_tankerkoenig_price()
        else:
            self._wire_verbrenner_price()
        self._wire_home_price()
        self._wire_gps()
        self._wire_motor()

    def _wire_home_price(self) -> None:
        """Heimstrompreis: optionale Live-Entitaet (z.B. ein dynamischer
        Tarif-Sensor), hat Vorrang vor dem festen Konfigurationswert (siehe
        _home_price())."""
        entity_id = self._opt(CONF_HOME_PRICE_ENTITY)
        if not entity_id:
            return

        @callback
        def _on_state(event) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in _INVALID:
                return
            self._set_home_price(new.state)

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in _INVALID:
            self._set_home_price(state.state)

    def _wire_verbrenner_price(self) -> None:
        """Kraftstoffpreis: optionale Live-Entitaet (z.B. Tankstellenpreis-
        Sensor), hat Vorrang vor dem festen Konfigurationswert (siehe
        savings())."""
        entity_id = self._opt(CONF_VERBRENNER_PRICE_ENTITY)
        if not entity_id:
            return

        @callback
        def _on_state(event) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in _INVALID:
                return
            self._set_verbrenner_price(new.state)

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in _INVALID:
            self._set_verbrenner_price(state.state)

    def _wire_tankerkoenig_price(self) -> None:
        """Kraftstoffpreis automatisch aus der Tankerkoenig-Integration:
        findet alle registrierten, nicht deaktivierten Preis-Sensoren der
        gewaehlten Kraftstoffsorte (ueber alle konfigurierten
        tankerkoenig-Config-Entries hinweg -- mehrere Tankstellen im Umkreis
        sind der Normalfall), ermittelt bei jeder Aenderung die guenstigste
        aktuell GEOEFFNETE Station (binary_sensor ..._status, device_class
        "door": "on" = offen) und speist das Ergebnis in _set_verbrenner_price()
        ein -- inklusive der dort bereits vorhandenen zeitgewichteten
        Durchschnittsbildung (siehe _price_average()). Sind alle bekannten
        Stationen geschlossen, wird trotzdem der guenstigste (wenn auch
        veraltete) Preis verwendet, statt ganz auszufallen."""
        fuel_type = self._opt(CONF_TANKERKOENIG_FUEL_TYPE)
        if not fuel_type:
            return

        from homeassistant.helpers import entity_registry as er

        ent_reg = er.async_get(self.hass)
        price_ids: list[str] = []
        for entry in self.hass.config_entries.async_entries("tankerkoenig"):
            for e in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
                if e.disabled_by:
                    continue
                if e.entity_id.startswith("sensor.") and e.entity_id.endswith(f"_{fuel_type}"):
                    price_ids.append(e.entity_id)
        if not price_ids:
            _LOGGER.warning(
                "ev_assistant: keine Tankerkoenig-Preis-Sensoren fuer Kraftstoffsorte '%s' gefunden",
                fuel_type,
            )
            self._tankerkoenig_notified = True
            self.hass.async_create_task(self._notify_tankerkoenig_unavailable())
            return

        def _status_id(price_id: str) -> str:
            station = price_id[len("sensor."):-len(f"_{fuel_type}")]
            return f"binary_sensor.{station}_status"

        status_ids = [_status_id(p) for p in price_ids]

        @callback
        def _recompute(_event=None) -> None:
            open_prices: list[float] = []
            all_prices: list[float] = []
            for price_id, stat_id in zip(price_ids, status_ids):
                price_state = self.hass.states.get(price_id)
                if price_state is None or price_state.state in _INVALID:
                    continue
                try:
                    price = float(price_state.state)
                except (ValueError, TypeError):
                    continue
                all_prices.append(price)
                status_state = self.hass.states.get(stat_id)
                if status_state is not None and status_state.state == "on":
                    open_prices.append(price)
            chosen = min(open_prices) if open_prices else (min(all_prices) if all_prices else None)
            if chosen is not None:
                self._set_verbrenner_price(chosen)
                if self._tankerkoenig_notified:
                    self._tankerkoenig_notified = False
                    self.hass.async_create_task(self._dismiss_tankerkoenig_unavailable())
            elif not self._tankerkoenig_notified:
                self._tankerkoenig_notified = True
                self.hass.async_create_task(self._notify_tankerkoenig_unavailable())

        self._unsub.append(
            async_track_state_change_event(self.hass, price_ids + status_ids, _recompute)
        )
        _recompute()

    def _wire_odo(self) -> None:
        """Kilometerstand: reine Anzeige-Entitaet (kein Erkennungssignal)."""
        entity_id = self._opt(CONF_ODO_ENTITY)
        if not entity_id:
            return

        @callback
        def _on_state(event) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in _INVALID:
                return
            self._set_odo(new.state, new.attributes.get("unit_of_measurement"))

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in _INVALID:
            self._set_odo(state.state, state.attributes.get("unit_of_measurement"))

    def _wire_plug(self) -> None:
        """Optionaler Stecker-/Connectivity-Sensor (device_class "plug" o.ae.).
        Anders als bei _wire() wird ein unbekannter Rohwert (unavailable/
        unknown/Entitaet entfernt) hier NICHT ignoriert, sondern explizit als
        None an den SignalDebouncer gemeldet -- der haelt in diesem Fall
        ohnehin den zuletzt bestaetigten Wert (siehe engine.py), zaehlt einen
        laufenden gegenteiligen Bestaetigungsversuch aber bewusst nicht als
        Fortsetzung, falls die Entitaet zwischenzeitlich ausfaellt."""
        entity_id = self._opt(CONF_PLUG_ENTITY)
        if not entity_id or self._plug_debouncer is None:
            return

        @callback
        def _on_state(event) -> None:
            new = event.data.get("new_state")
            self._set_plug(new.state if new is not None else None)

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        self._set_plug(state.state if state is not None else None)

    def _wire_motor(self) -> None:
        """Optionaler Motor-/Fahr-Sensor ("Ready"/Zuendung/Motorlauf) --
        ergaenzt die odometerbasierte Fahrterkennung, siehe const.py bei
        CONF_MOTOR_ENTITY. Gleiches Verhalten bei unbekanntem Rohwert wie
        _wire_plug() oben."""
        entity_id = self._opt(CONF_MOTOR_ENTITY)
        if not entity_id or self._motor_debouncer is None:
            return

        @callback
        def _on_state(event) -> None:
            new = event.data.get("new_state")
            self._set_motor(new.state if new is not None else None)

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        self._set_motor(state.state if state is not None else None)

    def _wire_gps(self) -> None:
        """Fahrtenbuch-Ortsvorschlag: optionale person-/device_tracker-
        oder sensor-Entitaet, deren Zustand bei Fahrtbeginn/-ende als
        Start-/Ziel-Ort-VORSCHLAG gespeichert wird (siehe
        _run_trip_detection()). Bei person/device_tracker ist der Zustand
        eine Zonen-Objekt-ID (z.B. "home"); bei einer beliebigen sensor-
        Entitaet wird der Zustand direkt als Ortsname verwendet, wenn er
        keiner Zone entspricht (siehe _zone_friendly_name())."""
        entity_id = self._opt(CONF_GPS_ENTITY)
        if not entity_id:
            return

        @callback
        def _on_state(event) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in _INVALID:
                return
            self._set_person_zone(new.state)

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in _INVALID:
            self._set_person_zone(state.state)

    def _wire(self, entity_key, tmpl_key, setter: Callable[[object], None]) -> None:
        entity_id = self._opt(entity_key)
        if not entity_id:
            return
        template_str = self._opt(tmpl_key, DEFAULT_TEMPLATE)

        @callback
        def _on_state(event, _setter=setter, _tmpl=template_str) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in _INVALID:
                return
            _setter(self._render(_tmpl, new.state))

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in _INVALID:
            setter(self._render(template_str, state.state))

    def _render(self, template_str, value):
        if not template_str:
            return value
        return Template(template_str, self.hass).async_render(
            {"value": value}, parse_result=False
        )

    # ----- Setter (parsen + ggf. Erkennung anstossen) --------------------
    @callback
    def _set_soc(self, raw) -> None:
        try:
            self._soc = float(raw)
        except (ValueError, TypeError):
            return
        self.hass.async_create_task(self._run_detection())

    @callback
    def _set_home(self, raw) -> None:
        was_home = self._home
        try:
            # Power-Entitaet (z.B. Wallbox-Ladeleistung): numerischer
            # Schwellwert statt Text-Vergleich.
            self._home = float(raw) > _HOME_POWER_THRESHOLD_KW
        except (ValueError, TypeError):
            # Text-/Boolean-artiges Signal (z.B. Status-Text wie "charging").
            self._home = str(raw).strip().lower() in _HOME_TRUE
        if self._calibrator is None or self._soc is None:
            return
        if not was_home and self._home:
            self._calibrator.start(self._soc, self._wallbox_energy)
        elif was_home and not self._home:
            sample = self._calibrator.end(self._soc, self._wallbox_energy)
            if sample is not None:
                self.hass.async_create_task(self._record_efficiency_sample(sample))

    @callback
    def _set_power(self, raw) -> None:
        try:
            self._power = float(raw)
        except (ValueError, TypeError):
            self._power = None

    @callback
    def _set_plug(self, raw: Optional[str]) -> None:
        if raw == "on":
            value: Optional[bool] = True
        elif raw == "off":
            value = False
        else:
            value = None  # unavailable/unknown/entfernt
        if self._plug_debouncer is None:
            return
        self._plugged_in = self._plug_debouncer.update(time.time(), value)
        self.data["plug_debounce_state"] = self._plug_debouncer.get_state()
        self.hass.async_create_task(self._save())

    @callback
    def _set_motor(self, raw: Optional[str]) -> None:
        if raw == "on":
            value: Optional[bool] = True
        elif raw == "off":
            value = False
        else:
            value = None  # unavailable/unknown/entfernt
        if self._motor_debouncer is None:
            return
        self._driving = self._motor_debouncer.update(time.time(), value)
        self.data["motor_debounce_state"] = self._motor_debouncer.get_state()
        self.hass.async_create_task(self._save())
        # Sofort neu pruefen statt auf die naechste Odometer-Aenderung oder
        # den 60s-Periodic-Check zu warten -- der Motor-Sensor soll die
        # Fahrt ja gerade unmittelbar starten/beenden (siehe const.py bei
        # CONF_MOTOR_ENTITY).
        self.hass.async_create_task(self._run_trip_detection())

    def _wallbox_energy_source(self) -> Optional[str]:
        return self._opt(CONF_WALLBOX_ENERGY_ENTITY)

    @callback
    def _set_wallbox_energy(self, raw) -> None:
        try:
            self._wallbox_energy = float(raw)
        except (ValueError, TypeError):
            self._wallbox_energy = None
            return
        # Referenzwert fuer die Heimladen-kWh-Berechnung im Kostenvergleich
        # (Gesamt-kWh seit Einrichtung = aktueller Zaehlerstand - dieser
        # Referenzwert). Wird neu gesetzt, wenn noch keiner existiert ODER
        # wenn die zugrunde liegende Entitaet/Topic seit dem letzten Mal
        # gewechselt wurde -- sonst bezieht sich der alte Referenzwert auf
        # einen anderen Zaehler und ergibt einen sinnlosen (oft stark
        # negativen) Sprung. Ein unbekannter (None) gespeicherter Quellenwert
        # gilt NICHT als Wechsel (Altbestand vor Einfuehrung dieses Felds) --
        # dort bleibt der bestehende Referenzwert unangetastet, nur die
        # Quelle wird nachtraeglich vermerkt.
        source = self._wallbox_energy_source()
        stored_source = self.data.get("wallbox_energy_start_source")
        if self.data.get("wallbox_energy_start") is None or (
            stored_source is not None and stored_source != source
        ):
            self.data["wallbox_energy_start"] = self._wallbox_energy
            self.data["wallbox_energy_start_source"] = source
            self.hass.async_create_task(self._save())
        elif stored_source is None:
            self.data["wallbox_energy_start_source"] = source
        self.async_set_updated_data(self.data)

    @callback
    def _set_odo(self, raw, unit) -> None:
        try:
            value = float(raw)
        except (ValueError, TypeError):
            return
        unit = unit or self.data.get("odo_unit") or "km"
        value_km = value * MILES_TO_KM if unit == "mi" else value

        # Plausibilitaetscheck: Kilometerstand faellt nie signifikant zurueck
        # (Sensor-Glitch), und ein einzelner Update-Sprung > 1500 km ist
        # unrealistisch (z.B. falscher Initialisierungswert oder Einheitenfehler).
        prev_km = self._odo_km()
        if prev_km is not None:
            if value_km < prev_km - 10:
                _LOGGER.debug("ODO-Glitch ignoriert: %.1f -> %.1f km", prev_km, value_km)
                return
            if value_km - prev_km > 1500:
                _LOGGER.warning("ODO-Sprung zu groß, ignoriert: %.1f -> %.1f km", prev_km, value_km)
                return

        # Referenzwert fuer die gefahrene Strecke im Kostenvergleich (siehe
        # savings()). Wird neu gesetzt, wenn noch keiner existiert ODER die
        # Kilometerstand-Entitaet seit dem letzten Mal gewechselt wurde --
        # siehe ausfuehrlichen Kommentar in _set_wallbox_energy() zum
        # identischen Problem/derselben Loesung.
        source = self._opt(CONF_ODO_ENTITY)
        stored_source = self.data.get("odo_start_source")
        if self.data.get("odo_start") is None or (
            stored_source is not None and stored_source != source
        ):
            self.data["odo_start"] = value
            self.data["odo_start_source"] = source
        elif stored_source is None:
            self.data["odo_start_source"] = source
        self.data["odo"] = value
        self.data["odo_unit"] = unit
        self._update_odo_periods(value_km)
        self.async_set_updated_data(self.data)
        self.hass.async_create_task(self._save())
        self.hass.async_create_task(self._run_trip_detection())

    def _update_odo_periods(self, odo_km: float) -> None:
        """Perioden-Baselines (Tag/Woche/Monat/Jahr) aktualisieren.
        Bei Periodenrollover wird der aktuelle Kilometerstand als neuer
        Startwert gesetzt."""
        now = dt_util.now()
        today = now.date()
        iso = today.isocalendar()
        keys = {
            "day":   str(today),
            "week":  f"{iso.year}-W{iso.week:02d}",
            "month": f"{today.year}-{today.month:02d}",
            "year":  str(today.year),
        }
        periods = self.data.setdefault("odo_periods", {})
        for period, key in keys.items():
            entry = periods.get(period)
            if entry is None or entry.get("key") != key:
                periods[period] = {"key": key, "odo_km": odo_km}

    @callback
    def _daily_lts_refresh(self, now) -> None:
        self.hass.async_create_task(self.async_refresh_lts_data())
        self.hass.async_create_task(self._daily_odo_period_rollover())

    async def _daily_odo_period_rollover(self) -> None:
        """Rollt die Tag/Woche/Monat/Jahr-Baselines (siehe
        _update_odo_periods()) auch dann taeglich, wenn seit Mitternacht
        noch kein neuer Kilometerstand gemeldet wurde (Auto steht) -- sonst
        zeigt z.B. 'km heute' morgens vor der ersten Fahrt faelschlich noch
        den gestrigen Wert, weil der Rollover bisher nur als Nebeneffekt
        einer neuen Kilometerstand-Meldung in _set_odo() ausgeloest wurde."""
        odo_km = self._odo_km()
        if odo_km is None:
            return
        self._update_odo_periods(odo_km)
        self.async_set_updated_data(self.data)
        await self._save()

    async def async_refresh_lts_data(self) -> None:
        """LTS-Summen des Odometer-Sensors abfragen fuer Perioden-Projektionen.
        Deltas der 'sum'-Werte ergeben gefahrene km pro Zeitraum."""
        odo_entity = self._opt(CONF_ODO_ENTITY)
        if not odo_entity:
            return
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period
        except ImportError:
            _LOGGER.debug("Recorder nicht verfuegbar, LTS-Abfrage uebersprungen")
            return

        now = dt_util.now()

        def _query(start_utc, end_utc):
            return statistics_during_period(
                self.hass, start_utc, end_utc, {odo_entity}, "hour", None, {"sum"}
            )

        def _first_sum(result):
            rows = result.get(odo_entity, [])
            return rows[0].get("sum") if rows else None

        def _last_sum(result):
            rows = result.get(odo_entity, [])
            return rows[-1].get("sum") if rows else None

        year_start = dt_util.as_utc(now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0))
        ago30 = dt_util.as_utc(now - timedelta(days=30))
        ago90  = dt_util.as_utc(now - timedelta(days=90))
        ago365 = dt_util.as_utc(now - timedelta(days=365))
        now_utc = dt_util.as_utc(now)

        try:
            instance = get_instance(self.hass)
            r_year  = await instance.async_add_executor_job(_query, year_start,       year_start + timedelta(hours=25))
            r_30d   = await instance.async_add_executor_job(_query, ago30,            ago30 + timedelta(hours=25))
            r_90d   = await instance.async_add_executor_job(_query, ago90,            ago90 + timedelta(hours=25))
            r_365d  = await instance.async_add_executor_job(_query, ago365,           ago365 + timedelta(hours=25))
            r_now   = await instance.async_add_executor_job(_query, now_utc - timedelta(hours=25), now_utc)

            lts = self.data.setdefault("odo_lts", {})
            sum_year  = _first_sum(r_year)
            sum_30d   = _first_sum(r_30d)
            sum_90d   = _first_sum(r_90d)
            sum_365d  = _first_sum(r_365d)
            sum_now   = _last_sum(r_now)

            if sum_year  is not None: lts["sum_year_start"] = sum_year
            if sum_30d   is not None: lts["sum_30d_ago"]    = sum_30d
            if sum_90d   is not None: lts["sum_90d_ago"]    = sum_90d
            if sum_365d  is not None: lts["sum_365d_ago"]   = sum_365d
            if sum_now   is not None: lts["sum_now"]        = sum_now

            _LOGGER.debug("LTS odo: year_start=%s 30d=%s 90d=%s 365d=%s now=%s", sum_year, sum_30d, sum_90d, sum_365d, sum_now)
        except Exception as exc:
            _LOGGER.debug("LTS-Abfrage fehlgeschlagen: %s", exc)

    @callback
    def _set_person_zone(self, raw) -> None:
        """raw ist der Zustand der konfigurierten CONF_GPS_ENTITY: bei
        person-/device_tracker entweder eine Zonen-Objekt-ID (z.B. "home")
        oder "not_home", falls in keiner Zone; bei einer beliebigen sensor-
        Entitaet ein beliebiger Text (z.B. ein vom Fahrzeug selbst gemeldeter
        Standortname). Wird nur zwischengespeichert -- der eigentliche
        Schnappschuss fuer Start-/Ziel-Ort-Vorschlag passiert in
        _run_trip_detection()."""
        self._person_zone = self._zone_friendly_name(raw)

    def _zone_friendly_name(self, raw: str) -> str:
        """Loest eine Zonen-Objekt-ID zu ihrem Anzeigenamen auf (z.B. "home"
        -> "Home"). Ohne passende Zone (z.B. "not_home", oder ein beliebiger
        sensor-Zustand ohne Zonen-Entsprechung) wird der Rohwert unveraendert
        zurueckgegeben -- so laesst sich z.B. ein sensor mit einem bereits
        lesbaren Ortsnamen direkt als Vorschlag nutzen."""
        zone_state = self.hass.states.get(f"zone.{raw}")
        if zone_state is not None:
            return zone_state.attributes.get("friendly_name", raw)
        return raw

    def _accumulate_price_interval(self, prefix: str, previous_value: Optional[float], now: float) -> None:
        """Schliesst das Zeitintervall ab, in dem `previous_value` gegolten
        hat, und addiert es zeitgewichtet zur laufenden Summe (siehe
        _price_average()). `prefix` z.B. "verbrenner_price"/"home_price"."""
        if previous_value is None:
            return
        start_ts = self.data.get(f"{prefix}_interval_start_ts")
        if start_ts is None:
            return
        elapsed = max(0.0, now - start_ts)
        self.data[f"{prefix}_weighted_sum"] = self.data.get(f"{prefix}_weighted_sum", 0.0) + previous_value * elapsed
        self.data[f"{prefix}_weighted_seconds"] = self.data.get(f"{prefix}_weighted_seconds", 0.0) + elapsed

    def _price_average(self, prefix: str, live_value: Optional[float]) -> Optional[float]:
        """Zeitgewichteter Durchschnitt aller bisher beobachteten Werte einer
        schwankenden Preis-Live-Entitaet (Kraftstoff/Heimstrom-Tarif) seit
        Einrichtung -- verhindert, dass savings()/_home_price() nur den
        aktuellen Momentanwert auf die GESAMTE seit Einrichtung gefahrene
        Strecke bzw. geladene Menge anwenden. Das noch offene Intervall (der
        aktuell gueltige Wert) wird bis JETZT mitgezaehlt, sonst wuerde die
        zuletzt gemeldete Aenderung nie einfliessen. Faellt auf den reinen
        Live-Wert zurueck, solange noch kein Intervall abgeschlossen ist
        (z.B. direkt nach der Ersteinrichtung)."""
        if live_value is None:
            return None
        weighted_sum = self.data.get(f"{prefix}_weighted_sum", 0.0)
        weighted_seconds = self.data.get(f"{prefix}_weighted_seconds", 0.0)
        start_ts = self.data.get(f"{prefix}_interval_start_ts")
        if start_ts is not None:
            elapsed = max(0.0, time.time() - start_ts)
            weighted_sum += live_value * elapsed
            weighted_seconds += elapsed
        if weighted_seconds <= 0:
            return live_value
        return round(weighted_sum / weighted_seconds, 4)

    def _accumulate_home_price_interval(self, previous_value: Optional[float], wallbox_energy: Optional[float]) -> None:
        """Schliesst das kWh-Intervall ab, in dem `previous_value` als
        Heimstrompreis gegolten hat, gewichtet nach der in diesem Intervall
        tatsaechlich geladenen Energie (NICHT nach verstrichener Zeit) --
        siehe _home_price_average()."""
        if previous_value is None or wallbox_energy is None:
            return
        start_energy = self.data.get("home_price_interval_start_wallbox_energy")
        if start_energy is None:
            return
        delta = max(0.0, wallbox_energy - start_energy)
        self.data["home_price_weighted_energy_sum"] = (
            self.data.get("home_price_weighted_energy_sum", 0.0) + previous_value * delta
        )
        self.data["home_price_weighted_kwh"] = self.data.get("home_price_weighted_kwh", 0.0) + delta

    def _home_price_average(self, live_value: Optional[float]) -> Optional[float]:
        """kWh-gewichteter Durchschnitt des Heimstrompreises seit
        Einrichtung (siehe _accumulate_home_price_interval() fuer die
        Begruendung, warum kWh- statt Zeitgewichtung). Das noch offene
        Intervall (der aktuell gueltige Preis) wird bis zum aktuellen
        Wallbox-Zaehlerstand mitgezaehlt. Faellt auf den reinen Live-Wert
        zurueck, solange noch kein Intervall abgeschlossen ist oder kein
        Wallbox-Energiezaehler konfiguriert ist -- ohne Energie-Gewicht
        laesst sich kein sinnvoller Durchschnitt bilden."""
        if live_value is None:
            return None
        weighted_sum = self.data.get("home_price_weighted_energy_sum", 0.0)
        weighted_kwh = self.data.get("home_price_weighted_kwh", 0.0)
        start_energy = self.data.get("home_price_interval_start_wallbox_energy")
        if start_energy is not None and self._wallbox_energy is not None:
            delta = max(0.0, self._wallbox_energy - start_energy)
            weighted_sum += live_value * delta
            weighted_kwh += delta
        if weighted_kwh <= 0:
            return live_value
        return round(weighted_sum / weighted_kwh, 4)

    @callback
    def _set_verbrenner_price(self, raw) -> None:
        try:
            new_value = float(raw)
        except (ValueError, TypeError):
            return
        now = time.time()
        self._accumulate_price_interval("verbrenner_price", self._verbrenner_price_live, now)
        self._verbrenner_price_live = new_value
        self.data["verbrenner_price_interval_start_ts"] = now
        # Persistiert, damit ein Neustart nicht auf "unbekannt" zurueckfaellt,
        # bevor sich die Entitaet zum ersten Mal wieder meldet (siehe
        # async_setup(), das diesen Wert als Startwert wiederherstellt).
        self.data["verbrenner_price_last"] = self._verbrenner_price_live
        self.async_set_updated_data(self.data)
        self.hass.async_create_task(self._save())

    @callback
    def _set_home_price(self, raw) -> None:
        try:
            new_value = float(raw)
        except (ValueError, TypeError):
            return
        self._accumulate_home_price_interval(self._home_price_live, self._wallbox_energy)
        self._home_price_live = new_value
        self.data["home_price_interval_start_wallbox_energy"] = self._wallbox_energy
        # Persistiert, damit ein Neustart nicht auf "unbekannt" zurueckfaellt,
        # bevor sich die Entitaet zum ersten Mal wieder meldet (siehe
        # async_setup(), das diesen Wert als Startwert wiederherstellt).
        self.data["home_price_last"] = self._home_price_live
        self.async_set_updated_data(self.data)
        self.hass.async_create_task(self._save())

    async def _run_detection(self) -> None:
        if self._soc is None or self._detector is None:
            return
        sample = ChargeSample(
            ts=time.time(), soc=self._soc, home_charging=self._home, power_kw=self._power,
            plugged_in=self._plugged_in,
        )
        event = self._detector.update(sample)
        self.data["detector_state"] = self._detector.get_state()
        await self._save()
        if event is not None:
            await self._handle_pending(event.as_dict())

    async def _periodic_check(self, _now) -> None:
        """Stoesst _run_detection()/_run_trip_detection() auch ohne neue
        SoC-/Kilometerstand-Messung an, damit idle_timeout_s bei einem
        laenger unveraenderten Wert trotzdem greift (siehe Kommentar in
        async_setup)."""
        self._recheck_plug()
        self._recheck_motor()
        await self._run_detection()
        await self._run_trip_detection()

    def _recheck_motor(self) -> None:
        """Analog _recheck_plug() oben, fuer den optionalen Motor-Sensor."""
        entity_id = self._opt(CONF_MOTOR_ENTITY)
        if not entity_id or self._motor_debouncer is None:
            return
        state = self.hass.states.get(entity_id)
        self._set_motor(state.state if state is not None else None)

    def _recheck_plug(self) -> None:
        """Fuehrt den SignalDebouncer auch ohne neues Stecker-Ereignis mit dem
        aktuellen Zeitstempel nach -- sonst wuerde eine laufende
        Bestaetigung (debounce_s) bei einem unveraendert anliegenden Rohwert
        NIE abschliessen, da HA bei unveraendertem Zustand kein neues
        state_changed-Ereignis feuert (analog der Begruendung fuer den
        periodischen idle_timeout_s-Check oben)."""
        entity_id = self._opt(CONF_PLUG_ENTITY)
        if not entity_id or self._plug_debouncer is None:
            return
        state = self.hass.states.get(entity_id)
        self._set_plug(state.state if state is not None else None)

    def _odo_km(self) -> Optional[float]:
        """Aktueller Kilometerstand in km, unabhaengig von der Quell-Einheit
        -- dieselbe Umrechnung wie in _km_driven()."""
        odo = self.data.get("odo")
        if odo is None:
            return None
        if self.data.get("odo_unit") == "mi":
            return odo * MILES_TO_KM
        return odo

    def _trip_avg_consumption_kwh(self) -> Optional[float]:
        """Durchschnittsverbrauch in kWh pro Fahrt ueber alle Fahrtenbuch-
        Eintraege mit bekanntem Verbrauch. Zwei Quellen pro Eintrag:
        importierte Fahrten liefern verbrauch_kwh direkt mit (siehe
        async_import_fahrtenbuch()); erkannte Fahrten haben stattdessen
        delta_soc (siehe _run_trip_detection()), woraus sich der Verbrauch
        wie bei der Ladewirkungsgrad-Kalibrierung ergibt: delta_soc% *
        nutzbare kWh. delta_soc ist beim Fahren negativ (SoC sinkt) -- auf
        >= 0 geklemmt, falls Rekuperation den SoC waehrend der Fahrt per
        saldo hat steigen lassen. None ohne einen einzigen Eintrag mit
        bekanntem Verbrauch."""
        fahrten = self.data.get("fahrten") or []
        usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        values: list[float] = []
        for rec in fahrten:
            verbrauch = rec.get("verbrauch_kwh")
            if verbrauch is not None:
                values.append(float(verbrauch))
                continue
            delta_soc = rec.get("delta_soc")
            if delta_soc is not None:
                values.append(max(0.0, -delta_soc) / 100.0 * usable_kwh)
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    async def _run_trip_detection(self) -> None:
        km = self._odo_km()
        if km is None or self._trip_detector is None:
            return
        was_active = self._trip_detector.active
        sample = TripSample(ts=time.time(), odo_km=km, driving=self._driving)
        event = self._trip_detector.update(sample)
        self.data["trip_detector_state"] = self._trip_detector.get_state()
        # Fahrtbeginn erkannt (idle -> aktiv): aktuelle Zone als Start-Ort-
        # Vorschlag sowie den aktuellen SoC als Start-SoC einfrieren, bevor
        # sich beide waehrend der Fahrt aendern. Persistiert, damit ein
        # HA-Neustart waehrend der Fahrt weder Vorschlag noch Start-SoC
        # verliert (siehe async_setup()).
        if not was_active and self._trip_detector.active:
            self._trip_start_zone = self._person_zone
            self.data["trip_start_zone"] = self._trip_start_zone
            self._trip_start_soc = self._soc
            self.data["trip_start_soc"] = self._trip_start_soc
        await self._save()
        if event is not None:
            pend = event.as_dict()
            pend["start_ort_vorschlag"] = self._trip_start_zone
            pend["end_ort_vorschlag"] = self._person_zone
            if self._trip_start_soc is not None and self._soc is not None:
                pend["soc_start"] = round(self._trip_start_soc, 1)
                pend["soc_end"] = round(self._soc, 1)
                pend["delta_soc"] = round(self._soc - self._trip_start_soc, 1)
            await self._handle_pending_trip(pend)

    async def _record_efficiency_sample(self, sample: float) -> None:
        """Neue Effizienz-Stichprobe aus einer abgeschlossenen Heim-
        Ladesession. Sobald genug Stichproben vorliegen (EFF_MIN_SAMPLES),
        wird der gemessene Durchschnitt automatisch fuer alle weiteren
        Berechnungen verwendet (Detector direkt aktualisiert, kein Neustart
        noetig) — der manuelle charge_efficiency-Wert bleibt Fallback."""
        samples = list(self.data.get("efficiency_samples") or [])
        samples.append(sample)
        samples = samples[-EFF_MAX_SAMPLES:]
        self.data["efficiency_samples"] = samples
        if len(samples) >= EFF_MIN_SAMPLES:
            measured = average_efficiency(samples, EFF_MAX_SAMPLES)
            self.data["measured_efficiency"] = measured
            if measured is not None and self._detector is not None:
                self._detector.charge_efficiency = measured
        await self._save()
        self.async_set_updated_data(self.data)

    # ----- Event-/Persistenz-Logik ---------------------------------------
    async def _handle_pending(self, pend: dict) -> None:
        # config_entry_id im Event, damit Automationen (z.B. packages/
        # ev_assistant_ui.yaml) bei mehreren Fahrzeugen wissen, welche
        # Instanz die Fremdladung gemeldet hat. "pending" ist eine Liste
        # (mehrere gleichzeitig offene Fremdladungen moeglich, z.B. bei
        # zwei Ladestopps auf einem Roadtrip vor dem ersten Bestaetigen) —
        # neue Ladungen werden per merge_pending() angehaengt (oder mit der
        # letzten offenen zusammengefuehrt, siehe dort).
        pend["config_entry_id"] = self.entry.entry_id
        merge_pending(self.data.setdefault("pending", []), pend)
        await self._save()
        self.hass.bus.async_fire(EVENT_PENDING, pend)
        await self._notify()
        self.async_set_updated_data(self.data)

    def _en(self) -> bool:
        """Ob die HA-Oberflaeche auf Englisch eingestellt ist. Entity-/
        Config-Flow-Texte laufen ueber strings.json/translations/*.json und
        HA's eigenes Uebersetzungssystem -- das hier betrifft nur den freien
        Benachrichtigungstext (persistent_notification/notify), den dieses
        System nicht abdeckt, daher die Sprachwahl von Hand."""
        return self.hass.config.language.startswith("en")

    async def _notify(self) -> None:
        """Baut EINE Benachrichtigung (gleiche notification_id, ersetzt sich
        selbst) fuer ALLE aktuell offenen Fremdladungen — nicht pro Ladung
        einzeln, sonst wuerden mehrere Notifications mit derselben ID sich
        gegenseitig ueberschreiben und nur die letzte waere sichtbar."""
        pending_list = self.data.get("pending") or []
        if not pending_list:
            return
        en = self._en()
        if len(pending_list) == 1:
            p = pending_list[0]
            title = "External charge detected" if en else "Fremdladung erkannt"
            if en:
                message = (
                    f"+{p['delta_soc']}% ({p['soc_start']} → {p['soc_end']}%), "
                    f"~{round(p['energy_kwh'], 1)} kWh estimated. Enter kWh and price."
                )
            else:
                message = (
                    f"+{p['delta_soc']} % ({p['soc_start']} -> {p['soc_end']} %), "
                    f"~{round(p['energy_kwh'], 1)} kWh geschätzt. kWh und Preis eintragen."
                )
        else:
            if en:
                title = f"{len(pending_list)} external charges detected"
                lines = [
                    f"{i + 1}) +{p['delta_soc']}% ({p['soc_start']} → {p['soc_end']}%), "
                    f"~{round(p['energy_kwh'], 1)} kWh"
                    for i, p in enumerate(pending_list)
                ]
                message = f"{len(pending_list)} open external charges:\n" + "\n".join(lines) + "\nEnter kWh and price."
            else:
                title = f"{len(pending_list)} Fremdladungen erkannt"
                lines = [
                    f"{i + 1}) +{p['delta_soc']} % ({p['soc_start']} -> {p['soc_end']} %), "
                    f"~{round(p['energy_kwh'], 1)} kWh"
                    for i, p in enumerate(pending_list)
                ]
                message = f"{len(pending_list)} offene Fremdladungen:\n" + "\n".join(lines) + "\nkWh und Preis eintragen."

        notify_service = self._opt(CONF_NOTIFY_SERVICE)
        if notify_service:
            try:
                await self.hass.services.async_call(
                    "notify", notify_service,
                    {
                        "title": title,
                        "message": message,
                        "data": {
                            "tag": self._notify_tag,
                            "persistent": True,
                            "actions": [{"action": "URI", "title": "Enter" if en else "Eintragen", "uri": "/lovelace"}],
                        },
                    },
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("notify.%s fehlgeschlagen: %s", notify_service, err)
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": self._notify_tag, "title": title, "message": message},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    # ----- Fahrtenbuch -----------------------------------------------------
    async def _handle_pending_trip(self, pend: dict) -> None:
        """Analog _handle_pending() fuer Fremdladungen: "pending_trips" ist
        eine Liste (mehrere gleichzeitig offene, noch nicht bestaetigte
        Fahrten moeglich), neue Fahrten werden angehaengt, nie ueberschrieben
        -- AUSSER CONF_TRIP_AUTO_CONFIRM ist aktiv, dann direkt ins
        Fahrtenbuch uebernehmen (siehe const.py)."""
        pend["config_entry_id"] = self.entry.entry_id
        if self._opt(CONF_TRIP_AUTO_CONFIRM, DEFAULT_TRIP_AUTO_CONFIRM):
            rec = self._build_trip_record(pend, pend.get("start_ort_vorschlag"), pend.get("end_ort_vorschlag"))
            self._finalize_trip_record(rec)
            await self._save()
            self.hass.bus.async_fire(EVENT_TRIP_LOGGED, rec)
            self.async_set_updated_data(self.data)
            return
        self.data.setdefault("pending_trips", []).append(pend)
        await self._save()
        self.hass.bus.async_fire(EVENT_TRIP_PENDING, pend)
        await self._notify_trip()
        self.async_set_updated_data(self.data)

    async def _notify_trip(self) -> None:
        """Analog _notify(): eine Benachrichtigung (eigene notification_id)
        fuer ALLE aktuell offenen Fahrten."""
        pending_list = self.data.get("pending_trips") or []
        if not pending_list:
            return
        en = self._en()
        if len(pending_list) == 1:
            p = pending_list[0]
            if en:
                title = "Trip detected"
                message = f"{p['km']} km driven. Enter start/end location."
            else:
                title = "Fahrt erkannt"
                message = f"{p['km']} km gefahren. Start-/Zielort eintragen."
        else:
            lines = [f"{i + 1}) {p['km']} km" for i, p in enumerate(pending_list)]
            if en:
                title = f"{len(pending_list)} trips detected"
                message = f"{len(pending_list)} open trips:\n" + "\n".join(lines) + "\nEnter start/end location."
            else:
                title = f"{len(pending_list)} Fahrten erkannt"
                message = f"{len(pending_list)} offene Fahrten:\n" + "\n".join(lines) + "\nStart-/Zielort eintragen."

        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": f"{self._notify_tag}_trip", "title": title, "message": message},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _dismiss_trip(self) -> None:
        try:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": f"{self._notify_tag}_trip"}, blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _notify_tankerkoenig_unavailable(self) -> None:
        """Dauerhafte Benachrichtigung, solange Tankerkoenig keinen einzigen
        gueltigen Preis fuer die gewaehlte Kraftstoffsorte liefert (siehe
        _wire_tankerkoenig_price()) -- der Kostenvergleich rechnet in der
        Zwischenzeit mit dem letzten bekannten bzw. festen Fallback-Preis
        weiter, statt auszufallen."""
        en = self._en()
        title = "Tankerkönig unavailable" if en else "Tankerkönig nicht verfügbar"
        message = (
            "No valid fuel price could be read from any configured Tankerkönig "
            "station — the cost comparison keeps using the last known or fixed "
            "fallback fuel price instead."
            if en else
            "Von keiner konfigurierten Tankerkönig-Station konnte ein gültiger "
            "Kraftstoffpreis gelesen werden — der Kostenvergleich rechnet "
            "stattdessen mit dem letzten bekannten bzw. festen Fallback-Preis weiter."
        )
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": f"{self._notify_tag}_tankerkoenig", "title": title, "message": message},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _dismiss_tankerkoenig_unavailable(self) -> None:
        try:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss",
                {"notification_id": f"{self._notify_tag}_tankerkoenig"}, blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    def _build_trip_record(self, pend: dict, start_ort: Optional[str], end_ort: Optional[str]) -> dict:
        """Baut den Fahrtenbuch-Eintrag aus einer offenen Fahrt (siehe
        pend-Schema in _run_trip_detection()) -- gemeinsam genutzt von
        async_log_trip() (manuelle Bestaetigung) und _handle_pending_trip()
        (CONF_TRIP_AUTO_CONFIRM, siehe const.py). start_ort/end_ort leer
        (None/"") ist hier zulaessig -- anders als beim manuellen Bestaetigen
        ueber das Panel/den Service gibt es beim Auto-Confirm ohne
        CONF_GPS_ENTITY keinen anderen Wert."""
        rec = {
            "config_entry_id": self.entry.entry_id,
            "datum": date.fromtimestamp(pend["start_ts"]).isoformat(),
            "start_ts": pend["start_ts"], "end_ts": pend["end_ts"],
            "odo_start": pend["odo_start"], "odo_end": pend["odo_end"],
            "km": pend["km"], "start_ort": start_ort or "", "end_ort": end_ort or "",
            "erfasst_ts": int(time.time()),
        }
        if pend.get("soc_start") is not None:
            rec["soc_start"] = pend["soc_start"]
            rec["soc_end"] = pend.get("soc_end")
            rec["delta_soc"] = pend.get("delta_soc")
            if rec["delta_soc"] is not None:
                # Verbrauch aus SoC-Delta, analog _trip_avg_consumption_kwh() --
                # damit haben erkannte Fahrten wie importierte einen
                # verbrauch_kwh-Wert und die Panel-Historie kann ihn
                # einheitlich anzeigen. delta_soc ist beim Fahren negativ
                # (SoC sinkt); auf >= 0 geklemmt falls Rekuperation den SoC
                # waehrend der Fahrt per saldo hat steigen lassen.
                usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
                rec["verbrauch_kwh"] = round(max(0.0, -rec["delta_soc"]) / 100.0 * usable_kwh, 2)
        return rec

    def _finalize_trip_record(self, rec: dict) -> None:
        self.data.setdefault("fahrten", []).insert(0, rec)
        totals = self.data.setdefault("trip_totals", {"km": 0.0, "count": 0})
        totals["km"] = round(totals.get("km", 0.0) + rec["km"], 2)
        totals["count"] = totals.get("count", 0) + 1

    async def async_log_trip(self, start_ort: str, end_ort: str, start_ts: Optional[float] = None) -> None:
        """Bestaetigt eine offene Fahrt mit Start-/Zielort. Bei mehreren
        gleichzeitig offenen waehlt `start_ts` die gemeinte aus; ohne Angabe
        die aelteste (FIFO). Anders als async_log_charge gibt es KEINEN
        Fallback auf einen manuellen Einzeleintrag ohne offene Fahrt --
        odo_start/odo_end/km stammen ausschliesslich aus der Erkennung."""
        pending_list = list(self.data.get("pending_trips") or [])
        pend = pop_pending(pending_list, start_ts)
        if pend is None:
            _LOGGER.warning("ev_assistant: keine offene Fahrt zum Bestaetigen gefunden")
            return
        self.data["pending_trips"] = pending_list

        rec = self._build_trip_record(pend, start_ort, end_ort)
        self._finalize_trip_record(rec)
        await self._save()
        self.hass.bus.async_fire(EVENT_TRIP_LOGGED, rec)
        if pending_list:
            await self._notify_trip()
        else:
            await self._dismiss_trip()
        self.async_set_updated_data(self.data)

    async def async_discard_trip(self, start_ts: Optional[float] = None) -> None:
        """Verwirft eine offene Fahrt. Bei mehreren gleichzeitig offenen
        waehlt `start_ts` die gemeinte aus; ohne Angabe die aelteste (FIFO)."""
        pending_list = list(self.data.get("pending_trips") or [])
        pop_pending(pending_list, start_ts)
        self.data["pending_trips"] = pending_list
        await self._save()
        if pending_list:
            await self._notify_trip()
        else:
            await self._dismiss_trip()
        self.async_set_updated_data(self.data)

    async def async_edit_trip(
        self,
        erfasst_ts: int,
        start_ort: Optional[str] = None,
        end_ort: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        km: Optional[float] = None,
        odo_start: Optional[float] = None,
        odo_end: Optional[float] = None,
        soc_start: Optional[float] = None,
        soc_end: Optional[float] = None,
        verbrauch_kwh: Optional[float] = None,
    ) -> bool:
        """Korrigiert einen bereits bestaetigten Fahrtenbuch-Eintrag --
        alle Felder optional, nur mitgegebene Werte werden geaendert. Bei
        Aenderung von km wird trip_totals["km"] um die Differenz angepasst
        (nicht neu aus der Historie berechnet, analog async_edit_charge()).
        Aendern sich soc_start/soc_end, wird delta_soc neu berechnet, und
        verbrauch_kwh (falls nicht explizit mitgegeben) daraus neu
        abgeleitet -- dieselbe Formel wie in async_log_trip(). Aendert sich
        start_ts, wird "datum" (fuer den CSV-Export) daraus neu abgeleitet,
        analog async_log_trip(). Gibt False zurueck, wenn kein Eintrag mit
        erfasst_ts gefunden wurde."""
        fahrten = self.data.get("fahrten") or []
        for rec in fahrten:
            if rec.get("erfasst_ts") == erfasst_ts:
                if start_ort is not None:
                    rec["start_ort"] = start_ort
                if end_ort is not None:
                    rec["end_ort"] = end_ort
                if start_ts is not None:
                    rec["start_ts"] = start_ts
                    rec["datum"] = date.fromtimestamp(start_ts).isoformat()
                if end_ts is not None:
                    rec["end_ts"] = end_ts
                if km is not None:
                    old_km = rec.get("km", 0.0)
                    rec["km"] = round(float(km), 2)
                    totals = self.data.setdefault("trip_totals", {"km": 0.0, "count": 0})
                    totals["km"] = round(totals.get("km", 0.0) - old_km + rec["km"], 2)
                if odo_start is not None:
                    rec["odo_start"] = round(float(odo_start), 2)
                if odo_end is not None:
                    rec["odo_end"] = round(float(odo_end), 2)
                if soc_start is not None:
                    rec["soc_start"] = round(float(soc_start), 1)
                if soc_end is not None:
                    rec["soc_end"] = round(float(soc_end), 1)
                if soc_start is not None or soc_end is not None:
                    if rec.get("soc_start") is not None and rec.get("soc_end") is not None:
                        rec["delta_soc"] = round(rec["soc_end"] - rec["soc_start"], 1)
                        if verbrauch_kwh is None:
                            usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
                            rec["verbrauch_kwh"] = round(max(0.0, -rec["delta_soc"]) / 100.0 * usable_kwh, 2)
                if verbrauch_kwh is not None:
                    rec["verbrauch_kwh"] = round(float(verbrauch_kwh), 2)
                await self._save()
                self.hass.bus.async_fire(EVENT_TRIP_EDITED, rec)
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_delete_trip(self, erfasst_ts: int) -> bool:
        """Loescht einen bereits bestaetigten Fahrtenbuch-Eintrag
        vollstaendig (z.B. eine faelschlich erkannte Fahrt) -- analog
        async_delete_charge(). Passt trip_totals um den geloeschten Betrag
        an. Gibt False zurueck, wenn kein Eintrag mit erfasst_ts gefunden
        wurde. Nicht rueckgaengig zu machen."""
        fahrten = self.data.get("fahrten") or []
        for i, rec in enumerate(fahrten):
            if rec.get("erfasst_ts") == erfasst_ts:
                fahrten.pop(i)
                totals = self.data.setdefault("trip_totals", {"km": 0.0, "count": 0})
                totals["km"] = round(totals.get("km", 0.0) - rec["km"], 2)
                totals["count"] = max(0, totals.get("count", 0) - 1)
                await self._save()
                self.hass.bus.async_fire(EVENT_TRIP_DELETED, rec)
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_import_fahrtenbuch(self, trips: list) -> int:
        """Importiert historische Fahrten aus einer Fremdquelle (z.B. Export
        einer anderen Fahrtenbuch-App) direkt in data['fahrten'], ohne den
        Umweg ueber die Kilometerstand-Erkennung -- odo_start/odo_end
        bleiben dabei None, da diese Fremddaten keine Kilometerstaende
        liefern, nur die gefahrene Strecke. Format je Eintrag: start/ende
        als 'YYYY-MM-DD HH:MM:SS' in lokaler Zeit, start_ort/ziel_ort,
        strecke (km), optional verbrauch_kwh/avg_verbrauch/avg_speed.
        Ungueltige Eintraege werden uebersprungen (Warnung im Log) statt
        den gesamten Import abzubrechen. Eintraege mit einem bereits
        vorhandenen start_ts werden uebersprungen, damit ein wiederholter
        Import keine Dubletten erzeugt. Gibt die Anzahl tatsaechlich neu
        importierter Fahrten zurueck."""
        existing_starts = {rec.get("start_ts") for rec in self.data.get("fahrten") or []}
        imported: list[dict] = []
        for row in trips:
            try:
                start_dt = datetime.strptime(row["start"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
                end_dt = datetime.strptime(row["ende"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
                start_ts = start_dt.timestamp()
                if start_ts in existing_starts:
                    continue
                rec = {
                    "config_entry_id": self.entry.entry_id,
                    "datum": start_dt.date().isoformat(),
                    "start_ts": start_ts, "end_ts": end_dt.timestamp(),
                    "odo_start": None, "odo_end": None,
                    "km": round(float(row["strecke"]), 2),
                    "start_ort": row["start_ort"], "end_ort": row["ziel_ort"],
                    "erfasst_ts": int(time.time()), "quelle": "import",
                }
                for key in ("verbrauch_kwh", "avg_verbrauch", "avg_speed"):
                    if row.get(key) is not None:
                        rec[key] = float(row[key])
                imported.append(rec)
                existing_starts.add(start_ts)
            except (KeyError, TypeError, ValueError) as exc:
                _LOGGER.warning(
                    "ev_assistant: Fahrtenbuch-Import: ungueltiger Eintrag uebersprungen (%s): %r", exc, row
                )

        if not imported:
            return 0

        fahrten = self.data.setdefault("fahrten", [])
        fahrten.extend(imported)
        fahrten.sort(key=lambda r: r.get("start_ts") or 0, reverse=True)

        totals = self.data.setdefault("trip_totals", {"km": 0.0, "count": 0})
        totals["km"] = round(totals.get("km", 0.0) + sum(r["km"] for r in imported), 2)
        totals["count"] = totals.get("count", 0) + len(imported)

        await self._save()
        self.hass.bus.async_fire(EVENT_TRIP_IMPORTED, {"anzahl": len(imported)})
        en = self._en()
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "notification_id": f"{self._notify_tag}_import",
                    "title": "Trip log import" if en else "Fahrtenbuch-Import",
                    "message": (
                        f"{len(imported)} trip(s) imported."
                        if en else f"{len(imported)} Fahrt(en) importiert."
                    ),
                },
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass
        self.async_set_updated_data(self.data)
        return len(imported)

    async def async_simulate_trip(self, km: float) -> None:
        odo = self._odo_km() or 0.0
        now = int(time.time())
        pend = {
            "start_ts": now - 1800, "end_ts": now,
            "odo_start": round(odo, 2), "odo_end": round(odo + km, 2),
            "km": round(km, 2),
        }
        await self._handle_pending_trip(pend)

    async def async_export_fahrtenbuch(self) -> str:
        """Exportiert das Fahrtenbuch (chronologisch aufsteigend) als CSV
        nach www/, damit es unter /local/... herunterladbar ist."""
        fahrten = list(reversed(self.data.get("fahrten") or []))
        path = self.hass.config.path("www", f"ev_assistant_fahrtenbuch_{self.entry.entry_id}.csv")
        await self.hass.async_add_executor_job(self._write_fahrtenbuch_csv, path, fahrten)
        filename = os.path.basename(path)
        en = self._en()
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {
                    "notification_id": f"{self._notify_tag}_export",
                    "title": "Trip log exported" if en else "Fahrtenbuch exportiert",
                    "message": (
                        f"CSV export ready: [{filename}](/local/{filename})" if en
                        else f"CSV-Export bereit: [{filename}](/local/{filename})"
                    ),
                },
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass
        return path

    @staticmethod
    def _write_fahrtenbuch_csv(path: str, fahrten: list[dict]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Datum", "Start", "Ziel", "km Start", "km Ende", "Strecke (km)"])
            for t in fahrten:
                odo_start = t["odo_start"] if t["odo_start"] is not None else ""
                odo_end = t["odo_end"] if t["odo_end"] is not None else ""
                writer.writerow([t["datum"], t["start_ort"], t["end_ort"], odo_start, odo_end, t["km"]])

    async def async_log_charge(self, kwh: float, price: float, start_ts: Optional[float] = None) -> None:
        """Bestaetigt eine offene Fremdladung. Bei mehreren gleichzeitig
        offenen waehlt `start_ts` die gemeinte aus; ohne Angabe wird die
        aelteste bestaetigt (FIFO)."""
        kwh = round(float(kwh), 2)
        price = round(float(price), 4)
        rec = {
            "config_entry_id": self.entry.entry_id,
            "kwh": kwh, "preis_kwh": price, "kosten": round(kwh * price, 2),
            "erfasst_ts": int(time.time()),
        }
        pending_list = list(self.data.get("pending") or [])
        pend = pop_pending(pending_list, start_ts)
        if pend:
            rec.update({
                "start_ts": pend.get("start_ts"), "soc_start": pend.get("soc_start"),
                "soc_end": pend.get("soc_end"), "delta_soc": pend.get("delta_soc"),
                "schaetzung_kwh": pend.get("energy_kwh"), "quelle": pend.get("energy_source"),
                "dauer_min": pend.get("duration_min"),
            })
        elif start_ts is not None:
            rec["start_ts"] = start_ts
        self.data["pending"] = pending_list

        self.data.setdefault("history", []).insert(0, rec)
        totals = self.data["totals"]
        totals["kwh"] = round(totals.get("kwh", 0.0) + kwh, 2)
        totals["kosten"] = round(totals.get("kosten", 0.0) + rec["kosten"], 2)
        totals["count"] = totals.get("count", 0) + 1
        self.data["last_price"] = price
        await self._save()
        self.hass.bus.async_fire(EVENT_LOGGED, rec)
        if pending_list:
            await self._notify()
        else:
            await self._dismiss()
        self.async_set_updated_data(self.data)

    async def async_edit_charge(self, erfasst_ts: int, kwh: float, price: float) -> bool:
        """Korrigiert einen bereits bestaetigten Historien-Eintrag (z.B.
        Tippfehler bei kWh/Preis beim Erfassen bemerkt). Passt die
        laufenden Summen um die Differenz an statt sie aus der Historie neu
        zu berechnen. Gibt False zurueck, wenn kein Eintrag mit erfasst_ts
        gefunden wurde."""
        history = self.data.get("history") or []
        for rec in history:
            if rec.get("erfasst_ts") == erfasst_ts:
                old_kwh = rec["kwh"]
                old_kosten = rec["kosten"]
                kwh = round(float(kwh), 2)
                price = round(float(price), 4)
                kosten = round(kwh * price, 2)
                totals = self.data["totals"]
                totals["kwh"] = round(totals.get("kwh", 0.0) - old_kwh + kwh, 2)
                totals["kosten"] = round(totals.get("kosten", 0.0) - old_kosten + kosten, 2)
                rec["kwh"] = kwh
                rec["preis_kwh"] = price
                rec["kosten"] = kosten
                if history[0] is rec:
                    self.data["last_price"] = price
                await self._save()
                self.hass.bus.async_fire(EVENT_EDITED, rec)
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_delete_charge(self, erfasst_ts: int) -> bool:
        """Loescht einen bereits bestaetigten Historien-Eintrag vollstaendig
        (z.B. eine faelschlich erkannte Fremdladung, die gar keine war).
        Passt die laufenden Summen um den geloeschten Betrag an; war der
        geloeschte Eintrag der juengste, wird last_price auf den neuen
        juengsten Eintrag zurueckgesetzt (oder 0.0, falls die Historie
        danach leer ist). Gibt False zurueck, wenn kein Eintrag mit
        erfasst_ts gefunden wurde."""
        history = self.data.get("history") or []
        for i, rec in enumerate(history):
            if rec.get("erfasst_ts") == erfasst_ts:
                was_newest = i == 0
                history.pop(i)
                totals = self.data["totals"]
                totals["kwh"] = round(totals.get("kwh", 0.0) - rec["kwh"], 2)
                totals["kosten"] = round(totals.get("kosten", 0.0) - rec["kosten"], 2)
                totals["count"] = max(0, totals.get("count", 0) - 1)
                if was_newest:
                    self.data["last_price"] = history[0]["preis_kwh"] if history else 0.0
                await self._save()
                self.hass.bus.async_fire(EVENT_DELETED, rec)
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_discard(self, start_ts: Optional[float] = None) -> None:
        """Verwirft eine offene Fremdladung. Bei mehreren gleichzeitig
        offenen waehlt `start_ts` die gemeinte aus; ohne Angabe wird die
        aelteste verworfen (FIFO)."""
        pending_list = list(self.data.get("pending") or [])
        pop_pending(pending_list, start_ts)
        self.data["pending"] = pending_list
        await self._save()
        if pending_list:
            await self._notify()
        else:
            await self._dismiss()
        self.async_set_updated_data(self.data)

    async def async_simulate(self, soc_start: float, soc_end: float, source: str = "soc") -> None:
        eff = float(self._opt(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) or 1.0
        usable = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        batt = (soc_end - soc_start) / 100.0 * usable
        ac = batt / eff
        now = int(time.time())
        pend = {
            "start_ts": now - 3600, "end_ts": now,
            "soc_start": round(soc_start, 1), "soc_end": round(soc_end, 1),
            "delta_soc": round(soc_end - soc_start, 1),
            "energy_kwh": round(ac, 2), "energy_batt_kwh": round(batt, 2),
            "losses_kwh": round(ac - batt, 2), "energy_source": source,
            "duration_min": 60.0, "kind": "extern",
        }
        await self._handle_pending(pend)

    # ----- Kostenvergleich gegenueber einem Verbrenner --------------------
    def _km_driven(self) -> Optional[float]:
        odo = self.data.get("odo")
        odo_start = self.data.get("odo_start")
        if odo is None or odo_start is None:
            return None
        delta = odo - odo_start
        if self.data.get("odo_unit") == "mi":
            delta *= MILES_TO_KM
        return round(delta, 1)

    def _vehicle_avg_consumption_kwh_per_100km(self) -> Optional[float]:
        """Durchschnittsverbrauch des Fahrzeugs in kWh/100km ueber die
        gesamte Zeit seit Einrichtung, aus der Energiebilanz: (Heimladen +
        Fremdladen) kWh gesamt, geteilt durch die seit Einrichtung
        gefahrenen km (siehe _km_driven()/_home_kwh()) -- dieselben immer
        vorhandenen Gesamtwerte wie savings(), unabhaengig davon, ob jede
        einzelne Fahrt im Fahrtenbuch bestaetigt wurde (anders als
        _trip_avg_consumption_kwh(), das nur bestaetigte/importierte
        Fahrten zaehlt). Kleine systematische Abweichung durch den Akku-
        Fuellstand zum Einrichtungszeitpunkt, ueber laengere Zeitraeume
        vernachlaessigbar."""
        km = self._km_driven()
        if km is None or km <= 0:
            return None
        home_kwh = self._home_kwh_since_setup() or 0.0
        external_kwh = self.data.get("totals", {}).get("kwh", 0.0)
        total_kwh = home_kwh + external_kwh
        return round(total_kwh / km * 100.0, 2)

    def _evcc_vehicle_key(self) -> Optional[str]:
        """Fahrzeugname in evcc: aus Konfiguration oder via Auto-Erkennung
        anhand von Hersteller/Modell (z.B. 'VW ID4' -> 'id4') -- dieselbe
        Berechnung wie der Geraetename (siehe entity.py/__init__.py), NICHT
        aus entry.title geparst: dessen Format war nicht immer
        "EV Assistant (Hersteller Modell)" (aeltere Eintraege wurden ohne
        Klammern angelegt), ein Parsen dort ist daher fragil."""
        configured = self._opt(CONF_EVCC_VEHICLE_NAME)
        if configured:
            return configured
        state = self.hass.states.get("sensor.evcc_charging_sessions_vehicles")
        if not state:
            return None
        hersteller = self._opt(CONF_VEHICLE_HERSTELLER) or ""
        modell = self._opt(CONF_VEHICLE_MODELL) or ""
        label = f"{hersteller} {modell}".strip().lower()
        _skip = {"state_class", "icon", "friendly_name", "unit_of_measurement", "device_class"}
        for key, val in state.attributes.items():
            if key in _skip or not isinstance(val, dict):
                continue
            k = key.lower()
            if label.find(k) != -1 or all(w in label for w in k.split()):
                return key
        return None

    def _since_setup(self, value: float, start_key: str) -> float:
        """Zieht vom absoluten/kumulativen Zaehlerwert `value` den beim
        ersten Aufruf gespeicherten Referenzwert ab (persistiert unter
        `start_key`). Ohne das wuerde ein Zaehler, der schon laenger laeuft
        als EV Assistant eingerichtet ist (z.B. evccs eigene Statistiken,
        unabhaengig von dieser Integration gefuehrt), faelschlich als "seit
        Einrichtung" interpretiert -- mit absurd hohen
        Durchschnittsverbrauchswerten als Folge, weil der Zaehler
        (Zaehler) einen viel laengeren Zeitraum abdeckt als die seit
        Einrichtung gefahrenen km (Nenner, siehe
        _vehicle_avg_consumption_kwh_per_100km())."""
        start = self.data.get(start_key)
        if start is None:
            self.data[start_key] = value
            self.hass.async_create_task(self._save())
            start = value
        return round(max(0.0, value - start), 2)

    def _home_kwh(self) -> Optional[float]:
        """Heimladen kWh seit Einrichtung. Prioritaet: (1) evccs eigene
        Fahrzeug-Session-Statistik (praezise, aber erfordert evccs
        "Erweiterte Fahrzeugdaten" und ist daher meist unavailable), (2)
        evccs standortweite Gesamt-Ladeenergie-Statistik
        (CONF_EVCC_STAT_TOTAL_KWH) -- NUR wenn ein Wallbox-Energiezaehler
        fuer dieses Fahrzeug konfiguriert ist, da diese Statistik
        standortweit (nicht pro Fahrzeug) ist und sonst bei mehreren
        EV-Assistant-Instanzen faelschlich auch einem Fahrzeug zugerechnet
        wuerde, das gar nicht zuhause laedt, (3) Differenz des Wallbox-
        Energiezaehlers seit Einrichtung. (1) und (2) sind evccs eigene,
        kumulative Statistiken -- werden ungekuerzt uebernommen, da evcc
        die praeziseste Quelle ist. Fuer Savings/kWh100km gibt
        _home_kwh_since_setup() das Delta seit ev_assistant-Einrichtung."""
        veh = self._evcc_vehicle_key()
        if veh:
            state = self.hass.states.get("sensor.evcc_charging_sessions_vehicles")
            if state:
                veh_data = state.attributes.get(veh)
                if isinstance(veh_data, dict):
                    energy = veh_data.get("chargedEnergy")
                    if energy is not None:
                        return round(float(energy), 2)
        if self._opt(CONF_WALLBOX_ENERGY_ENTITY):
            kwh_entity = self._opt(CONF_EVCC_STAT_TOTAL_KWH)
            if kwh_entity:
                state = self.hass.states.get(kwh_entity)
                if state is not None and state.state not in _INVALID:
                    try:
                        value = float(state.state)
                    except (ValueError, TypeError):
                        value = None
                    if value is not None:
                        return round(value, 2)
        start = self.data.get("wallbox_energy_start")
        if self._wallbox_energy is None or start is None:
            return None
        return round(self._wallbox_energy - start, 2)

    def _home_cost(self) -> Optional[float]:
        """Heimladen-Kosten direkt aus evccs Fahrzeug-Session-Statistik,
        falls verfuegbar -- praeziser als home_kwh * home_price, da evcc
        pro Session mit dem tatsaechlichen Tarif rechnet statt mit dem
        standortweiten Durchschnittspreis. Wie bei _home_kwh() wird der
        kumulative evcc-Wert ungekuerzt uebernommen; das Delta seit
        ev_assistant-Einrichtung liefert _home_cost_since_setup()."""
        veh = self._evcc_vehicle_key()
        if veh:
            state = self.hass.states.get("sensor.evcc_charging_sessions_vehicles")
            if state:
                veh_data = state.attributes.get(veh)
                if isinstance(veh_data, dict):
                    cost = veh_data.get("cost")
                    if cost is not None:
                        try:
                            return round(float(cost), 2)
                        except (ValueError, TypeError):
                            pass
        return None

    def _home_kwh_since_setup(self) -> Optional[float]:
        """home_kwh-Anteil seit ev_assistant-Einrichtung — fuer Savings und
        kWh/100km. Setzt einmalig beim ersten Aufruf den Referenzwert auf den
        aktuellen absoluten Zaehlerstand und gibt danach nur das Delta zurueck.
        Wird nie automatisch zurueckgesetzt, damit das Datum der Einrichtung
        erhalten bleibt, auch wenn der absolute evcc-Zaehler weiterlaeuft."""
        kwh = self._home_kwh()
        if kwh is None:
            return None
        start = self.data.get("savings_home_kwh_start")
        if start is None:
            self.data["savings_home_kwh_start"] = kwh
            self.hass.async_create_task(self._save())
            start = kwh
        return round(max(0.0, kwh - start), 2)

    def _home_cost_since_setup(self) -> Optional[float]:
        """home_cost-Anteil seit ev_assistant-Einrichtung — fuer Savings.
        Analoges Prinzip zu _home_kwh_since_setup()."""
        cost = self._home_cost()
        if cost is None:
            return None
        start = self.data.get("savings_home_cost_start")
        if start is None:
            self.data["savings_home_cost_start"] = cost
            self.hass.async_create_task(self._save())
            start = cost
        return round(max(0.0, cost - start), 2)

    def _home_price(self) -> Optional[float]:
        """Heimstrompreis. Prioritaet: (1) evccs standortweite
        Durchschnittspreis-Statistik (CONF_EVCC_STAT_AVG_PRICE) -- NUR wenn
        ein Wallbox-Energiezaehler fuer dieses Fahrzeug konfiguriert ist
        (siehe _home_kwh() fuer die Begruendung; evcc gewichtet dabei
        bereits selbst nach tatsaechlich geladener Energie), (2) der
        kWh-gewichtete Durchschnitt der eigenen Live-Entitaet (falls
        konfiguriert und ein gueltiger Wert vorliegt, siehe
        _home_price_average()), (3) der feste Konfigurationswert."""
        if self._opt(CONF_WALLBOX_ENERGY_ENTITY):
            price_entity = self._opt(CONF_EVCC_STAT_AVG_PRICE)
            if price_entity:
                state = self.hass.states.get(price_entity)
                if state is not None and state.state not in _INVALID:
                    try:
                        return round(float(state.state), 4)
                    except (ValueError, TypeError):
                        pass
        if self._home_price_live is not None:
            avg = self._home_price_average(self._home_price_live)
            if avg is not None:
                return avg
        price = self._opt(CONF_HOME_PRICE_KWH)
        return float(price) if price is not None else None

    def savings(self) -> Optional[dict]:
        """Kostenvergleich gegenueber einem Verbrenner (siehe
        engine.py::calculate_savings), oder None wenn eine der zwingend
        noetigen Groessen (Kilometerstand-Delta, Verbrenner-Verbrauch,
        Kraftstoffpreis) fehlt. Heimstrompreis und Kraftstoffpreis: der
        gewichtete Durchschnitt der jeweiligen Live-Entitaet (falls
        konfiguriert und ein gueltiger Wert vorliegt) hat Vorrang vor dem
        festen Konfigurationswert -- ein schwankender Preis wird so ueber
        die gesamte Menge/Strecke seit Einrichtung gewichtet statt nur mit
        seinem aktuellen Momentanwert angewendet zu werden. Kraftstoffpreis:
        zeitgewichtet (siehe _price_average()) -- Fahren korreliert nicht
        systematisch mit Preisschwankungen. Heimstrompreis: kWh-gewichtet
        (siehe _home_price_average()) -- Heimladen wird (z.B. per evcc)
        gezielt in Guenstigpreis-Fenster gelegt, eine Zeitgewichtung wuerde
        den effektiv gezahlten Preis dadurch systematisch ueberschaetzen."""
        verbrenner_l = self._opt(CONF_VERBRENNER_L_100KM)
        verbrenner_price = self._opt(CONF_VERBRENNER_PRICE_PER_LITER)
        if self._verbrenner_price_live is not None:
            avg = self._price_average("verbrenner_price", self._verbrenner_price_live)
            if avg is not None:
                verbrenner_price = avg
        return calculate_savings(
            km_driven=self._km_driven(),
            home_kwh=self._home_kwh_since_setup(),
            home_price_kwh=self._home_price(),
            fremdladen_kosten=self.data.get("totals", {}).get("kosten", 0.0),
            verbrenner_l_100km=float(verbrenner_l) if verbrenner_l is not None else None,
            verbrenner_price_per_liter=float(verbrenner_price) if verbrenner_price is not None else None,
            home_cost=self._home_cost_since_setup(),
        )

    async def _dismiss(self) -> None:
        try:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss", {"notification_id": self._notify_tag}, blocking=False
            )
        except Exception:  # noqa: BLE001
            pass

    async def _save(self) -> None:
        await self._store.async_save(self.data)

    async def async_shutdown(self) -> None:
        for unsub in self._unsub:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsub = []
