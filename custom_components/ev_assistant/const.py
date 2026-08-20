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
# Rekuperation (Bremsenergie-Rueckgewinnung waehrend der Fahrt) kann den SoC
# realistisch nur um wenige Prozentpunkte anheben. Ein SoC-Sprung ab dieser
# Groesse bei "bestaetigt ausgestecktem" Fahrzeug (siehe CONF_PLUG_ENTITY)
# ist mit ueberwiegender Wahrscheinlichkeit KEINE Rekuperation, sondern eine
# waehrend einer Erkennungsluecke (z.B. Telemetrie-Ausfall der Quell-
# Integration) VERPASSTE Fremdladung -- wird deshalb trotzdem als
# Ladungs-Start gewertet statt stillschweigend verworfen (siehe
# engine.py::ChargeDetector._update_idle()). Interne Heuristik, kein
# Config-Flow-Feld, analog TRIP_CONSUMPTION_MIN_KWH_100KM weiter unten.
IMPLAUSIBLE_REGEN_DELTA_PCT = 15.0
# Bei grober/lueckenhafter Leistungsmeldung (z.B. Stellantis-App: seltene,
# unregelmaessige Leistungs- UND SoC-Updates) integriert _integrate_power()
# ueber weite Luecken hinweg linear zwischen zwei zufaellig niedrigen
# Messpunkten -- das kann die tatsaechliche Ladeleistung um ein Vielfaches
# unterschaetzen (siehe engine.py::ChargeDetector._energy()), waehrend ein
# grosses SoC-Delta die Ladung plausibel belegt. Ab dieser Rate (Leistungs-
# Schaetzung / SoC-Schaetzung, beide in Batterie-kWh) gilt die Leistung als
# unplausibel niedrig und die SoC-Schaetzung wird stattdessen verwendet.
# 0.6 laesst der Leistungsmessung grosszuegig bis zu 40% Abweichung nach
# unten (z.B. durch eine ungenaue usable_kwh-Annahme), bevor sie verworfen
# wird -- der reale Feldfall (2.45 statt ~26 kWh, Verhaeltnis ca. 0.09)
# liegt weit darunter. Faellt NIE ein, wenn Leistung >= SoC-Schaetzung (der
# Fall "SoC grob, Leistung zuverlaessig" bleibt unveraendert). Interne
# Heuristik, kein Config-Flow-Feld, analog IMPLAUSIBLE_REGEN_DELTA_PCT.
IMPLAUSIBLE_POWER_RATIO = 0.6
# Deckel fuer die Trapez-Integration in _integrate_power(): eine Luecke
# zwischen zwei Leistungssamples, die laenger als dieser Wert ist, wird
# NICHT linear ueberbrueckt (Beitrag = 0 statt Trapezflaeche) -- eine derart
# lange Luecke ist keine verlaessliche Grundlage fuer eine Leistungsannahme
# ueber den gesamten Zeitraum. Grosszuegig gewaehlt (1h), um normal-grobe,
# aber noch brauchbare Meldefrequenzen (z.B. alle 15-20 Min.) nicht zu
# treffen -- wirkt nur bei echten Ausfaellen/sehr seltenen Updates.
MAX_POWER_GAP_S = 3600.0

# Fahrzeug-Eckdaten
CONF_VEHICLE_HERSTELLER = "vehicle_hersteller"
CONF_VEHICLE_MODELL = "vehicle_modell"
CONF_ERSTZULASSUNG = "erstzulassung"
CONF_ODO_ENTITY = "odo_entity"

# Lade-Modus: steuert NUR Sichtbarkeit (Panel-Tabs/Karten, welche Config-Flow-
# Schritte erscheinen) -- NICHT die Rechenlogik in engine.py. Ein reiner
# Fremdlader ist rechnerisch einfach der Fall, in dem die Heim-Aggregate 0
# sind (siehe coordinator.py::lade_modus()). "gemischt" ist Default UND der
# Wert, der fuer Bestandsinstallationen ohne gespeicherten CONF_LADE_MODUS
# ueberall gilt (siehe resolve_lade_modus() unten) -- fuer die aendert sich
# dadurch nichts.
CONF_LADE_MODUS = "lade_modus"
LADE_MODUS_NUR_ZUHAUSE = "nur_zuhause"
LADE_MODUS_GEMISCHT = "gemischt"
LADE_MODUS_NUR_AUSWAERTS = "nur_auswaerts"
LADE_MODUS_OPTIONS = (LADE_MODUS_NUR_ZUHAUSE, LADE_MODUS_GEMISCHT, LADE_MODUS_NUR_AUSWAERTS)
DEFAULT_LADE_MODUS = LADE_MODUS_GEMISCHT


def resolve_lade_modus(value) -> str:
    """Liefert einen gueltigen Lade-Modus fuer `value` (Rohwert aus
    entry.options/-.data). Fehlt er (Bestandsinstallationen vor Einfuehrung
    dieses Feldes) oder ist er kein bekannter Modus, gilt defensiv
    LADE_MODUS_GEMISCHT -- identisch zum bisherigen (impliziten) Verhalten,
    also keine Aenderung fuer Bestandsnutzer. Bewusst eine reine Funktion
    ohne HA-Import (wie der Rest von const.py), damit sie ohne HomeAssistant-
    Installation per pytest testbar ist -- anders als coordinator.py/
    config_flow.py, die HA-Importe ziehen. Zentral hier statt an jeder
    Lesestelle einzeln dupliziert, damit nur eine Stelle den Default kennen
    muss (siehe coordinator.py::lade_modus())."""
    return value if value in LADE_MODUS_OPTIONS else DEFAULT_LADE_MODUS

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

# AC/DC-Einordnung von Fremdladungen (siehe engine.ac_dc_breakdown()): es
# gibt kein direktes AC/DC-Signal im Fahrtenbuch, daher abgeleitet aus der
# Durchschnittsleistung je Ladung (kWh / Ladedauer). 3-phasiges AC-Laden
# erreicht realistisch nicht mehr als diesen Wert -- darueber gilt eine
# Ladung als DC (Schnellladen). Bewusst kein Config-Flow-Feld, analog
# TRIP_CONSUMPTION_MIN_KWH_100KM: grobe interne Heuristik. Nur fuer
# Fremdladungen -- Heimladen ist baulich praktisch immer AC.
AC_MAX_KW = 22.0

# Ab wann Detail-Eintraege aus "fahrten"/"history" in ein separates,
# unbegrenzt wachsendes Archiv wandern statt in der haeufig (bei praktisch
# jeder Coordinator-Aktualisierung) gespeicherten .storage-Datei zu bleiben
# (siehe coordinator.py::_async_truncate_lifetime_lists()) -- ueber mehrere
# Jahre Leasing wuerden sonst sowohl diese Datei als auch jeder ungecachte
# Voll-Scan unbegrenzt weiterwachsen. Bewusst konservativ hoch gewaehlt und
# kein Config-Flow-Feld (analog AC_MAX_KW). WICHTIG: kein Datenverlust --
# archivierte Eintraege bleiben vollstaendig erhalten und fliessen weiter
# in async_export_fahrtenbuch() ein; alle kumulativen Kennzahlen
# (Vollzyklen, Verbrauchs-/Temperaturband-/Wochentags-Schnitt, AC/DC-/
# Anbieter-Aufschluesselung) haengen NICHT an dieser Schwelle, sondern an
# separaten Lebenszeit-Baselines (siehe die *_totals-Felder in
# coordinator._empty_data()), die von der Kuerzung unberuehrt bleiben.
FAHRTEN_MAX_MONATE = 24
HISTORY_MAX_MONATE = 24

# Naeherung fuer die Umrechnung "monatliche Grundgebuehr" -> laufende
# Tagesrate (siehe engine.ladekarte_accrued_cost()): eine echte
# Kartenabrechnung erfolgt in monatlichen Spruengen, nicht stetig -- hier
# bewusst als laufende Summe behandelt (Tage aktiv / Ø Monatslaenge *
# Gebuehr), damit sie sich wie jede andere Kostensumme in dieser App
# kontinuierlich mitzieht statt in Spruengen. 365.25/12 = Ø Kalendermonat
# inkl. Schaltjahren. Bewusst kein Config-Flow-Feld, analog AC_MAX_KW.
LADEKARTE_AVG_DAYS_PER_MONTH = 365.25 / 12

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
SERVICE_ADD_LADEKARTE = "add_ladekarte"
SERVICE_EDIT_LADEKARTE = "edit_ladekarte"
SERVICE_DELETE_LADEKARTE = "delete_ladekarte"
SERVICE_ADD_LADEKARTE_PREISSTUFE = "add_ladekarte_preisstufe"
SERVICE_DELETE_LADEKARTE_PREISSTUFE = "delete_ladekarte_preisstufe"

NOTIFY_TAG = "ev_assistant"
