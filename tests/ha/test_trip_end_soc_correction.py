"""Tests fuer die nachtraegliche Fahrtende-SoC-Korrektur (siehe engine.
trip_end_soc_correction()/coordinator.py::_maybe_correct_last_trip_end_soc()).
Reine Entscheidungslogik (Schwelle/Fenster) ist bereits in tests/
test_engine.py abgedeckt -- hier nur die HA-Verdrahtung: Finden und
Aktualisieren der richtigen Fahrt (bestaetigt vs. noch offen), Baseline-
Neubuchung, Fortschreiben des Merkpostens fuer eine evtl. weitere,
unmittelbar folgende Korrektur."""
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="tesc1", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


def _seed_last_trip(coordinator, start_ts, end_ts, soc_end):
    coordinator.data["last_trip_start_ts"] = start_ts
    coordinator.data["last_trip_end_ts"] = end_ts
    coordinator.data["last_trip_end_soc"] = soc_end


async def test_correct_bestaetigte_fahrt_wird_korrigiert(hass, coordinators):
    """CONF_TRIP_AUTO_CONFIRM aktiv: die Fahrt steckt schon in "fahrten"
    mit gebuchter Baseline -- die Korrektur muss die alte Baseline abziehen
    und die neue wieder aufbuchen (analog async_edit_trip())."""
    from homeassistant.util import dt as dt_util

    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "tesc1", options={CONF_USABLE_KWH: 50.0})
    rec = {
        "start_ts": 1000.0, "end_ts": 1300.0, "km": 10.0,
        "soc_start": 30.0, "soc_end": 29.0, "delta_soc": -1.0,
        "verbrauch_kwh": 0.5, "erfasst_ts": 1300,
    }
    coordinator.data["fahrten"] = [rec]
    coordinator._apply_trip_baselines(rec, 1)
    weekday = dt_util.as_local(dt_util.utc_from_timestamp(1000.0)).date().weekday()
    _seed_last_trip(coordinator, 1000.0, 1300.0, 29.0)

    coordinator._maybe_correct_last_trip_end_soc(28.0, 1300.0 + 3600.0)

    fixed = coordinator.data["fahrten"][0]
    assert fixed["soc_end"] == 28.0
    assert fixed["delta_soc"] == -2.0
    assert fixed["verbrauch_kwh"] == 1.0  # 2% von 50 kWh
    assert coordinator.data["last_trip_end_soc"] == 28.0
    # Baseline wurde tatsaechlich neu gebucht (2% statt 1%), nicht nur das
    # Record-Dict veraendert.
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 1.0


async def test_correct_offene_fahrt_wird_direkt_nachgetragen(hass, coordinators):
    """CONF_TRIP_AUTO_CONFIRM aus: die Fahrt liegt noch in "pending_trips",
    keine Baseline gebucht -- direktes Nachtragen im Dict reicht."""
    coordinator, _ = await _make_coordinator(hass, coordinators, "tesc2")
    pend = {
        "start_ts": 1000.0, "end_ts": 1300.0, "km": 10.0,
        "soc_start": 30.0, "soc_end": 29.0, "delta_soc": -1.0,
    }
    coordinator.data["pending_trips"] = [pend]
    _seed_last_trip(coordinator, 1000.0, 1300.0, 29.0)

    coordinator._maybe_correct_last_trip_end_soc(28.0, 1300.0 + 3600.0)

    fixed = coordinator.data["pending_trips"][0]
    assert fixed["soc_end"] == 28.0
    assert fixed["delta_soc"] == -2.0
    assert coordinator.data["last_trip_end_soc"] == 28.0


async def test_correct_waehrend_aktiver_fahrt_ist_no_op(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "tesc3")
    pend = {"start_ts": 1000.0, "end_ts": 1300.0, "km": 10.0, "soc_start": 30.0, "soc_end": 29.0}
    coordinator.data["pending_trips"] = [pend]
    _seed_last_trip(coordinator, 1000.0, 1300.0, 29.0)
    coordinator._trip_detector._active = True  # simuliert eine gerade laufende neue Fahrt

    coordinator._maybe_correct_last_trip_end_soc(28.0, 1300.0 + 60.0)

    assert coordinator.data["pending_trips"][0]["soc_end"] == 29.0  # unveraendert


async def test_correct_zu_grosser_ruckgang_bleibt_unangetastet(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "tesc4")
    pend = {"start_ts": 1000.0, "end_ts": 1300.0, "km": 10.0, "soc_start": 30.0, "soc_end": 29.0}
    coordinator.data["pending_trips"] = [pend]
    _seed_last_trip(coordinator, 1000.0, 1300.0, 29.0)

    coordinator._maybe_correct_last_trip_end_soc(5.0, 1300.0 + 60.0)  # -24 Punkte, klar kein Nachzuegler

    assert coordinator.data["pending_trips"][0]["soc_end"] == 29.0


async def test_correct_ohne_vorherige_fahrt_ist_no_op(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "tesc5")
    coordinator._maybe_correct_last_trip_end_soc(28.0, 1000.0)  # keine Exception, einfach nichts zu tun
