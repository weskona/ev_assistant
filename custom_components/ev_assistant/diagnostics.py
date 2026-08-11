"""Diagnostics fuer ev_assistant."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import EvAssistantCoordinator

# Bewegungs-/Standortdaten aus dem Fahrtenbuch -- start_ort/end_ort koennen
# bei einem einfachen sensor als GPS-Vorschlag-Quelle (CONF_GPS_ENTITY) eine
# echte Adresse sein, nicht nur ein Zonen-Name (siehe README). async_redact_
# data() greift rekursiv in Listen/verschachtelte Dicts, trifft also
# gleichermassen data["fahrten"], data["pending_trips"] und den Top-Level-
# Schluessel trip_start_zone. Config-Felder (entry.data/entry.options)
# brauchen keine Redaction: das Schema enthaelt ausschliesslich Entity-IDs
# und Zahlenwerte, keine Kennwoerter/Tokens.
TO_REDACT_LOCATION = {
    "start_ort", "end_ort", "start_ort_vorschlag", "end_ort_vorschlag", "trip_start_zone",
}

# Nur die neuesten Eintraege in die Diagnose aufnehmen -- history/fahrten
# wachsen seit v0.20.1 bewusst unbegrenzt (siehe CHANGELOG), ein voller Dump
# waere fuer eine Punkt-in-der-Zeit-Fehlersuche unnoetig gross. Fuer einen
# vollstaendigen Export gibt es den export_fahrtenbuch-Service.
HISTORY_DIAG_LIMIT = 20


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Diagnose-Daten fuer einen ev_assistant Config Entry."""
    coordinator: EvAssistantCoordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data

    history = data.get("history") or []
    fahrten = data.get("fahrten") or []
    coordinator_data = {
        **data,
        "history": history[:HISTORY_DIAG_LIMIT],
        "history_gesamt_anzahl": len(history),
        "fahrten": fahrten[:HISTORY_DIAG_LIMIT],
        "fahrten_gesamt_anzahl": len(fahrten),
    }

    return {
        "entry_data": dict(entry.data),
        "entry_options": dict(entry.options),
        "coordinator_data": async_redact_data(coordinator_data, TO_REDACT_LOCATION),
    }
