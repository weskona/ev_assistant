"""Tests fuer das Steck-Zeitfenster-Beobachtungsfeature (siehe
coordinator.py::_update_plug_window()/_finalize_plug_window_day()/
plug_window_profile()) -- Nutzerwunsch 2026-09-23: "wäre für das
nutzungsprofil nicht auch die zeiten wann und wie lange am tag das auto
angeschlossen ist an die wallbox sinnvoll ... um zu erkennen wie das auto
zuhause ist und wann fenster zum laden entstehen", explizit "erstmal nur
zur beobachtung. steckersignal kommt von evcc" -- Quelle ist also evccs
Ladepunkt-Feld "connected", NICHT CONF_PLUG_ENTITY. Reine Sichtbarkeit,
kein Einfluss auf die Modus-/SoC-Steuerung."""
from datetime import datetime, timedelta

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="pw1", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
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
        "erste_abfahrt": None, "abfahrt_unsicher": False, "urlaub": False,
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


# ----- Morgen-Abfahrt (Abstecken, erste Abfahrt des Tages) -------------------
# Reine Beobachtung, KEINE Anbindung an die Steuerung.

def _at(day, hh, mm, ss=0):
    return datetime(2026, 10, day, hh, mm, ss, tzinfo=dt_util.DEFAULT_TIME_ZONE)


def _lp(coordinator, connected, vehicle_name=None, vehicles=None):
    lp = {"connected": connected}
    if vehicle_name:
        lp["vehicleName"] = vehicle_name
    coordinator._evcc_state = {"loadpoints": [lp], "vehicles": vehicles or {}}


def _run(coordinator, start, minutes, connected, step=15, **kw):
    """Tickt im 15-s-Takt ab `start` bis (exklusiv) `minutes` Minuten spaeter --
    direkt aufeinanderfolgende Aufrufe ergeben also lueckenlose 15-s-Ticks."""
    from datetime import timedelta as td

    _lp(coordinator, connected, **kw)
    t = start
    end = start + td(minutes=minutes)
    while t < end:
        coordinator._update_plug_window(t)
        t += td(seconds=step)
    return t


async def test_abfahrt_wird_nach_10_min_abgesteckt_bestaetigt(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep1")
    _run(coordinator, _at(14, 6, 0), 60, True)            # angesteckt bis 06:59:45
    _run(coordinator, _at(14, 7, 0), 10.25, False)        # ab 07:00 abgesteckt, 10 Min
    today = coordinator.data["plug_window_today"]
    assert today["erste_abfahrt"] == "07:00"
    assert today["abfahrt_unsicher"] is False
    assert coordinator.data["plug_departure_candidate"] is None


async def test_wiederanstecken_nach_5_min_verwirft_kandidat(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep2")
    _run(coordinator, _at(14, 6, 0), 60, True)
    _run(coordinator, _at(14, 7, 0), 5, False)
    assert coordinator.data["plug_departure_candidate"] is not None
    _run(coordinator, _at(14, 7, 5), 10, True)
    today = coordinator.data["plug_window_today"]
    assert coordinator.data["plug_departure_candidate"] is None
    assert today["erste_abfahrt"] is None


async def test_evcc_luecke_markiert_abfahrt_als_unsicher(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep3")
    _run(coordinator, _at(14, 6, 0), 60, True)
    # evcc 5 Minuten nicht erreichbar (keine Ticks), dann abgesteckt
    _run(coordinator, _at(14, 7, 5), 10.25, False)
    today = coordinator.data["plug_window_today"]
    assert today["erste_abfahrt"] == "07:05"
    assert today["abfahrt_unsicher"] is True


async def test_neustart_mit_offenem_kandidaten_ueberlebt_und_ist_unsicher(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep4")
    _run(coordinator, _at(14, 6, 0), 60, True)
    _run(coordinator, _at(14, 7, 0), 3, False)
    await coordinator._save()
    gespeichert = coordinator.data["plug_departure_candidate"]
    assert gespeichert["hhmm"] == "07:00"

    neu, _ = await _make_coordinator(hass, coordinators, "dep4")
    assert neu.data["plug_departure_candidate"] == gespeichert
    assert neu.data["plug_window_prev_connected"] is False
    # Weiter nach "Neustart" (4 Min. Pause): Kandidat wird bestaetigt, aber unsicher.
    _run(neu, _at(14, 7, 7), 4, False)
    today = neu.data["plug_window_today"]
    assert today["erste_abfahrt"] == "07:00"
    assert today["abfahrt_unsicher"] is True


async def test_nacht_angesteckt_abfahrt_morgens_zaehlt_fuer_den_folgetag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep5")
    _run(coordinator, _at(14, 22, 0), 120, True)           # 22:00 .. 23:59
    _run(coordinator, _at(15, 0, 0), 420, True)            # Nacht bis 06:59
    _run(coordinator, _at(15, 7, 0), 10.25, False)         # Abfahrt Donnerstag 07:00
    _run(coordinator, _at(16, 0, 0), 1, False)             # Tageswechsel -> finalisiert
    donnerstag = coordinator.data["plug_window_weekday_days"][str(_at(15, 0, 0).weekday())]
    eintrag = donnerstag[-1]
    assert eintrag["date"] == "2026-10-15"
    assert eintrag["erste_abfahrt"] == "07:00"
    # Mittwoch (Anstecken) bekommt keine Abfahrt
    mittwoch = coordinator.data["plug_window_weekday_days"][str(_at(14, 0, 0).weekday())][-1]
    assert mittwoch["erste_abfahrt"] is None


async def test_nacht_ohne_anstecken_liefert_keine_messung(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep6")
    _run(coordinator, _at(14, 0, 0), 600, False)
    _run(coordinator, _at(15, 0, 0), 1, False)
    eintrag = coordinator.data["plug_window_weekday_days"][str(_at(14, 0, 0).weekday())][-1]
    assert eintrag["erste_abfahrt"] is None
    stats = coordinator.plug_departure_profile()["wochentage"][_at(14, 0, 0).weekday()]
    assert stats["n_gueltig"] == 0 and stats["status"] == "keine_messung"


async def test_erste_abfahrt_gilt_ganztags_und_alle_abfahrten_werden_gespeichert(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep7")
    _run(coordinator, _at(14, 2, 0), 60, True)
    _run(coordinator, _at(14, 3, 0), 10.25, False)         # 03:00: seit 0.99.61 zaehlt der ganze Tag
    _run(coordinator, _at(14, 3, 10, 15), 229.75, True)
    _run(coordinator, _at(14, 7, 0), 10.25, False)         # 07:00 ist nicht mehr die erste
    today = coordinator.data["plug_window_today"]
    assert today["abfahrten_bestaetigt"] == 2
    assert today["erste_abfahrt"] == "03:00"
    assert [a["hhmm"] for a in today["abfahrten"]] == ["03:00", "07:00"]


async def test_urlaub_wird_am_tag_eingefroren_und_zaehlt_nicht(hass, coordinators):
    coordinator, _ = await _make_coordinator(
        hass, coordinators, "dep8", options={"urlaub_entity": "input_boolean.urlaub"}
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    _run(coordinator, _at(14, 6, 0), 60, True)
    _run(coordinator, _at(14, 7, 0), 10.25, False)
    hass.states.async_set("input_boolean.urlaub", "off")   # Schalter spaeter wieder aus
    _run(coordinator, _at(15, 0, 0), 1, False)
    eintrag = coordinator.data["plug_window_weekday_days"][str(_at(14, 0, 0).weekday())][-1]
    assert eintrag["urlaub"] is True and eintrag["erste_abfahrt"] == "07:00"
    profile = coordinator.plug_departure_profile()
    assert profile["wochentage"][_at(14, 0, 0).weekday()]["n_gueltig"] == 0
    assert profile["urlaub_nicht_gewertet"] == 1


async def test_urlaub_seit_markiert_rueckwirkend_und_idempotent(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep9")
    heute = dt_util.now().date()
    gestern = heute - timedelta(days=1)
    alt = heute - timedelta(days=10)
    coordinator.data["plug_window_weekday_days"] = {
        str(gestern.weekday()): [{"date": gestern.isoformat(), "stunden": 5.0, "erste_abfahrt": "07:00"}],
        str(alt.weekday()): [{"date": alt.isoformat(), "stunden": 5.0, "erste_abfahrt": "07:00"}],
    }
    coordinator.data["plug_window_today"] = {"date": heute.isoformat(), "connected_seconds": 0.0}
    since_ts = dt_util.start_of_local_day(gestern).timestamp()
    result = await coordinator.async_apply_vehicle_discharge_urlaub_since(since_ts)
    assert result["plug_markiert"] == 2          # gestern + offener Tag "heute"
    days = coordinator.data["plug_window_weekday_days"]
    assert days[str(gestern.weekday())][0]["urlaub"] is True
    assert "urlaub" not in days[str(alt.weekday())][0]
    # zweiter Aufruf: nichts Neues
    again = await coordinator.async_apply_vehicle_discharge_urlaub_since(since_ts)
    assert again == {"reclassified_kwh": 0.0, "wochentage": {}}


async def test_fremdes_fahrzeug_am_ladepunkt_zaehlt_nicht_als_dieses_fahrzeug(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep10")
    vehicles = {"db:1": {"title": "Zoe"}, "db:2": {"title": "Peugeot"}}
    coordinator._evcc_state = {"loadpoints": [{"connected": True, "vehicleName": "db:1"}], "vehicles": vehicles}
    coordinator._evcc_vehicle_api_key = lambda: "db:2"
    assert coordinator._own_vehicle_plugged(coordinator._current_loadpoint()) is False
    coordinator._evcc_state["loadpoints"][0]["vehicleName"] = "db:2"
    assert coordinator._own_vehicle_plugged(coordinator._current_loadpoint()) is True
    # noch nicht erkannt bei mehreren Fahrzeugen: unbekannt -> Zustand wird gehalten
    coordinator._evcc_state["loadpoints"][0].pop("vehicleName")
    assert coordinator._own_vehicle_plugged(coordinator._current_loadpoint()) is None
    # Ein einziges Fahrzeug in evcc: eindeutig dieses
    coordinator._evcc_state["vehicles"] = {"db:2": {"title": "Peugeot"}}
    assert coordinator._own_vehicle_plugged(coordinator._current_loadpoint()) is True


async def test_fremdfahrzeug_ersetzt_eigenes_ist_abfahrt_und_unbekannt_haelt_zustand(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep11")
    vehicles = {"db:1": {"title": "Zoe"}, "db:2": {"title": "Peugeot"}}
    coordinator._evcc_vehicle_api_key = lambda: "db:2"
    _run(coordinator, _at(14, 6, 0), 60, True, vehicle_name="db:2", vehicles=vehicles)
    # Erkennung laeuft (kein vehicleName): keine Flanke, Zustand gehalten
    _run(coordinator, _at(14, 7, 0), 2, True, vehicles=vehicles)
    assert coordinator.data["plug_window_prev_connected"] is True
    assert coordinator.data["plug_departure_candidate"] is None
    # Fremdes Fahrzeug haengt jetzt am Ladepunkt -> eigenes Auto ist weg
    _run(coordinator, _at(14, 7, 2), 10.25, True, vehicle_name="db:1", vehicles=vehicles)
    assert coordinator.data["plug_window_today"]["erste_abfahrt"] == "07:02"


async def test_sensor_morning_departure_klein_und_aware_timestamp(hass, coordinators):
    from custom_components.ev_assistant.sensor import MorningDepartureSensor

    coordinator, entry = await _make_coordinator(hass, coordinators, "dep12")
    sensor = MorningDepartureSensor(coordinator, entry)
    assert sensor.unique_id == "dep12_morning_departure"        # -> landet automatisch in der Entities-Map
    assert sensor.native_value is None                          # noch nichts belastbar
    morgen = dt_util.now().date() + timedelta(days=1)
    coordinator.data["plug_window_weekday_days"] = {
        str(morgen.weekday()): [
            {"date": f"2026-0{m}-0{d}", "erste_abfahrt": t}
            for m, d, t in [(8, 3, "07:00"), (8, 10, "07:05"), (8, 17, "06:55"), (8, 24, "07:10"), (8, 31, "10:00")]
        ],
    }
    wert = sensor.native_value
    assert wert.tzinfo is not None
    assert (wert.hour, wert.minute) == (7, 2) or (wert.hour, wert.minute) == (7, 3)
    assert wert.date() == morgen
    attrs = sensor.extra_state_attributes
    assert set(attrs) == {"je_wochentag", "urlaub_nicht_gewertet", "mindestanzahl"}
    je = attrs["je_wochentag"][sensor._WEEKDAY_KEYS[morgen.weekday()]]
    assert je["status"] == "ok" and je["n_gueltig"] == 5 and je["n_ausreisser"] == 1
    assert je["frueh_roh"] == "06:55" and je["n_ausreisser_frueh"] == 0
    assert attrs["mindestanzahl"] == 4


async def test_plug_window_sensor_schliesst_rohlisten_vom_recorder_aus(hass, coordinators):
    from custom_components.ev_assistant.sensor import PlugWindowSensor

    assert PlugWindowSensor._unrecorded_attributes == frozenset({"heute", "tage"})


async def test_abfahrt_kurz_vor_mitternacht_geht_in_den_eintrag_ihres_tages(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep_mn")
    gestern = _at(14, 23, 55).date()
    candidate = {"ts": 0.0, "hhmm": "23:55", "date": gestern.isoformat(), "unsicher": False}
    heute = {"date": _at(15, 0, 5).date().isoformat(), "abfahrten_bestaetigt": 0, "abfahrten": []}
    coordinator._confirm_plug_departure(candidate, heute)
    eintraege = coordinator.data["plug_window_weekday_days"][str(gestern.weekday())]
    assert eintraege[-1]["date"] == gestern.isoformat()
    assert [a["hhmm"] for a in eintraege[-1]["abfahrten"]] == ["23:55"]
    assert heute["abfahrten"] == [] and heute["abfahrten_bestaetigt"] == 0  # heutiger Tag unberuehrt


async def test_abfahrtsprofil_nachrechnen_aus_fahrtenbuch(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "dep_rb")
    heute = dt_util.now().date()

    def trip(tage_zurueck, hour, minute, ort="Home", delay_min=5.0):
        start = datetime(heute.year, heute.month, heute.day, hour, minute, tzinfo=dt_util.DEFAULT_TIME_ZONE)
        start -= timedelta(days=tage_zurueck)
        return {"start_ts": start.timestamp(), "end_ts": start.timestamp() + 1200,
                "erfasst_ts": start.timestamp() + 1200 + delay_min * 60, "start_ort": ort, "km": 5.0}

    tag_a, tag_b = heute - timedelta(days=3), heute - timedelta(days=5)
    coordinator.data["fahrten"] = [
        trip(3, 7, 40), trip(3, 12, 30), trip(5, 8, 0), trip(0, 9, 0), trip(4, 7, 0, delay_min=300),
    ]
    # tag_b hat schon eine gemessene Abfahrt (Wallbox) -> bleibt unberuehrt
    coordinator.data["plug_window_weekday_days"] = {str(tag_b.weekday()): [{
        "date": tag_b.isoformat(), "stunden": 9.0, "erster_connect": "18:00", "letzter_disconnect": "07:30",
        "erste_abfahrt": "07:31", "abfahrt_unsicher": False, "urlaub": False,
    }]}
    result = await coordinator.async_rebuild_departure_profile()
    assert result == {"tage_gebucht": 1, "tage_mit_messung_uebersprungen": 1}
    tage_a = coordinator.data["plug_window_weekday_days"][str(tag_a.weekday())]
    eintrag = next(e for e in tage_a if e["date"] == tag_a.isoformat())
    assert eintrag["quelle"] == "fahrtenbuch" and eintrag["erste_abfahrt"] == "07:40"
    assert [a["hhmm"] for a in eintrag["abfahrten"]] == ["07:40", "12:30"]
    gemessen = coordinator.data["plug_window_weekday_days"][str(tag_b.weekday())][0]
    assert gemessen["erste_abfahrt"] == "07:31" and "quelle" not in gemessen
    assert any(e["kategorie"] == "abfahrtsprofil_nachgerechnet" for e in coordinator.data["event_log"])
    # wiederholbar: gleicher Stand, kein Duplikat
    result = await coordinator.async_rebuild_departure_profile()
    assert result["tage_gebucht"] == 1
    tage_a = coordinator.data["plug_window_weekday_days"][str(tag_a.weekday())]
    assert len([e for e in tage_a if e["date"] == tag_a.isoformat()]) == 1
