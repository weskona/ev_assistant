"""Minimaler REST-Client fuer das evcc-Addon selbst.

Ersetzt die fruehere evcc_intg-Abhaengigkeit: evcc exponiert `/api/state`
(Site- und Loadpoint-Live-Daten, Statistiken) und `/api/sessions` (komplettes
Ladelogbuch, ohne Query-Filter) direkt und ohne Authentifizierung. Kein
Websocket noetig -- Polling reicht fuer die Zwecke von ev_assistant.
"""
from __future__ import annotations

import logging

import aiohttp

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=5)


class EvccClient:
    """Liest `/api/state` und `/api/sessions` vom evcc-Addon.

    Gibt bei jedem Fehler (Timeout, Verbindungsfehler, ungueltiges JSON)
    `None` bzw. eine leere Liste zurueck statt zu werfen -- passt zum
    "graceful degrade"-Muster, das der Rest von ev_assistant fuer optionale
    Datenquellen verwendet (siehe coordinator.py).
    """

    def __init__(self, host: str, session: aiohttp.ClientSession) -> None:
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        self._host = host.rstrip("/")
        self._session = session

    async def async_get_state(self) -> dict | None:
        return await self._get_json(f"{self._host}/api/state")

    async def async_get_sessions(self) -> list:
        data = await self._get_json(f"{self._host}/api/sessions")
        return data if isinstance(data, list) else []

    async def _get_json(self, url: str):
        try:
            async with self._session.get(url, timeout=_TIMEOUT, ssl=False) as resp:
                if resp.status != 200:
                    _LOGGER.debug("evcc_client: %s -> HTTP %s", url, resp.status)
                    return None
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.debug("evcc_client: %s -> %s: %s", url, type(err).__name__, err)
            return None

    async def async_probe_scope(
        self, loadpoint_id: int, vehicle_name: str | None, prop: str, state_field: str
    ) -> str | None:
        """Ermittelt einmalig, ob diese evcc-Instanz eine bestimmte
        Steuer-Eigenschaft (`prop`, z.B. "minsoc"/"limitsoc") ueber den
        Loadpoint oder ueber das Fahrzeug setzt -- unabhaengig je Eigenschaft
        aufzurufen, NICHT einmal fuer beide gemeinsam: neuere evcc-Versionen
        (ab ca. 0.13x) haben minSoc/targetSoc vom Loadpoint auf das Fahrzeug
        verschoben, aber (Stand 0.314.5) NICHT symmetrisch -- limitSoc bleibt
        weiterhin auch ueber den Loadpoint schreibbar, minSoc nicht mehr. Ein
        gemeinsamer Scope fuer beide Eigenschaften waere also falsch.

        Liest den aktuellen Wert aus /api/state (`state_field`, z.B.
        "limitSoc") und schreibt IHN SELBST zurueck -- bei Erfolg aendert
        sich am evcc-Zustand nichts (idempotent), bei Nichtvorhandensein der
        Endpunkt-Form schlaegt die Anfrage fehl (404/501). Reihenfolge:
        loadpoint zuerst (falls noch unterstuetzt), dann vehicle. None, wenn
        beide Formen fehlschlagen (z.B. kein `state_field` im State) -- der
        Aufrufer deaktiviert die Steuerung dieser einen Eigenschaft dann mit
        einer Warnung, die andere(n) laufen unabhaengig davon weiter."""
        state = await self.async_get_state()
        if state is None:
            return None
        loadpoints = state.get("loadpoints") or []
        loadpoint = loadpoints[loadpoint_id - 1] if 0 < loadpoint_id <= len(loadpoints) else None
        current = (loadpoint or {}).get(state_field)
        if current is None:
            return None
        if await self._post(f"{self._host}/api/loadpoints/{loadpoint_id}/{prop}/{int(current)}"):
            return "loadpoint"
        if vehicle_name and await self._post(f"{self._host}/api/vehicles/{vehicle_name}/{prop}/{int(current)}"):
            return "vehicle"
        return None

    async def async_set_mode(self, loadpoint_id: int, mode: str) -> bool:
        return await self._post(f"{self._host}/api/loadpoints/{loadpoint_id}/mode/{mode}")

    async def async_set_min_soc(self, loadpoint_id: int, vehicle_name: str | None, scope: str, soc: int) -> bool:
        url = (
            f"{self._host}/api/loadpoints/{loadpoint_id}/minsoc/{soc}" if scope == "loadpoint"
            else f"{self._host}/api/vehicles/{vehicle_name}/minsoc/{soc}"
        )
        return await self._post(url)

    async def async_set_limit_soc(self, loadpoint_id: int, vehicle_name: str | None, scope: str, soc: int) -> bool:
        url = (
            f"{self._host}/api/loadpoints/{loadpoint_id}/limitsoc/{soc}" if scope == "loadpoint"
            else f"{self._host}/api/vehicles/{vehicle_name}/limitsoc/{soc}"
        )
        return await self._post(url)

    async def _post(self, url: str) -> bool:
        """Wie _get_json(), aber fuer Schreibzugriffe -- POST, nicht PUT:
        evccs REST-API (Stand 0.314.5) erwartet POST fuer alle
        Steuer-Endpunkte unter /api/loadpoints/*/vehicles/* (PUT liefert dort
        404). Fehler werden mit _LOGGER.warning statt .debug geloggt: ein
        fehlgeschlagener Schreibversuch einer aktiven Steuerungsentscheidung
        ist ein Vorfall, der sichtbar sein soll, anders als eine (haeufige,
        erwartete) Leseanfrage waehrend evcc kurzzeitig nicht erreichbar
        ist."""
        try:
            async with self._session.post(url, timeout=_TIMEOUT, ssl=False) as resp:
                if resp.status != 200:
                    _LOGGER.warning("evcc_client: POST %s -> HTTP %s", url, resp.status)
                    return False
                return True
        except (aiohttp.ClientError, TimeoutError) as err:
            _LOGGER.warning("evcc_client: POST %s -> %s: %s", url, type(err).__name__, err)
            return False
