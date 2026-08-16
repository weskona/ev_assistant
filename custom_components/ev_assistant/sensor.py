"""Sensoren fuer ev_assistant."""
from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfLength, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EFFICIENCY,
    CONF_ERSTZULASSUNG,
    CONF_TANKERKOENIG_FUEL_TYPE,
    CONF_VERBRENNER_PRICE_ENTITY,
    CONF_VERBRENNER_PRICE_PER_LITER,
    DEFAULT_EFFICIENCY,
    DOMAIN,
    EFF_MIN_SAMPLES,
)
from .entity import EvAssistantEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PendingEstimateSensor(coordinator, entry),
        LastCostSensor(coordinator, entry),
        LastKwhSensor(coordinator, entry),
        TotalKwhSensor(coordinator, entry),
        TotalCostSensor(coordinator, entry),
        CountSensor(coordinator, entry),
        LastPriceSensor(coordinator, entry),
        LastDurationSensor(coordinator, entry),
        LastChargePowerSensor(coordinator, entry),
        MeasuredEfficiencySensor(coordinator, entry),
        OdoSensor(coordinator, entry),
        OdoDayKmSensor(coordinator, entry),
        OdoWeekKmSensor(coordinator, entry),
        OdoMonthKmSensor(coordinator, entry),
        OdoYearKmSensor(coordinator, entry),
        OdoAvgDaySensor(coordinator, entry),
        OdoAvgWeekSensor(coordinator, entry),
        OdoAvgMonthSensor(coordinator, entry),
        OdoAvgYearSensor(coordinator, entry),
        OdoYearProjectedSensor(coordinator, entry),
        OdoAnnualFromRegSensor(coordinator, entry),
        ErstzulassungSensor(coordinator, entry),
        HomeKwhSensor(coordinator, entry),
        HomeCostSensor(coordinator, entry),
        SavingsSensor(coordinator, entry),
        VerbrennerPriceSelectedSensor(coordinator, entry),
        PendingTripSensor(coordinator, entry),
        LastTripSensor(coordinator, entry),
        TripCountSensor(coordinator, entry),
        TotalTripKmSensor(coordinator, entry),
        TripAvgConsumptionSensor(coordinator, entry),
        VehicleAvgConsumptionSensor(coordinator, entry),
        RangeEstimateSensor(coordinator, entry),
        BatteryCapacitySensor(coordinator, entry),
        EquivalentFullCyclesSensor(coordinator, entry),
        ChargingLocationSensor(coordinator, entry),
        LeasingKmVorRuecklaufSensor(coordinator, entry),
        Co2SavingsSensor(coordinator, entry),
        HomeVsExternalPriceSensor(coordinator, entry),
        CostDaySensor(coordinator, entry),
        CostWeekSensor(coordinator, entry),
        CostMonthSensor(coordinator, entry),
        CostYearSensor(coordinator, entry),
        UsageProfileSensor(coordinator, entry),
        UsageProfileTomorrowSensor(coordinator, entry),
        AvailableKwhSensor(coordinator, entry),
    ])


class PendingEstimateSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "pending_estimate"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:help-circle-outline"
    # force_update: der native_value bleibt oft gleich, waehrend sich nur
    # Attribute aendern (z.B. offene_ladungen-Liste bei mehreren offenen
    # Ladungen) -- ohne force_update schreibt HA solche reinen
    # Attribut-Aenderungen nicht zuverlaessig in die State Machine.
    _attr_force_update = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "pending_estimate")

    @property
    def native_value(self):
        pending = self.coordinator.data.get("pending") or []
        return round(pending[0]["energy_kwh"], 2) if pending else None

    @property
    def extra_state_attributes(self):
        pending = self.coordinator.data.get("pending") or []
        attrs: dict = {"anzahl_offen": len(pending)}
        if pending:
            attrs.update(pending[0])
        attrs["offene_ladungen"] = pending
        return attrs


class LastCostSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "last_cost"
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash"
    # force_update: edit_charge/delete_charge auf einen AELTEREN (nicht den
    # juengsten) Historien-Eintrag aendert die historie-Liste, aber nicht
    # den native_value (hist[0]) -- ohne force_update kommt die Aenderung
    # sonst nicht zuverlaessig in der Karte/UI an.
    _attr_force_update = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_cost")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0]["kosten"] if hist else None

    @property
    def extra_state_attributes(self):
        hist = self.coordinator.data.get("history") or []
        attrs: dict = dict(hist[0]) if hist else {}
        attrs["historie"] = hist
        return attrs


class LastKwhSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "last_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_kwh")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0]["kwh"] if hist else None


class TotalKwhSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "total_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    # TOTAL statt TOTAL_INCREASING: edit_charge()/delete_charge() koennen den
    # zugrunde liegenden totals["kwh"]-Wert auch VERRINGERN (Korrektur/
    # Loeschung eines Eintrags) -- der Recorder wuerde ein Absinken bei
    # TOTAL_INCREASING als Zaehler-Reset werten und die Langzeitstatistik
    # verfaelschen.
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_kwh")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kwh", 0.0)


class TotalCostSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "total_cost"
    _attr_native_unit_of_measurement = "EUR"
    # Siehe Kommentar bei TotalKwhSensor -- totals["kosten"] kann durch
    # edit_charge()/delete_charge() sinken.
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_cost")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kosten", 0.0)


class CountSensor(EvAssistantEntity, SensorEntity):
    """Fremdladung-Anzahl -- traegt zusaetzlich "lade_modus" als Attribut
    (siehe coordinator.py::lade_modus()), damit das Panel den Modus lesen
    kann, ohne einen neuen Netzwerkweg/Sensor dafuer zu brauchen (dieselbe
    Entitaet wird ohnehin schon fuer die Fahrzeuge-Tab-KPI aufgeloest).
    Bewusst hier statt an einer neuen dedizierten Entitaet, um keine
    zusaetzliche Sensor-Entitaet nur fuer ein Sichtbarkeits-Flag anzulegen."""

    _attr_translation_key = "count"
    # Siehe Kommentar bei TotalKwhSensor -- totals["count"] kann durch
    # delete_charge() sinken.
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "count")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("count", 0)

    @property
    def extra_state_attributes(self):
        return {"lade_modus": self.coordinator.lade_modus()}


class LastPriceSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "last_price"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:currency-eur"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_price")

    @property
    def native_value(self):
        return self.coordinator.data.get("last_price", 0.0)


class LastDurationSensor(EvAssistantEntity, SensorEntity):
    """Ladezeit der zuletzt bestaetigten Fremdladung (von Erkennungs-Start
    bis Erkennungs-Ende, siehe engine.py::ChargeEvent.duration_min) --
    unbekannt fuer Alt-Eintraege vor Einfuehrung von dauer_min, sowie fuer
    manuelle Einzeleintraege ohne zugrunde liegende Erkennung."""

    _attr_translation_key = "last_duration"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_duration")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0].get("dauer_min") if hist else None


class LastChargePowerSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "last_charge_power"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:flash"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_charge_power")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        if not hist:
            return None
        h = hist[0]
        kwh = h.get("kwh")
        dauer_min = h.get("dauer_min")
        if not kwh or not dauer_min or dauer_min < 5:
            return None
        power = kwh / (dauer_min / 60)
        if not 1 <= power <= 350:
            return None
        return round(power, 2)


class MeasuredEfficiencySensor(EvAssistantEntity, SensorEntity):
    """Aus echten Heim-Ladesessions kalibrierter Ladewirkungsgrad (siehe
    engine.py::EfficiencyCalibrator). Ersetzt automatisch den manuell
    eingegebenen Wert fuer alle Berechnungen, sobald genug Sessions
    ausgewertet wurden (EFF_MIN_SAMPLES) — bis dahin bleibt der manuelle
    Wert (Attribut manueller_wert) massgeblich."""

    _attr_translation_key = "measured_efficiency"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "measured_efficiency")

    @property
    def native_value(self):
        val = self.coordinator.data.get("measured_efficiency")
        return round(val * 100, 1) if val is not None else None

    @property
    def extra_state_attributes(self):
        samples = self.coordinator.data.get("efficiency_samples") or []
        entry = self.coordinator.entry
        manueller_wert = entry.options.get(
            CONF_EFFICIENCY, entry.data.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)
        )
        return {
            "anzahl_sessions": len(samples),
            "benoetigte_sessions": EFF_MIN_SAMPLES,
            "einzelwerte_prozent": [round(s * 100, 1) for s in samples],
            "wird_verwendet": self.coordinator.data.get("measured_efficiency") is not None,
            "manueller_wert_prozent": round(manueller_wert * 100, 1),
        }


class OdoSensor(EvAssistantEntity, SensorEntity):
    """Kilometerstand, gespiegelt von der im Fahrzeug-Schritt gewaehlten
    Quell-Entitaet — gruppiert am EV-Assistant-Geraet statt an dem Geraet
    der Herkunfts-Integration."""

    _attr_translation_key = "odo"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo")

    @property
    def native_value(self):
        return self.coordinator.data.get("odo")

    @property
    def native_unit_of_measurement(self):
        return self.coordinator.data.get("odo_unit") or UnitOfLength.KILOMETERS


class _OdoPeriodSensor(EvAssistantEntity, SensorEntity):
    """Basis fuer Tag/Woche/Monat/Jahr-km-Sensoren."""
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _PERIOD: str = ""

    def __init__(self, coordinator, entry, unique_suffix):
        super().__init__(coordinator, entry, unique_suffix)

    @property
    def native_value(self):
        odo = self.coordinator.data.get("odo")
        if odo is None:
            return None
        unit = self.coordinator.data.get("odo_unit", "km")
        from .const import MILES_TO_KM
        odo_km = odo * MILES_TO_KM if unit == "mi" else float(odo)
        entry = self.coordinator.data.get("odo_periods", {}).get(self._PERIOD)
        if not entry:
            return None
        delta = round(odo_km - entry["odo_km"], 1)
        return delta if delta >= 0 else None


class OdoDayKmSensor(_OdoPeriodSensor):
    _attr_translation_key = "odo_day_km"
    _attr_icon = "mdi:calendar-today"
    _PERIOD = "day"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_day_km")


class OdoWeekKmSensor(_OdoPeriodSensor):
    _attr_translation_key = "odo_week_km"
    _attr_icon = "mdi:calendar-week"
    _PERIOD = "week"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_week_km")


class OdoMonthKmSensor(_OdoPeriodSensor):
    _attr_translation_key = "odo_month_km"
    _attr_icon = "mdi:calendar-month"
    _PERIOD = "month"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_month_km")


class OdoYearKmSensor(_OdoPeriodSensor):
    _attr_translation_key = "odo_year_km"
    _attr_icon = "mdi:calendar-blank"
    _PERIOD = "year"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_year_km")


class _OdoLtsSensor(EvAssistantEntity, SensorEntity):
    """Basis fuer LTS-basierte Odometer-Projektionssensoren."""
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def _lts(self):
        return self.coordinator.data.get("odo_lts", {})

    def _delta(self, key_start, key_end="sum_now"):
        lts = self._lts()
        s = lts.get(key_start)
        e = lts.get(key_end)
        if s is None or e is None:
            return None
        d = e - s
        return d if d >= 0 else None


class OdoAvgDaySensor(_OdoLtsSensor):
    _attr_translation_key = "odo_avg_day"
    _attr_icon = "mdi:calendar-today"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_avg_day")

    @property
    def native_value(self):
        d = self._delta("sum_30d_ago")
        return round(d / 30, 1) if d is not None else None


class OdoAvgWeekSensor(_OdoLtsSensor):
    _attr_translation_key = "odo_avg_week"
    _attr_icon = "mdi:calendar-week"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_avg_week")

    @property
    def native_value(self):
        d = self._delta("sum_30d_ago")
        return round(d / 30 * 7) if d is not None else None


class OdoAvgMonthSensor(_OdoLtsSensor):
    _attr_translation_key = "odo_avg_month"
    _attr_icon = "mdi:calendar-month"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_avg_month")

    @property
    def native_value(self):
        d = self._delta("sum_90d_ago")
        return round(d / 3) if d is not None else None


class OdoAvgYearSensor(_OdoLtsSensor):
    _attr_translation_key = "odo_avg_year"
    _attr_icon = "mdi:calendar-blank-multiple"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_avg_year")

    @property
    def native_value(self):
        d = self._delta("sum_365d_ago")
        return round(d) if d is not None else None


class OdoYearProjectedSensor(_OdoLtsSensor):
    _attr_translation_key = "odo_year_projected"
    _attr_icon = "mdi:chart-timeline-variant"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_year_projected")

    @property
    def native_value(self):
        import calendar as cal
        d = self._delta("sum_year_start")
        if d is None or d <= 0:
            return None
        today = dt_util.now().date()
        day_of_year = today.timetuple().tm_yday
        if day_of_year < 7:
            return None
        days_in_year = 366 if cal.isleap(today.year) else 365
        return round(d / (day_of_year / days_in_year))


class OdoAnnualFromRegSensor(EvAssistantEntity, SensorEntity):
    """Durchschnittliche Jahreskilometerleistung seit Erstzulassung.
    Berechnung: aktueller Kilometerstand / (Tage seit Erstzulassung / 365.25).
    Setzt voraus, dass das Fahrzeug bei Erstzulassung 0 km hatte."""

    _attr_translation_key = "odo_annual_from_reg"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:chart-bell-curve"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "odo_annual_from_reg")

    @property
    def native_value(self):
        reg_raw = self.coordinator.entry.options.get(
            CONF_ERSTZULASSUNG,
            self.coordinator.entry.data.get(CONF_ERSTZULASSUNG),
        )
        if not reg_raw:
            return None
        try:
            reg_date = date.fromisoformat(reg_raw)
        except (ValueError, TypeError):
            return None
        odo = self.coordinator.data.get("odo")
        if odo is None:
            return None
        unit = self.coordinator.data.get("odo_unit", "km")
        from .const import MILES_TO_KM
        odo_km = odo * MILES_TO_KM if unit == "mi" else float(odo)
        days = (dt_util.now().date() - reg_date).days
        if days < 30:
            return None
        return round(odo_km / (days / 365.25))


class ErstzulassungSensor(EvAssistantEntity, SensorEntity):
    """Erstzulassungsdatum aus den Fahrzeug-Eckdaten — rein statischer
    Konfigurationswert, keine Live-Quelle noetig."""

    _attr_translation_key = "erstzulassung"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:calendar"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "erstzulassung")

    @property
    def native_value(self):
        entry = self.coordinator.entry
        value = entry.options.get(CONF_ERSTZULASSUNG, entry.data.get(CONF_ERSTZULASSUNG))
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return None


class HomeKwhSensor(EvAssistantEntity, SensorEntity):
    """Zuhause geladene kWh seit Einrichtung (Delta des Wallbox-
    Energiezaehlers) -- Grundlage fuer den Kostenvergleich gegenueber
    einem Verbrenner. unknown ohne konfigurierte Wallbox-Energiemessung
    (Schritt 3 des Config Flow).

    Attribute (falls evccs Session-Entities konfiguriert UND verfuegbar
    sind, siehe coordinator.py::home_session_stats()): kWh-gewichteter
    Solaranteil sowie Kostensumme/Preis je kWh aus evccs eigenen Heim-
    Ladesessions. Gilt NUR fuer Heimladungen, die evcc selbst gesteuert
    hat -- Fremdladen liefert diese Felder nicht."""

    _attr_translation_key = "home_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "home_kwh")

    @property
    def native_value(self):
        return self.coordinator._home_kwh()

    @property
    def extra_state_attributes(self):
        stats = self.coordinator.home_session_stats()
        attrs = {}
        if "solar_pct" in stats:
            attrs["evcc_solaranteil_pct"] = stats["solar_pct"]
        if "kosten_gesamt" in stats:
            attrs["evcc_kosten_gesamt"] = stats["kosten_gesamt"]
        if "preis_je_kwh" in stats:
            attrs["evcc_preis_je_kwh"] = stats["preis_je_kwh"]
        return attrs


class HomeCostSensor(EvAssistantEntity, SensorEntity):
    """Geschaetzte Heimladen-Kosten seit Einrichtung (Heimladen-kWh x
    konfigurierter Heimstrompreis, Schritt 6). unknown ohne Wallbox-
    Energiemessung oder ohne konfigurierten Heimstrompreis."""

    _attr_translation_key = "home_cost"
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-currency-usd"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "home_cost")

    @property
    def native_value(self):
        direct = self.coordinator._home_cost()
        if direct is not None:
            return direct
        home_kwh = self.coordinator._home_kwh()
        home_price = self.coordinator._home_price()
        if home_kwh is None or home_price is None:
            return None
        return round(home_kwh * home_price, 2)


class SavingsSensor(EvAssistantEntity, SensorEntity):
    """Ersparnis gegenueber einem Vergleichs-Verbrenner auf derselben
    Strecke (siehe engine.py::calculate_savings). unknown, bis
    Kilometerstand-Entitaet (Schritt 1), Verbrenner-Verbrauch und
    -Kraftstoffpreis (Schritt 6) konfiguriert sind. Heimladen-kWh/-Preis
    sind dabei einzeln optional -- fehlen sie, wird nur mit den
    Fremdladungskosten gerechnet (siehe engine.py::calculate_savings)."""

    _attr_translation_key = "savings"
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "savings")

    @property
    def native_value(self):
        savings = self.coordinator.savings()
        return savings["ersparnis"] if savings else None

    @property
    def extra_state_attributes(self):
        savings = self.coordinator.savings()
        if not savings:
            return {}
        attrs = dict(savings)
        attrs["gefahrene_km"] = self.coordinator._km_driven()
        attrs["fremdladen_kosten"] = self.coordinator.data.get("totals", {}).get("kosten", 0.0)
        attrs["kraftstoffpreis_live"] = self.coordinator._verbrenner_price_live is not None
        attrs["heimstrompreis_live"] = self.coordinator._home_price_live is not None
        return attrs


class VerbrennerPriceSelectedSensor(EvAssistantEntity, SensorEntity):
    """Der aktuell fuer den Verbrenner-Vergleich verwendete Kraftstoffpreis
    (Rohwert, nicht der intern zeitgewichtete Durchschnitt aus
    coordinator.py::_price_average() -- der bleibt ein reines Detail der
    savings()-Berechnung). state_class macht diesen Wert per Long-Term
    Statistics historisierbar, unabhaengig davon, welche der drei Quellen
    (Tankerkoenig-Auto-Erkennung > eigene Entitaet > fester Wert) aktiv ist."""

    _attr_translation_key = "verbrenner_price_selected"
    _attr_native_unit_of_measurement = "EUR/L"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "verbrenner_price_selected")

    @property
    def native_value(self):
        if self.coordinator._verbrenner_price_live is not None:
            return self.coordinator._verbrenner_price_live
        price = self.coordinator._opt(CONF_VERBRENNER_PRICE_PER_LITER)
        return float(price) if price is not None else None

    @property
    def extra_state_attributes(self):
        if self.coordinator._opt(CONF_TANKERKOENIG_FUEL_TYPE):
            quelle = "tankerkoenig"
        elif self.coordinator._opt(CONF_VERBRENNER_PRICE_ENTITY):
            quelle = "entity"
        else:
            quelle = "fixed"
        return {"quelle": quelle}


class PendingTripSensor(EvAssistantEntity, SensorEntity):
    """Kilometer der aeltesten offenen (noch nicht bestaetigten) Fahrt --
    analog PendingEstimateSensor fuer Fremdladungen."""

    _attr_translation_key = "trip_pending_estimate"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_icon = "mdi:map-marker-path"
    _attr_force_update = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "trip_pending_estimate")

    @property
    def native_value(self):
        pending = self.coordinator.data.get("pending_trips") or []
        return pending[0]["km"] if pending else None

    @property
    def extra_state_attributes(self):
        pending = self.coordinator.data.get("pending_trips") or []
        attrs: dict = {"anzahl_offen": len(pending)}
        if pending:
            attrs.update(pending[0])
        attrs["offene_fahrten"] = pending
        return attrs


class LastTripSensor(EvAssistantEntity, SensorEntity):
    """Letzte bestaetigte Fahrt (Fahrtenbuch) -- analog LastCostSensor."""

    _attr_translation_key = "last_trip_km"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"
    _attr_force_update = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_trip_km")

    @property
    def native_value(self):
        fahrten = self.coordinator.data.get("fahrten") or []
        return fahrten[0]["km"] if fahrten else None

    @property
    def extra_state_attributes(self):
        fahrten = self.coordinator.data.get("fahrten") or []
        attrs: dict = dict(fahrten[0]) if fahrten else {}
        attrs["fahrtenbuch"] = fahrten
        return attrs


class TripCountSensor(EvAssistantEntity, SensorEntity):
    """Anzahl bestaetigter Fahrtenbuch-Eintraege -- analog CountSensor."""

    _attr_translation_key = "trip_count"
    # Siehe Kommentar bei TotalKwhSensor -- trip_totals["count"] kann durch
    # delete_trip() sinken.
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "trip_count")

    @property
    def native_value(self):
        return self.coordinator.data.get("trip_totals", {}).get("count", 0)


class TotalTripKmSensor(EvAssistantEntity, SensorEntity):
    """Gesamt-km im Fahrtenbuch seit Einrichtung -- analog TotalKwhSensor."""

    _attr_translation_key = "total_trip_km"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    # Siehe Kommentar bei TotalKwhSensor -- trip_totals["km"] kann durch
    # edit_trip()/delete_trip() sinken.
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_trip_km")

    @property
    def native_value(self):
        return self.coordinator.data.get("trip_totals", {}).get("km", 0.0)


class TripAvgConsumptionSensor(EvAssistantEntity, SensorEntity):
    """Durchschnittsverbrauch in kWh pro Fahrt ueber alle Fahrtenbuch-
    Eintraege mit bekanntem Verbrauch (siehe
    coordinator.py::_trip_avg_consumption_kwh())."""

    _attr_translation_key = "trip_avg_consumption"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "trip_avg_consumption")

    @property
    def native_value(self):
        return self.coordinator._trip_avg_consumption_kwh()


class VehicleAvgConsumptionSensor(EvAssistantEntity, SensorEntity):
    """Durchschnittsverbrauch des Fahrzeugs in kWh/100km ueber die gesamte
    Zeit seit Einrichtung, aus der Energiebilanz (Heimladen + Fremdladen
    kWh gesamt / gefahrene km) -- siehe
    coordinator.py::_vehicle_avg_consumption_kwh_per_100km(). Anders als
    trip_avg_consumption unabhaengig davon, ob jede Fahrt im Fahrtenbuch
    bestaetigt wurde."""

    _attr_translation_key = "vehicle_avg_consumption"
    _attr_native_unit_of_measurement = "kWh/100km"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "vehicle_avg_consumption")

    @property
    def native_value(self):
        return self.coordinator._vehicle_avg_consumption_kwh_per_100km()


class RangeEstimateSensor(EvAssistantEntity, SensorEntity):
    """Geschaetzte Restreichweite: aktueller SoC * nutzbare kWh ueber den
    Realverbrauch der letzten 30 Tage (siehe coordinator.py::
    range_estimate_km()) -- ehrlicher als eine Bordanzeige, weil
    tatsaechlicher Fahrstil/Jahreszeit einfliessen statt eines werksseitig
    pauschalen Verbrauchswerts. unknown ohne aktuellen SoC oder ganz ohne
    Fahrtenbuch-Verbrauchsdaten (weder rollierend noch Lebenszeit-
    Fallback verfuegbar, z.B. direkt nach Einrichtung)."""

    _attr_translation_key = "range_estimate"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "range_estimate")

    @property
    def native_value(self):
        return self.coordinator.range_estimate_km()

    @property
    def extra_state_attributes(self):
        coordinator = self.coordinator
        buckets = coordinator._consumption_by_temp_bucket()
        bucket = coordinator.current_temp_bucket()
        bucket_consumption = buckets.get(bucket)
        if bucket_consumption is not None:
            consumption = bucket_consumption
        else:
            consumption = coordinator._vehicle_avg_consumption_kwh_per_100km_rolling()
        attrs = {}
        if coordinator._outside_temp is not None:
            attrs["aussentemperatur"] = round(coordinator._outside_temp, 1)
        if consumption is None:
            return attrs
        attrs["verbrauch_kwh_100km"] = consumption
        if bucket is not None:
            attrs["temperaturband_aktuell"] = bucket
        if buckets:
            attrs["verbrauch_nach_temperatur"] = buckets
        return attrs


class BatteryCapacitySensor(EvAssistantEntity, SensorEntity):
    """Rollierend geschaetzte tatsaechliche Akku-Gesamtkapazitaet aus
    Fremdladungen mit grossem SoC-Hub (siehe coordinator.py::
    battery_capacity_kwh()). Der absolute Wert liegt typischerweise UEBER
    dem Datenblatt-Wert: DC-Schnellladung hat reale Ladeverluste (Innen-
    widerstand, BMS-Balancing), die hier nicht herausgerechnet werden
    (anders als bei Heim-Sessions gibt es keinen unabhaengigen zweiten
    Messwert, aus dem sich ein DC-Wirkungsgrad kalibrieren liesse) -- die
    gemeldete kWh-Energie ist also etwas mehr, als tatsaechlich in der
    Batterie ankommt, was die berechnete Kapazitaet nach oben verzerrt.
    Deshalb bewusst kein Vergleichswert gegen das eingetragene usable_kwh
    hier: das eigentliche Gesundheitssignal ist der Trend ueber Monate/
    Jahre, nicht die absolute Zahl. unknown ohne mindestens zwei
    ausreichend breite Fremdladungen."""

    _attr_translation_key = "battery_capacity"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-heart-variant"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "battery_capacity")

    @property
    def native_value(self):
        return self.coordinator.battery_capacity_kwh()


class EquivalentFullCyclesSensor(EvAssistantEntity, SensorEntity):
    """Aequivalente Vollzyklen (0%->100%->0% waere 1 Zyklus) aus Fahrtenbuch
    (Entladung), Fremd- und Heim-Ladungen (Ladung), siehe coordinator.py::
    equivalent_full_cycles() -- ergaenzt battery_capacity um die zweite,
    bei realen Akku-Garantien uebliche Kennzahl (Zyklen zusaetzlich zu
    Jahren). TOTAL statt TOTAL_INCREASING, da Fahrten/Fremdladungen
    nachtraeglich geloescht werden koennen (siehe TotalKwhSensor-Kommentar)."""

    _attr_translation_key = "equivalent_full_cycles"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:battery-sync"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "equivalent_full_cycles")

    @property
    def native_value(self):
        return self.coordinator.equivalent_full_cycles()


class ChargingLocationSensor(EvAssistantEntity, SensorEntity):
    """"So verteilt sich deine Ladung" -- Heim-Anteil an der kWh-Gesamt-
    Ladeenergie (Heim + Fremd) als Hauptwert, volle Aufschluesselung als
    Attribute (siehe coordinator.py::charging_location_stats()/engine.
    charging_location_breakdown()): kWh/Kosten/Anteile je Ladeort,
    Heim-Solaranteil, sowie ein fahrzeugweites eur_je_100km -- bewusst
    NICHT je Ladeort, da sich gefahrene km keinem Ladeort zuordnen lassen.
    unknown ohne jede bekannte Lademenge (weder Heim noch Fremd)."""

    _attr_translation_key = "charging_location_breakdown"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-donut"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "charging_location_breakdown")

    @property
    def native_value(self):
        stats = self.coordinator.charging_location_stats()
        return stats.get("heim", {}).get("kwh_anteil_pct")

    @property
    def extra_state_attributes(self):
        return self.coordinator.charging_location_stats()


class LeasingKmVorRuecklaufSensor(EvAssistantEntity, SensorEntity):
    """Leasing-Kilometerbudget: Ist- minus Soll-km seit Vertragsbeginn als
    Hauptwert (siehe coordinator.py::leasing_stats()/engine.py::
    leasing_status()) -- positiv heisst mehr gefahren als der lineare
    Vertrags-Plan bis heute vorsieht (Richtung Nachzahlung), negativ
    weniger. Volle Details (beide Projektionen linear/rollierend,
    verbleibendes Tagesbudget, Euro-Schaetzung, Status) als Attribute.
    unknown, solange Leasing nicht eingerichtet ist (inkl_km/end_datum
    fehlen, siehe build_leasing_schema()) -- absichtlich KEIN Rauschen ohne
    Konfiguration."""

    _attr_translation_key = "leasing_km_vor_ruecklauf"
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:file-document-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "leasing_km_vor_ruecklauf")

    @property
    def native_value(self):
        return self.coordinator.leasing_stats().get("km_vor_ruecklauf")

    @property
    def extra_state_attributes(self):
        return self.coordinator.leasing_stats()


class Co2SavingsSensor(EvAssistantEntity, SensorEntity):
    """CO2-Ersparnis gegenueber einem Vergleichs-Verbrenner auf derselben
    Strecke (siehe engine.py::calculate_co2_savings) -- analog SavingsSensor,
    nur kg CO2 statt EUR. unknown, bis Kilometerstand-Entitaet (Schritt 1)
    und Verbrenner-Verbrauch (Schritt 7) konfiguriert sind."""

    _attr_translation_key = "co2_savings"
    _attr_native_unit_of_measurement = "kg"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:molecule-co2"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "co2_savings")

    @property
    def native_value(self):
        co2 = self.coordinator.co2_savings()
        return co2["co2_ersparnis_kg"] if co2 else None

    @property
    def extra_state_attributes(self):
        co2 = self.coordinator.co2_savings()
        return dict(co2) if co2 else {}


class HomeVsExternalPriceSensor(EvAssistantEntity, SensorEntity):
    """Preisunterschied Fremdladen ggue. Heimladen (EUR/kWh, jeweils
    gewichteter Durchschnitt seit Einrichtung) -- siehe
    coordinator.py::home_vs_external_price(). Positiv = Fremdladen teurer
    (der Normalfall). unknown ohne Heimstrompreis oder solange noch keine
    Fremdladung bestaetigt wurde."""

    _attr_translation_key = "home_vs_external_price"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "home_vs_external_price")

    @property
    def native_value(self):
        cmp = self.coordinator.home_vs_external_price()
        return cmp["differenz_kwh"] if cmp else None

    @property
    def extra_state_attributes(self):
        cmp = self.coordinator.home_vs_external_price()
        return dict(cmp) if cmp else {}


class _CostPeriodSensor(EvAssistantEntity, SensorEntity):
    """Basisklasse fuer die Kosten-Perioden-Sensoren (Tag/Woche/Monat/Jahr)
    -- analog _OdoPeriodSensor, nur EV-Gesamtkosten (Heim + Fremd seit
    Einrichtung, siehe coordinator.py::_ev_cost_total_since_setup()) statt
    Kilometerstand. Anders als beim Odometer-Pendant wird ein negatives
    Delta auf 0 geklemmt statt als unknown behandelt: der Heimladen-Anteil
    ist (mangels evcc-Kostenstatistik) haeufig kWh * gewichteter
    Durchschnittspreis -- dieser Durchschnitt kann leicht sinken, wenn eine
    neue, guenstigere Ladesession einfliesst, wodurch die Gesamtkosten
    kurzzeitig unter die Perioden-Basislinie fallen koennen, OHNE dass dies
    ein Anzeichen fuer einen echten Fehler (wie beim monoton steigenden
    Kilometerstand) ist."""

    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cash-multiple"

    _PERIOD: str = ""

    def __init__(self, coordinator, entry, unique_suffix):
        super().__init__(coordinator, entry, unique_suffix)

    @property
    def native_value(self):
        entry = self.coordinator.data.get("cost_periods", {}).get(self._PERIOD)
        if not entry:
            return None
        cost = self.coordinator._ev_cost_total_since_setup()
        return max(0.0, round(cost - entry["cost"], 2))


class CostDaySensor(_CostPeriodSensor):
    _attr_translation_key = "cost_day"
    _attr_icon = "mdi:calendar-today"
    _PERIOD = "day"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "cost_day")


class CostWeekSensor(_CostPeriodSensor):
    _attr_translation_key = "cost_week"
    _attr_icon = "mdi:calendar-week"
    _PERIOD = "week"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "cost_week")


class CostMonthSensor(_CostPeriodSensor):
    _attr_translation_key = "cost_month"
    _attr_icon = "mdi:calendar-month"
    _PERIOD = "month"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "cost_month")


class CostYearSensor(_CostPeriodSensor):
    _attr_translation_key = "cost_year"
    _attr_icon = "mdi:calendar-blank"
    _PERIOD = "year"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "cost_year")


class UsageProfileSensor(EvAssistantEntity, SensorEntity):
    """Durchschnittlicher kWh-Bedarf pro Wochentag aus der Fahrtenbuch-
    Historie (siehe coordinator.py::usage_profile()/engine.py::
    weekday_usage_profile()) -- native_value ist der heutige Wochentag,
    alle 7 Werte stehen als Attribute zur Verfuegung (z.B. fuer das
    Nutzungsprofil-Tab im Panel). unknown, solange weniger als 7 Tage
    Fahrtenbuch-Historie vorliegen."""

    _attr_translation_key = "usage_profile"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calendar-week"

    _WEEKDAY_KEYS = ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "usage_profile")

    @property
    def native_value(self):
        profile = self.coordinator.usage_profile()
        if not profile:
            return None
        today_wd = dt_util.now().weekday()
        return profile.get(today_wd)

    @property
    def extra_state_attributes(self):
        profile = self.coordinator.usage_profile()
        if not profile:
            return {}
        return {self._WEEKDAY_KEYS[wd]: kwh for wd, kwh in profile.items()}


class UsageProfileTomorrowSensor(EvAssistantEntity, SensorEntity):
    """Gepufferter kWh-Bedarf fuer morgen (siehe
    coordinator.py::usage_profile_tomorrow()) -- direkt mit dem SoC-
    basierten `available_kwh`-Sensor vergleichbar, um zu entscheiden, ob
    heute noch (z.B. ohne PV-Ueberschuss) nachgeladen werden muss."""

    _attr_translation_key = "usage_profile_tomorrow"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "usage_profile_tomorrow")

    @property
    def native_value(self):
        need = self.coordinator.usage_profile_tomorrow()
        return need["benoetigt_kwh"] if need else None

    @property
    def extra_state_attributes(self):
        need = self.coordinator.usage_profile_tomorrow()
        return dict(need) if need else {}


class AvailableKwhSensor(EvAssistantEntity, SensorEntity):
    """Aktuell verfuegbare Batteriekapazitaet in kWh (siehe
    coordinator.py::available_kwh()) -- SoC% * nutzbare Kapazitaet."""

    _attr_translation_key = "available_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:battery-high"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "available_kwh")

    @property
    def native_value(self):
        return self.coordinator.available_kwh()
