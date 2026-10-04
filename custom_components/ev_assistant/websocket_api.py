"""Websocket-API: Ladelogbuch direkt vom evcc-Addon holen.

Ersetzt evcc_intgs fruehere `evcc_intg/sessions`-Kommando -- das Panel ruft
`/api/sessions` jetzt ueber den eigenen evcc-Client dieser Integration ab
(server-seitig, kein CORS/Mixed-Content, keine zusaetzlichen Entities),
aber ohne die fruehere Fremdabhaengigkeit und deren dreistufige
entry_id-Aufloesung -- config_entry_id ist bereits bekannt (das Panel
kennt sie ohnehin fuer jeden anderen ev_assistant-Aufruf, siehe
__init__.py::_coordinator_for()).
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EvAssistantCoordinator


def _lookup(hass: HomeAssistant, config_entry_id: str):
    """Coordinator zur config_entry_id -- hass.data[DOMAIN] enthaelt auch interne
    Flag-Schluessel (_ev_panel, ...), die nie als Coordinator gelten duerfen."""
    coordinator = hass.data.get(DOMAIN, {}).get(config_entry_id)
    return coordinator if isinstance(coordinator, EvAssistantCoordinator) else None


COMMAND_TYPE = "ev_assistant/evcc_sessions"


@websocket_api.websocket_command({
    vol.Required("type"): COMMAND_TYPE,
    vol.Required("config_entry_id"): str,
})
@websocket_api.async_response
async def _handle_evcc_sessions(hass: HomeAssistant, connection, msg) -> None:
    coordinator = _lookup(hass, msg["config_entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "unknown config_entry_id")
        return
    connection.send_result(msg["id"], {"sessions": await coordinator.async_get_evcc_sessions()})


EVENT_LOG_COMMAND_TYPE = "ev_assistant/event_log"


@websocket_api.websocket_command({
    vol.Required("type"): EVENT_LOG_COMMAND_TYPE,
    vol.Required("config_entry_id"): str,
})
@websocket_api.async_response
async def _handle_event_log(hass: HomeAssistant, connection, msg) -> None:
    """Liefert das persistente Ereignisprotokoll (siehe coordinator.py::
    _log_event()/EVENT_LOG_MAX_AGE_DAYS) direkt aus dem Arbeitsspeicher --
    fuer die scrollbare Live-Ansicht im Einstellungen-Panel-Tab (Nutzerwunsch
    2026-09-27: "die 14 tage logdatei... quasi live in der karte darstellen").
    Bewusst als eigenes WS-Kommando statt als Entity-Attribut: das Protokoll
    kann ueber 14 Tage auf mehrere zehn KB anwachsen, als State-Attribut
    wuerde das bei jeder Aenderung unnoetig den Recorder aufblaehen bzw.
    HAs Attribut-Groessenwarnung ausloesen -- ein WS-Abruf bei Tab-Oeffnen/
    -Auffrischung (siehe _fetchEventLog() im Panel) umgeht das komplett,
    identisches Muster wie _handle_evcc_sessions() oben."""
    coordinator = _lookup(hass, msg["config_entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "unknown config_entry_id")
        return
    connection.send_result(msg["id"], {"event_log": list(coordinator.data.get("event_log") or [])})


TRIPS_COMMAND_TYPE = "ev_assistant/trips"


@websocket_api.websocket_command({
    vol.Required("type"): TRIPS_COMMAND_TYPE,
    vol.Required("config_entry_id"): str,
})
@websocket_api.async_response
async def _handle_trips(hass: HomeAssistant, connection, msg) -> None:
    """Liefert das komplette Fahrtenbuch (data['fahrten']), sortiert nach
    start_ts absteigend -- identisches Muster wie _handle_event_log() oben:
    das Panel zeigt in der Fahrten-Historie (siehe _renderTripHistory()) bei
    "alle anzeigen" ALLE Eintraege, nicht nur die letzten 5 -- bei
    FAHRTEN_MAX_MONATE=24 Monaten und ggf. mehreren Fahrten pro Tag kann das
    weit ueber HAs 16KB-Attribut-Limit hinauswachsen (siehe frueherer Bug:
    "State attributes for sensor.*_fahrt_km_letzte exceed maximum size of
    16384 bytes"). Deshalb eigenes WS-Kommando statt Sensor-Attribut
    (sensor.py::LastTripSensor haengt seit diesem Fix nur noch die Felder
    der letzten Fahrt selbst an, keine "fahrtenbuch"-Liste mehr)."""
    coordinator = _lookup(hass, msg["config_entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "unknown config_entry_id")
        return
    fahrten = list(coordinator.data.get("fahrten") or [])
    fahrten.sort(key=lambda r: r.get("start_ts") or r.get("erfasst_ts") or 0, reverse=True)
    connection.send_result(msg["id"], {"trips": fahrten})


CHARGES_COMMAND_TYPE = "ev_assistant/charges"


@websocket_api.websocket_command({
    vol.Required("type"): CHARGES_COMMAND_TYPE,
    vol.Required("config_entry_id"): str,
})
@websocket_api.async_response
async def _handle_charges(hass: HomeAssistant, connection, msg) -> None:
    """Liefert die komplette Ladehistorie (data['history']), sortiert nach
    start_ts absteigend -- gleicher Grund/gleiches Muster wie
    _handle_trips() oben, fuer sensor.py::LastCostSensor ("historie"-
    Attribut). Bei HISTORY_MAX_MONATE=24 Monaten bisher seltener ueber
    16KB gewachsen als das Fahrtenbuch (Ladevorgaenge sind seltener als
    Fahrten), aber strukturell dieselbe Schwachstelle -- vorsorglich
    gleich mitbehoben."""
    coordinator = _lookup(hass, msg["config_entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "unknown config_entry_id")
        return
    history = list(coordinator.data.get("history") or [])
    history.sort(key=lambda r: r.get("start_ts") or r.get("erfasst_ts") or 0, reverse=True)
    connection.send_result(msg["id"], {"charges": history})


def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, _handle_evcc_sessions)
    websocket_api.async_register_command(hass, _handle_event_log)
    websocket_api.async_register_command(hass, _handle_trips)
    websocket_api.async_register_command(hass, _handle_charges)
