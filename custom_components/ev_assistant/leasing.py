"""Leasing-Kilometerbudget: Kennzahlen und Schwellen-Benachrichtigungen.

Aus coordinator.py ausgelagert (Umbau vor der 1.0, siehe Issue #12). Der Zustand
(Cache, Fahrten-Version, Optionen) bleibt im Coordinator ("host"); diese Klasse
haelt keinen eigenen Zustand. Die oeffentlichen Methoden des Coordinators bestehen
unveraendert und rufen hierher durch.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from .const import (
    CONF_LEASING_END_DATUM,
    CONF_LEASING_INKL_KM,
    CONF_LEASING_PREIS_MEHR_KM,
    CONF_LEASING_PREIS_MINDER_KM,
    CONF_LEASING_START_DATUM,
    CONF_LEASING_START_KM,
    CONF_LEASING_TOLERANZ_MEHR_KM,
    CONF_LEASING_TOLERANZ_MINDER_KM,
    LEASING_KNAPP_SCHWELLE_PCT,
    LEASING_TOLERANZ_PCT,
    MILES_TO_KM,
    NOTIFY_EVENT_LEASING,
)
from .engine import leasing_status, rolling_km_per_day

if TYPE_CHECKING:
    from .coordinator import EvAssistantCoordinator


# Rolling-Fenster fuer das aktuelle Fahrtempo (siehe engine.py::
# rolling_km_per_day()), das leasing_stats() als "rollierende" Projektion
# neben die lineare Projektion seit Vertragsbeginn stellt -- kurz genug, um
# eine juengere Verhaltensaenderung (z.B. neuer Arbeitsweg) schneller
# abzubilden als der lineare Vertrags-Schnitt es koennte.
_LEASING_ROLLING_WINDOW_DAYS = 30
# Rangfolge fuer die Hysterese in _check_leasing_thresholds() -- je hoeher,
# desto schlechter der Status.
_LEASING_STATUS_RANK = {"im_budget": 0, "knapp": 1, "ueber": 2}


class Leasing:
    """Leasing-Budget fuer genau einen Coordinator (siehe Modul-Docstring)."""

    def __init__(self, host: EvAssistantCoordinator) -> None:
        self._host = host

    def leasing_stats(self) -> dict:
        """Leasing-Kilometerbudget (siehe engine.py::leasing_status()).
        Verwendet den ABSOLUTEN Kilometerstand (host.data["odo"], mit
        derselben odo_unit-Umrechnung wie _km_driven()) gegen den
        konfigurierten Vertrags-Start-km -- bewusst NICHT _km_driven()
        selbst, das nur seit der ev_assistant-Einrichtung zaehlt und damit
        fuer einen laufenden Leasingvertrag die falsche Referenz waere.
        Leeres dict, solange inkl_km/end_datum nicht konfiguriert sind
        (siehe build_leasing_schema()) -- macht das Feature komplett
        inaktiv, bis es eingerichtet ist (keine Sensoren mit Rauschen).
        Fehlen weitere Pflichtfelder (Start-km/-datum), liefert bereits
        engine.leasing_status() selbst ein leeres dict.

        Ergebnis wird zwischengespeichert (siehe _leasing_cache in
        __init__) -- ohne das wuerde sowohl LeasingKmVorRuecklaufSensor
        (native_value + extra_state_attributes) als auch
        _check_leasing_thresholds() dieselbe Berechnung (inkl.
        rolling_km_per_day() ueber das gesamte Fahrtenbuch) jeweils einzeln
        anstossen -- bis zu dreimal pro Update fuer denselben Wert."""
        host = self._host
        inkl_km = host._opt(CONF_LEASING_INKL_KM)
        end_datum = host._opt(CONF_LEASING_END_DATUM)
        if not inkl_km or not end_datum:
            return {}
        odo = host.data.get("odo")
        if odo is None:
            return {}
        odo_km = odo * MILES_TO_KM if host.data.get("odo_unit") == "mi" else odo
        start_km = host._opt(CONF_LEASING_START_KM)
        heute = dt_util.now().date().isoformat()
        cache_key = (host._fahrten_version, odo_km, heute, start_km, end_datum)
        if host._leasing_cache is not None and host._leasing_cache[0] == cache_key:
            return host._leasing_cache[1]
        fahrten = host.data.get("fahrten") or []
        rollierendes_tempo = rolling_km_per_day(fahrten, time.time(), _LEASING_ROLLING_WINDOW_DAYS)
        result = leasing_status(
            aktueller_km=odo_km,
            vertrag_start_km=start_km,
            vertrag_start_datum=host._opt(CONF_LEASING_START_DATUM),
            vertrag_end_datum=end_datum,
            inkl_gesamt_km=inkl_km,
            heute=heute,
            preis_mehr_km=host._opt(CONF_LEASING_PREIS_MEHR_KM),
            preis_minder_km=host._opt(CONF_LEASING_PREIS_MINDER_KM),
            toleranz_mehr_km=host._opt(CONF_LEASING_TOLERANZ_MEHR_KM),
            toleranz_minder_km=host._opt(CONF_LEASING_TOLERANZ_MINDER_KM),
            rollierendes_tempo_km_pro_tag=rollierendes_tempo,
            knapp_schwelle_pct=LEASING_KNAPP_SCHWELLE_PCT,
            toleranz_pct=LEASING_TOLERANZ_PCT,
        )
        host._leasing_cache = (cache_key, result)
        return result

    def _check_leasing_thresholds(self) -> None:
        """Benachrichtigung, wenn die (lineare) Leasing-Projektion erstmals
        "knapp" oder "ueber" erreicht -- Hysterese analog
        _check_soc_thresholds(): der bereits gemeldete Status wird
        persistiert (ueberlebt einen HA-Neustart) und erst erneut gemeldet,
        wenn eine SCHLECHTERE Stufe erreicht wird -- sonst wuerde eine
        Projektion, die knapp um die Schwelle pendelt, bei jeder Messung neu
        benachrichtigen. Der gespeicherte Zustand wird zurueckgesetzt,
        sobald sich die Vertrags-Identitaet (Start-km + End-Datum) aendert
        -- ein neuer/verlaengerter Vertrag verdient wieder eigene
        Benachrichtigungen ab "im_budget"."""
        host = self._host
        stats = self.leasing_stats()
        status = stats.get("status")
        if status is None:
            return
        identity = [host._opt(CONF_LEASING_START_KM), host._opt(CONF_LEASING_END_DATUM)]
        if host.data.get("leasing_notified_identity") != identity:
            host.data["leasing_notified_identity"] = identity
            host.data["leasing_notified_rank"] = 0
        worst_rank = host.data.get("leasing_notified_rank", 0)
        rank = _LEASING_STATUS_RANK.get(status, 0)
        if rank <= worst_rank:
            return
        host.data["leasing_notified_rank"] = rank
        if rank > 0:
            host.hass.async_create_task(self._notify_leasing(status, stats))

    async def _notify_leasing(self, status: str, stats: dict) -> None:
        """Push + persistent_notification, wenn die Leasing-Projektion
        "knapp" oder "ueber" erreicht -- siehe _check_leasing_thresholds()."""
        host = self._host
        en = host._en()
        if status == "ueber":
            title = "Leasing mileage budget exceeded" if en else "Leasing-Kilometerbudget ueberschritten"
        else:
            title = "Leasing mileage budget tight" if en else "Leasing-Kilometerbudget knapp"
        km_vor_ruecklauf = stats.get("km_vor_ruecklauf")
        if km_vor_ruecklauf is not None:
            message = (
                f"Linear projection is currently {km_vor_ruecklauf:+.0f} km vs. plan."
                if en else
                f"Die lineare Projektion liegt aktuell {km_vor_ruecklauf:+.0f} km gegenueber dem Soll."
            )
        else:
            message = "Check the leasing tab for details." if en else "Details siehe Leasing-Tab."
        await host._push(NOTIFY_EVENT_LEASING, title, message)
        await host._persistent_notification(
            "create",
            {"notification_id": f"{host._notify_tag}_leasing", "title": title, "message": message},
        )
