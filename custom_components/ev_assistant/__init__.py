"""ev_assistant — Fremdladung: Setup, Services, Unload."""
from __future__ import annotations

import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    CONF_EVCC_VEHICLE_NAME,
    CONF_SOC_ENTITY,
    CONF_VEHICLE_HERSTELLER,
    CONF_VEHICLE_MODELL,
    DOMAIN,
    EVCC_CONF_KEYS,
    PLATFORMS,
    SERVICE_DELETE,
    SERVICE_DELETE_TRIP,
    SERVICE_DISCARD,
    SERVICE_DISCARD_TRIP,
    SERVICE_EDIT,
    SERVICE_EDIT_TRIP,
    SERVICE_EXPORT_TRIPS,
    SERVICE_IMPORT_TRIPS,
    SERVICE_LOG,
    SERVICE_LOG_TRIP,
    SERVICE_SIMULATE,
    SERVICE_SIMULATE_TRIP,
)
from .coordinator import EvAssistantCoordinator

_LOGGER = logging.getLogger(__name__)

_PANEL_URL_PATH = "ev-assistant"
_PANEL_STATIC_PATH = "/ev_assistant_static"
_PANEL_TITLE = "EV Assistant"
_PANEL_ICON = "mdi:car-electric"
_STATIC_REGISTERED = "_ev_panel_static"
_PANEL_REGISTERED = "_ev_panel"


def _vehicle_display_name(ev_entry: ConfigEntry) -> str:
    """Hersteller + Modell, exakt dieselbe Berechnung wie entity.py's
    DeviceInfo.name -- damit das Panel den Fahrzeugnamen direkt aus der
    Konfiguration bezieht statt ihn aus entry.title herzuleiten. entry.title
    (z.B. "EV Assistant (Peugeot eRifter)" oder aelter "EV Assistant Peugeot
    eRifter" ohne Klammern, je nach dem Code-Stand beim Anlegen) wird nur
    EINMAL bei der Erstellung gesetzt und nie automatisch aktualisiert --
    ein Parsen dieses Titels im Panel ist daher fragil gegenueber
    Formatwechseln zwischen Versionen."""
    hersteller = ev_entry.options.get(CONF_VEHICLE_HERSTELLER) or ev_entry.data.get(CONF_VEHICLE_HERSTELLER)
    modell = ev_entry.options.get(CONF_VEHICLE_MODELL) or ev_entry.data.get(CONF_VEHICLE_MODELL)
    fahrzeug = f"{hersteller or ''} {modell or ''}".strip()
    return fahrzeug or ev_entry.title


def _build_entity_map(ent_reg, ev_entry, evcc_conf_keys) -> dict:
    """Entity-Map für einen einzelnen Config-Entry aufbauen."""
    from homeassistant.helpers import entity_registry as er_mod
    entries = er_mod.async_entries_for_config_entry(ent_reg, ev_entry.entry_id)
    entity_map: dict = {}
    prefix = ev_entry.entry_id + "_"
    for e in entries:
        if e.unique_id.startswith(prefix):
            entity_map[e.unique_id[len(prefix):]] = e.entity_id
    for key in evcc_conf_keys:
        eid = ev_entry.options.get(key) or ev_entry.data.get(key)
        if eid:
            entity_map[key] = eid
    # Fahrzeugkarte im Panel soll den SoC von DIESER Entitaet zeigen (Schritt 1,
    # immer konfiguriert, dieselbe Quelle, der auch die Erkennung vertraut) --
    # nicht von evcc_vehicle_soc, das evcc-Namensschema-abhaengig und optional ist.
    soc_eid = ev_entry.options.get(CONF_SOC_ENTITY) or ev_entry.data.get(CONF_SOC_ENTITY)
    if soc_eid:
        entity_map["soc_entity"] = soc_eid
    return entity_map


async def _async_register_panel(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Sidebar-Panel registrieren. Fehler blockieren nie den Setup."""
    try:
        from homeassistant.components import frontend, panel_custom
        from homeassistant.components.http import StaticPathConfig
        from homeassistant.helpers import entity_registry as er

        domain_data = hass.data.setdefault(DOMAIN, {})
        frontend_dir = Path(__file__).parent / "frontend"

        if not domain_data.get(_STATIC_REGISTERED):
            await hass.http.async_register_static_paths(
                [StaticPathConfig(_PANEL_STATIC_PATH, str(frontend_dir), cache_headers=False)]
            )
            domain_data[_STATIC_REGISTERED] = True

        js_file = frontend_dir / "ev-assistant-panel.js"
        try:
            cache_bust = str(int(js_file.stat().st_mtime))
        except Exception:
            cache_bust = "1"

        ent_reg = er.async_get(hass)

        # Alle ev_assistant-Entries sammeln → vehicles-Array für das Panel
        vehicles = []
        for ev_entry in hass.config_entries.async_entries(DOMAIN):
            ev_map = _build_entity_map(ent_reg, ev_entry, EVCC_CONF_KEYS)
            vehicle: dict = {
                "config_entry_id": ev_entry.entry_id,
                "title": ev_entry.title,
                "name": _vehicle_display_name(ev_entry),
                "entities": ev_map,
            }
            evcc_vname = ev_entry.options.get(CONF_EVCC_VEHICLE_NAME) or ev_entry.data.get(CONF_EVCC_VEHICLE_NAME)
            if evcc_vname:
                vehicle["evcc_vehicle_name"] = evcc_vname
            vehicles.append(vehicle)

        # Aufrufenden Entry als Top-Level-Kontext setzen (Rückwärtskompatibilität)
        entity_map = _build_entity_map(ent_reg, entry, EVCC_CONF_KEYS)
        panel_config: dict = {
            "title": entry.title,
            "name": _vehicle_display_name(entry),
            "entities": entity_map,
            "config_entry_id": entry.entry_id,
            "vehicles": vehicles,
        }
        evcc_vehicle_name = entry.options.get(CONF_EVCC_VEHICLE_NAME) or entry.data.get(CONF_EVCC_VEHICLE_NAME)
        if evcc_vehicle_name:
            panel_config["evcc_vehicle_name"] = evcc_vehicle_name

        # evcc_intg config_entry_id direkt mitgeben, damit _evccEntryId() im Panel
        # nicht auf hass.entities.platform angewiesen ist (in panel_custom unzuverlaessig).
        for evcc_entry in hass.config_entries.async_entries("evcc_intg"):
            panel_config["evcc_entry_id"] = evcc_entry.entry_id
            break

        try:
            frontend.async_remove_panel(hass, _PANEL_URL_PATH, warn_if_unknown=False)
        except Exception:
            pass

        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=_PANEL_URL_PATH,
            webcomponent_name="ev-assistant-panel",
            module_url=f"{_PANEL_STATIC_PATH}/ev-assistant-panel.js?v={cache_bust}",
            sidebar_title=_PANEL_TITLE,
            sidebar_icon=_PANEL_ICON,
            require_admin=False,
            config=panel_config,
        )
        domain_data[_PANEL_REGISTERED] = True
        _LOGGER.info("EV Assistant Panel registriert (v=%s, %d Fahrzeuge)", cache_bust, len(vehicles))
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("EV Assistant Panel konnte nicht registriert werden: %s", exc)


def _async_unregister_panel(hass: HomeAssistant) -> None:
    """Panel beim Entladen des letzten Entries entfernen."""
    if not hass.data.get(DOMAIN, {}).get(_PANEL_REGISTERED):
        return
    try:
        from homeassistant.components import frontend
        frontend.async_remove_panel(hass, _PANEL_URL_PATH, warn_if_unknown=False)
        hass.data[DOMAIN].pop(_PANEL_REGISTERED, None)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Fehler beim Entfernen des Panels: %s", exc)

LOG_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("kwh"): vol.Coerce(float),
    vol.Required("price_kwh"): vol.Coerce(float),
    vol.Optional("start_ts"): vol.Coerce(float),
    vol.Optional("start_fee", default=0.0): vol.Coerce(float),
    vol.Optional("block_fee", default=0.0): vol.Coerce(float),
    vol.Optional("time_fee", default=0.0): vol.Coerce(float),
})

DISCARD_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Optional("start_ts"): vol.Coerce(float),
})

SIMULATE_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("soc_start"): vol.Coerce(float),
    vol.Required("soc_end"): vol.Coerce(float),
    vol.Optional("energy_source", default="soc"): str,
})

EDIT_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
    vol.Optional("kwh"): vol.Coerce(float),
    vol.Optional("price_kwh"): vol.Coerce(float),
    vol.Optional("start_fee"): vol.Coerce(float),
    vol.Optional("block_fee"): vol.Coerce(float),
    vol.Optional("time_fee"): vol.Coerce(float),
    vol.Optional("start_ts"): vol.Coerce(float),
    vol.Optional("end_ts"): vol.Coerce(float),
    vol.Optional("soc_start"): vol.Coerce(float),
    vol.Optional("soc_end"): vol.Coerce(float),
})

DELETE_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
})

LOG_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("start_ort"): str,
    vol.Required("end_ort"): str,
    vol.Optional("start_ts"): vol.Coerce(float),
})

DISCARD_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Optional("start_ts"): vol.Coerce(float),
})

EXPORT_TRIPS_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
})

SIMULATE_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("km"): vol.Coerce(float),
})

EDIT_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
    vol.Optional("start_ort"): str,
    vol.Optional("end_ort"): str,
    vol.Optional("start_ts"): vol.Coerce(float),
    vol.Optional("end_ts"): vol.Coerce(float),
    vol.Optional("km"): vol.Coerce(float),
    vol.Optional("odo_start"): vol.Coerce(float),
    vol.Optional("odo_end"): vol.Coerce(float),
    vol.Optional("soc_start"): vol.Coerce(float),
    vol.Optional("soc_end"): vol.Coerce(float),
    vol.Optional("verbrauch_kwh"): vol.Coerce(float),
})

DELETE_TRIP_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    vol.Required("erfasst_ts"): vol.Coerce(int),
})

IMPORT_TRIPS_SCHEMA = vol.Schema({
    vol.Required("config_entry_id"): str,
    # Akzeptiert sowohl eine reine Liste als auch versehentlich die komplette
    # Quelldatei inkl. ihres umschliessenden "trips"-Schluessels (haeufiger
    # Copy-Paste-Fehler in Entwicklertools -> Aktionen).
    vol.Required("trips"): vol.Any([dict], vol.Schema({vol.Required("trips"): [dict]}, extra=vol.ALLOW_EXTRA)),
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Backfill fuer Entries von vor Einfuehrung der unique_id (siehe
    # EvAssistantConfigFlow.async_step_fahrzeug) -- ohne das wuerde der
    # Duplikat-Schutz fuer bereits bestehende Fahrzeuge nie greifen, weil sie
    # schlicht keine unique_id haben, mit der eine neu angelegte kollidieren
    # koennte.
    if entry.unique_id is None:
        soc_entity = entry.options.get(CONF_SOC_ENTITY) or entry.data.get(CONF_SOC_ENTITY)
        if soc_entity:
            hass.config_entries.async_update_entry(entry, unique_id=soc_entity)
    coordinator = EvAssistantCoordinator(hass, entry)
    await coordinator.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _register_services(hass)
    await _async_register_panel(hass, entry)
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinator_for(hass: HomeAssistant, config_entry_id: str) -> EvAssistantCoordinator | None:
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry_id)
    if coordinator is None:
        _LOGGER.warning("ev_assistant: unbekannte config_entry_id %s", config_entry_id)
    return coordinator


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_LOG):
        return

    async def _handle_log(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_log_charge(
                call.data["kwh"], call.data["price_kwh"], call.data.get("start_ts"),
                call.data.get("start_fee", 0.0), call.data.get("block_fee", 0.0),
                call.data.get("time_fee", 0.0),
            )

    async def _handle_discard(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_discard(call.data.get("start_ts"))

    async def _handle_simulate(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_simulate(
                call.data["soc_start"], call.data["soc_end"], call.data.get("energy_source", "soc")
            )

    async def _handle_edit(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_edit_charge(
                call.data["erfasst_ts"],
                call.data.get("kwh"),
                call.data.get("price_kwh"),
                call.data.get("start_fee"),
                call.data.get("block_fee"),
                call.data.get("time_fee"),
                call.data.get("start_ts"),
                call.data.get("end_ts"),
                call.data.get("soc_start"),
                call.data.get("soc_end"),
            )

    async def _handle_delete(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_delete_charge(call.data["erfasst_ts"])

    async def _handle_log_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_log_trip(
                call.data["start_ort"], call.data["end_ort"], call.data.get("start_ts")
            )

    async def _handle_discard_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_discard_trip(call.data.get("start_ts"))

    async def _handle_export_trips(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_export_fahrtenbuch()

    async def _handle_simulate_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_simulate_trip(call.data["km"])

    async def _handle_edit_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_edit_trip(
                call.data["erfasst_ts"],
                start_ort=call.data.get("start_ort"),
                end_ort=call.data.get("end_ort"),
                start_ts=call.data.get("start_ts"),
                end_ts=call.data.get("end_ts"),
                km=call.data.get("km"),
                odo_start=call.data.get("odo_start"),
                odo_end=call.data.get("odo_end"),
                soc_start=call.data.get("soc_start"),
                soc_end=call.data.get("soc_end"),
                verbrauch_kwh=call.data.get("verbrauch_kwh"),
            )

    async def _handle_delete_trip(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            await coordinator.async_delete_trip(call.data["erfasst_ts"])

    async def _handle_import_trips(call: ServiceCall) -> None:
        coordinator = _coordinator_for(hass, call.data["config_entry_id"])
        if coordinator:
            trips = call.data["trips"]
            if isinstance(trips, dict):
                trips = trips.get("trips", [])
            await coordinator.async_import_fahrtenbuch(trips)

    hass.services.async_register(DOMAIN, SERVICE_LOG, _handle_log, schema=LOG_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCARD, _handle_discard, schema=DISCARD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SIMULATE, _handle_simulate, schema=SIMULATE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EDIT, _handle_edit, schema=EDIT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE, _handle_delete, schema=DELETE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_LOG_TRIP, _handle_log_trip, schema=LOG_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISCARD_TRIP, _handle_discard_trip, schema=DISCARD_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EXPORT_TRIPS, _handle_export_trips, schema=EXPORT_TRIPS_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SIMULATE_TRIP, _handle_simulate_trip, schema=SIMULATE_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_EDIT_TRIP, _handle_edit_trip, schema=EDIT_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_TRIP, _handle_delete_trip, schema=DELETE_TRIP_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_IMPORT_TRIPS, _handle_import_trips, schema=IMPORT_TRIPS_SCHEMA)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Default statt KeyError: async_unload_entry kann theoretisch auch
        # aufgerufen werden, wenn der Eintrag hier nie ankam (z.B. wenn
        # async_setup_entry vor dem hass.data-Eintrag fehlgeschlagen ist).
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None:
            await coordinator.async_shutdown()
        if not hass.data[DOMAIN]:
            _async_unregister_panel(hass)
            for service in (
                SERVICE_LOG, SERVICE_DISCARD, SERVICE_SIMULATE, SERVICE_EDIT, SERVICE_DELETE,
                SERVICE_LOG_TRIP, SERVICE_DISCARD_TRIP, SERVICE_EXPORT_TRIPS, SERVICE_SIMULATE_TRIP,
                SERVICE_EDIT_TRIP, SERVICE_DELETE_TRIP, SERVICE_IMPORT_TRIPS,
            ):
                hass.services.async_remove(DOMAIN, service)
        else:
            # Panel mit verbleibenden Fahrzeugen neu registrieren
            remaining = next(
                (e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id in hass.data[DOMAIN]),
                None,
            )
            if remaining:
                await _async_register_panel(hass, remaining)
    return unload_ok
