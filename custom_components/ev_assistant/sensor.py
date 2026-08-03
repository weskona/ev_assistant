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
    CONF_EFFICIENCY, CONF_ERSTZULASSUNG, DEFAULT_EFFICIENCY,
    CONF_TANKERKOENIG_FUEL_TYPE, CONF_VERBRENNER_PRICE_ENTITY, CONF_VERBRENNER_PRICE_PER_LITER,
    DOMAIN, EFF_MIN_SAMPLES,
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
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_kwh")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kwh", 0.0)


class TotalCostSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "total_cost"
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_cost")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kosten", 0.0)


class CountSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "count"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "count")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("count", 0)


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
    (Schritt 3 des Config Flow)."""

    _attr_translation_key = "home_kwh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:home-lightning-bolt"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "home_kwh")

    @property
    def native_value(self):
        return self.coordinator._home_kwh()


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
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
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
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_trip_km")

    @property
    def native_value(self):
        return self.coordinator.data.get("trip_totals", {}).get("km", 0.0)
