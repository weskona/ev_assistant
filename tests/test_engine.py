"""pytest fuer die reine Erkennungslogik (ohne Home Assistant)."""

import pytest
from engine import ChargeDetector, ChargeSample


def stream(socs, start_ts=0, step=60, home=False, power=None):
    return [
        ChargeSample(ts=start_ts + i * step, soc=v, home_charging=home, power_kw=power)
        for i, v in enumerate(socs)
    ]


def run(det, samples):
    return [e for s in samples if (e := det.update(s))]


def test_soc_pfad_ac_inkl_verluste():
    det = ChargeDetector(usable_kwh=45, charge_efficiency=0.88, idle_timeout_s=120)
    ev = run(det, stream([30, 30, 45, 60, 70, 70, 70]))[0]
    assert ev.delta_soc == 40
    assert ev.energy_source == "soc"
    assert round(ev.energy_batt_kwh, 2) == 18.0
    assert ev.energy_kwh == pytest.approx(18.0 / 0.88, abs=0.05)
    assert ev.losses_kwh > 0


def test_leistungs_integration_ac():
    n = 13
    socs = [30 + i * 1.6 for i in range(n)]
    samples = [ChargeSample(ts=i * 300, soc=socs[i], home_charging=False, power_kw=11.0) for i in range(n)]
    samples += stream([socs[-1]] * 3, start_ts=n * 300, step=300, power=0.0)
    det = ChargeDetector(charge_efficiency=0.88, power_is_ac=True, idle_timeout_s=600)
    ev = run(det, samples)[0]
    assert ev.energy_source == "power_ac"
    assert ev.energy_kwh == pytest.approx(9.6, abs=0.5)
    assert ev.energy_batt_kwh == pytest.approx(ev.energy_kwh * 0.88, abs=0.01)


def test_leistungs_integration_dc():
    n = 13
    socs = [30 + i * 1.6 for i in range(n)]
    samples = [ChargeSample(ts=i * 300, soc=socs[i], home_charging=False, power_kw=10.0) for i in range(n)]
    samples += stream([socs[-1]] * 3, start_ts=n * 300, step=300, power=0.0)
    det = ChargeDetector(charge_efficiency=0.90, power_is_ac=False, idle_timeout_s=600)
    ev = run(det, samples)[0]
    assert ev.energy_source == "power_dc"
    assert ev.energy_kwh == pytest.approx(ev.energy_batt_kwh / 0.90, abs=0.01)


def test_jitter_kein_fehltrigger():
    det = ChargeDetector(idle_timeout_s=120)
    assert run(det, stream([50, 50, 51, 50, 49, 50, 51, 50, 49])) == []


def test_heimladen_wird_ignoriert():
    det = ChargeDetector(idle_timeout_s=120)
    assert run(det, stream([30, 40, 55, 70, 80], home=True)) == []


def test_heimladen_beendet_fremdsession():
    det = ChargeDetector(usable_kwh=45, idle_timeout_s=9999)
    samples = stream([30, 45, 60], start_ts=0) + stream([65], start_ts=180, home=True)
    ev = run(det, samples)[0]
    assert (ev.soc_start, ev.soc_end) == (30, 60)


def test_zwei_sessions():
    det = ChargeDetector(usable_kwh=45, idle_timeout_s=120)
    samples = (
        stream([30, 30, 50, 60, 60, 60], start_ts=0)
        + stream([45, 40], start_ts=400)
        + stream([40, 55, 70, 70, 70], start_ts=600)
    )
    evs = run(det, samples)
    assert len(evs) == 2
    assert (evs[0].soc_start, evs[0].soc_end) == (30, 60)
    assert (evs[1].soc_start, evs[1].soc_end) == (40, 70)


def test_fahrt_beendet_ladung():
    det = ChargeDetector(usable_kwh=45, idle_timeout_s=9999, drop_ends=1.0)
    ev = run(det, stream([30, 50, 65, 62]))[0]
    assert ev.soc_end == 65


def test_as_dict_schema():
    det = ChargeDetector(usable_kwh=45, idle_timeout_s=120)
    d = run(det, stream([20, 20, 40, 60, 60, 60]))[0].as_dict()
    assert set(d) == {
        "start_ts", "end_ts", "soc_start", "soc_end", "delta_soc",
        "energy_kwh", "energy_batt_kwh", "losses_kwh",
        "energy_source", "duration_min", "kind",
    }
    assert d["energy_kwh"] >= d["energy_batt_kwh"]
