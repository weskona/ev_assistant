"""Isolierte Tests fuer die evcc_client.py-Schreibmethoden (Modus/Min-/
Ziel-SoC-Steuerung, siehe coordinator.py::_async_apply_evcc_mode_control()) --
kein hass/Coordinator noetig, nur ein selbstgebauter aiohttp.ClientSession-
Fake (keine zusaetzliche Test-Abhaengigkeit wie aioresponses).

Liegt in tests/ha/ statt tests/test_engine.py: evcc_client.py ist Teil der
HA-Verdrahtungsschicht (aiohttp, kein reines engine.py), braucht aber fuer
diese Tests kein echtes hass -- die async-Tests laufen trotzdem nur zuver-
laessig mit dem pytest-asyncio, das ueber pytest-homeassistant-custom-
component (siehe requirements_test.txt) bereitgestellt wird."""
import aiohttp

from custom_components.ev_assistant.evcc_client import EvccClient


class _FakeCtx:
    """Async-Context-Manager, wie ihn aiohttp.ClientSession.get()/post()
    zurueckgibt -- `outcome` ist entweder eine _FakeResponse (Erfolgsfall)
    oder eine Exception-Instanz (wird beim Verbindungsaufbau in
    __aenter__ geworfen, analog einem echten Timeout/Verbindungsfehler)."""

    def __init__(self, outcome):
        self._outcome = outcome

    async def __aenter__(self):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def __aexit__(self, *exc_info):
        return False


class _FakeResponse:
    def __init__(self, status: int, json_data=None):
        self.status = status
        self._json_data = json_data

    async def json(self):
        return self._json_data


class _FakeSession:
    """`outcomes`: dict URL -> Outcome (_FakeResponse oder Exception).
    Nicht konfigurierte URLs loesen einen AssertionError aus -- ein
    unerwarteter Call soll den Test hart fehlschlagen lassen, nicht still
    ignoriert werden."""

    def __init__(self, outcomes: dict):
        self._outcomes = outcomes
        self.calls: list[tuple[str, str]] = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return _FakeCtx(self._outcome_for(url))

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return _FakeCtx(self._outcome_for(url))

    def _outcome_for(self, url):
        if url not in self._outcomes:
            raise AssertionError(f"unerwarteter Call: {url}")
        return self._outcomes[url]


def _client(outcomes: dict) -> tuple[EvccClient, _FakeSession]:
    session = _FakeSession(outcomes)
    return EvccClient("http://evcc.local", session), session


# ----- async_probe_scope ----------------------------------------------------

async def test_probe_scope_loadpoint_form_erfolgreich_ohne_weiteren_versuch():
    client, session = _client({
        "http://evcc.local/api/state": _FakeResponse(200, {"loadpoints": [{"limitSoc": 80}]}),
        "http://evcc.local/api/loadpoints/1/limitsoc/80": _FakeResponse(200),
    })
    result = await client.async_probe_scope(1, "mein_auto", "limitsoc", "limitSoc")
    assert result == "loadpoint"
    post_calls = [url for method, url in session.calls if method == "POST"]
    assert post_calls == ["http://evcc.local/api/loadpoints/1/limitsoc/80"]


async def test_probe_scope_loadpoint_404_faellt_zurueck_auf_vehicle():
    client, session = _client({
        "http://evcc.local/api/state": _FakeResponse(200, {"loadpoints": [{"minSoc": 40}]}),
        "http://evcc.local/api/loadpoints/1/minsoc/40": _FakeResponse(404),
        "http://evcc.local/api/vehicles/mein_auto/minsoc/40": _FakeResponse(200),
    })
    result = await client.async_probe_scope(1, "mein_auto", "minsoc", "minSoc")
    assert result == "vehicle"


async def test_probe_scope_beide_formen_schlagen_fehl_gibt_none():
    client, _ = _client({
        "http://evcc.local/api/state": _FakeResponse(200, {"loadpoints": [{"limitSoc": 80}]}),
        "http://evcc.local/api/loadpoints/1/limitsoc/80": _FakeResponse(404),
        "http://evcc.local/api/vehicles/mein_auto/limitsoc/80": _FakeResponse(501),
    })
    result = await client.async_probe_scope(1, "mein_auto", "limitsoc", "limitSoc")
    assert result is None


async def test_probe_scope_kein_wert_im_state_gibt_none_ohne_post():
    client, session = _client({
        "http://evcc.local/api/state": _FakeResponse(200, {"loadpoints": [{}]}),
    })
    result = await client.async_probe_scope(1, "mein_auto", "limitsoc", "limitSoc")
    assert result is None
    assert all(method == "GET" for method, _ in session.calls)


async def test_probe_scope_minsoc_und_limitsoc_koennen_unterschiedliche_scopes_ergeben():
    """Regression fuer die reale evcc-0.314.5-Situation: limitSoc bleibt
    ueber den Loadpoint schreibbar, minSoc nicht mehr (nur noch ueber das
    Fahrzeug) -- ein gemeinsamer Scope fuer beide waere hier falsch."""
    client, _ = _client({
        "http://evcc.local/api/state": _FakeResponse(200, {"loadpoints": [{"limitSoc": 80, "minSoc": 40}]}),
        "http://evcc.local/api/loadpoints/1/limitsoc/80": _FakeResponse(200),
        "http://evcc.local/api/loadpoints/1/minsoc/40": _FakeResponse(404),
        "http://evcc.local/api/vehicles/mein_auto/minsoc/40": _FakeResponse(200),
    })
    limit_scope = await client.async_probe_scope(1, "mein_auto", "limitsoc", "limitSoc")
    min_scope = await client.async_probe_scope(1, "mein_auto", "minsoc", "minSoc")
    assert limit_scope == "loadpoint"
    assert min_scope == "vehicle"


# ----- async_set_mode/async_set_min_soc/async_set_limit_soc ---------------

async def test_async_set_mode_erfolgreich():
    client, _ = _client({"http://evcc.local/api/loadpoints/1/mode/pv": _FakeResponse(200)})
    assert await client.async_set_mode(1, "pv") is True


async def test_async_set_mode_http_fehler_gibt_false():
    client, _ = _client({"http://evcc.local/api/loadpoints/1/mode/now": _FakeResponse(500)})
    assert await client.async_set_mode(1, "now") is False


async def test_async_set_mode_verbindungsfehler_gibt_false():
    client, _ = _client({
        "http://evcc.local/api/loadpoints/1/mode/pv": aiohttp.ClientConnectionError("boom"),
    })
    assert await client.async_set_mode(1, "pv") is False


async def test_async_set_min_soc_loadpoint_scope():
    client, session = _client({"http://evcc.local/api/loadpoints/1/minsoc/40": _FakeResponse(200)})
    assert await client.async_set_min_soc(1, None, "loadpoint", 40) is True
    assert session.calls == [("POST", "http://evcc.local/api/loadpoints/1/minsoc/40")]


async def test_async_set_min_soc_vehicle_scope():
    client, session = _client({"http://evcc.local/api/vehicles/mein_auto/minsoc/40": _FakeResponse(200)})
    assert await client.async_set_min_soc(1, "mein_auto", "vehicle", 40) is True
    assert session.calls == [("POST", "http://evcc.local/api/vehicles/mein_auto/minsoc/40")]


async def test_async_set_limit_soc_loadpoint_scope():
    client, session = _client({"http://evcc.local/api/loadpoints/1/limitsoc/90": _FakeResponse(200)})
    assert await client.async_set_limit_soc(1, None, "loadpoint", 90) is True
    assert session.calls == [("POST", "http://evcc.local/api/loadpoints/1/limitsoc/90")]


async def test_async_set_limit_soc_vehicle_scope():
    client, session = _client({"http://evcc.local/api/vehicles/mein_auto/limitsoc/90": _FakeResponse(200)})
    assert await client.async_set_limit_soc(1, "mein_auto", "vehicle", 90) is True
    assert session.calls == [("POST", "http://evcc.local/api/vehicles/mein_auto/limitsoc/90")]


async def test_post_loggt_warning_bei_http_fehler(caplog):
    client, _ = _client({"http://evcc.local/api/loadpoints/1/mode/now": _FakeResponse(503)})
    with caplog.at_level("WARNING"):
        result = await client.async_set_mode(1, "now")
    assert result is False
    assert any("HTTP 503" in r.message for r in caplog.records)
