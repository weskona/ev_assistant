# EV Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Version](https://img.shields.io/github/v/release/weskona/ev_assistant)](https://github.com/weskona/ev_assistant/releases)

Detects EV charging sessions **away from your home wallbox** ("Fremdladung") from SoC telemetry, lets you log the actual kWh/price from the receipt, and can automatically calibrate the vehicle's charge efficiency from your real home-charging sessions. Manufacturer-independent — works with any HA entity or MQTT source (WiCAN Pro, evcc/Warp, Stellantis/VW cloud sensors, ...).

**[🇩🇪 Deutsche Version weiter unten](#-deutsch)**

---

## 🇬🇧 English

### How it works

EV Assistant never needs GPS, a specific manufacturer API, or a list of known charging stations. It works purely from two numbers it already gets from your car and your home:

1. **State of charge (SoC)** — the battery percentage, e.g. from a manufacturer cloud sensor or a cheap OBD dongle like WiCAN Pro.
2. **Home-charging signal** — anything that tells you "the car is charging at my own wallbox right now" (e.g. from evcc, a Warp box, or any charger integration).

The core idea is one sentence: **if the battery percentage goes up while the home-charging signal says "no", the car must be charging somewhere else** — a public charger, a hotel, a friend's house, work. That's a "Fremdladung" (external/away charge). Home charging is deliberately ignored by the detector — you already track that through your own wallbox/evcc setup, so EV Assistant only ever bothers you about charges *you'd otherwise lose track of*.

Internally, a small state machine (`engine.py::ChargeDetector`) watches every new SoC reading:

- **Idle** — nothing is happening. It keeps remembering the lowest SoC value seen recently (the "anchor"). Every time the SoC dips back down (or the home-charging signal is on), the anchor resets to that value. This means the anchor always represents "the charge level right before whatever happens next".
- **Start of a session** — as soon as SoC has climbed at least `start_delta` (default **3 %**) above the anchor *while home-charging is off*, a Fremdladung session begins. Its official start point is the anchor (the last known low point), not the moment the threshold was crossed — so the session correctly includes the very first bit of charging that triggered the detection.
- **Active session** — as SoC keeps climbing, EV Assistant tracks the highest value seen ("peak"). A small `noise` tolerance (default **0.5 %**) absorbs sensor jitter (SoC readings occasionally wobble by a fraction of a percent without anything actually happening) so it doesn't get confused by measurement noise.
- **End of a session** — whichever of these happens first:
  - the home-charging signal turns on (you've arrived home and plugged in — the away-charge that just happened is now finalized), or
  - SoC drops by more than `drop_ends` (default **1 %**) below the peak (you unplugged and started driving), or
  - `idle_timeout_s` (default **600 s / 10 minutes**) passes with no further SoC increase (charging finished, or the cable/connection dropped).

At the end, EV Assistant has a `soc_start`, a `soc_end`, and needs to turn that into an energy estimate — see the next section for exactly how, with worked numbers.

### Detection walkthrough — a worked example

Say your car has a 45 kWh usable battery and the default 88 % charge efficiency (both configurable in step 1 of setup). You drive away from home with the battery at **32 %** and plug in at a public charger. No power sensor is configured yet — just SoC and the home-charging signal.

1. Before you left, the last few SoC readings were flat at 32 % with home-charging off (you weren't charging, just driving/parked away from home). The anchor sits at **32 %**.
2. At the charger, the next SoC reading comes in at **35 %**. That's +3 percentage points above the anchor — exactly the `start_delta` threshold — so a Fremdladung session **starts**, officially from `soc_start = 32 %` (the anchor), at the timestamp of that last 32 % reading.
3. Over the next couple of hours, SoC keeps ticking up: 40 %, 55 %, 68 %, 74 %. Each new high becomes the tracked peak.
4. You unplug at **74 %** and drive home. Ten minutes pass with the SoC entity reporting no further increase (it's not charging anymore) — the `idle_timeout_s` fires and the session **ends**.
5. Delta = 74 % − 32 % = **42 percentage points**. Without a power sensor, EV Assistant falls back to the SoC-only estimate:
   - Battery-side energy: `42 % of 45 kWh = 18.9 kWh`
   - AC-side (billed) estimate, accounting for charging losses: `18.9 kWh ÷ 0.88 = 21.48 kWh` — the notification rounds this to **≈ 21.5 kWh**.
6. EV Assistant now:
   - stores this as the **pending** charge,
   - publishes it to the configured MQTT topic,
   - fires the `ev_assistant_pending` event (with `config_entry_id` so you can tell which car, if you have more than one),
   - sends a notification: *"+42 % (32 → 74 %), ~21.5 kWh geschätzt. kWh und Preis eintragen."* ("... estimated. Enter kWh and price.")
   - turns on `binary_sensor ... Fremdladung Erfassung offen` and sets `sensor ... Fremdladung Schätzung` to 21.48 kWh.
7. A few days later the receipt arrives: **21.4 kWh** actually billed at **0.59 EUR/kWh** = **12.63 EUR**. You call `ev_assistant.log_charge` (or use the optional card) with these real numbers.
8. EV Assistant writes a history entry containing **both** figures — the estimate (21.48 kWh, source `soc`) and the real one (21.4 kWh, 0.59 EUR/kWh, 12.63 EUR) — updates the running totals, clears the pending charge, and dismisses the notification.

The SoC-only estimate (21.48 kWh) was almost exactly right here (21.4 kWh actual) — but that's partly luck. Real invoices vary with charger efficiency, cable losses, and battery temperature, which is exactly why the receipt value always wins for the actual cost bookkeeping.

### Energy estimation methods

The estimate shown while a charge is pending, and stored as `schaetzung_kwh`/`quelle` in history, comes from one of three methods, automatically chosen based on what you've configured (visible per session as `energy_source` / `quelle`: `soc`, `power_ac`, or `power_dc`):

| Source | When it's used | How it's calculated |
|---|---|---|
| `soc` | No charging-power sensor configured (or no data during this session) | `battery_kwh = soc_delta% × usable_kWh`; `ac_kwh = battery_kwh ÷ charge_efficiency` |
| `power_ac` | Charging-power sensor configured with **"power is AC-side"** enabled (the default) | `ac_kwh` = the power readings integrated over time (trapezoidal rule) — this is already the billed-side energy, no efficiency math needed; `battery_kwh = ac_kwh × charge_efficiency` (informational only) |
| `power_dc` | Charging-power sensor configured with **"power is AC-side"** disabled (sensor measures the battery/DC side, e.g. some vehicle telemetry) | `battery_kwh` = the power readings integrated over time; `ac_kwh = battery_kwh ÷ charge_efficiency` |

A power sensor (when available) is generally more accurate than the SoC-only method, because it reacts to the *actual* charging curve (which typically tapers off well before 100 %) instead of assuming a linear relationship between percentage and kWh.

### Installation

**Via HACS**
1. HACS → Integrations → ⋮ → **Custom repositories**
2. URL: `https://github.com/weskona/ev_assistant` — Category: **Integration**
3. Install EV Assistant, restart Home Assistant

**Manual**
1. Copy `custom_components/ev_assistant/` into `config/custom_components/`
2. Restart Home Assistant

### Configuration

Settings → Devices & Services → **Add integration** → "EV Assistant". Setup is a 6-step flow (also used identically when editing via **Configure**):

1. **Vehicle** — Manufacturer + model (required, e.g. "Peugeot" / "e-2008" — together they become the HA device name), first registration date (optional), odometer entity (optional, filtered to `sensor` + `device_class: distance` — mirrored onto the EV Assistant device as its own `... Kilometerstand` sensor, and used as the distance basis for the cost comparison in step 6), usable battery capacity in kWh (required), charge efficiency (optional starting value, see calibration below).
2. **Basic signals** — SoC and home-charging source, each as **HA entity OR MQTT topic** (entity takes priority). At least one source per signal is required (marked with `*`). The SoC entity picker is filtered to `sensor` + `device_class: battery`; the home-charging entity picker to `sensor` + `device_class: power` (e.g. a wallbox's charging-power sensor from evcc/Warp) — a numeric value **above 0.1 kW counts as "charging"**; a non-numeric value (e.g. evcc's own `"charging"`/`"on"` status string) falls back to a plain text match instead. If your power sensor reports a different unit (e.g. Watts), convert it with the template field, e.g. `{{ value | float / 1000 }}`. If your setup doesn't fit those (e.g. a `binary_sensor`), use the MQTT-topic field instead.
3. **Charging power** (optional) — improves the energy estimate of an external charge beyond plain SoC-delta (see "Energy estimation methods" above). Also where you configure a **wallbox energy meter** (cumulative kWh counter) for automatic efficiency calibration *and* for the home-charging cost tracked in step 6.
4. **Output** — MQTT publish topic for detected charges, optional `notify.*` service.
5. **Detection fine-tuning** — thresholds of the underlying state machine described above (`start_delta`, `noise`, `idle_timeout_s`, `drop_ends`). Defaults work for most vehicles; raise them for a car whose SoC only updates coarsely/infrequently (e.g. some cloud APIs).
6. **Cost comparison** (optional) — see "Cost comparison vs. a combustion car" below.

### Sources: manufacturer-independent

Each signal is fed from either an **HA entity** (e.g. a manufacturer integration) or **MQTT** (e.g. WiCAN Pro) — works with any manufacturer that exposes an SoC sensor in HA.

- **WiCAN Pro (MQTT):** SoC topic `<your_prefix>/telemetry/soc` (template `{{ value }}` or `{{ value_json.soc }}`).
- **Stellantis / VW / ... (entity):** SoC entity = `sensor.<car>_battery`. Cloud SoC is often coarse/infrequent — raise `start_delta` and `idle_timeout_s` accordingly; the power-based path is unavailable without real power data (falls back to SoC × efficiency).
- **Mixed** is fine: SoC from an entity, `home_charging` from evcc MQTT, etc.

An optional Jinja template per signal converts the raw value (`value` = state/payload, `value_json` = parsed JSON payload for MQTT).

### Automatic charge-efficiency calibration

Instead of a fixed manual efficiency value, EV Assistant can learn the real AC→battery efficiency from your own home-charging sessions — no external charge is involved in this at all, it's purely about how efficiently *your car* converts grid power into stored battery energy while charging at home.

**How it works:** configure a **wallbox energy meter** in step 3 — a cumulative kWh counter that only ever counts up (like a normal utility meter), not a "session energy" value that resets. Every time the home-charging signal switches on, EV Assistant remembers the current SoC and the current wallbox meter reading. When home-charging switches off again, it compares the SoC gained against the wallbox energy consumed for that same session, and calculates the efficiency:

`efficiency = (soc_gained% × usable_kWh) ÷ wallbox_energy_delta_kWh`

**Worked example:** your wallbox meter reads **100.0 kWh** when a home charge starts, and **120.2 kWh** when it ends — so **20.2 kWh** of AC energy was drawn from the grid. Over the same session, SoC went from **30 %** to **68 %**, a gain of 38 percentage points. With a 45 kWh usable battery, that's `38% × 45 kWh = 17.1 kWh` that actually went into the battery. The measured efficiency for this one session is `17.1 ÷ 20.2 ≈ 0.847` (84.7 %).

A single session isn't trusted blindly — implausible samples are discarded automatically (session too short: less than 5 percentage points of SoC gain; missing data; or a result outside the 50–100 % plausible range, which usually means a meter reset or a missed reading happened). Once **3 valid sessions** have been collected, EV Assistant averages the last 10 samples and **automatically starts using that measured value** for every calculation from then on — live, without a restart. If your car's real efficiency is, say, 0.847, 0.86, and 0.855 across three sessions, the new value in use becomes their average, **0.854 (85.4 %)** — replacing whichever value you originally typed in during setup.

The manual value from step 1 remains the fallback the whole time until enough sessions exist. See sensor `... Ladewirkungsgrad (gemessen)` ("measured charge efficiency") below for the live status.

### Cost comparison vs. a combustion car

All fields in step 6 are optional — configure as many or as few as you like; the sensors below simply show `unknown` until their required inputs are available.

**Distance driven:** the odometer entity from step 1 is read once at first startup and remembered as a reference point. "km driven" is always `current odometer − that reference value` — so the comparison covers everything from when you configured EV Assistant onward, not the car's full lifetime mileage.

**Home-charging cost:** the wallbox energy meter from step 3 (the same cumulative counter used for efficiency calibration) is read the same way — first-seen value as reference, current value minus that reference gives total home-charged kWh. Multiplied by the price you enter in step 6 (`home_price_kwh`), that's your estimated home-charging spend. Without a wallbox meter configured, this is simply treated as 0 — the comparison still works using only the (always-tracked) external-charging costs.

**Combustion reference:** `(km driven ÷ 100) × verbrenner_l_100km × verbrenner_price_per_liter` — a straightforward "what would this distance have cost in fuel" estimate for the comparison vehicle you describe. The fuel price can also be linked to a live entity (e.g. a fuel-price tracker sensor) instead of typing in a fixed value — if both are set, the entity wins. The `... Ersparnis ggü. Verbrenner` sensor's `kraftstoffpreis_live` attribute tells you which one is currently in effect.

**Worked example:** you've driven **1,000 km** since setting up EV Assistant. Your wallbox meter shows **150 kWh** charged at home, at a configured price of **0.30 EUR/kWh** → **45.00 EUR** home-charging cost. Your tracked external ("Fremdladung") charges total **50.00 EUR** so far. Total EV energy cost: `45.00 + 50.00 = 95.00 EUR`. Your reference combustion car uses 6.5 L/100km at a fuel price of 1.75 EUR/L: `(1,000 ÷ 100) × 6.5 × 1.75 = 113.75 EUR`. Your estimated savings: `113.75 − 95.00 = 18.75 EUR` over those 1,000 km.

### Sensors in detail

The HA device is named after the vehicle (`{Manufacturer} {Model}`), so entity names below appear as `{Device} {Entity}`, e.g. "Peugeot e-2008 Fremdladung Anzahl".

| Sensor | Meaning |
|---|---|
| `binary_sensor ... Fremdladung Erfassung offen` | **On** while at least one detected external charge is waiting for you to confirm the real kWh/price. More than one can be open at once — attributes: `anzahl_offen` (count), `offene_ladungen` (the full list, each with start/end time, SoC start/end, estimate, source), plus the oldest one's fields flattened directly at the top level for convenience. |
| `sensor ... Fremdladung Schätzung` | The estimated kWh of the currently pending charge (see "Energy estimation methods"). `unknown` when nothing is pending. |
| `sensor ... Fremdladung kWh (letzte)` | The `kwh` value you entered for the most recently confirmed external charge (i.e. from the receipt, not the estimate). |
| `sensor ... Fremdladung Kosten (letzte)` | `kwh × price_kwh` for that same most recent confirmed charge. |
| `sensor ... Fremdladung Preis (letzter)` | The price per kWh you entered for the most recent confirmed charge. |
| `sensor ... Fremdladung Ladezeit (letzte)` | How long the detected charging session lasted (from detection start to end), in minutes. `unknown` for older history entries confirmed before this sensor existed, or for a manually logged charge with no underlying detection. |
| `sensor ... Fremdladung kWh (gesamt)` | Running total of all confirmed external-charge kWh since setup (or since you last reset it — it's a `total_increasing` sensor, so the HA Energy dashboard can use it directly). |
| `sensor ... Fremdladung Kosten (gesamt)` | Running total of all confirmed external-charge costs. |
| `sensor ... Fremdladung Anzahl` | How many external charges have been confirmed in total. |
| `sensor ... Ladewirkungsgrad (gemessen)` ("measured charge efficiency") | The live-calibrated efficiency from **home** charging sessions (see above) — **not** related to external charges at all. Shown as a percentage. Attributes: `anzahl_sessions` (samples collected so far), `benoetigte_sessions` (3, the minimum needed before it takes over), `einzelwerte_prozent` (each individual sample), `wird_verwendet` (whether the measured value is currently being used instead of the manual one), `manueller_wert_prozent` (the configured fallback value). |
| `sensor ... Kilometerstand` (diagnostic) | Mirrors the odometer entity configured in step 1, if any, grouped onto the EV Assistant device. Pure display passthrough. |
| `sensor ... Erstzulassung` (diagnostic) | The first-registration date entered in step 1, exposed as a proper `date`-typed sensor. |
| `sensor ... Heimladen kWh (gesamt)` | Total home-charged kWh since setup, from the wallbox energy meter (step 3). `unknown` without a configured meter. |
| `sensor ... Heimladen Kosten (gesamt)` | Home-charging kWh above × the price per kWh from step 6. `unknown` without a configured meter or price. |
| `sensor ... Ersparnis ggü. Verbrenner` | Estimated savings vs. the reference combustion car from step 6, over the distance driven since setup (see "Cost comparison" above). `unknown` until the odometer entity, combustion consumption, and fuel price are all configured. Attributes: `gefahrene_km`, `heimladen_kosten`, `fremdladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live` (whether the fuel-price entity is currently overriding the fixed value). |

### Example calculations

A compact reference for the three calculations EV Assistant does, all using the defaults (45 kWh usable battery, 88 % efficiency):

**1) External charge, SoC-only estimate** (no power sensor configured)
> SoC 32 % → 74 % (Δ 42 pp)
> Battery energy: `0.42 × 45 kWh = 18.9 kWh`
> Billed (AC) estimate: `18.9 ÷ 0.88 = 21.48 kWh` ≈ **21.5 kWh**

**2) External charge, power-sensor estimate** (charging power sensor configured, AC-side)
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

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): confirm a pending charge and write it to history. **More than one charge can be pending at once** (e.g. two charging stops on a road trip before you get around to confirming either) — `start_ts` picks which one; without it, the oldest is confirmed (FIFO).
- `ev_assistant.discard_pending` — `config_entry_id` (+ optional `start_ts`): discard a pending charge (e.g. a false positive — it wasn't actually an external charge). Same `start_ts` selection rule as above.
- `ev_assistant.edit_charge` — `config_entry_id`, `erfasst_ts`, `kwh`, `price_kwh`: correct the kWh/price of an already-confirmed history entry (e.g. a typo noticed after the fact), identified by its `erfasst_ts` attribute (see the `historie` attribute on the last-cost sensor, or the [EV Assistant Card](https://github.com/weskona/ev-assistant-card)'s History list). Running totals are adjusted by the difference, not recomputed from scratch.
- `ev_assistant.delete_charge` — `config_entry_id`, `erfasst_ts`: fully removes an already-confirmed history entry (e.g. a falsely detected charge that wasn't actually external). Running totals are adjusted by the removed amount. **Not reversible.**
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): generate a **test event without a car** (triggers notification, MQTT, sensors) — see "Testing" below.

All three services require `config_entry_id` to target a specific vehicle if you run more than one EV Assistant instance.

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
**2) End-to-end in HA (no car needed):** Developer tools → Services → call `ev_assistant.simulate_event` with `config_entry_id`, `soc_start: 32`, `soc_end: 74`. Expect: a notification appears, `binary_sensor ... Fremdladung Erfassung offen` turns on, `sensor ... Fremdladung Schätzung` ≈ 21.48 kWh (see the worked example above). Then enter kWh/price and call `ev_assistant.log_charge` (or the save button) — history/totals update, and a publish happens to `ev_assistant/ladung/extern/<entry_id>/erfasst`.

### Data record (history / MQTT `.../erfasst`)

Deliberately contains **both** the manually entered `kwh`/`preis_kwh`/`kosten` **and** the automatic `schaetzung_kwh` plus its `quelle` (`soc`/`power_ac`/`power_dc`) — so you can see over time how close the estimate gets, and adjust `charge_efficiency` accordingly (or just let the automatic calibration handle it).

### Structure

```
custom_components/ev_assistant/
  __init__.py        # setup, services, unload (reload-capable)
  manifest.json
  const.py
  engine.py           # pure logic (pytest-testable) — ChargeDetector + EfficiencyCalibrator
  coordinator.py      # entity/MQTT wiring, detection, calibration, persistence, notification
  config_flow.py      # config + options flow (5 steps)
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
- `mqtt` integration set up (dependency), even if you only use HA-entity sources

---

## 🇩🇪 Deutsch

### Funktionsweise

EV Assistant braucht kein GPS, keine herstellerspezifische API und keine Liste bekannter Ladestationen. Es funktioniert allein mit zwei Werten, die ohnehin schon aus Auto und Zuhause vorliegen:

1. **Ladezustand (SoC)** — der Akku-Prozentwert, z.B. aus einem Hersteller-Cloud-Sensor oder einem günstigen OBD-Dongle wie WiCAN Pro.
2. **Heim-Laden-Signal** — irgendetwas, das dir sagt "das Auto lädt gerade an meiner eigenen Wallbox" (z.B. von evcc, einer Warp-Box, oder einer beliebigen Ladebox-Integration).

Der Grundgedanke lässt sich in einem Satz zusammenfassen: **Wenn der Akkuprozentwert steigt, während das Heim-Laden-Signal "nein" sagt, muss das Auto woanders laden** — an einer öffentlichen Ladesäule, im Hotel, bei Freunden, auf der Arbeit. Das ist eine „Fremdladung". Heim-Laden wird von der Erkennung bewusst ignoriert — das trackst du ohnehin schon über deine eigene Wallbox/evcc-Anbindung, EV Assistant meldet sich also nur bei Ladungen, die du *sonst nicht mitbekommen würdest*.

Intern beobachtet eine kleine Zustandsmaschine (`engine.py::ChargeDetector`) jeden neuen SoC-Wert:

- **Ruhezustand** — es passiert nichts. Der niedrigste zuletzt gesehene SoC-Wert wird gemerkt (der „Anker"). Sinkt der SoC wieder ab (oder ist das Heim-Laden-Signal aktiv), wird der Anker auf diesen neuen, niedrigeren Wert zurückgesetzt. Der Anker steht also immer für „der Ladestand kurz bevor irgendetwas als Nächstes passiert".
- **Beginn einer Session** — sobald der SoC um mindestens `start_delta` (Standard **3 %**) über den Anker gestiegen ist, *während* Heim-Laden aus ist, beginnt eine Fremdladung. Offizieller Startpunkt ist der Anker (der letzte bekannte Tiefpunkt), nicht der Moment, in dem die Schwelle überschritten wurde — so wird auch das allererste bisschen Ladung, das die Erkennung ausgelöst hat, korrekt mitgezählt.
- **Laufende Session** — solange der SoC weiter steigt, merkt sich EV Assistant den höchsten bisher gesehenen Wert („Peak"). Eine kleine `noise`-Toleranz (Standard **0,5 %**) fängt Sensor-Rauschen ab (SoC-Werte wackeln gelegentlich um einen Bruchteil eines Prozents, ohne dass tatsächlich etwas passiert) — das verhindert Fehlinterpretationen durch Messrauschen.
- **Ende einer Session** — je nachdem, was zuerst eintritt:
  - das Heim-Laden-Signal wird aktiv (du bist zuhause angekommen und hast eingesteckt — die gerade abgeschlossene Fremdladung wird jetzt finalisiert), oder
  - der SoC fällt um mehr als `drop_ends` (Standard **1 %**) unter den Peak (du hast abgesteckt und bist losgefahren), oder
  - `idle_timeout_s` (Standard **600 s / 10 Minuten**) vergeht ohne weiteren SoC-Anstieg (Ladevorgang beendet, oder die Verbindung ist abgebrochen).

Am Ende hat EV Assistant einen `soc_start` und einen `soc_end` und muss daraus eine Energie-Schätzung machen — wie genau, mit konkreten Zahlen, steht im nächsten Abschnitt.

### Erkennungs-Ablauf — ein durchgerechnetes Beispiel

Angenommen dein Auto hat einen nutzbaren Akku von 45 kWh und den Standard-Ladewirkungsgrad von 88 % (beide in Schritt 1 der Einrichtung einstellbar). Du fährst mit 32 % Akkustand von zuhause weg und steckst an einer öffentlichen Ladesäule ein. Ein Ladeleistungssensor ist noch nicht konfiguriert — nur SoC und das Heim-Laden-Signal.

1. Bevor du losgefahren bist, lagen die letzten SoC-Werte konstant bei 32 % mit Heim-Laden aus (du hast nicht geladen, nur geparkt/bist gefahren). Der Anker steht bei **32 %**.
2. An der Ladesäule kommt der nächste SoC-Wert mit **35 %** rein. Das sind +3 Prozentpunkte über dem Anker — genau die `start_delta`-Schwelle — also **beginnt** eine Fremdladung-Session, offiziell ab `soc_start = 32 %` (dem Anker), zum Zeitpunkt dieses letzten 32-%-Werts.
3. In den nächsten Stunden steigt der SoC weiter: 40 %, 55 %, 68 %, 74 %. Jeder neue Höchstwert wird als Peak gemerkt.
4. Du steckst bei **74 %** ab und fährst nach Hause. Zehn Minuten vergehen, ohne dass der SoC-Sensor einen weiteren Anstieg meldet (es wird nicht mehr geladen) — der `idle_timeout_s` greift und die Session **endet**.
5. Delta = 74 % − 32 % = **42 Prozentpunkte**. Ohne Ladeleistungssensor greift EV Assistant auf die reine SoC-Schätzung zurück:
   - Batterieseitige Energie: `42 % von 45 kWh = 18,9 kWh`
   - AC-seitige (abgerechnete) Schätzung, unter Berücksichtigung der Ladeverluste: `18,9 kWh ÷ 0,88 = 21,48 kWh` — die Benachrichtigung rundet das auf **≈ 21,5 kWh**.
6. EV Assistant tut jetzt Folgendes:
   - speichert dies als **offene** Ladung,
   - veröffentlicht sie auf dem konfigurierten MQTT-Topic,
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
| `soc` | Kein Ladeleistungssensor konfiguriert (oder keine Daten während dieser Session) | `Batterie-kWh = SoC-Delta% × nutzbare kWh`; `AC-kWh = Batterie-kWh ÷ Ladewirkungsgrad` |
| `power_ac` | Ladeleistungssensor konfiguriert, mit **„Ladeleistung ist AC-seitig"** aktiviert (Standard) | `AC-kWh` = die Leistungswerte über die Zeit integriert (Trapezregel) — das ist bereits der abgerechnete Wert, keine Wirkungsgrad-Rechnung nötig; `Batterie-kWh = AC-kWh × Ladewirkungsgrad` (nur informativ) |
| `power_dc` | Ladeleistungssensor konfiguriert, „AC-seitig" deaktiviert (Sensor misst batterie-/DC-seitig, z.B. manche Fahrzeugtelemetrie) | `Batterie-kWh` = die Leistungswerte über die Zeit integriert; `AC-kWh = Batterie-kWh ÷ Ladewirkungsgrad` |

Ein Ladeleistungssensor (wenn vorhanden) ist meist genauer als die reine SoC-Schätzung, da er die *tatsächliche* Ladekurve abbildet (die typischerweise deutlich vor 100 % abflacht) statt einen linearen Zusammenhang zwischen Prozent und kWh anzunehmen.

### Installation

**Über HACS**
1. HACS → Integrationen → ⋮ → **Benutzerdefinierte Repositories**
2. URL: `https://github.com/weskona/ev_assistant` — Kategorie: **Integration**
3. EV Assistant installieren, Home Assistant neu starten

**Manuell**
1. Ordner `custom_components/ev_assistant/` nach `config/custom_components/` kopieren
2. Home Assistant neu starten

### Konfiguration

Einstellungen → Geräte & Dienste → **Integration hinzufügen** → „EV Assistant". Die Einrichtung läuft in 6 Schritten (identisch auch beim Bearbeiten über **Konfigurieren**):

1. **Fahrzeug** — Hersteller + Modell (Pflicht, z.B. „Peugeot" / „e-2008" — ergeben zusammen den HA-Gerätenamen), Erstzulassung (optional), Kilometerstand-Entität (optional, gefiltert auf `sensor` + `device_class: distance` — wird als eigener `... Kilometerstand`-Sensor am EV-Assistant-Gerät gespiegelt und als Streckenbasis für den Kostenvergleich in Schritt 6 genutzt), nutzbare Akku-Kapazität in kWh (Pflicht), Ladewirkungsgrad (optionaler Startwert, siehe Kalibrierung unten).
2. **Grundsignale** — SoC- und Heim-Laden-Quelle, jeweils als **HA-Entität ODER MQTT-Topic** (Entität hat Vorrang). Mindestens eine Quelle pro Signal ist Pflicht (mit `*` markiert). Der SoC-Entitäts-Picker ist auf `sensor` + `device_class: battery` gefiltert, der Heim-Laden-Picker auf `sensor` + `device_class: power` (z.B. die Ladeleistung einer Wallbox von evcc/Warp) — ein Zahlenwert **über 0,1 kW gilt als „lädt"**; ein nicht-numerischer Wert (z.B. evccs eigener `"charging"`/`"on"`-Status) fällt stattdessen auf einen reinen Text-Vergleich zurück. Meldet dein Leistungssensor eine andere Einheit (z.B. Watt), rechne über das Template-Feld um, z.B. `{{ value | float / 1000 }}`. Passt das nicht zu deinem Setup (z.B. ein `binary_sensor`), nutze stattdessen das MQTT-Topic-Feld.
3. **Ladeleistung** (optional) — verbessert die Energie-Schätzung einer Fremdladung gegenüber der reinen SoC-Delta-Schätzung (siehe „Energie-Schätzmethoden" oben). Hier wird auch ein **Wallbox-Energiezähler** (kumulativer kWh-Zähler) für die automatische Ladewirkungsgrad-Kalibrierung *und* für die Heimladen-Kosten in Schritt 6 hinterlegt.
4. **Ausgabe** — MQTT-Publish-Topic für erkannte Ladungen, optionaler `notify.*`-Dienst.
5. **Erkennungs-Feinjustierung** — Schwellwerte der oben beschriebenen Zustandsmaschine (`start_delta`, `noise`, `idle_timeout_s`, `drop_ends`). Die Standardwerte passen für die meisten Fahrzeuge; bei einem Auto, dessen SoC nur grob/selten aktualisiert wird (manche Cloud-APIs), großzügiger einstellen.
6. **Kostenvergleich** (optional) — siehe „Kostenvergleich gegenüber einem Verbrenner" unten.

### Quellen: herstellerunabhängig

Jedes Signal wird aus einer **HA-Entität** (z.B. Hersteller-Integration) oder aus **MQTT** (z.B. WiCAN Pro) gespeist — funktioniert mit jedem Hersteller, der einen SoC-Sensor in HA bereitstellt.

- **WiCAN Pro (MQTT):** SoC-Topic `<dein_prefix>/telemetrie/soc` (Template `{{ value }}` oder `{{ value_json.soc }}`).
- **Stellantis / VW / … (Entität):** SoC-Entität = `sensor.<auto>_battery`. Cloud-SoC ist oft grob/selten — dann `start_delta` höher und `idle_timeout_s` großzügiger; der Leistungs-Pfad entfällt mangels echter Leistungsdaten (Fallback auf SoC × Wirkungsgrad).
- **Gemischt** ist möglich: SoC aus Entität, `home_charging` aus evcc-MQTT usw.

Ein optionales Jinja-Template pro Signal rechnet den Rohwert um (`value` = Zustand/Payload, `value_json` = geparster JSON-Payload bei MQTT).

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

**Heimladen-Kosten:** der Wallbox-Energiezähler aus Schritt 3 (derselbe kumulative Zähler wie für die Wirkungsgrad-Kalibrierung) wird genauso ausgelesen — erster gesehener Wert als Referenz, aktueller Wert minus Referenz ergibt die gesamten zuhause geladenen kWh. Multipliziert mit dem in Schritt 6 eingetragenen Preis (`home_price_kwh`) ergibt das die geschätzten Heimladen-Kosten. Ohne konfigurierten Wallbox-Zähler wird das einfach als 0 behandelt — der Vergleich funktioniert dann nur mit den (immer getrackten) Fremdladungskosten.

**Verbrenner-Referenz:** `(gefahrene km ÷ 100) × verbrenner_l_100km × verbrenner_price_per_liter` — eine einfache „was hätte diese Strecke an Kraftstoff gekostet"-Schätzung für das von dir beschriebene Vergleichsfahrzeug. Der Kraftstoffpreis kann statt eines festen Werts auch an eine Live-Entität gekoppelt werden (z.B. ein Tankstellenpreis-Sensor) — sind beide gesetzt, gewinnt die Entität. Das Attribut `kraftstoffpreis_live` am Sensor „… Ersparnis ggü. Verbrenner" zeigt, welcher Wert gerade aktiv ist.

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
| `sensor … Ladewirkungsgrad (gemessen)` | Der live kalibrierte Wirkungsgrad aus **Heim**-Ladesessions (siehe oben) — hat mit Fremdladungen nichts zu tun. Als Prozentwert angezeigt. Attribute: `anzahl_sessions` (bisher gesammelte Stichproben), `benoetigte_sessions` (3, das Minimum bevor er übernimmt), `einzelwerte_prozent` (jede Einzelstichprobe), `wird_verwendet` (ob der gemessene Wert gerade anstelle des manuellen verwendet wird), `manueller_wert_prozent` (der konfigurierte Fallback-Wert). |
| `sensor … Kilometerstand` (Diagnose) | Spiegelt die in Schritt 1 konfigurierte Kilometerstand-Entität, falls vorhanden, gruppiert am EV-Assistant-Gerät. Reine Anzeige-Weiterleitung. |
| `sensor … Erstzulassung` (Diagnose) | Das in Schritt 1 eingetragene Erstzulassungsdatum, als eigener `date`-Sensor. |
| `sensor … Heimladen kWh (gesamt)` | Gesamte zuhause geladene kWh seit Einrichtung, aus dem Wallbox-Energiezähler (Schritt 3). `unknown` ohne konfigurierten Zähler. |
| `sensor … Heimladen Kosten (gesamt)` | Obige Heimladen-kWh × der in Schritt 6 eingetragene Preis pro kWh. `unknown` ohne konfigurierten Zähler oder Preis. |
| `sensor … Ersparnis ggü. Verbrenner` | Geschätzte Ersparnis gegenüber dem Vergleichs-Verbrenner aus Schritt 6, über die seit Einrichtung gefahrene Strecke (siehe „Kostenvergleich" oben). `unknown`, bis Kilometerstand-Entität, Verbrenner-Verbrauch und Kraftstoffpreis alle konfiguriert sind. Attribute: `gefahrene_km`, `heimladen_kosten`, `fremdladen_kosten`, `kosten_ev_gesamt`, `kosten_verbrenner_geschaetzt`, `kraftstoffpreis_live` (ob gerade die Kraftstoffpreis-Entität den festen Wert überschreibt). |

### Beispielrechnungen

Eine kompakte Referenz für die drei Berechnungen, die EV Assistant durchführt, jeweils mit den Standardwerten (45 kWh nutzbarer Akku, 88 % Wirkungsgrad):

**1) Fremdladung, reine SoC-Schätzung** (kein Ladeleistungssensor konfiguriert)
> SoC 32 % → 74 % (Δ 42 Prozentpunkte)
> Batterie-Energie: `0,42 × 45 kWh = 18,9 kWh`
> Abgerechnete (AC-)Schätzung: `18,9 ÷ 0,88 = 21,48 kWh` ≈ **21,5 kWh**

**2) Fremdladung, Schätzung per Ladeleistungssensor** (Ladeleistungssensor konfiguriert, AC-seitig)
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

### Services

- `ev_assistant.log_charge` — `config_entry_id`, `kwh`, `price_kwh` (+ optional `start_ts`): eine offene Ladung bestätigen und in die Historie schreiben. **Es können mehrere Ladungen gleichzeitig offen sein** (z.B. zwei Ladestopps auf einem Roadtrip, bevor du zum Bestätigen kommst) — `start_ts` wählt die gemeinte aus; ohne Angabe wird die älteste bestätigt (FIFO).
- `ev_assistant.discard_pending` — `config_entry_id` (+ optional `start_ts`): eine offene Ladung verwerfen (z.B. ein Fehlalarm — es war gar keine Fremdladung). Gleiche `start_ts`-Auswahlregel wie oben.
- `ev_assistant.edit_charge` — `config_entry_id`, `erfasst_ts`, `kwh`, `price_kwh`: korrigiert kWh/Preis eines bereits bestätigten Historien-Eintrags nachträglich (z.B. ein Tippfehler, der später auffällt), identifiziert über dessen `erfasst_ts`-Attribut (siehe das `historie`-Attribut am Kosten-Sensor, oder die Historie-Liste der [EV Assistant Card](https://github.com/weskona/ev-assistant-card)). Die laufenden Summen werden um die Differenz angepasst, nicht neu berechnet.
- `ev_assistant.delete_charge` — `config_entry_id`, `erfasst_ts`: löscht einen bereits bestätigten Historien-Eintrag vollständig (z.B. eine fälschlich erkannte Ladung, die gar keine Fremdladung war). Die laufenden Summen werden um den gelöschten Betrag verringert. **Nicht rückgängig zu machen.**
- `ev_assistant.simulate_event` — `config_entry_id`, `soc_start`, `soc_end` (+ `energy_source`): **Testereignis ohne Auto** erzeugen (löst Benachrichtigung, MQTT, Sensoren aus) — siehe „Testen" unten.

Alle drei Services benötigen `config_entry_id`, um bei mehreren EV-Assistant-Instanzen das richtige Fahrzeug anzusprechen.

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

### Datensatz (Historie / MQTT `…/erfasst`)

Enthält bewusst **beides**: manuell `kwh`/`preis_kwh`/`kosten` **und** die Auto-`schaetzung_kwh` samt `quelle` (`soc`/`power_ac`/`power_dc`) — so siehst du über die Zeit, wie gut die Schätzung trifft, und kannst `charge_efficiency` nachziehen (oder die automatische Kalibrierung das übernehmen lassen).

### Struktur

```
custom_components/ev_assistant/
  __init__.py        # Setup, Services, Unload (reload-fähig)
  manifest.json
  const.py
  engine.py          # reine Logik (pytest) — ChargeDetector + EfficiencyCalibrator
  coordinator.py     # Entity-/MQTT-Verdrahtung, Erkennung, Kalibrierung, Persistenz, Notification
  config_flow.py     # Config- + Options-Flow (5 Schritte)
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
- `mqtt`-Integration eingerichtet (Dependency), auch wenn nur HA-Entitäten als Quelle genutzt werden

---

## Lizenz / License

MIT © [weskona](https://github.com/weskona)
