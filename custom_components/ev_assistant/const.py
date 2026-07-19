"""Konstanten fuer die ev_assistant Integration."""

DOMAIN = "ev_assistant"
PLATFORMS = ["sensor", "binary_sensor"]

# Config / Options Keys
# Pro Signal: entweder eine HA-Entitaet (Vorrang) ODER ein MQTT-Topic.
CONF_SOC_ENTITY = "soc_entity"
CONF_SOC_TOPIC = "soc_topic"
CONF_SOC_TEMPLATE = "soc_template"
CONF_HOME_ENTITY = "home_entity"
CONF_HOME_TOPIC = "home_topic"
CONF_HOME_TEMPLATE = "home_template"
CONF_POWER_ENTITY = "power_entity"
CONF_POWER_TOPIC = "power_topic"
CONF_POWER_TEMPLATE = "power_template"
CONF_WALLBOX_ENERGY_ENTITY = "wallbox_energy_entity"
CONF_WALLBOX_ENERGY_TOPIC = "wallbox_energy_topic"
CONF_WALLBOX_ENERGY_TEMPLATE = "wallbox_energy_template"
CONF_PUBLISH_TOPIC = "publish_topic"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_USABLE_KWH = "usable_kwh"
CONF_EFFICIENCY = "charge_efficiency"
CONF_POWER_IS_AC = "power_is_ac"
CONF_START_DELTA = "start_delta"
CONF_NOISE = "noise"
CONF_IDLE_TIMEOUT = "idle_timeout_s"
CONF_DROP_ENDS = "drop_ends"

# Fahrzeug-Eckdaten
CONF_VEHICLE_HERSTELLER = "vehicle_hersteller"
CONF_VEHICLE_MODELL = "vehicle_modell"
CONF_ERSTZULASSUNG = "erstzulassung"
CONF_ODO_ENTITY = "odo_entity"

# Kostenvergleich gegenueber einem Verbrenner (alle optional -- ohne sie
# bleiben die Ersparnis-Sensoren unbekannt statt einen Fehler zu werfen).
# Heimstrompreis UND Kraftstoffpreis: jeweils fester Wert ODER live-Entitaet
# (z.B. ein dynamischer Tarif- bzw. ein Tankstellenpreis-Sensor) -- die
# Entitaet hat Vorrang, wenn beides gesetzt ist.
CONF_HOME_PRICE_KWH = "home_price_kwh"
CONF_HOME_PRICE_ENTITY = "home_price_entity"
CONF_VERBRENNER_L_100KM = "verbrenner_l_100km"
CONF_VERBRENNER_PRICE_PER_LITER = "verbrenner_price_per_liter"
CONF_VERBRENNER_PRICE_ENTITY = "verbrenner_price_entity"

DEFAULT_TEMPLATE = "{{ value }}"
DEFAULT_PUBLISH_TOPIC = "ev_assistant/ladung/extern"
DEFAULT_USABLE_KWH = 45.0
DEFAULT_EFFICIENCY = 0.88
DEFAULT_POWER_IS_AC = True
DEFAULT_START_DELTA = 1.0
DEFAULT_NOISE = 0.5
DEFAULT_IDLE_TIMEOUT = 600.0
DEFAULT_DROP_ENDS = 1.0

STORAGE_VERSION = 1
STORAGE_KEY = "ev_assistant_data"
HISTORY_MAX = 100

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

SERVICE_LOG = "log_charge"
SERVICE_DISCARD = "discard_pending"
SERVICE_SIMULATE = "simulate_event"
SERVICE_EDIT = "edit_charge"
SERVICE_DELETE = "delete_charge"

NOTIFY_TAG = "ev_assistant"
