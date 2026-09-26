"""Tests fuer das persistente Ereignisprotokoll (siehe
coordinator.py::_log_event()/async_export_event_log(), const.py::
EVENT_LOG_MAX_AGE_DAYS) -- Nutzerwunsch 2026-09-26: "logs, die alles
wiederspiegeln was zb zwei wochen lang passiert ist", "und einen restart
überleben", "wenn andere benutzer diese logs hochladen, können wir sie
auswerten"."""
import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="evlog1"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


async def test_log_event_haengt_eintrag_an(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog1")
    coordinator._log_event("test_kategorie", "test text")
    log = coordinator.data["event_log"]
    assert len(log) == 1
    assert log[0]["kategorie"] == "test_kategorie"
    assert log[0]["text"] == "test text"
    assert log[0]["ts"] == pytest.approx(dt_util.utcnow().timestamp(), abs=5)


async def test_log_event_kuerzt_zu_alte_eintraege(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog2")
    from custom_components.ev_assistant.const import EVENT_LOG_MAX_AGE_DAYS

    now = dt_util.utcnow().timestamp()
    # Ein Eintrag knapp ueber dem Limit (soll rausfallen) und einer knapp
    # darunter (soll bleiben) -- direkt vorbefuellt, um das Alter exakt zu
    # kontrollieren statt auf echtes Zeitvergehen waehrend des Tests zu warten.
    coordinator.data["event_log"] = [
        {"ts": now - (EVENT_LOG_MAX_AGE_DAYS * 86400 + 10), "kategorie": "alt", "text": "zu alt"},
        {"ts": now - (EVENT_LOG_MAX_AGE_DAYS * 86400 - 10), "kategorie": "jung", "text": "bleibt"},
    ]
    coordinator._log_event("neu", "frisch")
    log = coordinator.data["event_log"]
    kategorien = [e["kategorie"] for e in log]
    assert "alt" not in kategorien
    assert "jung" in kategorien
    assert "neu" in kategorien
    assert len(log) == 2


async def test_log_charge_erzeugt_event_log_eintrag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog3")
    await coordinator.async_simulate(32.0, 74.0)
    assert any(e["kategorie"] == "fremdladung_erkannt" for e in coordinator.data["event_log"])
    await coordinator.async_log_charge(kwh=18.9, price=0.55)
    assert any(e["kategorie"] == "fremdladung_bestaetigt" for e in coordinator.data["event_log"])


async def test_discard_erzeugt_event_log_eintrag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog4")
    await coordinator.async_simulate(32.0, 74.0)
    await coordinator.async_discard()
    assert any(e["kategorie"] == "fremdladung_verworfen" for e in coordinator.data["event_log"])


async def test_log_trip_erzeugt_event_log_eintraege(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog6")
    await coordinator.async_simulate_trip(12.5)
    assert any(e["kategorie"] == "fahrt_erkannt" for e in coordinator.data["event_log"])
    await coordinator.async_log_trip("Start", "Ziel")
    assert any(e["kategorie"] == "fahrt_bestaetigt" for e in coordinator.data["event_log"])


async def test_discard_trip_erzeugt_event_log_eintrag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog7")
    await coordinator.async_simulate_trip(8.0)
    await coordinator.async_discard_trip()
    assert any(e["kategorie"] == "fahrt_verworfen" for e in coordinator.data["event_log"])


async def test_urlaub_transition_wird_geloggt(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog8")
    # Erster Aufruf: kein Vorzustand bekannt -- kein Log-Eintrag, nur die
    # Baseline wird gesetzt (siehe _check_urlaub_transition()-Docstring).
    coordinator._urlaub_aktiv = lambda: False
    coordinator._check_urlaub_transition()
    assert not any(e["kategorie"].startswith("urlaub_") for e in coordinator.data.get("event_log", []))
    assert coordinator.data["urlaub_aktiv_last"] is False

    coordinator._urlaub_aktiv = lambda: True
    coordinator._check_urlaub_transition()
    assert any(e["kategorie"] == "urlaub_aktiviert" for e in coordinator.data["event_log"])

    coordinator._urlaub_aktiv = lambda: False
    coordinator._check_urlaub_transition()
    assert any(e["kategorie"] == "urlaub_beendet" for e in coordinator.data["event_log"])


async def test_export_event_log_schreibt_lesbare_datei(hass, coordinators, tmp_path):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evlog5")
    hass.config.config_dir = str(tmp_path)
    coordinator._log_event("fremdladung_erkannt", "SoC 32.0->74.0%, ~18.9 kWh, Quelle: soc")
    path = await coordinator.async_export_event_log()
    content = (tmp_path / "www" / f"ev_assistant_event_log_{coordinator.entry.entry_id}.txt").read_text(
        encoding="utf-8"
    )
    assert "fremdladung_erkannt: SoC 32.0->74.0%, ~18.9 kWh, Quelle: soc" in content
    assert path.endswith(f"ev_assistant_event_log_{coordinator.entry.entry_id}.txt")
