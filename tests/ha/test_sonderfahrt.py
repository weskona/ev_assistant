"""Tests fuer async_set_sonderfahrt(): eine einzelne Fahrt faellt aus den
Wochentags-Profilen, der uebrige Tag bleibt (siehe coordinator.py)."""
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="sf1"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


def _add_trip(coordinator, erfasst_ts, kwh, km, start_ts=None):
    rec = {
        "erfasst_ts": erfasst_ts,
        "start_ts": start_ts if start_ts is not None else dt_util.now().timestamp(),
        "end_ts": (start_ts if start_ts is not None else dt_util.now().timestamp()) + 600,
        "km": km,
        "verbrauch_kwh": kwh,
        "datum": dt_util.now().date().isoformat(),
    }
    coordinator._finalize_trip_record(rec)
    return rec


def _seed_day(coordinator, kwh):
    today = dt_util.now().date()
    coordinator.data["vehicle_discharge_weekday_days"] = {
        str(today.weekday()): [{"date": today.isoformat(), "kwh": kwh}],
    }
    return today


async def test_sonderfahrt_zieht_nur_diese_fahrt_vom_live_tageswert_ab(hass, coordinators):
    c = await _make_coordinator(hass, coordinators)
    today = _seed_day(c, 25.0)
    _add_trip(c, 1001, 3.0, 12.0)  # normale Fahrt
    _add_trip(c, 1002, 16.0, 69.0)  # Sonderfahrt
    assert await c.async_set_sonderfahrt(1002) is True
    days = c.data["vehicle_discharge_weekday_days"][str(today.weekday())]
    assert days == [{"date": today.isoformat(), "kwh": 9.0}]  # 25 - 16, normale Fahrt bleibt drin
    rec = next(r for r in c.data["fahrten"] if r["erfasst_ts"] == 1002)
    assert rec["sonderfahrt"] is True
    assert rec["weekday_applied"] is None
    assert rec["sonderfahrt_abzug_kwh"] == 16.0
    normal = next(r for r in c.data["fahrten"] if r["erfasst_ts"] == 1001)
    assert normal.get("sonderfahrt") is None
    assert normal["weekday_applied"] is not None


async def test_sonderfahrt_nimmt_fahrt_aus_fahrtenbuch_wochentagssumme(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf2")
    _add_trip(c, 2001, 10.0, 40.0)
    wd = str(dt_util.now().date().weekday())
    vorher = c.data["weekday_kwh_exact_totals"][wd]
    assert vorher > 0
    await c.async_set_sonderfahrt(2001)
    assert round(c.data["weekday_kwh_exact_totals"][wd], 4) == 0.0
    await c.async_set_sonderfahrt(2001, False)
    assert round(c.data["weekday_kwh_exact_totals"][wd], 4) == round(vorher, 4)


async def test_sonderfahrt_ist_idempotent(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf3")
    today = _seed_day(c, 25.0)
    _add_trip(c, 3001, 16.0, 69.0)
    await c.async_set_sonderfahrt(3001)
    await c.async_set_sonderfahrt(3001)
    days = c.data["vehicle_discharge_weekday_days"][str(today.weekday())]
    assert days[0]["kwh"] == 9.0
    await c.async_set_sonderfahrt(3001, False)
    await c.async_set_sonderfahrt(3001, False)
    days = c.data["vehicle_discharge_weekday_days"][str(today.weekday())]
    assert days[0]["kwh"] == 25.0


async def test_sonderfahrt_zurueckgenommen_bucht_verbrauch_zurueck(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf4")
    today = _seed_day(c, 25.0)
    _add_trip(c, 4001, 16.0, 69.0)
    await c.async_set_sonderfahrt(4001)
    await c.async_set_sonderfahrt(4001, False)
    days = c.data["vehicle_discharge_weekday_days"][str(today.weekday())]
    assert days == [{"date": today.isoformat(), "kwh": 25.0}]
    rec = c.data["fahrten"][0]
    assert "sonderfahrt" not in rec and "sonderfahrt_abzug_kwh" not in rec
    assert rec["weekday_applied"] is not None


async def test_sonderfahrt_ohne_tageseintrag_merkt_offenen_abzug_und_verrechnet_ihn(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf5")
    today = dt_util.now().date()
    _add_trip(c, 5001, 16.0, 69.0)
    await c.async_set_sonderfahrt(5001)
    assert c.data["vehicle_discharge_abzug_offen"] == {today.isoformat(): 16.0}
    # Der Abfall der Fahrt wird erst jetzt bestaetigt und gebucht: 20 kWh,
    # davon 16 offener Abzug -> 4 kWh landen im Fenster.
    c._book_vehicle_discharge_weekday(20.0, dt_util.now().timestamp())
    days = c.data["vehicle_discharge_weekday_days"][str(today.weekday())]
    assert days == [{"date": today.isoformat(), "kwh": 4.0}]
    assert c.data["vehicle_discharge_abzug_offen"] == {}


async def test_sonderfahrt_zurueckgenommen_storniert_offenen_abzug(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf6")
    today = dt_util.now().date()
    _add_trip(c, 6001, 16.0, 69.0)
    await c.async_set_sonderfahrt(6001)
    await c.async_set_sonderfahrt(6001, False)
    assert c.data["vehicle_discharge_abzug_offen"] == {}
    c._book_vehicle_discharge_weekday(5.0, dt_util.now().timestamp())
    days = c.data["vehicle_discharge_weekday_days"][str(today.weekday())]
    assert days == [{"date": today.isoformat(), "kwh": 5.0}]


async def test_sonderfahrt_unbekannte_fahrt_gibt_false(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf7")
    assert await c.async_set_sonderfahrt(999) is False


async def test_sonderfahrt_behaelt_urlaub_der_fahrt(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf8")
    rec = _add_trip(c, 8001, 10.0, 40.0)
    rec["urlaub"] = True
    rec["weekday_applied"] = None
    await c.async_set_sonderfahrt(8001)
    await c.async_set_sonderfahrt(8001, False)
    assert rec["urlaub"] is True
    assert rec["weekday_applied"] is None  # blieb ausgenommen, wurde nicht neu gebucht


async def test_sonderfahrt_service_ruft_coordinator(hass):
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import (
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        DOMAIN,
        SERVICE_SONDERFAHRT,
    )

    data = {
        CONF_VEHICLE_HERSTELLER: "Peugeot",
        CONF_VEHICLE_MODELL: "eRifter",
        CONF_SOC_ENTITY: "sensor.test_soc",
        CONF_USABLE_KWH: 50.0,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, options={}, entry_id="sf9")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert hass.services.has_service(DOMAIN, SERVICE_SONDERFAHRT)
        coordinator.async_set_sonderfahrt = AsyncMock(return_value=True)
        await hass.services.async_call(
            DOMAIN, SERVICE_SONDERFAHRT,
            {"config_entry_id": entry.entry_id, "erfasst_ts": 77, "aktiv": False}, blocking=True,
        )
        coordinator.async_set_sonderfahrt.assert_awaited_once_with(77, False)
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


async def test_sonderfahrt_heute_zaehlt_nicht_in_verbraucht_heute(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf9")
    _seed_day(c, 25.0)
    key = c._period_keys()["day"]
    c.data["vehicle_discharge_periods"] = {"day": {"key": key, "kwh": 100.0}}
    c.data["vehicle_discharge_kwh_total"] = 125.0
    _add_trip(c, 9001, 3.0, 12.0)
    _add_trip(c, 9002, 16.0, 69.0)
    assert c._vehicle_discharge_kwh_used_today() == 25.0
    await c.async_set_sonderfahrt(9002)
    assert c._vehicle_discharge_kwh_used_today() == 9.0
    await c.async_set_sonderfahrt(9002)  # idempotent
    assert c._vehicle_discharge_kwh_used_today() == 9.0
    await c.async_set_sonderfahrt(9002, False)
    assert c._vehicle_discharge_kwh_used_today() == 25.0


async def test_sonderfahrt_frueherer_tag_laesst_tagesbasis_unberuehrt(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "sf10")
    key = c._period_keys()["day"]
    c.data["vehicle_discharge_periods"] = {"day": {"key": key, "kwh": 100.0}}
    c.data["vehicle_discharge_kwh_total"] = 110.0
    gestern = dt_util.now().timestamp() - 86400
    _add_trip(c, 9101, 5.0, 20.0, start_ts=gestern)
    await c.async_set_sonderfahrt(9101)
    assert c._vehicle_discharge_kwh_used_today() == 10.0
