"""Coordinator: Quellen (Entity), Erkennung, Persistenz, Services."""
from __future__ import annotations

import csv
import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_change, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    AC_MAX_KW,
    BATTERY_CAPACITY_HOME_MAX_STORED,
    BATTERY_CAPACITY_MAX_SAMPLES,
    BATTERY_CAPACITY_MIN_SAMPLES,
    BATTERY_CAPACITY_MIN_SOC_DELTA,
    CO2_PER_LITER_KG,
    CONF_CO2_PER_KWH,
    CONF_DROP_ENDS,
    CONF_EFFICIENCY,
    CONF_EVCC_SESSION_ENERGY,
    CONF_EVCC_SESSION_PRICE,
    CONF_EVCC_SESSION_SOLAR_PCT,
    CONF_EVCC_STAT_AVG_PRICE,
    CONF_EVCC_STAT_TOTAL_KWH,
    CONF_EVCC_VEHICLE_NAME,
    CONF_GPS_ENTITY,
    CONF_HOME_ENTITY,
    CONF_HOME_PRICE_ENTITY,
    CONF_HOME_PRICE_KWH,
    CONF_HOME_TEMPLATE,
    CONF_IDLE_TIMEOUT,
    CONF_LADE_MODUS,
    CONF_LEASING_END_DATUM,
    CONF_LEASING_INKL_KM,
    CONF_LEASING_PREIS_MEHR_KM,
    CONF_LEASING_PREIS_MINDER_KM,
    CONF_LEASING_START_DATUM,
    CONF_LEASING_START_KM,
    CONF_MOTOR_DEBOUNCE,
    CONF_MOTOR_ENTITY,
    CONF_NOISE,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_EVENTS,
    CONF_ODO_ENTITY,
    CONF_OUTSIDE_TEMP_ENTITY,
    CONF_PLUG_DEBOUNCE,
    CONF_PLUG_ENTITY,
    CONF_POWER_ENTITY,
    CONF_POWER_IS_AC,
    CONF_POWER_TEMPLATE,
    CONF_PV_FORECAST_ENTITY,
    CONF_SOC_ENTITY,
    CONF_SOC_TEMPLATE,
    CONF_SOC_THRESHOLDS,
    CONF_START_DELTA,
    CONF_TANKERKOENIG_FUEL_TYPE,
    CONF_TRIP_AUTO_CONFIRM,
    CONF_TRIP_IDLE_TIMEOUT,
    CONF_TRIP_MIN_KM,
    CONF_USABLE_KWH,
    CONF_USAGE_PROFILE_BUFFER_PCT,
    CONF_VEHICLE_HERSTELLER,
    CONF_VEHICLE_MODELL,
    CONF_VERBRENNER_L_100KM,
    CONF_VERBRENNER_PRICE_ENTITY,
    CONF_VERBRENNER_PRICE_PER_LITER,
    CONF_WALLBOX_ENERGY_ENTITY,
    CONF_WALLBOX_ENERGY_TEMPLATE,
    DEFAULT_CO2_PER_KWH_G,
    DEFAULT_CO2_PER_LITER_KG,
    DEFAULT_DROP_ENDS,
    DEFAULT_EFFICIENCY,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_MOTOR_DEBOUNCE,
    DEFAULT_NOISE,
    DEFAULT_NOTIFY_EVENTS,
    DEFAULT_PLUG_DEBOUNCE,
    DEFAULT_POWER_IS_AC,
    DEFAULT_SOC_THRESHOLDS,
    DEFAULT_START_DELTA,
    DEFAULT_TEMPLATE,
    DEFAULT_TRIP_AUTO_CONFIRM,
    DEFAULT_TRIP_IDLE_TIMEOUT,
    DEFAULT_TRIP_MIN_KM,
    DEFAULT_USABLE_KWH,
    DEFAULT_USAGE_PROFILE_BUFFER_PCT,
    DOMAIN,
    EFF_MAX_EFFICIENCY,
    EFF_MAX_SAMPLES,
    EFF_MIN_EFFICIENCY,
    EFF_MIN_SAMPLES,
    EFF_MIN_SOC_DELTA,
    EVENT_DELETED,
    EVENT_EDITED,
    EVENT_LOGGED,
    EVENT_PENDING,
    EVENT_TRIP_DELETED,
    EVENT_TRIP_EDITED,
    EVENT_TRIP_IMPORTED,
    EVENT_TRIP_LOGGED,
    EVENT_TRIP_PENDING,
    FAHRTEN_MAX_MONATE,
    HISTORY_MAX_MONATE,
    IMPLAUSIBLE_POWER_RATIO,
    IMPLAUSIBLE_REGEN_DELTA_PCT,
    LADEKARTE_AVG_DAYS_PER_MONTH,
    LEASING_KNAPP_SCHWELLE_PCT,
    LEASING_TOLERANZ_PCT,
    MAX_POWER_GAP_S,
    MILES_TO_KM,
    MIN_USAGE_PROFILE_DAYS,
    NOTIFY_EVENT_FAHRT,
    NOTIFY_EVENT_FREMDLADUNG,
    NOTIFY_EVENT_LEASING,
    NOTIFY_EVENT_SOC_SCHWELLE,
    NOTIFY_EVENT_TANKERKOENIG,
    NOTIFY_TAG,
    STORAGE_KEY,
    STORAGE_VERSION,
    TEMP_BUCKET_BOUNDARIES,
    TEMP_BUCKET_MIN_SAMPLES,
    TRIP_CONSUMPTION_CHECK_MIN_KM,
    TRIP_CONSUMPTION_MAX_KWH_100KM,
    TRIP_CONSUMPTION_MIN_KWH_100KM,
    resolve_lade_modus,
)
from .engine import (
    ChargeDetector,
    ChargeSample,
    EfficiencyCalibrator,
    SignalDebouncer,
    TripDetector,
    TripSample,
    ac_dc_breakdown_from_totals,
    anbieter_breakdown_from_totals,
    apply_ac_dc_delta,
    apply_anbieter_delta,
    average_efficiency,
    battery_capacity_samples,
    bekannte_anbieter,
    calculate_co2_savings,
    calculate_range_km,
    calculate_savings,
    charge_before_pv_decision,
    charge_cost,
    charge_pct_of_history_entry,
    charging_location_breakdown,
    consumption_by_temp_bucket_from_totals,
    equivalent_full_cycles_from_totals,
    estimate_battery_capacity_kwh,
    home_capacity_sample,
    home_session_solar_and_cost,
    is_plausible_trip_consumption,
    ladekarte_legacy_gebuehren,
    ladekarten_summary,
    leasing_status,
    merge_pending,
    pop_pending,
    rolling_consumption_kwh_per_100km,
    rolling_km_per_day,
    split_by_age,
    temp_bucket_contribution,
    temperature_bucket,
    trip_avg_consumption_kwh_from_totals,
    trip_consumption_contribution,
    trip_discharge_pct,
    trip_weekday_kwh_parts,
    update_period_baseline,
    weekday_usage_profile_from_totals,
)

_LOGGER = logging.getLogger(__name__)

_HOME_TRUE = ("on", "true", "1", "yes", "charging", "charge")
_INVALID = ("unknown", "unavailable", "none", "", None)
# Ab dieser Leistung (kW) gilt eine Power-Entitaet als "laedt". Der
# Home-Entitaet-Picker im Config Flow filtert auf device_class: power (z.B.
# eine Wallbox-Ladeleistung von evcc/Warp), daher muss ein numerischer Wert
# als Schwellwert statt als Text-Vergleich ausgewertet werden.
_HOME_POWER_THRESHOLD_KW = 0.1
# Sekunden, um die unkritische Zwischenstaende (Sensor-Mirrorwerte, Debounce-/
# Rollover-/Kalibrierungs-Buchhaltung) gebuendelt werden, statt bei jedem
# einzelnen Update sofort synchron auf die Disk zu schreiben -- siehe
# EvAssistantCoordinator._save_soon().
_SAVE_DELAY = 10
# Index = date.weekday() (0=Montag..6=Sonntag), fuer usage_profile_tomorrow().
_WEEKDAY_NAMES_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Sekunden, die eine konfigurierte Quell-Entitaet mindestens unavailable/
# unknown/entfernt sein muss, bevor ein Repair-Issue erscheint (siehe
# _check_entity_health()) -- deutlich laenger als kurze Aussetzer/Wach-
# Fenster-Bliips, aber kurz genug, um denselben Tag noch zu merken.
_ENTITY_STALE_THRESHOLD_S = 1800
# Alle verdrahteten Quell-Entitaeten (siehe async_setup()), die ueberwacht
# werden -- fuer jede hat strings.json einen eigenen
# "entity_unavailable_<key>"-Uebersetzungsschluessel (Titel nennt das Feld
# konkret, Text ist gemeinsam mit {entity_id}/{minuten} parametrisiert).
_HEALTH_MONITORED_KEYS = (
    CONF_SOC_ENTITY, CONF_ODO_ENTITY, CONF_PLUG_ENTITY, CONF_MOTOR_ENTITY,
    CONF_HOME_ENTITY, CONF_POWER_ENTITY, CONF_WALLBOX_ENERGY_ENTITY,
    CONF_GPS_ENTITY, CONF_HOME_PRICE_ENTITY, CONF_VERBRENNER_PRICE_ENTITY,
)

# Rolling-Fenster fuer den Realverbrauch (siehe engine.py::
# rolling_consumption_kwh_per_100km()) -- deutlich kuerzer als der
# Lebenszeit-Durchschnitt seit Einrichtung, damit sich Jahreszeit/aktueller
# Fahrstil in der Reichweitenschaetzung abbilden statt ueber Monate/Jahre
# verwaschen zu werden.
_ROLLING_CONSUMPTION_WINDOW_DAYS = 30
# Mindest-km im Rolling-Fenster, bevor ihm statt dem Lebenszeit-Durchschnitt
# vertraut wird -- sonst wuerde z.B. eine einzelne kurze Kaltstart-/
# Stadtfahrt direkt nach einer laengeren Standzeit den Verbrauch verzerren.
_ROLLING_CONSUMPTION_MIN_KM = 50.0

# Rolling-Fenster fuer das aktuelle Fahrtempo (siehe engine.py::
# rolling_km_per_day()), das leasing_stats() als "rollierende" Projektion
# neben die lineare Projektion seit Vertragsbeginn stellt -- kurz genug, um
# eine juengere Verhaltensaenderung (z.B. neuer Arbeitsweg) schneller
# abzubilden als der lineare Vertrags-Schnitt es koennte.
_LEASING_ROLLING_WINDOW_DAYS = 30
# Rangfolge fuer die Hysterese in _check_leasing_thresholds() -- je hoeher,
# desto schlechter der Status.
_LEASING_STATUS_RANK = {"im_budget": 0, "knapp": 1, "ueber": 2}


def _empty_data() -> dict:
    return {
        "history": [],
        "totals": {"kwh": 0.0, "kosten": 0.0, "count": 0},
        "last_price": 0.0,
        "pending": [],
        "efficiency_samples": [],
        "measured_efficiency": None,
        "home_capacity_samples": [],
        "home_charge_pct_total": 0.0,
        "home_sessions": [],
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
        "soc_thresholds_notified": [],
        "soc_thresholds_was_charging": False,
        "leasing_notified_identity": None,
        "leasing_notified_rank": 0,
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
        "trip_start_temp": None,
        "odo_periods": {},
        "cost_periods": {},
        "kwh_periods": {},
        "odo_lts": {},
        "ladekarten": [],
        # Lebenszeit-Baselines, unabhaengig von der Laenge von "fahrten"/
        # "history" (siehe _apply_trip_baselines()/_apply_charge_baselines(),
        # _migrate_lifetime_baselines() und _async_truncate_lifetime_lists())
        # -- tragen equivalent_full_cycles(), _trip_avg_consumption_kwh(),
        # _consumption_by_temp_bucket(), charging_location_stats()'s
        # ac_dc/anbieter-Aufschluesselung und usage_profile(), damit diese
        # Kennzahlen beim Archivieren alter Detail-Eintraege unveraendert
        # bleiben.
        "fahrten_discharge_pct_total": 0.0,
        "history_charge_pct_total": 0.0,
        "ac_dc_totals": {},
        "anbieter_totals": {},
        "trip_consumption_exact_totals": {"sum_kwh": 0.0, "count": 0},
        "trip_consumption_deltasoc_totals": {"sum_frac": 0.0, "count": 0},
        "temp_bucket_totals": {},
        "fahrtenbuch_first_ts": None,
        "weekday_kwh_exact_totals": {},
        "weekday_km_est_totals": {},
        "lifetime_baselines_migrated": False,
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
        # Separates, unbegrenzt wachsendes Archiv fuer aus "fahrten"/
        # "history" ausgelagerte, aeltere Detail-Eintraege (siehe
        # _async_truncate_lifetime_lists()) -- bewusst NICHT derselbe Store
        # wie self._store: der wird bei praktisch jeder Coordinator-
        # Aktualisierung neu geschrieben (siehe _save()/_save_soon()), ein
        # unbegrenzt wachsendes Archiv darin wuerde die urspruengliche
        # Wachstumsproblematik nur verschieben statt loesen. Dieser Store
        # wird stattdessen nur einmal taeglich (Truncation) sowie bei
        # Export/Import gelesen/geschrieben.
        self._archive_store = Store(hass, 1, f"{STORAGE_KEY}_{entry.entry_id}_archiv")
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
        # Optionale Aussentemperatur (Wetter-Integration oder Sensor) fuer
        # temperaturabhaengige Verbrauchs-/Reichweiten-Auswertung -- siehe
        # _wire_outside_temp()/_extract_temp() sowie engine.temperature_
        # bucket()/consumption_by_temp_bucket(). _trip_start_temp wird wie
        # _trip_start_soc beim Fahrtbeginn eingefroren (siehe
        # _run_trip_detection()).
        self._outside_temp: Optional[float] = None
        self._trip_start_temp: Optional[float] = None
        # Ob gerade eine "Tankerkoenig nicht verfuegbar"-Benachrichtigung
        # aktiv ist -- verhindert wiederholte create/dismiss-Serviceaufrufe
        # bei jedem einzelnen _recompute()-Tick (siehe _wire_tankerkoenig_price()).
        self._tankerkoenig_notified: bool = False
        self._detector: Optional[ChargeDetector] = None
        self._calibrator: Optional[EfficiencyCalibrator] = None
        self._trip_detector: Optional[TripDetector] = None
        # Version-Zaehler fuer data["fahrten"] -- erhoeht sich bei jeder
        # Mutation (neue/bearbeitete/geloeschte/importierte Fahrt, siehe
        # _finalize_trip_record()/async_edit_trip()/async_delete_trip()/
        # async_import_fahrtenbuch()). _trip_avg_consumption_kwh() und
        # usage_profile() lesen inzwischen aus laufend gepflegten
        # Lebenszeit-Baselines (siehe _apply_trip_baselines()) statt die
        # fahrten-Liste bei jedem Coordinator-Update (jedes SoC-/Odo-/
        # Wallbox-Sample) neu zu durchlaufen -- die Caches unten sorgen
        # trotzdem dafuer, dass selbst dieser (guenstige) Baseline-Zugriff
        # nur bei tatsaechlicher Aenderung neu passiert, nicht bei jedem
        # Sensor-Update. Rein im Arbeitsspeicher (kein Persistenzbedarf:
        # nach einem Neustart ist das erste Ergebnis ohnehin ein Cache-Miss).
        self._fahrten_version = 0
        self._trip_avg_cache: Optional[tuple[int, Optional[float]]] = None
        self._usage_profile_cache: Optional[tuple[int, str, Optional[dict]]] = None
        # Repair-Issues fuer laenger unavailable/entfernte Quell-Entitaeten
        # (siehe _check_entity_health()) -- rein im Arbeitsspeicher, ein
        # Neustart faengt frisch mit "noch nicht lange genug schlecht" an,
        # statt sofort ein Issue aus der vorherigen Session zu recyceln.
        self._entity_bad_since: dict[str, float] = {}
        self._entity_issue_active: set[str] = set()
        # Cache fuer den rollierenden Realverbrauch, analog
        # _usage_profile_cache (Schluessel: _fahrten_version + heutiges
        # Datum, da das Rolling-Fenster auch ohne Fahrtenbuch-Aenderung
        # einmal pro Tag weiterwandert).
        self._rolling_consumption_cache: Optional[tuple[int, str, Optional[float]]] = None
        # Cache fuer den Verbrauch je Temperaturband (siehe
        # _consumption_by_temp_bucket()) -- analog _trip_avg_cache.
        self._temp_bucket_cache: Optional[tuple[int, dict]] = None
        # Cache fuer equivalent_full_cycles() -- haengt an BEIDEN Versionen
        # (Fahrtenbuch UND Fremdladungs-Historie tragen beide dazu bei).
        self._cycles_cache: Optional[tuple[tuple[int, int, int], float]] = None
        # Cache fuer home_session_stats() -- haengt am selben Zaehler wie
        # battery_capacity_kwh(), da beide am Session-Ende-Hook in
        # _set_home() aktualisiert werden.
        self._home_session_stats_cache: Optional[tuple[int, dict]] = None
        # Analog _fahrten_version, aber fuer "history" (Fremdladungen) --
        # bislang gab es dort noch keinen darauf angewiesenen Cache.
        self._history_version = 0
        # Analog fuer Heim-Session-Kapazitaets-Stichproben (siehe
        # _set_home()/_record_home_capacity_sample()) -- eigener Zaehler,
        # da diese unabhaengig von Fremdladungen dazukommen.
        self._home_capacity_version = 0
        self._battery_capacity_cache: Optional[tuple[tuple[int, int], Optional[float]]] = None
        # Cache fuer leasing_stats() -- Schluessel zusaetzlich zu
        # _fahrten_version auch ueber den Kilometerstand (aktueller km ist
        # selbst Teil der Berechnung, nicht nur das Fahrtenbuch) und das
        # heutige Datum (die lineare/rollierende Projektion wandert taeglich
        # weiter, auch ohne neue Fahrt) verkettet. Vertrags-Identitaet
        # (Start-km + End-Datum, siehe _check_leasing_thresholds()) ebenfalls
        # im Schluessel -- ein Reconfigure loest ohnehin einen kompletten
        # Coordinator-Reload aus (siehe __init__.py::_async_reload()), das
        # ist also nur zusaetzliche Absicherung, keine Notwendigkeit.
        self._leasing_cache: Optional[tuple[tuple, dict]] = None
        # Start-Anker (SoC + Wallbox-kWh) einer laufenden Heim-Ladesession,
        # analog EfficiencyCalibrator._anchor_*, aber unabhaengig davon
        # gefuehrt: die Kapazitaets-Schwelle (BATTERY_CAPACITY_MIN_SOC_DELTA)
        # ist deutlich breiter als EfficiencyCalibrator.min_soc_delta, beide
        # Zwecke sollen sich nicht gegenseitig beeinflussen.
        self._capacity_anchor_soc: Optional[float] = None
        self._capacity_anchor_wallbox_kwh: Optional[float] = None
        self.data = _empty_data()

    def _opt(self, key, default=None):
        return self.entry.options.get(key, self.entry.data.get(key, default))

    def lade_modus(self) -> str:
        """Aktueller Lade-Modus (siehe const.py::resolve_lade_modus()) --
        steuert nur Panel-/Config-Flow-Sichtbarkeit, keine Rechenlogik.
        Bestandsinstallationen ohne gespeicherten CONF_LADE_MODUS erhalten
        hier defensiv "gemischt" -- identisch zum bisherigen Verhalten."""
        return resolve_lade_modus(self._opt(CONF_LADE_MODUS))

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
        # Migration: Lebenszeit-Baselines (Vollzyklen/Verbrauchs-/
        # Temperaturband-/Wochentags-Schnitt, AC/DC-/Anbieter-
        # Aufschluesselung) aus einer bereits vorhandenen fahrten/history-
        # Liste ruecksichern -- MUSS vor der ersten Archivierung/Kuerzung
        # laufen, siehe _migrate_lifetime_baselines(). Sofort persistiert
        # (nicht ueber _save_soon()), damit ein Neustart vor dem naechsten
        # regulaeren Speichern die Migration nicht unbemerkt verliert und
        # beim naechsten Start faelschlich doppelt zaehlend wiederholt.
        if self._migrate_lifetime_baselines():
            await self._save()
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
        self._trip_start_temp = self.data.get("trip_start_temp")
        self._build_detector()
        self._build_trip_detector()
        await self._setup_sources()
        # Seedet die Kosten-/kWh-Perioden-Baselines sofort statt erst beim
        # naechsten taeglichen Rollover (siehe _daily_cost_period_rollover()/
        # _daily_kwh_period_rollover()) -- sonst waeren "Kosten/kWh
        # heute/Woche/..." bis Mitternacht unknown.
        self._update_cost_periods()
        self._update_kwh_periods()
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
            regen_implausible_delta_pct=IMPLAUSIBLE_REGEN_DELTA_PCT,
            implausible_power_ratio=IMPLAUSIBLE_POWER_RATIO,
            max_power_gap_s=MAX_POWER_GAP_S,
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
        self._wire_outside_temp()

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
            for price_id, stat_id in zip(price_ids, status_ids, strict=True):
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

    def _wire_outside_temp(self) -> None:
        """Optionale Aussentemperatur-Entitaet fuer temperaturabhaengige
        Verbrauchs-/Reichweiten-Auswertung (siehe engine.temperature_
        bucket()/consumption_by_temp_bucket()). Der aktuelle Wert wird
        live nachgefuehrt (fuer range_estimate_km()); beim Fahrtbeginn
        wird er zusaetzlich als Start-Temperatur eingefroren (siehe
        _run_trip_detection())."""
        entity_id = self._opt(CONF_OUTSIDE_TEMP_ENTITY)
        if not entity_id:
            return

        @callback
        def _on_state(event) -> None:
            new = event.data.get("new_state")
            if new is None or new.state in _INVALID:
                return
            self._outside_temp = self._extract_temp(new)

        self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
        state = self.hass.states.get(entity_id)
        if state is not None and state.state not in _INVALID:
            self._outside_temp = self._extract_temp(state)

    @staticmethod
    def _extract_temp(state) -> Optional[float]:
        """Akzeptiert sowohl eine reine Temperatursensor-Entitaet (state
        ist direkt die Zahl) als auch eine weather.*-Entitaet (state ist
        ein Wetter-Text wie "sunny", die Temperatur steckt im Attribut
        "temperature")."""
        try:
            return float(state.state)
        except (ValueError, TypeError):
            pass
        try:
            return float(state.attributes.get("temperature"))
        except (ValueError, TypeError):
            return None

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
            self._capacity_anchor_soc = self._soc
            self._capacity_anchor_wallbox_kwh = self._wallbox_energy
        elif was_home and not self._home:
            sample = self._calibrator.end(self._soc, self._wallbox_energy)
            if sample is not None:
                self.hass.async_create_task(self._record_efficiency_sample(sample))
            cap_sample = home_capacity_sample(
                self._capacity_anchor_soc, self._capacity_anchor_wallbox_kwh,
                self._soc, self._wallbox_energy,
                self.data.get("measured_efficiency"),
                BATTERY_CAPACITY_MIN_SOC_DELTA,
            )
            # Reiner SoC-Zuwachs dieser Session fuer equivalent_full_cycles()
            # -- unabhaengig von der SoC-Hub-Schwelle/Wirkungsgrad oben, da
            # dafuer kein kWh-Wert noetig ist (siehe engine.
            # equivalent_full_cycles()). Jede Heim-Session zaehlt mit,
            # nicht nur die fuer eine Kapazitaets-Stichprobe breiten.
            if self._capacity_anchor_soc is not None and self._soc is not None:
                raw_delta = self._soc - self._capacity_anchor_soc
                if raw_delta > 0:
                    self.hass.async_create_task(self._record_home_charge_pct(raw_delta))
            self._capacity_anchor_soc = None
            self._capacity_anchor_wallbox_kwh = None
            if cap_sample is not None:
                self.hass.async_create_task(self._record_home_capacity_sample(cap_sample))
            # evcc-Session-Kennzahlen (Solaranteil, Gesamtkosten) fuer
            # home_session_stats()/engine.home_session_solar_and_cost().
            # CONF_EVCC_SESSION_ENERGY ist evccs eigener Session-kWh-Wert --
            # unabhaengig von CONF_WALLBOX_ENERGY_ENTITY verfuegbar, dient
            # hier als Gewichtungsbasis. Ohne ihn kein Record (keine
            # Gewichtungsbasis, siehe engine-Docstring). solar_pct/kosten
            # je einzeln optional -- fehlt die Entity oder ist der Wert
            # ungueltig, wird das Feld einfach weggelassen.
            # WICHTIG: evccs "sessionPrice" (CONF_EVCC_SESSION_PRICE) ist
            # die GESAMTKOSTEN der Session in Waehrung, KEIN Preis/kWh --
            # verifiziert im evcc_intg-Quellcode: Tag.SESSIONPRICE hat
            # native_unit_of_measurement "@@@" (Waehrung), das getrennte
            # Tag.SESSIONPRICEPERKWH hat "@@@/kWh". Deshalb bei der
            # Aggregation nur aufsummieren, nicht mit kWh multiplizieren.
            session_kwh = self._read_evcc_session_value(CONF_EVCC_SESSION_ENERGY)
            if session_kwh is not None and session_kwh > 0:
                session_rec: dict = {"ts": time.time(), "kwh": round(session_kwh, 2)}
                solar_pct = self._read_evcc_session_value(CONF_EVCC_SESSION_SOLAR_PCT)
                if solar_pct is not None:
                    session_rec["solar_pct"] = round(solar_pct, 1)
                kosten = self._read_evcc_session_value(CONF_EVCC_SESSION_PRICE)
                if kosten is not None:
                    session_rec["kosten"] = round(kosten, 2)
                self.hass.async_create_task(self._record_home_session(session_rec))

    def _read_evcc_session_value(self, conf_key: str) -> Optional[float]:
        """Einzelnen evcc-Session-Wert lesen (CONF_EVCC_SESSION_ENERGY/
        _SOLAR_PCT/_PRICE) -- exakt das Muster von _home_price() fuer
        CONF_EVCC_STAT_AVG_PRICE: Entity ueber self._opt() aufloesen, State
        lesen, _INVALID abfangen. None ohne konfigurierte Entity oder ohne
        gueltigen Wert (kein Fehler -- das Feld wird dann in _set_home()
        einfach weggelassen)."""
        entity_id = self._opt(conf_key)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in _INVALID:
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

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
        self._save_soon()

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
        self._save_soon()
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
            self._save_soon()
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
        self._check_leasing_thresholds()
        self.async_set_updated_data(self.data)
        self._save_soon()
        self.hass.async_create_task(self._run_trip_detection())

    @staticmethod
    def _period_keys() -> dict:
        """Tag/Woche/Monat/Jahr-Schluessel fuer den aktuellen Zeitpunkt --
        gemeinsam genutzt von _update_odo_periods() und
        _update_cost_periods(), die beide nach demselben Muster
        (Baseline pro Periode, Rollover bei Schluessel-Wechsel)
        funktionieren."""
        today = dt_util.now().date()
        iso = today.isocalendar()
        return {
            "day":   str(today),
            "week":  f"{iso.year}-W{iso.week:02d}",
            "month": f"{today.year}-{today.month:02d}",
            "year":  str(today.year),
        }

    def _update_odo_periods(self, odo_km: float) -> None:
        """Perioden-Baselines (Tag/Woche/Monat/Jahr) aktualisieren.
        Bei Periodenrollover wird der aktuelle Kilometerstand als neuer
        Startwert gesetzt."""
        periods = self.data.setdefault("odo_periods", {})
        for period, key in self._period_keys().items():
            entry = periods.get(period)
            if entry is None or entry.get("key") != key:
                periods[period] = {"key": key, "odo_km": odo_km}

    def _update_cost_periods(self) -> None:
        """Perioden-Baselines (Tag/Woche/Monat/Jahr) fuer die EV-
        Gesamtkosten (Heim + Fremd seit Einrichtung, siehe
        _ev_cost_total_since_setup()) aktualisieren -- reine Logik in
        engine.update_period_baseline() (inkl. "prev" bei echtem Rollover,
        Grundlage fuer "vs. Vormonat" o.ae., siehe CostMonthSensor), hier
        nur die HA-Verdrahtung (aktueller Kostenstand rein, Ergebnis
        zurueck in self.data)."""
        cost = self._ev_cost_total_since_setup()
        self.data["cost_periods"] = update_period_baseline(
            self.data.get("cost_periods") or {}, self._period_keys(), cost, "cost",
        )

    def _update_kwh_periods(self) -> None:
        """Perioden-Baselines (Tag/Woche/Monat/Jahr) fuer die EV-Gesamt-kWh
        (Heim + Fremd seit Einrichtung, siehe _ev_kwh_total_since_setup())
        -- exakt analog _update_cost_periods(), nur fuer kWh statt Kosten.
        Eigenes Feld ("kwh_periods"), da kWh und Kosten unabhaengig
        voneinander variieren koennen (z.B. unterschiedliche Preise je
        Ladeort/Zeitpunkt)."""
        kwh = self._ev_kwh_total_since_setup()
        self.data["kwh_periods"] = update_period_baseline(
            self.data.get("kwh_periods") or {}, self._period_keys(), kwh, "kwh",
        )

    @callback
    def _daily_lts_refresh(self, now) -> None:
        self.hass.async_create_task(self.async_refresh_lts_data())
        self.hass.async_create_task(self._daily_odo_period_rollover())
        self.hass.async_create_task(self._daily_cost_period_rollover())
        self.hass.async_create_task(self._daily_kwh_period_rollover())
        self.hass.async_create_task(self._async_truncate_lifetime_lists())

    async def _load_archive(self) -> dict:
        """Laedt das Archiv aus ausgelagerten fahrten/history-Eintraegen
        (siehe _async_truncate_lifetime_lists()) -- leeres Archiv, falls
        noch nie etwas archiviert wurde."""
        stored = await self._archive_store.async_load()
        if not stored:
            return {"fahrten": [], "history": []}
        stored.setdefault("fahrten", [])
        stored.setdefault("history", [])
        return stored

    async def _async_truncate_lifetime_lists(self) -> None:
        """Kuerzt "fahrten"/"history" auf die letzten FAHRTEN_MAX_MONATE/
        HISTORY_MAX_MONATE (siehe const.py) und verschiebt aeltere
        Eintraege UNVERAENDERT (nicht geloescht) in ein separates,
        unbegrenzt wachsendes Archiv (siehe _archive_store/_load_archive())
        -- das eigentliche Ziel: die HAEUFIG gespeicherte self.data-Datei
        (siehe _save()/_save_soon(), bei praktisch jeder Coordinator-
        Aktualisierung) waechst nicht mehr unbegrenzt mit jedem weiteren
        Jahr Leasing, waehrend echte Nutzerdaten vollstaendig erhalten
        bleiben -- siehe async_export_fahrtenbuch() (fuehrt Archiv + Liste
        zusammen) und async_import_fahrtenbuch() (Dublettenpruefung
        ebenfalls gegen das Archiv).

        Alle kumulativen Kennzahlen (equivalent_full_cycles(),
        _trip_avg_consumption_kwh(), _consumption_by_temp_bucket(),
        charging_location_stats()'s ac_dc/anbieter-Aufschluesselung,
        usage_profile()) haengen NICHT an dieser Kuerzung, sondern an
        separaten Lebenszeit-Baselines (siehe _apply_trip_baselines()/
        _apply_charge_baselines()), die von _migrate_lifetime_baselines()
        VOR der allerersten Kuerzung aus dem damaligen Vollbestand
        ruecksichert wurden (siehe async_setup()) und seither nur noch
        durch echtes Hinzufuegen/Bearbeiten/Loeschen veraendert werden --
        eine Kuerzung selbst aendert sie nicht.

        Laeuft taeglich (siehe _daily_lts_refresh(), NICHT bei jedem
        einzelnen Sample) und ist idempotent: ohne etwas zu Kuerzendes
        passiert nichts (kein Archiv-Schreibzugriff, kein Save)."""
        now = time.time()
        fahrten_cutoff = now - FAHRTEN_MAX_MONATE * 30.44 * 86400
        history_cutoff = now - HISTORY_MAX_MONATE * 30.44 * 86400
        fahrten = self.data.get("fahrten") or []
        history = self.data.get("history") or []
        aktuelle_fahrten, alte_fahrten = split_by_age(fahrten, "start_ts", fahrten_cutoff)
        aktuelle_history, alte_history = split_by_age(history, "erfasst_ts", history_cutoff)
        if not alte_fahrten and not alte_history:
            return
        archiv = await self._load_archive()
        archiv["fahrten"].extend(alte_fahrten)
        archiv["history"].extend(alte_history)
        await self._archive_store.async_save(archiv)
        self.data["fahrten"] = aktuelle_fahrten
        self.data["history"] = aktuelle_history
        if alte_fahrten:
            self._fahrten_version += 1
        if alte_history:
            self._history_version += 1
        await self._save()
        self.async_set_updated_data(self.data)
        _LOGGER.info(
            "ev_assistant: %d Fahrt(en) und %d Fremdladung(en) ins Archiv verschoben "
            "(aelter als %s/%s Monate)",
            len(alte_fahrten), len(alte_history), FAHRTEN_MAX_MONATE, HISTORY_MAX_MONATE,
        )

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
        self._save_soon()

    async def _daily_cost_period_rollover(self) -> None:
        """Rollt die Tag/Woche/Monat/Jahr-Kosten-Baselines (siehe
        _update_cost_periods()) taeglich -- analog
        _daily_odo_period_rollover(), aus demselben Grund (Heim-/
        Fremdladen-Kosten aendern sich nicht zuverlaessig ueber ein
        einzelnes Ereignis, das den Rollover sonst anstossen wuerde)."""
        self._update_cost_periods()
        self.async_set_updated_data(self.data)
        self._save_soon()

    async def _daily_kwh_period_rollover(self) -> None:
        """Rollt die Tag/Woche/Monat/Jahr-kWh-Baselines (siehe
        _update_kwh_periods()) taeglich -- analog
        _daily_cost_period_rollover(), aus demselben Grund."""
        self._update_kwh_periods()
        self.async_set_updated_data(self.data)
        self._save_soon()

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
        self._save_soon()

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
        self._save_soon()

    async def _run_detection(self) -> None:
        if self._soc is None or self._detector is None:
            return
        sample = ChargeSample(
            ts=time.time(), soc=self._soc, home_charging=self._home, power_kw=self._power,
            plugged_in=self._plugged_in,
        )
        event = self._detector.update(sample)
        self.data["detector_state"] = self._detector.get_state()
        self._check_soc_thresholds()
        # Push bei JEDEM SoC-Sample, nicht nur wenn dabei eine Fremdladung
        # abgeschlossen wird (das pusht selbst schon ueber _handle_pending()
        # unten) -- sonst wuerden Entitaeten, die vom live self._soc abhaengen
        # (z.B. range_estimate_km()), erst beim naechsten ZUFAELLIGEN Push
        # ueber einen anderen Trigger (Odometer-/Preis-Update) aktualisiert,
        # nicht beim eigentlichen SoC-Wechsel selbst.
        self.async_set_updated_data(self.data)
        self._save_soon()
        if event is not None:
            await self._handle_pending(event.as_dict())

    def _check_soc_thresholds(self) -> None:
        """Benachrichtigung, wenn der SoC waehrend eines laufenden
        Ladevorgangs (Heim- ODER Fremdladung) einen der konfigurierten
        Schwellenwerte ueberschreitet. Der Satz bereits gemeldeter
        Schwellen wird persistiert (ueberlebt einen HA-Neustart mitten in
        der Session) und erst zurueckgesetzt, sobald das Laden endet --
        ein erneuter Anstieg danach ist eine neue Session.

        Beim Start einer Session werden bereits erreichte Schwellen (SoC war
        schon vorher hoch, z.B. Einstecken bei 85 % mit Schwelle 80 %)
        sofort als "schon gemeldet" markiert statt eine Benachrichtigung
        auszuloesen -- sonst wuerden beim ersten Sample alle bis dahin
        erreichten Schwellen auf einmal nachtraeglich feuern, obwohl sie
        nicht gerade jetzt ueberschritten wurden."""
        thresholds = [int(v) for v in self._opt(CONF_SOC_THRESHOLDS, DEFAULT_SOC_THRESHOLDS)]
        if not thresholds or self._soc is None:
            return
        is_charging = bool(self._home) or self._detector.active
        was_charging = bool(self.data.get("soc_thresholds_was_charging"))
        if not is_charging:
            if was_charging:
                self.data["soc_thresholds_was_charging"] = False
            if self.data.get("soc_thresholds_notified"):
                self.data["soc_thresholds_notified"] = []
            return
        notified = set(self.data.get("soc_thresholds_notified") or [])
        if not was_charging:
            notified |= {t for t in thresholds if self._soc >= t}
            self.data["soc_thresholds_was_charging"] = True
        for t in sorted(thresholds):
            if t not in notified and self._soc >= t:
                notified.add(t)
                self.hass.async_create_task(self._notify_soc_threshold(t))
        self.data["soc_thresholds_notified"] = sorted(notified)

    async def _periodic_check(self, _now) -> None:
        """Stoesst _run_detection()/_run_trip_detection() auch ohne neue
        SoC-/Kilometerstand-Messung an, damit idle_timeout_s bei einem
        laenger unveraenderten Wert trotzdem greift (siehe Kommentar in
        async_setup)."""
        self._recheck_plug()
        self._recheck_motor()
        await self._run_detection()
        await self._run_trip_detection()
        self._check_entity_health()

    def _check_entity_health(self) -> None:
        """Repair-Issue anlegen/entfernen fuer konfigurierte Quell-Entitaeten,
        die seit mindestens _ENTITY_STALE_THRESHOLD_S unavailable/unknown
        oder entfernt sind -- macht den haeufigsten stillen Fehlerfall
        (Quelle liefert keine Werte mehr, abhaengige Berechnungen laufen
        unbemerkt auf veralteten Daten weiter, siehe z.B. die eRifter-SoC-
        Faelle) sichtbar, statt ihn nur in falschen Sensorwerten auftauchen
        zu lassen."""
        now = time.time()
        for conf_key in _HEALTH_MONITORED_KEYS:
            entity_id = self._opt(conf_key)
            issue_id = f"{self.entry.entry_id}_{conf_key}_unavailable"
            if not entity_id:
                # Feld nicht (mehr) konfiguriert -- ggf. verwaistes Issue aus
                # einer frueheren Konfiguration aufraeumen. Nur tatsaechlich
                # aufrufen, wenn hier je etwas getrackt war, sonst wuerde
                # jedes nie konfigurierte Feld bei jedem 60s-Tick unnoetig
                # async_delete_issue() aufrufen.
                was_tracked = self._entity_bad_since.pop(conf_key, None) is not None
                was_active = conf_key in self._entity_issue_active
                self._entity_issue_active.discard(conf_key)
                if was_tracked or was_active:
                    ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                continue
            state = self.hass.states.get(entity_id)
            bad = state is None or state.state in ("unavailable", "unknown")
            if not bad:
                self._entity_bad_since.pop(conf_key, None)
                if conf_key in self._entity_issue_active:
                    self._entity_issue_active.discard(conf_key)
                    ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                continue
            since = self._entity_bad_since.setdefault(conf_key, now)
            if now - since >= _ENTITY_STALE_THRESHOLD_S and conf_key not in self._entity_issue_active:
                self._entity_issue_active.add(conf_key)
                ir.async_create_issue(
                    self.hass, DOMAIN, issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key=f"entity_unavailable_{conf_key}",
                    translation_placeholders={
                        "entity_id": entity_id,
                        "minuten": str(_ENTITY_STALE_THRESHOLD_S // 60),
                    },
                )

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
        bekanntem Verbrauch.

        Berechnet aus zwei laufend gepflegten Lebenszeit-Summen (siehe
        engine.trip_consumption_contribution()/trip_avg_consumption_kwh_from_totals(),
        _apply_trip_baselines()) statt aus der vollen fahrten-Liste --
        seit der Fahrtenbuch/History-Archivierung (siehe const.py::
        FAHRTEN_MAX_MONATE) waechst diese Liste nicht mehr unbegrenzt mit,
        die Summen bleiben davon unberuehrt. Ergebnis wird pro
        _fahrten_version zwischengespeichert (siehe __init__)."""
        if self._trip_avg_cache is not None and self._trip_avg_cache[0] == self._fahrten_version:
            return self._trip_avg_cache[1]
        exact = self.data.get("trip_consumption_exact_totals") or {"sum_kwh": 0.0, "count": 0}
        deltasoc = self.data.get("trip_consumption_deltasoc_totals") or {"sum_frac": 0.0, "count": 0}
        usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        result = trip_avg_consumption_kwh_from_totals(
            exact.get("sum_kwh", 0.0), exact.get("count", 0),
            deltasoc.get("sum_frac", 0.0), deltasoc.get("count", 0),
            usable_kwh,
        )
        self._trip_avg_cache = (self._fahrten_version, result)
        return result

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
        # sich beide waehrend der Fahrt aendern. Sofort (nicht ueber
        # _save_soon() gebuendelt) persistiert, damit ein HA-Neustart
        # waehrend der Fahrt weder Vorschlag noch Start-SoC verliert (siehe
        # async_setup()) -- anders als der routinemaessige
        # trip_detector_state-Mirror unten heilt sich ein Verlust hier
        # NICHT selbst: faellt die Fahrt spaeter fertig, wuerden die
        # Start-Werte der VORHERIGEN Fahrt (oder None) uebernommen.
        if not was_active and self._trip_detector.active:
            self._trip_start_zone = self._person_zone
            self.data["trip_start_zone"] = self._trip_start_zone
            self._trip_start_soc = self._soc
            self.data["trip_start_soc"] = self._trip_start_soc
            self._trip_start_temp = self._outside_temp
            self.data["trip_start_temp"] = self._trip_start_temp
            await self._save()
        else:
            self._save_soon()
        if event is not None:
            pend = event.as_dict()
            pend["start_ort_vorschlag"] = self._trip_start_zone
            pend["end_ort_vorschlag"] = self._person_zone
            if self._trip_start_soc is not None and self._soc is not None:
                pend["soc_start"] = round(self._trip_start_soc, 1)
                pend["soc_end"] = round(self._soc, 1)
                pend["delta_soc"] = round(self._soc - self._trip_start_soc, 1)
            if self._trip_start_temp is not None:
                pend["temp_start"] = round(self._trip_start_temp, 1)
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
        self._save_soon()
        self.async_set_updated_data(self.data)

    async def _record_home_capacity_sample(self, value: float) -> None:
        """Neue Kapazitaets-Stichprobe aus einer abgeschlossenen Heim-
        Ladesession mit ausreichend grossem SoC-Hub (siehe _set_home()/
        engine.home_capacity_sample()) -- neueste zuerst, analog "history"/
        "fahrten", damit battery_capacity_kwh() sie direkt mit den aus
        Fremdladungen abgeleiteten Stichproben nach Zeitstempel mischen
        kann."""
        samples = list(self.data.get("home_capacity_samples") or [])
        samples.insert(0, {"value": value, "ts": time.time()})
        self.data["home_capacity_samples"] = samples[:BATTERY_CAPACITY_HOME_MAX_STORED]
        self._home_capacity_version += 1
        self._save_soon()
        self.async_set_updated_data(self.data)

    async def _record_home_charge_pct(self, delta_soc: float) -> None:
        """Reiner SoC-Zuwachs (Prozentpunkte) einer abgeschlossenen Heim-
        Ladesession fuer equivalent_full_cycles() -- siehe _set_home() fuer
        die Berechnung. Nutzt denselben Versionszaehler wie
        _record_home_capacity_sample(), da beide am selben Session-Ende
        entstehen und coordinator.equivalent_full_cycles() ohnehin ueber
        alle Aenderungen an Heim-Ladedaten neu rechnen soll."""
        self.data["home_charge_pct_total"] = self.data.get("home_charge_pct_total", 0.0) + delta_soc
        self._home_capacity_version += 1
        self._save_soon()
        self.async_set_updated_data(self.data)

    async def _record_home_session(self, rec: dict) -> None:
        """Neuer Heim-Ladesessions-Record (evcc-Kennzahlen: kwh, optional
        solar_pct/kosten) fuer home_session_stats()/engine.home_session_
        solar_and_cost() -- siehe _set_home(). Neueste zuerst, analog
        "history"/"fahrten"; bewusst UNGEDECKELT (wie "history"), da hier
        -- anders als bei den rollierenden Kapazitaets-/Effizienz-
        Stichproben -- der Lebenszeit-Solaranteil/die Lebenszeit-Kosten
        interessieren, nicht nur ein rollierender Trend."""
        sessions = list(self.data.get("home_sessions") or [])
        sessions.insert(0, rec)
        self.data["home_sessions"] = sessions
        self._home_capacity_version += 1
        self._save_soon()
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

        await self._push(NOTIFY_EVENT_FREMDLADUNG, title, message)
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": self._notify_tag, "title": title, "message": message},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    async def _push(self, event_key: str, title: str, message: str) -> None:
        """Sendet eine Push-Benachrichtigung an die konfigurierten Notify-
        Entitaeten (moderne, entity-basierte Notify-Plattform), aber nur
        wenn event_key zu den in Schritt 4 ausgewaehlten Ereignissen gehoert
        (siehe const.py::NOTIFY_EVENTS) -- die persistent_notification im
        HA-Bereich "Benachrichtigungen" erscheint davon unabhaengig immer
        und wird von den Aufrufern separat erzeugt. KEIN data-Feld (Tag/
        Actions/persistent): notify.send_message akzeptiert bei dieser
        HA-Version nur message/title -- ein data-Feld liess den GESAMTEN
        Aufruf mit 400 Bad Request abbrechen, bevor ueberhaupt etwas
        verschickt wurde (weder Push noch Mail), siehe CHANGELOG."""
        events = self._opt(CONF_NOTIFY_EVENTS, DEFAULT_NOTIFY_EVENTS)
        entities = self._opt(CONF_NOTIFY_ENTITIES)
        if event_key not in events or not entities:
            return
        payload = {"entity_id": entities, "title": title, "message": message}
        try:
            await self.hass.services.async_call("notify", "send_message", payload, blocking=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("notify.send_message fehlgeschlagen: %s", err)

    async def _notify_soc_threshold(self, threshold: int) -> None:
        """Push + persistent_notification, wenn der SoC waehrend eines
        laufenden Ladevorgangs threshold erreicht -- siehe
        _check_soc_thresholds()."""
        en = self._en()
        title = f"{threshold}% SoC reached" if en else f"{threshold} % SoC erreicht"
        message = (
            f"Vehicle battery reached {threshold}%."
            if en else
            f"Fahrzeug-Akku hat {threshold} % erreicht."
        )
        await self._push(NOTIFY_EVENT_SOC_SCHWELLE, title, message)
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": f"{self._notify_tag}_soc_{threshold}", "title": title, "message": message},
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

        await self._push(NOTIFY_EVENT_FAHRT, title, message)
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
        await self._push(NOTIFY_EVENT_TANKERKOENIG, title, message)
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
        if pend.get("temp_start") is not None:
            rec["temp_start"] = pend["temp_start"]
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
                # Reine SoC-Delta-Schaetzung: bei WiCAN-Ausfall waehrend der
                # Fahrt (siehe soc.yaml) kann start_soc/end_soc eingefroren
                # sein statt live -- markiere unplausible Werte statt sie
                # kommentarlos anzuzeigen (siehe engine.is_plausible_trip_consumption).
                rec["verbrauch_unsicher"] = not is_plausible_trip_consumption(
                    rec["verbrauch_kwh"], rec["km"],
                    TRIP_CONSUMPTION_MIN_KWH_100KM, TRIP_CONSUMPTION_MAX_KWH_100KM,
                    TRIP_CONSUMPTION_CHECK_MIN_KM,
                )
        return rec

    def _apply_trip_baselines(self, rec: dict, sign: int) -> None:
        """Pflegt die von der fahrten-Liste selbst unabhaengigen Lebenszeit-
        Baselines (Vollzyklen-Entladeanteil, Verbrauchsschnitt,
        Temperaturband-Schnitt, Wochentags-Profil) parallel zu
        "trip_totals" -- sign=+1 beim Bestaetigen/Importieren einer Fahrt,
        -1 beim Loeschen; async_edit_trip() ruft dies zweimal auf (-1 fuer
        den alten, +1 fuer den neuen Stand), analog dem bestehenden
        Delta-Muster bei "trip_totals". Reine HA-Verdrahtung -- die
        eigentliche Rechenlogik (was ein einzelner Eintrag beitraegt) steht
        in engine.py, siehe dort fuer die Begruendung, warum diese
        Baselines unabhaengig von einer spaeteren Archivierung/Kuerzung der
        fahrten-Liste dieselben Ergebnisse liefern wie die alte
        volle-Liste-Berechnung."""
        self.data["fahrten_discharge_pct_total"] = round(
            self.data.get("fahrten_discharge_pct_total", 0.0) + sign * trip_discharge_pct(rec), 4
        )
        contribution = trip_consumption_contribution(rec)
        if contribution is not None:
            kind, value = contribution
            field = "trip_consumption_exact_totals" if kind == "exact" else "trip_consumption_deltasoc_totals"
            sum_field = "sum_kwh" if kind == "exact" else "sum_frac"
            totals = self.data.setdefault(field, {sum_field: 0.0, "count": 0})
            totals[sum_field] = round(totals.get(sum_field, 0.0) + sign * value, 6)
            totals["count"] = max(0, totals.get("count", 0) + sign)
        temp_contribution = temp_bucket_contribution(rec, TEMP_BUCKET_BOUNDARIES)
        if temp_contribution is not None:
            bucket_key, pct = temp_contribution
            buckets = self.data.setdefault("temp_bucket_totals", {})
            entry = buckets.setdefault(bucket_key, {"sum_pct": 0.0, "count": 0})
            entry["sum_pct"] = round(entry.get("sum_pct", 0.0) + sign * pct, 4)
            entry["count"] = max(0, entry.get("count", 0) + sign)
            if entry["count"] <= 0:
                buckets.pop(bucket_key, None)
        ts = rec.get("start_ts")
        weekday_parts = trip_weekday_kwh_parts(rec)
        if weekday_parts is not None and ts is not None:
            kind, value = weekday_parts
            weekday = dt_util.as_local(dt_util.utc_from_timestamp(ts)).date().weekday()
            weekday_field = "weekday_kwh_exact_totals" if kind == "exact" else "weekday_km_est_totals"
            weekday_totals = self.data.setdefault(weekday_field, {})
            key = str(weekday)
            weekday_totals[key] = round(weekday_totals.get(key, 0.0) + sign * value, 4)
        if sign > 0 and ts is not None:
            first_ts = self.data.get("fahrtenbuch_first_ts")
            if first_ts is None or ts < first_ts:
                self.data["fahrtenbuch_first_ts"] = ts

    def _apply_charge_baselines(self, rec: dict, sign: int) -> None:
        """Analog _apply_trip_baselines(), fuer Fremdladungen ("history"):
        Vollzyklen-Ladeanteil sowie die AC/DC- und Anbieter-Baselines
        (siehe engine.apply_ac_dc_delta()/apply_anbieter_delta())."""
        self.data["history_charge_pct_total"] = round(
            self.data.get("history_charge_pct_total", 0.0) + sign * charge_pct_of_history_entry(rec), 4
        )
        self.data["ac_dc_totals"] = apply_ac_dc_delta(self.data.get("ac_dc_totals") or {}, rec, sign, AC_MAX_KW)
        self.data["anbieter_totals"] = apply_anbieter_delta(self.data.get("anbieter_totals") or {}, rec, sign)

    def _migrate_lifetime_baselines(self) -> bool:
        """Einmalige Ruecksicherung der Lebenszeit-Baselines (siehe
        _apply_trip_baselines()/_apply_charge_baselines()) aus der beim
        Upgrade bereits vorhandenen VOLLEN fahrten/history-Liste -- MUSS vor
        der ersten Archivierung/Kuerzung gelaufen sein (siehe
        _async_truncate_lifetime_lists()), sonst wuerden aeltere
        Bestandsdaten beim ersten Kuerzen ersatzlos aus diesen Kennzahlen
        verschwinden. Ein persistiertes Flag verhindert ein erneutes (und
        dann falsches, doppelt zaehlendes) Nachrechnen bei jedem weiteren
        Neustart. Gibt True zurueck, wenn die Migration gerade eben
        gelaufen ist (der Aufrufer muss dann sofort speichern, siehe
        async_setup()) -- False, wenn sie (typischerweise) bereits vorher
        gelaufen war."""
        if self.data.get("lifetime_baselines_migrated"):
            return False
        for rec in self.data.get("fahrten") or []:
            self._apply_trip_baselines(rec, 1)
        for rec in self.data.get("history") or []:
            self._apply_charge_baselines(rec, 1)
        self.data["lifetime_baselines_migrated"] = True
        return True

    def _finalize_trip_record(self, rec: dict) -> None:
        self.data.setdefault("fahrten", []).insert(0, rec)
        totals = self.data.setdefault("trip_totals", {"km": 0.0, "count": 0})
        totals["km"] = round(totals.get("km", 0.0) + rec["km"], 2)
        totals["count"] = totals.get("count", 0) + 1
        self._apply_trip_baselines(rec, 1)
        self._fahrten_version += 1

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
                old_rec = dict(rec)
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
                            rec["verbrauch_unsicher"] = not is_plausible_trip_consumption(
                                rec["verbrauch_kwh"], rec.get("km"),
                                TRIP_CONSUMPTION_MIN_KWH_100KM, TRIP_CONSUMPTION_MAX_KWH_100KM,
                            )
                if verbrauch_kwh is not None:
                    # Explizit angegebener Verbrauch (z.B. reale Werte aus der
                    # Fahrzeug-App) gilt als bestaetigt -- kein Delta-Schaetzwert
                    # mehr, daher kein Unsicher-Flag.
                    rec["verbrauch_kwh"] = round(float(verbrauch_kwh), 2)
                    rec["verbrauch_unsicher"] = False
                self._apply_trip_baselines(old_rec, -1)
                self._apply_trip_baselines(rec, 1)
                self._fahrten_version += 1
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
                self._apply_trip_baselines(rec, -1)
                self._fahrten_version += 1
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
        Import keine Dubletten erzeugt -- die Pruefung beruecksichtigt dafuer
        NEBEN der aktuellen fahrten-Liste auch das Archiv (siehe
        _async_truncate_lifetime_lists()), sonst koennte ein laengst
        archivierter Import bei einem erneuten Lauf faelschlich als "neu"
        durchgehen. Gibt die Anzahl tatsaechlich neu importierter Fahrten
        zurueck."""
        archiv = await self._load_archive()
        existing_starts = {rec.get("start_ts") for rec in self.data.get("fahrten") or []}
        existing_starts.update(rec.get("start_ts") for rec in archiv.get("fahrten", []))
        imported: list[dict] = []
        # Ein Basiswert + laufender Index statt in jeder Iteration neu
        # int(time.time()) zu lesen -- sonst bekaemen mehrere Fahrten in
        # einem Aufruf denselben (ganzzahligen) erfasst_ts, der als
        # alleiniger Schluessel fuer edit_trip()/delete_trip() dient und
        # dann versehentlich die falsche Fahrt trifft.
        erfasst_ts_base = int(time.time())
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
                    "erfasst_ts": erfasst_ts_base + len(imported), "quelle": "import",
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
        for rec in imported:
            self._apply_trip_baselines(rec, 1)
        self._fahrten_version += 1

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
        """Exportiert das GESAMTE Fahrtenbuch (chronologisch aufsteigend,
        inkl. archivierter Fahrten, siehe _async_truncate_lifetime_lists())
        als CSV nach www/, damit es unter /local/... herunterladbar ist --
        der Export bleibt dadurch vollstaendig, auch wenn die aktuelle
        fahrten-Liste laengst gekuerzt wurde."""
        archiv = await self._load_archive()
        fahrten = archiv.get("fahrten", []) + list(self.data.get("fahrten") or [])
        fahrten.sort(key=lambda r: r.get("start_ts") or 0)
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

    async def async_log_charge(
        self, kwh: float, price: float, start_ts: Optional[float] = None,
        start_fee: float = 0.0, block_fee: float = 0.0, time_fee: float = 0.0,
        end_ts: Optional[float] = None,
        soc_start: Optional[float] = None, soc_end: Optional[float] = None,
        karte_id: Optional[int] = None, anbieter: Optional[str] = None,
    ) -> None:
        """Bestaetigt eine offene Fremdladung. Bei mehreren gleichzeitig
        offenen waehlt `start_ts` die gemeinte aus; ohne Angabe wird die
        aelteste bestaetigt (FIFO). `start_fee`/`block_fee`/`time_fee` sind
        optionale pauschale Gebuehren mancher Ladenetze/Ladepunkte,
        zusaetzlich zum kWh-Preis -- getrennte Felder, da mehrere auf
        demselben Beleg gleichzeitig auftauchen koennen (siehe
        engine.charge_cost()). `end_ts`/`soc_start`/`soc_end` sind nur
        wirksam, wenn KEINE passende offene Ladung gefunden wird (komplett
        manueller Einzeleintrag ohne vorherige automatische Erkennung, siehe
        Panel-Formular): `end_ts` ergibt zusammen mit start_ts die Ladedauer
        (dauer_min), `soc_start`/`soc_end` ergeben delta_soc -- beides
        analog async_edit_charge(). Bei einer erkannten offenen Ladung
        stammen Dauer und SoC-Werte weiterhin aus deren eigener Messung
        (pend["duration_min"]/["soc_start"]/["soc_end"]). `karte_id`
        optional: welche Ladekarte (siehe async_add_ladekarte()) fuer diese
        Ladung verwendet wurde -- rein informativ, fliesst NICHT in die
        Kostenberechnung ein (Ladekarten-Grundgebuehren laufen unabhaengig
        von einzelnen Ladungen, siehe _ladekarten_cost_total()); wird
        unveraendert gespeichert, auch wenn die Karte spaeter geloescht
        wird (verwaiste Referenz wird beim Anzeigen einfach ignoriert).
        `anbieter` optional: WO geladen wurde (Ladenetz-/Betreibername,
        z.B. "EnBW"/"Ionity") -- eine ganz andere Sache als `karte_id`
        (WOMIT bezahlt wurde), siehe engine.anbieter_breakdown(). Freitext,
        kein fester Katalog; nur getrimmt gespeichert, leer/None wird
        NICHT gespeichert (kein Fantasiewert -- alte Eintraege ohne
        Anbieter funktionieren unveraendert weiter, siehe dort)."""
        kwh = round(float(kwh), 2)
        price = round(float(price), 4)
        start_fee = round(float(start_fee), 2)
        block_fee = round(float(block_fee), 2)
        time_fee = round(float(time_fee), 2)
        rec = {
            "config_entry_id": self.entry.entry_id,
            "kwh": kwh, "preis_kwh": price, "startgebuehr": start_fee,
            "blockiergebuehr": block_fee, "zeitgebuehr": time_fee,
            "kosten": charge_cost(kwh, price, start_fee, block_fee, time_fee),
            "erfasst_ts": int(time.time()),
        }
        if karte_id is not None:
            rec["karte_id"] = karte_id
        if anbieter and anbieter.strip():
            rec["anbieter"] = anbieter.strip()
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
            if end_ts is not None:
                rec["dauer_min"] = round((end_ts - start_ts) / 60.0, 1)
            if soc_start is not None:
                rec["soc_start"] = round(float(soc_start), 1)
            if soc_end is not None:
                rec["soc_end"] = round(float(soc_end), 1)
            if soc_start is not None and soc_end is not None:
                rec["delta_soc"] = round(rec["soc_end"] - rec["soc_start"], 1)
        self.data["pending"] = pending_list

        self.data.setdefault("history", []).insert(0, rec)
        totals = self.data["totals"]
        totals["kwh"] = round(totals.get("kwh", 0.0) + kwh, 2)
        totals["kosten"] = round(totals.get("kosten", 0.0) + rec["kosten"], 2)
        totals["count"] = totals.get("count", 0) + 1
        self._apply_charge_baselines(rec, 1)
        self._history_version += 1
        self.data["last_price"] = price
        await self._save()
        self.hass.bus.async_fire(EVENT_LOGGED, rec)
        if pending_list:
            await self._notify()
        else:
            await self._dismiss()
        self.async_set_updated_data(self.data)

    async def async_edit_charge(
        self,
        erfasst_ts: int,
        kwh: Optional[float] = None,
        price: Optional[float] = None,
        start_fee: Optional[float] = None,
        block_fee: Optional[float] = None,
        time_fee: Optional[float] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        soc_start: Optional[float] = None,
        soc_end: Optional[float] = None,
        karte_id: Optional[int] = None,
        anbieter: Optional[str] = None,
    ) -> bool:
        """Korrigiert einen bereits bestaetigten Historien-Eintrag -- alle
        Felder optional, nur mitgegebene Werte werden geaendert (analog
        async_edit_trip()). kwh/price/start_fee/block_fee/time_fee:
        fehlende Werte bleiben unveraendert, kosten wird aus den effektiven
        (neuen oder bisherigen) Werten neu berechnet (engine.charge_cost()).
        end_ts wird nicht direkt gespeichert, sondern zusammen mit dem
        effektiven start_ts zu dauer_min umgerechnet (dieselbe Ableitung
        wie beim Bestaetigen). soc_start/soc_end: delta_soc wird neu
        berechnet. karte_id: None laesst die Zuordnung unveraendert, 0
        entfernt eine bestehende Zuordnung (0 ist keine gueltige Karten-ID,
        siehe async_add_ladekarte()), jeder andere Wert setzt/aendert sie.
        anbieter (WO geladen wurde, siehe engine.anbieter_breakdown() --
        nicht zu verwechseln mit karte_id): None laesst den Wert
        unveraendert, ein leerer String "" entfernt einen bestehenden
        Anbieter, jeder andere Wert setzt/aendert ihn (getrimmt).
        Passt die laufenden Summen (kwh/kosten) um die Differenz an statt
        sie aus der Historie neu zu berechnen. Gibt False zurueck, wenn
        kein Eintrag mit erfasst_ts gefunden wurde."""
        history = self.data.get("history") or []
        for rec in history:
            if rec.get("erfasst_ts") == erfasst_ts:
                old_rec = dict(rec)
                old_kwh = rec["kwh"]
                old_kosten = rec["kosten"]
                kwh = round(float(kwh), 2) if kwh is not None else rec["kwh"]
                price = round(float(price), 4) if price is not None else rec["preis_kwh"]
                fee = round(float(start_fee), 2) if start_fee is not None else rec.get("startgebuehr", 0.0)
                bfee = round(float(block_fee), 2) if block_fee is not None else rec.get("blockiergebuehr", 0.0)
                tfee = round(float(time_fee), 2) if time_fee is not None else rec.get("zeitgebuehr", 0.0)
                kosten = charge_cost(kwh, price, fee, bfee, tfee)
                totals = self.data["totals"]
                totals["kwh"] = round(totals.get("kwh", 0.0) - old_kwh + kwh, 2)
                totals["kosten"] = round(totals.get("kosten", 0.0) - old_kosten + kosten, 2)
                rec["kwh"] = kwh
                rec["preis_kwh"] = price
                rec["startgebuehr"] = fee
                rec["blockiergebuehr"] = bfee
                rec["zeitgebuehr"] = tfee
                rec["kosten"] = kosten
                if karte_id is not None:
                    if karte_id == 0:
                        rec.pop("karte_id", None)
                    else:
                        rec["karte_id"] = karte_id
                if anbieter is not None:
                    if anbieter.strip():
                        rec["anbieter"] = anbieter.strip()
                    else:
                        rec.pop("anbieter", None)
                if start_ts is not None:
                    rec["start_ts"] = start_ts
                if end_ts is not None and rec.get("start_ts") is not None:
                    rec["dauer_min"] = round((end_ts - rec["start_ts"]) / 60.0, 1)
                if soc_start is not None:
                    rec["soc_start"] = round(float(soc_start), 1)
                if soc_end is not None:
                    rec["soc_end"] = round(float(soc_end), 1)
                if soc_start is not None or soc_end is not None:
                    if rec.get("soc_start") is not None and rec.get("soc_end") is not None:
                        rec["delta_soc"] = round(rec["soc_end"] - rec["soc_start"], 1)
                if history[0] is rec:
                    self.data["last_price"] = price
                self._apply_charge_baselines(old_rec, -1)
                self._apply_charge_baselines(rec, 1)
                self._history_version += 1
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
                self._apply_charge_baselines(rec, -1)
                self._history_version += 1
                await self._save()
                self.hass.bus.async_fire(EVENT_DELETED, rec)
                self.async_set_updated_data(self.data)
                return True
        return False

    # ----- Ladekarten (monatliche Grundgebuehren, z.B. Ladekarten-Abos) ---

    async def async_add_ladekarte(
        self, name: str, monatliche_gebuehr: float, start_datum: str,
        end_datum: Optional[str] = None,
    ) -> None:
        """Legt eine neue Ladekarte an -- reiner Kostenposten (siehe
        engine.ladekarte_accrued_cost()), keine Verknuepfung mit
        Fremdladungen noetig (die optionale karte_id auf einzelnen
        Ladungen, siehe async_log_charge(), ist rein informativ). id ist
        ein simpler Millisekunden-Zeitstempel -- analog erfasst_ts bei
        Fremdladungen/Fahrten, hier ausreichend, da Karten einzeln von
        Hand angelegt werden (kein Tight-Loop-Kollisionsrisiko wie beim
        Bulk-Import von Fahrten). `monatliche_gebuehr` wird als erste
        Gebuehrenstufe ab `start_datum` gespeichert (siehe "gebuehren" in
        engine.ladekarte_accrued_cost()) -- weitere Stufen (z.B. Ende eines
        reduzierten Einfuehrungspreises) kommen ueber
        async_add_ladekarte_preisstufe() dazu."""
        karte = {
            "id": int(time.time() * 1000),
            "name": name.strip(),
            "gebuehren": [{"ab_datum": start_datum, "gebuehr": round(float(monatliche_gebuehr), 2)}],
            "start_datum": start_datum,
            "end_datum": end_datum,
        }
        karten = list(self.data.get("ladekarten") or [])
        karten.append(karte)
        self.data["ladekarten"] = karten
        await self._save()
        self.async_set_updated_data(self.data)

    @staticmethod
    def _ladekarte_gebuehren(karte: dict) -> list:
        """Gebuehrenstufen einer Karte, mit Ruecklauf-Kompatibilitaet fuer
        Karten aus der Zeit vor Gebuehrenstufen (siehe engine.
        ladekarte_legacy_gebuehren()) -- gibt IMMER die tatsaechliche Liste
        zurueck (nicht nur zur Berechnung wie im engine-Pendant), damit
        Schreibzugriffe (Stufe hinzufuegen/loeschen) sie direkt mutieren
        koennen."""
        gebuehren = karte.get("gebuehren")
        if not gebuehren:
            gebuehren = ladekarte_legacy_gebuehren(karte)
            karte["gebuehren"] = gebuehren
        return gebuehren

    async def async_edit_ladekarte(
        self,
        karte_id: int,
        name: Optional[str] = None,
        monatliche_gebuehr: Optional[float] = None,
        start_datum: Optional[str] = None,
        end_datum: Optional[str] = None,
    ) -> bool:
        """Korrigiert eine bestehende Ladekarte -- alle Felder optional,
        nur mitgegebene Werte werden geaendert (analog async_edit_charge()).
        end_datum: None laesst das Feld unveraendert, ein LEERER String
        loescht ein zuvor gesetztes Enddatum (z.B. eine gekuendigte Karte
        reaktivieren) -- unterscheidbar, weil ein Service-Aufruf ohne
        end_datum-Feld ueberhaupt None liefert, waehrend ein explizit
        geleertes Formularfeld "" liefert. monatliche_gebuehr korrigiert die
        Gebuehr der ZEITLICH FRUEHESTEN Stufe (typischerweise ein Tippfehler
        beim Anlegen) -- ein PREISWECHSEL (z.B. Ende eines reduzierten
        Einfuehrungspreises) laeuft stattdessen ueber
        async_add_ladekarte_preisstufe(), da hier nicht klar waere, welche
        von mehreren Stufen gemeint ist. Gibt False zurueck, wenn keine
        Karte mit dieser id gefunden wurde."""
        karten = self.data.get("ladekarten") or []
        for karte in karten:
            if karte.get("id") == karte_id:
                if name is not None:
                    karte["name"] = name.strip()
                if monatliche_gebuehr is not None:
                    gebuehren = self._ladekarte_gebuehren(karte)
                    if gebuehren:
                        fruehste = min(gebuehren, key=lambda s: s.get("ab_datum") or "")
                        fruehste["gebuehr"] = round(float(monatliche_gebuehr), 2)
                if start_datum is not None:
                    karte["start_datum"] = start_datum
                if end_datum is not None:
                    karte["end_datum"] = end_datum or None
                await self._save()
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_add_ladekarte_preisstufe(self, karte_id: int, gebuehr: float, ab_datum: str) -> bool:
        """Fuegt einer bestehenden Ladekarte eine neue Gebuehrenstufe hinzu
        (siehe engine.ladekarte_accrued_cost()) -- z.B. wenn ein reduzierter
        Einfuehrungspreis nach einigen Monaten auf den regulaeren Preis
        steigt. Existiert bereits eine Stufe mit exakt diesem ab_datum,
        wird deren Gebuehr ersetzt statt eine doppelte Stufe anzulegen
        (Korrektur eines Tippfehlers bei einem bereits erfassten
        Preiswechsel). Gibt False zurueck, wenn keine Karte mit dieser id
        gefunden wurde."""
        karten = self.data.get("ladekarten") or []
        for karte in karten:
            if karte.get("id") == karte_id:
                gebuehren = self._ladekarte_gebuehren(karte)
                for stufe in gebuehren:
                    if stufe.get("ab_datum") == ab_datum:
                        stufe["gebuehr"] = round(float(gebuehr), 2)
                        break
                else:
                    gebuehren.append({"ab_datum": ab_datum, "gebuehr": round(float(gebuehr), 2)})
                await self._save()
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_delete_ladekarte_preisstufe(self, karte_id: int, ab_datum: str) -> bool:
        """Entfernt eine Gebuehrenstufe wieder (siehe
        async_add_ladekarte_preisstufe()) -- z.B. eine versehentlich
        angelegte. Die zeitlich fruehste Stufe kann nicht geloescht werden
        (eine Karte braucht immer mindestens eine bekannte Gebuehr, siehe
        engine.ladekarte_accrued_cost()) -- der Aufruf gibt dafuer False
        zurueck, genau wie wenn Karte oder Stufe nicht gefunden wurden."""
        karten = self.data.get("ladekarten") or []
        for karte in karten:
            if karte.get("id") == karte_id:
                gebuehren = self._ladekarte_gebuehren(karte)
                if len(gebuehren) <= 1:
                    return False
                fruehste = min(gebuehren, key=lambda s: s.get("ab_datum") or "")
                if fruehste.get("ab_datum") == ab_datum:
                    return False
                for i, stufe in enumerate(gebuehren):
                    if stufe.get("ab_datum") == ab_datum:
                        gebuehren.pop(i)
                        await self._save()
                        self.async_set_updated_data(self.data)
                        return True
                return False
        return False

    async def async_delete_ladekarte(self, karte_id: int) -> bool:
        """Loescht eine Ladekarte vollstaendig. Bereits zugeordnete
        Fremdladungen (rec["karte_id"], siehe async_log_charge()) behalten
        ihre Referenz -- eine verwaiste karte_id wird beim Anzeigen einfach
        ignoriert, nicht rueckwirkend aus der Historie entfernt. Gibt False
        zurueck, wenn keine Karte mit dieser id gefunden wurde."""
        karten = self.data.get("ladekarten") or []
        for i, karte in enumerate(karten):
            if karte.get("id") == karte_id:
                karten.pop(i)
                await self._save()
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

    def _ev_kwh_total_since_setup(self) -> float:
        """(Heimladen + Fremdladen) kWh gesamt seit Einrichtung -- dieselbe
        Energiebilanz wie savings()/_vehicle_avg_consumption_kwh_per_100km()/
        co2_savings(), an einer Stelle gebuendelt."""
        home_kwh = self._home_kwh_since_setup() or 0.0
        external_kwh = self.data.get("totals", {}).get("kwh", 0.0)
        return home_kwh + external_kwh

    def _ev_cost_total_since_setup(self) -> float:
        """(Heimladen + Fremdladen + Ladekarten-Grundgebuehren) Kosten
        gesamt seit Einrichtung -- dieselbe Kosten-Prioritaet wie
        calculate_savings() (home_cost, falls vorhanden, sonst home_kwh *
        home_price), fuer die Perioden-Baselines (siehe
        _update_cost_periods()). Ladekarten-Grundgebuehren (siehe
        _ladekarten_cost_total()) zaehlen hier mit, da diese Summe "was
        kostet mich das Fahrzeug insgesamt" abbilden soll -- anders als
        totals["kosten"] (reine Ladekosten-Summe, unveraendert, siehe
        charging_location_stats() fuer die bewusste Trennung)."""
        home_cost = self._home_cost_since_setup()
        if home_cost is None:
            home_kwh = self._home_kwh_since_setup()
            home_price = self._home_price()
            home_cost = round(home_kwh * home_price, 2) if (home_kwh is not None and home_price is not None) else 0.0
        external_cost = self.data.get("totals", {}).get("kosten", 0.0)
        return home_cost + external_cost + self._ladekarten_cost_total()

    def _ladekarten_cost_total(self) -> float:
        """Aufgelaufene Summe aller Ladekarten-Grundgebuehren bis heute
        (siehe engine.ladekarten_summary()) -- 0.0 ohne jede Karte. Eigene
        Methode statt Inline-Code, da mehrere Stellen (_ev_cost_total_
        since_setup(), savings(), charging_location_stats()) sie
        brauchen."""
        return self.ladekarten_stats().get("gesamt", 0.0)

    def ladekarten_stats(self) -> dict:
        """Ladekarten-Uebersicht (siehe engine.ladekarten_summary()) --
        leeres dict ohne jede angelegte Karte (macht das Feature komplett
        inaktiv/unsichtbar, analog leasing_stats()). Absichtlich UNGECACHT:
        die Berechnung ist trivial billig (kurze Liste, reine Datums-
        arithmetik), anders als z.B. rolling_km_per_day() bei leasing_stats()."""
        karten = self.data.get("ladekarten") or []
        if not karten:
            return {}
        heute = dt_util.now().date().isoformat()
        return ladekarten_summary(karten, heute, LADEKARTE_AVG_DAYS_PER_MONTH)

    def _vehicle_avg_consumption_kwh_per_100km(self) -> Optional[float]:
        """Durchschnittsverbrauch des Fahrzeugs in kWh/100km ueber die
        gesamte Zeit seit Einrichtung, aus der Energiebilanz (siehe
        _ev_kwh_total_since_setup()), geteilt durch die seit Einrichtung
        gefahrenen km (siehe _km_driven()) -- dieselben immer vorhandenen
        Gesamtwerte wie savings(), unabhaengig davon, ob jede einzelne
        Fahrt im Fahrtenbuch bestaetigt wurde (anders als
        _trip_avg_consumption_kwh(), das nur bestaetigte/importierte
        Fahrten zaehlt). Kleine systematische Abweichung durch den Akku-
        Fuellstand zum Einrichtungszeitpunkt, ueber laengere Zeitraeume
        vernachlaessigbar."""
        km = self._km_driven()
        if km is None or km <= 0:
            return None
        return round(self._ev_kwh_total_since_setup() / km * 100.0, 2)

    def _vehicle_avg_consumption_kwh_per_100km_rolling(self) -> Optional[float]:
        """Wie _vehicle_avg_consumption_kwh_per_100km(), aber nur ueber die
        letzten _ROLLING_CONSUMPTION_WINDOW_DAYS Tage Fahrtenbuch (siehe
        engine.py::rolling_consumption_kwh_per_100km()) -- fuer
        range_estimate_km(), wo der AKTUELLE Verbrauch (Jahreszeit,
        Fahrstil) interessiert statt des ueber die gesamte Nutzungsdauer
        gemittelten Werts. Faellt auf den Lebenszeit-Durchschnitt zurueck,
        wenn das Rolling-Fenster zu wenig Fahrstrecke enthaelt.

        Ergebnis wird pro (_fahrten_version, heutiges Datum)
        zwischengespeichert, analog usage_profile()."""
        today = dt_util.now().date().isoformat()
        if (
            self._rolling_consumption_cache is not None
            and self._rolling_consumption_cache[0] == self._fahrten_version
            and self._rolling_consumption_cache[1] == today
        ):
            return self._rolling_consumption_cache[2]
        fahrten = self.data.get("fahrten") or []
        result = rolling_consumption_kwh_per_100km(
            fahrten, time.time(), _ROLLING_CONSUMPTION_WINDOW_DAYS, _ROLLING_CONSUMPTION_MIN_KM,
        )
        if result is None:
            result = self._vehicle_avg_consumption_kwh_per_100km()
        self._rolling_consumption_cache = (self._fahrten_version, today, result)
        return result

    def _consumption_by_temp_bucket(self) -> dict:
        """Durchschnittsverbrauch je Temperaturband (siehe engine.
        consumption_by_temp_bucket_from_totals()) -- nur Baender mit genug
        Fahrten (TEMP_BUCKET_MIN_SAMPLES) sind enthalten. Berechnet aus
        einer laufend gepflegten Lebenszeit-Summe je Band (siehe
        _apply_trip_baselines()) statt aus der vollen fahrten-Liste, bleibt
        also von einer Archivierung/Kuerzung dieser Liste unberuehrt.
        Ergebnis wird pro _fahrten_version zwischengespeichert, analog
        _trip_avg_cache."""
        if self._temp_bucket_cache is not None and self._temp_bucket_cache[0] == self._fahrten_version:
            return self._temp_bucket_cache[1]
        result = consumption_by_temp_bucket_from_totals(
            self.data.get("temp_bucket_totals") or {}, TEMP_BUCKET_MIN_SAMPLES
        )
        self._temp_bucket_cache = (self._fahrten_version, result)
        return result

    def current_temp_bucket(self) -> Optional[str]:
        """Temperaturband der aktuellen Aussentemperatur (siehe
        CONF_OUTSIDE_TEMP_ENTITY), z.B. fuer die Sensor-Attribute von
        RangeEstimateSensor. None ohne konfigurierte/aktuelle Temperatur."""
        return temperature_bucket(self._outside_temp, TEMP_BUCKET_BOUNDARIES)

    def equivalent_full_cycles(self) -> float:
        """Aequivalente Vollzyklen aus Fahrtenbuch (Entladung), Fremd- und
        Heim-Ladungen (Ladung), siehe engine.equivalent_full_cycles_from_totals().
        Berechnet aus zwei laufend gepflegten Lebenszeit-Summen (siehe
        _apply_trip_baselines()/_apply_charge_baselines()) statt aus den
        vollen fahrten/history-Listen, bleibt also von einer Archivierung/
        Kuerzung dieser Listen unberuehrt. Wird pro (_fahrten_version,
        _history_version, _home_capacity_version) zwischengespeichert --
        Letzteres, da home_charge_pct_total ueber _record_home_charge_pct()
        denselben Zaehler wie die Kapazitaets-Stichproben mitbenutzt (siehe
        dort)."""
        cache_key = (self._fahrten_version, self._history_version, self._home_capacity_version)
        if self._cycles_cache is not None and self._cycles_cache[0] == cache_key:
            return self._cycles_cache[1]
        fahrten_discharge = self.data.get("fahrten_discharge_pct_total", 0.0)
        history_charge = self.data.get("history_charge_pct_total", 0.0)
        home_charge_pct_total = self.data.get("home_charge_pct_total", 0.0)
        result = equivalent_full_cycles_from_totals(fahrten_discharge, history_charge, home_charge_pct_total)
        self._cycles_cache = (cache_key, result)
        return result

    def range_estimate_km(self) -> Optional[float]:
        """Geschaetzte Restreichweite: aktueller SoC * nutzbare kWh ueber den
        Realverbrauch -- ehrlicher als eine Bordanzeige, weil tatsaechlicher
        Fahrstil/Jahreszeit einfliessen statt eines werksseitig pauschalen
        Verbrauchswerts. Ist eine Aussentemperatur konfiguriert (siehe
        CONF_OUTSIDE_TEMP_ENTITY) UND liegen fuer deren aktuelles
        Temperaturband genug Fahrten vor, wird der bandspezifische statt
        der rollierende 30-Tage-Schnitt verwendet -- genauer bei starken
        Jahreszeiten-Schwankungen (Kaelte-Malus), faellt sonst auf den
        rollierenden Schnitt zurueck."""
        usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        consumption = self._vehicle_avg_consumption_kwh_per_100km_rolling()
        bucket = temperature_bucket(self._outside_temp, TEMP_BUCKET_BOUNDARIES)
        bucket_consumption = self._consumption_by_temp_bucket().get(bucket)
        if bucket_consumption is not None:
            consumption = bucket_consumption
        return calculate_range_km(self._soc, usable_kwh, consumption)

    def battery_capacity_kwh(self) -> Optional[float]:
        """Rollierend geschaetzte tatsaechliche Akku-Gesamtkapazitaet aus
        Fremd- UND Heim-Ladesessions mit ausreichend grossem SoC-Hub (siehe
        engine.battery_capacity_samples/home_capacity_sample/
        estimate_battery_capacity_kwh, sowie _set_home() fuer die Heim-
        Stichproben) -- der absolute Wert liegt wegen nicht herausgerechneter
        Ladeverluste typischerweise ueber der echten Kapazitaet (siehe
        Docstrings dort), ein Absinken ueber Monate/Jahre ist trotzdem das
        eigentliche Alterungssignal. Ergebnis wird pro (_history_version,
        _home_capacity_version) zwischengespeichert (siehe _trip_avg_cache-
        Kommentar in __init__ fuer die Begruendung)."""
        cache_key = (self._history_version, self._home_capacity_version)
        if self._battery_capacity_cache is not None and self._battery_capacity_cache[0] == cache_key:
            return self._battery_capacity_cache[1]
        history = self.data.get("history") or []
        samples = battery_capacity_samples(history, BATTERY_CAPACITY_MIN_SOC_DELTA)
        samples += self.data.get("home_capacity_samples") or []
        result = estimate_battery_capacity_kwh(samples, BATTERY_CAPACITY_MAX_SAMPLES, BATTERY_CAPACITY_MIN_SAMPLES)
        self._battery_capacity_cache = (cache_key, result)
        return result

    def home_session_stats(self) -> dict:
        """kWh-gewichteter Solaranteil + Kostensumme/Preis aus evcc-Heim-
        Ladesessions (siehe engine.home_session_solar_and_cost(), Feld
        "home_sessions" in _set_home()) -- leeres dict ohne jede Session
        mit den noetigen Daten. Ergebnis wird pro _home_capacity_version
        zwischengespeichert (derselbe Zaehler wie battery_capacity_kwh(),
        da beide am selben Session-Ende-Hook in _set_home() haengen)."""
        if (
            self._home_session_stats_cache is not None
            and self._home_session_stats_cache[0] == self._home_capacity_version
        ):
            return self._home_session_stats_cache[1]
        sessions = self.data.get("home_sessions") or []
        result = home_session_solar_and_cost(sessions)
        self._home_session_stats_cache = (self._home_capacity_version, result)
        return result

    def charging_location_stats(self) -> dict:
        """"So verteilt sich deine Ladung" nach Ladeort (Heim vs. Fremd) --
        siehe engine.charging_location_breakdown(). Fasst nur bereits an
        anderer Stelle berechnete Aggregate zusammen (keine eigene Preis-/
        PV-Logik): Heim-kWh/-Kosten mit derselben Prioritaet wie
        _ev_cost_total_since_setup() (evcc-Realkosten, sonst home_kwh *
        home_price), Fremd-kWh/-Kosten aus den bestaetigten Historien-
        Summen, gefahrene km aus _km_driven(), Heim-Solaranteil aus
        home_session_stats(). Zusaetzlich unter "ac_dc" die AC/DC-
        Aufschluesselung der Fremdladungen (siehe
        engine.ac_dc_breakdown_from_totals()) -- eigene Funktion statt Teil
        von charging_location_breakdown(), da diese bewusst nur bereits
        berechnete Aggregate zusammenfuehrt, waehrend die AC/DC-Einordnung
        aus einer eigenen, laufend gepflegten Lebenszeit-Summe je Kategorie
        stammt (siehe _apply_charge_baselines()) -- bleibt dadurch von
        einer Archivierung/Kuerzung der history-Liste unberuehrt.

        Absichtlich UNGECACHT (bewusst gegen einen Versionszaehler-Cache
        geprueft und verworfen, siehe ChargingLocationSensor/AcChargingKwhSensor/
        DcChargingKwhSensor fuer die stattdessen gewaehlte Loesung gegen
        Doppelaufrufe): _home_kwh_since_setup() liest den LIVE-Wallbox-
        Energiezaehlerstand (_wallbox_energy) und aendert sich damit bei
        JEDEM Heimlade-Leistungssample waehrend einer laufenden Session --
        _home_capacity_version erhoeht sich dagegen nur am SESSION-ENDE
        (siehe _record_home_capacity_sample()/_record_home_charge_pct()/
        _record_home_session()). Ein Cache-Schluessel aus den vorhandenen
        Versionszaehlern (auch inkl. Kilometerstand) wuerde Heim-kWh/-Kosten
        und damit die ganze Ladeort-Aufschluesselung fuer die GESAMTE DAUER
        einer laufenden Heimladung einfrieren, statt live mitzuziehen --
        genau der Moment, in dem man am ehesten hinschaut. Kein
        Versionszaehler deckt diese Aenderung ab, also lieber ungecacht als
        ein Cache, der genau dann stale ist, wenn es am meisten auffaellt.

        Zusaetzlich unter "ladekarten" die Ladekarten-Uebersicht (siehe
        ladekarten_stats()), nur wenn mindestens eine Karte existiert.
        Ladekarten-Grundgebuehren fliessen als extra_cost in
        eur_je_100km ein, aber NICHT in "fremd" (siehe
        engine.charging_location_breakdown()'s extra_cost-Dokumentation)
        -- eine Subskriptionsgebuehr ist keinem Ladeort zuzuordnen und
        wuerde sonst fremd.preis_je_kwh verzerren.

        Zusaetzlich unter "anbieter" die Fremdladungs-Aufschluesselung nach
        Ladenetz-/Betreibername (siehe engine.anbieter_breakdown_from_totals(),
        ebenfalls aus einer laufend gepflegten Lebenszeit-Summe, siehe
        _apply_charge_baselines() -- NICHT zu verwechseln mit "ladekarten",
        das ist WOMIT bezahlt wurde, hier geht es um WO geladen wurde) und
        unter "bekannte_anbieter" die bisher erfassten Anbieter-Namen fuer
        die Vorschlagsliste im Panel (siehe engine.bekannte_anbieter() --
        bewusst weiter aus der aktuellen history-Liste statt aus einer
        Baseline: laengst nicht mehr genutzte Anbieter duerfen aus dieser
        reinen Vorschlagsliste ausklingen), jeweils nur wenn nicht leer."""
        home_kwh = self._home_kwh_since_setup()
        home_cost = self._home_cost_since_setup()
        if home_cost is None and home_kwh is not None:
            home_price = self._home_price()
            if home_price is not None:
                home_cost = round(home_kwh * home_price, 2)
        totals = self.data.get("totals", {})
        extern_kwh = totals.get("kwh", 0.0)
        extern_cost = totals.get("kosten", 0.0)
        km_driven = self._km_driven()
        home_solar_pct = self.home_session_stats().get("solar_pct")
        ladekarten = self.ladekarten_stats()
        result = charging_location_breakdown(
            home_kwh, home_cost, extern_kwh, extern_cost, km_driven, home_solar_pct,
            extra_cost=ladekarten.get("gesamt"),
        )
        ac_dc = ac_dc_breakdown_from_totals(self.data.get("ac_dc_totals") or {})
        if ac_dc:
            result["ac_dc"] = ac_dc
        if ladekarten:
            result["ladekarten"] = ladekarten
        anbieter = anbieter_breakdown_from_totals(self.data.get("anbieter_totals") or {})
        if anbieter:
            result["anbieter"] = anbieter
        bekannte = bekannte_anbieter(self.data.get("history") or [])
        if bekannte:
            result["bekannte_anbieter"] = bekannte
        return result

    def leasing_stats(self) -> dict:
        """Leasing-Kilometerbudget (siehe engine.py::leasing_status()).
        Verwendet den ABSOLUTEN Kilometerstand (self.data["odo"], mit
        derselben odo_unit-Umrechnung wie _km_driven()) gegen den
        konfigurierten Vertrags-Start-km -- bewusst NICHT _km_driven()
        selbst, das nur seit der ev_assistant-Einrichtung zaehlt und damit
        fuer einen laufenden Leasingvertrag die falsche Referenz waere.
        Leeres dict, solange inkl_km/end_datum nicht konfiguriert sind
        (siehe build_leasing_schema()) -- macht das Feature komplett
        inaktiv, bis es eingerichtet ist (keine Sensoren mit Rauschen).
        Fehlen weitere Pflichtfelder (Start-km/-datum), liefert bereits
        engine.leasing_status() selbst ein leeres dict.

        Ergebnis wird zwischengespeichert (siehe _leasing_cache in
        __init__) -- ohne das wuerde sowohl LeasingKmVorRuecklaufSensor
        (native_value + extra_state_attributes) als auch
        _check_leasing_thresholds() dieselbe Berechnung (inkl.
        rolling_km_per_day() ueber das gesamte Fahrtenbuch) jeweils einzeln
        anstossen -- bis zu dreimal pro Update fuer denselben Wert."""
        inkl_km = self._opt(CONF_LEASING_INKL_KM)
        end_datum = self._opt(CONF_LEASING_END_DATUM)
        if not inkl_km or not end_datum:
            return {}
        odo = self.data.get("odo")
        if odo is None:
            return {}
        odo_km = odo * MILES_TO_KM if self.data.get("odo_unit") == "mi" else odo
        start_km = self._opt(CONF_LEASING_START_KM)
        heute = dt_util.now().date().isoformat()
        cache_key = (self._fahrten_version, odo_km, heute, start_km, end_datum)
        if self._leasing_cache is not None and self._leasing_cache[0] == cache_key:
            return self._leasing_cache[1]
        fahrten = self.data.get("fahrten") or []
        rollierendes_tempo = rolling_km_per_day(fahrten, time.time(), _LEASING_ROLLING_WINDOW_DAYS)
        result = leasing_status(
            aktueller_km=odo_km,
            vertrag_start_km=start_km,
            vertrag_start_datum=self._opt(CONF_LEASING_START_DATUM),
            vertrag_end_datum=end_datum,
            inkl_gesamt_km=inkl_km,
            heute=heute,
            preis_mehr_km=self._opt(CONF_LEASING_PREIS_MEHR_KM),
            preis_minder_km=self._opt(CONF_LEASING_PREIS_MINDER_KM),
            rollierendes_tempo_km_pro_tag=rollierendes_tempo,
            knapp_schwelle_pct=LEASING_KNAPP_SCHWELLE_PCT,
            toleranz_pct=LEASING_TOLERANZ_PCT,
        )
        self._leasing_cache = (cache_key, result)
        return result

    def _check_leasing_thresholds(self) -> None:
        """Benachrichtigung, wenn die (lineare) Leasing-Projektion erstmals
        "knapp" oder "ueber" erreicht -- Hysterese analog
        _check_soc_thresholds(): der bereits gemeldete Status wird
        persistiert (ueberlebt einen HA-Neustart) und erst erneut gemeldet,
        wenn eine SCHLECHTERE Stufe erreicht wird -- sonst wuerde eine
        Projektion, die knapp um die Schwelle pendelt, bei jeder Messung neu
        benachrichtigen. Der gespeicherte Zustand wird zurueckgesetzt,
        sobald sich die Vertrags-Identitaet (Start-km + End-Datum) aendert
        -- ein neuer/verlaengerter Vertrag verdient wieder eigene
        Benachrichtigungen ab "im_budget"."""
        stats = self.leasing_stats()
        status = stats.get("status")
        if status is None:
            return
        identity = [self._opt(CONF_LEASING_START_KM), self._opt(CONF_LEASING_END_DATUM)]
        if self.data.get("leasing_notified_identity") != identity:
            self.data["leasing_notified_identity"] = identity
            self.data["leasing_notified_rank"] = 0
        worst_rank = self.data.get("leasing_notified_rank", 0)
        rank = _LEASING_STATUS_RANK.get(status, 0)
        if rank <= worst_rank:
            return
        self.data["leasing_notified_rank"] = rank
        if rank > 0:
            self.hass.async_create_task(self._notify_leasing(status, stats))

    async def _notify_leasing(self, status: str, stats: dict) -> None:
        """Push + persistent_notification, wenn die Leasing-Projektion
        "knapp" oder "ueber" erreicht -- siehe _check_leasing_thresholds()."""
        en = self._en()
        if status == "ueber":
            title = "Leasing mileage budget exceeded" if en else "Leasing-Kilometerbudget ueberschritten"
        else:
            title = "Leasing mileage budget tight" if en else "Leasing-Kilometerbudget knapp"
        km_vor_ruecklauf = stats.get("km_vor_ruecklauf")
        if km_vor_ruecklauf is not None:
            message = (
                f"Linear projection is currently {km_vor_ruecklauf:+.0f} km vs. plan."
                if en else
                f"Die lineare Projektion liegt aktuell {km_vor_ruecklauf:+.0f} km gegenueber dem Soll."
            )
        else:
            message = "Check the leasing tab for details." if en else "Details siehe Leasing-Tab."
        await self._push(NOTIFY_EVENT_LEASING, title, message)
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": f"{self._notify_tag}_leasing", "title": title, "message": message},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

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
            self._save_soon()
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
            self._save_soon()
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
            self._save_soon()
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

    def home_vs_external_price(self) -> Optional[dict]:
        """Vergleich Heimladen- vs. Fremdladen-Preis pro kWh, jeweils seit
        Einrichtung. Heimladen: _home_price() (bereits ein Preis, keine
        Division noetig). Fremdladen: kWh-gewichteter Durchschnitt aus den
        bestaetigten Historien-Summen (Gesamtkosten / Gesamt-kWh) -- anders
        als last_price (nur die zuletzt bestaetigte Ladung). None, wenn
        einer der beiden Preise fehlt (kein Heimstrompreis konfiguriert,
        oder noch keine Fremdladung bestaetigt)."""
        home_price = self._home_price()
        if home_price is None:
            return None
        totals = self.data.get("totals", {})
        external_kwh = totals.get("kwh", 0.0)
        if external_kwh <= 0:
            return None
        external_price = round(totals.get("kosten", 0.0) / external_kwh, 4)
        home_price = round(home_price, 4)
        return {
            "heimladen_preis_kwh": home_price,
            "fremdladen_preis_kwh": external_price,
            "differenz_kwh": round(external_price - home_price, 4),
        }

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
        den effektiv gezahlten Preis dadurch systematisch ueberschaetzen.
        fremdladen_kosten enthaelt zusaetzlich aufgelaufene Ladekarten-
        Grundgebuehren (siehe _ladekarten_cost_total()) -- die zaehlen zu
        "was kostet mich das EV insgesamt", auch ohne eine einzige Ladung
        in diesem Zeitraum."""
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
            fremdladen_kosten=self.data.get("totals", {}).get("kosten", 0.0) + self._ladekarten_cost_total(),
            verbrenner_l_100km=float(verbrenner_l) if verbrenner_l is not None else None,
            verbrenner_price_per_liter=float(verbrenner_price) if verbrenner_price is not None else None,
            home_cost=self._home_cost_since_setup(),
        )

    def _co2_per_liter_kg(self) -> float:
        """CO2-Faktor (kg/Liter) fuer den Verbrenner-Vergleich, siehe
        const.py::CO2_PER_LITER_KG. Richtet sich nach CONF_TANKERKOENIG_
        FUEL_TYPE, falls gewaehlt (dieselbe Kraftstoffsorten-Auswahl wie
        fuer die automatische Tankerkoenig-Preisermittlung) -- sonst
        Fallback auf Super/Benzin, die ueblichste Annahme fuer einen
        Kostenvergleich ohne Tankerkoenig."""
        fuel_type = self._opt(CONF_TANKERKOENIG_FUEL_TYPE)
        return CO2_PER_LITER_KG.get(fuel_type, DEFAULT_CO2_PER_LITER_KG)

    def co2_savings(self) -> Optional[dict]:
        """CO2-Bilanz gegenueber einem Verbrenner (siehe
        engine.py::calculate_co2_savings), oder None wenn eine der
        zwingend noetigen Groessen fehlt (Kilometerstand-Delta, EV-
        Strommenge, Netzstrom-CO2-Intensitaet, Verbrenner-Verbrauch).
        Nutzt dieselbe Energiebilanz wie savings()/
        _vehicle_avg_consumption_kwh_per_100km() (siehe
        _ev_kwh_total_since_setup()), daher `unknown` unter denselben
        Bedingungen wie die Verbrauchs-/Ersparnis-Sensoren."""
        verbrenner_l = self._opt(CONF_VERBRENNER_L_100KM)
        co2_per_kwh_g = self._opt(CONF_CO2_PER_KWH, DEFAULT_CO2_PER_KWH_G)
        return calculate_co2_savings(
            km_driven=self._km_driven(),
            ev_kwh_total=self._ev_kwh_total_since_setup(),
            co2_per_kwh_kg=float(co2_per_kwh_g) / 1000.0 if co2_per_kwh_g is not None else None,
            verbrenner_l_100km=float(verbrenner_l) if verbrenner_l is not None else None,
            co2_per_liter_kg=self._co2_per_liter_kg(),
        )

    def usage_profile(self) -> Optional[dict]:
        """Durchschnittlicher kWh-Bedarf pro Wochentag (siehe
        engine.py::weekday_usage_profile_from_totals()), aus der gesamten
        Fahrtenbuch-Historie seit der ersten bestaetigten Fahrt. None ohne
        Fahrten oder mit weniger als MIN_USAGE_PROFILE_DAYS Tagen Historie
        (zu wenig fuer ein aussagekraeftiges Profil).

        Berechnet aus zwei laufend gepflegten Lebenszeit-Summen je Wochentag
        (siehe _apply_trip_baselines()) statt aus einer taeglich
        aufsummierten vollen fahrten-Liste -- bleibt dadurch von einer
        Archivierung/Kuerzung dieser Liste unberuehrt; der Beobachtungs-
        zeitraum-Start ("erste Fahrt") kommt aus dem separat gefuehrten,
        durch Kuerzung ebenfalls unveraenderten fahrtenbuch_first_ts (siehe
        _apply_trip_baselines()) statt aus min(start_ts) der aktuellen
        Liste.

        Ergebnis wird pro (_fahrten_version, heutiges Datum) zwischen-
        gespeichert -- das Datum gehoert mit in den Schluessel, weil
        last_date sich auch ohne jede Fahrtenbuch-Aenderung einmal pro Tag
        weiterbewegt (siehe _fahrten_version-Kommentar in __init__)."""
        today = dt_util.now().date().isoformat()
        if (
            self._usage_profile_cache is not None
            and self._usage_profile_cache[0] == self._fahrten_version
            and self._usage_profile_cache[1] == today
        ):
            return self._usage_profile_cache[2]
        first_ts = self.data.get("fahrtenbuch_first_ts")
        if first_ts is None:
            result = None
        else:
            first_date = dt_util.as_local(dt_util.utc_from_timestamp(first_ts)).date().isoformat()
            avg_consumption = self._vehicle_avg_consumption_kwh_per_100km()
            result = weekday_usage_profile_from_totals(
                self.data.get("weekday_kwh_exact_totals") or {},
                self.data.get("weekday_km_est_totals") or {},
                avg_consumption, first_date, today, min_days=MIN_USAGE_PROFILE_DAYS,
            )
        self._usage_profile_cache = (self._fahrten_version, today, result)
        return result

    def usage_profile_tomorrow(self) -> Optional[dict]:
        """Wochentags-Bedarf (siehe usage_profile()) fuer den morgigen
        Wochentag, zzgl. CONF_USAGE_PROFILE_BUFFER_PCT Puffer -- direkt mit
        available_kwh() vergleichbar, um zu entscheiden, ob heute noch
        (z.B. ohne PV-Ueberschuss) nachgeladen werden muss."""
        profile = self.usage_profile()
        if profile is None:
            return None
        tomorrow_wd = (dt_util.now().date() + timedelta(days=1)).weekday()
        raw = profile.get(tomorrow_wd)
        if raw is None:
            return None
        buffer_pct = float(self._opt(CONF_USAGE_PROFILE_BUFFER_PCT, DEFAULT_USAGE_PROFILE_BUFFER_PCT))
        return {
            "wochentag": _WEEKDAY_NAMES_DE[tomorrow_wd],
            "roh_kwh": raw,
            "puffer_prozent": buffer_pct,
            "benoetigt_kwh": round(raw * (1.0 + buffer_pct / 100.0), 2),
        }

    def available_kwh(self) -> Optional[float]:
        """Aktuell verfuegbare Batteriekapazitaet in kWh (SoC% * nutzbare
        Kapazitaet) -- fuer den Vergleich mit usage_profile_tomorrow()."""
        if self._soc is None:
            return None
        usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        return round(self._soc / 100.0 * usable_kwh, 2)

    def _pv_forecast_tomorrow_kwh(self) -> Optional[float]:
        """Liest die optionale CONF_PV_FORECAST_ENTITY roh aus -- eine
        beliebige Sensor-Entitaet mit der PV-Ertragsprognose fuer morgen
        (z.B. Solcast "Forecast Tomorrow", Forecast.Solar "Estimated Energy
        Production - Tomorrow"). Rechnet Wh automatisch in kWh um; andere
        Integrationen liefern i.d.R. bereits kWh. None ohne konfigurierte
        Entitaet oder bei unknown/unavailable/nicht-numerischem Zustand."""
        entity_id = self._opt(CONF_PV_FORECAST_ENTITY)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (None, "unknown", "unavailable"):
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if state.attributes.get("unit_of_measurement") == "Wh":
            value /= 1000.0
        return value

    def charge_before_pv_recommended(self) -> Optional[dict]:
        """Empfehlung, ob vor dem naechsten PV-Ueberschuss noch nachgeladen
        werden sollte. None, wenn available_kwh()/usage_profile_tomorrow()
        fehlt -- siehe charge_before_pv_decision() in engine.py fuer die
        eigentliche Entscheidung (mit optionaler PV-Prognose)."""
        need = self.usage_profile_tomorrow()
        available = self.available_kwh()
        if need is None or available is None:
            return None
        pv_forecast = self._pv_forecast_tomorrow_kwh()
        result = {
            "verfuegbare_kwh": available,
            "benoetigt_morgen_kwh": need["benoetigt_kwh"],
            "empfehlung": charge_before_pv_decision(available, need["benoetigt_kwh"], pv_forecast),
        }
        if pv_forecast is not None:
            result["pv_prognose_morgen_kwh"] = round(pv_forecast, 2)
        return result

    async def _dismiss(self) -> None:
        try:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss", {"notification_id": self._notify_tag}, blocking=False
            )
        except Exception:  # noqa: BLE001
            pass

    async def _save(self) -> None:
        await self._store.async_save(self.data)

    def _save_soon(self) -> None:
        """Wie _save(), aber gebuendelt mit _SAVE_DELAY statt sofort
        synchron zu schreiben -- fuer haeufige, unkritische Zwischenstaende
        (Sensor-Mirrorwerte, Debounce-/Rollover-/Kalibrierungs-Buchhaltung),
        die beim naechsten Update ohnehin neu ankommen bzw. sich selbst
        heilen. Tatsaechlich wichtige Ereignisse (neue/bearbeitete/
        geloeschte Ladungen und Fahrten, offene Bestaetigungen) speichern
        weiterhin sofort ueber _save(). Schreibt garantiert vor einem
        geordneten HA-Shutdown (Store.async_delay_save() eigener
        EVENT_HOMEASSISTANT_FINAL_WRITE-Listener) -- das greift aber NICHT
        bei einem Entry-Reload/-Unload waehrend HA weiterlaeuft (z.B. nach
        jeder Reconfigure, siehe __init__.py::_async_reload()), daher
        flusht async_shutdown() unten zusaetzlich explizit."""
        self._store.async_delay_save(lambda: self.data, _SAVE_DELAY)

    async def async_shutdown(self) -> None:
        # _save_soon() gebuendelte Schreibvorgaenge sind hier noch nicht
        # unbedingt geschrieben (bis zu _SAVE_DELAY alt) -- Store's eigener
        # Shutdown-Schutz greift nur bei einem kompletten HA-Stopp, nicht
        # bei einem Entry-Unload/-Reload waehrend HA weiterlaeuft. Ohne
        # diesen expliziten Flush wuerde der letzte unkritische
        # Zwischenstand (z.B. SoC-/Odo-Mirrorwert) bei einem Reload
        # (jede Reconfigure!) verloren gehen.
        await self._save()
        for unsub in self._unsub:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsub = []
