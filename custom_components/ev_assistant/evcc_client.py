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
