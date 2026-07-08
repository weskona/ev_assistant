"""Gemeinsame Entity-Basis (Device-Gruppierung)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EvAssistantCoordinator


class EvAssistantEntity(CoordinatorEntity[EvAssistantCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EvAssistantCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="EV Assistant",
            manufacturer="DIY",
            model="ev_assistant",
        )
