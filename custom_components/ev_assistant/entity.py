"""Gemeinsame Entity-Basis (Device-Gruppierung)."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL, DOMAIN
from .coordinator import EvAssistantCoordinator


def _opt(entry: ConfigEntry, key: str, default=None):
    return entry.options.get(key, entry.data.get(key, default))


class EvAssistantEntity(CoordinatorEntity[EvAssistantCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: EvAssistantCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        hersteller = _opt(entry, CONF_VEHICLE_HERSTELLER)
        modell = _opt(entry, CONF_VEHICLE_MODELL)
        fahrzeug = f"{hersteller} {modell}".strip() if (hersteller or modell) else None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=fahrzeug or "EV Assistant",
            manufacturer=hersteller or "DIY",
            model=modell or "ev_assistant",
        )
