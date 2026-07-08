"""Sensoren fuer ev_assistant."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
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
    ])


class PendingEstimateSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Schaetzung offen"
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
    _attr_name = "Letzte Kosten"
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
    _attr_name = "Letzte kWh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_icon = "mdi:ev-station"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_kwh")

    @property
    def native_value(self):
        hist = self.coordinator.data.get("history") or []
        return hist[0]["kwh"] if hist else None


class TotalKwhSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "kWh gesamt"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_kwh")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kwh", 0.0)


class TotalCostSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Kosten gesamt"
    _attr_native_unit_of_measurement = "EUR"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:cash-multiple"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "total_cost")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("kosten", 0.0)


class CountSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Anzahl Ladungen"
    _attr_icon = "mdi:format-list-numbered"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "count")

    @property
    def native_value(self):
        return self.coordinator.data.get("totals", {}).get("count", 0)


class LastPriceSensor(EvAssistantEntity, SensorEntity):
    _attr_name = "Letzter Preis"
    _attr_native_unit_of_measurement = "EUR/kWh"
    _attr_icon = "mdi:currency-eur"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "last_price")

    @property
    def native_value(self):
        return self.coordinator.data.get("last_price", 0.0)
