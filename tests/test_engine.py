"""pytest fuer die reine Erkennungslogik (ohne Home Assistant)."""

import pytest
from engine import (
    ChargeDetector,
    ChargeSample,
    EfficiencyCalibrator,
    SignalDebouncer,
    TripDetector,
    TripSample,
    average_efficiency,
    battery_capacity_samples,
    calculate_co2_savings,
    calculate_range_km,
    calculate_savings,
    charge_before_pv_decision,
    charge_cost,
    consumption_by_temp_bucket,
    equivalent_full_cycles,
    estimate_battery_capacity_kwh,
    home_capacity_sample,
    is_plausible_trip_consumption,
    merge_pending,
    pop_pending,
    rolling_consumption_kwh_per_100km,
    temperature_bucket,
    weekday_usage_profile,
)


def stream(socs, start_ts=0, step=60, home=False, power=None, plug=None):
    return [
        ChargeSample(ts=start_ts + i * step, soc=v, home_charging=home, power_kw=power, plugged_in=plug)
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


# ----- plugged_in: Steckersignal ueberstimmt idle_timeout_s ----------------

def test_plugged_in_true_verhindert_idle_timeout_split():
    # idle_timeout_s=120, aber grosse Sample-Abstaende (300s) -- ohne
    # Steckersignal wuerde das laengst in mehrere Sessions zerfallen.
    det = ChargeDetector(idle_timeout_s=120)
    samples = stream([30, 40, 50, 60], start_ts=0, step=300, plug=True)
    assert run(det, samples) == []
    ev = run(det, stream([60], start_ts=1200, step=300, plug=False))[0]
    assert (ev.soc_start, ev.soc_end) == (30, 60)


def test_plugged_in_false_beendet_sofort_trotz_kurzer_standzeit():
    det = ChargeDetector(idle_timeout_s=9999)
    samples = stream([30, 40, 50], start_ts=0, step=60, plug=True)
    assert run(det, samples) == []
    ev = run(det, stream([50], start_ts=180, step=60, plug=False))[0]
    assert (ev.soc_start, ev.soc_end) == (30, 50)


def test_plugged_in_none_faellt_auf_idle_timeout_zurueck():
    # Kein Steckersensor konfiguriert (plugged_in immer None) -- unveraendertes
    # Verhalten wie vor Einfuehrung des Signals.
    det = ChargeDetector(idle_timeout_s=120)
    samples = stream([30, 40, 50], start_ts=0, step=60) + stream([50], start_ts=300)
    ev = run(det, samples)[0]
    assert (ev.soc_start, ev.soc_end) == (30, 50)


def test_soc_anstieg_bei_bestaetigt_ausgesteckt_startet_keine_ladung():
    # Bestaetigt ausgesteckt (z.B. Rekuperation waehrend der Fahrt) -- ein
    # SoC-Anstieg darf dann keine Fremdladung starten.
    det = ChargeDetector(start_delta=3.0)
    samples = stream([70, 73], start_ts=0, step=30, plug=False)
    assert run(det, samples) == []


def test_soc_anstieg_bei_ausgesteckt_verschiebt_anker_statt_erneut_zu_triggern():
    # Nach einem ignorierten Anstieg (Rekuperation) darf derselbe Anstieg bei
    # der naechsten Messung nicht nochmal ausgewertet werden -- der Anker
    # wird auf den neuen (hoeheren) Wert nachgefuehrt.
    det = ChargeDetector(start_delta=3.0)
    run(det, stream([70, 73], start_ts=0, step=30, plug=False))
    # Kein weiterer Anstieg -- bleibt bei 73, keine Ladung.
    assert run(det, stream([73], start_ts=60, plug=False)) == []


def test_soc_anstieg_bei_eingesteckt_startet_ladung_normal():
    # Gegenprobe: mit bestaetigt eingestecktem Stecker startet derselbe
    # SoC-Anstieg ganz normal eine Fremdladung.
    det = ChargeDetector(start_delta=3.0, idle_timeout_s=60)
    run(det, stream([70, 73], start_ts=0, step=30, plug=True))
    ev = run(det, stream([73], start_ts=200, plug=False))[0]
    assert (ev.soc_start, ev.soc_end) == (70, 73)


def test_active_property_zeigt_idle_zu_ladung_uebergang():
    """Der Coordinator nutzt .active, um eine laufende Fremdladung von
    Heimladen zu unterscheiden (siehe coordinator.py::
    _check_soc_thresholds) -- die Eigenschaft muss also genau am
    idle->aktiv-Uebergang von False auf True kippen, analog
    TripDetector.active."""
    det = ChargeDetector(start_delta=3.0, idle_timeout_s=60)
    assert det.active is False

    det.update(ChargeSample(ts=0, soc=70, home_charging=False))  # Anker-Init
    assert det.active is False

    det.update(ChargeSample(ts=30, soc=70, home_charging=False))  # kein Anstieg
    assert det.active is False

    det.update(ChargeSample(ts=60, soc=73, home_charging=False))  # Ladung beginnt
    assert det.active is True

    det.update(ChargeSample(ts=90, soc=75, home_charging=False))  # laedt weiter
    assert det.active is True

    det.update(ChargeSample(ts=160, soc=75, home_charging=False))  # 100s Timeout -> Ende
    assert det.active is False


# ----- SignalDebouncer: Flacker-/Aussetzer-Filterung -------------------------

def test_plug_debouncer_unbekannt_vor_erster_bestaetigung():
    d = SignalDebouncer(debounce_s=100)
    assert d.update(0, True) is None
    assert d.update(50, True) is None


def test_plug_debouncer_bestaetigt_nach_debounce_s():
    d = SignalDebouncer(debounce_s=100)
    d.update(0, True)
    assert d.update(99, True) is None
    assert d.update(100, True) is True


def test_plug_debouncer_ignoriert_unbekannten_rohwert():
    d = SignalDebouncer(debounce_s=100)
    d.update(0, True)
    d.update(100, True)
    assert d.update(150, None) is True  # unavailable/unknown -> haelt Stand


def test_plug_debouncer_kurzer_blip_schlaegt_nicht_durch():
    d = SignalDebouncer(debounce_s=100)
    d.update(0, True)
    d.update(100, True)
    assert d.update(150, False) is True  # Blip beginnt
    assert d.update(155, True) is True  # Blip endet nach 5s -> verworfen
    assert d.update(200, False) is True  # neuer Off-Versuch, Uhr laeuft neu
    assert d.update(255, False) is True  # 55s < 100s debounce


def test_plug_debouncer_echter_wechsel_schlaegt_nach_debounce_s_durch():
    d = SignalDebouncer(debounce_s=100)
    d.update(0, True)
    d.update(100, True)
    d.update(150, False)
    assert d.update(250, False) is False


def test_plug_debouncer_get_load_state_roundtrip():
    d = SignalDebouncer(debounce_s=100)
    d.update(0, True)
    d.update(100, True)
    d.update(150, False)
    state = d.get_state()

    d2 = SignalDebouncer(debounce_s=100)
    d2.load_state(state)
    assert d2.update(250, False) is False


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


def test_charge_get_state_load_state_ueberlebt_simulierten_neustart():
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


def test_charge_load_state_ohne_gespeicherten_zustand_ist_no_op():
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


# ----- merge_pending: faelschlich per idle_timeout_s gesplittete Ladung ----

def test_merge_pending_leere_liste_haengt_an():
    pending = []
    merge_pending(pending, {"start_ts": 100, "end_ts": 200, "soc_start": 40.0, "soc_end": 42.0,
                             "energy_kwh": 1.0, "energy_batt_kwh": 0.9, "energy_source": "soc"})
    assert len(pending) == 1


def test_merge_pending_ohne_soc_abfall_wird_zusammengefuehrt():
    pending = [{"start_ts": 100, "end_ts": 200, "soc_start": 40.0, "soc_end": 47.0,
                "energy_kwh": 4.0, "energy_batt_kwh": 3.5, "energy_source": "soc"}]
    merge_pending(pending, {"start_ts": 800, "end_ts": 900, "soc_start": 47.0, "soc_end": 56.0,
                             "energy_kwh": 4.0, "energy_batt_kwh": 3.5, "energy_source": "soc"})
    assert len(pending) == 1
    merged = pending[0]
    assert merged["start_ts"] == 100
    assert merged["end_ts"] == 900
    assert merged["soc_end"] == 56.0
    assert merged["delta_soc"] == 16.0
    assert merged["energy_kwh"] == 8.0
    assert merged["energy_batt_kwh"] == 7.0


def test_merge_pending_mit_soc_abfall_bleibt_getrennt():
    # SoC-Abfall dazwischen == gefahren -> zwei echte, getrennte Ladestopps
    pending = [{"start_ts": 100, "end_ts": 200, "soc_start": 40.0, "soc_end": 47.0,
                "energy_kwh": 4.0, "energy_batt_kwh": 3.5, "energy_source": "soc"}]
    merge_pending(pending, {"start_ts": 800, "end_ts": 900, "soc_start": 30.0, "soc_end": 40.0,
                             "energy_kwh": 4.0, "energy_batt_kwh": 3.5, "energy_source": "soc"})
    assert len(pending) == 2


def test_merge_pending_unterschiedliche_quelle_wird_als_mixed_markiert():
    pending = [{"start_ts": 100, "end_ts": 200, "soc_start": 40.0, "soc_end": 47.0,
                "energy_kwh": 4.0, "energy_batt_kwh": 3.5, "energy_source": "power_ac"}]
    merge_pending(pending, {"start_ts": 800, "end_ts": 900, "soc_start": 47.0, "soc_end": 56.0,
                             "energy_kwh": 4.0, "energy_batt_kwh": 3.5, "energy_source": "soc"})
    assert pending[0]["energy_source"] == "mixed"


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


# ----- calculate_co2_savings: CO2-Bilanz gegenueber einem Verbrenner -------

def test_calculate_co2_savings_durchgerechnetes_beispiel():
    r = calculate_co2_savings(
        km_driven=1000, ev_kwh_total=200, co2_per_kwh_kg=0.38,
        verbrenner_l_100km=6.5, co2_per_liter_kg=2.33,
    )
    assert r == {
        "co2_ev_kg": 76.0,
        "co2_verbrenner_kg": 151.45,
        "co2_ersparnis_kg": 75.45,
    }


@pytest.mark.parametrize("km_driven,ev_kwh_total,co2_per_kwh,l_100km", [
    (None, 200, 0.38, 6.5),
    (1000, None, 0.38, 6.5),
    (1000, 200, None, 6.5),
    (1000, 200, 0.38, None),
])
def test_calculate_co2_savings_fehlende_pflichtgroesse_liefert_none(km_driven, ev_kwh_total, co2_per_kwh, l_100km):
    assert calculate_co2_savings(km_driven, ev_kwh_total, co2_per_kwh, l_100km, 2.33) is None


# ----- TripDetector: Fahrtenbuch-Erkennung aus dem Kilometerstand ----------

def trip_stream(odos, start_ts=0, step=60, driving=None):
    return [TripSample(ts=start_ts + i * step, odo_km=v, driving=driving) for i, v in enumerate(odos)]


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


def test_kilometerstand_ruecksprung_im_stand_korrumpiert_anker_nicht():
    # Kurzer Sensor-Glitch im Stand (z.B. Odometer meldet kurzzeitig 0) darf
    # den Anker nicht auf den Glitch-Wert absinken lassen -- sonst sieht die
    # naechste echte Fahrt (ab dem korrekten, hoeheren Wert) faelschlich
    # riesig aus, weil start_odo aus dem Anker kommt.
    det = TripDetector(min_km=0.5, idle_timeout_s=300)
    samples = (
        trip_stream([1000.0, 1000.0], step=60)  # steht bei 1000 km
        + trip_stream([0.0], start_ts=120)  # Glitch: kurz 0 km
        + trip_stream([1005.0], start_ts=180)  # echte Fahrt ab 1000 km
        + trip_stream([1005.0], start_ts=541)  # Stillstand -> finalize
    )
    ev = run_trips(det, samples)[0]
    assert (ev.odo_start, ev.odo_end) == (1000.0, 1005.0)
    assert ev.km == 5.0


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


# ----- driving: Motor-/Fahr-Signal ergaenzt den Odometer-Vergleich --------

def test_driving_true_startet_fahrt_ohne_odometer_anstieg():
    # Odometer bleibt unveraendert (grob/selten aktualisierte Hersteller-API)
    # -- ohne driving-Signal wuerde das nie als Fahrt erkannt.
    det = TripDetector(min_km=0.5, idle_timeout_s=300)
    samples = (
        trip_stream([100.0, 100.0], step=60)
        + trip_stream([100.0, 100.0], start_ts=120, step=60, driving=True)
        + trip_stream([102.0], start_ts=250, driving=False)
        + trip_stream([102.0], start_ts=600, driving=False)  # 350s Standzeit -> finalize
    )
    ev = run_trips(det, samples)[0]
    assert (ev.odo_start, ev.odo_end) == (100.0, 102.0)


def test_driving_false_beendet_fahrt_nicht_sofort_sondern_nach_idle_timeout():
    # Kurzes Motor-Aus (z.B. Stopp-Start an der Ampel) mitten in der Fahrt
    # darf sie nicht beenden -- anders als plugged_in=False bei ChargeDetector.
    det = TripDetector(min_km=0.5, idle_timeout_s=120)
    samples = (
        trip_stream([50.0, 50.0], step=60, driving=False)
        + trip_stream([50.0], start_ts=120, driving=True)  # Fahrt beginnt
        + trip_stream([55.0], start_ts=150, driving=False)  # kurzer Stopp
        + trip_stream([55.0], start_ts=180, driving=True)  # faehrt weiter
        + trip_stream([60.0], start_ts=240, driving=False)
    )
    assert run_trips(det, samples) == []  # noch keine 120s Standzeit erreicht
    ev = run_trips(det, trip_stream([60.0], start_ts=370, driving=False))[0]
    assert (ev.odo_start, ev.odo_end) == (50.0, 60.0)


def test_driving_none_faellt_auf_odometer_vergleich_zurueck():
    # Kein Motor-Sensor konfiguriert (driving immer None) -- unveraendertes
    # Verhalten wie vor Einfuehrung des Signals.
    det = TripDetector(min_km=0.5, idle_timeout_s=120)
    samples = trip_stream([10.0, 10.0], step=60) + trip_stream([15.0], start_ts=120) + trip_stream([15.0], start_ts=300)
    ev = run_trips(det, samples)[0]
    assert (ev.odo_start, ev.odo_end) == (10.0, 15.0)


def test_trip_get_state_load_state_ueberlebt_simulierten_neustart():
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


def test_trip_load_state_ohne_gespeicherten_zustand_ist_no_op():
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


def test_active_property_zeigt_idle_zu_fahrt_uebergang():
    """Der Coordinator nutzt .active, um beim idle->aktiv-Uebergang einen
    GPS-/Zonen-Schnappschuss als Start-Ort-Vorschlag einzufrieren (siehe
    coordinator.py::_run_trip_detection) -- die Eigenschaft muss also genau
    an diesem Uebergang und nur dort von False auf True kippen."""
    det = TripDetector(min_km=0.5, idle_timeout_s=120)
    assert det.active is False

    det.update(TripSample(ts=0, odo_km=100.0))  # Anker-Initialisierung
    assert det.active is False

    det.update(TripSample(ts=60, odo_km=100.0))  # weiterhin Stillstand
    assert det.active is False

    det.update(TripSample(ts=120, odo_km=105.0))  # Fahrt beginnt
    assert det.active is True

    det.update(TripSample(ts=180, odo_km=110.0))  # faehrt weiter
    assert det.active is True

    det.update(TripSample(ts=310, odo_km=110.0))  # 130s Stillstand -> Fahrt endet
    assert det.active is False


# ----- weekday_usage_profile: Wochentags-Nutzungsprofil --------------------

def test_weekday_usage_profile_zu_kurzer_zeitraum_liefert_none():
    # 2024-01-01 ist ein Montag; nur 5 Tage Beobachtung -- unter min_days=7.
    assert weekday_usage_profile({}, "2024-01-01", "2024-01-05") is None


def test_weekday_usage_profile_genau_eine_woche():
    daily = {"2024-01-01": 12.0}  # Montag
    profil = weekday_usage_profile(daily, "2024-01-01", "2024-01-07")
    assert profil == {0: 12.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}


def test_weekday_usage_profile_tage_ohne_fahrt_zaehlen_mit_null():
    # Zwei Wochen, nur am ersten Montag eine Fahrt -- der zweite Montag
    # (ohne Fahrt) muss den Schnitt trotzdem auf die Haelfte druecken.
    daily = {"2024-01-01": 12.0}
    profil = weekday_usage_profile(daily, "2024-01-01", "2024-01-14")
    assert profil[0] == 6.0
    assert profil[6] == 0.0


def test_weekday_usage_profile_durchschnitt_ueber_mehrere_wochen():
    daily = {
        "2024-01-01": 10.0, "2024-01-08": 20.0,  # zwei Montage
        "2024-01-06": 5.0, "2024-01-13": 15.0,   # zwei Samstage
    }
    profil = weekday_usage_profile(daily, "2024-01-01", "2024-01-14")
    assert profil[0] == 15.0  # (10+20)/2
    assert profil[5] == 10.0  # (5+15)/2
    assert profil[1] == 0.0


# ----- charge_before_pv_decision: Lade-Empfehlung ---------------------------

def test_charge_before_pv_decision_ohne_prognose_akku_reicht():
    assert charge_before_pv_decision(available_kwh=20.0, needed_kwh=15.0) is False


def test_charge_before_pv_decision_ohne_prognose_akku_reicht_nicht():
    assert charge_before_pv_decision(available_kwh=10.0, needed_kwh=15.0) is True


def test_charge_before_pv_decision_mit_prognose_schliesst_luecke():
    # Akku allein reicht nicht (10 < 15), aber PV-Prognose deckt die Luecke.
    assert charge_before_pv_decision(available_kwh=10.0, needed_kwh=15.0, pv_forecast_kwh=8.0) is False


def test_charge_before_pv_decision_mit_prognose_luecke_bleibt():
    # PV-Prognose reicht nicht aus, um die Luecke zu schliessen.
    assert charge_before_pv_decision(available_kwh=10.0, needed_kwh=15.0, pv_forecast_kwh=2.0) is True


# ----- charge_cost: Fremdladungs-Gesamtkosten inkl. Start-/Blockiergebuehr --

def test_charge_cost_ohne_gebuehr():
    assert charge_cost(kwh=20.0, price_kwh=0.5) == 10.0


def test_charge_cost_mit_gebuehr():
    assert charge_cost(kwh=20.0, price_kwh=0.5, start_fee=1.5) == 11.5


def test_charge_cost_rundet_auf_zwei_nachkommastellen():
    assert charge_cost(kwh=10.333, price_kwh=0.333, start_fee=0.001) == 3.44


# ----- rolling_consumption_kwh_per_100km: Realverbrauch der letzten X Tage -

def _fahrt(start_ts, km, verbrauch_kwh=None):
    rec = {"start_ts": start_ts, "km": km}
    if verbrauch_kwh is not None:
        rec["verbrauch_kwh"] = verbrauch_kwh
    return rec


def test_rolling_consumption_durchgerechnetes_beispiel():
    now = 1_000_000.0
    fahrten = [
        _fahrt(now - 1 * 86400, km=50.0, verbrauch_kwh=10.0),
        _fahrt(now - 2 * 86400, km=50.0, verbrauch_kwh=10.0),
    ]
    # 100 km gesamt, 20 kWh gesamt -> 20 kWh/100km.
    assert rolling_consumption_kwh_per_100km(fahrten, now, window_days=30, min_km=50.0) == 20.0


def test_rolling_consumption_fahrten_ausserhalb_des_fensters_zaehlen_nicht():
    now = 1_000_000.0
    fahrten = [
        _fahrt(now - 1 * 86400, km=50.0, verbrauch_kwh=10.0),
        _fahrt(now - 60 * 86400, km=999.0, verbrauch_kwh=999.0),  # ausserhalb 30-Tage-Fenster
    ]
    assert rolling_consumption_kwh_per_100km(fahrten, now, window_days=30, min_km=10.0) == 20.0


def test_rolling_consumption_fahrt_ohne_verbrauch_kwh_zaehlt_km_nicht_mit():
    # Eine Fahrt ohne verbrauch_kwh darf ihre km nicht in den Nenner
    # einbringen, ohne die zugehoerige Energie zu kennen -- sonst waere das
    # Ergebnis zu niedrig verzerrt.
    now = 1_000_000.0
    fahrten = [
        _fahrt(now - 1 * 86400, km=50.0, verbrauch_kwh=10.0),
        _fahrt(now - 1 * 86400, km=200.0),  # kein verbrauch_kwh
    ]
    assert rolling_consumption_kwh_per_100km(fahrten, now, window_days=30, min_km=10.0) == 20.0


def test_rolling_consumption_unter_min_km_liefert_none():
    now = 1_000_000.0
    fahrten = [_fahrt(now - 1 * 86400, km=10.0, verbrauch_kwh=2.0)]
    assert rolling_consumption_kwh_per_100km(fahrten, now, window_days=30, min_km=50.0) is None


def test_rolling_consumption_leere_liste_liefert_none():
    assert rolling_consumption_kwh_per_100km([], now_ts=1_000_000.0, window_days=30, min_km=50.0) is None


# ----- calculate_range_km: Restreichweite aus SoC und Realverbrauch --------

def test_calculate_range_km_durchgerechnetes_beispiel():
    # 60% von 50 kWh = 30 kWh Akku, bei 15 kWh/100km -> 200 km.
    assert calculate_range_km(soc_pct=60.0, usable_kwh=50.0, consumption_kwh_per_100km=15.0) == 200.0


@pytest.mark.parametrize("soc_pct,consumption", [
    (None, 15.0),
    (60.0, None),
    (60.0, 0.0),
    (60.0, -5.0),
])
def test_calculate_range_km_fehlende_oder_unplausible_eingabe_liefert_none(soc_pct, consumption):
    assert calculate_range_km(soc_pct=soc_pct, usable_kwh=50.0, consumption_kwh_per_100km=consumption) is None


# ----- is_plausible_trip_consumption: Ausreisser aus SoC-Delta erkennen ----

def test_is_plausible_trip_consumption_normaler_verbrauch_ist_plausibel():
    # 15.6 kWh auf 84.3 km = 18.5 kWh/100km -- typischer EV-Verbrauch.
    assert is_plausible_trip_consumption(15.6, 84.3) is True


def test_is_plausible_trip_consumption_eingefrorener_soc_ist_unplausibel():
    # Beobachteter Fall: 147.1 km, aber wegen WiCAN-Ausfall nur 5.5 kWh
    # (statt real ~29 kWh) aus dem SoC-Delta geschaetzt.
    assert is_plausible_trip_consumption(5.5, 147.1) is False


def test_is_plausible_trip_consumption_zu_hoher_verbrauch_ist_unplausibel():
    assert is_plausible_trip_consumption(50.0, 50.0) is False  # 100 kWh/100km


@pytest.mark.parametrize("kwh,km", [(None, 50.0), (10.0, None), (10.0, 0.0), (10.0, -5.0)])
def test_is_plausible_trip_consumption_ohne_pruefbare_daten_liefert_true(kwh, km):
    assert is_plausible_trip_consumption(kwh, km) is True


def test_is_plausible_trip_consumption_kurze_strecke_wird_nicht_geprueft():
    # 1km/1% SoC-Delta ergibt rechnerisch 50 kWh/100km -- reines Artefakt der
    # Ganzprozent-Quantisierung, kein Sensorproblem. Unter min_km ausgenommen.
    assert is_plausible_trip_consumption(0.5, 1.0) is True
    assert is_plausible_trip_consumption(0.1, 4.9) is True
    assert is_plausible_trip_consumption(0.1, 5.0) is False


def test_is_plausible_trip_consumption_grenzwerte_inklusiv():
    assert is_plausible_trip_consumption(8.0, 100.0, 8.0, 40.0) is True
    assert is_plausible_trip_consumption(40.0, 100.0, 8.0, 40.0) is True
    assert is_plausible_trip_consumption(7.99, 100.0, 8.0, 40.0) is False


# ----- battery_capacity_samples / home_capacity_sample /                  --
# ----- estimate_battery_capacity_kwh ----------------------------------------

def test_battery_capacity_samples_filtert_kleine_huebe_und_fehlende_felder_raus():
    history = [
        {"kwh": 22.33, "delta_soc": 38.0, "erfasst_ts": 100},   # 58.76 kWh -> zaehlt
        {"kwh": 1.0, "delta_soc": 2.0, "erfasst_ts": 200},       # zu kleiner Hub -> raus
        {"kwh": 25.65, "delta_soc": -45.0, "erfasst_ts": 300},   # negativer delta_soc, |45| zaehlt
        {"kwh": None, "delta_soc": 30.0, "erfasst_ts": 400},     # kein kwh -> raus
        {"kwh": 10.0, "delta_soc": None, "erfasst_ts": 500},     # kein delta_soc -> raus
        {"kwh": 10.0, "delta_soc": 30.0},                        # kein erfasst_ts -> raus
    ]
    samples = battery_capacity_samples(history, min_soc_delta=20.0)
    assert samples == [
        {"value": 58.76, "ts": 100},
        {"value": 57.0, "ts": 300},
    ]


# ----- home_capacity_sample --------------------------------------------------

def test_home_capacity_sample_durchgerechnetes_beispiel():
    # 20 kWh Wallbox-Delta * 0.9 Wirkungsgrad = 18 kWh Batterie; 30% SoC-Hub
    # -> 18 / 0.3 = 60 kWh implizite Kapazitaet.
    assert home_capacity_sample(
        anchor_soc=30.0, anchor_wallbox_kwh=100.0,
        soc=60.0, wallbox_kwh=120.0,
        efficiency=0.9, min_soc_delta=20.0,
    ) == 60.0


def test_home_capacity_sample_zu_kleiner_hub_liefert_none():
    assert home_capacity_sample(
        anchor_soc=60.0, anchor_wallbox_kwh=100.0,
        soc=65.0, wallbox_kwh=103.0,
        efficiency=0.9, min_soc_delta=20.0,
    ) is None


@pytest.mark.parametrize("anchor_soc,anchor_kwh,soc,kwh,eff", [
    (None, 100.0, 60.0, 120.0, 0.9),
    (30.0, None, 60.0, 120.0, 0.9),
    (30.0, 100.0, None, 120.0, 0.9),
    (30.0, 100.0, 60.0, None, 0.9),
    (30.0, 100.0, 60.0, 120.0, None),
    (30.0, 100.0, 60.0, 120.0, 0.0),
])
def test_home_capacity_sample_fehlende_werte_liefert_none(anchor_soc, anchor_kwh, soc, kwh, eff):
    assert home_capacity_sample(anchor_soc, anchor_kwh, soc, kwh, eff, min_soc_delta=20.0) is None


def test_home_capacity_sample_wallbox_ohne_zuwachs_liefert_none():
    # z.B. Session sofort wieder abgebrochen, keine Energie geflossen.
    assert home_capacity_sample(
        anchor_soc=30.0, anchor_wallbox_kwh=100.0,
        soc=60.0, wallbox_kwh=100.0,
        efficiency=0.9, min_soc_delta=20.0,
    ) is None


# ----- estimate_battery_capacity_kwh -----------------------------------------

def test_estimate_battery_capacity_kwh_sortiert_gemischte_quellen_nach_ts():
    # Absichtlich NICHT vorsortiert -- muss selbst nach ts absteigend
    # sortieren, unabhaengig davon, aus welcher Quelle (Fremd-/Heimladung)
    # ein Sample stammt.
    samples = [
        {"value": 40.0, "ts": 100},   # alt, Ausreisser
        {"value": 60.0, "ts": 400},   # neueste
        {"value": 58.0, "ts": 300},
        {"value": 56.0, "ts": 200},
    ]
    assert estimate_battery_capacity_kwh(samples, max_samples=3, min_samples=2) == 58.0


def test_estimate_battery_capacity_kwh_unter_min_samples_liefert_none():
    assert estimate_battery_capacity_kwh([{"value": 55.0, "ts": 1}], max_samples=5, min_samples=2) is None


def test_estimate_battery_capacity_kwh_leere_liste_liefert_none():
    assert estimate_battery_capacity_kwh([], max_samples=5, min_samples=2) is None


# ----- temperature_bucket / consumption_by_temp_bucket ----------------------

@pytest.mark.parametrize("temp,expected", [
    (-5.0, "<0°C"),
    (0.0, "0-10°C"),
    (5.0, "0-10°C"),
    (10.0, "10-20°C"),
    (15.0, "10-20°C"),
    (20.0, ">20°C"),
    (25.0, ">20°C"),
])
def test_temperature_bucket_zuordnung(temp, expected):
    assert temperature_bucket(temp, boundaries=(0.0, 10.0, 20.0)) == expected


def test_temperature_bucket_ohne_temperatur_liefert_none():
    assert temperature_bucket(None) is None


def test_consumption_by_temp_bucket_gruppiert_und_mittelt():
    fahrten = [
        {"verbrauch_kwh": 3.0, "km": 20.0, "temp_start": -5.0},   # 15.0 kWh/100km, <0°C
        {"verbrauch_kwh": 4.0, "km": 20.0, "temp_start": -2.0},   # 20.0 kWh/100km, <0°C
        {"verbrauch_kwh": 3.5, "km": 20.0, "temp_start": -1.0},   # 17.5 kWh/100km, <0°C
        {"verbrauch_kwh": 2.0, "km": 20.0, "temp_start": 15.0},   # 10.0 kWh/100km, nur 1x -> raus
    ]
    result = consumption_by_temp_bucket(fahrten, boundaries=(0.0, 10.0, 20.0), min_samples=3)
    assert result == {"<0°C": 17.5}


def test_consumption_by_temp_bucket_ohne_pruefbare_daten_ausgeschlossen():
    fahrten = [
        {"verbrauch_kwh": None, "km": 20.0, "temp_start": 5.0},
        {"verbrauch_kwh": 3.0, "km": None, "temp_start": 5.0},
        {"verbrauch_kwh": 3.0, "km": 20.0, "temp_start": None},
    ]
    assert consumption_by_temp_bucket(fahrten, min_samples=1) == {}


# ----- equivalent_full_cycles ------------------------------------------------

def test_equivalent_full_cycles_ein_voller_zyklus():
    # 0->100 laden, 100->0 fahren: zusammen 200 Prozentpunkte -> 1 Zyklus.
    fahrten = [{"delta_soc": -100.0}]
    history = [{"delta_soc": 100.0}]
    assert equivalent_full_cycles(fahrten, history) == 1.0


def test_equivalent_full_cycles_summiert_mehrere_teilzyklen():
    fahrten = [{"delta_soc": -30.0}, {"delta_soc": -20.0}]  # 50 Prozentpunkte Entladung
    history = [{"delta_soc": 40.0}, {"delta_soc": 10.0}]     # 50 Prozentpunkte Ladung
    assert equivalent_full_cycles(fahrten, history) == 0.5


def test_equivalent_full_cycles_negative_ladung_wird_geklemmt():
    # Rekuperation waehrend einer Fremdladung (kaum real, aber ein negativer
    # delta_soc auf der Lade-Seite darf die Zyklen nicht senken).
    fahrten = [{"delta_soc": -10.0}]
    history = [{"delta_soc": -5.0}]
    assert equivalent_full_cycles(fahrten, history) == 0.05  # nur die 10 der Entladung zaehlen


def test_equivalent_full_cycles_ignoriert_fehlende_delta_soc():
    fahrten = [{"delta_soc": -10.0}, {"delta_soc": None}, {"km": 5.0}]
    history = [{"delta_soc": 10.0}, {"delta_soc": None}]
    assert equivalent_full_cycles(fahrten, history) == 0.1


def test_equivalent_full_cycles_leere_listen_liefert_null():
    assert equivalent_full_cycles([], []) == 0.0


def test_equivalent_full_cycles_beruecksichtigt_heimladungen():
    fahrten = [{"delta_soc": -100.0}]
    history = []
    # Alle 100 Prozentpunkte Ladung kommen aus Heim-Sessions statt Fremdladungen.
    assert equivalent_full_cycles(fahrten, history, home_charge_pct_total=100.0) == 1.0


def test_equivalent_full_cycles_negativer_heimladungs_gesamtwert_wird_geklemmt():
    fahrten = [{"delta_soc": -10.0}]
    history = []
    assert equivalent_full_cycles(fahrten, history, home_charge_pct_total=-5.0) == 0.05
