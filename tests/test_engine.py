"""pytest fuer die reine Erkennungslogik (ohne Home Assistant)."""

import pytest
from engine import (
    UNBEKANNTER_ANBIETER,
    ChargeDetector,
    ChargeSample,
    EfficiencyCalibrator,
    SignalDebouncer,
    TripDetector,
    TripSample,
    ac_dc_breakdown,
    ac_dc_breakdown_from_totals,
    ac_dc_bucket_key,
    anbieter_breakdown,
    anbieter_breakdown_from_totals,
    apply_ac_dc_delta,
    apply_anbieter_delta,
    average_efficiency,
    battery_capacity_samples,
    bekannte_anbieter,
    calculate_co2_savings,
    calculate_range_km,
    calculate_savings,
    charge_before_pv_decision,
    charge_cost,
    charge_pct_of_history_entry,
    charging_location_breakdown,
    consumption_by_temp_bucket,
    consumption_by_temp_bucket_from_totals,
    equivalent_full_cycles,
    equivalent_full_cycles_from_totals,
    estimate_battery_capacity_kwh,
    home_capacity_sample,
    home_session_solar_and_cost,
    is_plausible_trip_consumption,
    ladekarte_accrued_cost,
    ladekarte_current_fee,
    ladekarten_summary,
    leasing_status,
    merge_pending,
    normalize_anbieter,
    pop_pending,
    rolling_consumption_kwh_per_100km,
    rolling_km_per_day,
    split_by_age,
    temp_bucket_contribution,
    temperature_bucket,
    trip_avg_consumption_kwh_from_totals,
    trip_consumption_contribution,
    trip_discharge_pct,
    trip_weekday_kwh_parts,
    update_period_baseline,
    weekday_usage_profile,
    weekday_usage_profile_from_totals,
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


# ----- _energy(): Plausibilitaets-Abgleich Leistung vs. SoC-Delta ----------

def test_leistung_stark_unterschaetzt_faellt_auf_soc_zurueck():
    # Feldfall: SoC 42 -> 100 (58 Prozentpunkte), aber nur zwei niedrige,
    # weit auseinanderliegende Leistungswerte (grobe/lueckenhafte Telemetrie
    # z.B. Stellantis-App) -- die integrierte Leistung waere nur ein
    # Bruchteil dessen, was das SoC-Delta plausibel macht (real: 2.45 statt
    # ~26 kWh). engine.ChargeDetector._energy() muss auf die SoC-Schaetzung
    # zurueckfallen statt der klar zu niedrigen Leistung zu vertrauen.
    usable_kwh = 45.0
    n = 59  # SoC 42 -> 100 in 1-Prozentpunkt-Schritten
    samples = []
    for i in range(n):
        power = 2.0 if i == 5 else (1.0 if i == 30 else None)
        samples.append(ChargeSample(ts=i * 60, soc=42 + i, home_charging=False, power_kw=power))
    samples.append(ChargeSample(ts=n * 60, soc=100, home_charging=True, power_kw=None))
    det = ChargeDetector(usable_kwh=usable_kwh, charge_efficiency=0.88, power_is_ac=True, idle_timeout_s=9999)
    ev = run(det, samples)[0]
    assert ev.delta_soc == 58
    assert ev.energy_source == "soc_power_implausible"
    expected_batt = 58 / 100 * usable_kwh
    assert ev.energy_batt_kwh == pytest.approx(expected_batt, abs=0.01)
    assert ev.energy_kwh == pytest.approx(expected_batt / 0.88, abs=0.01)


def test_leistung_und_soc_konsistent_bleibt_unveraendert():
    # Gegenprobe: Leistung und SoC-Delta passen zusammen -- der neue
    # Plausibilitaets-Abgleich darf hier NICHT eingreifen, die
    # Leistungsschaetzung gewinnt weiterhin wie vor dem Fix.
    n = 13
    socs = [30 + i * 1.6 for i in range(n)]
    samples = [ChargeSample(ts=i * 300, soc=socs[i], home_charging=False, power_kw=11.0) for i in range(n)]
    samples += stream([socs[-1]] * 3, start_ts=n * 300, step=300, power=0.0)
    det = ChargeDetector(usable_kwh=45, charge_efficiency=0.88, power_is_ac=True, idle_timeout_s=600)
    ev = run(det, samples)[0]
    assert ev.energy_source == "power_ac"
    assert ev.energy_batt_kwh == pytest.approx(8.47, abs=0.05)


def test_leistung_hoeher_als_soc_schaetzung_bleibt_leistung():
    # SoC-Meldung ist grob (nur 3 Prozentpunkte erkannter Anstieg), aber die
    # Leistung wird zuverlaessig gemeldet und ergibt einen HOEHEREN,
    # plausibleren Wert -- dieser Fall ("SoC grob, Leistung zuverlaessig")
    # darf NICHT durch die SoC-Schaetzung ueberschrieben werden.
    n = 13
    socs = [42, 42, 42, 42, 43, 43.5, 44, 44.5, 45, 45, 45.5, 45.5, 45.5]
    samples = [ChargeSample(ts=i * 300, soc=socs[i], home_charging=False, power_kw=11.0) for i in range(n)]
    samples += stream([socs[-1]] * 3, start_ts=n * 300, step=300, power=11.0)
    det = ChargeDetector(usable_kwh=45, charge_efficiency=0.88, power_is_ac=True, idle_timeout_s=600, start_delta=3.0)
    ev = run(det, samples)[0]
    assert ev.energy_source == "power_ac"
    assert ev.energy_batt_kwh > ev.delta_soc / 100 * 45


def test_energy_ohne_soc_delta_bleibt_unveraendert():
    # delta_soc <= 0 ist bei _finalize() ueber die Zustandsmaschine nicht
    # erreichbar (eine Session aktiviert erst ab einem Anstieg >=
    # start_delta, delta_soc ist am Ende also immer >= start_delta) --
    # daher hier direkt gegen _energy() getestet, um den Plausibilitaets-
    # Abgleich bei delta_soc<=0 explizit abzusichern: er muss komplett
    # uebersprungen werden, die Leistung gewinnt wie vor dem Fix, selbst
    # wenn sie fuer sich genommen sehr klein ist.
    det = ChargeDetector(usable_kwh=45, charge_efficiency=0.88, power_is_ac=True)
    det._e_power_kwh = 0.5
    det._have_power = True
    e_ac, e_batt, source = det._energy(0.0)
    assert source == "power_ac"
    assert e_ac == pytest.approx(0.5)


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


def test_unplausibel_grosser_sprung_bei_ausgesteckt_startet_trotzdem_ladung():
    # Ein SoC-Sprung >= regen_implausible_delta_pct ist trotz bestaetigt
    # ausgestecktem Fahrzeug KEINE plausible Rekuperation mehr, sondern eine
    # waehrend einer Erkennungsluecke (z.B. mehrtaegiger Telemetrie-Ausfall)
    # verpasste Fremdladung -- muss trotzdem eine Erkennung starten.
    det = ChargeDetector(start_delta=3.0, idle_timeout_s=60, regen_implausible_delta_pct=15.0)
    run(det, stream([59, 98], start_ts=0, step=30, plug=False))
    ev = run(det, stream([98], start_ts=200, plug=False))[0]
    assert (ev.soc_start, ev.soc_end) == (59, 98)


def test_sprung_knapp_unter_der_schwelle_bleibt_regen():
    # Grenzfall: knapp UNTER der Schwelle bleibt es beim bisherigen
    # Rekuperations-Verhalten (keine Ladung).
    det = ChargeDetector(start_delta=3.0, regen_implausible_delta_pct=15.0)
    samples = stream([70, 84.9], start_ts=0, step=30, plug=False)
    assert run(det, samples) == []


def test_sprung_genau_auf_der_schwelle_startet_ladung():
    # Grenzfall: genau die Schwelle selbst zaehlt schon als unplausibel
    # (">=", siehe _update_idle()).
    det = ChargeDetector(start_delta=3.0, idle_timeout_s=60, regen_implausible_delta_pct=15.0)
    run(det, stream([70, 85], start_ts=0, step=30, plug=False))
    ev = run(det, stream([85], start_ts=200, plug=False))[0]
    assert (ev.soc_start, ev.soc_end) == (70, 85)


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


# ----- trip_weekday_kwh_parts()/weekday_usage_profile_from_totals(): --------
# Baseline-Variante von weekday_usage_profile() (siehe Fahrtenbuch/History-
# Archivierung, coordinator.py::_apply_trip_baselines()).

def test_trip_weekday_kwh_parts_exakter_verbrauch():
    assert trip_weekday_kwh_parts({"verbrauch_kwh": 12.0, "km": 50.0}) == ("exact", 12.0)


def test_trip_weekday_kwh_parts_ohne_verbrauch_faellt_auf_km_zurueck():
    assert trip_weekday_kwh_parts({"km": 50.0}) == ("est_km", 50.0)


def test_trip_weekday_kwh_parts_ohne_beides_liefert_none():
    assert trip_weekday_kwh_parts({}) is None


def test_weekday_usage_profile_from_totals_exakte_werte_entsprechen_voller_liste():
    # Montag (wd=0) zweimal mit bekanntem Verbrauch, Samstag (wd=5) zweimal --
    # muss dieselben Werte liefern wie die volle-Liste-Variante oben.
    weekday_kwh = {"0": 30.0, "5": 20.0}
    result = weekday_usage_profile_from_totals(weekday_kwh, {}, None, "2024-01-01", "2024-01-14")
    assert result[0] == 15.0
    assert result[5] == 10.0
    assert result[1] == 0.0


def test_weekday_usage_profile_from_totals_schaetzung_nutzt_aktuellen_verbrauch():
    # Fahrten ohne bekannten Verbrauch: km-Summe wird ERST HIER mit dem
    # AKTUELLEN Durchschnittsverbrauch multipliziert (siehe Docstring) --
    # nicht mit einem beim Einsortieren eingefrorenen Wert.
    weekday_km = {"0": 100.0}  # 100 km an Montagen, kein bekannter Verbrauch
    result = weekday_usage_profile_from_totals({}, weekday_km, 20.0, "2024-01-01", "2024-01-07", min_days=7)
    # 100 km * 20 kWh/100km = 20 kWh, auf einen einzigen Montag in der Woche verteilt.
    assert result[0] == 20.0


def test_weekday_usage_profile_from_totals_ohne_avg_consumption_traegt_estimat_nichts_bei():
    weekday_km = {"0": 100.0}
    result = weekday_usage_profile_from_totals({}, weekday_km, None, "2024-01-01", "2024-01-07", min_days=7)
    assert result[0] == 0.0


def test_weekday_usage_profile_from_totals_zu_kurzer_zeitraum_liefert_none():
    assert weekday_usage_profile_from_totals({}, {}, None, "2024-01-01", "2024-01-03", min_days=7) is None


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


def test_charge_cost_mit_blockiergebuehr():
    assert charge_cost(kwh=20.0, price_kwh=0.5, block_fee=5.0) == 15.0


def test_charge_cost_mit_start_und_blockiergebuehr():
    assert charge_cost(kwh=20.0, price_kwh=0.5, start_fee=1.5, block_fee=5.0) == 16.5


def test_charge_cost_mit_zeitgebuehr():
    assert charge_cost(kwh=20.0, price_kwh=0.5, time_fee=3.0) == 13.0


def test_charge_cost_mit_allen_drei_gebuehren():
    assert charge_cost(kwh=20.0, price_kwh=0.5, start_fee=1.5, block_fee=5.0, time_fee=3.0) == 19.5


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


# ----- rolling_km_per_day: rollierendes Fahrtempo fuer leasing_status() -----

def test_rolling_km_per_day_durchgerechnetes_beispiel():
    now = 30 * 86400.0
    fahrten = [
        {"start_ts": now - 5 * 86400, "km": 100.0},
        {"start_ts": now - 10 * 86400, "km": 50.0},
    ]
    assert rolling_km_per_day(fahrten, now_ts=now, window_days=30) == round(150.0 / 30, 2)


def test_rolling_km_per_day_fahrten_ausserhalb_des_fensters_zaehlen_nicht():
    now = 30 * 86400.0
    fahrten = [
        {"start_ts": now - 5 * 86400, "km": 100.0},
        {"start_ts": now - 40 * 86400, "km": 1000.0},  # ausserhalb des 30-Tage-Fensters
    ]
    assert rolling_km_per_day(fahrten, now_ts=now, window_days=30) == round(100.0 / 30, 2)


def test_rolling_km_per_day_ohne_fahrten_im_fenster_liefert_none():
    assert rolling_km_per_day([], now_ts=1_000_000.0, window_days=30) is None


def test_rolling_km_per_day_ignoriert_fehlende_felder():
    fahrten = [{"start_ts": None, "km": 100.0}, {"start_ts": 1000.0, "km": None}]
    assert rolling_km_per_day(fahrten, now_ts=1_000_000.0, window_days=30) is None


# ----- update_period_baseline: Perioden-Baselines + "prev" bei Rollover ----

def test_update_period_baseline_erster_aufruf_setzt_baseline_ohne_prev():
    # Frische Installation / erste Periode ueberhaupt -- Baseline wird
    # gesetzt, aber "prev" fehlt bewusst (kein Fantasiewert).
    result = update_period_baseline({}, {"month": "2026-08"}, 100.0, "kwh")
    assert result == {"month": {"key": "2026-08", "kwh": 100.0}}
    assert "prev" not in result["month"]


def test_update_period_baseline_gleicher_schluessel_bleibt_unveraendert():
    # Kein Rollover (Schluessel unveraendert) -- die Baseline bleibt exakt
    # wie sie war, "kWh in der Periode" wird vom Aufrufer weiterhin ueber
    # aktueller Gesamtstand minus dieser Baseline gebildet.
    periods = {"month": {"key": "2026-08", "kwh": 100.0}}
    result = update_period_baseline(periods, {"month": "2026-08"}, 142.0, "kwh")
    assert result == {"month": {"key": "2026-08", "kwh": 100.0}}


def test_update_period_baseline_rollover_setzt_neue_baseline_und_prev():
    # Echter Rollover (Monatswechsel): neue Baseline = aktueller Stand,
    # "prev" = aktueller Stand minus ALTE Baseline (der Verbrauch der
    # gerade abgeschlossenen Periode).
    periods = {"month": {"key": "2026-08", "kwh": 100.0}}
    result = update_period_baseline(periods, {"month": "2026-09"}, 142.0, "kwh")
    assert result == {"month": {"key": "2026-09", "kwh": 142.0, "prev": 42.0}}


def test_update_period_baseline_mehrere_perioden_unabhaengig():
    # Tag rollt ueber, Monat nicht -- nur der Tag-Eintrag aendert sich.
    periods = {
        "day": {"key": "2026-08-17", "kwh": 90.0},
        "month": {"key": "2026-08", "kwh": 100.0},
    }
    result = update_period_baseline(periods, {"day": "2026-08-18", "month": "2026-08"}, 142.0, "kwh")
    assert result["day"] == {"key": "2026-08-18", "kwh": 142.0, "prev": 52.0}
    assert result["month"] == {"key": "2026-08", "kwh": 100.0}


def test_update_period_baseline_zwei_rollover_hintereinander_nutzen_jeweils_aktuelle_baseline():
    # Zweiter Rollover muss gegen die Baseline des ERSTEN Rollovers rechnen,
    # nicht gegen die urspruengliche -- sonst waere "prev" nach mehreren
    # Rollovers falsch.
    periods = {"day": {"key": "2026-08-16", "kwh": 50.0}}
    after_first = update_period_baseline(periods, {"day": "2026-08-17"}, 90.0, "kwh")
    assert after_first["day"] == {"key": "2026-08-17", "kwh": 90.0, "prev": 40.0}
    after_second = update_period_baseline(after_first, {"day": "2026-08-18"}, 142.0, "kwh")
    assert after_second["day"] == {"key": "2026-08-18", "kwh": 142.0, "prev": 52.0}


def test_update_period_baseline_feldname_ist_parametrisierbar():
    # cost_periods nutzt "cost", kwh_periods nutzt "kwh" -- derselbe
    # Mechanismus, unterschiedlicher, vom Aufrufer bestimmter Feldname.
    periods = {"month": {"key": "2026-08", "cost": 20.0}}
    result = update_period_baseline(periods, {"month": "2026-09"}, 35.0, "cost")
    assert result == {"month": {"key": "2026-09", "cost": 35.0, "prev": 15.0}}


def test_update_period_baseline_ist_eine_reine_funktion():
    # Das uebergebene dict wird nicht mutiert -- der Aufrufer entscheidet
    # ueber Zuweisung/Persistierung des Rueckgabewerts.
    periods = {"month": {"key": "2026-08", "kwh": 100.0}}
    update_period_baseline(periods, {"month": "2026-09"}, 142.0, "kwh")
    assert periods == {"month": {"key": "2026-08", "kwh": 100.0}}


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


def test_temp_bucket_contribution_entspricht_voller_liste_berechnung():
    rec = {"verbrauch_kwh": 3.0, "km": 20.0, "temp_start": -5.0}
    assert temp_bucket_contribution(rec) == ("<0°C", 15.0)


def test_temp_bucket_contribution_ohne_pruefbare_daten_liefert_none():
    assert temp_bucket_contribution({"verbrauch_kwh": None, "km": 20.0, "temp_start": 5.0}) is None
    assert temp_bucket_contribution({"verbrauch_kwh": 3.0, "km": None, "temp_start": 5.0}) is None
    assert temp_bucket_contribution({"verbrauch_kwh": 3.0, "km": 20.0, "temp_start": None}) is None


def test_consumption_by_temp_bucket_from_totals_entspricht_voller_liste():
    # Dieselben drei Fahrten wie test_consumption_by_temp_bucket_gruppiert_und_mittelt(),
    # aber als laufend gepflegte Summe/Anzahl je Band (siehe
    # coordinator.py::_apply_trip_baselines()) statt als volle Liste.
    totals = {"<0°C": {"sum_pct": 15.0 + 20.0 + 17.5, "count": 3}}
    result = consumption_by_temp_bucket_from_totals(totals, min_samples=3)
    assert result == {"<0°C": 17.5}


def test_consumption_by_temp_bucket_from_totals_unter_min_samples_ausgeschlossen():
    totals = {"<0°C": {"sum_pct": 15.0, "count": 2}}
    assert consumption_by_temp_bucket_from_totals(totals, min_samples=3) == {}


# ----- trip_consumption_contribution()/trip_avg_consumption_kwh_from_totals():
# Baseline-Variante von coordinator._trip_avg_consumption_kwh().

def test_trip_consumption_contribution_exakter_verbrauch():
    assert trip_consumption_contribution({"verbrauch_kwh": 12.0}) == ("exact", 12.0)


def test_trip_consumption_contribution_aus_delta_soc():
    # -40% SoC -> Bruchteil 0.4 (die nutzbare Kapazitaet wird ERST beim
    # Lesen angewendet, siehe trip_avg_consumption_kwh_from_totals()).
    kind, value = trip_consumption_contribution({"delta_soc": -40.0})
    assert kind == "delta_soc"
    assert value == pytest.approx(0.4)


def test_trip_consumption_contribution_ohne_beides_liefert_none():
    assert trip_consumption_contribution({}) is None


def test_trip_avg_consumption_kwh_from_totals_mischung_exakt_und_geschaetzt():
    # Ein Eintrag mit exaktem Verbrauch (12 kWh) + einer nur mit delta_soc
    # (Bruchteil 0.4, bei 45 kWh nutzbarer Kapazitaet -> 18 kWh) -> Schnitt
    # (12+18)/2 = 15.0, identisch zur alten Live-Berechnung mit denselben
    # zwei Fahrten.
    result = trip_avg_consumption_kwh_from_totals(
        exact_sum_kwh=12.0, exact_count=1, deltasoc_sum_frac=0.4, deltasoc_count=1, usable_kwh=45.0,
    )
    assert result == 15.0


def test_trip_avg_consumption_kwh_from_totals_ohne_eintraege_liefert_none():
    assert trip_avg_consumption_kwh_from_totals(0.0, 0, 0.0, 0, 45.0) is None


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


def test_trip_discharge_pct_und_charge_pct_of_history_entry():
    assert trip_discharge_pct({"delta_soc": -30.0}) == 30.0
    assert trip_discharge_pct({}) == 0.0
    assert charge_pct_of_history_entry({"delta_soc": 40.0}) == 40.0
    assert charge_pct_of_history_entry({"delta_soc": -10.0}) == 0.0  # geklemmt
    assert charge_pct_of_history_entry({}) == 0.0


def test_equivalent_full_cycles_from_totals_entspricht_voller_liste_berechnung():
    fahrten = [{"delta_soc": -60.0}, {"delta_soc": -40.0}]
    history = [{"delta_soc": 90.0}, {"delta_soc": -5.0}]  # zweiter Wert wird geklemmt
    erwartet = equivalent_full_cycles(fahrten, history, home_charge_pct_total=10.0)
    discharge_total = sum(trip_discharge_pct(r) for r in fahrten)
    charge_total = sum(charge_pct_of_history_entry(r) for r in history)
    result = equivalent_full_cycles_from_totals(discharge_total, charge_total, home_charge_pct_total=10.0)
    assert result == erwartet == 1.0  # (100 + 90 + 10) / 200


def test_equivalent_full_cycles_from_totals_bleibt_unveraendert_wenn_alte_eintraege_verschwinden():
    # Der ganze Sinn der Baseline: wird die Detail-Liste spaeter gekuerzt
    # (siehe split_by_age()), bleibt equivalent_full_cycles_from_totals()
    # trotzdem beim ALTEN (korrekten) Ergebnis -- die Summen selbst wurden
    # nie rueckwirkend veraendert, nur die (hier gar nicht mehr verwendete)
    # Detail-Liste.
    result_vor_kuerzung = equivalent_full_cycles_from_totals(100.0, 90.0, home_charge_pct_total=10.0)
    # Nach einer Kuerzung stuenden dieselben zwei Zahlen weiter unveraendert
    # in self.data["fahrten_discharge_pct_total"]/["history_charge_pct_total"] --
    # sie haengen nicht an der (jetzt kuerzeren) Liste.
    result_nach_kuerzung = equivalent_full_cycles_from_totals(100.0, 90.0, home_charge_pct_total=10.0)
    assert result_vor_kuerzung == result_nach_kuerzung == 1.0


# ----- home_session_solar_and_cost -------------------------------------------

def test_home_session_solar_and_cost_kwh_gewichteter_solaranteil():
    sessions = [
        {"kwh": 2.0, "solar_pct": 100.0},   # klein, viel Solar
        {"kwh": 20.0, "solar_pct": 0.0},    # gross, kein Solar
    ]
    # (2*100 + 20*0) / 22 = 9.09...
    result = home_session_solar_and_cost(sessions)
    assert result["solar_pct"] == 9.1
    assert "kosten_gesamt" not in result
    assert "preis_je_kwh" not in result


def test_home_session_solar_and_cost_kosten_werden_summiert_nicht_gewichtet():
    sessions = [
        {"kwh": 10.0, "kosten": 2.0},
        {"kwh": 5.0, "kosten": 1.0},
    ]
    result = home_session_solar_and_cost(sessions)
    assert result["kosten_gesamt"] == 3.0
    assert result["preis_je_kwh"] == round(3.0 / 15.0, 4)
    assert "solar_pct" not in result


def test_home_session_solar_and_cost_fehlende_felder_werden_ausgelassen_nicht_null():
    sessions = [
        {"kwh": 10.0},                                # weder solar_pct noch kosten
        {"kwh": 5.0, "solar_pct": 50.0},               # nur solar_pct
        {"kwh": 8.0, "kosten": 4.0},                   # nur kosten
    ]
    result = home_session_solar_and_cost(sessions)
    assert result["solar_pct"] == 50.0
    assert result["kosten_gesamt"] == 4.0
    assert result["preis_je_kwh"] == round(4.0 / 8.0, 4)


def test_home_session_solar_and_cost_ignoriert_sessions_ohne_oder_mit_null_kwh():
    sessions = [
        {"kwh": None, "solar_pct": 80.0, "kosten": 1.0},
        {"kwh": 0.0, "solar_pct": 80.0, "kosten": 1.0},
    ]
    assert home_session_solar_and_cost(sessions) == {}


def test_home_session_solar_and_cost_leere_liste_liefert_leeres_dict():
    assert home_session_solar_and_cost([]) == {}


# ----- charging_location_breakdown -------------------------------------------

def test_charging_location_breakdown_nur_heim():
    result = charging_location_breakdown(
        home_kwh=100.0, home_cost=25.0, extern_kwh=0.0, extern_cost=0.0,
        km_driven=500.0, home_solar_pct=60.0,
    )
    assert result["heim"] == {
        "kwh": 100.0, "kosten": 25.0, "kwh_anteil_pct": 100.0,
        "kosten_anteil_pct": 100.0, "preis_je_kwh": 0.25, "solar_pct": 60.0,
    }
    # Fremd hat kwh=0/kosten=0 -- Rohwerte bleiben, aber kein Anteil/Preis.
    assert result["fremd"] == {"kwh": 0.0, "kosten": 0.0}
    assert result["eur_je_100km"] == 5.0


def test_charging_location_breakdown_nur_fremd():
    result = charging_location_breakdown(
        home_kwh=0.0, home_cost=0.0, extern_kwh=50.0, extern_cost=30.0,
        km_driven=250.0,
    )
    assert result["fremd"] == {
        "kwh": 50.0, "kosten": 30.0, "kwh_anteil_pct": 100.0,
        "kosten_anteil_pct": 100.0, "preis_je_kwh": 0.6,
    }
    assert result["heim"] == {"kwh": 0.0, "kosten": 0.0}
    assert "solar_pct" not in result.get("heim", {})
    assert result["eur_je_100km"] == 12.0


def test_charging_location_breakdown_gemischt_anteile_summieren_zu_100():
    result = charging_location_breakdown(
        home_kwh=70.0, home_cost=14.0, extern_kwh=30.0, extern_cost=21.0,
        km_driven=400.0, home_solar_pct=45.0,
    )
    assert result["heim"]["kwh_anteil_pct"] + result["fremd"]["kwh_anteil_pct"] == 100.0
    assert result["heim"]["kosten_anteil_pct"] + result["fremd"]["kosten_anteil_pct"] == 100.0
    assert result["heim"]["preis_je_kwh"] == 0.2
    assert result["fremd"]["preis_je_kwh"] == 0.7
    assert result["heim"]["solar_pct"] == 45.0
    # (14+21) / 400 * 100 = 8.75
    assert result["eur_je_100km"] == 8.75


def test_charging_location_breakdown_km_null_liefert_kein_eur_je_100km():
    result = charging_location_breakdown(
        home_kwh=10.0, home_cost=2.0, extern_kwh=5.0, extern_cost=3.0, km_driven=0.0,
    )
    assert "eur_je_100km" not in result


def test_charging_location_breakdown_km_none_liefert_kein_eur_je_100km():
    result = charging_location_breakdown(
        home_kwh=10.0, home_cost=2.0, extern_kwh=5.0, extern_cost=3.0, km_driven=None,
    )
    assert "eur_je_100km" not in result


def test_charging_location_breakdown_kwh_null_an_einem_ort_kein_anteil_kein_preis():
    result = charging_location_breakdown(
        home_kwh=0.0, home_cost=None, extern_kwh=40.0, extern_cost=20.0, km_driven=200.0,
    )
    assert result["heim"] == {"kwh": 0.0}
    assert "kwh_anteil_pct" not in result["heim"]
    assert "preis_je_kwh" not in result["heim"]
    assert result["fremd"]["kwh_anteil_pct"] == 100.0


def test_charging_location_breakdown_fehlender_solaranteil_wird_ausgelassen():
    result = charging_location_breakdown(
        home_kwh=10.0, home_cost=2.0, extern_kwh=5.0, extern_cost=1.0,
        km_driven=100.0, home_solar_pct=None,
    )
    assert "solar_pct" not in result["heim"]


def test_charging_location_breakdown_fehlende_kosten_lassen_eur_je_100km_trotzdem_zu():
    # home_cost unbekannt (nicht 0!) -- eur_je_100km rechnet trotzdem mit
    # dem, was bekannt ist (analog calculate_savings()).
    result = charging_location_breakdown(
        home_kwh=10.0, home_cost=None, extern_kwh=20.0, extern_cost=10.0, km_driven=100.0,
    )
    assert "kosten" not in result["heim"]
    assert result["eur_je_100km"] == 10.0


def test_charging_location_breakdown_alles_none_liefert_leeres_dict():
    result = charging_location_breakdown(
        home_kwh=None, home_cost=None, extern_kwh=None, extern_cost=None, km_driven=None,
    )
    assert result == {}


def test_charging_location_breakdown_leere_eingaben_liefert_partielles_dict():
    # home komplett unbekannt (None, nicht 0) -- die Gesamtsumme besteht
    # dann nur aus dem bekannten Fremd-Anteil, der folgerichtig 100% ist
    # (analog calculate_savings(): fehlende Heimladen-Daten blockieren die
    # Rechnung mit dem, was bekannt ist, nicht).
    result = charging_location_breakdown(
        home_kwh=None, home_cost=None, extern_kwh=15.0, extern_cost=None, km_driven=None,
    )
    assert result == {"fremd": {"kwh": 15.0, "kwh_anteil_pct": 100.0}}


def test_charging_location_breakdown_extra_cost_fliesst_nur_in_eur_je_100km():
    # extra_cost (z.B. Ladekarten-Grundgebuehr) darf die Ladeort-Anteile/
    # den Preis je kWh NICHT verzerren -- nur eur_je_100km beruecksichtigt
    # sie (fahrzeugweit, keinem Ladeort zuzuordnen).
    ohne_extra = charging_location_breakdown(
        home_kwh=None, home_cost=None, extern_kwh=20.0, extern_cost=10.0, km_driven=100.0,
    )
    mit_extra = charging_location_breakdown(
        home_kwh=None, home_cost=None, extern_kwh=20.0, extern_cost=10.0, km_driven=100.0,
        extra_cost=5.0,
    )
    assert mit_extra["fremd"] == ohne_extra["fremd"]
    assert ohne_extra["eur_je_100km"] == 10.0
    assert mit_extra["eur_je_100km"] == 15.0


def test_charging_location_breakdown_nur_extra_cost_liefert_trotzdem_eur_je_100km():
    # Auch ganz ohne bekannte Heim-/Fremdkosten zaehlt extra_cost allein
    # schon fuer eur_je_100km.
    result = charging_location_breakdown(
        home_kwh=None, home_cost=None, extern_kwh=None, extern_cost=None, km_driven=50.0,
        extra_cost=10.0,
    )
    assert result == {"eur_je_100km": 20.0}


# ----- normalize_anbieter / bekannte_anbieter / anbieter_breakdown:
# Fremdladung-Anbieter (WO geladen, NICHT die Ladekarte/WOMIT bezahlt) -------

def test_normalize_anbieter_trimmt_und_kleinschreibt():
    assert normalize_anbieter("  EnBW  ") == "enbw"
    assert normalize_anbieter("Ionity") == "ionity"


def test_normalize_anbieter_leer_oder_none_liefert_none():
    assert normalize_anbieter(None) is None
    assert normalize_anbieter("") is None
    assert normalize_anbieter("   ") is None


def test_bekannte_anbieter_dedupliziert_case_insensitiv_neueste_zuerst():
    # history ist bereits neueste-zuerst sortiert (siehe
    # coordinator.py::async_log_charge()) -- "EnBW" (juengste Schreibweise)
    # gewinnt gegen die aeltere "enbw"-Schreibweise.
    history = [
        {"anbieter": "Ionity"},
        {"anbieter": "EnBW"},
        {"anbieter": "enbw"},
    ]
    assert bekannte_anbieter(history) == ["Ionity", "EnBW"]


def test_bekannte_anbieter_ignoriert_ladungen_ohne_anbieter():
    history = [{"anbieter": None}, {}, {"anbieter": "Aral pulse"}]
    assert bekannte_anbieter(history) == ["Aral pulse"]


def test_bekannte_anbieter_limit():
    history = [{"anbieter": "A"}, {"anbieter": "B"}, {"anbieter": "C"}]
    assert bekannte_anbieter(history, limit=2) == ["A", "B"]


def test_bekannte_anbieter_leere_historie_liefert_leere_liste():
    assert bekannte_anbieter([]) == []
    assert bekannte_anbieter(None) == []


def test_anbieter_breakdown_klassifiziert_je_anbieter():
    history = [
        {"anbieter": "EnBW", "kwh": 10.0, "kosten": 5.0},
        {"anbieter": "Ionity", "kwh": 30.0, "kosten": 21.0},
    ]
    result = anbieter_breakdown(history)
    assert result["EnBW"]["kwh"] == 10.0
    assert result["EnBW"]["anzahl"] == 1
    assert result["EnBW"]["kwh_anteil_pct"] == 25.0
    assert result["EnBW"]["preis_je_kwh"] == 0.5
    assert result["Ionity"]["kwh"] == 30.0
    assert result["Ionity"]["kwh_anteil_pct"] == 75.0


def test_anbieter_breakdown_ohne_anbieter_landet_unter_unbekannt_statt_verworfen():
    history = [
        {"anbieter": "EnBW", "kwh": 10.0, "kosten": 5.0},
        {"kwh": 20.0, "kosten": 10.0},  # kein anbieter-Feld
        {"anbieter": "", "kwh": 5.0, "kosten": 2.0},  # leerer Anbieter
    ]
    result = anbieter_breakdown(history)
    assert UNBEKANNTER_ANBIETER in result
    assert result[UNBEKANNTER_ANBIETER]["anzahl"] == 2
    assert result[UNBEKANNTER_ANBIETER]["kwh"] == 25.0
    assert "EnBW" in result


def test_anbieter_breakdown_case_insensitiv_zusammengefuehrt_neueste_schreibweise_gewinnt():
    # history neueste-zuerst: "EnBW" ist jungste Schreibweise, "enbw" aelter.
    history = [
        {"anbieter": "EnBW", "kwh": 10.0, "kosten": 5.0},
        {"anbieter": "enbw", "kwh": 5.0, "kosten": 2.5},
    ]
    result = anbieter_breakdown(history)
    assert list(result.keys()) == ["EnBW"]
    assert result["EnBW"]["kwh"] == 15.0
    assert result["EnBW"]["anzahl"] == 2


def test_anbieter_breakdown_fehlende_einzelfelder_werden_ausgelassen_nicht_null():
    # Eine Ladung ohne kwh traegt nichts zur kWh-Summe bei, zaehlt aber
    # trotzdem mit (anzahl), und die Kosten-Summe bleibt unberuehrt.
    history = [
        {"anbieter": "EnBW", "kosten": 5.0},  # kein kwh
        {"anbieter": "EnBW", "kwh": 10.0, "kosten": 4.0},
    ]
    result = anbieter_breakdown(history)
    assert result["EnBW"]["kwh"] == 10.0
    assert result["EnBW"]["kosten"] == 9.0
    assert result["EnBW"]["anzahl"] == 2
    assert result["EnBW"]["preis_je_kwh"] == 0.9


def test_anbieter_breakdown_leere_historie_liefert_leeres_dict():
    assert anbieter_breakdown([]) == {}
    assert anbieter_breakdown(None) == {}


def test_anbieter_breakdown_ladekarten_grundgebuehr_fliesst_nicht_ein():
    # anbieter_breakdown() kennt Ladekarten gar nicht -- es aggregiert nur
    # rec["kosten"] (die tatsaechlichen Ladungskosten), niemals extra_cost.
    history = [{"anbieter": "EnBW", "kwh": 10.0, "kosten": 5.0}]
    result = anbieter_breakdown(history)
    assert result["EnBW"]["kosten"] == 5.0


# ----- apply_anbieter_delta()/anbieter_breakdown_from_totals(): Baseline-
# Variante von anbieter_breakdown() (siehe Fahrtenbuch/History-Archivierung).

def test_apply_anbieter_delta_addiert_und_ergebnis_entspricht_voller_liste():
    history = [
        {"anbieter": "EnBW", "kwh": 10.0, "kosten": 5.0, "erfasst_ts": 100},
        {"anbieter": "Ionity", "kwh": 30.0, "kosten": 21.0, "erfasst_ts": 200},
    ]
    totals = {}
    for rec in history:
        totals = apply_anbieter_delta(totals, rec, 1)
    result = anbieter_breakdown_from_totals(totals)
    erwartet = anbieter_breakdown(history)
    assert result == erwartet


def test_apply_anbieter_delta_entfernen_macht_hinzufuegen_rueckgaengig():
    rec = {"anbieter": "EnBW", "kwh": 10.0, "kosten": 5.0, "erfasst_ts": 100}
    totals = apply_anbieter_delta({}, rec, 1)
    totals = apply_anbieter_delta(totals, rec, -1)
    assert totals == {}


def test_apply_anbieter_delta_case_insensitiv_zusammengefuehrt():
    totals = apply_anbieter_delta({}, {"anbieter": "enbw", "kwh": 5.0, "kosten": 2.5, "erfasst_ts": 100}, 1)
    # Juengere Ladung mit anderer Schreibweise: kwh/kosten/anzahl summieren
    # sich, Label wechselt auf die juengere Schreibweise (hoeherer erfasst_ts).
    totals = apply_anbieter_delta(totals, {"anbieter": "EnBW", "kwh": 10.0, "kosten": 5.0, "erfasst_ts": 200}, 1)
    result = anbieter_breakdown_from_totals(totals)
    assert list(result.keys()) == ["EnBW"]
    assert result["EnBW"]["kwh"] == 15.0
    assert result["EnBW"]["anzahl"] == 2


def test_apply_anbieter_delta_reine_funktion_mutiert_eingabe_nicht():
    original = {}
    apply_anbieter_delta(original, {"anbieter": "EnBW", "kwh": 1.0, "erfasst_ts": 1}, 1)
    assert original == {}


def test_anbieter_breakdown_from_totals_leer_liefert_leeres_dict():
    assert anbieter_breakdown_from_totals({}) == {}
    assert anbieter_breakdown_from_totals(None) == {}


# ----- ladekarte_accrued_cost / ladekarten_summary: Ladekarten-Grundgebuehren
# (inkl. Gebuehrenstufen, z.B. reduzierter Einfuehrungspreis) -----------------

def test_ladekarte_accrued_cost_durchgerechnetes_beispiel():
    # 30 Tage aktiv (inklusive Start- und Endtag) bei einer Monatslaenge
    # von genau 30 Tagen -- exakt eine Monatsgebuehr.
    kosten = ladekarte_accrued_cost(
        "2026-01-01", None, [{"ab_datum": "2026-01-01", "gebuehr": 9.90}], heute="2026-01-30",
        avg_days_per_month=30.0,
    )
    assert kosten == 9.90


def test_ladekarte_accrued_cost_vor_vertragsbeginn_liefert_null():
    kosten = ladekarte_accrued_cost(
        "2026-02-01", None, [{"ab_datum": "2026-02-01", "gebuehr": 9.90}],
        heute="2026-01-15", avg_days_per_month=30.0,
    )
    assert kosten == 0.0


def test_ladekarte_accrued_cost_gekuendigt_zaehlt_nur_bis_enddatum():
    # Karte zum 2026-01-15 gekuendigt -- Tage danach (bis "heute") zaehlen
    # nicht mehr, auch wenn heute viel spaeter liegt.
    kosten = ladekarte_accrued_cost(
        "2026-01-01", "2026-01-15", [{"ab_datum": "2026-01-01", "gebuehr": 30.0}],
        heute="2026-06-01", avg_days_per_month=30.0,
    )
    # (15 - 1) Tage + 1 = 15 aktive Tage von 30 Tagen Monatslaenge.
    assert kosten == 15.0


def test_ladekarte_accrued_cost_enddatum_vor_startdatum_liefert_null():
    kosten = ladekarte_accrued_cost(
        "2026-02-01", "2026-01-01", [{"ab_datum": "2026-02-01", "gebuehr": 9.90}], heute="2026-03-01",
    )
    assert kosten == 0.0


def test_ladekarte_accrued_cost_nicht_parsbares_datum_liefert_null_statt_exception():
    gebuehren = [{"ab_datum": "2026-01-01", "gebuehr": 9.90}]
    assert ladekarte_accrued_cost(None, None, gebuehren, heute="2026-01-01") == 0.0
    assert ladekarte_accrued_cost("keinDatum", None, gebuehren, heute="2026-01-01") == 0.0
    assert ladekarte_accrued_cost("2026-01-01", "keinDatum", gebuehren, heute="2026-01-15") == 0.0


def test_ladekarte_accrued_cost_ohne_gebuehren_liefert_null():
    assert ladekarte_accrued_cost("2026-01-01", None, [], heute="2026-01-15") == 0.0
    assert ladekarte_accrued_cost("2026-01-01", None, None, heute="2026-01-15") == 0.0


def test_ladekarte_accrued_cost_reduzierter_einfuehrungspreis_dann_regulaerer_preis():
    # Feldfall: 2,90 EUR/Monat fuer die ersten 30 Tage, danach 5,90 EUR/Monat.
    # Stufen absichtlich NICHT sortiert eingegeben -- Reihenfolge ist egal.
    gebuehren = [
        {"ab_datum": "2026-02-01", "gebuehr": 5.90},
        {"ab_datum": "2026-01-01", "gebuehr": 2.90},
    ]
    # Genau am Stufenwechsel (60 Tage: 31 Tage zu 2.90, 29 Tage zu 5.90).
    kosten = ladekarte_accrued_cost(
        "2026-01-01", None, gebuehren, heute="2026-03-01", avg_days_per_month=30.0,
    )
    erwartet = round(2.90 * 31 / 30.0 + 5.90 * 29 / 30.0, 2)
    assert kosten == erwartet
    # Vor dem Stufenwechsel: nur der Einfuehrungspreis zaehlt.
    kosten_vorher = ladekarte_accrued_cost(
        "2026-01-01", None, gebuehren, heute="2026-01-20", avg_days_per_month=30.0,
    )
    assert kosten_vorher == round(2.90 * 20 / 30.0, 2)


def test_ladekarte_accrued_cost_tage_vor_erster_stufe_zaehlen_nicht():
    # start_datum liegt vor der fruehesten Gebuehrenstufe -- die Tage
    # dazwischen haben keine bekannte Gebuehr, zaehlen mit 0 statt geraten.
    gebuehren = [{"ab_datum": "2026-01-11", "gebuehr": 10.0}]
    kosten = ladekarte_accrued_cost(
        "2026-01-01", None, gebuehren, heute="2026-01-20", avg_days_per_month=30.0,
    )
    # Nur 2026-01-11 bis 2026-01-20 = 10 Tage zaehlen.
    assert kosten == round(10.0 * 10 / 30.0, 2)


def test_ladekarte_accrued_cost_kaputte_einzelstufe_wird_uebersprungen():
    gebuehren = [
        {"ab_datum": "nixdatum", "gebuehr": 999.0},
        {"ab_datum": "2026-01-01", "gebuehr": 10.0},
    ]
    kosten = ladekarte_accrued_cost(
        "2026-01-01", None, gebuehren, heute="2026-01-10", avg_days_per_month=30.0,
    )
    assert kosten == round(10.0 * 10 / 30.0, 2)


def test_ladekarte_current_fee_waehlt_die_zeitlich_juengste_gueltige_stufe():
    gebuehren = [
        {"ab_datum": "2026-01-01", "gebuehr": 2.90},
        {"ab_datum": "2026-02-01", "gebuehr": 5.90},
    ]
    assert ladekarte_current_fee(gebuehren, heute="2026-01-15") == 2.90
    assert ladekarte_current_fee(gebuehren, heute="2026-02-15") == 5.90


def test_ladekarte_current_fee_vor_erster_stufe_liefert_die_fruehste():
    gebuehren = [{"ab_datum": "2026-02-01", "gebuehr": 5.90}]
    assert ladekarte_current_fee(gebuehren, heute="2026-01-01") == 5.90


def test_ladekarte_current_fee_ohne_gebuehren_liefert_none():
    assert ladekarte_current_fee([], heute="2026-01-01") is None
    assert ladekarte_current_fee(None, heute="2026-01-01") is None


def test_ladekarten_summary_leere_liste_liefert_leeres_dict():
    assert ladekarten_summary([], heute="2026-01-01") == {}


def test_ladekarten_summary_mehrere_karten_summieren_sich():
    karten = [
        {"id": 1, "name": "Karte A", "gebuehren": [{"ab_datum": "2026-01-01", "gebuehr": 30.0}],
         "start_datum": "2026-01-01", "end_datum": None},
        {"id": 2, "name": "Karte B", "gebuehren": [{"ab_datum": "2026-01-01", "gebuehr": 15.0}],
         "start_datum": "2026-01-01", "end_datum": None},
    ]
    result = ladekarten_summary(karten, heute="2026-01-30", avg_days_per_month=30.0)
    assert result["gesamt"] == 45.0
    assert result["karten"][0]["kosten"] == 30.0
    assert result["karten"][1]["kosten"] == 15.0
    assert result["karten"][0]["aktuelle_gebuehr"] == 30.0
    # Eingabefelder bleiben erhalten (Panel braucht Name/Gebuehr/Daten
    # weiterhin, nicht nur die berechneten Kosten).
    assert result["karten"][0]["name"] == "Karte A"


def test_ladekarten_summary_karte_mit_kaputtem_datum_bricht_nicht_alles_ab():
    karten = [
        {"id": 1, "name": "Kaputt", "gebuehren": [{"ab_datum": "2026-01-01", "gebuehr": 30.0}],
         "start_datum": "nixdaten", "end_datum": None},
        {"id": 2, "name": "Gut", "gebuehren": [{"ab_datum": "2026-01-01", "gebuehr": 15.0}],
         "start_datum": "2026-01-01", "end_datum": None},
    ]
    result = ladekarten_summary(karten, heute="2026-01-30", avg_days_per_month=30.0)
    assert result["karten"][0]["kosten"] == 0.0
    assert result["karten"][1]["kosten"] == 15.0
    assert result["gesamt"] == 15.0


def test_ladekarten_summary_alte_karte_ohne_gebuehren_feld_faellt_auf_monatliche_gebuehr_zurueck():
    # Ruecklauf-Kompatibilitaet: Karten aus der Zeit vor Gebuehrenstufen
    # (bis v0.67.0) haben nur "monatliche_gebuehr", kein "gebuehren".
    karten = [{"id": 1, "name": "Alt", "monatliche_gebuehr": 30.0, "start_datum": "2026-01-01", "end_datum": None}]
    result = ladekarten_summary(karten, heute="2026-01-30", avg_days_per_month=30.0)
    assert result["karten"][0]["kosten"] == 30.0
    assert result["karten"][0]["aktuelle_gebuehr"] == 30.0
    assert result["karten"][0]["gebuehren"] == [{"ab_datum": "2026-01-01", "gebuehr": 30.0}]


# ----- ac_dc_breakdown: Fremdladungen nach AC/DC (aus Durchschnittsleistung) --

def test_ac_dc_breakdown_klassifiziert_nach_durchschnittsleistung():
    history = [
        # 10 kWh in 60 min = 10 kW -- AC.
        {"kwh": 10.0, "kosten": 5.0, "dauer_min": 60.0},
        # 30 kWh in 20 min = 90 kW -- DC.
        {"kwh": 30.0, "kosten": 15.0, "dauer_min": 20.0},
    ]
    result = ac_dc_breakdown(history)
    assert result["ac"]["kwh"] == 10.0
    assert result["ac"]["anzahl"] == 1
    assert result["dc"]["kwh"] == 30.0
    assert result["dc"]["anzahl"] == 1
    assert result["ac"]["kwh_anteil_pct"] == 25.0
    assert result["dc"]["kwh_anteil_pct"] == 75.0
    assert result["ac"]["preis_je_kwh"] == 0.5
    assert result["dc"]["preis_je_kwh"] == 0.5


def test_ac_dc_breakdown_grenzfall_genau_auf_schwelle_bleibt_ac():
    # Exakt ac_max_kw gilt noch als AC (siehe Docstring: "ueber ac_max_kw"
    # ist DC, nicht "ab").
    history = [{"kwh": 22.0, "kosten": 10.0, "dauer_min": 60.0}]
    result = ac_dc_breakdown(history, ac_max_kw=22.0)
    assert "ac" in result
    assert "dc" not in result


def test_ac_dc_breakdown_ignoriert_eintraege_ohne_ladedauer():
    # Rein manuell ohne Endzeit erfasst (siehe async_log_charge()) -- kann
    # nicht eingeordnet werden, wird ausgelassen statt geraten.
    history = [
        {"kwh": 10.0, "kosten": 5.0},
        {"kwh": 30.0, "kosten": 15.0, "dauer_min": 20.0},
    ]
    result = ac_dc_breakdown(history)
    assert result["dc"]["anzahl"] == 1
    assert sum(b["anzahl"] for b in result.values()) == 1


def test_ac_dc_breakdown_leere_historie_liefert_leeres_dict():
    assert ac_dc_breakdown([]) == {}
    assert ac_dc_breakdown(None) == {}


def test_ac_dc_bucket_key_klassifiziert_wie_ac_dc_breakdown():
    assert ac_dc_bucket_key({"kwh": 10.0, "dauer_min": 60.0}) == "ac"
    assert ac_dc_bucket_key({"kwh": 30.0, "dauer_min": 20.0}) == "dc"
    assert ac_dc_bucket_key({"kwh": 10.0}) is None
    assert ac_dc_bucket_key({}) is None


# ----- apply_ac_dc_delta()/ac_dc_breakdown_from_totals(): Baseline-Variante
# von ac_dc_breakdown() (siehe Fahrtenbuch/History-Archivierung).

def test_apply_ac_dc_delta_addiert_und_ergebnis_entspricht_voller_liste():
    history = [
        {"kwh": 10.0, "kosten": 5.0, "dauer_min": 60.0},
        {"kwh": 30.0, "kosten": 15.0, "dauer_min": 20.0},
    ]
    totals = {}
    for rec in history:
        totals = apply_ac_dc_delta(totals, rec, 1)
    assert ac_dc_breakdown_from_totals(totals) == ac_dc_breakdown(history)


def test_apply_ac_dc_delta_entfernen_macht_hinzufuegen_rueckgaengig():
    rec = {"kwh": 10.0, "kosten": 5.0, "dauer_min": 60.0}
    totals = apply_ac_dc_delta({}, rec, 1)
    totals = apply_ac_dc_delta(totals, rec, -1)
    assert totals == {}


def test_apply_ac_dc_delta_reklassifizierung_bei_bearbeiteter_dauer():
    # Bearbeiten kann die Klassifizierung aendern (siehe async_edit_charge()):
    # alten Stand entfernen, neuen Stand hinzufuegen -- wie beim Delta-Muster
    # bei "totals" fuer async_edit_trip()/async_edit_charge().
    old_rec = {"kwh": 10.0, "kosten": 5.0, "dauer_min": 60.0}  # AC
    new_rec = {"kwh": 10.0, "kosten": 5.0, "dauer_min": 5.0}   # DC (120 kW)
    totals = apply_ac_dc_delta({}, old_rec, 1)
    totals = apply_ac_dc_delta(totals, old_rec, -1)
    totals = apply_ac_dc_delta(totals, new_rec, 1)
    result = ac_dc_breakdown_from_totals(totals)
    assert "ac" not in result
    assert result["dc"]["anzahl"] == 1


def test_apply_ac_dc_delta_ohne_einordenbare_daten_aendert_nichts():
    totals = apply_ac_dc_delta({}, {"kwh": 10.0}, 1)
    assert totals == {}


def test_ac_dc_breakdown_from_totals_leer_liefert_leeres_dict():
    assert ac_dc_breakdown_from_totals({}) == {}
    assert ac_dc_breakdown_from_totals(None) == {}


# ----- leasing_status ---------------------------------------------------------
# Gemeinsame Vertragsbasis fuer die meisten Tests: 2026-01-01 bis 2027-01-01
# (365 Tage), heute = 2026-04-11 (100 vergangene, 265 verbleibende Tage).

_L_START = "2026-01-01"
_L_END = "2027-01-01"  # 365 Tage Vertragslaufzeit
_L_HEUTE = "2026-04-11"  # Tag 100


def test_leasing_status_im_budget():
    result = leasing_status(
        aktueller_km=14000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute=_L_HEUTE,
        preis_minder_km=0.05,
    )
    assert result["gefahrene_vertrags_km"] == 4000.0
    assert result["vertrag_tage"] == 365
    assert result["vergangene_tage"] == 100
    assert result["verbleibende_tage"] == 265
    assert result["soll_km_bis_heute"] == 5479.5
    assert result["km_vor_ruecklauf"] == -1479.5
    assert result["status"] == "im_budget"
    assert result["linear"]["tempo_km_pro_tag"] == 40.0
    assert result["linear"]["erwartete_end_km"] == 14600.0
    assert result["linear"]["erwartete_mehr_bzw_minder_km"] == -5400.0
    assert result["linear"]["gutschrift_eur"] == 270.0  # 5400 * 0.05
    assert "mehrkosten_eur" not in result["linear"]
    assert result["verbleibendes_tagesbudget_km"] == 60.4
    assert "rollierend" not in result


def test_leasing_status_spiegelt_vertragseingaben_fuer_die_anzeige():
    result = leasing_status(
        aktueller_km=14000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute=_L_HEUTE,
        preis_mehr_km=0.30, preis_minder_km=0.05,
    )
    assert result["vertrag_start_km"] == 10000.0
    assert result["vertrag_start_datum"] == _L_START
    assert result["vertrag_end_datum"] == _L_END
    assert result["vertrag_inkl_km"] == 20000.0
    assert result["preis_mehr_km"] == 0.30
    assert result["preis_minder_km"] == 0.05
    assert result["resterlaubte_km"] == 16000.0  # 20000 - 4000 gefahrene km


def test_leasing_status_ohne_preise_keine_preis_felder():
    result = leasing_status(
        aktueller_km=14000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute=_L_HEUTE,
    )
    assert "preis_mehr_km" not in result
    assert "preis_minder_km" not in result


def test_leasing_status_knapp():
    result = leasing_status(
        aktueller_km=15000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute=_L_HEUTE,
    )
    assert result["linear"]["erwartete_end_km"] == 18250.0  # 91.25 % von 20000
    assert result["status"] == "knapp"


def test_leasing_status_ueber():
    result = leasing_status(
        aktueller_km=17000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute=_L_HEUTE,
        preis_mehr_km=0.20,
    )
    assert result["linear"]["erwartete_end_km"] == 25550.0  # 127.75 % von 20000
    assert result["status"] == "ueber"
    assert result["linear"]["erwartete_mehr_bzw_minder_km"] == 5550.0
    assert result["linear"]["mehrkosten_eur"] == 1110.0  # 5550 * 0.20
    assert "gutschrift_eur" not in result["linear"]


def test_leasing_status_exakt_auf_soll():
    # inkl_gesamt_km so gewaehlt, dass die Soll-Linie an Tag 100 exakt 10000
    # ergibt (36500 / 365 Tage = 100 km/Tag, keine Rundungsreste).
    result = leasing_status(
        aktueller_km=20000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=36500.0, heute=_L_HEUTE,
    )
    assert result["gefahrene_vertrags_km"] == 10000.0
    assert result["soll_km_bis_heute"] == 10000.0
    assert result["km_vor_ruecklauf"] == 0.0


def test_leasing_status_linear_vs_rollierend_divergierend():
    result = leasing_status(
        aktueller_km=15000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=36500.0, heute=_L_HEUTE,
        rollierendes_tempo_km_pro_tag=150.0,
    )
    # linear (50 km/Tag seit Vertragsstart) liegt klar im Budget...
    assert result["linear"]["erwartete_end_km"] == 18250.0
    assert result["linear"]["erwartete_mehr_bzw_minder_km"] < 0
    # ...waehrend das zuletzt gefahrene (rollierende) Tempo klar drueber landet.
    assert result["rollierend"]["tempo_km_pro_tag"] == 150.0
    assert result["rollierend"]["erwartete_end_km"] == 44750.0
    assert result["rollierend"]["erwartete_mehr_bzw_minder_km"] > 0
    # status haengt NUR an der linearen Hochrechnung (siehe Docstring).
    assert result["status"] == "im_budget"


def test_leasing_status_minderkilometer_ohne_preis_keine_gutschrift():
    result = leasing_status(
        aktueller_km=14000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute=_L_HEUTE,
    )
    assert result["linear"]["erwartete_mehr_bzw_minder_km"] < 0
    assert "gutschrift_eur" not in result["linear"]
    assert "mehrkosten_eur" not in result["linear"]


def test_leasing_status_vertrag_noch_nicht_gestartet():
    result = leasing_status(
        aktueller_km=10000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute="2025-12-01",
    )
    assert result["vergangene_tage"] == 0
    assert result["verbleibende_tage"] == 365
    assert result["soll_km_bis_heute"] == 0.0
    assert result["gefahrene_vertrags_km"] == 0.0
    assert result["km_vor_ruecklauf"] == 0.0
    assert "linear" not in result
    assert result["status"] == "im_budget"


def test_leasing_status_vertrag_schon_beendet():
    result = leasing_status(
        aktueller_km=25000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute="2027-06-01",
    )
    assert result["vergangene_tage"] == 365
    assert result["verbleibende_tage"] == 0
    assert result["soll_km_bis_heute"] == 20000.0
    assert "verbleibendes_tagesbudget_km" not in result
    # Hochrechnung an Tag "vertrag_tage" mit 0 Resttagen == der Ist-Stand.
    assert result["linear"]["erwartete_end_km"] == 15000.0


def test_leasing_status_verbleibende_tage_null_am_stichtag():
    result = leasing_status(
        aktueller_km=18000.0, vertrag_start_km=10000.0,
        vertrag_start_datum=_L_START, vertrag_end_datum=_L_END,
        inkl_gesamt_km=20000.0, heute=_L_END,
    )
    assert result["verbleibende_tage"] == 0
    assert "verbleibendes_tagesbudget_km" not in result


@pytest.mark.parametrize("kwargs", [
    dict(aktueller_km=None, vertrag_start_km=10000.0, vertrag_start_datum=_L_START,
         vertrag_end_datum=_L_END, inkl_gesamt_km=20000.0, heute=_L_HEUTE),
    dict(aktueller_km=14000.0, vertrag_start_km=None, vertrag_start_datum=_L_START,
         vertrag_end_datum=_L_END, inkl_gesamt_km=20000.0, heute=_L_HEUTE),
    dict(aktueller_km=14000.0, vertrag_start_km=10000.0, vertrag_start_datum=None,
         vertrag_end_datum=_L_END, inkl_gesamt_km=20000.0, heute=_L_HEUTE),
    dict(aktueller_km=14000.0, vertrag_start_km=10000.0, vertrag_start_datum=_L_START,
         vertrag_end_datum=None, inkl_gesamt_km=20000.0, heute=_L_HEUTE),
    dict(aktueller_km=14000.0, vertrag_start_km=10000.0, vertrag_start_datum=_L_START,
         vertrag_end_datum=_L_END, inkl_gesamt_km=None, heute=_L_HEUTE),
    dict(aktueller_km=14000.0, vertrag_start_km=10000.0, vertrag_start_datum=_L_START,
         vertrag_end_datum=_L_END, inkl_gesamt_km=0.0, heute=_L_HEUTE),
    dict(aktueller_km=14000.0, vertrag_start_km=10000.0, vertrag_start_datum="nicht-iso",
         vertrag_end_datum=_L_END, inkl_gesamt_km=20000.0, heute=_L_HEUTE),
    dict(aktueller_km=14000.0, vertrag_start_km=10000.0, vertrag_start_datum=_L_END,
         vertrag_end_datum=_L_START, inkl_gesamt_km=20000.0, heute=_L_HEUTE),
])
def test_leasing_status_fehlende_oder_ungueltige_pflichtfelder_liefert_leeres_dict(kwargs):
    assert leasing_status(**kwargs) == {}


# ----- split_by_age(): Grundlage der Fahrtenbuch/History-Archivierung -------
# (siehe coordinator.py::_async_truncate_lifetime_lists()) -----------------

def test_split_by_age_teilt_nach_schwelle():
    records = [{"ts": 100}, {"ts": 50}, {"ts": 200}]
    aktuell, alt = split_by_age(records, "ts", cutoff_ts=100)
    assert aktuell == [{"ts": 100}, {"ts": 200}]
    assert alt == [{"ts": 50}]


def test_split_by_age_behaelt_reihenfolge():
    records = [{"ts": 300}, {"ts": 100}, {"ts": 400}]
    aktuell, _ = split_by_age(records, "ts", cutoff_ts=0)
    assert aktuell == records  # unveraendert, nicht neu sortiert


def test_split_by_age_fehlendes_feld_gilt_als_alt():
    records = [{"ts": 500}, {"andere_spalte": 1}]
    aktuell, alt = split_by_age(records, "ts", cutoff_ts=0)
    assert aktuell == [{"ts": 500}]
    assert alt == [{"andere_spalte": 1}]


def test_split_by_age_leere_liste():
    assert split_by_age([], "ts", cutoff_ts=100) == ([], [])


def test_split_by_age_mutiert_eingabe_nicht():
    records = [{"ts": 100}]
    split_by_age(records, "ts", cutoff_ts=0)
    assert records == [{"ts": 100}]


def test_split_by_age_ist_idempotent():
    records = [{"ts": 100}, {"ts": 50}, {"ts": 200}]
    aktuell, alt = split_by_age(records, "ts", cutoff_ts=100)
    # Erneutes Anwenden auf das "aktuell"-Ergebnis mit demselben (oder
    # einem frueheren) cutoff_ts liefert keine weiteren "alt"-Eintraege.
    aktuell2, alt2 = split_by_age(aktuell, "ts", cutoff_ts=100)
    assert aktuell2 == aktuell
    assert alt2 == []


# ----- Kernanforderung: kumulative Kennzahlen bleiben nach dem Archivieren
# alter Detail-Eintraege UNVERAENDERT -----------------------------------
#
# Simuliert eine mehrjaehrige Historie, baut die Lebenszeit-Baselines
# (siehe coordinator.py::_apply_trip_baselines()/_apply_charge_baselines())
# einmal record-fuer-record auf und zeigt:
#   1. Die Baseline-Funktionen liefern zum Zeitpunkt der vollen Historie
#      EXAKT dieselben Werte wie die alten volle-Liste-Funktionen.
#   2. Nach einem simulierten Kuerzen (split_by_age(), analog
#      _async_truncate_lifetime_lists()) liefern die Baseline-Funktionen
#      WEITERHIN dieselben Werte -- sie lesen die (jetzt kuerzere) Liste
#      gar nicht mehr.
#   3. Zum Vergleich: wuerde man (falsch) die alten volle-Liste-Funktionen
#      auf der gekuerzten Liste weiterlaufen lassen, kaeme ein ANDERES
#      (zu kleines) Ergebnis heraus -- das ist genau die Verfaelschung,
#      die die Baselines verhindern.

_JAHRE_SEKUNDEN = 3 * 365 * 86400  # simulierte Gesamtlaenge: 3 Jahre


def _synthetische_fahrten(anzahl=36):
    # Ueber 3 Jahre verteilt, abwechselnd mit exaktem Verbrauch/nur
    # delta_soc, mit/ohne Temperatur -- ein Querschnitt der echten Felder.
    fahrten = []
    for i in range(anzahl):
        ts = i * (_JAHRE_SEKUNDEN // anzahl)
        rec = {"start_ts": ts, "km": 20.0 + i}
        if i % 2 == 0:
            rec["verbrauch_kwh"] = 3.0 + (i % 5)
            rec["delta_soc"] = -(rec["verbrauch_kwh"] / 45.0 * 100.0)
        else:
            rec["delta_soc"] = -(10.0 + i % 15)
        if i % 3 == 0:
            rec["temp_start"] = -5.0 + (i % 30)
        fahrten.append(rec)
    return fahrten


def _synthetische_history(anzahl=24):
    anbieter_liste = ["EnBW", "Ionity", None, "Aral pulse"]
    history = []
    for i in range(anzahl):
        ts = i * (_JAHRE_SEKUNDEN // anzahl)
        rec = {
            "erfasst_ts": ts,
            "kwh": 10.0 + i,
            "kosten": round((10.0 + i) * 0.45, 2),
            "dauer_min": 20.0 if i % 2 == 0 else 90.0,  # abwechselnd DC/AC
            "delta_soc": 30.0 + (i % 40),
            "anbieter": anbieter_liste[i % len(anbieter_liste)],
        }
        history.append(rec)
    return history


def test_baselines_entsprechen_voller_liste_und_bleiben_nach_kuerzung_unveraendert():
    fahrten = _synthetische_fahrten()
    history = _synthetische_history()
    home_charge_pct_total = 42.0
    usable_kwh = 45.0

    # --- 1. Ausgangswerte ueber die volle Liste (alte Berechnung) ---
    cycles_voll = equivalent_full_cycles(fahrten, history, home_charge_pct_total)
    ac_dc_voll = ac_dc_breakdown(history)
    anbieter_voll = anbieter_breakdown(history)
    temp_voll = consumption_by_temp_bucket(fahrten)

    def _trip_avg_alt(fahrten):
        # Nachbau der ALTEN coordinator._trip_avg_consumption_kwh()-Formel,
        # als unabhaengige Referenz (siehe dortigen Docstring vor der
        # Baseline-Umstellung).
        values = []
        for rec in fahrten:
            v = rec.get("verbrauch_kwh")
            if v is not None:
                values.append(float(v))
                continue
            d = rec.get("delta_soc")
            if d is not None:
                values.append(max(0.0, -d) / 100.0 * usable_kwh)
        return round(sum(values) / len(values), 2) if values else None

    trip_avg_voll = _trip_avg_alt(fahrten)

    # --- 2. Baselines einmal record-fuer-record aus der VOLLEN Historie
    # aufbauen (entspricht _migrate_lifetime_baselines()) ---
    discharge_total = 0.0
    exact_sum, exact_count = 0.0, 0
    deltasoc_sum, deltasoc_count = 0.0, 0
    temp_totals = {}
    for rec in fahrten:
        discharge_total += trip_discharge_pct(rec)
        contribution = trip_consumption_contribution(rec)
        if contribution is not None:
            kind, value = contribution
            if kind == "exact":
                exact_sum += value
                exact_count += 1
            else:
                deltasoc_sum += value
                deltasoc_count += 1
        temp_contribution = temp_bucket_contribution(rec)
        if temp_contribution is not None:
            bucket, pct = temp_contribution
            entry = temp_totals.setdefault(bucket, {"sum_pct": 0.0, "count": 0})
            entry["sum_pct"] += pct
            entry["count"] += 1

    charge_total = 0.0
    ac_dc_totals, anbieter_totals = {}, {}
    for rec in history:
        charge_total += charge_pct_of_history_entry(rec)
        ac_dc_totals = apply_ac_dc_delta(ac_dc_totals, rec, 1)
        anbieter_totals = apply_anbieter_delta(anbieter_totals, rec, 1)

    # --- 3. Baseline-Ergebnisse muessen den Ausgangswerten entsprechen ---
    assert equivalent_full_cycles_from_totals(discharge_total, charge_total, home_charge_pct_total) == cycles_voll
    assert ac_dc_breakdown_from_totals(ac_dc_totals) == ac_dc_voll
    assert anbieter_breakdown_from_totals(anbieter_totals) == anbieter_voll
    assert consumption_by_temp_bucket_from_totals(temp_totals) == temp_voll
    assert trip_avg_consumption_kwh_from_totals(
        exact_sum, exact_count, deltasoc_sum, deltasoc_count, usable_kwh
    ) == trip_avg_voll

    # --- 4. Simuliertes Kuerzen: nur die juengere Haelfte bleibt in der
    # "heissen" Liste, der Rest waere jetzt im Archiv ---
    cutoff = _JAHRE_SEKUNDEN // 2
    fahrten_aktuell, fahrten_alt = split_by_age(fahrten, "start_ts", cutoff)
    history_aktuell, history_alt = split_by_age(history, "erfasst_ts", cutoff)
    assert fahrten_alt and history_alt  # Testaufbau: tatsaechlich etwas gekuerzt

    # --- 5. Baseline-Ergebnisse sind UNVERAENDERT -- sie haengen nicht an
    # der (jetzt kuerzeren) Liste, sondern an den bereits berechneten Summen ---
    assert equivalent_full_cycles_from_totals(discharge_total, charge_total, home_charge_pct_total) == cycles_voll
    assert ac_dc_breakdown_from_totals(ac_dc_totals) == ac_dc_voll
    assert anbieter_breakdown_from_totals(anbieter_totals) == anbieter_voll
    assert consumption_by_temp_bucket_from_totals(temp_totals) == temp_voll
    assert trip_avg_consumption_kwh_from_totals(
        exact_sum, exact_count, deltasoc_sum, deltasoc_count, usable_kwh
    ) == trip_avg_voll

    # --- 6. Gegenprobe: die ALTEN volle-Liste-Funktionen auf der jetzt
    # gekuerzten Liste weiterlaufen zu lassen, waere FALSCH -- sie liefern
    # ein anderes (zu kleines) Ergebnis. Das ist die Verfaelschung, die
    # Aufgabe 2 verhindern soll.
    cycles_gekuerzt = equivalent_full_cycles(fahrten_aktuell, history_aktuell, home_charge_pct_total)
    assert cycles_gekuerzt != cycles_voll
    assert ac_dc_breakdown(history_aktuell) != ac_dc_voll
    assert anbieter_breakdown(history_aktuell) != anbieter_voll


def test_split_by_age_idempotent_auf_bereits_gekuerzter_liste():
    # Zweiter taeglicher Lauf ohne neu hinzugekommene alte Eintraege darf
    # nichts mehr veraendern (siehe _async_truncate_lifetime_lists()).
    fahrten = _synthetische_fahrten()
    cutoff = _JAHRE_SEKUNDEN // 2
    aktuell, _ = split_by_age(fahrten, "start_ts", cutoff)
    aktuell2, alt2 = split_by_age(aktuell, "start_ts", cutoff)
    assert aktuell2 == aktuell
    assert alt2 == []
