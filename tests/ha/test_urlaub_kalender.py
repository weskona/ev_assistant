"""Tests fuer den Urlaubskalender (gesetzte Urlaubstage/-zeitraeume, siehe
coordinator.py::async_set_urlaub_zeitraum()): sie zaehlen wie der
Urlaubsschalter, auch fuer kuenftige Tage, und nehmen beim Setzen
vergangene Tage rueckwirkend aus den Profil-Fenstern."""
from datetime import timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="uk1"):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator


def _today():
    return dt_util.now().date()


async def test_heute_im_zeitraum_zaehlt_als_urlaub(hass, coordinators):
    c = await _make_coordinator(hass, coordinators)
    assert c._urlaub_aktiv() is False
    await c.async_set_urlaub_zeitraum(_today() - timedelta(days=1), _today() + timedelta(days=2))
    assert c._urlaub_aktiv() is True
    assert c._urlaub_tag(_today() + timedelta(days=2)) is True
    assert c._urlaub_tag(_today() + timedelta(days=3)) is False
    assert c.urlaub_info()["aktiv_heute"] is True
    assert c.urlaub_info()["schalter_konfiguriert"] is False


async def test_zukuenftiger_zeitraum_ist_heute_nicht_aktiv(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "uk2")
    await c.async_set_urlaub_zeitraum(_today() + timedelta(days=10), _today() + timedelta(days=14))
    assert c._urlaub_aktiv() is False
    assert c._urlaub_tag(_today() + timedelta(days=12)) is True
    assert len(c.urlaub_info()["zeitraeume"]) == 1


async def test_einzelner_tag_ohne_bis(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "uk3")
    tag = _today() + timedelta(days=5)
    await c.async_set_urlaub_zeitraum(tag)
    assert c.data["urlaub_zeitraeume"] == [{"von": tag.isoformat(), "bis": tag.isoformat()}]


async def test_entfernen_teilt_zeitraum(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "uk4")
    heute = _today()
    await c.async_set_urlaub_zeitraum(heute + timedelta(days=10), heute + timedelta(days=20))
    await c.async_set_urlaub_zeitraum(heute + timedelta(days=14), heute + timedelta(days=15), aktiv=False)
    assert c.data["urlaub_zeitraeume"] == [
        {"von": (heute + timedelta(days=10)).isoformat(), "bis": (heute + timedelta(days=13)).isoformat()},
        {"von": (heute + timedelta(days=16)).isoformat(), "bis": (heute + timedelta(days=20)).isoformat()},
    ]


async def test_vertauschte_grenzen_werden_gedreht(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "uk5")
    heute = _today()
    await c.async_set_urlaub_zeitraum(heute + timedelta(days=8), heute + timedelta(days=5))
    assert c.data["urlaub_zeitraeume"] == [
        {"von": (heute + timedelta(days=5)).isoformat(), "bis": (heute + timedelta(days=8)).isoformat()}
    ]


async def test_setzen_nimmt_vergangene_tage_aus_den_fenstern_und_laesst_andere_stehen(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "uk6")
    heute = _today()
    d1, d2, d3 = heute - timedelta(days=3), heute - timedelta(days=2), heute - timedelta(days=10)
    for key in ("vehicle_discharge_weekday_days", "house_weekday_days"):
        c.data[key] = {}
        for d, kwh in ((d1, 5.0), (d2, 7.0), (d3, 9.0)):
            c.data[key].setdefault(str(d.weekday()), []).append({"date": d.isoformat(), "kwh": kwh})
    # d1 und d3 liegen genau eine Woche auseinander, also im selben Wochentags-Fenster
    c.data["plug_window_weekday_days"] = {
        str(d1.weekday()): [{"date": d3.isoformat(), "kwh": 0.0}, {"date": d1.isoformat(), "kwh": 0.0}],
    }
    res = await c.async_set_urlaub_zeitraum(d1, d2)
    assert res["rueckwirkend_bereinigt"] >= 4
    for key in ("vehicle_discharge_weekday_days", "house_weekday_days"):
        daten = {e["date"] for v in c.data[key].values() for e in v}
        assert daten == {d3.isoformat()}
    plug = c.data["plug_window_weekday_days"]
    eintraege = {e["date"]: e for e in plug[str(d1.weekday())]}
    assert eintraege[d1.isoformat()]["urlaub"] is True
    assert not eintraege[d3.isoformat()].get("urlaub")
    assert d1.isoformat() in c.data["vehicle_discharge_counted_dates"]


async def test_live_soc_buchung_an_kalendertag_wird_uebersprungen_auch_wenn_heute_kein_urlaub(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "uk7")
    gestern = _today() - timedelta(days=1)
    await c.async_set_urlaub_zeitraum(gestern, gestern)
    assert c._urlaub_aktiv() is False  # heute normal
    beobachtet = dt_util.as_utc(dt_util.start_of_local_day(gestern)).timestamp() + 12 * 3600
    c._book_vehicle_discharge_weekday(10.0, beobachtet)
    assert (c.data.get("vehicle_discharge_weekday_days") or {}) == {}
    c._book_vehicle_discharge_weekday(10.0, dt_util.now().timestamp())  # heute: normal gebucht
    assert any(e["date"] == _today().isoformat() for v in c.data["vehicle_discharge_weekday_days"].values() for e in v)


async def test_fahrt_an_kalendertag_wird_nicht_ins_wochenprofil_gebucht(hass, coordinators):
    c = await _make_coordinator(hass, coordinators, "uk8")
    gestern = _today() - timedelta(days=1)
    await c.async_set_urlaub_zeitraum(gestern, gestern)
    start = dt_util.start_of_local_day(gestern).timestamp() + 8 * 3600
    rec = {"erfasst_ts": 1, "start_ts": start, "end_ts": start + 600, "km": 20.0, "verbrauch_kwh": 4.0,
           "datum": gestern.isoformat()}
    c._finalize_trip_record(rec)
    assert rec["urlaub"] is True
    assert rec["weekday_applied"] is None


async def test_urlaub_zeitraum_service_und_ws_info(hass):
    from custom_components.ev_assistant.const import (
        CONF_SOC_ENTITY,
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        DOMAIN,
        SERVICE_SET_URLAUB_ZEITRAUM,
    )

    data = {
        CONF_VEHICLE_HERSTELLER: "Peugeot",
        CONF_VEHICLE_MODELL: "eRifter",
        CONF_SOC_ENTITY: "sensor.test_soc",
        CONF_USABLE_KWH: 50.0,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, options={}, entry_id="uk9")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    try:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert hass.services.has_service(DOMAIN, SERVICE_SET_URLAUB_ZEITRAUM)
        von = (_today() + timedelta(days=30)).isoformat()
        bis = (_today() + timedelta(days=33)).isoformat()
        await hass.services.async_call(
            DOMAIN, SERVICE_SET_URLAUB_ZEITRAUM,
            {"config_entry_id": entry.entry_id, "von": von, "bis": bis}, blocking=True,
        )
        assert coordinator.urlaub_info()["zeitraeume"] == [{"von": von, "bis": bis}]
        await hass.services.async_call(
            DOMAIN, SERVICE_SET_URLAUB_ZEITRAUM,
            {"config_entry_id": entry.entry_id, "von": von, "bis": bis, "aktiv": False}, blocking=True,
        )
        assert coordinator.urlaub_info()["zeitraeume"] == []
    finally:
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
