"""Tests fuer die Reichweite aus dem Live-SoC-Zaehler (coordinator.py::
_update_range_log()/_current_consumption_estimate_kwh_per_100km()): das
Fahrtenbuch geht nicht mehr ein, Kurzstreckentage zaehlen nicht, die
Temperatur wirkt glatt."""
from datetime import timedelta
from unittest.mock import patch

from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def _make_coordinator(hass, coordinators, entry_id="rl1"):
    from custom_components.ev_assistant.const import CONF_USABLE_KWH, DOMAIN
    from custom_components.ev_assistant.coordinator import EvAssistantCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={}, options={CONF_USABLE_KWH: 50.0}, entry_id=entry_id)
    entry.add_to_hass(hass)
    coordinator = EvAssistantCoordinator(hass, entry)
    coordinators.append(coordinator)
    await coordinator.async_setup()
    return coordinator, entry


def _tage(n, km=60.0, kwh=15.0, temp=None, ab=1):
    heute = dt_util.now().date()
    out = []
    for i in range(ab, ab + n):
        rec = {"d": (heute - timedelta(days=i)).isoformat(), "km": km, "kwh": kwh, "tw": 0.0, "tk": 0.0}
        if temp is not None:
            rec["tw"], rec["tk"] = temp * kwh, kwh
        out.append(rec)
    return out


async def test_tageslog_legt_stand_an_und_schliesst_den_vortag_ab(hass, coordinators):
    c, _ = await _make_coordinator(hass, coordinators)
    c.data["odo"] = 1000.0
    c.data["odo_unit"] = "km"
    c.data["vehicle_discharge_kwh_total"] = 100.0
    c.data.pop("range_snap", None)
    c._update_range_log()
    assert c.data["range_snap"]["odo"] == 1000.0
    # Der Stand stammt von gestern: heute Nacht wird der Vortag abgeschlossen.
    gestern = (dt_util.now().date() - timedelta(days=1)).isoformat()
    c.data["range_snap"] = {"date": gestern, "odo": 1000.0, "kwh": 100.0}
    c.data["range_temp_acc"] = {gestern: {"tw": 6.0 * 5.0, "tk": 5.0}}
    c.data["odo"] = 1062.0
    c.data["vehicle_discharge_kwh_total"] = 115.5
    c._update_range_log()
    assert c.data["range_tage"] == [{"d": gestern, "kwh": 15.5, "km": 62.0, "tw": 30.0, "tk": 5.0}]
    assert c.data["range_snap"]["date"] == dt_util.now().date().isoformat()
    assert c.data["range_snap"]["odo"] == 1062.0


async def test_tageslog_bucht_keinen_tag_bei_luecke_oder_ohne_odometer(hass, coordinators):
    c, _ = await _make_coordinator(hass, coordinators, "rl2")
    c.data["odo"] = 1100.0
    c.data["odo_unit"] = "km"
    c.data["vehicle_discharge_kwh_total"] = 120.0
    vor_drei_tagen = (dt_util.now().date() - timedelta(days=3)).isoformat()
    c.data["range_snap"] = {"date": vor_drei_tagen, "odo": 1000.0, "kwh": 100.0}
    c._update_range_log()
    assert not c.data.get("range_tage")  # Rollover verpasst: nicht gebucht
    assert c.data["range_snap"]["date"] == dt_util.now().date().isoformat()
    c.data["odo"] = None
    c._update_range_log()  # ohne Odometer passiert nichts
    assert c.data["range_snap"]["odo"] == 1100.0


async def test_temperaturprobe_je_tag_gewichtet_nach_kwh(hass, coordinators):
    c, _ = await _make_coordinator(hass, coordinators, "rl3")
    heute = dt_util.now().date().isoformat()
    c._outside_temp = 4.0
    c._range_temp_sample(1.0)
    c._outside_temp = 10.0
    c._range_temp_sample(3.0)
    acc = c.data["range_temp_acc"][heute]
    assert acc["tk"] == 4.0
    assert acc["tw"] / acc["tk"] == (4.0 * 1.0 + 10.0 * 3.0) / 4.0
    c._outside_temp = None
    c._range_temp_sample(5.0)  # ohne Temperatur nichts
    assert c.data["range_temp_acc"][heute]["tk"] == 4.0


async def test_verbrauch_kommt_aus_dem_live_soc_nicht_aus_dem_fahrtenbuch(hass, coordinators):
    from custom_components.ev_assistant.sensor import RangeEstimateSensor

    c, entry = await _make_coordinator(hass, coordinators, "rl4")
    c.data["range_tage"] = _tage(4, km=60.0, kwh=15.0)  # 25 kWh/100km
    c._vehicle_avg_consumption_kwh_per_100km = lambda: 18.0  # Lebenszeit, wird nicht gebraucht
    c._soc = 40.0
    with patch.object(c, "_consumption_by_temp_bucket", return_value={"0-10°C": 40.0}):
        c._outside_temp = 5.0
        assert c._current_consumption_estimate_kwh_per_100km() == 25.0
        attrs = RangeEstimateSensor(c, entry).extra_state_attributes
    assert attrs["verbrauch_quelle"] == "live_soc"
    assert attrs["live_soc_tage"] == 4
    assert c.range_estimate_km() == 80.0  # 40 % von 50 kWh = 20 kWh bei 25 kWh/100km


async def test_ohne_genug_tage_gilt_der_lebenszeit_schnitt(hass, coordinators):
    from custom_components.ev_assistant.sensor import RangeEstimateSensor

    c, entry = await _make_coordinator(hass, coordinators, "rl5")
    c.data["range_tage"] = _tage(1, km=60.0, kwh=15.0)  # nur 60 km, Schwelle 80
    c._vehicle_avg_consumption_kwh_per_100km = lambda: 18.0
    assert c._current_consumption_estimate_kwh_per_100km() == 18.0
    assert RangeEstimateSensor(c, entry).extra_state_attributes["verbrauch_quelle"] == "lebenszeit"


async def test_kurzstreckentage_und_unplausible_tage_zaehlen_nicht(hass, coordinators):
    c, _ = await _make_coordinator(hass, coordinators, "rl6")
    c.data["range_tage"] = _tage(3, km=60.0, kwh=15.0) + _tage(10, km=4.0, kwh=3.0, ab=4)
    c._vehicle_avg_consumption_kwh_per_100km = lambda: 18.0
    assert c._current_consumption_estimate_kwh_per_100km() == 25.0


async def test_temperatur_wirkt_ohne_sprung_an_der_alten_bandgrenze(hass, coordinators):
    c, _ = await _make_coordinator(hass, coordinators, "rl7")
    c.data["range_tage"] = _tage(4, km=60.0, kwh=18.0, temp=2.0) + _tage(4, km=60.0, kwh=12.0, temp=18.0, ab=5)
    c._vehicle_avg_consumption_kwh_per_100km = lambda: 18.0
    c._outside_temp = 9.9
    unter = c._current_consumption_estimate_kwh_per_100km()
    c._outside_temp = 10.1
    ueber = c._current_consumption_estimate_kwh_per_100km()
    assert abs(unter - ueber) < 1.0  # 0,2 Grad: nur der echte Verlauf, kein Sprung von rund 10 kWh/100km
    c._soc = 40.0
    c._outside_temp = 9.9
    r1 = c.range_estimate_km()
    c._outside_temp = 10.1
    r2 = c.range_estimate_km()
    assert abs(r1 - r2) < 5.0  # vorher: Sprung von etwa 52 auf 78 km
