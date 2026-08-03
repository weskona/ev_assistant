# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Version](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)

Detects EV charging sessions **away from your home wallbox** ("external charge") from SoC telemetry, lets you log the actual kWh/price from the receipt, and can automatically calibrate the vehicle's charge efficiency from your real home-charging sessions. Manufacturer-independent — works with any HA entity (WiCAN Pro via mqtt integration, evcc/Warp, Stellantis/VW cloud sensors, ...).

**[🇩🇪 Deutsche Version weiter unten](#-deutsch)**

---

## 🇬🇧 English

### How it works

EV Assistant never needs GPS, a specific manufacturer API, or a list of known charging stations. It works purely from two numbers it already gets from your car and your home:

1. **State of charge (SoC)** — the battery percentage, e.g. from a manufacturer cloud sensor or a cheap OBD dongle like WiCAN Pro.
2. **Home-charging signal** — anything that tells you "the car is charging at my own wallbox right now" (e.g. from evcc, a Warp box, or any charger integration).

The core idea is one sentence: **if the battery percentage goes up while the home-charging signal says "no", the car must be charging somewhere else** — a public charger, a hotel, a friend's house, work. That's an **external charge**. Home charging is deliberately ignored by the detector — you already track that through your own wallbox/evcc setup, so EV Assistant only ever bothers you about charges *you'd otherwise lose track of*.

Internally, a small state machine (`engine.py::ChargeDetector`) watches every new SoC reading:

- **Idle** — nothing is happening. It keeps remembering the lowest SoC value seen recently (the "anchor"). Every time the SoC dips back down (or the home-charging signal is on), the anchor resets to that value. This means the anchor always represents "the charge level right before whatever happens next".
- **Start of a session** — as soon as SoC has climbed at least `start_delta` (default **1 %**) above the anchor *while home-charging is off*, an external-charge session begins. Its official start point is the anchor (the last known low point), not the moment the threshold was crossed — so the session correctly includes the very first bit of charging that triggered the detection.
- **Active session** — as SoC keeps climbing, EV Assistant tracks the highest value seen ("peak"). A small `noise` tolerance (default **0.5 %**) absorbs sensor jitter (SoC readings occasionally wobble by a fraction of a percent without anything actually happening) so it doesn't get confused by measurement noise. Keep `start_delta` **above** `noise` — if they're equal (or `start_delta` is lower), ordinary jitter can look like a genuine rise and trigger false detections.
- **End of a session** — whichever of these happens first:
  - the home-charging signal turns on (you've arrived home and plugged in — the away-charge that just happened is now finalized), or
  - SoC drops by more than `drop_ends` (default **1 %**) below the peak (you unplugged and started driving), or
  - `idle_timeout_s` (default **600 s / 10 minutes**) passes with no further SoC increase (charging finished, or the cable/connection dropped).

At the end, EV Assistant has a `soc_start`, a `soc_end`, and needs to turn that into an energy estimate — see the next section for exactly how, with worked numbers.

### Detection walkthrough — a worked example

Say your car has a 45 kWh usable battery and the default 88 % charge efficiency (both configurable in step 1 of setup). You drive away from home with the battery at **32 %** and plug in at a public charger. No vehicle charging-power sensor is configured yet — just SoC and the home-charging signal.

1. Before you left, the last few SoC readings were flat at 32 % with home-charging off (you weren't charging, just driving/parked away from home). The anchor sits at **32 %**.
2. At the charger, the next SoC reading comes in at **35 %**. That's +3 percentage points above the anchor — exactly the `start_delta` threshold — so an external-charge session **starts**, officially from `soc_start = 32 %` (the anchor), at the timestamp of that last 32 % reading.
3. Over the next couple of hours, SoC keeps ticking up: 40 %, 55 %, 68 %, 74 %. Each new high becomes the tracked peak.
4. You unplug at **74 %** and drive home. Ten minutes pass with the SoC entity reporting no further increase (it's not charging anymore) — the `idle_timeout_s` fires and the session **ends**.
5. Delta = 74 % − 32 % = **42 percentage points**. Without a vehicle charging-power sensor, EV Assistant falls back to the SoC-only estimate:
   - Battery-side energy: `42 % of 45 kWh = 18.9 kWh`
   - AC-side (billed) estimate, accounting for charging losses: `18.9 kWh ÷ 0.88 = 21.48 kWh` — the notification rounds this to **≈ 21.5 kWh**.
6. EV Assistant now:
   - stores this as the **pending** charge,
   - fires the `ev_assistant_pending` event (with `config_entry_id` so you can tell which car, if you have more than one),
   - sends a notification: *"+42% (32 → 74%), ~21.5 kWh estimated. Enter kWh and price."* (shown in German instead if your HA UI language is set to German)
   - turns on `binary_sensor ... External Charge Detection Open` and sets `sensor ... External Charge Estimate` to 21.48 kWh.
7. A few days later the receipt arrives: **21.4 kWh** actually billed at **0.59 EUR/kWh** = **12.63 EUR**. You call `ev_assistant.log_charge` (or use the optional card) with these real numbers.
8. EV Assistant writes a history entry containing **both** figures — the estimate (21.48 kWh, source `soc`) and the real one (21.4 kWh, 0.59 EUR/kWh, 12.63 EUR) — updates the running totals, clears the pending charge, and dismisses the notification.

The SoC-only estimate (21.48 kWh) was almost exactly right here (21.4 kWh actual) — but that's partly luck. Real invoices vary with charger efficiency, cable losses, and battery temperature, which is exactly why the receipt value always wins for the actual cost bookkeeping.

### Energy estimation methods

The estimate shown while a charge is pending, and stored as `schaetzung_kwh`/`quelle` in history, comes from one of three methods, automatically chosen based on what you've configured (visible per session as `energy_source` / `quelle`: `soc`, `power_ac`, or `power_dc`):

| Source | When it's used | How it's calculated |
|---|---|---|
| `soc` | No vehicle charging-power sensor configured (or no data during this session) | `battery_kwh = soc_delta% × usable_kWh`; `ac_kwh = battery_kwh ÷ charge_efficiency` |
| `power_ac` | Vehicle charging-power sensor configured with **"power is AC-side"** enabled (the default) | `ac_kwh` = the power readings integrated over time (trapezoidal rule) — this is already the billed-side energy, no efficiency math needed; `battery_kwh = ac_kwh × charge_efficiency` (informational only) |
| `power_dc` | Vehicle charging-power sensor configured with **"power is AC-side"** disabled (sensor reports the battery/DC side) | `battery_kwh` = the power readings integrated over time; `ac_kwh = battery_kwh ÷ charge_efficiency` |

A vehicle charging-power sensor (when available) is generally more accurate than the SoC-only method, because it reacts to the *actual* charging curve (which typically tapers off well before 100 %) instead of assuming a linear relationship between percentage and kWh. It's read from the vehicle's own telemetry (not your home wallbox) so it also reports data during an external charge away from home, where your wallbox naturally has no signal at all.

### Installation

**Via HACS**
1. HACS → Integrations → ⋮ → **Custom repositories**
2. URL: `https://github.com/weskona/ev_assistant` — Category: **Integration**
3. Install EV Assistant, restart Home Assistant

**Manual**
1. Copy `custom_components/ev_assistant/` into `config/custom_components/`
2. Restart Home Assistant

### Configuration

Settings → Devices & Services → **Add integration** → "EV Assistant". Setup is a 7-step flow (also used identically when editing via **Configure**):

1. **Vehicle** — Manufacturer + model (required, e.g. "Peugeot" / "e-2008" — together they become the HA device name), first registration date (optional, display only), odometer entity (optional, filtered to `sensor` + `device_class: distance`), **SoC entity** (required, filtered to `sensor` + `device_class: battery` — the vehicle's battery percentage from your manufacturer integration, OBD dongle, etc.), usable battery capacity in kWh (required — the *net* value your car can actually use, not the often-larger gross/factory figure some manufacturers advertise; this directly determines how many kWh one percentage point of SoC represents, so getting it wrong throws off every energy estimate), charge efficiency (optional starting value only — replaced automatically once enough real home charges have been measured, see calibration below).
2. **evcc & Wallbox** — all evcc site and loadpoint entities (PV power, grid power, home battery, tariffs, statistics, charge power, charge status, mode, session energy, etc.) are **automatically discovered** from the installed evcc integration — no manual entity selection needed. Only two optional fields remain: the vehicle name in evcc (filters the home-charging history to this vehicle when multiple EVs share one evcc instance) and the **wallbox charge power entity** (filtered to `sensor` + `device_class: power` — used as the yes/no signal "currently charging at home"; a value **above 0.1 kW counts as "charging"**). Without the wallbox charge power entity every SoC increase is falsely detected as an external charge. Requires the `evcc_intg` integration to be installed.
3. **Charging power** (optional) — two different sources for two different purposes. Charging power is a momentary power reading in W/kW, typically from vehicle telemetry rather than your wallbox (so it still reports data during an external charge, where the wallbox is idle); it improves the energy estimate of an external charge beyond plain SoC-delta (see "Energy estimation methods" above). The **wallbox energy meter**, on the other hand, is a cumulative kWh counter of your own wallbox (never momentary, only relevant while charging at home) — it's used for automatic efficiency calibration *and* for the home-charging cost tracked in step 7.
4. **Output** (optional) — a persistent notification in Home Assistant's own notification panel always appears automatically for a detected charge, regardless of this step. The `notify.*` service additionally sends a push notification (e.g. to your phone).
5. **Detection fine-tuning** — thresholds of the underlying state machine described above (`start_delta`, `noise`, `idle_timeout_s`, `drop_ends`). A session starts once SoC rises by `start_delta` above its last resting value; it ends either when SoC drops by more than `drop_ends` below the tracked peak, or when `idle_timeout_s` passes with no new peak (e.g. battery full). `noise` tolerates ordinary sensor jitter while tracking the peak and must always be **smaller** than `start_delta`, or jitter alone could trigger a false detection. Defaults work for most vehicles; raise them for a car whose SoC only updates coarsely/infrequently (e.g. some cloud APIs).
6. **Trip log** (optional) — thresholds of the trip detector (`trip_min_km`, `trip_idle_timeout_s`) described in "Trip log" below. Defaults work for most odometer sensors. Also an optional location-suggestion source (`gps_entity`, a `person`/`device_tracker`).
7. **Cost comparison** (optional) — see "Cost comparison vs. a combustion car" below. Fuel price priority: Tankerkönig auto-detection (pick a fuel type) > fuel-price entity > fixed value — configure only one source.

### Sources: manufacturer-independent

The SoC signal is fed from any **HA entity** — works with any manufacturer or dongle that exposes an SoC sensor in HA.

- **WiCAN Pro:** set up the HA `mqtt` integration and use the MQTT SoC sensor it exposes.
- **Stellantis / VW / ...:** SoC entity = `sensor.<car>_battery`. Cloud SoC is often coarse/infrequent — raise `start_delta` and `idle_timeout_s` accordingly; the power-based path is unavailable without real power data (falls back to SoC × efficiency).

### Automatic charge-efficiency calibration

Instead of a fixed manual efficiency value, EV Assistant can learn the real AC→battery efficiency from your own home-charging sessions — no external charge is involved in this at all, it's purely about how efficiently *your car* converts grid power into stored battery energy while charging at home.

**How it works:** configure a **wallbox energy meter** in step 3 — a cumulative kWh counter that only ever counts up (like a normal utility meter), not a "session energy" value that resets. Every time the home-charging signal switches on, EV Assistant remembers the current SoC and the current wallbox meter reading. When home-charging switches off again, it compares the SoC gained against the wallbox energy consumed for that same session, and calculates the efficiency:

`efficiency = (soc_gained% × usable_kWh) ÷ wallbox_energy_delta_kWh`

**Worked example:** your wallbox meter reads **100.0 kWh** when a home charge starts, and **120.2 kWh** when it ends — so **20.2 kWh** of AC energy was drawn from the grid. Over the same session, SoC went from **30 %** to **68 %**, a gain of 38 percentage points. With a 45 kWh usable battery, that's `38% × 45 kWh = 17.1 kWh` that actually went into the battery. The measured efficiency for this one session is `17.1 ÷ 20.2 ≈ 0.847` (84.7 %).

A single session isn't trusted blindly — implausible samples are discarded automatically (session too short: less than 5 percentage points of SoC gain; missing data; or a result outside the 50–100 % plausible range, which usually means a meter reset or a missed reading happened). Once **3 valid sessions** have been collected, EV Assistant averages the last 10 samples and **automatically starts using that measured value** for every calculation from then on — live, without a restart. If your car's real efficiency is, say, 0.847, 0.86, and 0.855 across three sessions, the new value in use becomes their average, **0.854 (85.4 %)** — replacing whichever value you originally typed in during setup.

The manual value from step 1 remains the fallback the whole time until enough sessions exist. See sensor `... Charge Efficiency (Measured)` below for the live status.

### Cost comparison vs. a combustion car

All fields in step 6 are optional — configure as many or as few as you like; the sensors below simply show `unknown` until their required inputs are available.

**Distance driven:** the odometer entity from step 1 is read once at first startup and remembered as a reference point. "km driven" is always `current odometer − that reference value` — so the comparison covers everything from when you configured EV Assistant onward, not the car's full lifetime mileage.

**Home-charging cost:** total home-charged kWh and its price are each resolved with their own priority order. kWh: evcc's own vehicle charging-session statistic (most precise, but requires evcc's "extended vehicle data" and is therefore usually unavailable) beats evcc's site-wide "total charged energy" statistic (`sensor.evcc_stat_total_charged_kwh`, auto-discovered from the evcc integration) beats the plain **wallbox energy meter delta** from step 3 (first-seen value as reference, current value minus that reference). The site-wide evcc statistic is only used when a wallbox energy meter is *also* configured for this vehicle — that statistic isn't per-vehicle, so without this guard a second EV Assistant instance for another car sharing the same evcc site would wrongly inherit the first car's home-charging total. Price: evcc's site-wide average-price statistic (`sensor.evcc_stat_total_avg_price`, same per-vehicle guard) beats a manually linked **live entity** (`home_price_entity`, e.g. a dynamic-tariff sensor, kWh-weighted — see below) beats the plain **fixed value** (`home_price_kwh`). kWh × price gives the estimated home-charging spend. Without a wallbox meter configured for this vehicle, home-charging cost is simply treated as 0 — the comparison still works using only the (always-tracked) external-charging costs.

**Combustion reference:** `(km driven ÷ 100) × verbrenner_l_100km × verbrenner_price_per_liter` — a straightforward "what would this distance have cost in fuel" estimate for the comparison vehicle you describe. Three fuel-price sources are available, in this priority order: **Tankerkönig auto-detection** (pick a fuel type — `super`, `super_e10`, or `diesel` — and EV Assistant automatically finds every station you've configured in the core Tankerkönig integration and always uses the cheapest currently *open* one) beats a manually linked **live entity** (`verbrenner_price_entity`, e.g. any other fuel-price sensor), which beats the plain **fixed value** (`verbrenner_price_per_liter`). Only configure one — whichever is set takes over. Because a live/auto-detected price fluctuates, EV Assistant doesn't just apply its current reading to the whole distance driven: it keeps a **time-weighted average** of every price seen since setup (each reading weighted by how long it was actually in effect), so a week at 1.70 EUR/L followed by a day at 1.90 EUR/L doesn't get miscounted as if 1.90 EUR/L applied the whole time. Time-weighting fits fuel because driving doesn't systematically correlate with fuel-price swings. The home electricity live-entity price is different: home charging (e.g. via evcc) is often deliberately scheduled into cheap-price windows, so EV Assistant instead keeps a **kWh-weighted average** — each price weighted by how much was actually charged while it was in effect, via the wallbox energy meter — so a price spike with zero charging during it contributes no weight at all, rather than dragging the average up. If a live source (Tankerkönig or entity) ever goes `unavailable` — including across restarts — its **last known value keeps being used** rather than the comparison silently dropping out, and a **persistent notification** appears in Home Assistant for as long as Tankerkönig can't produce a single valid reading (e.g. the fuel type was never found, or the integration was removed); it's dismissed automatically once a valid price returns. The `... Fuel Price (Selected)` sensor shows the current raw price in effect together with a `quelle` attribute (`tankerkoenig`/`entity`/`fixed`) telling you which of the three sources is active; the `... Savings vs. Combustion Car` sensor's `kraftstoffpreis_live` and `heimstrompreis_live` attributes tell you whether a live source (rather than the fixed value) is currently providing fuel/home-electricity prices.

**Worked example:** you've driven **1,000 km** since setting up EV Assistant. Your wallbox meter shows **150 kWh** charged at home, at a configured price of **0.30 EUR/kWh** → **45.00 EUR** home-charging cost. Your tracked external charges total **50.00 EUR** so far. Total EV energy cost: `45.00 + 50.00 = 95.00 EUR`. Your reference combustion car uses 6.5 L/100km at a fuel price of 1.75 EUR/L: `(1,000 ÷ 100) × 6.5 × 1.75 = 113.75 EUR`. Your estimated savings: `113.75 − 95.00 = 18.75 EUR` over those 1,000 km.

### Sensors in detail

The HA device is named after the vehicle (`{Manufacturer} {Model}`), so entity names below appear as `{Device} {Entity}`, e.g. "Peugeot e-2008 External Charge Count".

| Sensor | Meaning |
|---|---|
| `binary_sensor ... External Charge Detection Open` | **On** while at least one detected external charge is waiting for you to confirm the real kWh/price. More than one can be open at once — attributes: `anzahl_offen` (count), `offene_ladungen` (the full list, each with start/end time, SoC start/end, estimate, source), plus the oldest one's fields flattened directly at the top level for convenience. |
| `sensor ... External Charge Estimate` | The estimated kWh of the currently pending charge (see "Energy estimation methods"). `unknown` when nothing is pending. |
| `sensor ... External Charge kWh (Last)` | The `kwh` value you entered for the most recently confirmed external charge (i.e. from the receipt, not the estimate). |
| `sensor ... External Charge Cost (Last)` | `kwh × price_kwh` for that same most recent confirmed charge. |
| `sensor ... External Charge Price (Last)` | The price per kWh you entered for the most recent confirmed charge. |
| `sensor ... External Charge Duration (Last)` | How long the detected charging session lasted (from detection start to end), in minutes. `unknown` for older history entries confirmed before this sensor existed, or for a manually logged charge with no underlying detection. |
| `sensor ... External Charge kWh (Total)` | Running total of all confirmed external-charge kWh since setup (or since you last reset it — it's a `total_increasing` sensor, so the HA Energy dashboard can use it directly). |
| `sensor ... External Charge Cost (Total)` | Running total of all confirmed external-charge costs. |
| `sensor ... External Charge Count` | How many external charges have been confirmed in total. |
| `sensor ... Charge Efficiency (Measured)` (diagnostic) | The live-calibrated efficiency from **home** charging sessions (see above) — **not** related to external charges at all. Shown as a percentage. Attributes: `anzahl_sessions` (samples collected so far), `benoetigte_sessions` (3, the minimum needed before it takes over), `einzelwerte_prozent` (each individual sample), `wird_verwendet` (whether the measured value is currently being used instead of the manual one), `manueller_wert_prozent` (the configured fallback value). |
| `sensor ... Odometer` (diagnostic) | Mirrors the odometer entity configured in step 1, if any, grouped onto the EV Assistant device. Pure display passthrough. |
| `sensor ... First Registration` (diagnostic) | The first-registration date entered in step 1, exposed as a proper `date`-typed sensor. |
| `sensor ... Home Charging kWh (Total)` | Total home-charged kWh since setup, from the wallbox energy meter (step 3). `unknown` without a configured meter. |
| `sensor ... Home Charging Cost (Total)` | Home-charging kWh above × the home electricity price from step 6 (fixed value or live entity, see above). `unknown` without a configured meter or price. |
| `sensor ... Savings vs. Combustion Car` | Estimated savings vs. the reference combustion car from step 6, over the distance driven since setup (see "Cost comparison" above). `unknown` until the odometer entity, combustion consumption, and fuel price are all configured. Attributes: `gefahrene_km`, `heimladen_kosten`, `fremdladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live` (whether a live source — Tankerkönig or entity — is currently providing the fuel price instead of the fixed value), `heimstrompreis_live` (same, for the home electricity price). |
| `sensor ... Fuel Price (Selected)` | The raw fuel price currently in effect for the comparison — whichever of the three configured sources is active (see "Cost comparison" above). Attribute `quelle`: `tankerkoenig`, `entity`, or `fixed`. `state_class: measurement`, so it's historized in HA's Long-Term Statistics. |
| `sensor ... Vehicle Avg Consumption` | Overall average consumption in kWh/100 km since setup, from the energy balance: total charged kWh (home + external) ÷ km driven (`_km_driven()`/`_home_kwh()`, same totals `savings()` uses). Distance-weighted across the whole tracked period — unlike `... Trip Log Avg Consumption` (see "Trip log" below), independent of whether every trip was individually confirmed. `unknown` without odometer tracking. |

### Example calculations

A compact reference for the three calculations EV Assistant does, all using the defaults (45 kWh usable battery, 88 % efficiency):

**1) External charge, SoC-only estimate** (no vehicle charging-power sensor configured)
> SoC 32 % → 74 % (Δ 42 pp)
> Battery energy: `0.42 × 45 kWh = 18.9 kWh`
> Billed (AC) estimate: `18.9 ÷ 0.88 = 21.48 kWh` ≈ **21.5 kWh**

**2) External charge, power-sensor estimate** (vehicle charging-power sensor configured, AC-side)
> Suppose the power readings for this session integrate to **11.0 kWh** total (EV Assistant does this integration automatically from however many power readings arrive, using the trapezoidal rule — it doesn't need a fixed sampling interval).
> That 11.0 kWh **is already the billed-side number** — no efficiency division needed, unlike the SoC-only method above.
> Battery-side figure (informational only, e.g. for the losses shown in history): `11.0 × 0.88 = 9.68 kWh` → `losses_kwh = 11.0 − 9.68 = 1.32 kWh`.

**3) Home charge, efficiency calibration sample**
> Wallbox meter: 100.0 kWh → 120.2 kWh (Δ **20.2 kWh** AC drawn)
> SoC: 30 % → 68 % (Δ 38 pp) → battery energy `0.38 × 45 kWh = 17.1 kWh`
> Efficiency sample: `17.1 ÷ 20.2 ≈ 0.847` (84.7 %) — one of at least 3 such samples averaged together to replace the manual efficiency value automatically.

**4) Logging the real receipt** (continuing example 1)
> Estimate was 21.48 kWh; the actual receipt says **21.4 kWh** at **0.59 EUR/kWh**.
> `ev_assistant.log_charge` with `kwh: 21.4`, `price_kwh: 0.59` → cost = `21.4 × 0.59 = 12.63 EUR`.
> The history entry keeps **both** numbers side by side (estimate 21.48 kWh via `soc`, actual 21.4 kWh/12.63 EUR) so you can see over time how close the estimate tends to get.

### Trip log

Trips are detected automatically from the **same odometer entity** used for the cost comparison above (step 1) — no GPS needed. A trip is simply the stretch between two stationary periods: once the odometer starts increasing again after standing still, a trip has begun; once it stops increasing for longer than the configured timeout (step 6, "Trip log"), the trip is finalized. Detected trips shorter than the configured minimum distance are silently dropped (filters out odometer rounding noise). This mirrors the external-charge detector architecture (`TripDetector` next to `ChargeDetector` in `engine.py`) — same idle-based state machine, same restart-safe persistence.

A detected trip records start/end odometer, distance, timestamps, and — if the vehicle's SOC entity was available — start/end SOC and a computed `verbrauch_kwh` (energy consumed, from `delta_soc × usable battery kWh`, clamped to ≥ 0). You then confirm it manually with a start/end location via `ev_assistant.log_trip`, the same "detect automatically, confirm the human part manually" pattern as external charges. There is deliberately **no** business/private purpose field or comment field — this is a plain distance/location log, not a tax-compliance tool.

**Optional location suggestion:** configure a `person` or `device_tracker` entity (step 6, e.g. the driver's phone) and the pending trip gets a `start_ort_vorschlag`/`end_ort_vorschlag` attribute — the entity's HA zone (e.g. "Home") at the moment the trip started/ended. This is a **prefill suggestion only**, not an automatic entry — `log_trip` still requires an explicit call, so a phone that stayed home or a trip outside any configured zone just means an empty suggestion, not a wrong automatic log entry.

| Sensor | Meaning |
|---|---|
| `binary_sensor ... Trip Detection Open` | **On** while at least one detected trip is waiting for a start/end location. Attributes analogous to the charge-pending binary sensor (`anzahl_offen`, `offene_fahrten`). |
| `sensor ... Trip Estimate` | Distance (km) of the oldest pending trip. `unknown` when nothing is pending. |
| `sensor ... Trip km (Last)` | Distance of the most recently confirmed trip, with the full `fahrtenbuch` history as an attribute. |
| `sensor ... Trip Log Count` | How many trips have been confirmed in total. |
| `sensor ... Trip Log km (Total)` | Running total of all confirmed trip distances (`total_increasing`). |
| `sensor ... Trip Log Avg Consumption` | Average kWh consumed per trip, across all trips with known consumption — either imported directly (`verbrauch_kwh`) or derived from `delta_soc × usable battery kWh` for detected trips (clamped to ≥ 0, in case net regeneration during the trip). `unknown` without a single trip with usable consumption data. |

`ev_assistant.export_fahrtenbuch` writes the full trip history (chronological, oldest first) as a semicolon-separated CSV to `www/ev_assistant_fahrtenbuch_<entry_id>.csv`, downloadable at `/local/ev_assistant_fahrtenbuch_<entry_id>.csv` — handy for further processing (e.g. a tax filing) outside Home Assistant.

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): confirm a pending charge and write it to history. **More than one charge can be pending at once** (e.g. two charging stops on a road trip before you get around to confirming either) — `start_ts` picks which one; without it, the oldest is confirmed (FIFO).
- `ev_assistant.discard_pending` — `config_entry_id` (+ optional `start_ts`): discard a pending charge (e.g. a false positive — it wasn't actually an external charge). Same `start_ts` selection rule as above.
- `ev_assistant.edit_charge` — `config_entry_id`, `erfasst_ts`, `kwh`, `price_kwh`: correct the kWh/price of an already-confirmed history entry (e.g. a typo noticed after the fact), identified by its `erfasst_ts` attribute (see the `historie` attribute on the last-cost sensor, or the [EV Assistant Card](https://github.com/weskona/ev-assistant-card)'s History list). Running totals are adjusted by the difference, not recomputed from scratch.
- `ev_assistant.delete_charge` — `config_entry_id`, `erfasst_ts`: fully removes an already-confirmed history entry (e.g. a falsely detected charge that wasn't actually external). Running totals are adjusted by the removed amount. **Not reversible.**
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): generate a **test event without a car** (triggers notification and sensors) — see "Testing" below.
- `ev_assistant.log_trip` — `config_entry_id`, `start_ort`, `end_ort` (+ optional `start_ts`): confirm a pending trip with a start/end location. Same multiple-pending/`start_ts` selection rule as `log_charge`. Unlike `log_charge`, there is **no** fallback to a manual one-off entry without a pending trip — odometer values only ever come from the detector.
- `ev_assistant.discard_pending_trip` — `config_entry_id` (+ optional `start_ts`): discard a pending trip (e.g. moving the car a few meters in the driveway).
- `ev_assistant.export_fahrtenbuch` — `config_entry_id`: write the full trip history as CSV to `www/` (see "Trip log" above).
- `ev_assistant.simulate_trip` — `config_entry_id`, `km`: generate a **test trip without a car**, same idea as `simulate_event`.
- `ev_assistant.edit_trip` — `config_entry_id`, `erfasst_ts`, `start_ort`, `end_ort`: correct the start/end location of an already-confirmed trip log entry (e.g. a typo noticed after the fact), identified by its `erfasst_ts` attribute. Distance/odometer values are **not** editable — they only ever come from the detector.
- `ev_assistant.delete_trip` — `config_entry_id`, `erfasst_ts`: fully removes an already-confirmed trip log entry (e.g. a falsely detected trip). Running totals are adjusted by the removed amount. **Not reversible.**
- `ev_assistant.import_fahrtenbuch` — `config_entry_id`, `trips` (a list): bulk-import historical trips from another trip-log app/export, bypassing the odometer detector entirely. Each entry: `start`/`ende` as local time `"YYYY-MM-DD HH:MM:SS"`, `start_ort`, `ziel_ort`, `strecke` (km), optionally `verbrauch_kwh`/`avg_verbrauch`/`avg_speed`. Odometer values stay empty (the source has none) — only distance is tracked. Imported entries are tagged `quelle: "import"`; re-running the same import skips entries already present (deduplicated by start time), so it's safe to call repeatedly. Accepts either a plain list or the whole source file's `{"trips": [...]}` shape directly (common copy-paste from a JSON export).

All services require `config_entry_id` to target a specific vehicle if you run more than one EV Assistant instance.

### Manual-entry UI (recommended: dedicated card)

**[EV Assistant Card](https://github.com/weskona/ev-assistant-card)** is a custom Lovelace card built specifically for this integration — point it at your vehicle's device and it finds all sensors itself, shows an inline kWh/price form when a charge is pending, and calls the services directly with the correct `config_entry_id` (no helper entities or automations needed, works correctly with multiple vehicles). This supersedes the YAML package below.

### Manual-entry UI (legacy, YAML package)

`packages/ev_assistant_ui.yaml` provides two input fields + save/discard buttons wired to the services above; `packages/ev_assistant_karte.yaml` is a matching Lovelace card. Copy into `config/packages/` (`homeassistant: packages: !include_dir_named packages`) and reload.

> **Known limitation:** the card's example entity IDs (e.g. `sensor.ev_assistant_letzte_kosten`) assume the old fixed device name "EV Assistant" — since v0.4.0 the device is named after your vehicle instead, so adjust the card's entity list to match your actual entity IDs. If you're setting this up fresh, use the [EV Assistant Card](https://github.com/weskona/ev-assistant-card) above instead.

### Testing

**1) Logic only (no HA):**
```bash
cd <repo>
python -m pytest tests -q
```
**2) End-to-end in HA (no car needed):** Developer tools → Services → call `ev_assistant.simulate_event` with `config_entry_id`, `soc_start: 32`, `soc_end: 74`. Expect: a notification appears, `binary_sensor ... External Charge Detection Open` turns on, `sensor ... External Charge Estimate` ≈ 21.48 kWh (see the worked example above). Then enter kWh/price and call `ev_assistant.log_charge` (or the save button) — history/totals update, and a publish happens to `ev_assistant/ladung/extern/<entry_id>/erfasst`.

**3) Trip log, end-to-end (no car needed):** call `ev_assistant.simulate_trip` with `config_entry_id`, `km: 12.5`. Expect: a notification appears, `binary_sensor ... Trip Detection Open` turns on, `sensor ... Trip Estimate` shows `12.5`. Then call `ev_assistant.log_trip` with `start_ort`/`end_ort` — `sensor ... Trip km (Last)` updates. Finally call `ev_assistant.export_fahrtenbuch` and check `www/ev_assistant_fahrtenbuch_<entry_id>.csv` was created.

### Data record (history)

Deliberately contains **both** the manually entered `kwh`/`preis_kwh`/`kosten` **and** the automatic `schaetzung_kwh` plus its `quelle` (`soc`/`power_ac`/`power_dc`) — so you can see over time how close the estimate gets, and adjust `charge_efficiency` accordingly (or just let the automatic calibration handle it).

### Structure

```
custom_components/ev_assistant/
  __init__.py        # setup, services, unload (reload-capable)
  manifest.json
  const.py
  engine.py           # pure logic (pytest-testable) — ChargeDetector + EfficiencyCalibrator + TripDetector
  coordinator.py      # entity wiring, detection, calibration, persistence, notification
  config_flow.py      # config + options flow (7 steps)
  entity.py           # shared entity base (device grouping, vehicle-based device name)
  sensor.py
  binary_sensor.py
  services.yaml
  strings.json
  translations/{de,en}.json
packages/             # optional UI glue + Lovelace card (see known limitation above)
tests/                # pytest (engine.py)
```

### Requirements

- Home Assistant 2024.1+
- [`evcc_intg`](https://github.com/marq24/ha-evcc) integration installed (required — evcc entities are auto-discovered from it)

---

## 🇩🇪 Deutsch

### Funktionsweise

EV Assistant braucht kein GPS, keine herstellerspezifische API und keine Liste bekannter Ladestationen. Es funktioniert allein mit zwei Werten, die ohnehin schon aus Auto und Zuhause vorliegen:

1. **Ladezustand (SoC)** — der Akku-Prozentwert, z.B. aus einem Hersteller-Cloud-Sensor oder einem günstigen OBD-Dongle wie WiCAN Pro.
2. **Heim-Laden-Signal** — irgendetwas, das dir sagt "das Auto lädt gerade an meiner eigenen Wallbox" (z.B. von evcc, einer Warp-Box, oder einer beliebigen Ladebox-Integration).

Der Grundgedanke lässt sich in einem Satz zusammenfassen: **Wenn der Akkuprozentwert steigt, während das Heim-Laden-Signal "nein" sagt, muss das Auto woanders laden** — an einer öffentlichen Ladesäule, im Hotel, bei Freunden, auf der Arbeit. Das ist eine „Fremdladung". Heim-Laden wird von der Erkennung bewusst ignoriert — das trackst du ohnehin schon über deine eigene Wallbox/evcc-Anbindung, EV Assistant meldet sich also nur bei Ladungen, die du *sonst nicht mitbekommen würdest*.

Intern beobachtet eine kleine Zustandsmaschine (`engine.py::ChargeDetector`) jeden neuen SoC-Wert:

- **Ruhezustand** — es passiert nichts. Der niedrigste zuletzt gesehene SoC-Wert wird gemerkt (der „Anker"). Sinkt der SoC wieder ab (oder ist das Heim-Laden-Signal aktiv), wird der Anker auf diesen neuen, niedrigeren Wert zurückgesetzt. Der Anker steht also immer für „der Ladestand kurz bevor irgendetwas als Nächstes passiert".
- **Beginn einer Session** — sobald der SoC um mindestens `start_delta` (Standard **1 %**) über den Anker gestiegen ist, *während* Heim-Laden aus ist, beginnt eine Fremdladung. Offizieller Startpunkt ist der Anker (der letzte bekannte Tiefpunkt), nicht der Moment, in dem die Schwelle überschritten wurde — so wird auch das allererste bisschen Ladung, das die Erkennung ausgelöst hat, korrekt mitgezählt.
- **Laufende Session** — solange der SoC weiter steigt, merkt sich EV Assistant den höchsten bisher gesehenen Wert („Peak"). Eine kleine `noise`-Toleranz (Standard **0,5 %**) fängt Sensor-Rauschen ab (SoC-Werte wackeln gelegentlich um einen Bruchteil eines Prozents, ohne dass tatsächlich etwas passiert) — das verhindert Fehlinterpretationen durch Messrauschen. `start_delta` sollte **größer** als `noise` sein — sind beide gleich (oder `start_delta` kleiner), kann normales Rauschen bereits wie ein echter Anstieg aussehen und Fehlalarme auslösen.
- **Ende einer Session** — je nachdem, was zuerst eintritt:
  - das Heim-Laden-Signal wird aktiv (du bist zuhause angekommen und hast eingesteckt — die gerade abgeschlossene Fremdladung wird jetzt finalisiert), oder
  - der SoC fällt um mehr als `drop_ends` (Standard **1 %**) unter den Peak (du hast abgesteckt und bist losgefahren), oder
  - `idle_timeout_s` (Standard **600 s / 10 Minuten**) vergeht ohne weiteren SoC-Anstieg (Ladevorgang beendet, oder die Verbindung ist abgebrochen).

Am Ende hat EV Assistant einen `soc_start` und einen `soc_end` und muss daraus eine Energie-Schätzung machen — wie genau, mit konkreten Zahlen, steht im nächsten Abschnitt.

### Erkennungs-Ablauf — ein durchgerechnetes Beispiel

Angenommen dein Auto hat einen nutzbaren Akku von 45 kWh und den Standard-Ladewirkungsgrad von 88 % (beide in Schritt 1 der Einrichtung einstellbar). Du fährst mit 32 % Akkustand von zuhause weg und steckst an einer öffentlichen Ladesäule ein. Ein Fahrzeug-Ladeleistungssensor ist noch nicht konfiguriert — nur SoC und das Heim-Laden-Signal.

1. Bevor du losgefahren bist, lagen die letzten SoC-Werte konstant bei 32 % mit Heim-Laden aus (du hast nicht geladen, nur geparkt/bist gefahren). Der Anker steht bei **32 %**.
2. An der Ladesäule kommt der nächste SoC-Wert mit **35 %** rein. Das sind +3 Prozentpunkte über dem Anker — genau die `start_delta`-Schwelle — also **beginnt** eine Fremdladung-Session, offiziell ab `soc_start = 32 %` (dem Anker), zum Zeitpunkt dieses letzten 32-%-Werts.
3. In den nächsten Stunden steigt der SoC weiter: 40 %, 55 %, 68 %, 74 %. Jeder neue Höchstwert wird als Peak gemerkt.
4. Du steckst bei **74 %** ab und fährst nach Hause. Zehn Minuten vergehen, ohne dass der SoC-Sensor einen weiteren Anstieg meldet (es wird nicht mehr geladen) — der `idle_timeout_s` greift und die Session **endet**.
5. Delta = 74 % − 32 % = **42 Prozentpunkte**. Ohne Fahrzeug-Ladeleistungssensor greift EV Assistant auf die reine SoC-Schätzung zurück:
   - Batterieseitige Energie: `42 % von 45 kWh = 18,9 kWh`
   - AC-seitige (abgerechnete) Schätzung, unter Berücksichtigung der Ladeverluste: `18,9 kWh ÷ 0,88 = 21,48 kWh` — die Benachrichtigung rundet das auf **≈ 21,5 kWh**.
6. EV Assistant tut jetzt Folgendes:
   - speichert dies als **offene** Ladung,
   - feuert das Event `ev_assistant_pending` (mit `config_entry_id`, damit du bei mehreren Autos weißt, welches gemeint ist),
   - schickt eine Benachrichtigung: *„+42 % (32 → 74 %), ~21,5 kWh geschätzt. kWh und Preis eintragen."*
   - schaltet `binary_sensor … Fremdladung Erfassung offen` ein und setzt `sensor … Fremdladung Schätzung` auf 21,48 kWh.
7. Ein paar Tage später kommt der Beleg: tatsächlich **21,4 kWh** abgerechnet zu **0,59 EUR/kWh** = **12,63 EUR**. Du rufst `ev_assistant.log_charge` (oder die optionale Karte) mit diesen echten Werten auf.
8. EV Assistant schreibt einen Historieneintrag mit **beiden** Werten — der Schätzung (21,48 kWh, Quelle `soc`) und dem echten Wert (21,4 kWh, 0,59 EUR/kWh, 12,63 EUR) — aktualisiert die laufenden Summen, löscht die offene Ladung und entfernt die Benachrichtigung.

Die reine SoC-Schätzung (21,48 kWh) lag hier fast exakt richtig (21,4 kWh real) — das ist aber auch etwas Glück. Echte Rechnungen schwanken je nach Ladeeffizienz der Säule, Kabelverlusten und Akkutemperatur, weshalb für die tatsächliche Kostenerfassung immer der Beleg-Wert gewinnt.

### Energie-Schätzmethoden

Die Schätzung, die bei einer offenen Ladung angezeigt und als `schaetzung_kwh`/`quelle` in der Historie gespeichert wird, stammt aus einer von drei Methoden, automatisch gewählt je nach Konfiguration (pro Session sichtbar als `energy_source`/`quelle`: `soc`, `power_ac` oder `power_dc`):

| Quelle | Wann verwendet | Berechnung |
|---|---|---|
| `soc` | Kein Fahrzeug-Ladeleistungssensor konfiguriert (oder keine Daten während dieser Session) | `Batterie-kWh = SoC-Delta% × nutzbare kWh`; `AC-kWh = Batterie-kWh ÷ Ladewirkungsgrad` |
| `power_ac` | Fahrzeug-Ladeleistungssensor konfiguriert, mit **„Ladeleistung ist AC-seitig"** aktiviert (Standard) | `AC-kWh` = die Leistungswerte über die Zeit integriert (Trapezregel) — das ist bereits der abgerechnete Wert, keine Wirkungsgrad-Rechnung nötig; `Batterie-kWh = AC-kWh × Ladewirkungsgrad` (nur informativ) |
| `power_dc` | Fahrzeug-Ladeleistungssensor konfiguriert, „AC-seitig" deaktiviert (Sensor misst batterie-/DC-seitig) | `Batterie-kWh` = die Leistungswerte über die Zeit integriert; `AC-kWh = Batterie-kWh ÷ Ladewirkungsgrad` |

Ein Fahrzeug-Ladeleistungssensor (wenn vorhanden) ist meist genauer als die reine SoC-Schätzung, da er die *tatsächliche* Ladekurve abbildet (die typischerweise deutlich vor 100 % abflacht) statt einen linearen Zusammenhang zwischen Prozent und kWh anzunehmen. Er kommt aus der Fahrzeug-Telemetrie (nicht deiner Wallbox), liefert daher auch bei einer Fremdladung unterwegs Werte — die eigene Wallbox hat dort naturgemäß gar kein Signal.

### Installation

**Über HACS**
1. HACS → Integrationen → ⋮ → **Benutzerdefinierte Repositories**
2. URL: `https://github.com/weskona/ev_assistant` — Kategorie: **Integration**
3. EV Assistant installieren, Home Assistant neu starten

**Manuell**
1. Ordner `custom_components/ev_assistant/` nach `config/custom_components/` kopieren
2. Home Assistant neu starten

### Konfiguration

Einstellungen → Geräte & Dienste → **Integration hinzufügen** → „EV Assistant". Die Einrichtung läuft in 7 Schritten (identisch auch beim Bearbeiten über **Konfigurieren**):

1. **Fahrzeug** — Hersteller + Modell (Pflicht, z.B. „Peugeot" / „e-2008" — ergeben zusammen den HA-Gerätenamen), Erstzulassung (optional, nur Anzeige), Kilometerstand-Entität (optional, gefiltert auf `sensor` + `device_class: distance`), **Fahrzeug-SoC** (Pflicht, gefiltert auf `sensor` + `device_class: battery` — der Akkustand aus der Hersteller-Integration, dem OBD-Dongle usw.), nutzbare Akku-Kapazität in kWh (Pflicht — der *netto* nutzbare Wert, nicht die oft größere Brutto-/Werksangabe mancher Hersteller; bestimmt direkt, wie viele kWh ein Prozentpunkt SoC-Anstieg entspricht, falsch eingetragen sind also alle Energie-Schätzungen falsch), Ladewirkungsgrad (nur ein Startwert — wird automatisch ersetzt, sobald genug echte Heim-Ladesessions vorliegen, siehe Kalibrierung unten).
2. **evcc & Wallbox** — alle evcc-Standort- und Ladepunkt-Entitäten (PV-Leistung, Netz, Hausspeicher, Tarife, Statistiken, Ladeleistung, Ladestatus, Modus, Session-Energie usw.) werden **automatisch erkannt** aus der installierten evcc-Integration — keine manuelle Entitäts-Auswahl nötig. Nur zwei optionale Felder bleiben: der Fahrzeugname in evcc (filtert die Heimladen-Historie auf dieses Fahrzeug, wenn mehrere EVs eine evcc-Instanz teilen) und die **Wallbox-Ladeleistungs-Entität** (gefiltert auf `sensor` + `device_class: power` — dient als Ja/Nein-Signal „lädt gerade zuhause"; ein Wert **über 0,1 kW gilt als „lädt"**). Ohne die Wallbox-Leistungsentität wird jeder SoC-Anstieg fälschlich als Fremdladung erkannt. Setzt die `evcc_intg`-Integration voraus.
3. **Ladeleistung** (optional) — zwei unterschiedliche Quellen für zwei unterschiedliche Zwecke. Die Ladeleistung ist ein Momentanwert in W/kW, typischerweise aus der Fahrzeug-Telemetrie statt deiner Wallbox (liefert dadurch auch bei einer Fremdladung unterwegs Werte, wo die Wallbox nichts misst); sie verbessert die Energie-Schätzung einer Fremdladung gegenüber der reinen SoC-Delta-Schätzung (siehe „Energie-Schätzmethoden" oben). Der **Wallbox-Energiezähler** dagegen ist ein kumulativer kWh-Zähler deiner eigenen Wallbox (nie ein Momentanwert, nur beim Heim-Laden relevant) — er dient der automatischen Ladewirkungsgrad-Kalibrierung *und* den Heimladen-Kosten in Schritt 7.
4. **Ausgabe** (optional) — eine Benachrichtigung im Home-Assistant-eigenen Benachrichtigungsbereich erscheint bei einer erkannten Ladung immer automatisch, unabhängig von diesem Schritt. Der `notify.*`-Dienst schickt zusätzlich eine Push-Nachricht (z.B. aufs Handy).
5. **Erkennungs-Feinjustierung** — Schwellwerte der oben beschriebenen Zustandsmaschine (`start_delta`, `noise`, `idle_timeout_s`, `drop_ends`). Eine Ladung startet, sobald der SoC um `start_delta` über den letzten Ruhewert steigt; sie endet entweder bei einem SoC-Abfall um mehr als `drop_ends` unter den erreichten Höchststand, oder wenn `idle_timeout_s` lang kein neuer Höchststand erreicht wurde (z.B. Akku voll). `noise` toleriert normales Sensor-Zittern beim Verfolgen des Höchststands und muss immer **kleiner** sein als `start_delta`, sonst kann schon Rauschen eine falsche Erkennung auslösen. Die Standardwerte passen für die meisten Fahrzeuge; bei einem Auto, dessen SoC nur grob/selten aktualisiert wird (manche Cloud-APIs), großzügiger einstellen.
6. **Fahrtenbuch** (optional) — Schwellwerte der Fahrten-Erkennung (`trip_min_km`, `trip_idle_timeout_s`), siehe „Fahrtenbuch" unten. Die Standardwerte passen für die meisten Kilometerstand-Sensoren. Zusätzlich eine optionale Orts-Vorschlag-Quelle (`gps_entity`, eine person-/device_tracker-Entität).
7. **Kostenvergleich** (optional) — siehe „Kostenvergleich gegenüber einem Verbrenner" unten. Kraftstoffpreis-Priorität: Tankerkönig-Auto-Erkennung (Kraftstoffsorte wählen) > Kraftstoffpreis-Entität > fester Wert — nur eine Quelle konfigurieren.

### Quellen: herstellerunabhängig

Das SoC-Signal kommt aus einer beliebigen **HA-Entität** — funktioniert mit jedem Hersteller oder Dongle, der einen SoC-Sensor in HA bereitstellt.

- **WiCAN Pro:** HA-`mqtt`-Integration einrichten und den daraus entstehenden MQTT-SoC-Sensor verwenden.
- **Stellantis / VW / …:** SoC-Entität = `sensor.<auto>_battery`. Cloud-SoC ist oft grob/selten — dann `start_delta` höher und `idle_timeout_s` großzügiger einstellen; der Leistungs-Pfad entfällt mangels echter Leistungsdaten (Fallback auf SoC × Wirkungsgrad).

### Automatische Ladewirkungsgrad-Kalibrierung

Statt eines festen manuellen Werts kann EV Assistant den echten Ladewirkungsgrad (AC→Batterie) aus deinen eigenen Heim-Ladesessions lernen — dabei geht es um **keine** Fremdladung, sondern rein darum, wie effizient *dein Auto* beim Laden zuhause Netzstrom in gespeicherte Akku-Energie umwandelt.

**So funktioniert es:** Im Schritt „Ladeleistung" einen **Wallbox-Energiezähler** hinterlegen — ein kumulativer kWh-Zähler, der nur hochzählt (wie ein normaler Stromzähler), keinen „Session-Energie"-Wert, der zurückgesetzt wird. Jedes Mal, wenn das Heim-Laden-Signal angeht, merkt sich EV Assistant den aktuellen SoC und den aktuellen Zählerstand der Wallbox. Geht das Heim-Laden-Signal wieder aus, wird der SoC-Gewinn gegen die für dieselbe Session verbrauchte Wallbox-Energie verglichen und der Wirkungsgrad berechnet:

`Wirkungsgrad = (SoC-Gewinn% × nutzbare kWh) ÷ Wallbox-Energie-Delta-kWh`

**Durchgerechnetes Beispiel:** Dein Wallbox-Zähler zeigt **100,0 kWh**, als eine Heim-Ladung beginnt, und **120,2 kWh**, als sie endet — es wurden also **20,2 kWh** AC-Energie aus dem Netz gezogen. Im selben Zeitraum stieg der SoC von **30 %** auf **68 %**, ein Gewinn von 38 Prozentpunkten. Bei 45 kWh nutzbarer Kapazität sind das `38 % × 45 kWh = 17,1 kWh`, die tatsächlich in die Batterie geflossen sind. Der gemessene Wirkungsgrad für diese eine Session ist `17,1 ÷ 20,2 ≈ 0,847` (84,7 %).

Einer einzelnen Session wird nicht blind vertraut — unplausible Stichproben werden automatisch verworfen (Session zu kurz: weniger als 5 Prozentpunkte SoC-Gewinn; Daten fehlen; oder ein Ergebnis außerhalb des plausiblen Bereichs von 50–100 %, was meist auf einen Zählerreset oder eine verpasste Ablesung hindeutet). Sobald **3 gültige Sessions** gesammelt wurden, mittelt EV Assistant die letzten 10 Stichproben und **beginnt automatisch, diesen gemessenen Wert** für alle weiteren Berechnungen zu verwenden — live, ohne Neustart. Wenn dein Auto tatsächlich 0,847, 0,86 und 0,855 über drei Sessions liefert, wird der neue verwendete Wert deren Durchschnitt, **0,854 (85,4 %)** — er ersetzt den Wert, den du ursprünglich bei der Einrichtung eingetragen hast.

Der manuelle Wert aus Schritt 1 bleibt die ganze Zeit Fallback, bis genug Sessions vorliegen. Siehe Sensor „… Ladewirkungsgrad (gemessen)" unten für den aktuellen Live-Status.

### Kostenvergleich gegenüber einem Verbrenner

Alle Felder in Schritt 6 sind optional — beliebig viele oder wenige konfigurieren; die Sensoren unten zeigen einfach `unknown`, solange ihre nötigen Eingaben fehlen.

**Gefahrene Strecke:** die Kilometerstand-Entität aus Schritt 1 wird beim ersten Start einmal ausgelesen und als Referenzwert gemerkt. „Gefahrene km" ist immer `aktueller Kilometerstand − dieser Referenzwert` — der Vergleich deckt also alles seit der Einrichtung von EV Assistant ab, nicht die Gesamt-Laufleistung des Autos.

**Heimladen-Kosten:** geladene kWh und Preis werden jeweils über eine eigene Prioritätskette ermittelt. kWh: evccs eigene Fahrzeug-Ladesession-Statistik (am präzisesten, erfordert aber evccs „Erweiterte Fahrzeugdaten" und ist daher meist nicht verfügbar) schlägt evccs standortweite „gesamt geladene Energie"-Statistik (`sensor.evcc_stat_total_charged_kwh`, automatisch aus der evcc-Integration übernommen) schlägt den reinen **Wallbox-Energiezähler-Delta** aus Schritt 3 (erster gesehener Wert als Referenz, aktueller Wert minus Referenz). Die standortweite evcc-Statistik wird nur verwendet, wenn für dieses Fahrzeug *auch* ein Wallbox-Energiezähler konfiguriert ist — diese Statistik ist nicht pro Fahrzeug, ohne diese Absicherung würde eine zweite EV-Assistant-Instanz für ein weiteres Auto am selben evcc-Standort fälschlich die Heimladen-Summe des ersten Autos übernehmen. Preis: evccs standortweite Durchschnittspreis-Statistik (`sensor.evcc_stat_total_avg_price`, gleiche Fahrzeug-Absicherung) schlägt eine manuell verknüpfte **Live-Entität** (`home_price_entity`, z.B. ein dynamischer Tarif-Sensor, kWh-gewichtet — siehe unten) schlägt den festen **Wert** (`home_price_kwh`). kWh × Preis ergibt die geschätzten Heimladen-Kosten. Ohne für dieses Fahrzeug konfigurierten Wallbox-Zähler wird das Heimladen einfach als 0 behandelt — der Vergleich funktioniert dann nur mit den (immer getrackten) Fremdladungskosten.

**Verbrenner-Referenz:** `(gefahrene km ÷ 100) × verbrenner_l_100km × verbrenner_price_per_liter` — eine einfache „was hätte diese Strecke an Kraftstoff gekostet"-Schätzung für das von dir beschriebene Vergleichsfahrzeug. Drei Kraftstoffpreis-Quellen stehen zur Wahl, in dieser Prioritätsreihenfolge: **Tankerkönig-Auto-Erkennung** (Kraftstoffsorte wählen — `super`, `super_e10` oder `diesel` — EV Assistant findet dann automatisch alle in der Tankerkönig-Kernintegration eingerichteten Tankstellen und nutzt immer die günstigste gerade *geöffnete*) schlägt eine manuell verknüpfte **Live-Entität** (`verbrenner_price_entity`, z.B. ein beliebiger anderer Kraftstoffpreis-Sensor), die wiederum den festen **Wert** (`verbrenner_price_per_liter`) schlägt. Nur eine Quelle konfigurieren — welche gesetzt ist, übernimmt. Weil ein Live-/Auto-Preis schwankt, wird nicht einfach der aktuelle Momentanwert auf die gesamte gefahrene Strecke angewendet: EV Assistant führt stattdessen einen **zeitgewichteten Durchschnitt** aller seit Einrichtung gesehenen Preise (jeder Wert gewichtet danach, wie lange er tatsächlich galt) — so wird eine Woche zu 1,70 EUR/L gefolgt von einem Tag zu 1,90 EUR/L nicht fälschlich so gerechnet, als hätte 1,90 EUR/L die ganze Zeit gegolten. Zeitgewichtung passt hier, weil Fahren nicht systematisch mit Kraftstoffpreis-Schwankungen korreliert. Beim Heimstrompreis über die Live-Entität ist das anders: Heimladen wird (z.B. per evcc) oft gezielt in Günstigpreis-Fenster gelegt, deshalb führt EV Assistant hier stattdessen einen **kWh-gewichteten Durchschnitt** — jeder Preis gewichtet danach, wie viel während seiner Gültigkeit tatsächlich geladen wurde (über den Wallbox-Energiezähler) — eine teure Preisspitze ohne jede Ladung fließt so mit Gewicht 0 ein, statt den Durchschnitt hochzuziehen. Fällt eine Live-Quelle (Tankerkönig oder Entität) mal aus (`unavailable`, auch über Neustarts hinweg), wird ihr **letzter bekannter Wert weiterverwendet**, statt dass der Vergleich einfach ausfällt — und solange Tankerkönig keinen einzigen gültigen Wert liefern kann (z.B. Kraftstoffsorte nie gefunden, Integration entfernt), erscheint eine **dauerhafte Benachrichtigung** in Home Assistant, die automatisch verschwindet, sobald wieder ein gültiger Preis vorliegt. Der Sensor „… Kraftstoffpreis (ausgewählt)" zeigt den aktuell geltenden Rohpreis zusammen mit dem Attribut `quelle` (`tankerkoenig`/`entity`/`fixed`), welche der drei Quellen gerade aktiv ist; die Attribute `kraftstoffpreis_live` und `heimstrompreis_live` am Sensor „… Ersparnis ggü. Verbrenner" zeigen, ob gerade eine Live-Quelle (statt des festen Werts) den Kraftstoff- bzw. Heimstrompreis liefert.

**Durchgerechnetes Beispiel:** du bist seit der Einrichtung von EV Assistant **1.000 km** gefahren. Dein Wallbox-Zähler zeigt **150 kWh** zuhause geladen, bei einem eingetragenen Preis von **0,30 EUR/kWh** → **45,00 EUR** Heimladen-Kosten. Deine erfassten Fremdladungen summieren sich bisher auf **50,00 EUR**. Gesamte EV-Energiekosten: `45,00 + 50,00 = 95,00 EUR`. Dein Vergleichs-Verbrenner verbraucht 6,5 L/100km bei einem Kraftstoffpreis von 1,75 EUR/L: `(1.000 ÷ 100) × 6,5 × 1,75 = 113,75 EUR`. Geschätzte Ersparnis: `113,75 − 95,00 = 18,75 EUR` über diese 1.000 km.

### Sensoren im Detail

Das HA-Gerät heißt wie das Fahrzeug (`{Hersteller} {Modell}`), Entitäten erscheinen daher als `{Gerät} {Entität}`, z.B. „Peugeot e-2008 Fremdladung Anzahl".

| Sensor | Bedeutung |
|---|---|
| `binary_sensor … Fremdladung Erfassung offen` | **An**, solange mindestens eine erkannte Fremdladung auf deine Bestätigung der echten kWh/des Preises wartet. Es können mehrere gleichzeitig offen sein — Attribute: `anzahl_offen` (Anzahl), `offene_ladungen` (die vollständige Liste, je mit Start-/Endzeit, SoC Start/Ende, Schätzung, Quelle), zusätzlich die Felder der ältesten direkt oben drüber gespiegelt zur Bequemlichkeit. |
| `sensor … Fremdladung Schätzung` | Die geschätzten kWh der aktuell offenen Ladung (siehe „Energie-Schätzmethoden"). `unknown`, wenn nichts offen ist. |
| `sensor … Fremdladung kWh (letzte)` | Der `kwh`-Wert, den du für die zuletzt bestätigte Fremdladung eingetragen hast (also vom Beleg, nicht die Schätzung). |
| `sensor … Fremdladung Kosten (letzte)` | `kwh × preis_kwh` für dieselbe zuletzt bestätigte Ladung. |
| `sensor … Fremdladung Preis (letzter)` | Der Preis pro kWh, den du für die zuletzt bestätigte Ladung eingetragen hast. |
| `sensor … Fremdladung Ladezeit (letzte)` | Wie lange die erkannte Ladesession gedauert hat (von Erkennungs-Start bis -Ende), in Minuten. `unknown` bei älteren Historien-Einträgen von vor Einführung dieses Sensors, oder bei einem manuellen Einzeleintrag ohne zugrunde liegende Erkennung. |
| `sensor … Fremdladung kWh (gesamt)` | Laufende Summe aller bestätigten Fremdladungs-kWh seit Einrichtung (bzw. seit dem letzten Reset — ein `total_increasing`-Sensor, direkt fürs HA-Energie-Dashboard nutzbar). |
| `sensor … Fremdladung Kosten (gesamt)` | Laufende Summe aller bestätigten Fremdladungskosten. |
| `sensor … Fremdladung Anzahl` | Wie viele Fremdladungen insgesamt bestätigt wurden. |
| `sensor … Ladewirkungsgrad (gemessen)` (Diagnose) | Der live kalibrierte Wirkungsgrad aus **Heim**-Ladesessions (siehe oben) — hat mit Fremdladungen nichts zu tun. Als Prozentwert angezeigt. Attribute: `anzahl_sessions` (bisher gesammelte Stichproben), `benoetigte_sessions` (3, das Minimum bevor er übernimmt), `einzelwerte_prozent` (jede Einzelstichprobe), `wird_verwendet` (ob der gemessene Wert gerade anstelle des manuellen verwendet wird), `manueller_wert_prozent` (der konfigurierte Fallback-Wert). |
| `sensor … Kilometerstand` (Diagnose) | Spiegelt die in Schritt 1 konfigurierte Kilometerstand-Entität, falls vorhanden, gruppiert am EV-Assistant-Gerät. Reine Anzeige-Weiterleitung. |
| `sensor … Erstzulassung` (Diagnose) | Das in Schritt 1 eingetragene Erstzulassungsdatum, als eigener `date`-Sensor. |
| `sensor … Heimladen kWh (gesamt)` | Gesamte zuhause geladene kWh seit Einrichtung, aus dem Wallbox-Energiezähler (Schritt 3). `unknown` ohne konfigurierten Zähler. |
| `sensor … Heimladen Kosten (gesamt)` | Obige Heimladen-kWh × der Heimstrompreis aus Schritt 6 (fester Wert oder Live-Entität, siehe oben). `unknown` ohne konfigurierten Zähler oder Preis. |
| `sensor … Ersparnis ggü. Verbrenner` | Geschätzte Ersparnis gegenüber dem Vergleichs-Verbrenner aus Schritt 6, über die seit Einrichtung gefahrene Strecke (siehe „Kostenvergleich" oben). `unknown`, bis Kilometerstand-Entität, Verbrenner-Verbrauch und Kraftstoffpreis alle konfiguriert sind. Attribute: `gefahrene_km`, `heimladen_kosten`, `fremdladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live` (ob gerade eine Live-Quelle — Tankerkönig oder Entität — statt des festen Werts den Kraftstoffpreis liefert), `heimstrompreis_live` (dasselbe für den Heimstrompreis). |
| `sensor … Kraftstoffpreis (ausgewählt)` | Der aktuell für den Vergleich geltende Rohpreis — je nachdem, welche der drei konfigurierten Quellen aktiv ist (siehe „Kostenvergleich" oben). Attribut `quelle`: `tankerkoenig`, `entity` oder `fixed`. `state_class: measurement`, dadurch in HAs Langzeitstatistik historisierbar. |
| `sensor … Fahrzeug Durchschnittsverbrauch` | Gesamt-Durchschnittsverbrauch in kWh/100 km seit Einrichtung, aus der Energiebilanz: geladene kWh gesamt (Heim + Fremd) ÷ gefahrene km (`_km_driven()`/`_home_kwh()`, dieselben Gesamtwerte wie `savings()`). Distanzgewichtet über die gesamte erfasste Zeit — anders als „… Fahrtenbuch Durchschnittsverbrauch" (siehe „Fahrtenbuch" unten) unabhängig davon, ob jede Fahrt einzeln bestätigt wurde. `unknown` ohne Kilometerstand-Tracking. |

### Beispielrechnungen

Eine kompakte Referenz für die drei Berechnungen, die EV Assistant durchführt, jeweils mit den Standardwerten (45 kWh nutzbarer Akku, 88 % Wirkungsgrad):

**1) Fremdladung, reine SoC-Schätzung** (kein Fahrzeug-Ladeleistungssensor konfiguriert)
> SoC 32 % → 74 % (Δ 42 Prozentpunkte)
> Batterie-Energie: `0,42 × 45 kWh = 18,9 kWh`
> Abgerechnete (AC-)Schätzung: `18,9 ÷ 0,88 = 21,48 kWh` ≈ **21,5 kWh**

**2) Fremdladung, Schätzung per Ladeleistungssensor** (Fahrzeug-Ladeleistungssensor konfiguriert, AC-seitig)
> Angenommen die Leistungswerte dieser Session integrieren sich zu insgesamt **11,0 kWh** (EV Assistant macht diese Integration automatisch aus beliebig vielen Leistungswerten per Trapezregel — kein festes Abtastintervall nötig).
> Diese 11,0 kWh sind **bereits der abgerechnete Wert** — anders als bei der reinen SoC-Schätzung ist keine Wirkungsgrad-Division nötig.
> Batterieseitiger Wert (nur informativ, z.B. für die in der Historie angezeigten Verluste): `11,0 × 0,88 = 9,68 kWh` → `losses_kwh = 11,0 − 9,68 = 1,32 kWh`.

**3) Heim-Ladung, Wirkungsgrad-Stichprobe**
> Wallbox-Zähler: 100,0 kWh → 120,2 kWh (Δ **20,2 kWh** AC bezogen)
> SoC: 30 % → 68 % (Δ 38 Prozentpunkte) → Batterie-Energie `0,38 × 45 kWh = 17,1 kWh`
> Wirkungsgrad-Stichprobe: `17,1 ÷ 20,2 ≈ 0,847` (84,7 %) — eine von mindestens 3 solchen Stichproben, die gemittelt automatisch den manuellen Wirkungsgrad-Wert ersetzen.

**4) Den echten Beleg erfassen** (Fortsetzung von Beispiel 1)
> Die Schätzung lag bei 21,48 kWh; der echte Beleg sagt **21,4 kWh** zu **0,59 EUR/kWh**.
> `ev_assistant.log_charge` mit `kwh: 21.4`, `price_kwh: 0.59` → Kosten = `21,4 × 0,59 = 12,63 EUR`.
> Der Historieneintrag behält **beide** Werte nebeneinander (Schätzung 21,48 kWh via `soc`, echt 21,4 kWh/12,63 EUR) — so siehst du über die Zeit, wie nah die Schätzung tendenziell liegt.

### Fahrtenbuch

Fahrten werden automatisch aus derselben Kilometerstand-Entität erkannt, die auch für den Kostenvergleich oben genutzt wird (Schritt 1) — kein GPS nötig. Eine Fahrt ist einfach die Strecke zwischen zwei Standzeiten: sobald der Kilometerstand nach einer Standzeit wieder steigt, hat eine Fahrt begonnen; sobald er länger als der konfigurierte Timeout (Schritt 6, „Fahrtenbuch") nicht mehr steigt, wird die Fahrt abgeschlossen. Erkannte Fahrten unter der konfigurierten Mindest-Strecke werden stillschweigend verworfen (filtert Rundungsrauschen des Kilometerstand-Sensors). Das Ganze spiegelt die Architektur der Fremdlade-Erkennung (`TripDetector` neben `ChargeDetector` in `engine.py`) — dieselbe standzeit-basierte Zustandsmaschine, dieselbe neustart-sichere Persistenz.

Eine erkannte Fahrt speichert Start-/End-Kilometerstand, Strecke, Zeitstempel und — falls die SOC-Entität des Fahrzeugs verfügbar war — Start-/End-SOC sowie einen berechneten `verbrauch_kwh`-Wert (Energieverbrauch aus `delta_soc × nutzbare Akku-kWh`, auf ≥ 0 geklemmt). Start-/Zielort trägst du anschließend manuell über `ev_assistant.log_trip` nach, nach demselben Muster „automatisch erkennen, den menschlichen Teil manuell bestätigen" wie bei Fremdladungen. Es gibt bewusst **kein** Zweck-Feld (dienstlich/privat) und kein Kommentarfeld — das ist ein reines Strecken-/Ort-Log, kein Steuer-Compliance-Werkzeug.

**Optionaler Orts-Vorschlag:** konfigurierst du eine person- oder device_tracker-Entität (Schritt 6, z.B. das Handy des Fahrers), bekommt die offene Fahrt ein `start_ort_vorschlag`/`end_ort_vorschlag`-Attribut — die HA-Zone der Entität (z.B. „Home") zum Zeitpunkt von Fahrtbeginn/-ende. Das ist nur ein **Vorschlag zum Vorausfüllen**, kein automatischer Eintrag — `log_trip` erfordert weiterhin einen expliziten Aufruf. Blieb das Handy zuhause oder liegt die Fahrt außerhalb aller konfigurierten Zonen, gibt's einfach keinen Vorschlag statt eines falschen automatischen Eintrags.

| Sensor | Bedeutung |
|---|---|
| `binary_sensor … Fahrt Erfassung offen` | **An**, solange mindestens eine erkannte Fahrt auf Start-/Zielort wartet. Attribute analog zum Fremdladungs-Pendant (`anzahl_offen`, `offene_fahrten`). |
| `sensor … Fahrt Schätzung` | Strecke (km) der ältesten offenen Fahrt. `unknown`, wenn nichts offen ist. |
| `sensor … Fahrt km (letzte)` | Strecke der zuletzt bestätigten Fahrt, mit der vollständigen `fahrtenbuch`-Historie als Attribut. |
| `sensor … Fahrtenbuch Anzahl` | Wie viele Fahrten insgesamt bestätigt wurden. |
| `sensor … Fahrtenbuch km (gesamt)` | Laufende Summe aller bestätigten Fahrtstrecken (`total_increasing`). |
| `sensor … Fahrtenbuch Durchschnittsverbrauch` | Durchschnittlicher Verbrauch in kWh pro Fahrt, über alle Fahrten mit bekanntem Verbrauch — entweder direkt importiert (`verbrauch_kwh`) oder aus `delta_soc × nutzbare Akku-kWh` berechnet für erkannte Fahrten (auf ≥ 0 geklemmt, falls die Fahrt per saldo Energie zurückgewonnen hat). `unknown` ohne eine einzige Fahrt mit nutzbaren Verbrauchsdaten. |

`ev_assistant.export_fahrtenbuch` schreibt das komplette Fahrtenbuch (chronologisch, älteste zuerst) als Semikolon-getrennte CSV-Datei nach `www/ev_assistant_fahrtenbuch_<entry_id>.csv`, herunterladbar unter `/local/ev_assistant_fahrtenbuch_<entry_id>.csv` — praktisch für die Weiterverarbeitung (z.B. eine Steuererklärung) außerhalb von Home Assistant.

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): eine offene Ladung bestätigen und in die Historie schreiben. **Es können mehrere Ladungen gleichzeitig offen sein** (z.B. zwei Ladestopps auf einem Roadtrip, bevor du zum Bestätigen kommst) — `start_ts` wählt die gemeinte aus; ohne Angabe wird die älteste bestätigt (FIFO).
- `ev_assistant.discard_pending` — `config_entry_id` (+ optional `start_ts`): eine offene Ladung verwerfen (z.B. ein Fehlalarm — es war gar keine Fremdladung). Gleiche `start_ts`-Auswahlregel wie oben.
- `ev_assistant.edit_charge` — `config_entry_id`, `erfasst_ts`, `kwh`, `price_kwh`: korrigiert kWh/Preis eines bereits bestätigten Historien-Eintrags nachträglich (z.B. ein Tippfehler, der später auffällt), identifiziert über dessen `erfasst_ts`-Attribut (siehe das `historie`-Attribut am Kosten-Sensor, oder die Historie-Liste der [EV Assistant Card](https://github.com/weskona/ev-assistant-card)). Die laufenden Summen werden um die Differenz angepasst, nicht neu berechnet.
- `ev_assistant.delete_charge` — `config_entry_id`, `erfasst_ts`: löscht einen bereits bestätigten Historien-Eintrag vollständig (z.B. eine fälschlich erkannte Ladung, die gar keine Fremdladung war). Die laufenden Summen werden um den gelöschten Betrag verringert. **Nicht rückgängig zu machen.**
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): **Testereignis ohne Auto** erzeugen (löst Benachrichtigung und Sensoren aus) — siehe „Testen" unten.
- `ev_assistant.log_trip` — `config_entry_id`, `start_ort`, `end_ort` (+ optional `start_ts`): eine offene Fahrt mit Start-/Zielort bestätigen. Gleiche Mehrfach-/`start_ts`-Auswahlregel wie `log_charge`. Anders als `log_charge` gibt es **keinen** Fallback auf einen manuellen Einzeleintrag ohne offene Fahrt — Kilometerstand-Werte stammen ausschließlich aus der Erkennung.
- `ev_assistant.discard_pending_trip` — `config_entry_id` (+ optional `start_ts`): eine offene Fahrt verwerfen (z.B. ein kurzes Rangieren in der Einfahrt).
- `ev_assistant.export_fahrtenbuch` — `config_entry_id`: das komplette Fahrtenbuch als CSV nach `www/` schreiben (siehe „Fahrtenbuch" oben).
- `ev_assistant.simulate_trip` — `config_entry_id`, `km`: **Test-Fahrt ohne Auto** erzeugen, analog zu `simulate_event`.
- `ev_assistant.edit_trip` — `config_entry_id`, `erfasst_ts`, `start_ort`, `end_ort`: korrigiert Start-/Zielort eines bereits bestätigten Fahrtenbuch-Eintrags nachträglich (z.B. ein Tippfehler, der später auffällt), identifiziert über dessen `erfasst_ts`-Attribut. Kilometerstand/Strecke sind **nicht** editierbar — sie stammen ausschließlich aus der Erkennung.
- `ev_assistant.delete_trip` — `config_entry_id`, `erfasst_ts`: löscht einen bereits bestätigten Fahrtenbuch-Eintrag vollständig (z.B. eine fälschlich erkannte Fahrt). Die laufenden Summen werden um den gelöschten Betrag verringert. **Nicht rückgängig zu machen.**
- `ev_assistant.import_fahrtenbuch` — `config_entry_id`, `trips` (eine Liste): importiert historische Fahrten aus einer anderen Fahrtenbuch-App/einem Export in einem Rutsch, ohne die Kilometerstand-Erkennung. Je Eintrag: `start`/`ende` als lokale Zeit `"YYYY-MM-DD HH:MM:SS"`, `start_ort`, `ziel_ort`, `strecke` (km), optional `verbrauch_kwh`/`avg_verbrauch`/`avg_speed`. Kilometerstände bleiben leer (die Quelle liefert keine) — nur die Strecke wird erfasst. Importierte Einträge bekommen `quelle: "import"`; ein wiederholter Import überspringt bereits vorhandene Einträge (Dublettenerkennung über die Startzeit), ist also gefahrlos mehrfach aufrufbar. Akzeptiert sowohl eine reine Liste als auch direkt die komplette Quelldatei mit ihrem umschließenden `{"trips": [...]}`-Aufbau (häufiger Copy-Paste-Fall aus einem JSON-Export).

Alle Services benötigen `config_entry_id`, um bei mehreren EV-Assistant-Instanzen das richtige Fahrzeug anzusprechen.

### UI zur manuellen Eingabe (empfohlen: eigene Karte)

**[EV Assistant Card](https://github.com/weskona/ev-assistant-card)** ist eine eigens für diese Integration gebaute Lovelace-Karte — auf das Fahrzeug-Gerät zeigen, sie findet alle Sensoren selbst, zeigt bei offener Ladung ein direktes kWh/Preis-Formular und ruft die Services direkt mit der korrekten `config_entry_id` auf (keine Helfer-Entitäten oder Automationen nötig, funktioniert korrekt auch mit mehreren Fahrzeugen). Ersetzt das YAML-Package unten.

### UI zur manuellen Eingabe (Legacy, YAML-Package)

`packages/ev_assistant_ui.yaml` liefert zwei Eingabefelder + Speichern/Verwerfen-Buttons, die die obigen Services aufrufen; `packages/ev_assistant_karte.yaml` ist die passende Lovelace-Karte. Nach `config/packages/` kopieren (`homeassistant: packages: !include_dir_named packages`) und neu laden.

> **Bekannte Einschränkung:** Die Beispiel-Entity-IDs der Karte (z.B. `sensor.ev_assistant_letzte_kosten`) gehen vom alten, festen Gerätenamen „EV Assistant" aus — seit v0.4.0 heißt das Gerät wie dein Fahrzeug, daher die Entity-Liste der Karte an deine tatsächlichen Entity-IDs anpassen. Bei einer Neueinrichtung stattdessen gleich die [EV Assistant Card](https://github.com/weskona/ev-assistant-card) oben verwenden.

### Testen

**1) Logik (ohne HA):**
```bash
cd <repo>
python -m pytest tests -q
```
**2) Ende-zu-Ende in HA (ohne Auto):** Entwicklerwerkzeuge → Dienste → `ev_assistant.simulate_event` mit `config_entry_id`, `soc_start: 32`, `soc_end: 74` aufrufen. Erwartung: Benachrichtigung erscheint, `binary_sensor … Fremdladung Erfassung offen` = an, `sensor … Fremdladung Schätzung` ≈ 21,48 kWh (siehe durchgerechnetes Beispiel oben). Dann kWh/Preis eintragen und `ev_assistant.log_charge` (oder Speichern-Button) — Historie/Summen aktualisieren sich, Publish auf `ev_assistant/ladung/extern/<entry_id>/erfasst`.

**3) Fahrtenbuch, Ende-zu-Ende (ohne Auto):** `ev_assistant.simulate_trip` mit `config_entry_id`, `km: 12.5` aufrufen. Erwartung: Benachrichtigung erscheint, `binary_sensor … Fahrt Erfassung offen` = an, `sensor … Fahrt Schätzung` zeigt `12.5`. Dann `ev_assistant.log_trip` mit `start_ort`/`end_ort` aufrufen — `sensor … Fahrt km (letzte)` aktualisiert sich. Zuletzt `ev_assistant.export_fahrtenbuch` aufrufen und prüfen, dass `www/ev_assistant_fahrtenbuch_<entry_id>.csv` angelegt wurde.

### Datensatz (Historie)

Enthält bewusst **beides**: manuell `kwh`/`preis_kwh`/`kosten` **und** die Auto-`schaetzung_kwh` samt `quelle` (`soc`/`power_ac`/`power_dc`) — so siehst du über die Zeit, wie gut die Schätzung trifft, und kannst `charge_efficiency` nachziehen (oder die automatische Kalibrierung das übernehmen lassen).

### Struktur

```
custom_components/ev_assistant/
  __init__.py        # Setup, Services, Unload (reload-fähig)
  manifest.json
  const.py
  engine.py          # reine Logik (pytest) — ChargeDetector + EfficiencyCalibrator + TripDetector
  coordinator.py     # Entity-Verdrahtung, Erkennung, Kalibrierung, Persistenz, Notification
  config_flow.py     # Config- + Options-Flow (7 Schritte)
  entity.py          # gemeinsame Entity-Basis (Device-Gruppierung, fahrzeugbasierter Gerätename)
  sensor.py
  binary_sensor.py
  services.yaml
  strings.json
  translations/{de,en}.json
packages/            # optionales UI-Glue + Lovelace-Karte (siehe bekannte Einschränkung oben)
tests/               # pytest (engine.py)
```

### Anforderungen

- Home Assistant 2024.1+
- [`evcc_intg`](https://github.com/marq24/ha-evcc)-Integration installiert (Pflicht — evcc-Entitäten werden daraus automatisch erkannt)

---

## Lizenz / License

MIT © [weskona](https://github.com/weskona)
