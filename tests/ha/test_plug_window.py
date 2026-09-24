"""Tests fuer das Steck-Zeitfenster-Beobachtungsfeature (siehe
coordinator.py::_update_plug_window()/_finalize_plug_window_day()/
plug_window_profile()) -- Nutzerwunsch 2026-09-23: "wäre für das
nutzungsprofil nicht auch die zeiten wann und wie lange am tag das auto
angeschlossen ist an die wallbox sinnvoll ... um zu erkennen wie das auto
zuhause ist und wann fenster zum laden entstehen", explizit "erstmal nur
zur beobachtung. steckersignal kommt von evcc" -- Quelle ist also evccs
Ladepunkt-Feld "connected", NICHT CONF_PLUG_ENTITY. Reine Sichtbarkeit,
kein Einfluss auf die Modus-/SoC-Steuerung."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="pw1"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


async def test_update_plug_window_ohne_verbindung_legt_leeren_tag_an(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "pw1")
    coordinator._evcc_state = {"loadpoints": [{"connected": False}]}
    coordinator._update_plug_window()
    today = coordinator.data["plug_window_today"]
    assert today["date"] == dt_util.now().date().isoformat()
    assert today["connected_seconds"] == 0.0
    assert today["erster_connect"] is None
    assert today["letzter_disconnect"] is None
    assert coordinator.data["plug_window_prev_connected"] is False


async def test_update_plug_window_verbunden_erhoeht_sekunden_und_setzt_ersten_connect(hass, coordinators):
    import custom_components.ev_assistant.coordinator as coordinator_module

    coordinator, _ = await _make_coordinator(hass, coordinators, "pw2")
    coordinator._evcc_state = {"loadpoints": [{"connected": True}]}
    coordinator._update_plug_window()
    coordinator._update_plug_window()
    today = coordinator.data["plug_window_today"]
    assert today["connected_seconds"] == round(2 * coordinator_module._EVCC_POLL_INTERVAL_S, 1)
    assert today["erster_connect"] == dt_util.now().strftime("%H:%M")
    assert today["letzter_disconnect"] is None


async def test_update_plug_window_disconnect_flanke_setzt_letzten_disconnect(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "pw3")
    coordinator._evcc_state = {"loadpoints": [{"connected": True}]}
    coordinator._update_plug_window()
    coordinator._evcc_state = {"loadpoints": [{"connected": False}]}
    coordinator._update_plug_window()
    today = coordinator.data["plug_window_today"]
    assert today["letzter_disconnect"] == dt_util.now().strftime("%H:%M")
    connected_seconds_nach_disconnect = today["connected_seconds"]

    # Weiterer Poll waehrend weiterhin nicht verbunden -- KEIN erneuter
    # "Flanken"-Trigger, letzter_disconnect bleibt unveraendert, keine
    # zusaetzlichen Sekunden werden gezaehlt.
    coordinator._update_plug_window()
    today = coordinator.data["plug_window_today"]
    assert today["letzter_disconnect"] == dt_util.now().strftime("%H:%M")
    assert today["connected_seconds"] == connected_seconds_nach_disconnect


async def test_update_plug_window_ohne_loadpoint_gilt_als_nicht_verbunden(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "pw4")
    coordinator._evcc_state = {"loadpoints": []}
    coordinator._update_plug_window()
    assert coordinator.data["plug_window_today"]["connected_seconds"] == 0.0
    assert coordinator.data["plug_window_prev_connected"] is False


async def test_finalize_plug_window_day_bucht_ins_sliding_window_bei_datumswechsel(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "pw5")
    gestern = dt_util.now().date() - timedelta(days=1)
    coordinator.data["plug_window_today"] = {
        "date": gestern.isoformat(), "connected_seconds": 3600.0 * 8,
        "erster_connect": "18:00", "letzter_disconnect": "02:00",
    }
    coordinator._evcc_state = {"loadpoints": [{"connected": False}]}
    coordinator._update_plug_window()

    weekday_days = coordinator.data["plug_window_weekday_days"]
    eintrag = weekday_days[str(gestern.weekday())][0]
    assert eintrag == {
        "date": gestern.isoformat(), "stunden": 8.0,
        "erster_connect": "18:00", "letzter_disconnect": "02:00",
    }
    # "heute" beginnt frisch bei 0.
    heute = coordinator.data["plug_window_today"]
    assert heute["date"] == dt_util.now().date().isoformat()
    assert heute["connected_seconds"] == 0.0


async def test_plug_window_profile_durchschnitt_je_wochentag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "pw6")
    coordinator.data["plug_window_weekday_days"] = {
        "2": [
            {"date": "2026-09-01", "stunden": 8.0, "erster_connect": "18:00", "letzter_disconnect": "07:00"},
            {"date": "2026-09-08", "stunden": 10.0, "erster_connect": "17:00", "letzter_disconnect": "07:30"},
        ],
    }
    assert coordinator.plug_window_profile() == {2: 9.0}


async def test_plug_window_profile_ohne_daten_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "pw7")
    assert coordinator.plug_window_profile() is None
