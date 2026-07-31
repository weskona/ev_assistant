# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Version](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)

A comprehensive **EV monitoring integration for Home Assistant** — covering home charging (via evcc), external charge detection and logging, automatic trip logging, efficiency calibration, cost comparison vs. a combustion car, and a dedicated sidebar panel as a full EV dashboard. Manufacturer-independent: works with any HA entity source (WiCAN Pro, evcc/Warp, Stellantis/VW cloud sensors, ...).

**[🇩🇪 Deutsche Version weiter unten](#-deutsch)**

---

## 🇬🇧 English

### What EV Assistant does

EV Assistant brings together everything about your electric vehicle in one place:

- **Home charging monitoring** — tracks home-charged kWh and cost via your wallbox energy meter and evcc session history, displayed in the panel's Heimladen column with full session history, SOC bars, and solar share.
- **External charge detection** — automatically detects when you charged away from home (public charger, work, hotel) purely from SoC telemetry, no GPS or charger list needed. Prompts you to log the real kWh/price from the receipt.
- **Trip log** — automatically detects trips from your odometer sensor and lets you confirm start/end locations. CSV export included.
- **Efficiency calibration** — learns your car's real AC→battery charge efficiency from home sessions and applies it automatically to all estimates.
- **Cost comparison** — tracks what you've spent on home and external charging and compares it to the equivalent combustion car cost.
- **Dedicated sidebar panel** — a full EV dashboard built into Home Assistant's sidebar; no Lovelace card setup needed.

### Panel / EV Dashboard

EV Assistant registers a dedicated **"EV Assistant" sidebar panel** automatically — no extra configuration needed beyond the integration itself being set up.

The panel has two tabs:

**Übersicht** — live energy flow diagram showing current PV, grid, home, battery, and wallbox power. Shows the active charging session (mode, SOC, session energy, solar share, tariff) and pending charges/trips waiting for confirmation.

**Fahrzeuge** — per-vehicle EV dashboard in a three-column layout:

| Column | What it shows |
|---|---|
| **Heimladen** | Home charging totals (kWh, EUR, session count, avg. solar share), last session KPIs, and scrollable history from evcc's session log. Each history entry shows SOC start→end, kWh, EUR/kWh, total cost, solar share, duration, and a SOC progress bar. |
| **Fremdladung** | External charge totals, last session KPIs, and editable history with SOC bar per entry. |
| **Fahrtenbuch** | Trip totals, last trip KPIs (km, route), and editable trip history. |

At the top of the Fahrzeuge tab: a **vehicle card** showing the vehicle name, current SOC as a large number with a colour-coded bar (red < 20 %, orange < 40 %, green otherwise), odometer, charge efficiency, and estimated savings vs. combustion.

If you run EV Assistant for **multiple vehicles**, pill-style tabs appear to switch between them — each tab has its own complete dashboard.

Cards are colour-coded after the HA Energy Dashboard palette: PV amber (`#ff9800`) for home charging, grid blue (`#488fc2`) for external charges, teal (`#14b8a6`) for the trip log.

### How external charge detection works

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
7. A few days later the receipt arrives: **21.4 kWh** actually billed at **0.59 EUR/kWh** = **12.63 EUR**. You call `ev_assistant.log_charge` (or use the panel) with these real numbers.
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

Settings → Devices & Services → **Add integration** → "EV Assistant". Setup is a 9-step flow (also used identically when editing via **Configure**):

1. **Vehicle** — Manufacturer + model (required, e.g. "Peugeot" / "e-2008" — together they become the HA device name), first registration date (optional, display only), odometer entity (optional, filtered to `sensor` + `device_class: distance` — mirrored onto the EV Assistant device as its own `... Odometer` sensor, and used both as the basis for automatic trip detection (trip log, step 6) and as the distance basis for the cost comparison in step 7), usable battery capacity in kWh (required — the *net* value your car can actually use, not the often-larger gross/factory figure some manufacturers advertise; this directly determines how many kWh one percentage point of SoC represents, so getting it wrong throws off every energy estimate), charge efficiency (optional starting value only — replaced automatically once enough real home charges have been measured, see calibration below).
2. **Basic signals** — SoC and home-charging source, each as an **HA entity**. At least one source per signal is required (marked with `*`). The SoC entity picker is filtered to `sensor` + `device_class: battery`; the home-charging entity picker to `sensor` + `device_class: power` (e.g. a wallbox's charging-power sensor from evcc/Warp) — a numeric value **above 0.1 kW counts as "charging"**; a non-numeric value (e.g. evcc's own `"charging"`/`"on"` status string) falls back to a plain text match instead. **This is a yes/no "charging at home right now" signal only** — it is not the same charging-power reading as step 3 (that one deliberately comes from the vehicle, not the wallbox, so it still works away from home during an external charge). If your power sensor reports a different unit (e.g. Watts), convert it with the template field, e.g. `{{ value | float / 1000 }}`.
3. **Charging power** (optional) — two different sources for two different purposes. Charging power is a momentary power reading in W/kW, typically from vehicle telemetry rather than your wallbox (so it still reports data during an external charge, where the wallbox is idle); it improves the energy estimate of an external charge beyond plain SoC-delta (see "Energy estimation methods" above). The **wallbox energy meter**, on the other hand, is a cumulative kWh counter of your own wallbox (never momentary, only relevant while charging at home) — it's used for automatic efficiency calibration *and* for the home-charging cost tracked in step 9.
4. **Output** (optional) — a persistent notification in Home Assistant's own notification panel always appears automatically for a detected charge, regardless of this step. The `notify.*` service additionally sends a push notification (e.g. to your phone).
5. **Detection fine-tuning** — thresholds of the underlying state machine described above (`start_delta`, `noise`, `idle_timeout_s`, `drop_ends`). A session starts once SoC rises by `start_delta` above its last resting value; it ends either when SoC drops by more than `drop_ends` below the tracked peak, or when `idle_timeout_s` passes with no new peak (e.g. battery full). `noise` tolerates ordinary sensor jitter while tracking the peak and must always be **smaller** than `start_delta`, or jitter alone could trigger a false detection. Defaults work for most vehicles; raise them for a car whose SoC only updates coarsely/infrequently (e.g. some cloud APIs).
6. **Trip log** (optional) — thresholds of the trip detector (`trip_min_km`, `trip_idle_timeout_s`) described in "Trip log" below. Defaults work for most odometer sensors. Also an optional location-suggestion source (`gps_entity`, a `person`/`device_tracker`).
7. **Cost comparison** (optional) — see "Cost comparison vs. a combustion car" below.
8. **Wallbox (evcc)** — live loadpoint state from evcc for this vehicle's charge point (power, status, mode, phases, vehicle SoC, limit SoC, session energy/solar/price, duration). Used for the live energy flow panel.
9. **evcc (site-wide)** — data that applies to the whole evcc installation (PV/grid/home-battery power, tariffs, all-time statistics, evcc vehicle name for the panel's Heimladen filter).

### Sources: manufacturer-independent

Each signal is fed from an **HA entity** (e.g. a manufacturer integration) — works with any manufacturer that exposes an SoC sensor in HA.

- **WiCAN Pro (MQTT→HA):** SoC topic exposed as HA sensor via the `mqtt` integration.
- **Stellantis / VW / ... (entity):** SoC entity = `sensor.<car>_battery`. Cloud SoC is often coarse/infrequent — raise `start_delta` and `idle_timeout_s` accordingly.
- **evcc:** Use evcc's vehicle SoC sensor entity for the SoC input; use a wallbox power sensor for the home-charging signal.

An optional Jinja template per signal converts the raw value (`value` = state).

### Automatic charge-efficiency calibration

Instead of a fixed manual efficiency value, EV Assistant can learn the real AC→battery efficiency from your own home-charging sessions — no external charge is involved in this at all, it's purely about how efficiently *your car* converts grid power into stored battery energy while charging at home.

**How it works:** configure a **wallbox energy meter** in step 3 — a cumulative kWh counter that only ever counts up (like a normal utility meter), not a "session energy" value that resets. Every time the home-charging signal switches on, EV Assistant remembers the current SoC and the current wallbox meter reading. When home-charging switches off again, it compares the SoC gained against the wallbox energy consumed for that same session, and calculates the efficiency:

`efficiency = (soc_gained% × usable_kWh) ÷ wallbox_energy_delta_kWh`

**Worked example:** your wallbox meter reads **100.0 kWh** when a home charge starts, and **120.2 kWh** when it ends — so **20.2 kWh** of AC energy was drawn from the grid. Over the same session, SoC went from **30 %** to **68 %**, a gain of 38 percentage points. With a 45 kWh usable battery, that's `38% × 45 kWh = 17.1 kWh` that actually went into the battery. The measured efficiency for this one session is `17.1 ÷ 20.2 ≈ 0.847` (84.7 %).

A single session isn't trusted blindly — implausible samples are discarded automatically (session too short: less than 5 percentage points of SoC gain; missing data; or a result outside the 50–100 % plausible range, which usually means a meter reset or a missed reading happened). Once **3 valid sessions** have been collected, EV Assistant averages the last 10 samples and **automatically starts using that measured value** for every calculation from then on — live, without a restart. If your car's real efficiency is, say, 0.847, 0.86, and 0.855 across three sessions, the new value in use becomes their average, **0.854 (85.4 %)** — replacing whichever value you originally typed in during setup.

The manual value from step 1 remains the fallback the whole time until enough sessions exist. See sensor `... Charge Efficiency (Measured)` below for the live status.

### Cost comparison vs. a combustion car

All fields in step 7 are optional — configure as many or as few as you like; the sensors below simply show `unknown` until their required inputs are available.

**Distance driven:** the odometer entity from step 1 is read once at first startup and remembered as a reference point. "km driven" is always `current odometer − that reference value` — so the comparison covers everything from when you configured EV Assistant onward, not the car's full lifetime mileage.

**Home-charging cost:** the wallbox energy meter from step 3 (the same cumulative counter used for efficiency calibration) is read the same way — first-seen value as reference, current value minus that reference gives total home-charged kWh. Multiplied by the home electricity price, that's your estimated home-charging spend. The price can be a fixed value (`home_price_kwh`) or a live entity (`home_price_entity`, e.g. a dynamic-tariff sensor) — if both are set, the entity wins, and its last known good value is remembered across restarts/outages. Without a wallbox meter configured, home-charging cost is simply treated as 0 — the comparison still works using only the (always-tracked) external-charging costs.

**Combustion reference:** `(km driven ÷ 100) × verbrenner_l_100km × verbrenner_price_per_liter` — a straightforward "what would this distance have cost in fuel" estimate for the comparison vehicle you describe. The fuel price can also be linked to a live entity (e.g. a fuel-price tracker sensor) instead of typing in a fixed value — if both are set, the entity wins. Its last known good value is remembered and keeps being used if the entity ever goes `unavailable` (including across restarts), so the comparison doesn't silently drop out.

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
| `sensor ... Home Charging Cost (Total)` | Home-charging kWh above × the home electricity price from step 7 (fixed value or live entity, see above). `unknown` without a configured meter or price. |
| `sensor ... Savings vs. Combustion Car` | Estimated savings vs. the reference combustion car from step 7, over the distance driven since setup (see "Cost comparison" above). `unknown` until the odometer entity, combustion consumption, and fuel price are all configured. Attributes: `gefahrene_km`, `heimladen_kosten`, `fremdladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live` (whether the fuel-price entity is currently overriding its fixed value), `heimstrompreis_live` (same, for the home electricity price). |

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

A detected trip only records start/end odometer, distance, and timestamps — you then confirm it manually with a start/end location via `ev_assistant.log_trip`, the same "detect automatically, confirm the human part manually" pattern as external charges. There is deliberately **no** business/private purpose field or comment field — this is a plain distance/location log, not a tax-compliance tool.

**Optional location suggestion:** configure a `person` or `device_tracker` entity (step 6, e.g. the driver's phone) and the pending trip gets a `start_ort_vorschlag`/`end_ort_vorschlag` attribute — the entity's HA zone (e.g. "Home") at the moment the trip started/ended. This is a **prefill suggestion only**, not an automatic entry — `log_trip` still requires an explicit call, so a phone that stayed home or a trip outside any configured zone just means an empty suggestion, not a wrong automatic log entry.

| Sensor | Meaning |
|---|---|
| `binary_sensor ... Trip Detection Open` | **On** while at least one detected trip is waiting for a start/end location. Attributes analogous to the charge-pending binary sensor (`anzahl_offen`, `offene_fahrten`). |
| `sensor ... Trip Estimate` | Distance (km) of the oldest pending trip. `unknown` when nothing is pending. |
| `sensor ... Trip km (Last)` | Distance of the most recently confirmed trip, with the full `fahrtenbuch` history as an attribute. |
| `sensor ... Trip Log Count` | How many trips have been confirmed in total. |
| `sensor ... Trip Log km (Total)` | Running total of all confirmed trip distances (`total_increasing`). |

`ev_assistant.export_fahrtenbuch` writes the full trip history (chronological, oldest first) as a semicolon-separated CSV to `www/ev_assistant_fahrtenbuch_<entry_id>.csv`, downloadable at `/local/ev_assistant_fahrtenbuch_<entry_id>.csv` — handy for further processing (e.g. a tax filing) outside Home Assistant.

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): confirm a pending charge and write it to history. **More than one charge can be pending at once** (e.g. two charging stops on a road trip before you get around to confirming either) — `start_ts` picks which one; without it, the oldest is confirmed (FIFO).
- `ev_assistant.discard_pending` — `config_entry_id` (+ optional `start_ts`): discard a pending charge (e.g. a false positive — it wasn't actually an external charge). Same `start_ts` selection rule as above.
- `ev_assistant.edit_charge` — `config_entry_id`, `erfasst_ts`, `kwh`, `price_kwh`: correct the kWh/price of an already-confirmed history entry (e.g. a typo noticed after the fact), identified by its `erfasst_ts` attribute (see the `historie` attribute on the last-cost sensor, or the panel's History list). Running totals are adjusted by the difference, not recomputed from scratch.
- `ev_assistant.delete_charge` — `config_entry_id`, `erfasst_ts`: fully removes an already-confirmed history entry (e.g. a falsely detected charge that wasn't actually external). Running totals are adjusted by the removed amount. **Not reversible.**
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): generate a **test event without a car** (triggers notification, sensors) — see "Testing" below.
- `ev_assistant.log_trip` — `config_entry_id`, `start_ort`, `end_ort` (+ optional `start_ts`): confirm a pending trip with a start/end location. Same multiple-pending/`start_ts` selection rule as `log_charge`. Unlike `log_charge`, there is **no** fallback to a manual one-off entry without a pending trip — odometer values only ever come from the detector.
- `ev_assistant.discard_pending_trip` — `config_entry_id` (+ optional `start_ts`): discard a pending trip (e.g. moving the car a few meters in the driveway).
- `ev_assistant.export_fahrtenbuch` — `config_entry_id`: write the full trip history as CSV to `www/` (see "Trip log" above).
- `ev_assistant.simulate_trip` — `config_entry_id`, `km`: generate a **test trip without a car**, same idea as `simulate_event`.
- `ev_assistant.edit_trip` — `config_entry_id`, `erfasst_ts`, `start_ort`, `end_ort`: correct the start/end location of an already-confirmed trip log entry (e.g. a typo noticed after the fact), identified by its `erfasst_ts` attribute. Distance/odometer values are **not** editable — they only ever come from the detector.
- `ev_assistant.delete_trip` — `config_entry_id`, `erfasst_ts`: fully removes an already-confirmed trip log entry (e.g. a falsely detected trip). Running totals are adjusted by the removed amount. **Not reversible.**

All services require `config_entry_id` to target a specific vehicle if you run more than one EV Assistant instance.

### Manual-entry UI (recommended: sidebar panel)

The **EV Assistant sidebar panel** (registered automatically) provides a full in-HA UI for confirming pending charges and trips, editing/deleting history, and viewing all stats and session history per vehicle. No extra setup needed.

**[EV Assistant Card](https://github.com/weskona/ev-assistant-card)** is an alternative custom Lovelace card built specifically for this integration — point it at your vehicle's device and it finds all sensors itself.

### Testing

**1) Logic only (no HA):**
```bash
cd <repo>
python -m pytest tests -q
```
**2) End-to-end in HA (no car needed):** Developer tools → Services → call `ev_assistant.simulate_event` with `config_entry_id`, `soc_start: 32`, `soc_end: 74`. Expect: a notification appears, `binary_sensor ... External Charge Detection Open` turns on, `sensor ... External Charge Estimate` ≈ 21.48 kWh (see the worked example above). Then enter kWh/price in the panel — history/totals update.

**3) Trip log, end-to-end (no car needed):** call `ev_assistant.simulate_trip` with `config_entry_id`, `km: 12.5`. Expect: a notification appears, `binary_sensor ... Trip Detection Open` turns on, `sensor ... Trip Estimate` shows `12.5`. Then call `ev_assistant.log_trip` with `start_ort`/`end_ort` — `sensor ... Trip km (Last)` updates. Finally call `ev_assistant.export_fahrtenbuch` and check `www/ev_assistant_fahrtenbuch_<entry_id>.csv` was created.

### Data record (history / `.../erfasst`)

Deliberately contains **both** the manually entered `kwh`/`preis_kwh`/`kosten` **and** the automatic `schaetzung_kwh` plus its `quelle` (`soc`/`power_ac`/`power_dc`) — so you can see over time how close the estimate gets, and adjust `charge_efficiency` accordingly (or just let the automatic calibration handle it).

### Structure

```
custom_components/ev_assistant/
  __init__.py        # setup, services, unload, panel registration (reload-capable)
  manifest.json
  const.py
  engine.py           # pure logic (pytest-testable) — ChargeDetector + EfficiencyCalibrator + TripDetector
  coordinator.py      # entity wiring, detection, calibration, persistence, notification
  config_flow.py      # config + options flow (9 steps)
  entity.py           # shared entity base (device grouping, vehicle-based device name)
  sensor.py
  binary_sensor.py
  services.yaml
  strings.json
  translations/{de,en}.json
  frontend/           # sidebar panel (ev-assistant-panel.js)
packages/             # optional legacy UI glue + Lovelace card
tests/                # pytest (engine.py)
```

### Requirements

- Home Assistant 2024.1+

---

## 🇩🇪 Deutsch

### Was EV Assistant macht

EV Assistant bringt alles rund um dein Elektroauto an einem Ort zusammen:

- **Heimladen-Monitoring** — erfasst zuhause geladene kWh und Kosten über deinen Wallbox-Energiezähler und die evcc-Ladehistorie, dargestellt im Panel mit vollständiger Session-Historie, SOC-Balken und Solaranteil.
- **Fremdladung-Erkennung** — erkennt automatisch, wenn du unterwegs geladen hast (Ladesäule, Arbeit, Hotel), rein aus der SoC-Telemetrie — kein GPS, keine Stationsliste nötig. Fordert dich dann auf, die echten kWh/den Preis vom Beleg einzutragen.
- **Fahrtenbuch** — erkennt Fahrten automatisch aus dem Kilometerstand-Sensor und lässt dich Start-/Zielort bestätigen. CSV-Export inklusive.
- **Wirkungsgrad-Kalibrierung** — lernt den echten AC→Batterie-Ladewirkungsgrad deines Autos aus Heim-Sessions und wendet ihn automatisch auf alle Schätzungen an.
- **Kostenvergleich** — verfolgt deine Heim- und Fremdladungskosten und vergleicht sie mit den Kosten eines Verbrenners.
- **Eigenes Sidebar-Panel** — ein vollwertiges EV-Dashboard, direkt in die HA-Sidebar integriert; keine Lovelace-Karte nötig.

### Panel / EV-Dashboard

EV Assistant registriert automatisch ein **„EV Assistant"-Sidebar-Panel** — keine Extra-Konfiguration nötig, sobald die Integration eingerichtet ist.

Das Panel hat zwei Tabs:

**Übersicht** — Live-Energieflussdiagramm mit aktueller PV-, Netz-, Haus-, Batterie- und Wallbox-Leistung. Zeigt die laufende Ladeession (Modus, SOC, Session-Energie, Solaranteil, Tarif) und offene Ladungen/Fahrten, die auf Bestätigung warten.

**Fahrzeuge** — Fahrzeug-Dashboard pro Fahrzeug in drei Spalten:

| Spalte | Inhalt |
|---|---|
| **Heimladen** | Heimlade-Gesamtwerte (kWh, EUR, Anzahl Sessions, Ø Solaranteil), KPIs der letzten Session und scrollbare Historie aus dem evcc-Ladelogbuch. Jeder Eintrag zeigt SOC Start→Ende, kWh, EUR/kWh, Gesamtkosten, Solaranteil, Dauer und einen SOC-Fortschrittsbalken. |
| **Fremdladung** | Fremdladungs-Gesamtwerte, KPIs der letzten Ladung und bearbeitbare Historie mit SOC-Balken pro Eintrag. |
| **Fahrtenbuch** | Fahrten-Gesamtwerte, KPIs der letzten Fahrt (km, Route) und bearbeitbare Fahrtenhistorie. |

Oberhalb der drei Spalten: eine **Fahrzeugkarte** mit Fahrzeugname, aktuellem SOC als große Zahl mit farbcodiertem Balken (rot < 20 %, orange < 40 %, grün sonst), Kilometerstand, Ladewirkungsgrad und geschätzter Ersparnis ggü. Verbrenner.

Bei **mehreren konfigurierten Fahrzeugen** erscheinen Pill-Tabs zum Umschalten — jeder Tab hat sein eigenes vollständiges Dashboard.

Karten sind nach der HA-Energiedashboard-Farbpalette eingefärbt: PV-Amber (`#ff9800`) für Heimladen, Grid-Blau (`#488fc2`) für Fremdladung, Teal (`#14b8a6`) für das Fahrtenbuch.

### Funktionsweise der Fremdladung-Erkennung

EV Assistant braucht kein GPS, keine herstellerspezifische API und keine Liste bekannter Ladestationen. Es funktioniert allein mit zwei Werten, die ohnehin schon aus Auto und Zuhause vorliegen:

1. **Ladezustand (SoC)** — der Akku-Prozentwert, z.B. aus einem Hersteller-Cloud-Sensor oder einem günstigen OBD-Dongle wie WiCAN Pro.
2. **Heim-Laden-Signal** — irgendetwas, das dir sagt "das Auto lädt gerade an meiner eigenen Wallbox" (z.B. von evcc, einer Warp-Box, oder einer beliebigen Ladebox-Integration).

Der Grundgedanke lässt sich in einem Satz zusammenfassen: **Wenn der Akkuprozentwert steigt, während das Heim-Laden-Signal "nein" sagt, muss das Auto woanders laden** — an einer öffentlichen Ladesäule, im Hotel, bei Freunden, auf der Arbeit. Das ist eine „Fremdladung". Heim-Laden wird von der Erkennung bewusst ignoriert — das trackst du ohnehin schon über deine eigene Wallbox/evcc-Anbindung, EV Assistant meldet sich also nur bei Ladungen, die du *sonst nicht mitbekommen würdest*.

Intern beobachtet eine kleine Zustandsmaschine (`engine.py::ChargeDetector`) jeden neuen SoC-Wert:

- **Ruhezustand** — es passiert nichts. Der niedrigste zuletzt gesehene SoC-Wert wird gemerkt (der „Anker"). Sinkt der SoC wieder ab (oder ist das Heim-Laden-Signal aktiv), wird der Anker zurückgesetzt. Der Anker steht also immer für „der Ladestand kurz bevor irgendetwas als Nächstes passiert".
- **Beginn einer Session** — sobald der SoC um mindestens `start_delta` (Standard **1 %**) über den Anker gestiegen ist, *während* Heim-Laden aus ist, beginnt eine Fremdladung. Offizieller Startpunkt ist der Anker (der letzte bekannte Tiefpunkt), nicht der Moment, in dem die Schwelle überschritten wurde — so wird auch das allererste bisschen Ladung korrekt mitgezählt.
- **Laufende Session** — solange der SoC weiter steigt, merkt sich EV Assistant den höchsten bisher gesehenen Wert („Peak"). Eine kleine `noise`-Toleranz (Standard **0,5 %**) fängt Sensor-Rauschen ab. `start_delta` sollte **größer** als `noise` sein — sind beide gleich, kann normales Rauschen bereits eine Erkennung auslösen.
- **Ende einer Session** — je nachdem, was zuerst eintritt:
  - das Heim-Laden-Signal wird aktiv (du bist zuhause angekommen und hast eingesteckt), oder
  - der SoC fällt um mehr als `drop_ends` (Standard **1 %**) unter den Peak (du hast abgesteckt und bist losgefahren), oder
  - `idle_timeout_s` (Standard **600 s / 10 Minuten**) vergeht ohne weiteren SoC-Anstieg.

### Erkennungs-Ablauf — ein durchgerechnetes Beispiel

Angenommen dein Auto hat einen nutzbaren Akku von 45 kWh und den Standard-Ladewirkungsgrad von 88 %. Du fährst mit 32 % Akkustand von zuhause weg und steckst an einer öffentlichen Ladesäule ein.

1. Letzte SoC-Werte lagen konstant bei 32 % mit Heim-Laden aus. Der Anker steht bei **32 %**.
2. Nächster SoC-Wert: **35 %**. Das sind +3 Prozentpunkte über dem Anker — Schwelle erreicht, Fremdladung **beginnt** ab `soc_start = 32 %`.
3. SoC steigt weiter: 40 %, 55 %, 68 %, 74 %. Jeder neue Höchstwert wird als Peak gemerkt.
4. Du steckst bei **74 %** ab. Zehn Minuten ohne weiteren Anstieg — `idle_timeout_s` greift, Session **endet**.
5. Delta = 42 Prozentpunkte. Schätzung: `42 % × 45 kWh = 18,9 kWh` Batterie; `18,9 ÷ 0,88 = 21,48 kWh` abgerechnet.
6. Benachrichtigung, offene Ladung im Panel; `binary_sensor … Fremdladung Erfassung offen` = an.
7. Beleg kommt: **21,4 kWh** zu **0,59 EUR/kWh** = **12,63 EUR**. Im Panel bestätigen.
8. Historieneintrag mit Schätzung + echten Werten, Summen aktualisiert, Benachrichtigung weg.

### Energie-Schätzmethoden

| Quelle | Wann verwendet | Berechnung |
|---|---|---|
| `soc` | Kein Fahrzeug-Ladeleistungssensor konfiguriert | `Batterie-kWh = SoC-Delta% × nutzbare kWh`; `AC-kWh = Batterie-kWh ÷ Ladewirkungsgrad` |
| `power_ac` | Fahrzeug-Ladeleistungssensor, AC-seitig (Standard) | `AC-kWh` = Leistungswerte über die Zeit integriert (Trapezregel) |
| `power_dc` | Fahrzeug-Ladeleistungssensor, DC-seitig | `Batterie-kWh` = integriert; `AC-kWh = Batterie-kWh ÷ Ladewirkungsgrad` |

### Installation

**Über HACS**
1. HACS → Integrationen → ⋮ → **Benutzerdefinierte Repositories**
2. URL: `https://github.com/weskona/ev_assistant` — Kategorie: **Integration**
3. EV Assistant installieren, Home Assistant neu starten

**Manuell**
1. Ordner `custom_components/ev_assistant/` nach `config/custom_components/` kopieren
2. Home Assistant neu starten

### Konfiguration

Einstellungen → Geräte & Dienste → **Integration hinzufügen** → „EV Assistant". Die Einrichtung läuft in 9 Schritten (identisch auch beim Bearbeiten über **Konfigurieren**):

1. **Fahrzeug** — Hersteller + Modell (Pflicht), Erstzulassung (optional), Kilometerstand-Entität (optional), nutzbare Akku-Kapazität in kWh (Pflicht), Ladewirkungsgrad (Startwert — wird automatisch kalibriert).
2. **Grundsignale** — SoC-Entität (gefiltert auf `sensor` + `device_class: battery`) und Heim-Laden-Signal (gefiltert auf `sensor` + `device_class: power`, Zahlenwert > 0,1 kW = „lädt").
3. **Ladeleistung** (optional) — Fahrzeug-Ladeleistungssensor (verbessert Fremdladungs-Schätzung) und Wallbox-Energiezähler (für Wirkungsgrad-Kalibrierung und Heimladen-Kosten).
4. **Ausgabe** (optional) — zusätzlicher `notify.*`-Dienst für Push-Benachrichtigungen.
5. **Erkennungs-Feinjustierung** — `start_delta`, `noise`, `idle_timeout_s`, `drop_ends`. Standardwerte passen für die meisten Fahrzeuge; bei grob/selten aktualisierendem SoC großzügiger einstellen.
6. **Fahrtenbuch** (optional) — `trip_min_km`, `trip_idle_timeout_s`, optionale `gps_entity` für Orts-Vorschläge.
7. **Kostenvergleich** (optional) — Verbrenner-Verbrauch, Kraftstoffpreis, Heimstrompreis (je fester Wert oder Live-Entität).
8. **Wallbox (evcc)** — Live-Ladepunkt-Daten für dieses Fahrzeug (Leistung, Status, Modus, Phasen, SOC, Limit-SOC, Session-Energie/Solar/Preis, Dauer).
9. **evcc (gesamt)** — Anlage-weite evcc-Daten (PV/Netz/Batterie-Leistung, Tarife, Statistiken, evcc-Fahrzeugname für den Heimladen-Filter im Panel).

### Quellen: herstellerunabhängig

Jedes Signal wird aus einer **HA-Entität** gespeist — funktioniert mit jedem Hersteller, der einen SoC-Sensor in HA bereitstellt.

- **WiCAN Pro:** SoC über die `mqtt`-Integration als HA-Sensor exponieren.
- **Stellantis / VW / …:** SoC-Entität = `sensor.<auto>_battery`. Bei grob/selten aktualisierendem Cloud-SoC `start_delta` und `idle_timeout_s` erhöhen.
- **evcc:** evcc-Fahrzeug-SOC-Sensor als SoC-Entität; Wallbox-Leistungssensor als Heim-Laden-Signal.

Ein optionales Jinja-Template pro Signal rechnet den Rohwert um (`value` = Zustand).

### Automatische Ladewirkungsgrad-Kalibrierung

Statt eines festen manuellen Werts kann EV Assistant den echten Ladewirkungsgrad (AC→Batterie) aus deinen eigenen Heim-Ladesessions lernen.

**Wie es funktioniert:** Wallbox-Energiezähler in Schritt 3 hinterlegen — ein kumulativer kWh-Zähler, der nur hochzählt. Bei jedem Heim-Laden-Start merkt sich EV Assistant SoC und Zählerstand; beim Ende wird der Wirkungsgrad berechnet:

`Wirkungsgrad = (SoC-Gewinn% × nutzbare kWh) ÷ Wallbox-Energie-Delta-kWh`

Unplausible Stichproben werden automatisch verworfen (< 5 Prozentpunkte SoC-Gewinn; außerhalb 50–100 %). Sobald **3 gültige Sessions** gesammelt wurden, mittelt EV Assistant die letzten 10 Stichproben und verwendet diesen Wert automatisch — live, ohne Neustart.

### Kostenvergleich gegenüber einem Verbrenner

Alle Felder in Schritt 7 sind optional.

**Gefahrene Strecke:** `aktueller Kilometerstand − Referenzwert beim ersten Start`.

**Heimladen-Kosten:** `Wallbox-Delta-kWh × Heimstrompreis` (fester Wert oder Live-Entität).

**Verbrenner-Referenz:** `(gefahrene km ÷ 100) × verbrenner_l_100km × verbrenner_price_per_liter`.

**Durchgerechnetes Beispiel:** 1.000 km gefahren, 150 kWh zu Hause geladen à 0,30 EUR/kWh = 45,00 EUR, Fremdladungen 50,00 EUR gesamt = 95,00 EUR EV-Kosten. Verbrenner: 6,5 L/100km à 1,75 EUR/L = 113,75 EUR. Ersparnis: **18,75 EUR**.

### Sensoren im Detail

Das HA-Gerät heißt wie das Fahrzeug (`{Hersteller} {Modell}`), Entitäten erscheinen als `{Gerät} {Entität}`.

| Sensor | Bedeutung |
|---|---|
| `binary_sensor … Fremdladung Erfassung offen` | **An**, solange mindestens eine erkannte Fremdladung auf Bestätigung wartet. Attribute: `anzahl_offen`, `offene_ladungen`. |
| `sensor … Fremdladung Schätzung` | Geschätzte kWh der aktuell offenen Ladung. `unknown` wenn nichts offen. |
| `sensor … Fremdladung kWh (letzte)` | kWh-Wert der zuletzt bestätigten Fremdladung (vom Beleg). |
| `sensor … Fremdladung Kosten (letzte)` | `kwh × preis_kwh` der zuletzt bestätigten Ladung. |
| `sensor … Fremdladung Preis (letzter)` | Preis pro kWh der zuletzt bestätigten Ladung. |
| `sensor … Fremdladung Ladezeit (letzte)` | Dauer der erkannten Ladesession in Minuten. |
| `sensor … Fremdladung kWh (gesamt)` | Laufende Summe aller bestätigten Fremdladungs-kWh (`total_increasing`). |
| `sensor … Fremdladung Kosten (gesamt)` | Laufende Summe aller Fremdladungskosten. |
| `sensor … Fremdladung Anzahl` | Anzahl bestätigter Fremdladungen. |
| `sensor … Ladewirkungsgrad (gemessen)` (Diagnose) | Live-kalibrierter Wirkungsgrad aus Heim-Sessions. Attribute: `anzahl_sessions`, `benoetigte_sessions`, `einzelwerte_prozent`, `wird_verwendet`, `manueller_wert_prozent`. |
| `sensor … Kilometerstand` (Diagnose) | Spiegelt die Kilometerstand-Entität. |
| `sensor … Erstzulassung` (Diagnose) | Erstzulassungsdatum als `date`-Sensor. |
| `sensor … Heimladen kWh (gesamt)` | Gesamte zuhause geladene kWh seit Einrichtung. |
| `sensor … Heimladen Kosten (gesamt)` | Heimladen-kWh × Heimstrompreis. |
| `sensor … Ersparnis ggü. Verbrenner` | Geschätzte Ersparnis gegenüber dem Vergleichs-Verbrenner. Attribute: `gefahrene_km`, `heimladen_kosten`, `fremdladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live`, `heimstrompreis_live`. |

### Fahrtenbuch

Fahrten werden automatisch aus der Kilometerstand-Entität erkannt — kein GPS nötig. Eine Fahrt ist die Strecke zwischen zwei Standzeiten. Erkannte Fahrten unter der Mindest-Strecke werden verworfen.

Eine erkannte Fahrt speichert nur Start-/End-Kilometerstand, Strecke und Zeitstempel — Start-/Zielort trägst du manuell über `ev_assistant.log_trip` nach. Kein Zweck-Feld, kein Kommentarfeld — reines Strecken-/Ort-Log.

**Optionaler Orts-Vorschlag:** `person`- oder `device_tracker`-Entität konfigurieren (Schritt 6) → offene Fahrt bekommt `start_ort_vorschlag`/`end_ort_vorschlag` aus der HA-Zone des Geräts beim Fahrtstart/-ende. Nur ein Vorschlag, kein automatischer Eintrag.

| Sensor | Bedeutung |
|---|---|
| `binary_sensor … Fahrt Erfassung offen` | **An**, solange mindestens eine erkannte Fahrt auf Start-/Zielort wartet. |
| `sensor … Fahrt Schätzung` | Strecke (km) der ältesten offenen Fahrt. |
| `sensor … Fahrt km (letzte)` | Strecke der zuletzt bestätigten Fahrt, mit `fahrtenbuch`-Attribut. |
| `sensor … Fahrtenbuch Anzahl` | Anzahl bestätigter Fahrten. |
| `sensor … Fahrtenbuch km (gesamt)` | Laufende Summe aller Fahrtstrecken (`total_increasing`). |

`ev_assistant.export_fahrtenbuch` schreibt das komplette Fahrtenbuch als CSV nach `www/ev_assistant_fahrtenbuch_<entry_id>.csv`.

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): offene Ladung bestätigen.
- `ev_assistant.discard_pending` — `config_entry_id` (+ optional `start_ts`): offene Ladung verwerfen.
- `ev_assistant.edit_charge` — `config_entry_id`, `erfasst_ts`, `kwh`, `price_kwh`: bestätigten Eintrag korrigieren.
- `ev_assistant.delete_charge` — `config_entry_id`, `erfasst_ts`: bestätigten Eintrag löschen. **Nicht rückgängig.**
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): Testereignis ohne Auto.
- `ev_assistant.log_trip` — `config_entry_id`, `start_ort`, `end_ort` (+ optional `start_ts`): offene Fahrt bestätigen.
- `ev_assistant.discard_pending_trip` — `config_entry_id` (+ optional `start_ts`): offene Fahrt verwerfen.
- `ev_assistant.export_fahrtenbuch` — `config_entry_id`: Fahrtenbuch als CSV schreiben.
- `ev_assistant.simulate_trip` — `config_entry_id`, `km`: Test-Fahrt ohne Auto.
- `ev_assistant.edit_trip` — `config_entry_id`, `erfasst_ts`, `start_ort`, `end_ort`: Fahrtenbuch-Eintrag korrigieren.
- `ev_assistant.delete_trip` — `config_entry_id`, `erfasst_ts`: Fahrtenbuch-Eintrag löschen. **Nicht rückgängig.**

Alle Services benötigen `config_entry_id` für die Fahrzeugauswahl bei mehreren Instanzen.

### UI zur manuellen Eingabe

Das **EV-Assistant-Sidebar-Panel** (automatisch registriert) bietet eine vollständige HA-UI zum Bestätigen offener Ladungen/Fahrten, Bearbeiten/Löschen der Historie und Anzeigen aller Statistiken.

**[EV Assistant Card](https://github.com/weskona/ev-assistant-card)** ist eine alternative Lovelace-Karte.

### Testen

**1) Logik (ohne HA):**
```bash
cd <repo>
python -m pytest tests -q
```
**2) Ende-zu-Ende in HA (ohne Auto):** `ev_assistant.simulate_event` mit `config_entry_id`, `soc_start: 32`, `soc_end: 74` aufrufen. Erwartung: Benachrichtigung, `binary_sensor … Fremdladung Erfassung offen` = an, `sensor … Fremdladung Schätzung` ≈ 21,48 kWh. Im Panel bestätigen.

**3) Fahrtenbuch (ohne Auto):** `ev_assistant.simulate_trip` mit `config_entry_id`, `km: 12.5` aufrufen. Im Panel bestätigen, dann `export_fahrtenbuch` prüfen.

### Datensatz (Historie)

Enthält bewusst **beides**: manuell eingetragene `kwh`/`preis_kwh`/`kosten` **und** die automatische `schaetzung_kwh` samt `quelle` (`soc`/`power_ac`/`power_dc`).

### Struktur

```
custom_components/ev_assistant/
  __init__.py        # Setup, Services, Unload, Panel-Registrierung (reload-fähig)
  manifest.json
  const.py
  engine.py          # reine Logik (pytest) — ChargeDetector + EfficiencyCalibrator + TripDetector
  coordinator.py     # Entity-Verdrahtung, Erkennung, Kalibrierung, Persistenz, Notification
  config_flow.py     # Config- + Options-Flow (9 Schritte)
  entity.py          # gemeinsame Entity-Basis (Device-Gruppierung, fahrzeugbasierter Gerätename)
  sensor.py
  binary_sensor.py
  services.yaml
  strings.json
  translations/{de,en}.json
  frontend/          # Sidebar-Panel (ev-assistant-panel.js)
packages/            # optionales Legacy-UI
tests/               # pytest (engine.py)
```

### Anforderungen

- Home Assistant 2024.1+

---

## Lizenz / License

MIT
