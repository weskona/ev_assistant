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
    auch min_kwh/target_kwh (morgen) reduzieren, nicht nur rest_heute."""
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
    # target_raw = (0 + morgen 10, EVCC_MODE_TARGET_DAYS=1) - 5 Ueberschuss
    # = 5 -> * 1.2 = 6.0 -- identisch zu min_kwh (siehe const.py-Kommentar zu
    # EVCC_MODE_TARGET_DAYS: die "minpv"-Zwischenstufe faellt damit weg).
    assert targets["target_kwh"] == 6.0
    assert targets["min_kwh"] <= targets["target_kwh"]


async def test_evcc_mode_targets_grosser_pv_ueberschuss_deckt_gesamten_puffer(hass, coordinators):
    """Reicht der heutige PV-Ueberschuss fuer den kompletten Puffer (siehe
    EVCC_MODE_TARGET_DAYS), faellt der Modus zurueck auf "pv" statt
    "minpv"/"now" -- exakt das eigentliche Nutzer-Szenario (Speicher/Auto
    luden nachts durch, obwohl tagsueber genug PV fuer den Rest-Bedarf zu
    erwarten war)."""
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


# ----- CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX: Deckel gegen taegliches Vollladen ---

async def test_evcc_mode_targets_target_soc_max_default_deckelt_auf_80(hass, coordinators):
    """Nutzerwunsch 2026-09-29: 'das soll auch fuer die automatische ladung
    dann das max sein. um nicht immer bis 100% zu laden' -- ohne explizite
    Konfiguration deckelt der Default (80%) ein profilbasiertes Ziel, das
    sonst (wie hier) rechnerisch ueber 100% laege (kwh_to_soc_percent()
    klemmt selbst schon auf 100, die neue Obergrenze zusaetzlich auf 80)."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "emt_socmax1", options={CONF_USABLE_KWH: 10.0})
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 0.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    targets = coordinator._evcc_mode_targets()
    assert targets["target_soc_max"] == 80
    assert targets["target_soc"] == 80


async def test_evcc_mode_targets_target_soc_max_konfigurierbar(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_socmax2",
        options={CONF_USABLE_KWH: 10.0, CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX: 60},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 0.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    targets = coordinator._evcc_mode_targets()
    assert targets["target_soc_max"] == 60
    assert targets["target_soc"] == 60


async def test_evcc_mode_targets_target_soc_max_wirkt_nicht_unter_eigenem_wert(hass, coordinators):
    """Liegt das profilbasierte Ziel ohnehin schon unter der Obergrenze,
    bleibt es unveraendert -- die Deckelung greift nur nach oben, nicht als
    Mindestwert."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "emt_socmax3", options={CONF_USABLE_KWH: 50.0},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.0
    targets = coordinator._evcc_mode_targets()
    assert targets["target_soc"] < 80
    assert targets["target_soc_max"] == 80


async def test_async_set_evcc_mode_control_target_soc_max_schreibt_in_entry_data(hass, coordinators):
    """Panel-Feld in der Karte 'Automatische Ladesteuerung' (Nutzerwunsch
    2026-09-29) -- gleiches Muster wie async_set_weekly_full_charge_
    enabled(): entry.data statt Laufzeit-Override, damit der Options-Flow
    nie einen anderen Wert zeigt."""
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX

    coordinator, entry = await _make_coordinator(hass, coordinators, "socmax_set1")
    await coordinator.async_set_evcc_mode_control_target_soc_max(65)
    assert entry.data[CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX] == 65


async def test_async_set_evcc_mode_control_target_soc_max_klemmt_auf_1_100(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX

    coordinator, entry = await _make_coordinator(hass, coordinators, "socmax_set2")
    await coordinator.async_set_evcc_mode_control_target_soc_max(150)
    assert entry.data[CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX] == 100
    await coordinator.async_set_evcc_mode_control_target_soc_max(-5)
    assert entry.data[CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX] == 1


async def test_async_set_evcc_mode_control_target_soc_max_none_entfernt_key(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "socmax_set3", options={CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX: 50},
    )
    # Options bleiben unberuehrt (schreibt nur entry.data), aber der Key
    # muss dort verschwinden, damit _opt() wieder auf den Default faellt --
    # dafuer muss er zunaechst ueberhaupt in entry.data stehen.
    await coordinator.async_set_evcc_mode_control_target_soc_max(65)
    assert entry.data[CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX] == 65
    await coordinator.async_set_evcc_mode_control_target_soc_max(None)
    assert CONF_EVCC_MODE_CONTROL_TARGET_SOC_MAX not in entry.data


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

    # Fehlgeschlagene Probe wird nicht mehr persistiert, nur gedrosselt -- die
    # Drosselung zuruecksetzen (simuliert den Ablauf von _EVCC_SCOPE_RETRY_S)
    # und dieses Mal erfolgreich probieren.
    assert "evcc_min_soc_scope" not in coordinator.data
    assert "evcc_limit_soc_scope" not in coordinator.data
    coordinator._evcc_scope_failed.clear()
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


async def test_apply_evcc_mode_control_target_soc_null_evcc_spiegelt_fahrzeug_default_kein_endlos_schreiben(
    hass, coordinators
):
    """Produktionsvorfall 2026-09-26 (Event-Log, 11:04-11:08 Uhr, 5 identische
    Rewrites im Minutentakt): evcc behandelt limitSoc=0 nicht als "Ziel 0%",
    sondern als "kein Limit gesetzt" und spiegelt stattdessen den fahrzeug-
    eigenen Default (hier 80) als effectiveLimitSoc zurueck -- ein woertlicher
    Live-Vergleich haette das nie erkannt und bei target_soc=0 (z.B. weil das
    Puffer-Fenster schon komplett gedeckt ist) jeden Zyklus neu geschrieben.
    minSoc=0 ist NICHT betroffen (siehe Gegenprobe unten) -- effectiveMinSoc
    wird von evcc korrekt als 0 gespiegelt."""
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc_zero1", options={CONF_EVCC_MODE_CONTROL_ENABLED: True, CONF_USABLE_KWH: 50.0},
    )
    # weekday_kwh=0.0 -> min_kwh/target_kwh runden auf 0.0 -> target_soc=0.
    _seed_usage_profile(coordinator, weekday_kwh=0.0)
    coordinator._soc = 50.0
    coordinator._evcc_client = _fake_evcc_client(probe_result="loadpoint")
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()
    written = coordinator.data["evcc_mode_control"]
    assert written["target_soc"] == 0
    coordinator._evcc_client.async_set_mode.assert_awaited_once()

    # evcc spiegelt effectiveLimitSoc als seinen Fahrzeug-Default (80) statt
    # der geschriebenen 0 zurueck -- alles andere (Modus, effectiveMinSoc)
    # stimmt bereits ueberein.
    coordinator._evcc_state = {
        "loadpoints": [{
            "mode": written["modus"],
            "effectiveMinSoc": written["min_soc"],
            "effectiveLimitSoc": 80,
        }],
    }
    await coordinator._async_apply_evcc_mode_control()

    coordinator._evcc_client.async_set_mode.assert_awaited_once()  # KEIN zweiter Schreibvorgang


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


async def test_evcc_vehicle_key_matched_trotz_punkt_vs_leerzeichen(hass, coordinators):
    # Produktionsvorfall 2026-09-27 (Issue #2, Jochen754, VW iD3): evccs
    # Titel "iD3" matchte gegen konfiguriertes "ID.3" vorher NICHT.
    from custom_components.ev_assistant.const import (
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "evak6",
        options={CONF_VEHICLE_HERSTELLER: "VW", CONF_VEHICLE_MODELL: "ID.3"},
    )
    coordinator._evcc_state = {"vehicles": {"db:9": {"title": "iD3"}}}
    assert coordinator._evcc_vehicle_key() == "iD3"
    assert coordinator._evcc_vehicle_api_key() == "db:9"


async def test_evcc_vehicle_key_matched_trotz_diakritika(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "evak7",
        options={CONF_VEHICLE_HERSTELLER: "Skoda", CONF_VEHICLE_MODELL: "Enyaq"},
    )
    coordinator._evcc_state = {"vehicles": {"db:10": {"title": "Škoda Enyaq"}}}
    assert coordinator._evcc_vehicle_key() == "Škoda Enyaq"


# ----- _check_evcc_vehicle_match_issue: Repair-Issue bei riskantem Fallback ----

async def test_check_evcc_vehicle_match_issue_erstellt_issue_bei_fehlgeschlagenem_matching(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_WALLBOX_ENERGY_ENTITY, DOMAIN

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "evmi1", options={CONF_WALLBOX_ENERGY_ENTITY: "sensor.wallbox_energy"},
    )
    coordinator._evcc_state = {
        "vehicles": {"db:1": {"title": "eRifter"}},
        "statistics": {"total": {"chargedKWh": 500.0}},
    }
    coordinator._check_evcc_vehicle_match_issue()
    issue_id = f"{entry.entry_id}_evcc_vehicle_match_fallback"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None


async def test_check_evcc_vehicle_match_issue_kein_issue_ohne_wallbox_energy_entity(hass, coordinators):
    from custom_components.ev_assistant.const import DOMAIN

    coordinator, entry = await _make_coordinator(hass, coordinators, "evmi2")
    coordinator._evcc_state = {
        "vehicles": {"db:1": {"title": "eRifter"}},
        "statistics": {"total": {"chargedKWh": 500.0}},
    }
    coordinator._check_evcc_vehicle_match_issue()
    issue_id = f"{entry.entry_id}_evcc_vehicle_match_fallback"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_check_evcc_vehicle_match_issue_kein_issue_bei_explizit_konfiguriertem_namen(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_VEHICLE_NAME,
        CONF_WALLBOX_ENERGY_ENTITY,
        DOMAIN,
    )

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "evmi3",
        options={CONF_WALLBOX_ENERGY_ENTITY: "sensor.wallbox_energy", CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator._evcc_state = {
        "vehicles": {"db:1": {"title": "eRifter"}},
        "statistics": {"total": {"chargedKWh": 500.0}},
    }
    coordinator._check_evcc_vehicle_match_issue()
    issue_id = f"{entry.entry_id}_evcc_vehicle_match_fallback"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


async def test_check_evcc_vehicle_match_issue_verschwindet_nach_erfolgreichem_matching(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_VEHICLE_NAME,
        CONF_WALLBOX_ENERGY_ENTITY,
        DOMAIN,
    )

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "evmi4", options={CONF_WALLBOX_ENERGY_ENTITY: "sensor.wallbox_energy"},
    )
    coordinator._evcc_state = {
        "vehicles": {"db:1": {"title": "eRifter"}},
        "statistics": {"total": {"chargedKWh": 500.0}},
    }
    coordinator._check_evcc_vehicle_match_issue()
    issue_id = f"{entry.entry_id}_evcc_vehicle_match_fallback"
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is not None

    # Simuliert den Nutzer, der CONF_EVCC_VEHICLE_NAME nach der Warnung
    # manuell setzt (Handlungsempfehlung aus dem Issue-Text).
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator._check_evcc_vehicle_match_issue()
    assert ir.async_get(hass).async_get_issue(DOMAIN, issue_id) is None


def _set_home_sums(coordinator, kwh, cost, veh="eRifter"):
    """Setzt die Wasserzeichen-Laufsummen direkt (siehe coordinator.py::
    _accumulate_home_sessions()), wie sie _home_kwh()/_home_cost() lesen --
    und markiert den ersten Sessions-Abruf als erledigt."""
    coordinator._evcc_sessions_loaded = True
    coordinator.data.setdefault("home_kwh_accumulated", {})[veh] = kwh
    coordinator.data.setdefault("home_cost_accumulated", {})[veh] = cost
    coordinator._evcc_open_sums = {}


# ----- _home_kwh/_home_cost: Monotonie-Schutz gegen schrumpfendes evcc-Logbuch --

def _evcc_session(day, kwh, cost, finished=True, vehicle="eRifter"):
    return {
        "vehicle": vehicle,
        "created": f"2026-09-{day:02d}T10:00:00+02:00",
        "finished": f"2026-09-{day:02d}T12:00:00+02:00" if finished else "0001-01-01T00:00:00Z",
        "chargedEnergy": kwh,
        "price": cost,
    }


async def test_home_kwh_bleibt_bei_schrumpfendem_evcc_sessions_logbuch(hass, coordinators):
    """Produktionsvorfall 2026-09-29 (Issue #5): evccs Sessions-Logbuch fuer
    ein Fahrzeug verlor aeltere Sessions -- die frueher bei jedem Refresh
    neu summierte chargedEnergy fiel dadurch von ~309 auf 93.3 kWh. Seit dem
    Wasserzeichen-Verfahren bleibt die persistierte Laufsumme erhalten und
    waechst nur durch NEUE beendete Sessions."""
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hk1", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_client.async_get_sessions.return_value = [
        _evcc_session(1, 215.82, 40.0), _evcc_session(20, 93.3, 16.98),
    ]
    await coordinator._refresh_evcc_sessions()
    assert coordinator._home_kwh() == 309.12

    # evcc verliert die aeltere Session -- Laufsumme bleibt.
    coordinator._evcc_client.async_get_sessions.return_value = [_evcc_session(20, 93.3, 16.98)]
    await coordinator._refresh_evcc_sessions()
    assert coordinator._home_kwh() == 309.12

    # Eine neue beendete Session wird zusaetzlich gezaehlt.
    coordinator._evcc_client.async_get_sessions.return_value = [
        _evcc_session(20, 93.3, 16.98), _evcc_session(25, 10.0, 2.0),
    ]
    await coordinator._refresh_evcc_sessions()
    assert coordinator._home_kwh() == 319.12


async def test_home_kwh_ohne_ersten_sessions_abruf_kein_stufe2_rueckfall(hass, coordinators):
    """Issue #5: vor dem ersten Sessions-Abruf darf _home_kwh() NICHT auf
    evccs standortweite Lifetime-Statistik zurueckfallen (wuerde als Start-/
    Hoechstwert festgeschrieben)."""
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME, CONF_WALLBOX_ENERGY_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hk0",
        options={CONF_EVCC_VEHICLE_NAME: "eRifter", CONF_WALLBOX_ENERGY_ENTITY: "sensor.wb"},
    )
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_sessions_loaded = False
    coordinator._evcc_state = {"statistics": {"total": {"chargedKWh": 2370.0}}}
    assert coordinator._home_kwh() is None
    assert coordinator._home_kwh_since_setup() is None
    assert coordinator.data.get("savings_home_kwh_start") is None


async def test_accumulate_home_sessions_repariert_vergiftete_baseline(hass, coordinators):
    """Jochens Fall (Issue #5): Startwert = last_known = 2370 (evccs
    Lifetime-Statistik) ueber der echten Session-Summe -> Start wird so
    gesetzt, dass "seit Einrichtung" die Sessions ab Einrichtung zaehlt."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "hk9", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    entry.created_at = datetime(2026, 9, 10, tzinfo=UTC)
    coordinator.data["savings_home_kwh_start"] = 2370.0
    coordinator.data["home_kwh_last_known"] = 2370.0
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_client.async_get_sessions.return_value = [
        _evcc_session(1, 200.0, 40.0), _evcc_session(15, 12.0, 2.0), _evcc_session(20, 8.0, 1.0),
    ]
    await coordinator._refresh_evcc_sessions()

    assert coordinator._home_kwh() == 220.0
    assert coordinator._home_kwh_since_setup() == 20.0
    assert coordinator.data["home_kwh_last_known"] is None
    assert any(e["kategorie"] == "home_baseline_repariert" for e in coordinator.data["event_log"])


async def test_home_kwh_folgt_weiterhin_echten_anstiegen(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hk2", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    _set_home_sums(coordinator, 100.0, 0.0)
    assert coordinator._home_kwh() == 100.0

    _set_home_sums(coordinator, 105.5, 0.0)
    assert coordinator._home_kwh() == 105.5


async def test_home_cost_bleibt_bei_schrumpfendem_evcc_sessions_logbuch(hass, coordinators):
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "hc1", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_client.async_get_sessions.return_value = [
        _evcc_session(1, 0.0, 52.6), _evcc_session(20, 0.0, 12.4),
    ]
    await coordinator._refresh_evcc_sessions()
    assert coordinator._home_cost() == 65.0

    coordinator._evcc_client.async_get_sessions.return_value = [_evcc_session(20, 0.0, 12.4)]
    await coordinator._refresh_evcc_sessions()
    assert coordinator._home_cost() == 65.0


async def test_update_kwh_periods_heilt_unmoegliche_baseline_selbst(hass, coordinators):
    """_discard_impossible_period_baselines(): eine gespeicherte Tages-
    Baseline UEBER dem aktuellen Gesamtwert ist unmoeglich unter normalem
    Betrieb -- muss verworfen (statt beibehalten) und beim naechsten Aufruf
    prev-los neu kalibriert werden."""
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ukp1", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator.data["savings_home_kwh_start"] = 0.0  # bereits laengst etabliert, wie im echten Vorfall
    coordinator.data["kwh_periods"] = {
        "day": {"key": coordinator._period_keys()["day"], "kwh": 309.12, "prev": -89.83},
        "week": {"key": coordinator._period_keys()["week"], "kwh": 50.0, "prev": 10.0},
    }
    _set_home_sums(coordinator, 93.3, 0.0)

    coordinator._update_kwh_periods()

    day = coordinator.data["kwh_periods"]["day"]
    assert day["kwh"] == 93.3
    assert "prev" not in day  # keine erfundene Differenz
    # Woche liegt unter dem aktuellen Wert -> bleibt unangetastet.
    assert coordinator.data["kwh_periods"]["week"] == {
        "key": coordinator._period_keys()["week"], "kwh": 50.0, "prev": 10.0,
    }


async def test_update_kwh_periods_heilt_baseline_die_unter_der_wochen_baseline_liegt(hass, coordinators):
    """Realistischere Nachstellung des tatsaechlichen Produktionsvorfalls
    2026-09-29 (siehe _home_kwh()-Docstring): externe Ladungen (totals.kwh)
    zaehlen zusaetzlich zum Heimladen-Anteil, wodurch der AKTUELLE
    Gesamtwert trotz verfaelschter Tages-Baseline schon wieder DARUEBER
    liegt -- _discard_impossible_period_baselines() (Vergleich gegen jetzt)
    erkennt das allein NICHT, aber _discard_inconsistent_period_baselines()
    (Vergleich gegen die Wochen-Baseline, die den Bruch nicht miterlebte)
    schon."""
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ukp2", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator.data["savings_home_kwh_start"] = 0.0
    coordinator.data["totals"] = {"kwh": 309.12, "kosten": 137.07, "count": 20}
    # Seit 0.99.30 gelten die Baselines nur noch fuer die Nicht-Fremd-Summe
    # (Heimladen) -- Fremdladungen kommen live aus der Historie.
    coordinator.data["kwh_periods"] = {
        # Tages-Baseline wurde mit Heimladen-Anteil=0 gesetzt (async_setup()
        # lief vor dem ersten evcc-Sessions-Abruf).
        "day": {"key": coordinator._period_keys()["day"], "kwh": 0.0, "prev": -89.83},
        # Wochen-Baseline wurde VOR dem Bruch gesetzt, ist also noch korrekt.
        "week": {"key": coordinator._period_keys()["week"], "kwh": 89.83, "prev": 56.22},
    }
    _set_home_sums(coordinator, 93.3, 0.0)

    coordinator._update_kwh_periods()

    day = coordinator.data["kwh_periods"]["day"]
    assert day["kwh"] == 93.3  # aktueller Heimladen-Stand
    assert "prev" not in day
    # Wochen-Baseline war in sich konsistent -- bleibt unangetastet.
    assert coordinator.data["kwh_periods"]["week"] == {
        "key": coordinator._period_keys()["week"], "kwh": 89.83, "prev": 56.22,
    }


async def test_update_kwh_periods_heilt_negatives_prev_auch_wenn_wochen_referenz_bereits_kompromittiert(
    hass, coordinators,
):
    """Deckt die tatsaechliche Reihenfolge des Produktionsvorfalls
    2026-09-29 ab: eine FRUEHERE, noch unvollstaendige Selbstheilung hatte
    die Wochen-Baseline bereits selbst faelschlich auf denselben (damals
    noch unvollstaendigen) Wert wie die Tages-Baseline zurueckgesetzt --
    _discard_inconsistent_period_baselines() findet dadurch keinen
    Widerspruch mehr (Tag == Woche, nicht Tag < Woche). Nur das direkt am
    Eintrag selbst ablesbare negative "prev" bleibt zuverlaessig."""
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ukp3", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator.data["savings_home_kwh_start"] = 0.0
    coordinator.data["totals"] = {"kwh": 309.12, "kosten": 137.07, "count": 20}
    coordinator.data["kwh_periods"] = {
        "day": {"key": coordinator._period_keys()["day"], "kwh": 0.0, "prev": -89.83},
        # Woche wurde von einer frueheren (unvollstaendigen) Selbstheilung
        # bereits prev-los auf denselben Wert wie Tag zurueckgesetzt.
        "week": {"key": coordinator._period_keys()["week"], "kwh": 0.0},
        "month": {"key": coordinator._period_keys()["month"], "kwh": 0.0, "prev": 78.97},
    }
    _set_home_sums(coordinator, 93.3, 0.0)

    coordinator._update_kwh_periods()

    day = coordinator.data["kwh_periods"]["day"]
    assert day["kwh"] == 93.3
    assert "prev" not in day


async def test_refresh_evcc_sessions_stoesst_perioden_selbstheilung_an(hass, coordinators):
    """async_setup() seedet kwh_periods/cost_periods synchron, BEVOR der
    erste _refresh_evcc_sessions()-Task fertig ist (siehe dortigen
    Docstring) -- die Selbstheilung greift deshalb erst hier, sobald echte
    evcc-Sessions-Daten eintreffen."""
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "res1", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator.data["savings_home_kwh_start"] = 0.0  # bereits laengst etabliert, wie im echten Vorfall
    coordinator.data["kwh_periods"] = {
        "day": {"key": coordinator._period_keys()["day"], "kwh": 309.12, "prev": -89.83},
    }
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_client.async_get_sessions.return_value = [_evcc_session(20, 93.3, 16.98)]

    await coordinator._refresh_evcc_sessions()

    day = coordinator.data["kwh_periods"]["day"]
    assert day["kwh"] == 93.3
    assert "prev" not in day


async def test_refresh_evcc_sessions_leere_liste_loest_keine_selbstheilung_aus(hass, coordinators):
    """Leere `sessions` (evcc_client.py::async_get_sessions() gibt bei
    Netzwerkfehler/Timeout ebenfalls `[]` zurueck) darf eine intakte
    Baseline NICHT anfassen -- sonst wuerde ein transienter evcc-Ausfall
    dieselbe Art Datenverlust ausloesen, die die Selbstheilung eigentlich
    verhindern soll."""
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "res2", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator.data["savings_home_kwh_start"] = 0.0
    intact = {"key": coordinator._period_keys()["day"], "kwh": 309.12, "prev": 12.3}
    coordinator.data["kwh_periods"] = {"day": dict(intact)}
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_client.async_get_sessions.return_value = []

    await coordinator._refresh_evcc_sessions()

    assert coordinator.data["kwh_periods"]["day"] == intact


# ----- async_reset_lifetime_kpis: manuelle Neu-Baselinierung -------------------

async def test_reset_lifetime_kpis_ohne_parameter_setzt_delta_auf_null(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "rlk1", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator.data["odo"] = 12000.0
    coordinator.data["odo_unit"] = "km"
    _set_home_sums(coordinator, 300.0, 60.0)

    await coordinator.async_reset_lifetime_kpis()

    assert coordinator.data["odo_start"] == 12000.0
    assert coordinator.data["savings_home_kwh_start"] == 300.0
    assert coordinator.data["savings_home_cost_start"] == 60.0
    assert coordinator._home_kwh_since_setup() == 0.0
    assert coordinator._home_cost_since_setup() == 0.0
    assert coordinator._km_driven() == 0.0


async def test_reset_lifetime_kpis_mit_parametern_rechnet_anker_zurueck(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_VEHICLE_NAME

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "rlk2", options={CONF_EVCC_VEHICLE_NAME: "eRifter"},
    )
    coordinator.data["odo"] = 12850.0
    coordinator.data["odo_unit"] = "km"
    _set_home_sums(coordinator, 420.0, 90.0)

    await coordinator.async_reset_lifetime_kpis(
        home_kwh_since_setup=120.0, home_cost_since_setup=25.0, km_driven=850.0,
    )

    # savings_home_kwh_start = 420 - 120 = 300 -> Delta bleibt exakt 120.
    assert coordinator.data["savings_home_kwh_start"] == 300.0
    assert coordinator._home_kwh_since_setup() == 120.0
    assert coordinator.data["savings_home_cost_start"] == 65.0
    assert coordinator._home_cost_since_setup() == 25.0
    # odo_start = 12850 - 850 = 12000 -> Delta bleibt exakt 850.
    assert coordinator.data["odo_start"] == 12000.0
    assert coordinator._km_driven() == 850.0


async def test_reset_lifetime_kpis_faehrt_wallbox_energy_start_immer_unconditional(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "rlk3")
    coordinator._wallbox_energy = 4200.0
    coordinator.data["wallbox_energy_start"] = 1000.0

    await coordinator.async_reset_lifetime_kpis(home_kwh_since_setup=5.0)

    assert coordinator.data["wallbox_energy_start"] == 4200.0


# ----- async_export_backup / async_restore_backup ------------------------------

async def test_export_backup_schreibt_json_mit_config_snapshot(hass, coordinators):
    import json

    coordinator, entry = await _make_coordinator(hass, coordinators, "bkp1")
    coordinator.data["totals"] = {"kwh": 42.0, "kosten": 10.0, "count": 3}

    path = await coordinator.async_export_backup()

    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["totals"]["kwh"] == 42.0
    assert payload["_config_snapshot_readonly"]["options"] == dict(entry.options)


async def test_restore_backup_ersetzt_data_und_legt_pre_restore_backup_an(hass, coordinators):
    import json

    coordinator, entry = await _make_coordinator(hass, coordinators, "bkp2")
    coordinator.data["totals"] = {"kwh": 5.0, "kosten": 1.0, "count": 1}
    coordinator.hass.config_entries.async_reload = AsyncMock(return_value=None)

    backup = dict(coordinator.data)
    backup["totals"] = {"kwh": 999.0, "kosten": 50.0, "count": 9}
    backup["_config_snapshot_readonly"] = {"data": {}, "options": {}}

    ok = await coordinator.async_restore_backup(json.dumps(backup))
    await hass.async_block_till_done()

    assert ok is True
    assert coordinator.data["totals"]["kwh"] == 999.0
    assert "_config_snapshot_readonly" not in coordinator.data
    coordinator.hass.config_entries.async_reload.assert_called()

    pre_restore_path = hass.config.path("www", f"ev_assistant_backup_pre_restore_{entry.entry_id}.json")
    with open(pre_restore_path, encoding="utf-8") as f:
        pre_restore = json.load(f)
    assert pre_restore["totals"]["kwh"] == 5.0


async def test_restore_backup_ungueltiges_json_wird_abgelehnt(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "bkp3")
    coordinator.data["totals"] = {"kwh": 5.0, "kosten": 1.0, "count": 1}

    ok = await coordinator.async_restore_backup("das ist kein json")

    assert ok is False
    assert coordinator.data["totals"]["kwh"] == 5.0


async def test_restore_backup_fehlende_kernstruktur_wird_abgelehnt(hass, coordinators):
    import json

    coordinator, _ = await _make_coordinator(hass, coordinators, "bkp4")
    coordinator.data["totals"] = {"kwh": 5.0, "kosten": 1.0, "count": 1}

    ok = await coordinator.async_restore_backup(json.dumps({"foo": "bar"}))

    assert ok is False
    assert coordinator.data["totals"]["kwh"] == 5.0


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


# ----- Woechentliches Balancing: Tageszeit-Gate (weekly_balancing_time_ok) -


async def test_evcc_mode_targets_balancing_faellig_mittags_noch_pv_uebrig_nicht_aktiv(hass, coordinators):
    """Produktionsvorfall 2026-09-27: eine mittags faellig gewordene
    woechentliche Vollladung erzwang bislang sofort minpv/100%, obwohl noch
    reichlich PV fuer den Rest des Tages zu erwarten war. "faellig" (reines
    Intervall) und "aktiv" (tatsaechlich erzwungen) muessen jetzt
    auseinanderfallen koennen."""
    from custom_components.ev_assistant.const import (
        CONF_PV_FORECAST_TODAY_REMAINING_ENTITY,
        CONF_USABLE_KWH,
        CONF_WEEKLY_FULL_CHARGE_ENABLED,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "wb_mittag",
        options={
            CONF_USABLE_KWH: 50.0,
            CONF_WEEKLY_FULL_CHARGE_ENABLED: True,
            CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest",
        },
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.5
    coordinator._local_hour = lambda: 13
    coordinator.data["vollladung_letzter_ts"] = None  # noch nie -> sofort faellig
    hass.states.async_set("sensor.pv_rest", "5.0", {"unit_of_measurement": "kWh"})

    targets = coordinator._evcc_mode_targets()
    assert targets["balancing_faellig"] is True
    assert targets["balancing_aktiv"] is False
    assert targets["modus"] != "minpv" or targets["target_soc"] != 100


async def test_evcc_mode_targets_balancing_faellig_pv_aufgebraucht_wird_aktiv(hass, coordinators):
    """Gegenprobe: sobald die PV-Restprognose (fast) aufgebraucht ist, wird
    die faellige Vollladung tatsaechlich erzwungen."""
    from custom_components.ev_assistant.const import (
        CONF_PV_FORECAST_TODAY_REMAINING_ENTITY,
        CONF_USABLE_KWH,
        CONF_WEEKLY_FULL_CHARGE_ENABLED,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "wb_abend",
        options={
            CONF_USABLE_KWH: 50.0,
            CONF_WEEKLY_FULL_CHARGE_ENABLED: True,
            CONF_PV_FORECAST_TODAY_REMAINING_ENTITY: "sensor.pv_rest",
        },
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator._day_fraction_elapsed = lambda: 0.9
    coordinator._local_hour = lambda: 20
    coordinator.data["vollladung_letzter_ts"] = None
    hass.states.async_set("sensor.pv_rest", "0.05", {"unit_of_measurement": "kWh"})

    targets = coordinator._evcc_mode_targets()
    assert targets["balancing_faellig"] is True
    assert targets["balancing_aktiv"] is True
    assert targets["modus"] == "minpv"
    assert targets["target_soc"] == 100


async def test_evcc_mode_targets_balancing_faellig_ohne_pv_prognose_fallback_stunde(hass, coordinators):
    """Ohne konfigurierte PV-Restprognose greift die feste Fallback-Stunde
    (23 Uhr, Nutzerentscheidung 2026-09-27) statt nie auszuloesen."""
    from custom_components.ev_assistant.const import (
        CONF_USABLE_KWH,
        CONF_WEEKLY_FULL_CHARGE_ENABLED,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "wb_fallback",
        options={CONF_USABLE_KWH: 50.0, CONF_WEEKLY_FULL_CHARGE_ENABLED: True},
    )
    _seed_usage_profile(coordinator, weekday_kwh=10.0)
    coordinator._soc = 50.0
    coordinator.data["vollladung_letzter_ts"] = None

    coordinator._day_fraction_elapsed = lambda: 0.9
    coordinator._local_hour = lambda: 22
    targets = coordinator._evcc_mode_targets()
    assert targets["balancing_aktiv"] is False

    coordinator._local_hour = lambda: 23
    targets = coordinator._evcc_mode_targets()
    assert targets["balancing_aktiv"] is True


# ----- Issue #1 (fugazzy): Reset einfrierte "seit Einrichtung" (Stufe 3) -------

async def _make_wallbox_coordinator(hass, coordinators, entry_id):
    from custom_components.ev_assistant.const import CONF_HOME_PRICE_KWH, CONF_WALLBOX_ENERGY_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, entry_id,
        options={CONF_WALLBOX_ENERGY_ENTITY: "sensor.wb", CONF_HOME_PRICE_KWH: 0.23},
    )
    coordinator.data["wallbox_energy_start"] = 1000.0
    coordinator.data["savings_home_kwh_start"] = 0.0
    coordinator._wallbox_energy = 1236.0
    assert coordinator._home_kwh() == 236.0
    return coordinator


async def test_reset_lifetime_kpis_stufe3_waechst_danach_weiter(hass, coordinators):
    coordinator = await _make_wallbox_coordinator(hass, coordinators, "rst1")
    await coordinator.async_reset_lifetime_kpis()
    assert coordinator._home_kwh() == 0.0
    assert coordinator._home_kwh_since_setup() == 0.0

    coordinator._wallbox_energy = 1256.0  # 20 kWh Heimladen nach dem Reset
    assert coordinator._home_kwh() == 20.0
    assert coordinator._home_kwh_since_setup() == 20.0


async def test_reset_lifetime_kpis_stufe3_mit_vorgabewert(hass, coordinators):
    coordinator = await _make_wallbox_coordinator(hass, coordinators, "rst2")
    await coordinator.async_reset_lifetime_kpis(home_kwh_since_setup=50.0)
    assert coordinator._home_kwh_since_setup() == 50.0
    coordinator._wallbox_energy = 1246.0
    assert coordinator._home_kwh_since_setup() == 60.0


async def test_home_kwh_stufe3_heilt_eingefrorenen_stand_nach_altem_reset(hass, coordinators):
    """Zustand wie bei fugazzy nach dem Reset VOR dem Fix: wallbox_energy_start
    neu, Hoechststand == Startwert == 236 bei Rohwert 20."""
    coordinator = await _make_wallbox_coordinator(hass, coordinators, "rst3")
    coordinator.data["wallbox_energy_start"] = 1236.0
    coordinator._wallbox_energy = 1256.0  # raw = 20
    coordinator.data["home_kwh_last_known"] = 236.0
    coordinator.data["savings_home_kwh_start"] = 236.0

    assert coordinator._home_kwh() == 20.0
    # Stufe 3: der Rohwert ist bereits die Energie SEIT dem Reset -- sie darf
    # durch die Heilung nicht verloren gehen (synchron zum Kilometerstand-Anker).
    assert coordinator._home_kwh_since_setup() == 20.0
    assert any(e["kategorie"] == "home_baseline_repariert" for e in coordinator.data["event_log"])

    coordinator._wallbox_energy = 1261.0  # +5 kWh danach
    assert coordinator._home_kwh_since_setup() == 25.0


async def test_home_kwh_stufe3_schutz_bleibt_bei_gesundem_rueckgang(hass, coordinators):
    """Fallender Rohwert OHNE Reset-Signatur (Startwert != Hoechststand,
    "seit Einrichtung" > 0) bleibt wie bisher auf dem Hoechststand geklemmt."""
    coordinator = await _make_wallbox_coordinator(hass, coordinators, "rst4")
    assert coordinator._home_kwh_since_setup() == 236.0
    coordinator._wallbox_energy = 1200.0  # Zaehler springt zurueck, raw = 200
    assert coordinator._home_kwh() == 236.0
    assert not any(e["kategorie"] == "home_baseline_repariert" for e in coordinator.data.get("event_log", []))


# ----- Issue #6: nachgetragene Fremdladungen ---------------------------------

def _charge_rec(start_ts, erfasst_ts, kwh=10.0, kosten=5.0, preis=0.5):
    return {
        "config_entry_id": "x", "kwh": kwh, "preis_kwh": preis, "kosten": kosten,
        "startgebuehr": 0.0, "blockiergebuehr": 0.0, "zeitgebuehr": 0.0,
        "erfasst_ts": erfasst_ts, "start_ts": start_ts,
    }


async def test_nachgetragene_fremdladung_landet_nicht_in_aktuellem_monat(hass, coordinators):
    """Issue #6: eine heute fuer einen frueheren Monat nachgetragene Ladung
    darf den aktuellen Monat/Woche/Tag/Jahr nicht veraendern, solange sie
    dort nicht stattgefand."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    coordinator, _ = await _make_coordinator(hass, coordinators, "bf1")
    coordinator._update_cost_periods()
    coordinator._update_kwh_periods()
    assert coordinator.cost_period_value("month") == 0.0

    # Ladung vor ~100 Tagen: anderer Monat und andere Woche (das Jahr kann je
    # nach Testdatum dasselbe oder ein anderes sein -- deshalb dort nicht geprueft).
    alt = (dt_util.now() - timedelta(days=100)).timestamp()
    await coordinator.async_log_charge(kwh=20.0, price=0.5, start_ts=alt)
    assert coordinator.data["totals"]["kosten"] == 10.0  # Lebenszeit zaehlt sie
    assert coordinator.cost_period_value("day") == 0.0
    assert coordinator.cost_period_value("week") == 0.0
    assert coordinator.cost_period_value("month") == 0.0
    assert coordinator.kwh_period_value("month") == 0.0

    # Eine Ladung von heute zaehlt dagegen sofort.
    await coordinator.async_log_charge(kwh=10.0, price=0.5, start_ts=dt_util.now().timestamp() - 60)
    assert coordinator.cost_period_value("day") == 5.0
    assert coordinator.cost_period_value("month") == 5.0
    assert coordinator.kwh_period_value("month") == 10.0


async def test_letzte_fremdladung_ist_zeitlich_letzte_nicht_zuletzt_eingetragene(hass, coordinators):
    """Issue #6: Sensor-Werte "(letzte)" und last_price folgen start_ts."""
    import time

    coordinator, _ = await _make_coordinator(hass, coordinators, "bf2")
    now = time.time()
    await coordinator.async_log_charge(kwh=30.0, price=0.40, start_ts=now - 3600)
    await coordinator.async_log_charge(kwh=5.0, price=0.99, start_ts=now - 86400 * 60)  # nachgetragen, aelter
    from custom_components.ev_assistant.engine import latest_charge

    # erfasst_ts ist die Eintrags-ID -- im Test kommen beide in derselben Sekunde.
    coordinator.data["history"][0]["erfasst_ts"] += 5

    assert latest_charge(coordinator.data["history"])["kwh"] == 30.0
    assert coordinator.data["last_price"] == 0.40

    # Loeschen der (zeitlich) letzten Ladung: die aeltere wird wieder "letzte".
    newest = latest_charge(coordinator.data["history"])
    assert await coordinator.async_delete_charge(newest["erfasst_ts"])
    assert coordinator.data["last_price"] == 0.99


async def test_migration_zerlegt_alte_gesamt_baseline(hass, coordinators):
    """0.99.30: alte Baseline = Snapshot der Gesamtsumme (Heim + Fremd). Die
    seit Periodenbeginn ERFASSTEN Fremdladungen steckten noch nicht darin."""
    import time

    coordinator, _ = await _make_coordinator(hass, coordinators, "bf3")
    now = time.time()
    day_key = coordinator._period_keys()["day"]
    # Bis gestern: 100 EUR Fremd in der Baseline; heute nachtraeglich eine
    # 30-EUR-Ladung fuer einen alten Monat erfasst (steckt NICHT in der Baseline).
    coordinator.data["history"] = [
        _charge_rec(now - 86400 * 90, int(now) - 10, kwh=60.0, kosten=30.0),
        _charge_rec(now - 86400 * 5, int(now) - 86400 * 4, kwh=200.0, kosten=100.0),
    ]
    coordinator.data["totals"] = {"kwh": 260.0, "kosten": 130.0, "count": 2}
    coordinator.data["cost_periods"] = {"day": {"key": day_key, "cost": 100.0, "prev": 100.0}}
    coordinator.data["kwh_periods"] = {}
    coordinator.data["period_baselines_split_migrated"] = False

    assert coordinator._migrate_period_baselines_split() is True
    assert coordinator.data["cost_periods"]["day"]["cost"] == 0.0  # 100 - (130 - 30)
    assert coordinator._migrate_period_baselines_split() is False  # Flag, idempotent


# ----- Review 2026-10-04: Startrennen Fahrzeug-Zuordnung, generische Sessions ---

async def test_auto_zuordnung_sessions_vor_evcc_state_migration_laeuft_trotzdem(hass, coordinators):
    """Ohne konfigurierten Fahrzeugnamen kann der Sessions-Abruf VOR dem
    evcc-State fertig sein (Schluessel noch None): bis dahin kein Rueckfall
    auf Stufe 2, und die Baseline-Reparatur laeuft, sobald der Schluessel da ist."""
    from datetime import UTC, datetime
    from unittest.mock import AsyncMock

    from custom_components.ev_assistant.const import (
        CONF_VEHICLE_HERSTELLER,
        CONF_VEHICLE_MODELL,
        CONF_WALLBOX_ENERGY_ENTITY,
    )

    coordinator, entry = await _make_coordinator(
        hass, coordinators, "rv1",
        options={CONF_VEHICLE_HERSTELLER: "Peugeot", CONF_VEHICLE_MODELL: "eRifter", CONF_WALLBOX_ENERGY_ENTITY: "sensor.wb"},
    )
    entry.created_at = datetime(2026, 9, 10, tzinfo=UTC)
    coordinator.data["savings_home_kwh_start"] = 2370.0
    coordinator.data["home_kwh_last_known"] = 2370.0
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_client.async_get_sessions.return_value = [
        _evcc_session(1, 200.0, 40.0), _evcc_session(20, 20.0, 3.0),
    ]
    coordinator._evcc_state = None
    await coordinator._refresh_evcc_sessions()
    assert coordinator._home_kwh() is None  # Zuordnung noch offen, kein Stufe-2-Rueckfall
    assert coordinator.cost_period_value("month") is None

    coordinator._evcc_state = {
        "vehicles": {"db:1": {"title": "eRifter"}}, "statistics": {"total": {"chargedKWh": 2370.0}},
    }
    await coordinator._refresh_evcc_sessions()
    assert coordinator._home_kwh() == 220.0
    assert coordinator._home_kwh_since_setup() == 20.0  # Baseline repariert


async def test_generische_home_sessions_werden_nach_wh_migration_repariert(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "rv2")  # ohne evcc
    coordinator.data["home_sessions"] = [
        {"ts": 1.0, "kwh": 0.012, "solar_pct": 80.0, "kosten": 2.9},   # 12.34 kWh, durch Migration /1000
        {"ts": 2.0, "kwh": 8.0, "solar_pct": 50.0, "kosten": 2.0},     # nach der Migration geschrieben
    ]
    coordinator.data["home_sessions_generic_repaired"] = False
    assert coordinator._repair_generic_home_sessions_kwh() is True
    assert coordinator.data["home_sessions"][0]["kwh"] == 12.0
    assert coordinator.data["home_sessions"][1]["kwh"] == 8.0
    assert coordinator.home_session_stats()["preis_je_kwh"] < 1.0
    assert any(e["kategorie"] == "home_sessions_repariert" for e in coordinator.data["event_log"])
    assert coordinator._repair_generic_home_sessions_kwh() is False  # Flag


async def test_generische_home_sessions_reparatur_nicht_bei_evcc(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_EVCC_HOST

    coordinator, entry = await _make_coordinator(hass, coordinators, "rv3")
    # erst nach dem Setup setzen -- sonst wuerde ein echter evcc-Client aufgebaut
    hass.config_entries.async_update_entry(entry, options={CONF_EVCC_HOST: "h:7070"})
    coordinator.data["home_sessions"] = [{"ts": 1.0, "kwh": 0.012, "solar_pct": 80.0, "kosten": 2.9}]
    coordinator.data["home_sessions_generic_repaired"] = False
    coordinator._repair_generic_home_sessions_kwh()
    assert coordinator.data["home_sessions"][0]["kwh"] == 0.012  # evcc-Pfad: war echt Wh


async def test_perioden_baselines_bleiben_bei_nicht_erreichbarem_evcc_erhalten(hass, coordinators):
    """Review 2026-10-04: erreicht der taegliche Rollover evcc nicht (State
    None, kein expliziter Fahrzeugname), darf er die Baselines nicht auf 0
    zuruecksetzen."""
    from unittest.mock import AsyncMock

    coordinator, _ = await _make_coordinator(hass, coordinators, "rv4")
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_sessions_loaded = True
    coordinator._evcc_state = None
    coordinator.data["kwh_periods"] = {"day": {"key": coordinator._period_keys()["day"], "kwh": 310.0, "prev": 5.0}}
    coordinator.data["cost_periods"] = {"day": {"key": coordinator._period_keys()["day"], "cost": 90.0}}
    coordinator._update_kwh_periods()
    coordinator._update_cost_periods()
    assert coordinator.data["kwh_periods"]["day"] == {"key": coordinator._period_keys()["day"], "kwh": 310.0, "prev": 5.0}
    assert coordinator.data["cost_periods"]["day"]["cost"] == 90.0


async def test_inkonsistenz_pruefung_loescht_keine_woche_die_vor_dem_monat_beginnt(hass, coordinators):
    """Review 2026-10-04: eine Woche, die vor dem Monatsbeginn startet (Mo 28.09.,
    Monat ab 01.10.), hat zu Recht eine NIEDRIGERE Baseline als der Monat."""
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    periods = {
        "week": {"key": "2026-W40", "kwh": 200.0, "prev": 5.0},   # Mo 28.09.
        "month": {"key": "2026-10", "kwh": 230.0, "prev": 9.0},   # 01.10.
        "day": {"key": "2026-10-04", "kwh": 240.0},
    }
    result = EvAssistantCoordinator._discard_inconsistent_period_baselines(periods, "kwh")
    assert set(result) == {"week", "month", "day"}
    # echte Inkonsistenz (Tag vor Monat zu niedrig) wird weiterhin erkannt
    periods["day"]["kwh"] = 100.0
    assert "day" not in EvAssistantCoordinator._discard_inconsistent_period_baselines(periods, "kwh")


async def test_sessions_fehlschlag_markiert_nicht_als_geladen(hass, coordinators):
    from unittest.mock import AsyncMock

    coordinator, _ = await _make_coordinator(hass, coordinators, "rv5")
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_client.async_get_sessions.return_value = []
    coordinator._evcc_client.last_sessions_ok = False
    await coordinator._refresh_evcc_sessions()
    assert coordinator._evcc_sessions_loaded is False
    coordinator._evcc_client.last_sessions_ok = True
    await coordinator._refresh_evcc_sessions()
    assert coordinator._evcc_sessions_loaded is True


async def test_home_tick_ohne_anker_wirft_nicht(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "rv6")
    coordinator._home = True
    coordinator._pv_generation = 100.0
    coordinator._home_consumption_live_raw = 50.0
    coordinator._wallbox_energy = 10.0
    coordinator._home_tick_acc = {
        "solar_kwh": 0.0, "grid_kwh": 0.0, "kosten": 0.0,
        "last_pv": None, "last_home": 50.0, "last_auto": 10.0, "last_battery": None,
        "last_feedin_price": 0.08, "last_grid_price": 0.3,
    }
    coordinator._process_home_tick()  # darf nicht werfen
    assert coordinator._home_tick_acc["last_pv"] == 100.0


async def test_inkonsistenz_pruefung_senkt_zu_hohes_jahr_ab_statt_andere_zu_loeschen(hass, coordinators):
    """Live-Fall 2026-10-04: Jahres-Baseline (spaet geseedet) 113.75 liegt ueber den
    korrekten Monats-/Wochen-Baselines 98.07 -- diese duerfen nicht geloescht werden."""
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    periods = {
        "year": {"key": "2026", "kwh": 113.75},
        "month": {"key": "2026-10", "kwh": 98.07, "prev": 9.0},
        "week": {"key": "2026-W40", "kwh": 98.07},
        "day": {"key": "2026-10-04", "kwh": 113.75, "prev": 1.0},
    }
    result = EvAssistantCoordinator._discard_inconsistent_period_baselines(periods, "kwh")
    assert set(result) == {"year", "month", "week", "day"}
    assert result["year"]["kwh"] == 98.07
    assert result["month"]["prev"] == 9.0
    assert periods["year"]["kwh"] == 113.75  # Eingabe unveraendert


# ----- Review 2026-10-04 (2): Kilometerstand-Plausibilitaet -------------------

async def test_odo_grosser_sprung_wird_nach_wiederholung_uebernommen(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "odo1")
    coordinator._set_odo(1000, "km")
    assert coordinator.data["odo"] == 1000
    coordinator._set_odo(3000, "km")  # >1500 km Sprung: 1. Mal ignoriert
    coordinator._set_odo(3001, "km")  # 2. Mal ignoriert (+-1 km gleicher Kandidat)
    assert coordinator.data["odo"] == 1000
    coordinator._set_odo(3001, "km")  # 3. Mal -> neuer Stand
    assert coordinator.data["odo"] == 3001
    coordinator._set_odo(3005, "km")
    assert coordinator.data["odo"] == 3005


async def test_odo_einzelner_glitch_wird_weiter_ignoriert(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "odo2")
    coordinator._set_odo(1000, "km")
    coordinator._set_odo(50, "km")      # Glitch
    coordinator._set_odo(1002, "km")    # normaler Wert setzt den Kandidaten zurueck
    coordinator._set_odo(50, "km")
    coordinator._set_odo(51, "km")
    assert coordinator.data["odo"] == 1002  # nie 3x in Folge derselbe Wert


async def test_odo_ruecksprung_dauerhaft_fuehrt_odo_start_mit(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "odo3")
    coordinator._set_odo(1000, "km")
    coordinator._set_odo(1100, "km")
    assert coordinator.data["odo"] - coordinator.data["odo_start"] == 100
    for _ in range(3):
        coordinator._set_odo(20, "km")  # neuer Tacho
    assert coordinator.data["odo"] == 20
    # gefahrene Strecke seit Einrichtung bleibt kontinuierlich (100 km), nicht negativ
    assert coordinator.data["odo"] - coordinator.data["odo_start"] == 100


async def test_evcc_scope_fehlgeschlagene_probe_wird_gedrosselt_nicht_dauerhaft_gecacht(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "scp1")
    coordinator._evcc_client = _fake_evcc_client(probe_result=None)
    assert await coordinator._evcc_scope("evcc_min_soc_scope", 1, None, "minsoc", "minSoc") is None
    assert "evcc_min_soc_scope" not in coordinator.data
    # innerhalb der Drosselung keine zweite Probe
    await coordinator._evcc_scope("evcc_min_soc_scope", 1, None, "minsoc", "minSoc")
    assert coordinator._evcc_client.async_probe_scope.await_count == 1
    # nach Ablauf der Drosselung wird erneut geprobt und ein Erfolg persistiert
    coordinator._evcc_scope_failed.clear()
    coordinator._evcc_client = _fake_evcc_client(probe_result="vehicle")
    assert await coordinator._evcc_scope("evcc_min_soc_scope", 1, "eRifter", "minsoc", "minSoc") == "vehicle"
    assert coordinator.data["evcc_min_soc_scope"] == "vehicle"


async def test_haus_profil_bucht_verpassten_mehrtages_rollover_nicht_als_einen_tag(hass, coordinators):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    coordinator, _ = await _make_coordinator(hass, coordinators, "hp1")
    coordinator._house_combined_reading_kwh = lambda: 200.0
    today = dt_util.now().date()
    coordinator.data["house_periods"] = {"day": {"key": str(today - timedelta(days=3)), "kwh": 100.0}}
    coordinator._update_house_usage_profile()
    assert not coordinator.data.get("house_weekday_days")
    assert coordinator.data["house_periods"]["day"]["key"] == str(today)

    # normaler Rollover (gestern -> heute) wird weiterhin gebucht
    coordinator.data["house_periods"] = {"day": {"key": str(today - timedelta(days=1)), "kwh": 150.0}}
    coordinator._update_house_usage_profile()
    assert coordinator.data.get("house_weekday_days")


async def test_mitternachts_rollover_ruft_perioden_rollover_auf(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "mid1")
    coordinator.data["cost_periods"] = {"day": {"key": "2000-01-01", "cost": 0.0}}
    coordinator._midnight_period_rollover()
    await hass.async_block_till_done()
    assert coordinator.data["cost_periods"]["day"]["key"] == coordinator._period_keys()["day"]


async def test_restart_unterdrueckung_wird_bei_nicht_ladender_erster_messung_verbraucht(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "sup1")
    coordinator._home_tick_restart_suppress = True
    coordinator.data["home_generic_estimate_open"] = True
    coordinator._set_home("0")
    assert coordinator._home_tick_restart_suppress is False
    assert coordinator.data["home_generic_estimate_open"] is False


async def test_heim_uebergang_ohne_soc_wird_nachgeholt(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "sup2")
    coordinator._set_home("0")  # nicht ladend
    coordinator._soc = None
    coordinator._set_home("7.4")  # Ladebeginn, aber noch kein SoC -> wird gemerkt
    assert coordinator._home_session_start_ts is None
    coordinator._soc = 50.0
    coordinator._set_home("7.4")  # naechste Messung: Uebergang wird nachgeholt
    assert coordinator._home_session_start_ts is not None
