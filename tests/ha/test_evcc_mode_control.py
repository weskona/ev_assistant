"""Tests fuer die evcc-Modus-/SoC-Steuerung (CONF_EVCC_MODE_CONTROL_ENABLED,
siehe coordinator.py::_async_apply_evcc_mode_control()/_evcc_mode_targets())
sowie das dafuer optionale, einfache Haus-Nutzungsprofil
(_update_house_usage_profile() u.a.). Reine Berechnungslogik (engine.py::
determine_evcc_mode() etc.) ist bereits in tests/test_engine.py abgedeckt --
hier nur die HA-Verdrahtung (Entity-Lesen, Coordinator-Zustand, evcc-Client-
Schreibaufrufe, Repair-Issues)."""
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
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
    """Fuellt usage_profile() (Fahrtenbuch) UND vehicle_discharge_usage_
    profile() (Live-SoC) mit einem kontrollierbaren, vollstaendigen
    7-Tage-Profil (identischer Bedarf an jedem Wochentag) -- first_ts genau
    6 Tage in der Vergangenheit ergibt eine 7-Kalendertage-Spanne, in der
    jeder Wochentag GENAU EINMAL vorkommt, unabhaengig vom aktuellen
    Wochentag -- dadurch entspricht weekday_kwh_exact_totals direkt dem
    Ergebnis, ohne die Anzahl Vorkommen je Wochentag ausrechnen zu muessen.
    Seit der Entfernung des Fahrtenbuch-Fallbacks aus _effective_vehicle_
    usage_profile() (2026-09-23, siehe dortigen Docstring) braucht
    _evcc_mode_targets() zwingend das Live-SoC-Profil -- ohne das hier
    ebenfalls zu seeden, wuerde jeder Test, der sich (wie frueher genuegend)
    nur auf das Fahrtenbuch-Profil verlaesst, ploetzlich ins Leere laufen.
    usage_profile() bleibt zusaetzlich gefuellt, weil es unabhaengig davon
    noch fuer die fahrtenbuch-interne Ausreisser-Daempfung gebraucht wird
    (siehe coordinator.py::_apply_trip_baselines())."""
    coordinator.data["fahrtenbuch_first_ts"] = (dt_util.now() - timedelta(days=6)).timestamp()
    coordinator.data["weekday_kwh_exact_totals"] = {str(wd): weekday_kwh for wd in range(7)}
    coordinator.data["weekday_km_est_totals"] = {}
    coordinator.data["vehicle_discharge_weekday_days"] = {
        str(wd): [{"date": f"2020-01-{wd + 1:02d}", "kwh": weekday_kwh}] for wd in range(7)
    }
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
    # Wohlgeformter Default statt eines auto-generierten AsyncMock/MagicMock,
    # das _current_loadpoint() (z.B. ueber _check_evcc_manual_mode_session_
    # end(), von _refresh_evcc_state() nach jedem Schreibvorgang aufgerufen)
    # nicht als echtes dict lesen koennte.
    client.async_get_state = AsyncMock(return_value={"loadpoints": [], "vehicles": {}})
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
    assert coordinator.data["house_weekday_days"] == {}


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
    yesterday_iso = (dt_util.now().date() - timedelta(days=1)).isoformat()
    assert coordinator.data["house_weekday_days"] == {
        str(yesterday_wd): [{"date": yesterday_iso, "kwh": 15.0}],
    }


async def test_update_house_usage_profile_unveraenderter_schluessel_aendert_eimer_nicht(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup3", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    hass.states.async_set("sensor.haus", "1005.0")
    coordinator._update_house_usage_profile()  # gleicher Perioden-Schluessel -- kein Rollover
    assert coordinator.data["house_weekday_days"] == {}
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
    coordinator.data["house_weekday_days"] = {str(today_wd): [{"date": "2020-01-01", "kwh": 12.0}]}
    coordinator.data["house_periods"] = {"day": {"key": "x", "kwh": 100.0}}
    hass.states.async_set("sensor.haus", "104.0")
    # Fixe Tageszeit statt der echten Wanduhrzeit -- sonst waere die
    # Erwartung vom weichen Abbau (siehe engine.py::remaining_today_kwh())
    # abhaengig davon, wann genau der Test laeuft. 0.0 = alter, flacher
    # Vergleich (kein Abbau).
    coordinator._day_fraction_elapsed = lambda: 0.0
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
    coordinator.data["house_weekday_days"] = {str(other_wd): [{"date": "2020-01-01", "kwh": 12.0}]}
    assert coordinator._house_remaining_today_kwh() is None


# ----- house_usage_profile / house_usage_profile_includes_battery -----------

async def test_house_usage_profile_oeffentliche_methode_liefert_dasselbe_wie_intern_genutzt(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hup1", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    today_wd = dt_util.now().date().weekday()
    coordinator.data["house_weekday_days"] = {str(today_wd): [{"date": "2020-01-01", "kwh": 9.0}]}
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


# ----- _update_vehicle_discharge (Live-SoC-Ratchet) --------------------------

async def test_update_vehicle_discharge_erster_aufruf_initialisiert_ohne_buchung(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvd1", options={CONF_USABLE_KWH: 50.0})
    coordinator._update_vehicle_discharge(84.0)
    assert coordinator.data["vehicle_discharge_reference_soc"] == 84.0
    assert coordinator.data["vehicle_discharge_kwh_total"] == 0.0


def _confirm_pending(coordinator, seconds=61.0):
    """Testhilfe: laesst einen gerade gesetzten Rueckgangs-Kandidaten
    (vehicle_discharge_pending_since) so weit in der Vergangenheit
    erscheinen, dass der naechste _update_vehicle_discharge()-Aufruf mit
    demselben Wert ihn als bestaetigt bucht -- ohne echte Wartezeit im
    Test (siehe VEHICLE_DISCHARGE_CONFIRM_SECONDS)."""
    coordinator.data["vehicle_discharge_pending_since"] -= seconds


async def test_update_vehicle_discharge_einzelner_rueckgang_bucht_noch_nicht(hass, coordinators):
    """Ein einzelner Rueckgang darf nicht sofort gebucht werden -- das ist
    genau die Haertung gegen kurzzeitige SoC-Ausreisser."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvd2a", options={CONF_USABLE_KWH: 50.0})
    coordinator._update_vehicle_discharge(84.0)
    coordinator._update_vehicle_discharge(82.0)
    assert coordinator.data["vehicle_discharge_reference_soc"] == 84.0
    assert coordinator.data["vehicle_discharge_kwh_total"] == 0.0
    assert coordinator.data["vehicle_discharge_pending_soc"] == 82.0


async def test_update_vehicle_discharge_rueckgang_bucht_kwh_nach_bestaetigung(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvd2", options={CONF_USABLE_KWH: 50.0})
    coordinator._update_vehicle_discharge(84.0)
    coordinator._update_vehicle_discharge(82.0)
    _confirm_pending(coordinator)
    coordinator._update_vehicle_discharge(82.0)
    assert coordinator.data["vehicle_discharge_reference_soc"] == 82.0
    assert coordinator.data["vehicle_discharge_kwh_total"] == 1.0  # 2% von 50 kWh
    assert coordinator.data["vehicle_discharge_pending_soc"] is None


async def test_update_vehicle_discharge_kurzer_ausreisser_wird_nicht_gebucht(hass, coordinators):
    """Regressionstest fuer den Produktionsvorfall: ein SoC-Wert, der sich
    im naechsten Messwert bereits wieder erholt hat, darf NIE gebucht
    werden -- unabhaengig davon, wie lange spaeter der naechste Aufruf
    kommt."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvd2b", options={CONF_USABLE_KWH: 50.0})
    coordinator._update_vehicle_discharge(84.0)
    coordinator._update_vehicle_discharge(37.0)  # kurzzeitiger Ausreisser
    coordinator._update_vehicle_discharge(84.0)  # Erholung im naechsten Messwert
    assert coordinator.data["vehicle_discharge_reference_soc"] == 84.0
    assert coordinator.data["vehicle_discharge_kwh_total"] == 0.0
    assert coordinator.data["vehicle_discharge_pending_soc"] is None


async def test_update_vehicle_discharge_standby_zwischen_kurzfahrten_wird_erfasst(hass, coordinators):
    """Regression fuer den Ausloeser dieses Features: mehrere kurze Fahrten
    ohne SoC-Delta (grob meldender Sensor), aber ein echter Rueckgang WAEHREND
    der Standzeit dazwischen -- muss trotzdem im Akkumulator landen, auch
    wenn er in keiner einzelnen Fahrt als delta_soc auftaucht (jeweils nach
    Bestaetigung, siehe VEHICLE_DISCHARGE_CONFIRM_SECONDS)."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvd3", options={CONF_USABLE_KWH: 50.0})
    coordinator._update_vehicle_discharge(86.0)  # Fahrt 1 Start
    coordinator._update_vehicle_discharge(85.0)  # Fahrt 1 Ende (Kandidat)
    _confirm_pending(coordinator)
    coordinator._update_vehicle_discharge(85.0)  # bestaetigt: 0.5 kWh gebucht
    coordinator._update_vehicle_discharge(84.0)  # Standby-Rueckgang (Kandidat)
    _confirm_pending(coordinator)
    coordinator._update_vehicle_discharge(84.0)  # bestaetigt: weitere 0.5 kWh
    coordinator._update_vehicle_discharge(84.0)  # Fahrt 2 Start/Ende (kein Delta)
    assert coordinator.data["vehicle_discharge_kwh_total"] == 1.0


async def test_update_vehicle_discharge_anstieg_setzt_referenz_ohne_buchung(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvd4", options={CONF_USABLE_KWH: 50.0})
    coordinator._update_vehicle_discharge(82.0)
    coordinator._update_vehicle_discharge(90.0)
    assert coordinator.data["vehicle_discharge_reference_soc"] == 90.0
    assert coordinator.data["vehicle_discharge_kwh_total"] == 0.0


# ----- _periodic_check: bestaetigt haengengebliebene Kandidaten nach ------
# Regressionstest fuer einen echten Vorfall: das Fahrzeug meldete stunden-
# lang keinen neuen SoC-Wert, ein laengst bestaetigungsreifer Rueckgangs-
# Kandidat blieb dadurch unbegrenzt in der Schwebe (siehe VEHICLE_
# DISCHARGE_CONFIRM_SECONDS-Docstring). _periodic_check() speist seitdem
# den zuletzt bekannten SoC-Wert zusaetzlich alle 60s erneut ein.

async def test_periodic_check_bestaetigt_haengenden_kandidaten(hass, coordinators):
    from homeassistant.util import dt as dt_util

    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "pc1", options={CONF_USABLE_KWH: 50.0})
    coordinator._soc = 82.0
    coordinator._update_vehicle_discharge(82.0)
    coordinator._soc = 80.0
    coordinator._update_vehicle_discharge(80.0)  # Kandidat, noch nicht bestaetigt
    assert coordinator.data["vehicle_discharge_kwh_total"] == 0.0
    # Fahrzeug meldet sich stundenlang nicht mehr -- Kandidat "altert",
    # ohne dass ein neues Event ihn je erneut prueft.
    coordinator.data["vehicle_discharge_pending_since"] -= 3 * 3600
    await coordinator._periodic_check(dt_util.utcnow())
    assert coordinator.data["vehicle_discharge_reference_soc"] == 80.0
    assert coordinator.data["vehicle_discharge_kwh_total"] == 1.0  # 2% von 50 kWh
    assert coordinator.data["vehicle_discharge_pending_soc"] is None


async def test_periodic_check_ohne_soc_ist_no_op_fuers_discharge(hass, coordinators):
    from homeassistant.util import dt as dt_util

    coordinator, _ = await _make_coordinator(hass, coordinators, "pc2")
    assert coordinator._soc is None
    await coordinator._periodic_check(dt_util.utcnow())
    assert coordinator.data["vehicle_discharge_reference_soc"] is None


# ----- _update_vehicle_discharge_profile / vehicle_discharge_usage_profile ---

async def test_update_vehicle_discharge_profile_erster_aufruf_setzt_nur_baseline(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "uvdp1")
    coordinator.data["vehicle_discharge_kwh_total"] = 5.0
    coordinator._update_vehicle_discharge_profile()
    assert coordinator.data["vehicle_discharge_periods"]["day"]["kwh"] == 5.0
    assert coordinator.data["vehicle_discharge_weekday_days"] == {}


async def test_update_vehicle_discharge_profile_rollover_zaehlt_nur_den_tag_keine_kwh(hass, coordinators):
    """Seit der Bestaetigungs-Haertung (siehe VEHICLE_DISCHARGE_CONFIRM_
    SECONDS) bucht der taegliche Rollover KEINE echten kWh mehr um -- das
    passiert direkt bei Bestaetigung (siehe _book_vehicle_discharge_
    weekday() in test_urlaub_ausreisser.py) -- sondern legt nur noch
    einen Null-Fenster-Eintrag fuer den beobachteten Kalendertag an."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvdp2")
    coordinator.data["vehicle_discharge_kwh_total"] = 5.0
    coordinator._update_vehicle_discharge_profile()
    yesterday = dt_util.now().date() - timedelta(days=1)
    yesterday_wd = yesterday.weekday()
    coordinator.data["vehicle_discharge_periods"]["day"]["key"] = str(yesterday)
    coordinator.data["vehicle_discharge_kwh_total"] = 6.5
    coordinator._update_vehicle_discharge_profile()
    assert coordinator.data["vehicle_discharge_weekday_days"] == {
        str(yesterday_wd): [{"date": yesterday.isoformat(), "kwh": 0.0}],
    }


async def test_update_vehicle_discharge_profile_holt_uebersprungenen_tag_nach(hass, coordinators):
    """Regressionstest fuer einen echten Vorfall: _daily_lts_refresh() laeuft
    nur einmal taeglich um 00:05 Uhr ohne Nachhol-Mechanismus -- war HA
    genau dann nicht erreichbar, wird ein kompletter Kalendertag
    uebersprungen. Der naechste Rollover muss ALLE dazwischenliegenden
    Tage nachtragen, nicht nur den unmittelbar vorherigen, sonst bekommt
    ein Wochentag, dem _book_vehicle_discharge_weekday() bereits kWh
    gutgeschrieben hat, nie einen passenden Fenster-Eintrag (dauerhaft
    verwaiste Summe)."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    coordinator, _ = await _make_coordinator(hass, coordinators, "uvdp3")
    coordinator.data["vehicle_discharge_kwh_total"] = 5.0
    coordinator._update_vehicle_discharge_profile()
    # Zwei Tage werden uebersprungen (kein Rollover lief in der Zwischenzeit).
    drei_tage_zurueck = dt_util.now().date() - timedelta(days=3)
    coordinator.data["vehicle_discharge_periods"]["day"]["key"] = str(drei_tage_zurueck)
    coordinator.data["vehicle_discharge_kwh_total"] = 6.5
    coordinator._update_vehicle_discharge_profile()
    weekday_days = coordinator.data["vehicle_discharge_weekday_days"]
    erwartete_tage = [drei_tage_zurueck + timedelta(days=i) for i in range(3)]
    gefundene_tage = 0
    for tag in erwartete_tage:
        eintraege = weekday_days.get(str(tag.weekday()), [])
        match = next((e for e in eintraege if e["date"] == tag.isoformat()), None)
        assert match is not None
        assert match["kwh"] == 0.0
        gefundene_tage += 1
    assert gefundene_tage == 3


async def test_vehicle_discharge_usage_profile_ohne_beobachteten_tag_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "vdup1")
    assert coordinator.vehicle_discharge_usage_profile() is None


async def test_vehicle_discharge_usage_profile_normale_durchschnittsbildung(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "vdup2")
    coordinator.data["vehicle_discharge_weekday_days"] = {
        "2": [{"date": "2020-01-01", "kwh": 4.0}, {"date": "2020-01-08", "kwh": 0.0}],
    }
    assert coordinator.vehicle_discharge_usage_profile() == {2: 2.0}


# ----- _vehicle_discharge_kwh_used_today --------------------------------------

async def test_vehicle_discharge_kwh_used_today_normalfall(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "vdkut1")
    coordinator.data["vehicle_discharge_periods"] = {"day": {"key": "x", "kwh": 5.0}}
    coordinator.data["vehicle_discharge_kwh_total"] = 6.5
    assert coordinator._vehicle_discharge_kwh_used_today() == 1.5


async def test_vehicle_discharge_kwh_used_today_ohne_baseline_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "vdkut2")
    coordinator.data["vehicle_discharge_kwh_total"] = 6.5
    assert coordinator._vehicle_discharge_kwh_used_today() is None


# ----- _effective_vehicle_usage_profile ---------------------------------------
# Nutzerentscheidung 2026-09-23: der vormalige Fahrtenbuch-Fallback (fuer
# Wochentage ohne Live-SoC-Daten, z.B. in den ersten 1-2 Wochen nach
# Einrichtung) wurde ersatzlos gestrichen -- er schloss Urlaubstage nicht
# aus (anders als der Live-Tracker) und haette so ausgerechnet die
# allerersten Profilwerte verzerren koennen. "der nutzer weiss ja, es
# dauert 2 wochen bis er die ersten werte bekommt". _effective_vehicle_
# usage_profile() ist seitdem ein reines Pass-Through auf
# vehicle_discharge_usage_profile().

async def test_effective_vehicle_usage_profile_ist_reines_discharge_profil(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evup1")
    _seed_usage_profile(coordinator, weekday_kwh=10.0)  # Fahrtenbuch, darf keine Rolle mehr spielen
    today_wd = dt_util.now().date().weekday()
    coordinator.data["vehicle_discharge_weekday_days"] = {str(today_wd): [{"date": "2020-01-01", "kwh": 3.0}]}
    profile = coordinator._effective_vehicle_usage_profile()
    assert profile == {today_wd: 3.0}  # NUR der beobachtete Wochentag, kein Fahrtenbuch-Fallback


async def test_effective_vehicle_usage_profile_ohne_discharge_gibt_none_trotz_fahrtenbuch(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evup2")
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    # _seed_usage_profile() seedet standardmaessig BEIDE Quellen -- hier
    # gezielt nur das Live-SoC-Profil wieder leeren, um "Fahrtenbuch hat
    # Daten, Live-Tracker (noch) nicht" zu simulieren.
    coordinator.data["vehicle_discharge_weekday_days"] = {}
    assert coordinator._effective_vehicle_usage_profile() is None


async def test_effective_vehicle_usage_profile_ohne_jede_quelle_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "evup3")
    assert coordinator._effective_vehicle_usage_profile() is None


# ----- _evcc_mode_targets ----------------------------------------------------

async def test_evcc_mode_targets_ohne_jede_entitaet_roh_und_netto_identisch(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "emt1", options={CONF_USABLE_KWH: 50.0})
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    # Fixe Tageszeit statt echter Wanduhrzeit (siehe engine.py::
    # remaining_today_kwh()-Abbau) -- sonst waeren absolute Erwartungen in
    # diesem und den folgenden _evcc_mode_targets()-Tests vom Testzeitpunkt
    # abhaengig.
    coordinator._day_fraction_elapsed = lambda: 0.0
    targets = coordinator._evcc_mode_targets()
    assert targets is not None
    assert targets["rest_heute_kwh"] == targets["rest_heute_roh_kwh"]
    assert targets["pv_fuer_auto_kwh"] == targets["pv_rest_heute_roh_kwh"] == 0.0
    assert targets["haus_rest_heute_kwh"] == 0.0
    assert targets["pv_ueberschuss_puffer_kwh"] == 0.0


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
    coordinator._day_fraction_elapsed = lambda: 0.0
    hass.states.async_set("sensor.pv_rest", "4.0", {"unit_of_measurement": "kWh"})
    targets = coordinator._evcc_mode_targets()
    assert targets["pv_rest_heute_roh_kwh"] == 4.0
    assert targets["rest_heute_kwh"] < targets["rest_heute_roh_kwh"]


async def test_evcc_mode_targets_pv_ueberschuss_reduziert_min_und_target(hass, coordinators):
    """Produktionsvorfall 2026-09-24: Fahrzeug lud nachts durch, obwohl
    tagsueber reichlich PV fuer den kompletten Rest-Bedarf zu erwarten war
    -- der heutige PV-Ueberschuss (ueber den heutigen Bedarf hinaus) muss
    auch min_kwh/target_kwh (morgen/uebermorgen) reduzieren, nicht nur
    rest_heute."""
    from custom_components.ev_assistant.const import (
        CONF_PV_FORECAST_TODAY_REMAINING_ENTITY,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_ueberschuss1",
        options={CONF_USABLE_KWH: 50.0, CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)  # jeder Wochentag 10 kWh
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    # Heutiger Bedarf 10 kWh, PV-Prognose 15 kWh -> 5 kWh Ueberschuss uebrig.
    hass.states.async_set("sensor.pv_rest", "15.0", {"unit_of_measurement": "kWh"})
    targets = coordinator._evcc_mode_targets()
    assert targets["rest_heute_kwh"] == 0.0  # heutiger Bedarf schon gedeckt
    assert targets["pv_ueberschuss_puffer_kwh"] == 5.0
    # min_raw = (0 + morgen 10) - 5 Ueberschuss = 5 -> * 1.2 Puffer = 6.0
    assert targets["min_kwh"] == 6.0
    # target_raw = (0 + morgen+uebermorgen 20) - 5 Ueberschuss = 15 -> * 1.2 = 18.0
    assert targets["target_kwh"] == 18.0
    assert targets["min_kwh"] <= targets["target_kwh"]


async def test_evcc_mode_targets_grosser_pv_ueberschuss_deckt_gesamten_puffer(hass, coordinators):
    """Reicht der heutige PV-Ueberschuss fuer den kompletten Zwei-Tage-
    Puffer, faellt der Modus zurueck auf "pv" statt "minpv"/"now" -- exakt
    das eigentliche Nutzer-Szenario (Speicher/Auto luden nachts durch,
    obwohl tagsueber genug PV fuer Rest-Bedarf inkl. eines
    verbrauchsstarken Tages im Fenster zu erwarten war)."""
    from custom_components.ev_assistant.const import (
        CONF_PV_FORECAST_TODAY_REMAINING_ENTITY,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_ueberschuss2",
        options={CONF_USABLE_KWH: 50.0, CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest"},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    # 50 kWh PV-Prognose decken heute (10) + den kompletten Zwei-Tage-Puffer
    # (20) locker ab.
    hass.states.async_set("sensor.pv_rest", "50.0", {"unit_of_measurement": "kWh"})
    targets = coordinator._evcc_mode_targets()
    assert targets["min_kwh"] == 0.0
    assert targets["target_kwh"] == 0.0
    assert targets["modus"] == "pv"


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
    coordinator._day_fraction_elapsed = lambda: 0.0
    hass.states.async_set("sensor.pv_rest", "4.0", {"unit_of_measurement": "kWh"})
    today_wd = dt_util.now().date().weekday()
    coordinator.data["house_weekday_days"] = {str(today_wd): [{"date": "2020-01-01", "kwh": 3.0}]}
    coordinator.data["house_periods"] = {"day": {"key": "x", "kwh": 100.0}}
    hass.states.async_set("sensor.haus", "100.0")
    targets = coordinator._evcc_mode_targets()
    assert targets["haus_rest_heute_kwh"] == 3.0
    assert targets["pv_fuer_auto_kwh"] < targets["pv_rest_heute_roh_kwh"]


async def test_evcc_mode_targets_bevorzugt_discharge_basiertes_used_today(hass, coordinators):
    """Kernszenario dieses Features: die Fahrtenbuch-basierte
    _kwh_used_today() wuerde hier 0.0 liefern (kein Odometer-Tracking
    gesetzt), obwohl der Live-SoC-Tracker bereits 2.0 kWh Verbrauch fuer
    heute kennt -- _evcc_mode_targets() muss den praeziseren Wert nutzen."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "emt_disc1", options={CONF_USABLE_KWH: 50.0})
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    coordinator.data["vehicle_discharge_periods"] = {"day": {"key": "x", "kwh": 5.0}}
    coordinator.data["vehicle_discharge_kwh_total"] = 7.0  # 2.0 kWh heute schon verbraucht
    targets = coordinator._evcc_mode_targets()
    assert targets["rest_heute_roh_kwh"] == 8.0  # 10.0 - 2.0, nicht 10.0 - 0.0


async def test_evcc_mode_targets_ohne_usage_profile_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "emt4")
    coordinator._soc = 50.0
    assert coordinator._evcc_mode_targets() is None


async def test_evcc_mode_targets_nutzt_day_fraction_elapsed_fuer_weichen_abbau(hass, coordinators):
    """Produktionsfall 2026-09-23: "der soc ist bei knapp 44%. haben 20:00
    uhr. da muss doch nix mehr nachgeladen werden" -- _evcc_mode_targets()
    muss _day_fraction_elapsed() tatsaechlich an remaining_today_kwh()
    durchreichen, nicht nur pur in engine.py vorhanden sein."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "emt_taper", options={CONF_USABLE_KWH: 50.0})
    _seed_usage_profile(coordinator, weekday_kwh=15.0)
    coordinator._soc = 50.0
    coordinator.data["vehicle_discharge_periods"] = {"day": {"key": "x", "kwh": 5.0}}
    coordinator.data["vehicle_discharge_kwh_total"] = 17.5  # 17.5 - 5.0 = 12.5 kWh heute schon verbraucht

    coordinator._day_fraction_elapsed = lambda: 0.0
    targets_frueh = coordinator._evcc_mode_targets()
    assert targets_frueh["rest_heute_roh_kwh"] == 2.5  # 15 - 12.5, kein Abbau

    coordinator._day_fraction_elapsed = lambda: 20 / 24  # 20 Uhr
    targets_abends = coordinator._evcc_mode_targets()
    assert targets_abends["rest_heute_roh_kwh"] == 0.0  # 15*4/24=2.5, minus 12.5 -> geklammert


# ----- _evcc_mode_targets: wirtschaftliche Kappung der Echtzeit-PV-
# Uebersteuerung (Nutzerwunsch 2026-09-24: "ich würde schon netzstrom dazu
# nehmen, aber nur wenn wirtschaftlich passt") -----------------------------

async def test_evcc_mode_targets_wirtschaftliche_kappung_verhindert_minpv(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_REALTIME_OVERRIDE_MIN_SOLAR_SHARE,
        CONF_USABLE_KWH,
        CONF_WALLBOX_MIN_POWER_W,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_kappung1",
        options={
            CONF_USABLE_KWH: 50.0,
            CONF_WALLBOX_MIN_POWER_W: 1380.0,
            CONF_EVCC_REALTIME_OVERRIDE_MIN_SOLAR_SHARE: 50.0,
        },
    )
    _seed_usage_profile(coordinator, weekday_kwh=1.0)  # winziger Bedarf -> Tageslogik bleibt "pv"
    coordinator._soc = 90.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    coordinator._evcc_state = {
        "loadpoints": [{}],
        "gridPower": -500.0,  # 500 W Ueberschuss
        "tariffFeedIn": 0.081,
        "tariffGrid": 0.298,
    }
    targets = coordinator._evcc_mode_targets()
    assert targets["modus"] == "pv"
    # Ohne Kappung waere 500W < 1380W ein "minpv"-Kandidat -- der Mischpreis
    # (~0.2194, ~36% Solaranteil) liegt aber unter der bei 50% Mindest-
    # Solaranteil live berechneten Obergrenze (0.1895).
    assert targets["modus_effektiv"] == "pv"
    assert targets["pv_override_mischpreis_kwh"] == round((500 * 0.081 + 880 * 0.298) / 1380.0, 4)
    assert targets["pv_override_max_mischpreis_kwh"] == round((0.081 + 0.298) / 2, 4)
    assert targets["wallbox_min_power_w"] == 1380.0


async def test_evcc_mode_targets_wirtschaftliche_kappung_erlaubt_minpv(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_REALTIME_OVERRIDE_MIN_SOLAR_SHARE,
        CONF_USABLE_KWH,
        CONF_WALLBOX_MIN_POWER_W,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_kappung2",
        options={
            CONF_USABLE_KWH: 50.0,
            CONF_WALLBOX_MIN_POWER_W: 1380.0,
            CONF_EVCC_REALTIME_OVERRIDE_MIN_SOLAR_SHARE: 20.0,
        },
    )
    _seed_usage_profile(coordinator, weekday_kwh=1.0)
    coordinator._soc = 90.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    coordinator._evcc_state = {
        "loadpoints": [{}],
        "gridPower": -500.0,
        "tariffFeedIn": 0.081,
        "tariffGrid": 0.298,
    }
    targets = coordinator._evcc_mode_targets()
    # 20% Mindest-Solaranteil -> Obergrenze 0.2546, der tatsaechliche
    # Mischpreis (~0.2194, ~36% Solaranteil) liegt darunter -> erlaubt.
    assert targets["modus_effektiv"] == "minpv"


async def test_evcc_mode_targets_ohne_kappungswert_bleibt_reine_watt_schwelle(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH, CONF_WALLBOX_MIN_POWER_W

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_kappung3",
        options={CONF_USABLE_KWH: 50.0, CONF_WALLBOX_MIN_POWER_W: 1380.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=1.0)
    coordinator._soc = 90.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    coordinator._evcc_state = {
        "loadpoints": [{}],
        "gridPower": -500.0,
        "tariffFeedIn": 0.081,
        "tariffGrid": 0.298,
    }
    targets = coordinator._evcc_mode_targets()
    # Keine Kappung konfiguriert -- unveraendertes Watt-Verhalten (minpv),
    # der Mischpreis wird aber trotzdem zur Transparenz mit ausgegeben.
    assert targets["modus_effektiv"] == "minpv"
    assert targets["pv_override_mischpreis_kwh"] == round((500 * 0.081 + 880 * 0.298) / 1380.0, 4)
    assert targets["pv_override_max_mischpreis_kwh"] is None


async def test_evcc_mode_targets_ohne_tarife_kein_mischpreis(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_REALTIME_OVERRIDE_MIN_SOLAR_SHARE,
        CONF_USABLE_KWH,
        CONF_WALLBOX_MIN_POWER_W,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_kappung4",
        options={
            CONF_USABLE_KWH: 50.0,
            CONF_WALLBOX_MIN_POWER_W: 1380.0,
            CONF_EVCC_REALTIME_OVERRIDE_MIN_SOLAR_SHARE: 50.0,
        },
    )
    _seed_usage_profile(coordinator, weekday_kwh=1.0)
    coordinator._soc = 90.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    # evcc meldet keine Tarife -- Kappung kann nicht greifen, reine
    # Watt-Schwelle bleibt wirksam, kein Mischpreis anzeigbar.
    coordinator._evcc_state = {"loadpoints": [{}], "gridPower": -500.0}
    targets = coordinator._evcc_mode_targets()
    assert targets["modus_effektiv"] == "minpv"
    assert targets["pv_override_mischpreis_kwh"] is None
    assert targets["pv_override_max_mischpreis_kwh"] is None


# ----- _usage_profile_buffer_pct / async_set_usage_profile_buffer_pct ------
# Schieberegler in der Wallbox-Karte (Uebersicht-Beta) -- der Override lebt
# bewusst in self.data statt in entry.options, siehe Docstring: eine
# Options-Aenderung wuerde per Update-Listener einen vollen Reload der
# Integration ausloesen.

async def test_usage_profile_buffer_pct_ohne_override_gibt_konfigurierten_wert(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USAGE_PROFILE_BUFFER_PCT

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "upbp1", options={CONF_USAGE_PROFILE_BUFFER_PCT: 30.0},
    )
    assert coordinator._usage_profile_buffer_pct() == 30.0


async def test_usage_profile_buffer_pct_ohne_konfiguration_gibt_default(hass, coordinators):
    from custom_components.ev_assistant.const import DEFAULT_USAGE_PROFILE_BUFFER_PCT

    coordinator, _ = await _make_coordinator(hass, coordinators, "upbp2")
    assert coordinator._usage_profile_buffer_pct() == DEFAULT_USAGE_PROFILE_BUFFER_PCT


async def test_set_usage_profile_buffer_pct_override_hat_vorrang(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USAGE_PROFILE_BUFFER_PCT

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "upbp3", options={CONF_USAGE_PROFILE_BUFFER_PCT: 30.0},
    )
    await coordinator.async_set_usage_profile_buffer_pct(45.0)
    assert coordinator._usage_profile_buffer_pct() == 45.0
    # entry.options selbst bleibt unveraendert -- kein Reload ausgeloest.
    assert coordinator.entry.options[CONF_USAGE_PROFILE_BUFFER_PCT] == 30.0


async def test_set_usage_profile_buffer_pct_wird_geklemmt(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "upbp4")
    await coordinator.async_set_usage_profile_buffer_pct(150.0)
    assert coordinator._usage_profile_buffer_pct() == 100.0
    await coordinator.async_set_usage_profile_buffer_pct(-10.0)
    assert coordinator._usage_profile_buffer_pct() == 0.0


async def test_set_usage_profile_buffer_pct_none_setzt_zurueck(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_USAGE_PROFILE_BUFFER_PCT

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "upbp5", options={CONF_USAGE_PROFILE_BUFFER_PCT: 30.0},
    )
    await coordinator.async_set_usage_profile_buffer_pct(45.0)
    assert coordinator._usage_profile_buffer_pct() == 45.0
    await coordinator.async_set_usage_profile_buffer_pct(None)
    assert coordinator._usage_profile_buffer_pct() == 30.0


async def test_set_usage_profile_buffer_pct_wirkt_sich_auf_usage_profile_tomorrow_aus(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "upbp6")
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    await coordinator.async_set_usage_profile_buffer_pct(50.0)
    need = coordinator.usage_profile_tomorrow()
    assert need["puffer_prozent"] == 50.0
    assert need["benoetigt_kwh"] == 15.0  # 10 kWh * 1.5


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
    # evcc-Live-Zustand jetzt so tun, als haette der erste Schreibvorgang
    # tatsaechlich gewirkt (siehe _async_apply_evcc_mode_control()-
    # Docstring: seit dem Live-Zustand-Abgleich muss der Loadpoint den
    # geschriebenen Stand auch widerspiegeln, sonst wuerde JEDER Zyklus
    # erneut schreiben, unabhaengig von einer unveraenderten Empfehlung).
    written = coordinator.data["evcc_mode_control"]
    coordinator._evcc_state = {
        "loadpoints": [{
            "mode": written["modus"],
            "effectiveMinSoc": written["min_soc"],
            "effectiveLimitSoc": written["target_soc"],
        }],
    }
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


async def test_apply_evcc_mode_control_evcc_live_zustand_weicht_ab_schreibt_erneut(hass, coordinators):
    """Kernszenario des Live-Zustand-Abgleichs (Produktionsfeedback
    2026-09-18): evcc hat den zuletzt geschriebenen Modus/SoC verloren
    (z.B. Addon-Neustart faellt auf den evcc-eigenen Konfig-Default
    zurueck), OBWOHL sich die eigene Empfehlung nicht geaendert hat -- ein
    reiner Vergleich gegen den eigenen Schreib-Cache (self.data
    ["evcc_mode_control"]) wuerde das nie bemerken und z.B. eine faellige
    woechentliche Vollladung dauerhaft blockieren."""
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc12", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()
    coordinator._evcc_client.async_set_mode.assert_awaited_once()

    # evcc "vergisst" den geschriebenen Stand wieder (z.B. Addon-Neustart) --
    # die eigene Empfehlung (SoC/Profil) bleibt dabei UNVERAENDERT.
    coordinator._evcc_state = {"loadpoints": [{"mode": "off", "effectiveMinSoc": 0, "effectiveLimitSoc": 80}]}
    await coordinator._async_apply_evcc_mode_control()

    assert coordinator._evcc_client.async_set_mode.await_count == 2


async def test_apply_evcc_mode_control_evcc_live_zustand_stimmt_ueberein_kein_erneutes_schreiben(hass, coordinators):
    """Gegenprobe zu obigem Test: stimmt der evcc-Live-Zustand bereits mit
    der (unveraenderten) Empfehlung ueberein, wird trotz vorhandenem
    Loadpoint-Objekt nicht erneut geschrieben."""
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc13", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()
    written = coordinator.data["evcc_mode_control"]

    coordinator._evcc_state = {
        "loadpoints": [{
            "mode": written["modus"],
            "effectiveMinSoc": written["min_soc"],
            "effectiveLimitSoc": written["target_soc"],
        }],
    }
    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_awaited_once()


async def test_apply_evcc_mode_control_pause_unterdrueckt_schreiben(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc14", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{"mode": "off", "effectiveMinSoc": 0, "effectiveLimitSoc": 80}]}

    await coordinator.async_set_evcc_mode_control_pause(True)
    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_not_called()


async def test_apply_evcc_mode_control_pause_wieder_ausgeschaltet_schreibt_wieder(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc15", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{"mode": "off", "effectiveMinSoc": 0, "effectiveLimitSoc": 80}]}

    await coordinator.async_set_evcc_mode_control_pause(True)
    await coordinator.async_set_evcc_mode_control_pause(False)
    assert coordinator.data.get("evcc_mode_control_paused") is False
    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_awaited_once()


async def test_set_evcc_mode_control_pause_setzt_und_loescht_flag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "aemc16")
    await coordinator.async_set_evcc_mode_control_pause(True)
    assert coordinator.data["evcc_mode_control_paused"] is True
    await coordinator.async_set_evcc_mode_control_pause(False)
    assert coordinator.data["evcc_mode_control_paused"] is False


# ----- evcc-Ladeplan (Zielzeit-Laden) ----------------------------------------

async def test_evcc_charge_plan_status_ohne_plan_gibt_none(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "ecp1")
    coordinator._evcc_state = {"loadpoints": [{"effectivePlanTime": None, "planTime": None}]}
    assert coordinator._evcc_charge_plan_status() is None
    assert coordinator._evcc_charge_plan_active() is False


async def test_evcc_charge_plan_status_mit_plan_liest_live_felder(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "ecp2")
    coordinator._evcc_state = {
        "loadpoints": [{
            "effectivePlanTime": "2026-09-19T06:00:00Z",
            "effectivePlanSoc": 80,
            "planProjectedStart": "2026-09-19T04:48:00+02:00",
            "planProjectedEnd": "2026-09-19T06:00:00+02:00",
            "planActive": True,
        }],
    }
    status = coordinator._evcc_charge_plan_status()
    assert status == {
        "target_time": "2026-09-19T06:00:00Z",
        "target_soc": 80,
        "projected_start": "2026-09-19T04:48:00+02:00",
        "projected_end": "2026-09-19T06:00:00+02:00",
        "aktiv": True,
    }
    assert coordinator._evcc_charge_plan_active() is True


async def test_apply_evcc_mode_control_charge_plan_aktiv_unterdrueckt_schreiben(hass, coordinators):
    """Kernszenario: ein aktiver evcc-Ladeplan (egal ob per ev_assistant
    oder direkt in evccs eigener Oberflaeche gesetzt) pausiert die
    profilbasierte Modus-/SoC-Steuerung, damit sich beide nicht in die
    Quere kommen (Nutzerentscheidung 2026-09-19)."""
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecp3", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {
        "loadpoints": [{
            "mode": "off", "effectiveMinSoc": 0, "effectiveLimitSoc": 80,
            "effectivePlanTime": "2026-09-19T06:00:00Z", "effectivePlanSoc": 80,
        }],
    }

    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_not_called()


async def test_async_set_evcc_charge_plan_ruft_client_mit_rfc3339_zeit_auf(hass, coordinators):
    from datetime import datetime, timezone

    from custom_components.ev_assistant.const import CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecp4",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter"},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_client.async_set_vehicle_plan_soc = AsyncMock(return_value=True)

    target_time = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    ok = await coordinator.async_set_evcc_charge_plan(80, target_time)

    assert ok is True
    coordinator._evcc_client.async_set_vehicle_plan_soc.assert_awaited_once_with(
        "db:8", 80, "2026-09-19T12:00:00Z"
    )


async def test_async_set_evcc_charge_plan_ohne_vehicle_key_gibt_false(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "ecp5")
    coordinator._evcc_client = _fake_evcc_client()

    ok = await coordinator.async_set_evcc_charge_plan(80, 1789833600.0)

    assert ok is False
    coordinator._evcc_client.async_set_vehicle_plan_soc.assert_not_called()


async def test_async_set_evcc_charge_plan_klemmt_unerreichbares_ziel(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecp7",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter", CONF_USABLE_KWH: 50.0},
    )
    coordinator._soc = 20.0  # 10 kWh verfuegbar
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter"}},
        # chargerSinglePhase: True -- echte 1-phasige Hardware-Grenze
        # (siehe _evcc_max_charge_power_kw()-Docstring, sonst wuerde ein
        # 1p3p-faehiger Lader mit 3 Phasen/Best-Case gerechnet).
        "loadpoints": [{"effectiveMaxCurrent": 16, "chargerSinglePhase": True}],  # 3,68 kW
    }
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_client.async_set_vehicle_plan_soc = AsyncMock(return_value=True)

    # Nur 1h Zeit -> max. 10 + 3,68 = 13,68 kWh -> 27% (bei 50 kWh nutzbar).
    target_time = dt_util.utcnow().timestamp() + 3600
    ok = await coordinator.async_set_evcc_charge_plan(90, target_time)

    assert ok is True
    args, _ = coordinator._evcc_client.async_set_vehicle_plan_soc.call_args
    assert args[1] == 27  # gekappt statt der angefragten 90%


async def test_async_set_evcc_charge_plan_erreichbares_ziel_bleibt_unveraendert(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecp8",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter", CONF_USABLE_KWH: 50.0},
    )
    coordinator._soc = 20.0
    coordinator._evcc_state = {
        "vehicles": {"db:8": {"title": "eRifter"}},
        # Kein phasesConfigured/chargerSinglePhase -- 1p3p-faehiger Lader
        # ohne feste Konfiguration, also 3 Phasen als Best-Case (Default).
        "loadpoints": [{"effectiveMaxCurrent": 16}],  # 11 kW
    }
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_client.async_set_vehicle_plan_soc = AsyncMock(return_value=True)

    # 5h bei 11kW -> 55 kWh moeglich, mehr als genug fuer 80%.
    target_time = dt_util.utcnow().timestamp() + 5 * 3600
    ok = await coordinator.async_set_evcc_charge_plan(80, target_time)

    assert ok is True
    args, _ = coordinator._evcc_client.async_set_vehicle_plan_soc.call_args
    assert args[1] == 80


async def test_evcc_max_charge_power_kw_phasenauswahl(hass, coordinators):
    """_evcc_max_charge_power_kw(): phasesConfigured (fest) > chargerSinglePhase
    (Hardware-Grenze) > Default 3 Phasen (1p3p-faehiger Lader ohne feste
    Konfiguration) -- siehe Docstring / Produktionsvorfall 2026-09-22."""
    from custom_components.ev_assistant.const import CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecp10",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter"},
    )

    # phasesConfigured fest auf 1 -> 16A * 1 * 230V = 3,68 kW, auch wenn
    # chargerSinglePhase/phasesActive etwas anderes sagen wuerden.
    coordinator._evcc_state = {
        "loadpoints": [{
            "effectiveMaxCurrent": 16,
            "phasesConfigured": 1,
            "chargerSinglePhase": False,
            "phasesActive": 3,
        }]
    }
    assert coordinator._evcc_max_charge_power_kw() == pytest.approx(3.68)

    # phasesConfigured fest auf 3 -> 16A * 3 * 230V = 11,04 kW.
    coordinator._evcc_state = {
        "loadpoints": [{"effectiveMaxCurrent": 16, "phasesConfigured": 3}]
    }
    assert coordinator._evcc_max_charge_power_kw() == pytest.approx(11.04)

    # phasesConfigured 0 (= auto/flexibel) + chargerSinglePhase True -> Lader
    # kann hardwareseitig nur 1 Phase, unabhaengig vom momentanen phasesActive.
    coordinator._evcc_state = {
        "loadpoints": [{
            "effectiveMaxCurrent": 16,
            "phasesConfigured": 0,
            "chargerSinglePhase": True,
            "phasesActive": 1,
        }]
    }
    assert coordinator._evcc_max_charge_power_kw() == pytest.approx(3.68)

    # phasesConfigured 0, kein chargerSinglePhase (1p3p-faehig, "auto") ->
    # Best-Case 3 Phasen, AUCH WENN phasesActive gerade nur 1 zeigt (weil
    # momentan nicht geladen wird -- das war genau der Bug).
    coordinator._evcc_state = {
        "loadpoints": [{
            "effectiveMaxCurrent": 16,
            "phasesConfigured": 0,
            "chargerSinglePhase": False,
            "phasesActive": 1,
        }]
    }
    assert coordinator._evcc_max_charge_power_kw() == pytest.approx(11.04)


async def test_async_set_evcc_charge_plan_ohne_max_power_keine_pruefung(hass, coordinators):
    # Loadpoint ohne effectiveMaxCurrent/maxCurrent (z.B. aeltere evcc-
    # Version oder Feld noch nicht befuellt) -- konservativ KEINE Kappung.
    from custom_components.ev_assistant.const import CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecp9",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter"},
    )
    coordinator._soc = 20.0
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_client.async_set_vehicle_plan_soc = AsyncMock(return_value=True)

    target_time = dt_util.utcnow().timestamp() + 3600
    ok = await coordinator.async_set_evcc_charge_plan(90, target_time)

    assert ok is True
    args, _ = coordinator._evcc_client.async_set_vehicle_plan_soc.call_args
    assert args[1] == 90


async def test_async_clear_evcc_charge_plan_ruft_client_auf(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecp6",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter"},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_client.async_clear_vehicle_plan_soc = AsyncMock(return_value=True)

    ok = await coordinator.async_clear_evcc_charge_plan()

    assert ok is True
    coordinator._evcc_client.async_clear_vehicle_plan_soc.assert_awaited_once_with("db:8")


# ----- async_set_evcc_charge_plan_range_km -----------------------------------

async def test_async_set_evcc_charge_plan_range_km_rechnet_um_und_ruft_client_auf(hass, coordinators):
    from datetime import datetime, timezone

    from custom_components.ev_assistant.const import (
        CONF_USABLE_KWH,
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecpkm1",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter", CONF_USABLE_KWH: 50.0},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_client.async_set_vehicle_plan_soc = AsyncMock(return_value=True)
    # 15 kWh/100km fest vorgeben -- 200 km -> 30 kWh -> bei 50 kWh nutzbar = 60%.
    coordinator._current_consumption_estimate_kwh_per_100km = lambda: 15.0

    target_time = datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    ok = await coordinator.async_set_evcc_charge_plan_range_km(200.0, target_time)

    assert ok is True
    coordinator._evcc_client.async_set_vehicle_plan_soc.assert_awaited_once_with(
        "db:8", 60, "2026-09-19T12:00:00Z"
    )


async def test_async_set_evcc_charge_plan_range_km_ohne_verbrauchswert_gibt_false(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_VEHICLE_HERSTELLER, CONF_VEHICLE_MODELL

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ecpkm2",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter"},
    )
    coordinator._evcc_state = {"vehicles": {"db:8": {"title": "eRifter"}}, "loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client()
    coordinator._evcc_client.async_set_vehicle_plan_soc = AsyncMock(return_value=True)
    coordinator._current_consumption_estimate_kwh_per_100km = lambda: None

    ok = await coordinator.async_set_evcc_charge_plan_range_km(200.0, 1789833600.0)

    assert ok is False
    coordinator._evcc_client.async_set_vehicle_plan_soc.assert_not_called()


# ----- async_set_evcc_manual_mode / _check_evcc_manual_mode_session_end ------

async def test_async_set_evcc_manual_mode_schreibt_und_setzt_flag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "emm1")
    coordinator._evcc_state = {"loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client()

    ok = await coordinator.async_set_evcc_manual_mode("now")

    assert ok is True
    coordinator._evcc_client.async_set_mode.assert_awaited_once_with(1, "now")
    assert coordinator.data["evcc_manual_mode_active"] is True
    assert coordinator.data["evcc_manual_mode"] == "now"


async def test_async_set_evcc_manual_mode_ohne_loadpoint_gibt_false(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "emm2")
    coordinator._evcc_client = _fake_evcc_client()  # kein _evcc_state gesetzt

    ok = await coordinator.async_set_evcc_manual_mode("now")

    assert ok is False
    assert not coordinator.data.get("evcc_manual_mode_active")


async def test_async_set_evcc_manual_mode_schreibfehler_setzt_flag_nicht(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "emm3")
    coordinator._evcc_state = {"loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client(mode_ok=False)

    ok = await coordinator.async_set_evcc_manual_mode("now")

    assert ok is False
    assert not coordinator.data.get("evcc_manual_mode_active")


async def test_async_clear_evcc_manual_mode_setzt_flag_zurueck(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "emm4")
    coordinator.data["evcc_manual_mode_active"] = True
    coordinator.data["evcc_manual_mode"] = "now"

    await coordinator.async_clear_evcc_manual_mode()

    assert coordinator.data["evcc_manual_mode_active"] is False
    assert coordinator.data["evcc_manual_mode"] is None


async def test_apply_evcc_mode_control_manueller_modus_ueberspringt_schreibvorgang(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_ENABLED

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emm5", options={CONF_EVCC_MODE_CONTROL_ENABLED: True},
    )
    coordinator._evcc_state = {"loadpoints": [{}]}
    coordinator._evcc_client = _fake_evcc_client()
    coordinator.data["evcc_manual_mode_active"] = True
    _seed_usage_profile(coordinator)

    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_not_called()


async def test_check_evcc_manual_mode_session_end_setzt_bei_trennen_zurueck(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "emm6")
    coordinator.data["evcc_manual_mode_active"] = True
    coordinator.data["evcc_manual_mode"] = "now"

    # Erst verbunden (Vorzustand setzen)...
    coordinator._evcc_state = {"loadpoints": [{"connected": True}]}
    coordinator._check_evcc_manual_mode_session_end()
    assert coordinator.data["evcc_manual_mode_active"] is True  # noch verbunden, unveraendert

    # ...dann getrennt -> Flanke loest Reset aus.
    coordinator._evcc_state = {"loadpoints": [{"connected": False}]}
    coordinator._check_evcc_manual_mode_session_end()
    assert coordinator.data["evcc_manual_mode_active"] is False
    assert coordinator.data["evcc_manual_mode"] is None


async def test_check_evcc_manual_mode_session_end_kein_reset_ohne_vorherigen_connect(hass, coordinators):
    # Direkt nach Neustart (_evcc_connected_prev noch None) darf ein
    # "nicht verbunden" NICHT als Trenn-Flanke zaehlen.
    coordinator, _ = await _make_coordinator(hass, coordinators, "emm7")
    coordinator.data["evcc_manual_mode_active"] = True
    coordinator.data["evcc_manual_mode"] = "now"

    coordinator._evcc_state = {"loadpoints": [{"connected": False}]}
    coordinator._check_evcc_manual_mode_session_end()

    assert coordinator.data["evcc_manual_mode_active"] is True


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


# ----- _migrate_weekday_usage_windows -----------------------------------------
# Migration von den Lebenszeit-Skalar-Akkumulatoren (Summe + Tageszaehler je
# Wochentag) auf das Sliding-Window-Modell (siehe engine.append_recent_
# weekday_day()/weekday_profile_from_recent_days(), USAGE_PROFILE_WINDOW_DAYS,
# Nutzerentscheidung 2026-09-23 "ja mach das" zur Recency-Gewichtung).

async def test_migrate_weekday_usage_windows_konvertiert_skalare_in_fenster_eintrag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "mwuw1")
    coordinator.data["house_weekday_kwh_totals"] = {"2": 20.0}
    coordinator.data["house_weekday_day_counts"] = {"2": 2}
    coordinator.data["vehicle_discharge_weekday_kwh_totals"] = {"3": 9.0}
    coordinator.data["vehicle_discharge_weekday_day_counts"] = {"3": 3}

    geaendert = coordinator._migrate_weekday_usage_windows()
    assert geaendert is True
    assert "house_weekday_kwh_totals" not in coordinator.data
    assert "house_weekday_day_counts" not in coordinator.data
    assert "vehicle_discharge_weekday_kwh_totals" not in coordinator.data
    assert "vehicle_discharge_weekday_day_counts" not in coordinator.data

    house_days = coordinator.data["house_weekday_days"]["2"]
    assert len(house_days) == 1
    assert house_days[0]["kwh"] == 10.0  # 20 / 2, alter Lebenszeit-Schnitt

    vehicle_days = coordinator.data["vehicle_discharge_weekday_days"]["3"]
    assert len(vehicle_days) == 1
    assert vehicle_days[0]["kwh"] == 3.0  # 9 / 3

    assert coordinator.house_usage_profile() == {2: 10.0}
    assert coordinator.vehicle_discharge_usage_profile() == {3: 3.0}


async def test_migrate_weekday_usage_windows_loescht_veraltetes_event_log(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "mwuw2")
    coordinator.data["vehicle_discharge_events"] = [{"ts": 1.0, "weekday": 0, "kwh_applied": 1.0}]
    geaendert = coordinator._migrate_weekday_usage_windows()
    assert geaendert is True
    assert "vehicle_discharge_events" not in coordinator.data


async def test_migrate_weekday_usage_windows_ohne_alte_daten_ist_no_op(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "mwuw3")
    geaendert = coordinator._migrate_weekday_usage_windows()
    assert geaendert is False


async def test_migrate_weekday_usage_windows_ist_idempotent(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "mwuw4")
    coordinator.data["house_weekday_kwh_totals"] = {"2": 20.0}
    coordinator.data["house_weekday_day_counts"] = {"2": 2}
    assert coordinator._migrate_weekday_usage_windows() is True
    assert coordinator._migrate_weekday_usage_windows() is False
