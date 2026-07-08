"""Coordinator: Quellen (Entity ODER MQTT), Erkennung, Persistenz, Services."""
from __future__ import annotations

import json
import logging
import time
from typing import Callable, Optional

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_DROP_ENDS, CONF_EFFICIENCY, CONF_HOME_ENTITY, CONF_HOME_TEMPLATE,
    CONF_HOME_TOPIC, CONF_IDLE_TIMEOUT, CONF_NOISE, CONF_NOTIFY_SERVICE,
    CONF_POWER_ENTITY, CONF_POWER_IS_AC, CONF_POWER_TEMPLATE, CONF_POWER_TOPIC,
    CONF_PUBLISH_TOPIC, CONF_SOC_ENTITY, CONF_SOC_TEMPLATE, CONF_SOC_TOPIC,
    CONF_START_DELTA, CONF_USABLE_KWH, DEFAULT_DROP_ENDS, DEFAULT_EFFICIENCY,
    DEFAULT_IDLE_TIMEOUT, DEFAULT_NOISE, DEFAULT_POWER_IS_AC,
    DEFAULT_PUBLISH_TOPIC, DEFAULT_START_DELTA, DEFAULT_TEMPLATE,
    DEFAULT_USABLE_KWH, DOMAIN, EVENT_LOGGED, EVENT_PENDING, HISTORY_MAX,
    NOTIFY_TAG, STORAGE_KEY, STORAGE_VERSION,
)
from .engine import ChargeDetector, ChargeSample

_LOGGER = logging.getLogger(__name__)

_HOME_TRUE = ("on", "true", "1", "yes", "charging", "charge")
_INVALID = ("unknown", "unavailable", "none", "", None)


def _empty_data() -> dict:
    return {
        "history": [],
        "totals": {"kwh": 0.0, "kosten": 0.0, "count": 0},
        "last_price": 0.0,
        "pending": None,
    }


class EvAssistantCoordinator(DataUpdateCoordinator):
    """Haelt Detector + Zustand, published Events, persistiert.

    Jedes Signal wird entweder aus einer HA-Entitaet (Vorrang) oder einem
    MQTT-Topic gespeist -> funktioniert mit Hersteller-Integrationen
    (Stellantis, VW, ...) genauso wie mit WiCAN Pro ueber MQTT.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._unsub: list[Callable] = []
        self._soc: Optional[float] = None
        self._home: bool = False
        self._power: Optional[float] = None
        self._detector: Optional[ChargeDetector] = None
        self.data = _empty_data()

    def _opt(self, key, default=None):
        return self.entry.options.get(key, self.entry.data.get(key, default))

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            base = _empty_data()
            base.update(stored)
            self.data = base
        self._build_detector()
        await self._setup_sources()
        self.async_set_updated_data(self.data)

    def _build_detector(self) -> None:
        self._detector = ChargeDetector(
            usable_kwh=float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH)),
            charge_efficiency=float(self._opt(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)),
            power_is_ac=bool(self._opt(CONF_POWER_IS_AC, DEFAULT_POWER_IS_AC)),
            start_delta=float(self._opt(CONF_START_DELTA, DEFAULT_START_DELTA)),
            noise=float(self._opt(CONF_NOISE, DEFAULT_NOISE)),
            idle_timeout_s=float(self._opt(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)),
            drop_ends=float(self._opt(CONF_DROP_ENDS, DEFAULT_DROP_ENDS)),
        )

    # ----- Quellen-Verdrahtung -------------------------------------------
    async def _setup_sources(self) -> None:
        await self._wire(CONF_SOC_ENTITY, CONF_SOC_TOPIC, CONF_SOC_TEMPLATE, self._set_soc)
        await self._wire(CONF_HOME_ENTITY, CONF_HOME_TOPIC, CONF_HOME_TEMPLATE, self._set_home)
        await self._wire(CONF_POWER_ENTITY, CONF_POWER_TOPIC, CONF_POWER_TEMPLATE, self._set_power)

    async def _wire(self, entity_key, topic_key, tmpl_key, setter: Callable[[object], None]) -> None:
        entity_id = self._opt(entity_key)
        topic = self._opt(topic_key)
        template_str = self._opt(tmpl_key, DEFAULT_TEMPLATE)

        if entity_id:  # Entitaet hat Vorrang
            @callback
            def _on_state(event, _setter=setter, _tmpl=template_str) -> None:
                new = event.data.get("new_state")
                if new is None or new.state in _INVALID:
                    return
                _setter(self._render(_tmpl, new.state, None))

            self._unsub.append(async_track_state_change_event(self.hass, [entity_id], _on_state))
            state = self.hass.states.get(entity_id)
            if state is not None and state.state not in _INVALID:
                setter(self._render(template_str, state.state, None))
            return

        if topic:
            @callback
            def _on_msg(msg, _setter=setter, _tmpl=template_str) -> None:
                value_json = None
                try:
                    value_json = json.loads(msg.payload)
                except (ValueError, TypeError):
                    pass
                _setter(self._render(_tmpl, msg.payload, value_json))

            self._unsub.append(await mqtt.async_subscribe(self.hass, topic, _on_msg))

    def _render(self, template_str, value, value_json):
        if not template_str:
            return value
        return Template(template_str, self.hass).async_render(
            {"value": value, "value_json": value_json}, parse_result=False
        )

    # ----- Setter (parsen + ggf. Erkennung anstossen) --------------------
    @callback
    def _set_soc(self, raw) -> None:
        try:
            self._soc = float(raw)
        except (ValueError, TypeError):
            return
        self.hass.async_create_task(self._run_detection())

    @callback
    def _set_home(self, raw) -> None:
        self._home = str(raw).strip().lower() in _HOME_TRUE

    @callback
    def _set_power(self, raw) -> None:
        try:
            self._power = float(raw)
        except (ValueError, TypeError):
            self._power = None

    async def _run_detection(self) -> None:
        if self._soc is None or self._detector is None:
            return
        sample = ChargeSample(ts=time.time(), soc=self._soc, home_charging=self._home, power_kw=self._power)
        event = self._detector.update(sample)
        if event is not None:
            await self._handle_pending(event.as_dict())

    # ----- Event-/Persistenz-Logik ---------------------------------------
    async def _handle_pending(self, pend: dict) -> None:
        self.data["pending"] = pend
        await self._save()
        await self._publish(self._opt(CONF_PUBLISH_TOPIC, DEFAULT_PUBLISH_TOPIC), pend, retain=False)
        self.hass.bus.async_fire(EVENT_PENDING, pend)
        await self._notify(pend)
        self.async_set_updated_data(self.data)

    async def _publish(self, topic: str, payload: dict, retain: bool) -> None:
        try:
            await mqtt.async_publish(self.hass, topic, json.dumps(payload), qos=1, retain=retain)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("MQTT publish auf %s fehlgeschlagen: %s", topic, err)

    async def _notify(self, pend: dict) -> None:
        message = (
            f"+{pend['delta_soc']} % ({pend['soc_start']} -> {pend['soc_end']} %), "
            f"~{round(pend['energy_kwh'], 1)} kWh geschaetzt. kWh und Preis eintragen."
        )
        notify_service = self._opt(CONF_NOTIFY_SERVICE)
        if notify_service:
            try:
                await self.hass.services.async_call(
                    "notify", notify_service,
                    {
                        "title": "Fremdladung erkannt",
                        "message": message,
                        "data": {
                            "tag": NOTIFY_TAG,
                            "persistent": True,
                            "actions": [{"action": "URI", "title": "Eintragen", "uri": "/lovelace"}],
                        },
                    },
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("notify.%s fehlgeschlagen: %s", notify_service, err)
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"notification_id": NOTIFY_TAG, "title": "Fremdladung erfassen", "message": message},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    async def async_log_charge(self, kwh: float, price: float, start_ts: Optional[float] = None) -> None:
        kwh = round(float(kwh), 2)
        price = round(float(price), 4)
        rec = {"kwh": kwh, "preis_kwh": price, "kosten": round(kwh * price, 2), "erfasst_ts": int(time.time())}
        pend = self.data.get("pending")
        if pend:
            rec.update({
                "start_ts": pend.get("start_ts"), "soc_start": pend.get("soc_start"),
                "soc_end": pend.get("soc_end"), "delta_soc": pend.get("delta_soc"),
                "schaetzung_kwh": pend.get("energy_kwh"), "quelle": pend.get("energy_source"),
            })
        elif start_ts is not None:
            rec["start_ts"] = start_ts

        self.data.setdefault("history", []).insert(0, rec)
        self.data["history"] = self.data["history"][:HISTORY_MAX]
        totals = self.data["totals"]
        totals["kwh"] = round(totals.get("kwh", 0.0) + kwh, 2)
        totals["kosten"] = round(totals.get("kosten", 0.0) + rec["kosten"], 2)
        totals["count"] = totals.get("count", 0) + 1
        self.data["last_price"] = price
        self.data["pending"] = None
        await self._save()
        await self._publish(self._opt(CONF_PUBLISH_TOPIC, DEFAULT_PUBLISH_TOPIC) + "/erfasst", rec, retain=True)
        self.hass.bus.async_fire(EVENT_LOGGED, rec)
        await self._dismiss()
        self.async_set_updated_data(self.data)

    async def async_discard(self) -> None:
        self.data["pending"] = None
        await self._save()
        await self._dismiss()
        self.async_set_updated_data(self.data)

    async def async_simulate(self, soc_start: float, soc_end: float, source: str = "soc") -> None:
        eff = float(self._opt(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) or 1.0
        usable = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        batt = (soc_end - soc_start) / 100.0 * usable
        ac = batt / eff
        now = int(time.time())
        pend = {
            "start_ts": now - 3600, "end_ts": now,
            "soc_start": round(soc_start, 1), "soc_end": round(soc_end, 1),
            "delta_soc": round(soc_end - soc_start, 1),
            "energy_kwh": round(ac, 2), "energy_batt_kwh": round(batt, 2),
            "losses_kwh": round(ac - batt, 2), "energy_source": source,
            "duration_min": 60.0, "kind": "extern",
        }
        await self._handle_pending(pend)

    async def _dismiss(self) -> None:
        try:
            await self.hass.services.async_call(
                "persistent_notification", "dismiss", {"notification_id": NOTIFY_TAG}, blocking=False
            )
        except Exception:  # noqa: BLE001
            pass

    async def _save(self) -> None:
        await self._store.async_save(self.data)

    async def async_shutdown(self) -> None:
        for unsub in self._unsub:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsub = []
