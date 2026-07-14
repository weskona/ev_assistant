"""Sensoren fuer ev_assistant."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_EFFICIENCY, DEFAULT_EFFICIENCY, DOMAIN, EFF_MIN_SAMPLES
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
        MeasuredEfficiencySensor(coordinator, entry),
    ])


class PendingEstimateSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Fremdladung Schätzung"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:help-circle-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "pending_estimate")

    @property
    def native_value(self):
        pend = self.coordinator.data.get("pending")
        return round(pend["energy_kwh"], 2) if pend else None

    @property
    def extra_state_attributes(self):
        return self.coordinator.data.get("pending") or {}


class LastCostSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Fremdladung Kosten (letzte)"
    _attr_native_unit_of_measurement = "EUR"
    _attr_icon = "mdi:cash"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_cost")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0]["kosten"] if hist else None

    @property
    def extra_state_attributes(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0] if hist else {}


class LastKwhSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Fremdladung kWh (letzte)"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_kwh")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0]["kwh"] if hist else None


class TotalKwhSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Fremdladung kWh (gesamt)"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_kwh")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kwh", 0.0)


class TotalCostSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Fremdladung Kosten (gesamt)"
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_cost")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kosten", 0.0)


class CountSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Fremdladung Anzahl"
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "count")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("count", 0)


class LastPriceSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Fremdladung Preis (letzter)"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_icon = "mdi:currency-eur"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_price")

    @property
    def native_value(self):
        return self.coordinator.data.get("last_price", 0.0)


class MeasuredEfficiencySensor(EvAssistantEntity, SensorEntity):
    """Aus echten Heim-Ladesessions kalibrierter Ladewirkungsgrad (siehe
    engine.py::EfficiencyCalibrator). Ersetzt automatisch den manuell
    eingegebenen Wert fuer alle Berechnungen, sobald genug Sessions
    ausgewertet wurden (EFF_MIN_SAMPLES) — bis dahin bleibt der manuelle
    Wert (Attribut manueller_wert) massgeblich."""

    _attr_name = "Ladewirkungsgrad (gemessen)"
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
