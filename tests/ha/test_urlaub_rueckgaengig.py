"""Tests fuer das Zuruecknehmen einer rueckwirkenden Urlaubs-Anwendung (siehe
coordinator.py::async_urlaub_rueckgaengig()): der Dienst urlaub_seit und das
Setzen von Urlaubstagen im Kalender entfernen Tageswerte aus den Profilen --
das muss sich wieder zurueckholen lassen, und es gibt einen Hinweis darauf
(Vorfall 2026-11-17: "Rueckwirkend" im Panel loeschte den heutigen Tag ohne
Warnung)."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="ur1"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    coordinator._notifications._persistent_notification = AsyncMock()
    return coordinator


def _heute():
    return dt_util.now().date()


def _mitternacht_ts(tag):
    return dt_util.as_local(datetime(tag.year, tag.month, tag.day)).timestamp()


def _seed_heute(c, kwh=19.0):
    heute = _heute()
    wd = str(heute.weekday())
    c.data["vehicle_discharge_weekday_days"] = {wd: [{"date": heute.isoformat(), "kwh": kwh}]}
    c.data["vehicle_discharge_counted_dates"] = []
    c.data["plug_window_today"] = {"date": heute.isoformat(), "urlaub": False, "abfahrten": []}
    return heute, wd


async def test_urlaub_seit_wird_zurueckgenommen(hass, coordinators):
    c = await _make_coordinator(hass, coordinators)
    heute, wd = _seed_heute(c)
    await c.async_apply_vehicle_discharge_urlaub_since(_mitternacht_ts(heute))
    assert c.data["vehicle_discharge_weekday_days"] == {}
    assert heute.isoformat() in c.data["vehicle_discharge_counted_dates"]
    assert c.data["plug_window_today"]["urlaub"] is True
    assert c.data["urlaub_rueckgaengig"]["quelle"] == "seit"

    result = await c.async_urlaub_rueckgaengig()
    assert result["wiederhergestellt"] >= 1
    assert c.data["vehicle_discharge_weekday_days"][wd] == [{"date": heute.isoformat(), "kwh": 19.0}]
    assert heute.isoformat() not in c.data["vehicle_discharge_counted_dates"]
    assert c.data["plug_window_today"]["urlaub"] is False
    assert c.data["urlaub_rueckgaengig"] is None


async def test_rueckgaengig_addiert_zu_neu_gebuchtem_wert_desselben_tages(hass, coordinators):
    from custom_components.ev_assistant.engine import append_recent_weekday_day

    c = await _make_coordinator(hass, coordinators, "ur2")
    heute, wd = _seed_heute(c, 19.0)
    await c.async_apply_vehicle_discharge_urlaub_since(_mitternacht_ts(heute))
    # nach der Anwendung wird heute weiter gebucht (neue Bestaetigung)
    c.data["vehicle_discharge_weekday_days"] = append_recent_weekday_day(
        c.data["vehicle_discharge_weekday_days"], heute.weekday(), heute.isoformat(), 1.5, 8
    )
    await c.async_urlaub_rueckgaengig()
    assert c.data["vehicle_discharge_weekday_days"][wd] == [{"date": heute.isoformat(), "kwh": 20.5}]


async def test_ohne_vorherige_anwendung_gibt_es_nichts_zurueckzunehmen(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "ur3")
    assert await c.async_urlaub_rueckgaengig() == {"wiederhergestellt": 0}


async def test_zweites_rueckgaengig_ist_wirkungslos(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "ur4")
    heute, wd = _seed_heute(c)
    await c.async_apply_vehicle_discharge_urlaub_since(_mitternacht_ts(heute))
    await c.async_urlaub_rueckgaengig()
    assert await c.async_urlaub_rueckgaengig() == {"wiederhergestellt": 0}
    assert c.data["vehicle_discharge_weekday_days"][wd] == [{"date": heute.isoformat(), "kwh": 19.0}]


async def test_kalender_zeitraum_wird_samt_profilwerten_zurueckgenommen(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "ur5")
    heute = _heute()
    gestern = heute - timedelta(days=1)
    c.data["vehicle_discharge_weekday_days"] = {
        str(gestern.weekday()): [{"date": gestern.isoformat(), "kwh": 7.5}]
    }
    c.data["house_weekday_days"] = {str(gestern.weekday()): [{"date": gestern.isoformat(), "kwh": 12.0}]}
    c.data["vehicle_discharge_counted_dates"] = []
    await c.async_set_urlaub_zeitraum(gestern, heute)
    assert c.data["vehicle_discharge_weekday_days"] == {}
    assert c.data["house_weekday_days"] == {}
    assert c.data["urlaub_zeitraeume"]
    assert c.data["urlaub_rueckgaengig"]["quelle"] == "zeitraum"

    await c.async_urlaub_rueckgaengig()
    wd = str(gestern.weekday())
    assert c.data["vehicle_discharge_weekday_days"][wd] == [{"date": gestern.isoformat(), "kwh": 7.5}]
    assert c.data["house_weekday_days"][wd] == [{"date": gestern.isoformat(), "kwh": 12.0}]
    assert c.data["urlaub_zeitraeume"] == []
    assert gestern.isoformat() not in c.data["vehicle_discharge_counted_dates"]


async def test_nach_der_anwendung_gibt_es_einen_hinweis_mit_tag_und_kwh(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "ur6")
    heute, _ = _seed_heute(c, 19.0)
    await c.async_apply_vehicle_discharge_urlaub_since(_mitternacht_ts(heute))
    action, payload = c._notifications._persistent_notification.await_args.args
    assert action == "create"
    assert heute.strftime("%d.%m.") in payload["message"]
    assert "19.0 kWh" in payload["message"]
    assert "urlaub_rueckgaengig" in payload["message"]

    await c.async_urlaub_rueckgaengig()
    action, payload2 = c._notifications._persistent_notification.await_args.args
    assert action == "dismiss"
    assert payload2["notification_id"] == payload["notification_id"]


async def test_ohne_aenderung_gibt_es_keinen_hinweis_und_keine_spur(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "ur7")
    c.data["plug_window_today"] = {"date": _heute().isoformat(), "urlaub": True, "abfahrten": []}
    await c.async_apply_vehicle_discharge_urlaub_since(_mitternacht_ts(_heute()))
    c._notifications._persistent_notification.assert_not_awaited()
    assert not c.data.get("urlaub_rueckgaengig")
