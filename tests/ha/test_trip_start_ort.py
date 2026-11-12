"""Startort-Vorschlag beim Fahrtbeginn (#95): der Endort der zeitlich letzten
erfassten Fahrt statt der aktuellen Personenzone, die bei verzoegerten
Meldungen schon nicht mehr stimmen kann. Ohne Endort wie bisher die Zone.
Die reine Auswahl steckt in tests/test_engine.py (last_trip_end_ort) -- hier
nur die Verdrahtung beim Idle->Aktiv-Uebergang in _run_trip_detection()."""
from unittest.mock import patch

from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _coordinator(hass, coordinators, fahrten=None, pending=None, zone="Zone-jetzt"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="tso1")
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    coordinator.data["fahrten"] = fahrten or []
    coordinator.data["pending_trips"] = pending or []
    coordinator._person_zone = zone
    return coordinator


async def _start_trip(coordinator):
    """Erst Ruhe (Anker), dann Odometer-Anstieg = Fahrtbeginn."""
    with patch.object(coordinator, "_odo_km", return_value=1000.0):
        await coordinator._run_trip_detection()
    with patch.object(coordinator, "_odo_km", return_value=1001.0):
        await coordinator._run_trip_detection()
    assert coordinator._trip_detector.active


async def test_startort_ist_endort_der_letzten_fahrt(hass, coordinators):
    c = await _coordinator(
        hass, coordinators,
        fahrten=[{"start_ts": 100.0, "end_ts": 200.0, "end_ort": "Zuhause"}],
        zone="Unterwegs-Zone",
    )
    await _start_trip(c)
    assert c._trip_start_zone == "Zuhause"
    assert c.data["trip_start_zone"] == "Zuhause"


async def test_ohne_endort_bleibt_die_personenzone(hass, coordinators):
    c = await _coordinator(hass, coordinators, fahrten=[], zone="Buero")
    await _start_trip(c)
    assert c._trip_start_zone == "Buero"
    assert c.data["trip_start_zone"] == "Buero"


async def test_letzte_fahrt_mit_leerem_endort_faellt_auf_die_zone_zurueck(hass, coordinators):
    c = await _coordinator(
        hass, coordinators,
        fahrten=[
            {"start_ts": 100.0, "end_ts": 200.0, "end_ort": "Altort"},
            {"start_ts": 300.0, "end_ts": 400.0, "end_ort": ""},
        ],
        zone="Buero",
    )
    await _start_trip(c)
    assert c._trip_start_zone == "Buero"


async def test_offene_fahrt_liefert_ihren_endort_vorschlag(hass, coordinators):
    c = await _coordinator(
        hass, coordinators,
        fahrten=[{"start_ts": 100.0, "end_ts": 200.0, "end_ort": "Buero"}],
        pending=[{"start_ts": 300.0, "end_ts": 400.0, "end_ort_vorschlag": "Supermarkt"}],
        zone="Zone-jetzt",
    )
    await _start_trip(c)
    assert c._trip_start_zone == "Supermarkt"


async def test_vorschlag_landet_in_der_offenen_fahrt(hass, coordinators):
    """Der Startort-Vorschlag der abgeschlossenen Fahrt ist der beim
    Fahrtbeginn eingefrorene Wert, nicht die Zone beim Fahrtende."""
    c = await _coordinator(
        hass, coordinators,
        fahrten=[{"start_ts": 100.0, "end_ts": 200.0, "end_ort": "Zuhause"}],
        zone="Unterwegs-Zone",
    )
    await _start_trip(c)
    c._person_zone = "Ziel-Zone"
    # Fahrtende: Standzeit ueber idle_timeout_s ohne Bewegung
    import time as _time

    with patch.object(c, "_odo_km", return_value=1001.0), patch(
        "custom_components.ev_assistant.coordinator.time.time", return_value=_time.time() + 100000
    ):
        await c._run_trip_detection()
    pend = (c.data.get("pending_trips") or [])[-1:] or (c.data.get("fahrten") or [])[-1:]
    assert pend, "Fahrt wurde nicht abgeschlossen"
    rec = pend[0]
    assert rec.get("start_ort_vorschlag", rec.get("start_ort")) == "Zuhause"
