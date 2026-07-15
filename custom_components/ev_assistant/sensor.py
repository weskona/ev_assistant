"""Sensoren fuer ev_assistant."""
from __future__ import annotations

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_EFFICIENCY, CONF_ERSTZULASSUNG, DEFAULT_EFFICIENCY, DOMAIN, EFF_MIN_SAMPLES
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
        MeasuredEfficiencySensor(coordinator, entry),
        OdoSensor(coordinator, entry),
        ErstzulassungSensor(coordinator, entry),
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
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "count")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("count", 0)


class LastPriceSensor(EvAssistantEntity, SensorEntity):
    _attr_translation_key = "last_price"
    _attr_native_unit_of_measurement = "EUR/kWh"
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
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_duration")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0].get("dauer_min") if hist else None


class MeasuredEfficiencySensor(EvAssistantEntity, SensorEntity):
    """Aus echten Heim-Ladesessions kalibrierter Ladewirkungsgrad (siehe
    engine.py::EfficiencyCalibrator). Ersetzt automatisch den manuell
    eingegebenen Wert fuer alle Berechnungen, sobald genug Sessions
    ausgewertet wurden (EFF_MIN_SAMPLES) — bis dahin bleibt der manuelle
    Wert (Attribut manueller_wert) massgeblich."""

    _attr_translation_key = "measured_efficiency"
    _attr_native_unit_of_measurement = "%"
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
