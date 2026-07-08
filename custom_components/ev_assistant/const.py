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
CONF_PUBLISH_TOPIC = "publish_topic"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_USABLE_KWH = "usable_kwh"
CONF_EFFICIENCY = "charge_efficiency"
CONF_POWER_IS_AC = "power_is_ac"
CONF_START_DELTA = "start_delta"
CONF_NOISE = "noise"
CONF_IDLE_TIMEOUT = "idle_timeout_s"
CONF_DROP_ENDS = "drop_ends"

DEFAULT_TEMPLATE = "{{ value }}"
DEFAULT_PUBLISH_TOPIC = "ev_assistant/ladung/extern"
DEFAULT_USABLE_KWH = 45.0
DEFAULT_EFFICIENCY = 0.88
DEFAULT_POWER_IS_AC = True
DEFAULT_START_DELTA = 3.0
DEFAULT_NOISE = 0.5
DEFAULT_IDLE_TIMEOUT = 600.0
DEFAULT_DROP_ENDS = 1.0

STORAGE_VERSION = 1
STORAGE_KEY = "ev_assistant_data"
HISTORY_MAX = 100

EVENT_PENDING = "ev_assistant_pending"
EVENT_LOGGED = "ev_assistant_logged"

SERVICE_LOG = "log_charge"
SERVICE_DISCARD = "discard_pending"
SERVICE_SIMULATE = "simulate_event"

NOTIFY_TAG = "ev_assistant"
