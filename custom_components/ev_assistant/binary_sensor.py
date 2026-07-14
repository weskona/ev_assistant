"""Binary-Sensor: offene (unbestaetigte) Fremdladung."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import EvAssistantEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PendingBinarySensor(coordinator, entry)])


class PendingBinarySensor(EvAssistantEntity, BinarySensorEntity):
    _attr_name = "Fremdladung Erfassung offen"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "pending")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("pending") is not None

    @property
    def extra_state_attributes(self):
        return self.coordinator.data.get("pending") or {}
