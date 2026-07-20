"""pytest fuer die reine Erkennungslogik (ohne Home Assistant)."""

import pytest
from engine import (
    ChargeDetector, ChargeSample, EfficiencyCalibrator, TripDetector, TripSample,
    average_efficiency, calculate_savings, pop_pending,
)


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


def test_get_state_load_state_ueberlebt_simulierten_neustart():
    """Ein HA-Neustart darf eine bereits laufende (noch nicht
    abgeschlossene) Fremdladung nicht verwerfen -- get_state()/load_state()
    muss denselben Ablauf liefern wie ohne Neustart dazwischen."""
    socs = [80, 80.5, 81.0, 82.0, 83.0, 81.5]  # letzter Wert fällt >drop_ends unter peak -> finalize
    samples = stream(socs, start_ts=0)

    det_ref = ChargeDetector(usable_kwh=45, idle_timeout_s=9999, start_delta=1.0, noise=0.5, drop_ends=1.0)
    events_ref = run(det_ref, samples)

    det_a = ChargeDetector(usable_kwh=45, idle_timeout_s=9999, start_delta=1.0, noise=0.5, drop_ends=1.0)
    events_a = run(det_a, samples[:3])  # Session ist an dieser Stelle bereits aktiv
    state = det_a.get_state()

    det_b = ChargeDetector(usable_kwh=45, idle_timeout_s=9999, start_delta=1.0, noise=0.5, drop_ends=1.0)
    det_b.load_state(state)
    events_b = run(det_b, samples[3:])

    d_ref = [e.as_dict() for e in events_ref]
    d_sim = [e.as_dict() for e in (events_a + events_b)]
    assert d_ref == d_sim
    assert d_ref[0]["soc_start"] == 80
    assert d_ref[0]["soc_end"] == 83.0


def test_load_state_ohne_gespeicherten_zustand_ist_no_op():
    det = ChargeDetector(usable_kwh=45)
    det.load_state(None)
    det.load_state({})
    assert det.get_state()["active"] is False
    assert det.get_state()["anchor_soc"] is None


# ----- EfficiencyCalibrator: Ladewirkungsgrad aus echten Heim-Ladesessions ---

def test_kalibrierung_erfolgreich():
    cal = EfficiencyCalibrator(usable_kwh=45)
    cal.start(soc=30, wallbox_kwh=100.0)
    eff = cal.end(soc=50, wallbox_kwh=110.2)
    # 20% von 45 kWh = 9 kWh Batterie, 10.2 kWh AC -> 9 / 10.2
    assert eff == pytest.approx(9.0 / 10.2, abs=0.001)


def test_kalibrierung_zu_kurze_session_wird_verworfen():
    cal = EfficiencyCalibrator(usable_kwh=45, min_soc_delta=5.0)
    cal.start(soc=30, wallbox_kwh=100.0)
    assert cal.end(soc=32, wallbox_kwh=101.0) is None


def test_kalibrierung_ohne_wallbox_wert_wird_verworfen():
    cal = EfficiencyCalibrator(usable_kwh=45)
    cal.start(soc=30, wallbox_kwh=None)
    assert cal.end(soc=50, wallbox_kwh=110.0) is None

    cal.start(soc=30, wallbox_kwh=100.0)
    assert cal.end(soc=50, wallbox_kwh=None) is None


def test_kalibrierung_unplausibler_wert_wird_verworfen():
    cal = EfficiencyCalibrator(usable_kwh=45, min_efficiency=0.5, max_efficiency=1.0)
    cal.start(soc=30, wallbox_kwh=100.0)
    # 20% von 45 kWh = 9 kWh Batterie, aber nur 5 kWh AC gemessen -> Effizienz > 1.0, unplausibel
    assert cal.end(soc=50, wallbox_kwh=105.0) is None


def test_kalibrierung_ohne_start_wird_verworfen():
    cal = EfficiencyCalibrator(usable_kwh=45)
    assert cal.end(soc=50, wallbox_kwh=110.0) is None


def test_kalibrierung_reset_nach_end():
    cal = EfficiencyCalibrator(usable_kwh=45)
    cal.start(soc=30, wallbox_kwh=100.0)
    cal.end(soc=50, wallbox_kwh=110.2)
    # Anker wurde zurueckgesetzt -> ohne neuen start() liefert end() None
    assert cal.end(soc=60, wallbox_kwh=120.0) is None


def test_average_efficiency_leer():
    assert average_efficiency([]) is None


def test_average_efficiency_rollierend():
    samples = [0.80, 0.82, 0.84, 0.86, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 1.00]
    # 11 Werte, max_samples=10 -> der aelteste (0.80) faellt raus
    avg = average_efficiency(samples, max_samples=10)
    assert avg == pytest.approx(sum(samples[1:]) / 10, abs=0.0001)


# ----- pop_pending: Auswahl bei mehreren gleichzeitig offenen Ladungen ------

def test_pop_pending_leere_liste():
    assert pop_pending([], None) is None
    assert pop_pending([], 123) is None


def test_pop_pending_ohne_start_ts_nimmt_die_aelteste():
    pending = [{"start_ts": 100, "kind": "a"}, {"start_ts": 200, "kind": "b"}]
    popped = pop_pending(pending, None)
    assert popped == {"start_ts": 100, "kind": "a"}
    assert pending == [{"start_ts": 200, "kind": "b"}]


def test_pop_pending_mit_start_ts_trifft_die_richtige():
    pending = [{"start_ts": 100, "kind": "a"}, {"start_ts": 200, "kind": "b"}, {"start_ts": 300, "kind": "c"}]
    popped = pop_pending(pending, 200)
    assert popped == {"start_ts": 200, "kind": "b"}
    assert pending == [{"start_ts": 100, "kind": "a"}, {"start_ts": 300, "kind": "c"}]


def test_pop_pending_unbekannter_start_ts_liefert_none_und_laesst_liste_unveraendert():
    pending = [{"start_ts": 100, "kind": "a"}]
    assert pop_pending(pending, 999) is None
    assert pending == [{"start_ts": 100, "kind": "a"}]


# ----- calculate_savings: Kostenvergleich gegenueber einem Verbrenner ------

def test_calculate_savings_durchgerechnetes_beispiel():
    r = calculate_savings(
        km_driven=1000, home_kwh=150, home_price_kwh=0.30,
        fremdladen_kosten=50, verbrenner_l_100km=6.5, verbrenner_price_per_liter=1.75,
    )
    assert r == {
        "heimladen_kosten": 45.0,
        "kosten_ev_gesamt": 95.0,
        "kosten_verbrenner_geschaetzt": 113.75,
        "ersparnis": 18.75,
    }


def test_calculate_savings_ohne_heimladen_nur_fremdladungskosten():
    r = calculate_savings(
        km_driven=1000, home_kwh=None, home_price_kwh=None,
        fremdladen_kosten=50, verbrenner_l_100km=6.5, verbrenner_price_per_liter=1.75,
    )
    assert r == {
        "heimladen_kosten": 0.0,
        "kosten_ev_gesamt": 50.0,
        "kosten_verbrenner_geschaetzt": 113.75,
        "ersparnis": 63.75,
    }


@pytest.mark.parametrize("km_driven,l_100km,price", [
    (None, 6.5, 1.75),
    (1000, None, 1.75),
    (1000, 6.5, None),
])
def test_calculate_savings_fehlende_pflichtgroesse_liefert_none(km_driven, l_100km, price):
    assert calculate_savings(km_driven, 150, 0.30, 50, l_100km, price) is None


# ----- TripDetector: Fahrtenbuch-Erkennung aus dem Kilometerstand ----------

def trip_stream(odos, start_ts=0, step=60):
    return [TripSample(ts=start_ts + i * step, odo_km=v) for i, v in enumerate(odos)]


def run_trips(det, samples):
    return [e for s in samples if (e := det.update(s))]


def test_fahrt_wird_erkannt_und_start_ts_ist_letzter_ruhepunkt():
    det = TripDetector(min_km=0.5, idle_timeout_s=300)
    samples = (
        trip_stream([100.0, 100.0], start_ts=0, step=60)  # steht, 0s/60s
        + trip_stream([105.0, 112.3, 120.0], start_ts=120, step=60)  # faehrt
        + trip_stream([120.0], start_ts=541)  # 301s Stillstand -> finalize
    )
    ev = run_trips(det, samples)[0]
    assert ev.start_ts == 60  # letzter Ruhepunkt VOR Fahrtbeginn, nicht der erste Fahrt-Sample
    assert ev.end_ts == 240
    assert (ev.odo_start, ev.odo_end) == (100.0, 120.0)
    assert ev.km == 20.0


def test_kleine_strecke_unter_min_km_wird_verworfen():
    det = TripDetector(min_km=0.5, idle_timeout_s=300)
    samples = trip_stream([50.0, 50.0], step=60) + trip_stream([50.2], start_ts=120) + trip_stream([50.2], start_ts=500)
    assert run_trips(det, samples) == []


def test_zwei_fahrten_getrennt_durch_standzeit():
    det = TripDetector(min_km=0.5, idle_timeout_s=120)
    samples = (
        trip_stream([0.0, 0.0], step=60)
        + trip_stream([10.0], start_ts=120)
        + trip_stream([10.0], start_ts=241)  # 121s Stillstand -> Fahrt 1 endet
        + trip_stream([10.0], start_ts=360)  # weiterhin Stillstand (Anker wird nachgefuehrt)
        + trip_stream([15.0], start_ts=420)  # neue Fahrt beginnt
        + trip_stream([15.0], start_ts=541)  # 121s Stillstand -> Fahrt 2 endet
    )
    evs = run_trips(det, samples)
    assert len(evs) == 2
    assert (evs[0].odo_start, evs[0].odo_end) == (0.0, 10.0)
    assert (evs[1].odo_start, evs[1].odo_end) == (10.0, 15.0)


def test_get_state_load_state_ueberlebt_simulierten_neustart():
    """Wie bei ChargeDetector: eine noch nicht abgeschlossene Fahrt darf
    einen HA-Neustart nicht verwerfen."""
    samples = trip_stream([200.0, 200.0], step=60) + trip_stream([205.0], start_ts=120) + trip_stream([205.0], start_ts=460)

    det_ref = TripDetector(min_km=0.5, idle_timeout_s=300)
    events_ref = run_trips(det_ref, samples)

    det_a = TripDetector(min_km=0.5, idle_timeout_s=300)
    events_a = run_trips(det_a, samples[:3])  # Fahrt ist an dieser Stelle bereits aktiv
    state = det_a.get_state()

    det_b = TripDetector(min_km=0.5, idle_timeout_s=300)
    det_b.load_state(state)
    events_b = run_trips(det_b, samples[3:])

    d_ref = [e.as_dict() for e in events_ref]
    d_sim = [e.as_dict() for e in (events_a + events_b)]
    assert d_ref == d_sim
    assert d_ref[0]["odo_start"] == 200.0
    assert d_ref[0]["odo_end"] == 205.0


def test_load_state_ohne_gespeicherten_zustand_ist_no_op():
    det = TripDetector()
    det.load_state(None)
    det.load_state({})
    assert det._active is False
    assert det._anchor_odo is None


def test_trip_as_dict_schema():
    det = TripDetector(min_km=0.5, idle_timeout_s=120)
    samples = trip_stream([0.0, 0.0], step=60) + trip_stream([5.0], start_ts=120) + trip_stream([5.0], start_ts=300)
    d = run_trips(det, samples)[0].as_dict()
    assert set(d) == {"start_ts", "end_ts", "odo_start", "odo_end", "km", "duration_min"}
