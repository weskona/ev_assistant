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
    _attr_translation_key = "pending"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "pending")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("pending"))

    @property
    def extra_state_attributes(self):
        pending = self.coordinator.data.get("pending") or []
        attrs: dict = {"anzahl_offen": len(pending)}
        if pending:
            # Aelteste Ladung weiterhin flach in den Attributen (Rueckwaerts-
            # kompatibel zu Dashboards/Automationen aus der Zeit vor
            # Mehrfach-Unterstuetzung, die z.B. state_attr(..., 'soc_start')
            # direkt lesen).
            attrs.update(pending[0])
        attrs["offene_ladungen"] = pending
        return attrs
