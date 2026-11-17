"""Tests fuer den Urlaubs-Kalender als Quelle (CONF_URLAUB_KALENDER_ENTITY,
coordinator.py::async_refresh_urlaub_kalender()): Termine gelten als
Zeitfenster von Start bis Ende, Fahrten/Verbrauch davor zaehlen normal."""
from datetime import timedelta

from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

CAL = "calendar.familien_urlaub"


async def _make_coordinator(hass, coordinators, entry_id="uq1", events=None):
    from custom_components.ev_assistant.const import CONF_URLAUB_KALENDER_ENTITY, DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    state = {"events": events or [], "fail": False}

    async def _get_events(call):
        if state["fail"]:
            raise HomeAssistantError("Kalender nicht erreichbar")
        return {CAL: {"events": state["events"]}}

    hass.services.async_register("calendar", "get_events", _get_events, supports_response=SupportsResponse.ONLY)
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={CONF_URLAUB_KALENDER_ENTITY: CAL}, entry_id=entry_id
    )
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, state


def _event(start, end):
    return {"start": start.isoformat(), "end": end.isoformat(), "summary": "Urlaub"}


async def test_termine_werden_gelesen_und_als_zeitfenster_gespeichert(hass, coordinators):
    now = dt_util.now()
    c, _ = await _make_coordinator(
        hass, coordinators, events=[_event(now + timedelta(hours=2), now + timedelta(days=3))]
    )
    assert await c.async_refresh_urlaub_kalender() is True
    assert len(c.data["urlaub_kalender_intervalle"]) == 1
    assert c._urlaub_zeit((now + timedelta(days=1)).timestamp()) is True
    assert c._urlaub_zeit((now + timedelta(hours=1)).timestamp()) is False
    assert c._urlaub_zeit((now + timedelta(days=4)).timestamp()) is False


async def test_verbrauch_vor_dem_start_zaehlt_danach_nicht(hass, coordinators):
    now = dt_util.now()
    start = now - timedelta(hours=1)  # Urlaub hat vor einer Stunde begonnen
    c, _ = await _make_coordinator(hass, coordinators, "uq2", events=[_event(start, now + timedelta(days=3))])
    await c.async_refresh_urlaub_kalender()
    c._book_vehicle_discharge_weekday(8.0, (start - timedelta(hours=3)).timestamp())  # Arbeitsweg am Vormittag
    c._book_vehicle_discharge_weekday(5.0, (start + timedelta(minutes=10)).timestamp())  # Fahrt in den Urlaub
    tag = start.date().isoformat()
    days = [e for v in c.data["vehicle_discharge_weekday_days"].values() for e in v if e["date"] == tag]
    assert days and days[0]["kwh"] == 8.0  # nur die Fahrt vor dem Start zaehlt


async def test_fahrt_vor_dem_start_wird_gebucht_danach_als_urlaub(hass, coordinators):
    now = dt_util.now()
    start = now - timedelta(hours=1)
    c, _ = await _make_coordinator(hass, coordinators, "uq3", events=[_event(start, now + timedelta(days=3))])
    await c.async_refresh_urlaub_kalender()
    datum = start.date().isoformat()
    vor_start = (start - timedelta(hours=4)).timestamp()
    nach_start = (start + timedelta(minutes=5)).timestamp()
    vor = {"erfasst_ts": 1, "start_ts": vor_start, "end_ts": vor_start + 3600, "km": 15.0, "verbrauch_kwh": 3.0, "datum": datum}
    nach = {
        "erfasst_ts": 2, "start_ts": nach_start, "end_ts": nach_start + 2700,
        "km": 80.0, "verbrauch_kwh": 15.0, "datum": datum,
    }
    c._finalize_trip_record(vor)
    c._finalize_trip_record(nach)
    assert vor["urlaub"] is False and vor["weekday_applied"] is not None
    assert nach["urlaub"] is True and nach["weekday_applied"] is None


async def test_urlaub_aktiv_waehrend_des_termins(hass, coordinators):
    now = dt_util.now()
    events = [_event(now - timedelta(hours=1), now + timedelta(days=2))]
    c, state = await _make_coordinator(hass, coordinators, "uq4", events=events)
    assert c._urlaub_aktiv() is False  # noch nicht gelesen
    await c.async_refresh_urlaub_kalender()
    assert c._urlaub_aktiv() is True
    state["events"] = []  # Termin geloescht -> verschwindet beim naechsten Abruf
    await c.async_refresh_urlaub_kalender()
    assert c._urlaub_aktiv() is False


async def test_ueberwiegend_urlaubstag_ab_zwoelf_stunden(hass, coordinators):
    tag = dt_util.now().date() + timedelta(days=5)
    start = dt_util.start_of_local_day(tag)
    c, _ = await _make_coordinator(
        hass, coordinators, "uq5", events=[_event(start + timedelta(hours=14), start + timedelta(days=2))]
    )
    await c.async_refresh_urlaub_kalender()
    assert c._urlaub_tag_ueberwiegend(tag) is False  # nur 10 von 24 Stunden
    assert c._urlaub_tag_ueberwiegend(tag + timedelta(days=1)) is True
    c.data["urlaub_kalender_intervalle"] = [[(start + timedelta(hours=10)).timestamp(), (start + timedelta(days=1)).timestamp()]]
    assert c._urlaub_tag_ueberwiegend(tag) is True  # 14 von 24 Stunden


async def test_kalender_fehler_behaelt_letzten_stand_und_loggt_einmal(hass, coordinators):
    now = dt_util.now()
    events = [_event(now + timedelta(hours=1), now + timedelta(days=2))]
    c, state = await _make_coordinator(hass, coordinators, "uq6", events=events)
    await c.async_refresh_urlaub_kalender()
    vorher = list(c.data["urlaub_kalender_intervalle"])
    state["fail"] = True
    assert await c.async_refresh_urlaub_kalender() is False
    assert await c.async_refresh_urlaub_kalender() is False
    assert c.data["urlaub_kalender_intervalle"] == vorher
    fehler = [e for e in c.data["event_log"] if e["kategorie"] == "urlaub_kalender_fehler"]
    assert len(fehler) == 1
    state["fail"] = False
    assert await c.async_refresh_urlaub_kalender() is True
    assert any(e["kategorie"] == "urlaub_kalender_wieder_lesbar" for e in c.data["event_log"])


async def test_info_liefert_termine_mit_tagen_fuer_die_karte(hass, coordinators):
    tag = dt_util.now().date() + timedelta(days=10)
    start = dt_util.start_of_local_day(tag)
    c, _ = await _make_coordinator(
        hass, coordinators, "uq7", events=[_event(start + timedelta(hours=14), start + timedelta(days=3))]
    )
    await c.async_refresh_urlaub_kalender()
    info = c.urlaub_info()
    assert info["kalender_konfiguriert"] is True
    assert len(info["kalender_termine"]) == 1
    termin = info["kalender_termine"][0]
    assert termin["von"] == tag.isoformat()
    assert termin["bis"] == (tag + timedelta(days=2)).isoformat()  # Ende um 00:00 -> Vortag zaehlt
    assert termin["start"].startswith(tag.isoformat() + "T14:00")


async def test_ohne_konfigurierten_kalender_bleibt_alles_wie_vorher(hass, coordinators):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={}, entry_id="uq8")
    entry.add_to_hass(hass)
    c = EvAssistantCoordinator(hass, entry)
    coordinators.append(c)
    await c.async_setup()
    assert await c.async_refresh_urlaub_kalender() is False
    assert c._urlaub_zeit(dt_util.now().timestamp()) is False
    assert c.urlaub_info()["kalender_konfiguriert"] is False
    assert c.urlaub_info()["kalender_termine"] == []
