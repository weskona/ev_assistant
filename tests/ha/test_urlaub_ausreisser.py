"""Tests fuer den optionalen Urlaubsmodus (CONF_URLAUB_ENTITY, siehe
coordinator.py::_urlaub_aktiv()) und die automatische, nutzerunsichtbare
Ausreisser-Daempfung (OUTLIER_DAMPING_FACTOR, siehe engine.py::
clamp_weekday_contribution()) an allen drei Wochentags-Profil-
Buchungsstellen (_apply_trip_baselines()/_update_house_usage_profile()/
_update_vehicle_discharge_profile()) sowie der evcc-Steuerungs-Pause
(_async_apply_evcc_mode_control()). Reine Daempfungslogik selbst ist
bereits in tests/test_engine.py abgedeckt (clamp_weekday_contribution()) --
hier nur die HA-Verdrahtung: Entity-Lesen, das Einfrieren von
"weekday_applied"/"urlaub" auf dem Trip-Record fuer exakte
sign=-1-Reversibilitaet bei Loeschen/Editieren, sowie die Rollover-Stellen
Haus/Fahrzeug (analog zueinander, kein Reversibilitaets-Thema dort -- siehe
jeweiliger Docstring in coordinator.py)."""
from datetime import timedelta
from unittest.mock import AsyncMock

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="ua1", options=None):
    from custom_components.ev_assistant.const import DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options or {}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


def _trip_rec(kwh=None, km=None, ts=None):
    rec = {"start_ts": ts if ts is not None else dt_util.now().timestamp()}
    if kwh is not None:
        rec["verbrauch_kwh"] = kwh
    if km is not None:
        rec["km"] = km
    return rec


def _seed_7_tage_schnitt(coordinator, weekday_kwh=10.0, avg_consumption=20.0):
    """7-Kalendertage-Spanne, jeder Wochentag kommt genau einmal vor --
    weekday_kwh_exact_totals[key] entspricht dann direkt dem Schnitt fuer
    diesen Wochentag, analog test_evcc_mode_control.py::_seed_usage_profile()."""
    coordinator.data["fahrtenbuch_first_ts"] = (dt_util.now() - timedelta(days=6)).timestamp()
    coordinator.data["weekday_kwh_exact_totals"] = {str(wd): weekday_kwh for wd in range(7)}
    coordinator.data["weekday_km_est_totals"] = {}
    coordinator._usage_profile_cache = None
    coordinator._vehicle_avg_consumption_kwh_per_100km = lambda: avg_consumption


# ----- _urlaub_aktiv ---------------------------------------------------------

async def test_urlaub_aktiv_ohne_konfigurierte_entitaet_gibt_false(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "ua1")
    assert coordinator._urlaub_aktiv() is False


async def test_urlaub_aktiv_an_gibt_true(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua2", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    assert coordinator._urlaub_aktiv() is True


async def test_urlaub_aktiv_aus_gibt_false(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua3", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "off")
    assert coordinator._urlaub_aktiv() is False


async def test_urlaub_aktiv_unknown_gibt_false_failsafe(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua4", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "unknown")
    assert coordinator._urlaub_aktiv() is False


async def test_urlaub_aktiv_fehlende_entitaet_gibt_false(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "ua5", options={CONF_URLAUB_ENTITY: "input_boolean.existiert_nicht"},
    )
    assert coordinator._urlaub_aktiv() is False


# ----- _apply_trip_baselines: Urlaubsausschluss + Reversibilitaet ----------

async def test_apply_trip_baselines_urlaub_aktiv_schliesst_fahrt_aus(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "atb1", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    rec = _trip_rec(kwh=10.0)
    coordinator._apply_trip_baselines(rec, 1)
    assert coordinator.data.get("weekday_kwh_exact_totals", {}) == {}
    assert rec["urlaub"] is True
    assert rec["weekday_applied"] is None


async def test_apply_trip_baselines_urlaub_inaktiv_bucht_normal(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb2")
    rec = _trip_rec(kwh=10.0)
    weekday = dt_util.now().date().weekday()
    coordinator._apply_trip_baselines(rec, 1)
    assert coordinator.data["weekday_kwh_exact_totals"] == {str(weekday): 10.0}
    assert rec["urlaub"] is False
    assert rec["weekday_applied"] == ["exact", 10.0]


async def test_apply_trip_baselines_loeschen_nimmt_eingefrorenen_urlaubsstand_zurueck(hass, coordinators):
    """sign=-1 (Loeschen) MUSS den bei sign=+1 eingefrorenen Stand
    zuruecknehmen, NICHT den aktuellen (ggf. veraenderten) Urlaubsschalter
    neu abfragen -- siehe Kommentar in _apply_trip_baselines()."""
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "atb3", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    rec = _trip_rec(kwh=10.0)
    coordinator._apply_trip_baselines(rec, 1)  # ausgeschlossen (Urlaub aktiv)
    assert coordinator.data.get("weekday_kwh_exact_totals", {}) == {}
    hass.states.async_set("input_boolean.urlaub", "off")  # Urlaub inzwischen beendet
    coordinator._apply_trip_baselines(rec, -1)  # Loeschen -- darf NICHTS abziehen
    assert coordinator.data.get("weekday_kwh_exact_totals", {}) == {}


async def test_apply_trip_baselines_bestaetigen_dann_loeschen_ist_exakt_reversibel(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb4")
    rec = _trip_rec(kwh=10.0)
    weekday = dt_util.now().date().weekday()
    coordinator._apply_trip_baselines(rec, 1)
    coordinator._apply_trip_baselines(rec, -1)
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 0.0


async def test_apply_trip_baselines_altbestand_ohne_weekday_applied_faellt_auf_rohwert_zurueck(hass, coordinators):
    """Records von VOR Einfuehrung dieses Felds (kein "weekday_applied"-Key)
    duerfen beim Loeschen nicht stillschweigend nichts abziehen -- Fallback
    auf den rohen weekday_parts-Wert, exakt das, was sie urspruenglich ohne
    dieses Feature gebucht hatten."""
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb5")
    weekday = dt_util.now().date().weekday()
    coordinator.data["weekday_kwh_exact_totals"] = {str(weekday): 10.0}
    rec = _trip_rec(kwh=10.0)  # kein "weekday_applied"-Feld (Altbestand)
    coordinator._apply_trip_baselines(rec, -1)
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 0.0


async def test_apply_trip_baselines_ausreisser_wird_gedaempft(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb6")
    _seed_7_tage_schnitt(coordinator, weekday_kwh=10.0, avg_consumption=20.0)
    weekday = dt_util.now().date().weekday()
    rec = _trip_rec(kwh=100.0)  # 10x Schnitt
    coordinator._apply_trip_baselines(rec, 1)
    # Schwelle = 3 * 10 kWh Schnitt = 30 kWh statt der rohen 100 kWh
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 40.0  # 10 (Alt) + 30 (gekappt)
    assert rec["weekday_applied"] == ["exact", 30.0]


async def test_apply_trip_baselines_unauffaellige_fahrt_wird_nicht_gedaempft(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "atb7")
    _seed_7_tage_schnitt(coordinator, weekday_kwh=10.0, avg_consumption=20.0)
    weekday = dt_util.now().date().weekday()
    rec = _trip_rec(kwh=12.0)  # deutlich unter der 30-kWh-Schwelle
    coordinator._apply_trip_baselines(rec, 1)
    assert coordinator.data["weekday_kwh_exact_totals"][str(weekday)] == 22.0  # 10 + 12
    assert rec["weekday_applied"] == ["exact", 12.0]


# ----- _update_house_usage_profile: Urlaubsausschluss + Daempfung ----------

async def test_update_house_usage_profile_urlaub_aktiv_schliesst_tag_aus(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY, CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup_u1",
        options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus", CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "off")
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    coordinator.data["house_periods"]["day"]["key"] = "ein-anderer-tag"
    hass.states.async_set("input_boolean.urlaub", "on")
    hass.states.async_set("sensor.haus", "1015.0")
    coordinator._update_house_usage_profile()
    assert coordinator.data.get("house_weekday_days", {}) == {}


async def test_update_house_usage_profile_ausreisser_wird_gedaempft(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_HOME_CONSUMPTION_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "huup_u2", options={CONF_HOME_CONSUMPTION_ENTITY: "sensor.haus"},
    )
    yesterday = dt_util.now().date() - timedelta(days=1)
    yesterday_wd = yesterday.weekday()
    coordinator.data["house_weekday_days"] = {
        str(yesterday_wd): [{"date": "2020-01-01", "kwh": 10.0}, {"date": "2020-01-08", "kwh": 10.0}],
    }
    hass.states.async_set("sensor.haus", "1000.0")
    coordinator._update_house_usage_profile()
    coordinator.data["house_periods"]["day"]["key"] = "ein-anderer-tag"
    hass.states.async_set("sensor.haus", "1100.0")  # 100 kWh -- 10x Schnitt (10 kWh)
    coordinator._update_house_usage_profile()
    days = coordinator.data["house_weekday_days"][str(yesterday_wd)]
    assert len(days) == 3
    assert round(sum(d["kwh"] for d in days), 2) == 50.0  # 20 alt + 30 (gekappt)
    neuer_eintrag = next(d for d in days if d["date"] == yesterday.isoformat())
    assert neuer_eintrag["kwh"] == 30.0


# ----- _update_vehicle_discharge_profile: nur noch Tageszaehler, Urlaub ---
# Seit der Bestaetigungs-Haertung (VEHICLE_DISCHARGE_CONFIRM_SECONDS) bucht
# der taegliche Rollover KEINE kWh mehr um -- das passiert direkt bei
# Bestaetigung (siehe _book_vehicle_discharge_weekday() weiter unten),
# zugeordnet zum Tag der ERSTEN Beobachtung statt zum Tag der Bestaetigung.

async def test_update_vehicle_discharge_profile_urlaub_aktiv_schliesst_tag_aus(hass, coordinators):
    """Der Tages-Zaehler (Nenner fuer den Schnitt) darf einen Urlaubstag
    nicht mitzaehlen, sonst zoege er den Schnitt als "0 kWh Tag" trotzdem
    nach unten."""
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "uvdp1", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "off")
    coordinator.data["vehicle_discharge_kwh_total"] = 100.0
    coordinator._update_vehicle_discharge_profile()
    coordinator.data["vehicle_discharge_periods"]["day"]["key"] = str(dt_util.now().date() - timedelta(days=1))
    hass.states.async_set("input_boolean.urlaub", "on")
    coordinator.data["vehicle_discharge_kwh_total"] = 115.0
    coordinator._update_vehicle_discharge_profile()
    assert coordinator.data.get("vehicle_discharge_weekday_days", {}) == {}


# ----- _book_vehicle_discharge_weekday: korrekte Zuordnung, Urlaub/Daempfung -

async def test_book_vehicle_discharge_weekday_urlaub_aktiv_bucht_nicht(hass, coordinators):
    from custom_components.ev_assistant.const import CONF_URLAUB_ENTITY

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "bvdw1", options={CONF_URLAUB_ENTITY: "input_boolean.urlaub"},
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    coordinator._book_vehicle_discharge_weekday(5.0, dt_util.now().timestamp())
    assert coordinator.data.get("vehicle_discharge_weekday_days", {}) == {}


async def test_book_vehicle_discharge_weekday_ordnet_dem_tag_der_beobachtung_zu(hass, coordinators):
    """Kernverhalten des Fixes: die Buchung muss dem Wochentag von
    observed_ts folgen, nicht dem aktuellen (heutigen) Wochentag -- genau
    das war vorher kaputt, wenn eine Bestaetigung tagelang verzoegert war
    (siehe _update_vehicle_discharge()-Docstring)."""
    coordinator, _ = await _make_coordinator(hass, coordinators, "bvdw2")
    beobachtet_ts = dt_util.now().timestamp() - 3 * 86400  # garantiert ein anderer Wochentag
    beobachtet_wd = dt_util.as_local(dt_util.utc_from_timestamp(beobachtet_ts)).date().weekday()
    heute_wd = dt_util.now().date().weekday()
    assert beobachtet_wd != heute_wd
    coordinator._book_vehicle_discharge_weekday(5.0, beobachtet_ts)
    beobachtet_date = dt_util.as_local(dt_util.utc_from_timestamp(beobachtet_ts)).date().isoformat()
    assert coordinator.data["vehicle_discharge_weekday_days"] == {
        str(beobachtet_wd): [{"date": beobachtet_date, "kwh": 5.0}],
    }


async def test_book_vehicle_discharge_weekday_ausreisser_wird_gedaempft(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "bvdw3")
    ts = dt_util.now().timestamp()
    weekday = dt_util.now().date().weekday()
    coordinator.data["vehicle_discharge_weekday_days"] = {
        str(weekday): [{"date": "2020-01-01", "kwh": 10.0}, {"date": "2020-01-08", "kwh": 10.0}],
    }
    coordinator._book_vehicle_discharge_weekday(100.0, ts)  # 10x Schnitt (10 kWh)
    days = coordinator.data["vehicle_discharge_weekday_days"][str(weekday)]
    assert round(sum(d["kwh"] for d in days), 2) == 50.0  # 20 alt + 30 (gekappt)
    heute = dt_util.now().date().isoformat()
    neuer_eintrag = next(d for d in days if d["date"] == heute)
    assert neuer_eintrag["kwh"] == 30.0


async def test_update_vehicle_discharge_end_to_end_verzoegerte_bestaetigung_landet_auf_richtigem_tag(hass, coordinators):
    """Regressionstest fuer den eigentlichen Bug-Report: ein Abfall, der
    an einem Tag beobachtet, aber erst Tage spaeter bestaetigt wird
    (seltene Fahrzeug-Updates waehrend des Parkens), muss trotzdem dem
    Wochentag der BEOBACHTUNG gutgeschrieben werden, nicht dem der
    Bestaetigung."""
    from custom_components.ev_assistant.const import CONF_USABLE_KWH

    coordinator, _ = await _make_coordinator(hass, coordinators, "e2e1", options={CONF_USABLE_KWH: 50.0})
    coordinator._update_vehicle_discharge(84.0)  # Referenz initialisieren
    coordinator._update_vehicle_discharge(82.0)  # Abfall beobachtet (pending)
    # Simuliert: der Abfall wurde vor 3 Tagen beobachtet, wird aber erst
    # JETZT (jetziger Aufruf unten) bestaetigt.
    coordinator.data["vehicle_discharge_pending_since"] -= 3 * 86400
    beobachtet_ts = coordinator.data["vehicle_discharge_pending_since"]
    beobachtet_wd = dt_util.as_local(dt_util.utc_from_timestamp(beobachtet_ts)).date().weekday()
    heute_wd = dt_util.now().date().weekday()
    assert beobachtet_wd != heute_wd  # Testvoraussetzung: 3 Tage verschieben den Wochentag garantiert
    coordinator._update_vehicle_discharge(82.0)  # Bestaetigung "heute"
    assert coordinator.data["vehicle_discharge_kwh_total"] == 1.0  # 2% von 50 kWh
    beobachtet_date = dt_util.as_local(dt_util.utc_from_timestamp(beobachtet_ts)).date().isoformat()
    assert coordinator.data["vehicle_discharge_weekday_days"] == {
        str(beobachtet_wd): [{"date": beobachtet_date, "kwh": 1.0}],
    }


# ----- async_apply_vehicle_discharge_urlaub_since ---------------------------

async def test_async_apply_vehicle_discharge_urlaub_since_entfernt_kalendertag(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "auds1")
    today = dt_util.now().date()
    wd = today.weekday()
    coordinator.data["vehicle_discharge_weekday_days"] = {
        str(wd): [{"date": today.isoformat(), "kwh": 5.0}],
    }
    since_ts = dt_util.start_of_local_day().timestamp()
    result = await coordinator.async_apply_vehicle_discharge_urlaub_since(since_ts)
    assert result["reclassified_kwh"] == 5.0
    assert result["wochentage"] == {str(wd): 5.0}
    assert coordinator.data["vehicle_discharge_weekday_days"].get(str(wd), []) == []
    assert today.isoformat() in coordinator.data["vehicle_discharge_counted_dates"]


async def test_async_apply_vehicle_discharge_urlaub_since_ohne_eintrag_gibt_leeres_ergebnis(hass, coordinators):
    coordinator, _ = await _make_coordinator(hass, coordinators, "auds2")
    since_ts = dt_util.start_of_local_day().timestamp()
    result = await coordinator.async_apply_vehicle_discharge_urlaub_since(since_ts)
    assert result == {"reclassified_kwh": 0.0, "wochentage": {}}


async def test_async_apply_vehicle_discharge_urlaub_since_verhindert_erneute_zaehlung_durch_rollover(
    hass, coordinators,
):
    """Nach einer rueckwirkenden Korrektur darf der naechtliche Rollover
    (_update_vehicle_discharge_profile()) denselben Tag NICHT anhand des
    dann laengst wieder inaktiven Urlaubsschalters ein zweites Mal (und
    diesmal faelschlich als normalen 0-kWh-Tag) zaehlen -- siehe
    "vehicle_discharge_counted_dates" im Docstring beider Funktionen."""
    coordinator, _ = await _make_coordinator(hass, coordinators, "auds3")
    yesterday = dt_util.now().date() - timedelta(days=1)
    wd = yesterday.weekday()
    coordinator.data["vehicle_discharge_weekday_days"] = {
        str(wd): [{"date": yesterday.isoformat(), "kwh": 5.0}],
    }
    since_ts = dt_util.start_of_local_day(yesterday).timestamp()
    result = await coordinator.async_apply_vehicle_discharge_urlaub_since(since_ts)
    assert result["reclassified_kwh"] == 5.0

    # Rollover hat seit vorgestern nicht mehr gelaufen (Baseline zwei Tage
    # alt) -- holt also sowohl "vorgestern" als auch "gestern" nach.
    vorgestern = yesterday - timedelta(days=1)
    coordinator.data["vehicle_discharge_periods"] = {
        "day": {"key": str(vorgestern), "kwh": coordinator.data.get("vehicle_discharge_kwh_total", 0.0)},
    }
    coordinator._update_vehicle_discharge_profile()

    # "gestern" bleibt wie von der Korrektur entschieden -- kein neuer
    # (faelschlich normaler) Eintrag, obwohl der Urlaubsschalter (den es in
    # diesem Test nie gab bzw. der hier "aus" ist) das jetzt zulassen wuerde.
    assert coordinator.data["vehicle_discharge_weekday_days"].get(str(wd), []) == []
    # "vorgestern" war nie Teil der Korrektur -- der Rollover zaehlt ihn ganz
    # normal (anderer Wochentag als "gestern").
    other_wd = vorgestern.weekday()
    assert any(
        e["date"] == vorgestern.isoformat()
        for e in coordinator.data["vehicle_discharge_weekday_days"].get(str(other_wd), [])
    )


# ----- _async_apply_evcc_mode_control: Urlaubs-Pause ------------------------

async def test_apply_evcc_mode_control_urlaub_aktiv_ist_no_op(hass, coordinators):
    from custom_components.ev_assistant.const import (
        CONF_EVCC_MODE_CONTROL_ENABLED,
        CONF_URLAUB_ENTITY,
        CONF_USABLE_KWH,
    )

    coordinator, _ = await _make_coordinator(
        hass, coordinators, "aemc_u1",
        options={
            CONF_EVCC_MODE_CONTROL_ENABLED: True,
            CONF_USABLE_KWH: 50.0,
            CONF_URLAUB_ENTITY: "input_boolean.urlaub",
        },
    )
    hass.states.async_set("input_boolean.urlaub", "on")
    _seed_7_tage_schnitt(coordinator)
    coordinator._soc = 50.0
    coordinator._evcc_client = AsyncMock()
    coordinator._evcc_state = {"loadpoints": [{}]}
    await coordinator._async_apply_evcc_mode_control()
    coordinator._evcc_client.async_set_mode.assert_not_called()
    coordinator._evcc_client.async_probe_scope.assert_not_called()
    assert coordinator.data.get("evcc_mode_control") is None
