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
    async_add_entities([
        PendingBinarySensor(coordinator, entry),
        TripPendingBinarySensor(coordinator, entry),
        ChargeBeforePvBinarySensor(coordinator, entry),
    ])


class PendingBinarySensor(EvAssistantEntity, BinarySensorEntity):
    _attr_translation_key = "pending"
    _attr_icon = "mdi:bell-ring"
    # force_update: is_on bleibt oft gleich, waehrend sich nur Attribute
    # aendern (z.B. anzahl_offen 1->2 bei mehreren offenen Ladungen) --
    # siehe PendingEstimateSensor in sensor.py fuer denselben Fall.
    _attr_force_update = True

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


class TripPendingBinarySensor(EvAssistantEntity, BinarySensorEntity):
    """Analog PendingBinarySensor, aber fuer offene (unbestaetigte) Fahrten."""

    _attr_translation_key = "trip_pending"
    _attr_icon = "mdi:map-marker-distance"
    # Siehe Kommentar bei PendingBinarySensor.
    _attr_force_update = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "trip_pending")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("pending_trips"))

    @property
    def extra_state_attributes(self):
        pending = self.coordinator.data.get("pending_trips") or []
        attrs: dict = {"anzahl_offen": len(pending)}
        if pending:
            attrs.update(pending[0])
        attrs["offene_fahrten"] = pending
        return attrs


class ChargeBeforePvBinarySensor(EvAssistantEntity, BinarySensorEntity):
    """Empfehlung, ob vor dem naechsten PV-Ueberschuss noch nachgeladen
    werden sollte (siehe coordinator.py::charge_before_pv_recommended()):
    verfuegbare Batteriekapazitaet reicht nicht fuer den morgigen,
    historisch-typischen (gepufferten) Wochentags-Bedarf. Mit optionaler
    CONF_PV_FORECAST_ENTITY darf die morgen erwartete PV-Erzeugung eine
    Luecke schliessen (siehe engine.py::charge_before_pv_decision()).
    unknown, solange kein Nutzungsprofil vorliegt (siehe UsageProfileSensor)
    oder kein SoC bekannt ist."""

    _attr_translation_key = "charge_before_pv_recommended"
    _attr_icon = "mdi:battery-charging-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "charge_before_pv_recommended")

    @property
    def is_on(self):
        rec = self.coordinator.charge_before_pv_recommended()
        return rec["empfehlung"] if rec else None

    @property
    def extra_state_attributes(self):
        rec = self.coordinator.charge_before_pv_recommended()
        if not rec:
            return {}
        attrs = {"verfuegbare_kwh": rec["verfuegbare_kwh"], "benoetigt_morgen_kwh": rec["benoetigt_morgen_kwh"]}
        if "pv_prognose_morgen_kwh" in rec:
            attrs["pv_prognose_morgen_kwh"] = rec["pv_prognose_morgen_kwh"]
        return attrs
