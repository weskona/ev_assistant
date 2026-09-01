"""Tests fuer die evcc-Modus-/SoC-Steuerung (CONF_EVCC_MODE_CONTROL_ENABLED,
siehe coordinator.py::_async_apply_evcc_mode_control()/_evcc_mode_targets())
sowie das dafuer optionale, einfache Haus-Nutzungsprofil
(_update_house_usage_profile() u.a.). Reine Berechnungslogik (engine.py::
determine_evcc_mode() etc.) ist bereits in tests/test_engine.py abgedeckt --
hier nur die HA-Verdrahtung (Entity-Lesen, Coordinator-Zustand, evcc-Client-
Schreibaufrufe, Repair-Issues)."""
from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="evcc_mc", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


def _seed_usage_profile(coordinator, weekday_kwh=10.0, avg_consumption=20.0):
    """Fuellt usage_profile() mit einem kontrollierbaren, vollstaendigen
    7-Tage-Profil (identischer Bedarf an jedem Wochentag) -- first_ts genau
    6 Tage in der Vergangenheit ergibt eine 7-Kalendertage-Spanne, in der
    jeder Wochentag GENAU EINMAL vorkommt, unabhaengig vom aktuellen
    Wochentag -- dadurch entspricht weekday_kwh_exact_totals direkt dem
    Ergebnis, ohne die Anzahl Vorkommen je Wochentag ausrechnen zu muessen."""
    coordinator.data["fahrtenbuch_first_ts"] = (dt_util.now() - timedelta(days=6)).timestamp()
    coordinator.data["weekday_kwh_exact_totals"] = {str(wd): weekday_kwh for wd in range(7)}
    coordinator.data["weekday_km_est_totals"] = {}
    coordinator._usage_profile_cache = None
    # Monkeypatch statt echter Fahrzeug-/Kosten-Historie -- _kwh_used_today()
    # braucht nur einen festen Wert, kein realistisches Zusammenspiel aus
    # _km_driven()/_ev_kwh_total_since_setup().
    coordinator._vehicle_avg_consumption_kwh_per_100km = lambda: avg_consumption


def _seed_odo_today(coordinator, baseline_km, current_km):
    coordinator.data["odo"] = current_km
    coordinator.data["odo_unit"] = "km"
    coordinator.data["odo_periods"] = {"day": {"key": "irgendein-schluessel", "odo_km": baseline_km}}


def _fake_evcc_client(probe_result="loadpoint", mode_ok=True, min_soc_ok=True, limit_soc_ok=True):
    """`probe_result` gilt fuer BEIDE Eigenschaften (min-/limitsoc) gleich,
    sofern nicht als (min, limit)-Tupel uebergeben -- die meisten Tests
    unterscheiden nicht zwischen den beiden Scopes; siehe
    test_apply_evcc_mode_control_min_und_limit_soc_koennen_unterschiedliche_scopes_haben
    fuer den Fall, in dem sie es tun."""
    min_result, limit_result = probe_result if isinstance(probe_result, tuple) else (probe_result, probe_result)

    async def _probe_scope(loadpoint_id, vehicle_name, prop, state_field):
        return min_result if prop == "minsoc" else limit_result

    client = AsyncMock()
    client.async_probe_scope = AsyncMock(side_effect=_probe_scope)
    client.async_set_mode = AsyncMock(return_value=mode_ok)
    client.async_set_min_soc = AsyncMock(return_value=min_soc_ok)
    client.async_set_limit_soc = AsyncMock(return_value=limit_soc_ok)
    return client


# ----- _kwh_used_today ------------------------------------------------------

async def test_kwh_used_today_normalfall(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "kut1")
    _seed_usage_profile(coordinator, avg_consumption=20.0)
    _seed_odo_today(coordinator, baseline_km=100.0, current_km=130.0)
    assert coordinator._kwh_used_today() == 6.0  # 30 km * 20 kWh/100km


async def test_kwh_used_today_ohne_tages_baseline_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "kut2")
    _seed_usage_profile(coordinator)
    coordinator.data["odo"] = 130.0
    coordinator.data["odo_unit"] = "km"
    coordinator.data["odo_periods"] = {}
    assert coordinator._kwh_used_today() is None


async def test_kwh_used_today_negatives_delta_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "kut3")
    _seed_usage_profile(coordinator)
    _seed_odo_today(coordinator, baseline_km=130.0, current_km=100.0)
    assert coordinator._kwh_used_today() is None


# ----- _pv_forecast_today_remaining_kwh -------------------------------------

async def test_pv_forecast_today_remaining_kwh_normalfall(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_PV_FORECAST_TODAY_REMAINING_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "pvr1", options={CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    hass.states.async_set("sensor.pv_rest", "3.5", {"unit_of_measurement": "kWh"})
    assert coordinator._pv_forecast_today_remaining_kwh() == 3.5


async def test_pv_forecast_today_remaining_kwh_wh_wird_zu_kwh(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_PV_FORECAST_TODAY_REMAINING_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "pvr2", options={CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    hass.states.async_set("sensor.pv_rest", "3500", {"unit_of_measurement": "Wh"})
    assert coordinator._pv_forecast_today_remaining_kwh() == 3.5


async def test_pv_forecast_today_remaining_kwh_ohne_entitaet_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "pvr3")
    assert coordinator._pv_forecast_today_remaining_kwh() is None


async def test_pv_forecast_today_remaining_kwh_unavailable_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_PV_FORECAST_TODAY_REMAINING_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "pvr4", options={CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    hass.states.async_set("sensor.pv_rest", "unavailable")
    assert coordinator._pv_forecast_today_remaining_kwh() is None


async def test_pv_forecast_today_remaining_kwh_nicht_numerisch_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_PV_FORECAST_TODAY_REMAINING_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "pvr5", options={CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    hass.states.async_set("sensor.pv_rest", "kaputt")
    assert coordinator._pv_forecast_today_remaining_kwh() is None


# ----- _house_combined_reading_kwh ------------------------------------------

async def test_house_combined_reading_kwh_nur_hausverbrauch(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hcr1", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    hass.states.async_set("sensor.haus", "1000.0")
    assert coordinator._house_combined_reading_kwh() == 1000.0


async def test_house_combined_reading_kwh_mit_speicher_addiert(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_BATTERY_CHARGE_ENTITY,
        CONF_HOME_CONSUMPTION_ENTITY,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hcr2",
        options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus", CONF_BATTERY_CHARGE_ENTITY: "sensor.speicher"},
    )
    hass.states.async_set("sensor.haus", "1000.0")
    hass.states.async_set("sensor.speicher", "200.0")
    assert coordinator._house_combined_reading_kwh() == 1200.0


async def test_house_combined_reading_kwh_defekter_speicherwert_wird_ignoriert(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_BATTERY_CHARGE_ENTITY,
        CONF_HOME_CONSUMPTION_ENTITY,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hcr3",
        options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus", CONF_BATTERY_CHARGE_ENTITY: "sensor.speicher"},
    )
    hass.states.async_set("sensor.haus", "1000.0")
    hass.states.async_set("sensor.speicher", "kaputt")
    assert coordinator._house_combined_reading_kwh() == 1000.0


async def test_house_combined_reading_kwh_ohne_hausverbrauchszaehler_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "hcr4")
    assert coordinator._house_combined_reading_kwh() is None


# ----- _update_house_usage_profile -------------------------------------------

async def test_update_house_usage_profile_erster_aufruf_setzt_nur_baseline(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup1", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    assert coordinator.data["house_periods"]["day"]["kwh"] == 1000.0
    assert coordinator.data["house_weekday_kwh_totals"] == {}
    assert coordinator.data["house_weekday_day_counts"] == {}


async def test_update_house_usage_profile_rollover_fuellt_genau_einen_wochentags_eimer(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup2", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    yesterday_wd = (dt_util.now().date() - timedelta(days=1)).weekday()
    # Rollover simulieren: anderer Perioden-Schluessel als beim ersten Aufruf.
    coordinator.data["house_periods"]["day"]["key"] = "ein-anderer-tag"
    hass.states.async_set("sensor.haus", "1015.0")
    coordinator._update_house_usage_profile()
    assert coordinator.data["house_weekday_kwh_totals"] == {str(yesterday_wd): 15.0}
    assert coordinator.data["house_weekday_day_counts"] == {str(yesterday_wd): 1}


async def test_update_house_usage_profile_unveraenderter_schluessel_aendert_eimer_nicht(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup3", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    hass.states.async_set("sensor.haus", "1005.0")
    coordinator._update_house_usage_profile()  # gleicher Perioden-Schluessel -- kein Rollover
    assert coordinator.data["house_weekday_kwh_totals"] == {}
    assert coordinator.data["house_weekday_day_counts"] == {}
    assert coordinator.data["house_periods"]["day"]["kwh"] == 1000.0


# ----- _house_kwh_used_today -------------------------------------------------

async def test_house_kwh_used_today_normalfall(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hkut1", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    coordinator.data["house_periods"] = {"day": {"key": "x", "kwh": 1000.0}}
    hass.states.async_set("sensor.haus", "1004.5")
    assert coordinator._house_kwh_used_today() == 4.5


async def test_house_kwh_used_today_ohne_baseline_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hkut2", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    hass.states.async_set("sensor.haus", "1004.5")
    assert coordinator._house_kwh_used_today() is None


async def test_house_kwh_used_today_negatives_delta_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hkut3", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    coordinator.data["house_periods"] = {"day": {"key": "x", "kwh": 1000.0}}
    hass.states.async_set("sensor.haus", "990.0")
    assert coordinator._house_kwh_used_today() is None


# ----- _house_remaining_today_kwh --------------------------------------------

async def test_house_remaining_today_kwh_mit_vollstaendigem_profil(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hrt1", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    today_wd = dt_util.now().date().weekday()
    coordinator.data["house_weekday_kwh_totals"] = {str(today_wd): 12.0}
    coordinator.data["house_weekday_day_counts"] = {str(today_wd): 1}
    coordinator.data["house_periods"] = {"day": {"key": "x", "kwh": 100.0}}
    hass.states.async_set("sensor.haus", "104.0")
    assert coordinator._house_remaining_today_kwh() == 8.0  # 12 - 4 bereits verbraucht


async def test_house_remaining_today_kwh_ohne_profil_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hrt2", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    assert coordinator._house_remaining_today_kwh() is None


async def test_house_remaining_today_kwh_heutiger_wochentag_fehlt_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hrt3", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    today_wd = dt_util.now().date().weekday()
    other_wd = (today_wd + 1) % 7
    coordinator.data["house_weekday_kwh_totals"] = {str(other_wd): 12.0}
    coordinator.data["house_weekday_day_counts"] = {str(other_wd): 1}
    assert coordinator._house_remaining_today_kwh() is None


# ----- house_usage_profile / house_usage_profile_includes_battery -----------

async def test_house_usage_profile_oeffentliche_methode_liefert_dasselbe_wie_intern_genutzt(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hup1", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    today_wd = dt_util.now().date().weekday()
    coordinator.data["house_weekday_kwh_totals"] = {str(today_wd): 9.0}
    coordinator.data["house_weekday_day_counts"] = {str(today_wd): 1}
    profile = coordinator.house_usage_profile()
    assert profile == {today_wd: 9.0}


async def test_house_usage_profile_ohne_beobachteten_tag_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hup2", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    assert coordinator.house_usage_profile() is None


async def test_house_usage_profile_includes_battery_mit_speicherentitaet(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_BATTERY_CHARGE_ENTITY,
        CONF_HOME_CONSUMPTION_ENTITY,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hib1",
        options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus", CONF_BATTERY_CHARGE_ENTITY: "sensor.speicher"},
    )
    assert coordinator.house_usage_profile_includes_battery() is True


async def test_house_usage_profile_includes_battery_ohne_speicherentitaet(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hib2", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    assert coordinator.house_usage_profile_includes_battery() is False


# ----- _evcc_mode_targets ----------------------------------------------------

async def test_evcc_mode_targets_ohne_jede_entitaet_roh_und_netto_identisch(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "emt1", options={CONF_USABLE_KWH: 50.0})
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    targets = coordinator._evcc_mode_targets()
    assert targets is not None
    assert targets["rest_heute_kwh"] == targets["rest_heute_roh_kwh"]
    assert targets["pv_fuer_auto_kwh"] == targets["pv_rest_heute_roh_kwh"] == 0.0
    assert targets["haus_rest_heute_kwh"] == 0.0


async def test_evcc_mode_targets_mit_pv_rest_reduziert_netto_bedarf(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_PV_FORECAST_TODAY_REMAINING_ENTITY,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt2",
        options={CONF_USABLE_KWH: 50.0, CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    hass.states.async_set("sensor.pv_rest", "4.0", {"unit_of_measurement": "kWh"})
    targets = coordinator._evcc_mode_targets()
    assert targets["pv_rest_heute_roh_kwh"] == 4.0
    assert targets["rest_heute_kwh"] < targets["rest_heute_roh_kwh"]


async def test_evcc_mode_targets_mit_hausverbrauch_reduziert_pv_fuer_auto(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_HOME_CONSUMPTION_ENTITY,
        CONF_PV_FORECAST_TODAY_REMAINING_ENTITY,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt3",
        options={
            CONF_USABLE_KWH: 50.0,
            CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest",
            CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus",
        },
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    hass.states.async_set("sensor.pv_rest", "4.0", {"unit_of_measurement": "kWh"})
    today_wd = dt_util.now().date().weekday()
    coordinator.data["house_weekday_kwh_totals"] = {str(today_wd): 3.0}
    coordinator.data["house_weekday_day_counts"] = {str(today_wd): 1}
    coordinator.data["house_periods"] = {"day": {"key": "x", "kwh": 100.0}}
    hass.states.async_set("sensor.haus", "100.0")
    targets = coordinator._evcc_mode_targets()
    assert targets["haus_rest_heute_kwh"] == 3.0
    assert targets["pv_fuer_auto_kwh"] < targets["pv_rest_heute_roh_kwh"]


async def test_evcc_mode_targets_ohne_usage_profile_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "emt4")
    coordinator._soc = 50.0
    assert coordinator._evcc_mode_targets() is None


# ----- _async_apply_evcc_mode_control ---------------------------------------

async def test_apply_evcc_mode_control_option_aus_ist_no_op(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "aemc1")
    _seed_usage_profile(coordinator)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()
    coordinator._evcc_client.async_set_mode.assert_not_called()
    coordinator._evcc_client.async_probe_scope.assert_not_called()


async def test_apply_evcc_mode_control_erste_aktivierung_schreibt_modus_und_beide_soc_werte(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc2", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{}]}

    await coordinator._async_apply_evcc_mode_control()

    # Min- und Ziel-SoC werden unabhaengig voneinander geprobt (siehe
    # coordinator.py::_evcc_scope()) -- zwei Probe-Aufrufe bei der ersten
    # Aktivierung, nicht einer.
    assert coordinator._evcc_client.async_probe_scope.await_count == 2
    coordinator._evcc_client.async_set_mode.assert_awaited_once()
    coordinator._evcc_client.async_set_min_soc.assert_awaited_once()
    coordinator._evcc_client.async_set_limit_soc.assert_awaited_once()
    assert coordinator.data["evcc_mode_control"] is not None
    assert "geschrieben_ts" in coordinator.data["evcc_mode_control"]


async def test_apply_evcc_mode_control_unveraenderte_empfehlung_schreibt_kein_zweites_mal(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc3", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{}]}

    await coordinator._async_apply_evcc_mode_control()
    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_awaited_once()
    assert coordinator._evcc_client.async_probe_scope.await_count == 2


async def test_apply_evcc_mode_control_schreibfehler_laesst_evcc_mode_control_unveraendert(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc4", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint", mode_ok=False)
    coordinator._evcc_state = {"loadpoints": [{}]}

    await coordinator._async_apply_evcc_mode_control()

    assert coordinator.data.get("evcc_mode_control") is None


async def test_apply_evcc_mode_control_kein_loadpoint_loggt_warning_ohne_crash(hass, coordinators, caplog):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc5", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_state = {"loadpoints": []}

    with caplog.at_level("WARNING"):
        await coordinator._async_apply_evcc_mode_control()

    assert any("kein Loadpoint gefunden" in r.message for r in caplog.records)
    coordinator._evcc_client.async_set_mode.assert_not_called()


async def test_apply_evcc_mode_control_ohne_usage_profile_ist_no_op(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc6", options={CONF_EVCC_MODE_CONTROL_ENABLED: True},
    )
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_state = {"loadpoints": [{}]}

    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_not_called()


async def test_apply_evcc_mode_control_zweiter_zyklus_nutzt_gecachten_scope(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc7", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()

    # Empfehlung aendert sich (SoC sinkt) -- neuer Schreibversuch, aber OHNE
    # erneute Probe, da der Scope bereits gecacht ist.
    coordinator._soc = 20.0
    await coordinator._async_apply_evcc_mode_control()

    assert coordinator._evcc_client.async_probe_scope.await_count == 2
    assert coordinator._evcc_client.async_set_mode.await_count == 2


async def test_apply_evcc_mode_control_probe_schlaegt_fehl_modus_wird_trotzdem_gesetzt_und_issue_angelegt(
    hass, coordinators,
):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
        DOMAIN,
    )

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "aemc8", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result=None)
    coordinator._evcc_state = {"loadpoints": [{}]}

    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_awaited_once()
    coordinator._evcc_client.async_set_min_soc.assert_not_called()
    coordinator._evcc_client.async_set_limit_soc.assert_not_called()
    issue = ir.async_get(hass).async_get_issue(DOMAIN, f"{entry.entry_id}_evcc_soc_scope_failed")
    assert issue is not None


async def test_apply_evcc_mode_control_repair_issue_verschwindet_nach_erfolgreichem_re_probe(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
        DOMAIN,
    )

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "aemc9", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result=None)
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()
    issue_id = f"{entry.entry_id}_evcc_soc_scope_failed"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # Scope-Cache manuell zuruecksetzen (simuliert eine erneute Aktivierung/
    # Options-Aenderung) und dieses Mal erfolgreich probieren.
    del coordinator.data["evcc_min_soc_scope"]
    del coordinator.data["evcc_limit_soc_scope"]
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._soc = 20.0  # Empfehlung aendern, damit ueberhaupt neu geschrieben wird
    await coordinator._async_apply_evcc_mode_control()

    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_apply_evcc_mode_control_soc_schreibfehler_mit_gecachtem_scope_re_probt_genau_einmal(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc10", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator.data["evcc_min_soc_scope"] = "loadpoint"  # bereits gecacht
    coordinator.data["evcc_limit_soc_scope"] = "loadpoint"  # bereits gecacht
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint", limit_soc_ok=False)
    coordinator._evcc_state = {"loadpoints": [{}]}

    await coordinator._async_apply_evcc_mode_control()

    # Nur der Ziel-SoC-Schreibversuch schlug fehl -> genau ein Re-Probe (fuer
    # limitsoc); der bereits gecachte min-Scope wird nicht erneut geprobt.
    coordinator._evcc_client.async_probe_scope.assert_awaited_once()


async def test_apply_evcc_mode_control_min_und_limit_soc_koennen_unterschiedliche_scopes_haben(hass, coordinators):
    """Regression fuer die reale evcc-0.314.5-Situation (siehe
    evcc_client.py::async_probe_scope()): limitSoc bleibt ueber den
    Loadpoint schreibbar, minSoc nur noch ueber das Fahrzeug -- beide
    Schreibversuche muessen trotzdem in einem Zyklus erfolgreich sein."""
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
        DOMAIN,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc11", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result=("vehicle", "loadpoint"))
    coordinator._evcc_state = {"loadpoints": [{}]}

    await coordinator._async_apply_evcc_mode_control()

    assert coordinator.data["evcc_min_soc_scope"] == "vehicle"
    assert coordinator.data["evcc_limit_soc_scope"] == "loadpoint"
    coordinator._evcc_client.async_set_min_soc.assert_awaited_once()
    coordinator._evcc_client.async_set_limit_soc.assert_awaited_once()
    assert coordinator.data["evcc_mode_control"] is not None
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"{coordinator.entry.entry_id}_evcc_soc_scope_failed") is None


# ----- _evcc_vehicle_api_key --------------------------------------------------

async def test_evcc_vehicle_api_key_matched_gegen_hersteller_modell(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "evak1",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter"},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}}
    assert coordinator._evcc_vehicle_api_key() == "db:8"


async def test_evcc_vehicle_api_key_matched_gegen_explizit_konfigurierten_titel(hass, coordinators):
    """CONF_EVCC_VEHICLE_NAME haelt den evcc-Anzeige-Titel (wie im evcc-UI
    sichtbar), nicht den internen Schluessel -- muss trotzdem gegen
    vehicles{} aufgeloest werden, um den Schluessel zu liefern (anders als
    _evcc_vehicle_key(), das den konfigurierten Titel direkt zurueckgibt)."""
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "evak2", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}}
    assert coordinator._evcc_vehicle_api_key() == "db:8"


async def test_evcc_vehicle_api_key_liefert_schluessel_nicht_titel(hass, coordinators):
    """Direkter Unterschied zu _evcc_vehicle_key(): dieselbe Konfiguration,
    aber der interne Schluessel statt des Titels."""
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "evak3", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}}
    assert coordinator._evcc_vehicle_key() == "eRifter"
    assert coordinator._evcc_vehicle_api_key() == "db:8"


async def test_evcc_vehicle_api_key_ohne_treffer_gibt_none(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "evak4",
        options={CONF_VEHICLE_HERSTELLER: "Tesla", CONF_VEHICLE_MODELL: "Model 3"},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}}
    assert coordinator._evcc_vehicle_api_key() is None


async def test_evcc_vehicle_api_key_ohne_evcc_state_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evak5")
    assert coordinator._evcc_vehicle_api_key() is None
