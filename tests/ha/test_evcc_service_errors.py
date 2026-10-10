"""Fehlerfaelle der evcc-Schreib-Services (set_evcc_charge_plan,
..._range_km, clear_evcc_charge_plan, set_evcc_manual_mode): sie enden nicht
mehr still "erfolgreich", sondern werfen mit konkretem Grund
(glow-dashboard#19, siehe __init__.py::_raise_if_evcc_blocked()). Die
internen Aufrufer (zyklische Modus-Steuerung) behalten ihr Verhalten -- siehe
die letzten Tests."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

PLAN = {"target_soc": 80, "target_time": 1_900_000_000.0}


@pytest.fixture(autouse=True)
async def _entries_entladen(hass):
    """Nach jedem Test alle ev_assistant-Eintraege entladen (Timer/Listener),
    sonst meldet pytest-homeassistant verbliebene Timer."""
    yield
    from custom_components.ev_assistant.const import DOMAIN

    for entry in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def _setup(hass, entry_id, options=None, mit_evcc=True):
    """Richtet einen Eintrag OHNE evcc_host ein (kein echter Netzwerkzugriff,
    kein Client) und haengt bei `mit_evcc` einen gemockten evcc-Client an --
    so ist evcc "konfiguriert", ohne dass der Test je ins Netz geht."""
    from custom_components.ev_assistant.const import (
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        DOMAIN,
    )

    data = {
        CONF_VEHICLE_HERSTELLER: "Peugeot",
        CONF_VEHICLE_MODELL: "eRifter",
        CONF_SOC_ENTITY: "sensor.test_soc",
        CONF_USABLE_KWH: 50.0,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if mit_evcc:
        client = AsyncMock()
        client.async_set_vehicle_plan_soc = AsyncMock(return_value=True)
        client.async_clear_vehicle_plan_soc = AsyncMock(return_value=True)
        client.async_set_mode = AsyncMock(return_value=True)
        client.async_get_state = AsyncMock(return_value=None)
        coordinator._evcc_client = client
    return entry, coordinator


async def _call(hass, entry, service, data=None):
    from custom_components.ev_assistant.const import DOMAIN

    return await hass.services.async_call(
        DOMAIN, service, {"config_entry_id": entry.entry_id, **(data or {})}, blocking=True,
    )


async def test_kein_treffer_nennt_erwarteten_namen_und_evcc_titel(hass):
    entry, coordinator = await _setup(hass, "svc1")
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "Tesla Model 3"}}, "loadpoints": [{}]}
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, entry, "set_evcc_charge_plan", PLAN)
    msg = str(err.value)
    assert "Peugeot eRifter" in msg and "Tesla Model 3" in msg
    # Sprachunabhaengig: die Meldung nennt die anzugleichende Option.
    assert "Fahrzeugname in evcc" in msg or "Vehicle name in evcc" in msg
    assert "{" not in msg  # keine unaufgeloesten Platzhalter
    coordinator._evcc_client.async_set_vehicle_plan_soc.assert_not_called()


async def test_mehrdeutig_nennt_kandidaten(hass):
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    entry, coordinator = await _setup(hass, "svc2", options={CONF_EVCC_VEHICLE_NAME: "e-Rifter"})
    coordinator._evcc_state = {
        "vehicles": {"db:1": {"title": "Peugeot e-Rifter"}, "db:2": {"title": "Opel Combo e-Rifter"}},
        "loadpoints": [{}],
    }
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, entry, "clear_evcc_charge_plan")
    assert "Peugeot e-Rifter" in str(err.value) and "Opel Combo e-Rifter" in str(err.value)


async def test_evcc_ohne_fahrzeuge_wirft_eigene_meldung(hass):
    entry, coordinator = await _setup(hass, "svc3")
    coordinator._evcc_state = {"vehicles": {}, "loadpoints": [{}]}
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, entry, "set_evcc_charge_plan", PLAN)
    assert "Peugeot eRifter" in str(err.value)
    assert "{" not in str(err.value)


async def test_evcc_nicht_konfiguriert(hass):
    entry, _ = await _setup(hass, "svc4", mit_evcc=False)
    with pytest.raises(ServiceValidationError) as err:
        await _call(hass, entry, "set_evcc_charge_plan", PLAN)
    assert "evcc" in str(err.value)


async def test_evcc_nicht_erreichbar_ist_homeassistanterror(hass):
    entry, coordinator = await _setup(hass, "svc5")
    coordinator._evcc_state = None
    coordinator.data["evcc_reachable_last"] = False
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, entry, "set_evcc_charge_plan", PLAN)
    assert not isinstance(err.value, ServiceValidationError)


async def test_evcc_state_noch_nicht_da_ist_homeassistanterror(hass):
    entry, coordinator = await _setup(hass, "svc6")
    coordinator._evcc_state = None
    coordinator.data["evcc_reachable_last"] = None
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, entry, "clear_evcc_charge_plan")
    assert not isinstance(err.value, ServiceValidationError)


async def test_evcc_lehnt_ab_wirft_homeassistanterror(hass):
    entry, coordinator = await _setup(hass, "svc7")
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    coordinator._evcc_client.async_set_vehicle_plan_soc = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError) as err:
        await _call(hass, entry, "set_evcc_charge_plan", PLAN)
    assert not isinstance(err.value, ServiceValidationError)


async def test_erfolg_wirft_nicht_und_schreibt_mit_evcc_schluessel(hass):
    entry, coordinator = await _setup(hass, "svc8")
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "Peugeot e-Rifter"}}, "loadpoints": [{}]}
    await _call(hass, entry, "set_evcc_charge_plan", PLAN)
    assert coordinator._evcc_client.async_set_vehicle_plan_soc.await_args.args[0] == "db:8"


async def test_range_km_ohne_verbrauchswert_wirft_validierungsfehler(hass):
    entry, coordinator = await _setup(hass, "svc9")
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    coordinator._current_consumption_estimate_kwh_per_100km = lambda: None
    with pytest.raises(ServiceValidationError):
        await _call(hass, entry, "set_evcc_charge_plan_range_km", {"target_range_km": 200.0, "target_time": 1_900_000_000.0})


async def test_manual_mode_ohne_loadpoint_wirft_validierungsfehler(hass):
    entry, coordinator = await _setup(hass, "svc10")
    coordinator._evcc_state = {"vehicles": {}, "loadpoints": []}
    with pytest.raises(ServiceValidationError):
        await _call(hass, entry, "set_evcc_manual_mode", {"mode": "now"})


async def test_manual_mode_abgelehnt_wirft_homeassistanterror(hass):
    entry, coordinator = await _setup(hass, "svc11")
    coordinator._evcc_state = {"vehicles": {}, "loadpoints": [{}]}
    coordinator._evcc_client.async_set_mode = AsyncMock(return_value=False)
    with pytest.raises(HomeAssistantError):
        await _call(hass, entry, "set_evcc_manual_mode", {"mode": "now"})


async def test_clear_manual_mode_kann_nicht_fehlschlagen(hass):
    entry, coordinator = await _setup(hass, "svc12", mit_evcc=False)
    await _call(hass, entry, "clear_evcc_manual_mode")  # darf nicht werfen


async def test_interne_abfragen_werfen_nie(hass):
    """Die zyklische Modus-Steuerung benutzt _evcc_vehicle_api_key() und das
    Zuordnungs-Logging -- beides darf bei Nicht-Treffer nur None/loggen."""
    entry, coordinator = await _setup(hass, "svc13")
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "Tesla Model 3"}}, "loadpoints": [{}]}
    assert coordinator._evcc_vehicle_api_key() is None
    reason, match = coordinator._evcc_vehicle_resolution()
    assert reason == "kein_treffer"
    coordinator._note_evcc_vehicle_resolution(reason, match, user_triggered=False)  # darf nicht werfen


async def test_hintergrund_logging_nur_einmal_je_kombination(hass, caplog):
    entry, coordinator = await _setup(hass, "svc14")
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "Tesla Model 3"}}, "loadpoints": [{}]}
    reason, match = coordinator._evcc_vehicle_resolution()
    caplog.clear()
    for _ in range(3):
        coordinator._note_evcc_vehicle_resolution(reason, match, user_triggered=False)
    assert sum("Zuordnung fehlgeschlagen" in r.message for r in caplog.records) == 1
    # Service-Aufruf (nutzergetriggert) loggt dagegen jedes Mal.
    caplog.clear()
    for _ in range(2):
        coordinator._note_evcc_vehicle_resolution(reason, match, user_triggered=True)
    assert sum("Zuordnung fehlgeschlagen" in r.message for r in caplog.records) == 2
    log = [e for e in coordinator.data.get("event_log", []) if e.get("kategorie") == "evcc_fahrzeug_nicht_zugeordnet"]
    assert len(log) == 1
    assert "Peugeot eRifter" in log[0]["text"] and "Tesla Model 3" in log[0]["text"]
    # Wieder zugeordnet -> Merker zurueck, ein Ereignis, danach wieder neu loggbar.
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    reason, match = coordinator._evcc_vehicle_resolution()
    assert reason == "ok"
    coordinator._note_evcc_vehicle_resolution(reason, match, user_triggered=False)
    assert coordinator._evcc_vehicle_problem_sig is None
    assert any(e.get("kategorie") == "evcc_fahrzeug_zugeordnet" for e in coordinator.data["event_log"])


def test_exceptions_uebersetzungen_vollstaendig_und_platzhalter_aufloesbar():
    """Alle Fehlertexte existieren in strings.json/de.json/en.json und nutzen
    nur Platzhalter, die _raise_if_evcc_blocked() auch liefert (expected/
    titles) -- sonst stuende im Fehlerdialog ein unaufgeloester Platzhalter."""
    import json
    import pathlib
    import re

    basis = pathlib.Path(__file__).resolve().parents[2] / "custom_components" / "ev_assistant"
    erwartet = {
        "evcc_not_configured", "evcc_not_reachable", "evcc_state_pending", "evcc_vehicle_no_match",
        "evcc_vehicle_ambiguous", "evcc_no_vehicles", "evcc_loadpoint_not_found", "range_no_consumption",
        "evcc_write_rejected",
    }
    for datei in ("strings.json", "translations/de.json", "translations/en.json"):
        block = json.loads((basis / datei).read_text(encoding="utf-8"))["exceptions"]
        assert set(block) == erwartet, datei
        for key, eintrag in block.items():
            platzhalter = set(re.findall(r"{(\w+)}", eintrag["message"]))
            assert platzhalter <= {"expected", "titles"}, (datei, key, platzhalter)
