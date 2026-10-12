"""Image-Entitaet: das optionale Fahrzeugbild eines Entries.

Vertrag fuer externe Karten (Glow & Co.): pro Entry gibt es IMMER genau eine
Entitaet "Fahrzeugbild" (unique_id "<entry_id>_vehicle_image", Entity-ID
sprach-/namensabhaengig -- aus der Panel-Konfiguration lesen,
Schluessel "vehicle_image" in der Panel-Konfiguration, auch in jedem
vehicles[i].entities). Sie ist versteckt, aber aktiviert. Ohne Bild ist der
State `unknown` -- dann NICHT image_proxy abrufen (liefert HTTP 500), sondern
den eigenen Platzhalter zeigen: EV Assistant liefert keinen. Mit Bild ist der
State der Zeitpunkt der letzten Aenderung, `entity_picture` zeigt auf
/api/image_proxy/<entity_id>?token=... Gesetzt/entfernt wird es ueber die
Services set_vehicle_image/clear_vehicle_image.

Das Bild liegt als Datei unter <config>/ev_assistant_images/ (siehe images.py),
nie in self.data/Store/Attributen."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import images
from .const import DOMAIN
from .entity import device_info_for

# hass.data-Schluessel: entry_id -> VehicleImageEntity (damit die Services die
# Entitaet nach set/clear aktualisieren koennen).
IMAGE_ENTITIES_KEY = f"{DOMAIN}_vehicle_images"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([VehicleImageEntity(hass, entry)])


class VehicleImageEntity(ImageEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_image"
    _attr_entity_registry_visible_default = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass)
        self._entry_id = entry.entry_id
        self._dir = images.image_dir(hass.config.config_dir)
        self._attr_unique_id = f"{entry.entry_id}_vehicle_image"
        self._attr_device_info = device_info_for(entry)

    async def async_added_to_hass(self) -> None:
        self.hass.data.setdefault(IMAGE_ENTITIES_KEY, {})[self._entry_id] = self
        await self.async_refresh_from_disk(write_state=False)

    async def async_will_remove_from_hass(self) -> None:
        registry = self.hass.data.get(IMAGE_ENTITIES_KEY, {})
        if registry.get(self._entry_id) is self:
            registry.pop(self._entry_id, None)

    async def async_refresh_from_disk(self, write_state: bool = True) -> None:
        """Liest Zeitpunkt/Typ der Datei neu ein (Setup, nach set/clear). Ohne
        Datei wird der State wieder `unknown`."""
        info = await self.hass.async_add_executor_job(images.image_info, self._dir, self._entry_id)
        last_updated: datetime | None
        if info is None:
            last_updated = None
        else:
            last_updated, self._attr_content_type = info
        self._attr_image_last_updated = last_updated
        self._cached_image = None
        if write_state and self.hass is not None:
            self.async_write_ha_state()

    def image(self) -> bytes | None:
        """Laeuft im Executor (siehe ImageEntity.async_image())."""
        return images.read_image(self._dir, self._entry_id)
