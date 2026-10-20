"""Sanftes Nachladen (0.99.53): now nur bei Bedarf, Nachladen nach Sonnenuntergang."""
import importlib.util
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from homeassistant.util import dt as dt_util

_spec = importlib.util.spec_from_file_location("_mc_helpers", Path(__file__).with_name("test_evcc_mode_control.py"))
_mc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mc)
_make_coordinator = _mc._make_coordinator
_seed_usage_profile = _mc._seed_usage_profile


def _at(hour, minute=0, day=14):
    return datetime(2026, 10, day, hour, minute, tzinfo=dt_util.DEFAULT_TIME_ZONE)


async def _coord(hass, coordinators, entry_id, soc, sun="above_horizon", options=None):
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_ENABLED, CONF_USABLE_KWH

    opts = {CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0, **(options or {})}
    c, entry = await _make_coordinator(hass, coordinators, entry_id, options=opts)
    # Profil 10 kWh/Tag, Verbrauch 20 -> Puffer 30 km = 6 kWh: sofort 16, min 26
    _seed_usage_profile(c, weekday_kwh=10.0, avg_consumption=20.0)
    c._soc = soc
    c._day_fraction_elapsed = lambda: 0.0
    c._current_loadpoint = lambda: {"effectiveMinCurrent": 6, "phasesConfigured": 0}
    if sun:
        hass.states.async_set("sun.sun", sun, {"next_setting": "2026-10-14T16:38:00+00:00"})
    return c, entry


def _targets(c, when):
    with patch.object(dt_util, "now", return_value=when):
        return c._evcc_mode_targets()


async def test_tag_genug_zeit_wartet_auf_sonnenuntergang_min_soc_null(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn1", soc=40.0)  # 20 kWh: Defizit nur zu min
    t = _targets(c, _at(12))
    assert (t["modus"], t["nachladen_status"]) == ("pv", "wartet_auf_sonnenuntergang")
    assert t["nachladen_ab"] == "2026-10-14T16:38:00+00:00"
    assert t["min_soc"] == 0  # evccs Min-SoC wuerde sonst sofort voll laden
    assert t["min_kwh"] == 26.0 and t["sofort_kwh"] == 16.0  # Puffer in km wirkt in beiden


async def test_nacht_genug_zeit_minpv_und_zu_wenig_zeit_now(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn2", soc=40.0, sun="below_horizon")
    t = _targets(c, _at(22))
    assert (t["modus"], t["nachladen_status"], t["min_soc"]) == ("minpv", "sanft", 0)
    c2, _ = await _coord(hass, coordinators, "sn3", soc=32.0, sun="below_horizon")  # 16 kWh = sofort
    t = _targets(c2, _at(23))  # 7 h bis 06:00: 7,25 h + 0,5 h Bedarf -> Fristdruck
    assert (t["modus"], t["nachladen_status"], t["nachladen_halt"]) == ("now", "frist", "frist")
    assert t["min_soc"] == 52  # now bleibt -> berechneter Min-SoC bleibt


async def test_sofort_defizit_klein_minpv_gross_now(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn4", soc=30.0)  # 15 kWh, Defizit 1 kWh
    t = _targets(c, _at(12))
    assert (t["modus"], t["nachladen_status"]) == ("minpv", "sofort_sanft")
    c2, _ = await _coord(hass, coordinators, "sn5", soc=20.0)  # 10 kWh, Defizit 6 kWh
    t = _targets(c2, _at(12))
    assert (t["modus"], t["nachladen_status"], t["min_soc"]) == ("now", "sofort_zu_langsam", 52)


async def test_sonne_unbekannt_minpv_statt_now(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn6", soc=40.0, sun=None)
    t = _targets(c, _at(12))
    assert (t["modus"], t["nachladen_status"]) == ("minpv", "sanft")
    hass.states.async_set("sun.sun", "unavailable")
    assert _targets(c, _at(12))["modus"] == "minpv"


async def test_option_aus_ist_das_bisherige_verhalten(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_SOFT_RECHARGE_ENABLED

    c, _ = await _coord(hass, coordinators, "sn7", soc=40.0, options={CONF_EVCC_SOFT_RECHARGE_ENABLED: False})
    t = _targets(c, _at(12))
    assert (t["modus"], t["min_soc"], t["nachladen_status"]) == ("now", 52, None)
    assert t["sofort_kwh"] is None and t["abfahrt_frist"] is None


async def test_nicht_now_bleibt_unveraendert(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn8", soc=60.0)  # 30 kWh >= min 26
    t = _targets(c, _at(12))
    assert t["modus"] in ("pv", "minpv") and t["nachladen_status"] == "nicht_noetig"
    assert t["min_soc"] == 52


async def test_frist_ruckfall_wochentagswechsel_und_mitternacht(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn9", soc=40.0)
    d, q = c._evcc_departure_deadline(_at(22))
    assert (d.day, d.hour, d.minute, q) == (15, 6, 0, "fallback")  # ueber Mitternacht
    d, q = c._evcc_departure_deadline(_at(5, 0, day=15))
    assert (d.day, d.hour, q) == (15, 6, "fallback")  # heute noch nicht erreicht
    d, q = c._evcc_departure_deadline(_at(6, 30, day=15))
    assert d.day == 16  # heute vorbei -> morgen
    # belastbarer Wert nur fuer Donnerstag (15.10.2026): 05:30
    wd = _at(22).date().weekday() + 1
    c.plug_departure_profile = lambda: {"wochentage": {wd % 7: {"frueh_roh_min": 330}}}
    d, q = c._evcc_departure_deadline(_at(22))
    assert (d.day, d.hour, d.minute, q) == (15, 5, 30, "profil")
    d, q = c._evcc_departure_deadline(_at(5, 45, day=15))  # Donnerstag-Frist vorbei, Freitag Rueckfall
    assert (d.day, d.hour, d.minute, q) == (16, 6, 0, "fallback")


async def test_rueckfallzeit_option(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_DEPARTURE_FALLBACK_TIME

    c, _ = await _coord(hass, coordinators, "sn10", soc=40.0, options={CONF_EVCC_DEPARTURE_FALLBACK_TIME: "07:15"})
    d, q = c._evcc_departure_deadline(_at(22))
    assert (d.hour, d.minute, q) == (7, 15, "fallback")


async def test_mindestleistung_phasen(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn11", soc=40.0)
    assert c._evcc_min_charge_power_kw() == 1.38  # 1p3p ohne feste Konfiguration: niedrigste Annahme
    c._current_loadpoint = lambda: {"effectiveMinCurrent": 6, "phasesConfigured": 3}
    assert c._evcc_min_charge_power_kw() == 4.14
    c._current_loadpoint = lambda: {"minCurrent": 8, "chargerSinglePhase": True}
    assert c._evcc_min_charge_power_kw() == 1.84
    c._current_loadpoint = lambda: None
    assert c._evcc_min_charge_power_kw() == 1.38  # Rueckfall 6 A


async def test_haltezeit_festschreiben_und_loeschen(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn12", soc=32.0, sun="below_horizon")
    t = _targets(c, _at(23))
    c._nachladen_festschreiben(t)
    assert c.data["evcc_now_halt"]["grund"] == "frist"
    assert c.data["evcc_nachladen_status"] == "frist"
    # Halt wirkt: SoC steigt, Fristdruck waere weg, es bleibt now
    c._soc = 40.0  # 20 kWh >= sofort
    assert _targets(c, _at(23, 30))["modus"] == "now"
    c._nachladen_halt_loeschen()  # Pause/manuell/Urlaub
    assert c.data["evcc_now_halt"] is None
    assert _targets(c, _at(23, 30))["modus"] == "minpv"


async def test_attribute_am_sensor(hass, coordinators):
    from custom_components.ev_assistant.sensor import EvccModeControlSensor

    c, entry = await _coord(hass, coordinators, "sn13", soc=40.0)
    with patch.object(dt_util, "now", return_value=_at(12)):
        a = EvccModeControlSensor(c, entry).extra_state_attributes
    assert a["nachladen_status"] == "wartet_auf_sonnenuntergang"
    assert a["nachladen_ab"] and a["frist_quelle"] == "fallback" and a["abfahrt_frist"]
    assert a["sofort_kwh"] == 16.0 and a["sofort_km"] == 80.0 and a["min_km"] == 130.0


async def test_rueckfallzeit_je_wochentag_geht_vor_der_allgemeinen_zeit(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_DEPARTURE_FALLBACK_TIME,
        CONF_EVCC_DEPARTURE_FALLBACK_WEEKDAY,
    )

    # 14.10.2026 = Mittwoch, 15.10. = Donnerstag (Index 3), 16.10. = Freitag (Index 4)
    c, _ = await _coord(
        hass, coordinators, "sn12", soc=40.0,
        options={
            CONF_EVCC_DEPARTURE_FALLBACK_TIME: "06:00",
            CONF_EVCC_DEPARTURE_FALLBACK_WEEKDAY[3]: "13:30",
            CONF_EVCC_DEPARTURE_FALLBACK_WEEKDAY[4]: "",  # leer = allgemeine Zeit
        },
    )
    d, q = c._evcc_departure_deadline(_at(22))
    assert (d.day, d.hour, d.minute, q) == (15, 13, 30, "fallback")
    d, q = c._evcc_departure_deadline(_at(14, 0, day=15))  # Donnerstag 13:30 vorbei -> Freitag, leer = 06:00
    assert (d.day, d.hour, d.minute, q) == (16, 6, 0, "fallback")


async def test_rueckfall_aus_gibt_keine_frist_und_keinen_fristdruck(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_DEPARTURE_FALLBACK_ENABLED

    c, _ = await _coord(
        hass, coordinators, "sn13", soc=40.0, options={CONF_EVCC_DEPARTURE_FALLBACK_ENABLED: False},
        sun="below_horizon",
    )
    d, q = c._evcc_departure_deadline(_at(22))
    assert (d, q) == (None, "keine")
    t = _targets(c, _at(22))
    assert t["abfahrt_frist"] is None and t["frist_quelle"] == "keine"
    assert t["nachladen_grund"] != "frist"


async def test_entitaet_mit_naechster_abfahrt_geht_vor_statistik_und_rueckfall(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_DEPARTURE_ENTITY

    c, _ = await _coord(
        hass, coordinators, "sn14", soc=40.0, options={CONF_EVCC_DEPARTURE_ENTITY: "input_datetime.abfahrt"},
    )
    hass.states.async_set("input_datetime.abfahrt", "2026-10-15 14:15:00")
    d, q = c._evcc_departure_deadline(_at(22))
    assert (d.day, d.hour, d.minute, q) == (15, 14, 15, "entitaet")
    # Kalender: Beginn des naechsten Termins
    c2, _ = await _coord(
        hass, coordinators, "sn15", soc=40.0, options={CONF_EVCC_DEPARTURE_ENTITY: "calendar.schicht"},
    )
    hass.states.async_set("calendar.schicht", "off", {"start_time": "2026-10-15 22:00:00"})
    d, q = c2._evcc_departure_deadline(_at(22))
    assert (d.day, d.hour, q) == (15, 22, "entitaet")
    # unbrauchbarer Wert oder Vergangenheit -> naechste Quelle (Rueckfall)
    hass.states.async_set("input_datetime.abfahrt", "unknown")
    d, q = c._evcc_departure_deadline(_at(22))
    assert (d.hour, d.minute, q) == (6, 0, "fallback")
    hass.states.async_set("input_datetime.abfahrt", "2026-10-14 08:00:00")
    d, q = c._evcc_departure_deadline(_at(22))
    assert q == "fallback"


async def test_quellenwechsel_der_frist_steht_im_ereignisprotokoll(hass, coordinators):
    c, _ = await _coord(hass, coordinators, "sn16", soc=40.0)
    targets = {"frist_quelle": "fallback", "abfahrt_frist": "2026-10-15T06:00:00+02:00"}
    c._nachladen_festschreiben(targets)
    c._nachladen_festschreiben(targets)  # unveraendert -> kein zweiter Eintrag
    c._nachladen_festschreiben({"frist_quelle": "profil", "abfahrt_frist": "2026-10-15T13:00:00+02:00"})
    eintraege = [e["text"] for e in c.data["event_log"] if e["kategorie"] == "abfahrt_frist_quelle_geaendert"]
    assert len(eintraege) == 2 and eintraege[0].startswith("None->fallback") and eintraege[1].startswith("fallback->profil")
