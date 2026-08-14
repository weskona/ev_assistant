"""Konstanten fuer die ev_assistant Integration."""

DOMAIN = "ev_assistant"
PLATFORMS = ["sensor", "binary_sensor"]

# Config / Options Keys
# Pro Signal: eine HA-Entitaet, optional per Template umgerechnet (z.B. andere
# Einheit). Templates bleiben nuetzlich unabhaengig von der Quelle, MQTT-Topics
# als Alternative wurden entfernt (siehe CHANGELOG). Die *_TEMPLATE-Keys sind
# absichtlich in keinem der 7 Config-Flow-Schritte als Feld vorhanden (wie
# z.B. EFF_MIN_SOC_DELTA unten, um die Formulare nicht mit Nischen-Reglern zu
# ueberladen) -- nur per direkter entry.data-Bearbeitung erreichbar, fuer den
# seltenen Fall einer Quell-Entitaet mit unpassender Einheit/Skalierung.
# Ohne gesetztes Template greift ueberall DEFAULT_TEMPLATE ("{{ value }}").
CONF_SOC_ENTITY = "soc_entity"
CONF_SOC_TEMPLATE = "soc_template"
CONF_HOME_ENTITY = "home_entity"
CONF_HOME_TEMPLATE = "home_template"
CONF_POWER_ENTITY = "power_entity"
CONF_POWER_TEMPLATE = "power_template"
CONF_WALLBOX_ENERGY_ENTITY = "wallbox_energy_entity"
CONF_WALLBOX_ENERGY_TEMPLATE = "wallbox_energy_template"
# Push-Benachrichtigungen: Zielgeraete (notify.*-Entitaeten der modernen,
# entity-basierten Notify-Plattform statt der alten "notify.<service>"-
# Aufrufe per Freitext) + welche Ereignisse ueberhaupt einen Push ausloesen
# sollen. Die persistent_notification im HA-Bereich "Benachrichtigungen"
# erscheint davon unabhaengig immer (siehe coordinator.py::_push()).
CONF_NOTIFY_ENTITIES = "notify_entities"
CONF_NOTIFY_EVENTS = "notify_events"

NOTIFY_EVENT_FREMDLADUNG = "fremdladung"
NOTIFY_EVENT_SOC_SCHWELLE = "soc_schwelle"
NOTIFY_EVENT_FAHRT = "fahrt"
NOTIFY_EVENT_TANKERKOENIG = "tankerkoenig"
NOTIFY_EVENT_LEASING = "leasing"
NOTIFY_EVENTS = [
    NOTIFY_EVENT_FREMDLADUNG, NOTIFY_EVENT_SOC_SCHWELLE,
    NOTIFY_EVENT_FAHRT, NOTIFY_EVENT_TANKERKOENIG, NOTIFY_EVENT_LEASING,
]
# Verhaelt sich wie vor Einfuehrung der Auswahl: nur Fremdladung loeste einen
# Push aus. Tupel statt Liste: DEFAULT_NOTIFY_EVENTS wird an vielen Stellen
# (mehrere Config Entries, jedes Mal derselbe Objektverweis) als Fallback-
# Wert zurueckgegeben -- ein Tupel schliesst aus, dass eine versehentliche
# In-Place-Mutation (z.B. .append()) diesen Fallback fuer alle Entries
# gleichzeitig verfaelscht. NOTIFY_EVENT_LEASING bewusst NICHT enthalten --
# jeder, der Leasing einrichtet, soll die Benachrichtigung aktiv dazuwaehlen.
DEFAULT_NOTIFY_EVENTS = (NOTIFY_EVENT_FREMDLADUNG,)

# SoC-Schwellenwerte (%) fuer eine Benachrichtigung waehrend eines laufenden
# Ladevorgangs (Heim- ODER Fremdladung, siehe coordinator.py::
# _check_soc_thresholds()). Feste Auswahl statt Freitext, um krumme/
# widersinnige Werte auszuschliessen. Werte kommen als Strings aus dem
# SelectSelector zurueck und werden erst beim Auswerten zu int.
CONF_SOC_THRESHOLDS = "soc_thresholds"
SOC_THRESHOLD_OPTIONS = [50, 60, 70, 80, 90, 100]
# Tupel statt Liste: siehe Kommentar bei DEFAULT_NOTIFY_EVENTS.
DEFAULT_SOC_THRESHOLDS = ()
CONF_USABLE_KWH = "usable_kwh"
CONF_EFFICIENCY = "charge_efficiency"
CONF_POWER_IS_AC = "power_is_ac"
CONF_START_DELTA = "start_delta"
CONF_NOISE = "noise"
CONF_IDLE_TIMEOUT = "idle_timeout_s"
CONF_DROP_ENDS = "drop_ends"
# Optional: binaerer Stecker-/Connectivity-Sensor (device_class "plug" oder
# "connectivity"). Bestaetigt "ausgesteckt" beendet eine Fremdladung sofort
# statt ueber idle_timeout_s zu warten -- bestaetigt "eingesteckt" verhindert
# umgekehrt, dass idle_timeout_s eine durchgehende Ladung bei grob/langsam
# gemeldetem SoC faelschlich splittet (siehe engine.py::SignalDebouncer).
CONF_PLUG_ENTITY = "plug_entity"
CONF_PLUG_DEBOUNCE = "plug_debounce_s"

# Fahrzeug-Eckdaten
CONF_VEHICLE_HERSTELLER = "vehicle_hersteller"
CONF_VEHICLE_MODELL = "vehicle_modell"
CONF_ERSTZULASSUNG = "erstzulassung"
CONF_ODO_ENTITY = "odo_entity"

# Fahrtenbuch: Feinjustierung der Fahrten-Erkennung (engine.py::TripDetector),
# basiert auf derselben Kilometerstand-Entitaet (CONF_ODO_ENTITY oben).
CONF_TRIP_MIN_KM = "trip_min_km"
CONF_TRIP_IDLE_TIMEOUT = "trip_idle_timeout_s"
# Optional: person-/device_tracker-Entitaet (liefert eine Zonen-Objekt-ID,
# z.B. "home") ODER eine beliebige sensor-Entitaet (Zustand wird direkt als
# Ortsname verwendet, wenn er keiner Zone entspricht -- z.B. ein Fahrzeug-
# eigener Standort-/Adress-Sensor). Wird bei Fahrtbeginn/-ende als Start-/
# Ziel-Ort-VORSCHLAG gespeichert (log_trip bestaetigt/korrigiert weiterhin
# manuell -- siehe coordinator.py::_run_trip_detection).
CONF_GPS_ENTITY = "gps_entity"
# Optional: binaerer Motor-/Fahr-Sensor ("Ready"/Zuendung/Motorlauf). Ergaenzt
# die odometerbasierte Fahrterkennung um ein zweites Signal fuer manche
# Hersteller-APIs, deren Kilometerstand zu grob/selten aktualisiert wird, um
# Fahrtbeginn/-ende daraus abzuleiten -- der Odometer bleibt trotzdem die
# einzige Quelle fuer die gefahrene Strecke (siehe engine.py::TripDetector).
CONF_MOTOR_ENTITY = "motor_entity"
CONF_MOTOR_DEBOUNCE = "motor_debounce_s"
# Optional: eine erkannte Fahrt wird sofort ins Fahrtenbuch uebernommen statt
# als "pending_trips"-Eintrag auf eine manuelle Bestaetigung mit Start-/
# Zielort zu warten (siehe coordinator.py::_handle_pending_trip). Start-/
# Zielort kommen dabei aus dem GPS-Ortsvorschlag (CONF_GPS_ENTITY), falls
# konfiguriert, sonst bleiben sie leer (spaeter per edit_trip nachtragbar).
CONF_TRIP_AUTO_CONFIRM = "trip_auto_confirm"
# Optional: Puffer (%) auf den historischen Wochentags-kWh-Bedarf beim
# Nutzungsprofil (siehe engine.py::weekday_usage_profile(),
# coordinator.py::usage_profile_tomorrow()) -- soll verhindern, dass ein
# leicht ueberdurchschnittlicher Tag den Akku knapp werden laesst.
CONF_USAGE_PROFILE_BUFFER_PCT = "usage_profile_buffer_pct"
# Optional: beliebige Sensor-Entitaet mit der PV-Ertragsprognose fuer morgen
# (kWh oder Wh, z.B. Solcast "Forecast Tomorrow" oder Forecast.Solar
# "Estimated Energy Production - Tomorrow") -- siehe
# coordinator.py::_pv_forecast_tomorrow_kwh(). Ohne sie vergleicht
# charge_before_pv_recommended() nur den aktuellen Akkustand gegen den
# morgigen Bedarf; mit ihr darf die morgen erwartete PV-Erzeugung eine
# Luecke schliessen, auch wenn der Akku allein nicht reicht.
CONF_PV_FORECAST_ENTITY = "pv_forecast_entity"

# Optionale Aussentemperatur-Entitaet (Wetter-Integration oder beliebiger
# Temperatursensor) fuer temperaturabhaengige Verbrauchs-/Reichweiten-
# Auswertung -- siehe engine.temperature_bucket()/consumption_by_temp_bucket()
# sowie coordinator.py::_extract_temp()/range_estimate_km().
CONF_OUTSIDE_TEMP_ENTITY = "outside_temp_entity"
# Baender in °C: (0, 10, 20) -> "<0°C", "0-10°C", "10-20°C", ">20°C".
TEMP_BUCKET_BOUNDARIES = (0.0, 10.0, 20.0)
# Wie viele Fahrten mit bekannter Start-Temperatur mindestens in einem Band
# liegen muessen, bevor dessen Durchschnitt als verlaesslich gilt.
TEMP_BUCKET_MIN_SAMPLES = 3

# Leasing-Kilometerbudget (alle optional -- Leasing gilt als eingerichtet,
# sobald CONF_LEASING_INKL_KM und CONF_LEASING_END_DATUM beide gesetzt sind,
# siehe coordinator.py::leasing_stats()/engine.leasing_status()). Kein
# einzelnes Feld bekommt einen DEFAULT_-Wert: ein Vertrags-Kilometerstand,
# -datum oder -preis laesst sich nicht sinnvoll raten, anders als z.B.
# DEFAULT_TRIP_MIN_KM (eine Erkennungsschwelle mit vernuenftigem
# Universalwert). Datumsfelder als ISO-String (wie CONF_ERSTZULASSUNG).
CONF_LEASING_START_KM = "leasing_start_km"
CONF_LEASING_START_DATUM = "leasing_start_datum"
CONF_LEASING_END_DATUM = "leasing_end_datum"
CONF_LEASING_INKL_KM = "leasing_inkl_km"
CONF_LEASING_PREIS_MEHR_KM = "leasing_preis_mehr_km"
CONF_LEASING_PREIS_MINDER_KM = "leasing_preis_minder_km"
# Interne Schwellwerte fuer engine.leasing_status() -- keine Config-Flow-
# Felder, analog TEMP_BUCKET_MIN_SAMPLES/BATTERY_CAPACITY_MIN_SOC_DELTA.
LEASING_KNAPP_SCHWELLE_PCT = 90.0
LEASING_TOLERANZ_PCT = 2.0

# Kostenvergleich gegenueber einem Verbrenner (alle optional -- ohne sie
# bleiben die Ersparnis-Sensoren unbekannt statt einen Fehler zu werfen).
# Heimstrompreis UND Kraftstoffpreis: jeweils fester Wert ODER live-Entitaet
# (z.B. ein dynamischer Tarif- bzw. ein Tankstellenpreis-Sensor) -- die
# Entitaet hat Vorrang, wenn beides gesetzt ist. CONF_TANKERKOENIG_FUEL_TYPE
# hat wiederum Vorrang vor CONF_VERBRENNER_PRICE_ENTITY: ist eine Kraftstoff-
# sorte gewaehlt, ermittelt der Coordinator selbst die guenstigste offene
# Tankerkoenig-Station (siehe coordinator.py::_wire_tankerkoenig_price()) statt
# eine einzelne, manuell konfigurierte Preis-Entitaet zu lesen -- Nutzer koennen
# so zwischen "eigene Entitaet/fester Preis" und "automatisch aus Tankerkoenig"
# waehlen, je nachdem, ob das Feld gesetzt ist.
CONF_HOME_PRICE_KWH = "home_price_kwh"
CONF_HOME_PRICE_ENTITY = "home_price_entity"
CONF_VERBRENNER_L_100KM = "verbrenner_l_100km"
CONF_VERBRENNER_PRICE_PER_LITER = "verbrenner_price_per_liter"
CONF_VERBRENNER_PRICE_ENTITY = "verbrenner_price_entity"
CONF_TANKERKOENIG_FUEL_TYPE = "tankerkoenig_fuel_type"
# Optional: Netzstrom-CO2-Intensitaet (g/kWh) fuer den CO2-Vergleich gegen
# den Verbrenner (siehe engine.py::calculate_co2_savings()). Fester Wert
# statt Live-Entitaet, anders als beim Kraftstoff-/Heimstrompreis -- die
# CO2-Intensitaet schwankt fuer die Zwecke dieses Vergleichs deutlich
# weniger stark als Preise und eine Live-Quelle (z.B. eine CO2-Signal-
# Integration) waere ein weiterer optionaler Konfigurationsschritt fuer
# einen Wert, der ohnehin nur eine grobe Schaetzung sein kann.
CONF_CO2_PER_KWH = "co2_per_kwh_g"

# Evcc-Fahrzeugname (String, kein Entity — muss dem "vehicle"-Feld in evcc's
# Ladelogbuch entsprechen), zum Filtern der Heimladen-Historie bei mehreren
# Fahrzeugen in evcc. Bewusst NICHT in EVCC_CONF_KEYS (das ist nur fuer
# Entity-ID-Felder, die 1:1 ins Panel-"entities"-Mapping kopiert werden).
CONF_EVCC_VEHICLE_NAME      = "evcc_vehicle_name"

# Evcc/Wallbox-Entitäten für das Dashboard-Panel (Übersicht-Tab)
CONF_EVCC_CHARGE_POWER      = "evcc_charge_power"
CONF_EVCC_CHARGE_STATUS     = "evcc_charge_status"
CONF_EVCC_MODE              = "evcc_mode"
CONF_EVCC_PHASES_ACTIVE     = "evcc_phases_active"
CONF_EVCC_VEHICLE_SOC       = "evcc_vehicle_soc"
CONF_EVCC_LIMIT_SOC         = "evcc_limit_soc"
CONF_EVCC_SESSION_ENERGY    = "evcc_session_energy"
CONF_EVCC_SESSION_SOLAR_PCT = "evcc_session_solar_pct"
CONF_EVCC_SESSION_PRICE     = "evcc_session_price"
CONF_EVCC_CHARGE_DURATION   = "evcc_charge_duration"
CONF_EVCC_TARIFF_GRID       = "evcc_tariff_grid"
CONF_EVCC_TARIFF_FEEDIN     = "evcc_tariff_feedin"
CONF_EVCC_STAT_TOTAL_KWH    = "evcc_stat_total_kwh"
CONF_EVCC_STAT_SOLAR_PCT    = "evcc_stat_solar_pct"
CONF_EVCC_STAT_AVG_PRICE    = "evcc_stat_avg_price"
# Site-level power (Watts) — used for the flow diagram
CONF_EVCC_PV_POWER          = "evcc_pv_power"
CONF_EVCC_GRID_POWER        = "evcc_grid_power"
CONF_EVCC_BATTERY_POWER     = "evcc_battery_power"

EVCC_CONF_KEYS = [
    CONF_EVCC_CHARGE_POWER, CONF_EVCC_CHARGE_STATUS, CONF_EVCC_MODE,
    CONF_EVCC_PHASES_ACTIVE, CONF_EVCC_VEHICLE_SOC, CONF_EVCC_LIMIT_SOC,
    CONF_EVCC_SESSION_ENERGY, CONF_EVCC_SESSION_SOLAR_PCT, CONF_EVCC_SESSION_PRICE,
    CONF_EVCC_CHARGE_DURATION, CONF_EVCC_TARIFF_GRID, CONF_EVCC_TARIFF_FEEDIN,
    CONF_EVCC_STAT_TOTAL_KWH, CONF_EVCC_STAT_SOLAR_PCT, CONF_EVCC_STAT_AVG_PRICE,
    CONF_EVCC_PV_POWER, CONF_EVCC_GRID_POWER, CONF_EVCC_BATTERY_POWER,
]

DEFAULT_TEMPLATE = "{{ value }}"
DEFAULT_USABLE_KWH = 45.0
DEFAULT_EFFICIENCY = 0.88
DEFAULT_POWER_IS_AC = True
DEFAULT_START_DELTA = 1.0
DEFAULT_NOISE = 0.5
DEFAULT_IDLE_TIMEOUT = 600.0
DEFAULT_DROP_ENDS = 1.0

# Plausibilitaetsband fuer aus SoC-Delta geschaetzten Fahrt-Verbrauch (siehe
# engine.is_plausible_trip_consumption) -- bewusst kein Config-Flow-Feld,
# analog EFF_MIN_SOC_DELTA: grobe interne Heuristik, keine Nutzer-Einstellung.
TRIP_CONSUMPTION_MIN_KWH_100KM = 8.0
TRIP_CONSUMPTION_MAX_KWH_100KM = 40.0
TRIP_CONSUMPTION_CHECK_MIN_KM = 5.0

# Geschaetzte Akkukapazitaet aus Fremdladungen (siehe engine.battery_capacity_
# samples/estimate_battery_capacity_kwh) -- ebenfalls interne Heuristik, kein
# Config-Flow-Feld.
BATTERY_CAPACITY_MIN_SOC_DELTA = 20.0
BATTERY_CAPACITY_MAX_SAMPLES = 5
BATTERY_CAPACITY_MIN_SAMPLES = 2
# Wie viele Heim-Session-Kapazitaets-Stichproben dauerhaft aufbewahrt werden
# (mehr als BATTERY_CAPACITY_MAX_SAMPLES, damit auch bei laengerer Pause
# ohne Fremdladung noch genug Historie fuer den rollierenden Schnitt da ist).
BATTERY_CAPACITY_HOME_MAX_STORED = 10
# Grosszuegig, da Hersteller-/Dongle-APIs den Steckerstatus teils verzoegert
# oder kurzzeitig unzuverlaessig melden (siehe engine.py::SignalDebouncer).
DEFAULT_PLUG_DEBOUNCE = 300.0
DEFAULT_TRIP_MIN_KM = 0.5
DEFAULT_TRIP_IDLE_TIMEOUT = 300.0
# Kuerzer als DEFAULT_PLUG_DEBOUNCE: filtert nur kurze Sensor-Fehlmeldungen --
# die eigentliche Kulanzzeit fuer normale Fahrpausen (Ampel, Stopp-Start-
# Automatik) liefert bereits DEFAULT_TRIP_IDLE_TIMEOUT.
DEFAULT_MOTOR_DEBOUNCE = 60.0
DEFAULT_TRIP_AUTO_CONFIRM = False
DEFAULT_USAGE_PROFILE_BUFFER_PCT = 20.0
# Mindestanzahl Kalendertage Fahrtenbuch-Historie, bevor ein Nutzungsprofil
# gezeigt wird (siehe engine.py::weekday_usage_profile()) -- 7 Tage
# garantieren, dass jeder Wochentag mindestens einmal vorkommt.
MIN_USAGE_PROFILE_DAYS = 7
# Deutscher Strommix-Durchschnitt (grobe Schaetzung, schwankt je nach Jahr/
# Versorger/Tarif) -- Nutzer mit einer praeziseren Quelle (z.B. Oekostrom-
# Vertrag) sollten den Wert anpassen.
DEFAULT_CO2_PER_KWH_G = 380.0
# Direkte Verbrennungs-CO2-Faktoren (kg/Liter, Tank-to-Wheel, ohne
# Vorkette) je Kraftstoffsorte -- dieselben Werte, die CONF_TANKERKOENIG_
# FUEL_TYPE bereits zur Auswahl anbietet. "super" ist der Fallback fuer
# Verbrenner-Vergleiche ohne gewaehlte Kraftstoffsorte (die meisten reinen
# Kostenvergleiche ohne Tankerkoenig-Integration).
CO2_PER_LITER_KG = {"super": 2.33, "super_e10": 2.24, "diesel": 2.65}
DEFAULT_CO2_PER_LITER_KG = CO2_PER_LITER_KG["super"]

STORAGE_VERSION = 1
STORAGE_KEY = "ev_assistant_data"

MILES_TO_KM = 1.60934

# Ladewirkungsgrad-Kalibrierung aus echten Heim-Ladesessions (siehe
# engine.py::EfficiencyCalibrator). Nicht ueber den Config Flow einstellbar,
# um die Erkennungs-Feinjustierung nicht mit Nischen-Reglern zu ueberladen.
EFF_MIN_SOC_DELTA = 5.0
EFF_MIN_SAMPLES = 3
EFF_MAX_SAMPLES = 10
EFF_MIN_EFFICIENCY = 0.5
EFF_MAX_EFFICIENCY = 1.0

EVENT_PENDING = "ev_assistant_pending"
EVENT_LOGGED = "ev_assistant_logged"
EVENT_EDITED = "ev_assistant_edited"
EVENT_DELETED = "ev_assistant_deleted"
EVENT_TRIP_PENDING = "ev_assistant_trip_pending"
EVENT_TRIP_LOGGED = "ev_assistant_trip_logged"
EVENT_TRIP_EDITED = "ev_assistant_trip_edited"
EVENT_TRIP_DELETED = "ev_assistant_trip_deleted"
EVENT_TRIP_IMPORTED = "ev_assistant_trip_imported"

SERVICE_LOG = "log_charge"
SERVICE_DISCARD = "discard_pending"
SERVICE_SIMULATE = "simulate_event"
SERVICE_EDIT = "edit_charge"
SERVICE_DELETE = "delete_charge"
SERVICE_LOG_TRIP = "log_trip"
SERVICE_DISCARD_TRIP = "discard_pending_trip"
SERVICE_EXPORT_TRIPS = "export_fahrtenbuch"
SERVICE_SIMULATE_TRIP = "simulate_trip"
SERVICE_EDIT_TRIP = "edit_trip"
SERVICE_DELETE_TRIP = "delete_trip"
SERVICE_IMPORT_TRIPS = "import_fahrtenbuch"

NOTIFY_TAG = "ev_assistant"
