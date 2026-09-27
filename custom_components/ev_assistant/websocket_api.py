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

COMMAND_TYPE = "ev_assistant/evcc_sessions"


@websocket_api.websocket_command({
    vol.Required("type"): COMMAND_TYPE,
    vol.Required("config_entry_id"): str,
})
@websocket_api.async_response
async def _handle_evcc_sessions(hass: HomeAssistant, connection, msg) -> None:
    coordinator = hass.data.get(DOMAIN, {}).get(msg["config_entry_id"])
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
    coordinator = hass.data.get(DOMAIN, {}).get(msg["config_entry_id"])
    if coordinator is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "unknown config_entry_id")
        return
    connection.send_result(msg["id"], {"event_log": list(coordinator.data.get("event_log") or [])})


def async_register(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, _handle_evcc_sessions)
    websocket_api.async_register_command(hass, _handle_event_log)
