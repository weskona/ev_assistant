"""Benachrichtigungen: Push (notify) und persistent_notification fuer Fremdladungen, Fahrten, SoC-Schwellen und Tankerkoenig.

Aus coordinator.py ausgelagert (Umbau vor der 1.0, siehe Issue #12). Der Zustand
(data['pending'], _notify_tag usw.) bleibt im Coordinator ("host"); diese Klasse
haelt keinen eigenen Zustand. Die Methoden des Coordinators bestehen unveraendert
und rufen hierher durch.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.exceptions import ServiceNotFound

from .const import (
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_EVENTS,
    DEFAULT_NOTIFY_EVENTS,
    NOTIFY_EVENT_FAHRT,
    NOTIFY_EVENT_FREMDLADUNG,
    NOTIFY_EVENT_SOC_SCHWELLE,
    NOTIFY_EVENT_TANKERKOENIG,
)

if TYPE_CHECKING:
    from .coordinator import EvAssistantCoordinator

_LOGGER = logging.getLogger(__name__)


class Notifications:
    """Benachrichtigungen fuer genau einen Coordinator (siehe Modul-Docstring)."""

    def __init__(self, host: EvAssistantCoordinator) -> None:
        self._host = host

    def _en(self) -> bool:
        """Ob die HA-Oberflaeche auf Englisch eingestellt ist. Entity-/
        Config-Flow-Texte laufen ueber strings.json/translations/*.json und
        HA's eigenes Uebersetzungssystem -- das hier betrifft nur den freien
        Benachrichtigungstext (persistent_notification/notify), den dieses
        System nicht abdeckt, daher die Sprachwahl von Hand."""
        host = self._host
        return host.hass.config.language.startswith("en")

    async def _notify(self) -> None:
        """Baut EINE Benachrichtigung (gleiche notification_id, ersetzt sich
        selbst) fuer ALLE aktuell offenen Fremdladungen — nicht pro Ladung
        einzeln, sonst wuerden mehrere Notifications mit derselben ID sich
        gegenseitig ueberschreiben und nur die letzte waere sichtbar."""
        host = self._host
        pending_list = host.data.get("pending") or []
        if not pending_list:
            return
        en = self._en()
        if len(pending_list) == 1:
            p = pending_list[0]
            title = "External charge detected" if en else "Fremdladung erkannt"
            if en:
                message = (
                    f"+{p['delta_soc']}% ({p['soc_start']} → {p['soc_end']}%), "
                    f"~{round(p['energy_kwh'], 1)} kWh estimated. Enter kWh and price."
                )
            else:
                message = (
                    f"+{p['delta_soc']} % ({p['soc_start']} -> {p['soc_end']} %), "
                    f"~{round(p['energy_kwh'], 1)} kWh geschätzt. kWh und Preis eintragen."
                )
        else:
            if en:
                title = f"{len(pending_list)} external charges detected"
                lines = [
                    f"{i + 1}) +{p['delta_soc']}% ({p['soc_start']} → {p['soc_end']}%), "
                    f"~{round(p['energy_kwh'], 1)} kWh"
                    for i, p in enumerate(pending_list)
                ]
                message = f"{len(pending_list)} open external charges:\n" + "\n".join(lines) + "\nEnter kWh and price."
            else:
                title = f"{len(pending_list)} Fremdladungen erkannt"
                lines = [
                    f"{i + 1}) +{p['delta_soc']} % ({p['soc_start']} -> {p['soc_end']} %), "
                    f"~{round(p['energy_kwh'], 1)} kWh"
                    for i, p in enumerate(pending_list)
                ]
                message = f"{len(pending_list)} offene Fremdladungen:\n" + "\n".join(lines) + "\nkWh und Preis eintragen."

        await self._push(NOTIFY_EVENT_FREMDLADUNG, title, message)
        await self._persistent_notification(
            "create",
            {"notification_id": host._notify_tag, "title": title, "message": message},
        )

    async def _push(self, event_key: str, title: str, message: str) -> None:
        """Sendet eine Push-Benachrichtigung an die konfigurierten Notify-
        Entitaeten (moderne, entity-basierte Notify-Plattform), aber nur
        wenn event_key zu den in Schritt 4 ausgewaehlten Ereignissen gehoert
        (siehe const.py::NOTIFY_EVENTS) -- die persistent_notification im
        HA-Bereich "Benachrichtigungen" erscheint davon unabhaengig immer
        und wird von den Aufrufern separat erzeugt. KEIN data-Feld (Tag/
        Actions/persistent): notify.send_message akzeptiert bei dieser
        HA-Version nur message/title -- ein data-Feld liess den GESAMTEN
        Aufruf mit 400 Bad Request abbrechen, bevor ueberhaupt etwas
        verschickt wurde (weder Push noch Mail), siehe CHANGELOG."""
        host = self._host
        events = host._opt(CONF_NOTIFY_EVENTS, DEFAULT_NOTIFY_EVENTS)
        entities = host._opt(CONF_NOTIFY_ENTITIES)
        if event_key not in events or not entities:
            return
        payload = {"entity_id": entities, "title": title, "message": message}
        try:
            await host.hass.services.async_call("notify", "send_message", payload, blocking=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("notify.send_message fehlgeschlagen: %s", err)

    async def _notify_soc_threshold(self, threshold: int) -> None:
        """Push + persistent_notification, wenn der SoC waehrend eines
        laufenden Ladevorgangs threshold erreicht -- siehe
        _check_soc_thresholds()."""
        host = self._host
        en = self._en()
        title = f"{threshold}% SoC reached" if en else f"{threshold} % SoC erreicht"
        message = (
            f"Vehicle battery reached {threshold}%."
            if en else
            f"Fahrzeug-Akku hat {threshold} % erreicht."
        )
        await self._push(NOTIFY_EVENT_SOC_SCHWELLE, title, message)
        await self._persistent_notification(
            "create",
            {"notification_id": f"{host._notify_tag}_soc_{threshold}", "title": title, "message": message},
        )

    async def _notify_trip(self) -> None:
        """Analog _notify(): eine Benachrichtigung (eigene notification_id)
        fuer ALLE aktuell offenen Fahrten."""
        host = self._host
        pending_list = host.data.get("pending_trips") or []
        if not pending_list:
            return
        en = self._en()
        if len(pending_list) == 1:
            p = pending_list[0]
            if en:
                title = "Trip detected"
                message = f"{p['km']} km driven. Enter start/end location."
            else:
                title = "Fahrt erkannt"
                message = f"{p['km']} km gefahren. Start-/Zielort eintragen."
        else:
            lines = [f"{i + 1}) {p['km']} km" for i, p in enumerate(pending_list)]
            if en:
                title = f"{len(pending_list)} trips detected"
                message = f"{len(pending_list)} open trips:\n" + "\n".join(lines) + "\nEnter start/end location."
            else:
                title = f"{len(pending_list)} Fahrten erkannt"
                message = f"{len(pending_list)} offene Fahrten:\n" + "\n".join(lines) + "\nStart-/Zielort eintragen."

        await self._push(NOTIFY_EVENT_FAHRT, title, message)
        await self._persistent_notification(
            "create",
            {"notification_id": f"{host._notify_tag}_trip", "title": title, "message": message},
        )

    async def _dismiss_trip(self) -> None:
        host = self._host
        await self._persistent_notification(
            "dismiss",
            {"notification_id": f"{host._notify_tag}_trip"},
        )

    async def _notify_tankerkoenig_unavailable(self) -> None:
        """Dauerhafte Benachrichtigung, solange Tankerkoenig keinen einzigen
        gueltigen Preis fuer die gewaehlte Kraftstoffsorte liefert (siehe
        _wire_tankerkoenig_price()) -- der Kostenvergleich rechnet in der
        Zwischenzeit mit dem letzten bekannten bzw. festen Fallback-Preis
        weiter, statt auszufallen."""
        host = self._host
        en = self._en()
        title = "Tankerkönig unavailable" if en else "Tankerkönig nicht verfügbar"
        message = (
            "No valid fuel price could be read from any configured Tankerkönig "
            "station — the cost comparison keeps using the last known or fixed "
            "fallback fuel price instead."
            if en else
            "Von keiner konfigurierten Tankerkönig-Station konnte ein gültiger "
            "Kraftstoffpreis gelesen werden — der Kostenvergleich rechnet "
            "stattdessen mit dem letzten bekannten bzw. festen Fallback-Preis weiter."
        )
        await self._push(NOTIFY_EVENT_TANKERKOENIG, title, message)
        await self._persistent_notification(
            "create",
            {"notification_id": f"{host._notify_tag}_tankerkoenig", "title": title, "message": message},
        )

    async def _dismiss_tankerkoenig_unavailable(self) -> None:
        host = self._host
        await self._persistent_notification(
            "dismiss",
            {"notification_id": f"{host._notify_tag}_tankerkoenig"},
        )

    async def _persistent_notification(self, action: str, data: dict) -> None:
        """persistent_notification.create/.dismiss, best effort: eine fehlende
        Benachrichtigung darf nie die eigentliche Aktion (Ladung erfassen,
        Export, Erinnerung ...) abbrechen. Fehlt der Dienst (Integration
        "persistent_notification" deaktiviert), ist das nur eine Debug-Zeile;
        jeder andere Fehler (z.B. ein ungueltiger Payload nach einer Aenderung
        hier) steht als Warnung im Log statt still verschluckt zu werden."""
        host = self._host
        try:
            await host.hass.services.async_call("persistent_notification", action, data, blocking=False)
        except ServiceNotFound:
            _LOGGER.debug("persistent_notification.%s nicht verfuegbar", action)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("persistent_notification.%s fehlgeschlagen: %s", action, err)

    async def _dismiss(self) -> None:
        host = self._host
        await self._persistent_notification(
            "dismiss", {"notification_id": host._notify_tag},
        )
