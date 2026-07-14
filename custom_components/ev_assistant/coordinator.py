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
    CONF_START_DELTA, CONF_USABLE_KWH, CONF_WALLBOX_ENERGY_ENTITY,
    CONF_WALLBOX_ENERGY_TEMPLATE, CONF_WALLBOX_ENERGY_TOPIC,
    DEFAULT_DROP_ENDS, DEFAULT_EFFICIENCY,
    DEFAULT_IDLE_TIMEOUT, DEFAULT_NOISE, DEFAULT_POWER_IS_AC,
    DEFAULT_PUBLISH_TOPIC, DEFAULT_START_DELTA, DEFAULT_TEMPLATE,
    DEFAULT_USABLE_KWH, DOMAIN, EFF_MAX_SAMPLES, EFF_MIN_EFFICIENCY,
    EFF_MAX_EFFICIENCY, EFF_MIN_SAMPLES, EFF_MIN_SOC_DELTA,
    EVENT_DELETED, EVENT_EDITED, EVENT_LOGGED, EVENT_PENDING, HISTORY_MAX,
    NOTIFY_TAG, STORAGE_KEY, STORAGE_VERSION,
)
from .engine import ChargeDetector, ChargeSample, EfficiencyCalibrator, average_efficiency, pop_pending

_LOGGER = logging.getLogger(__name__)

_HOME_TRUE = ("on", "true", "1", "yes", "charging", "charge")
_INVALID = ("unknown", "unavailable", "none", "", None)


def _empty_data() -> dict:
    return {
        "history": [],
        "totals": {"kwh": 0.0, "kosten": 0.0, "count": 0},
        "last_price": 0.0,
        "pending": [],
        "efficiency_samples": [],
        "measured_efficiency": None,
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
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{entry.entry_id}")
        self._notify_tag = f"{NOTIFY_TAG}_{entry.entry_id}"
        self._default_publish_topic = f"{DEFAULT_PUBLISH_TOPIC}/{entry.entry_id}"
        self._unsub: list[Callable] = []
        self._soc: Optional[float] = None
        self._home: bool = False
        self._power: Optional[float] = None
        self._wallbox_energy: Optional[float] = None
        self._detector: Optional[ChargeDetector] = None
        self._calibrator: Optional[EfficiencyCalibrator] = None
        self.data = _empty_data()

    def _opt(self, key, default=None):
        return self.entry.options.get(key, self.entry.data.get(key, default))

    async def async_setup(self) -> None:
        stored = await self._store.async_load()
        if stored:
            base = _empty_data()
            base.update(stored)
            self.data = base
        # Migration: "pending" war vor Mehrfach-Unterstuetzung ein einzelnes
        # Dict oder None statt einer Liste.
        pending = self.data.get("pending")
        if isinstance(pending, dict):
            self.data["pending"] = [pending]
        elif pending is None:
            self.data["pending"] = []
        self._build_detector()
        await self._setup_sources()
        self.async_set_updated_data(self.data)

    def _build_detector(self) -> None:
        usable_kwh = float(self._opt(CONF_USABLE_KWH, DEFAULT_USABLE_KWH))
        manual_efficiency = float(self._opt(CONF_EFFICIENCY, DEFAULT_EFFICIENCY))
        measured_efficiency = self.data.get("measured_efficiency")
        self._detector = ChargeDetector(
            usable_kwh=usable_kwh,
            charge_efficiency=measured_efficiency if measured_efficiency is not None else manual_efficiency,
            power_is_ac=bool(self._opt(CONF_POWER_IS_AC, DEFAULT_POWER_IS_AC)),
            start_delta=float(self._opt(CONF_START_DELTA, DEFAULT_START_DELTA)),
            noise=float(self._opt(CONF_NOISE, DEFAULT_NOISE)),
            idle_timeout_s=float(self._opt(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)),
            drop_ends=float(self._opt(CONF_DROP_ENDS, DEFAULT_DROP_ENDS)),
        )
        self._calibrator = EfficiencyCalibrator(
            usable_kwh=usable_kwh,
            min_soc_delta=EFF_MIN_SOC_DELTA,
            min_efficiency=EFF_MIN_EFFICIENCY,
            max_efficiency=EFF_MAX_EFFICIENCY,
        )

    # ----- Quellen-Verdrahtung -------------------------------------------
    async def _setup_sources(self) -> None:
        await self._wire(CONF_SOC_ENTITY, CONF_SOC_TOPIC, CONF_SOC_TEMPLATE, self._set_soc)
        await self._wire(
            CONF_WALLBOX_ENERGY_ENTITY, CONF_WALLBOX_ENERGY_TOPIC,
            CONF_WALLBOX_ENERGY_TEMPLATE, self._set_wallbox_energy,
        )
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
        was_home = self._home
        self._home = str(raw).strip().lower() in _HOME_TRUE
        if self._calibrator is None or self._soc is None:
            return
        if not was_home and self._home:
            self._calibrator.start(self._soc, self._wallbox_energy)
        elif was_home and not self._home:
            sample = self._calibrator.end(self._soc, self._wallbox_energy)
            if sample is not None:
                self.hass.async_create_task(self._record_efficiency_sample(sample))

    @callback
    def _set_power(self, raw) -> None:
        try:
            self._power = float(raw)
        except (ValueError, TypeError):
            self._power = None

    @callback
    def _set_wallbox_energy(self, raw) -> None:
        try:
            self._wallbox_energy = float(raw)
        except (ValueError, TypeError):
            self._wallbox_energy = None

    async def _run_detection(self) -> None:
        if self._soc is None or self._detector is None:
            return
        sample = ChargeSample(ts=time.time(), soc=self._soc, home_charging=self._home, power_kw=self._power)
        event = self._detector.update(sample)
        if event is not None:
            await self._handle_pending(event.as_dict())

    async def _record_efficiency_sample(self, sample: float) -> None:
        """Neue Effizienz-Stichprobe aus einer abgeschlossenen Heim-
        Ladesession. Sobald genug Stichproben vorliegen (EFF_MIN_SAMPLES),
        wird der gemessene Durchschnitt automatisch fuer alle weiteren
        Berechnungen verwendet (Detector direkt aktualisiert, kein Neustart
        noetig) — der manuelle charge_efficiency-Wert bleibt Fallback."""
        samples = list(self.data.get("efficiency_samples") or [])
        samples.append(sample)
        samples = samples[-EFF_MAX_SAMPLES:]
        self.data["efficiency_samples"] = samples
        if len(samples) >= EFF_MIN_SAMPLES:
            measured = average_efficiency(samples, EFF_MAX_SAMPLES)
            self.data["measured_efficiency"] = measured
            if measured is not None and self._detector is not None:
                self._detector.charge_efficiency = measured
        await self._save()
        self.async_set_updated_data(self.data)

    # ----- Event-/Persistenz-Logik ---------------------------------------
    async def _handle_pending(self, pend: dict) -> None:
        # config_entry_id im Event, damit Automationen (z.B. packages/
        # ev_assistant_ui.yaml) bei mehreren Fahrzeugen wissen, welche
        # Instanz die Fremdladung gemeldet hat. "pending" ist eine Liste
        # (mehrere gleichzeitig offene Fremdladungen moeglich, z.B. bei
        # zwei Ladestopps auf einem Roadtrip vor dem ersten Bestaetigen) —
        # neue Ladungen werden angehaengt, nie ueberschrieben.
        pend["config_entry_id"] = self.entry.entry_id
        self.data.setdefault("pending", []).append(pend)
        await self._save()
        await self._publish(self._opt(CONF_PUBLISH_TOPIC, self._default_publish_topic), pend, retain=False)
        self.hass.bus.async_fire(EVENT_PENDING, pend)
        await self._notify()
        self.async_set_updated_data(self.data)

    async def _publish(self, topic: str, payload: dict, retain: bool) -> None:
        try:
            await mqtt.async_publish(self.hass, topic, json.dumps(payload), qos=1, retain=retain)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("MQTT publish auf %s fehlgeschlagen: %s", topic, err)

    async def _notify(self) -> None:
        """Baut EINE Benachrichtigung (gleiche notification_id, ersetzt sich
        selbst) fuer ALLE aktuell offenen Fremdladungen — nicht pro Ladung
        einzeln, sonst wuerden mehrere Notifications mit derselben ID sich
        gegenseitig ueberschreiben und nur die letzte waere sichtbar."""
        pending_list = self.data.get("pending") or []
        if not pending_list:
            return
        if len(pending_list) == 1:
            p = pending_list[0]
            title = "Fremdladung erkannt"
            message = (
                f"+{p['delta_soc']} % ({p['soc_start']} -> {p['soc_end']} %), "
                f"~{round(p['energy_kwh'], 1)} kWh geschätzt. kWh und Preis eintragen."
            )
        else:
            title = f"{len(pending_list)} Fremdladungen erkannt"
            lines = [
                f"{i + 1}) +{p['delta_soc']} % ({p['soc_start']} -> {p['soc_end']} %), "
                f"~{round(p['energy_kwh'], 1)} kWh"
                for i, p in enumerate(pending_list)
            ]
            message = f"{len(pending_list)} offene Fremdladungen:\n" + "\n".join(lines) + "\nkWh und Preis eintragen."

        notify_service = self._opt(CONF_NOTIFY_SERVICE)
        if notify_service:
            try:
                await self.hass.services.async_call(
                    "notify", notify_service,
                    {
                        "title": title,
                        "message": message,
                        "data": {
                            "tag": self._notify_tag,
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
                {"notification_id": self._notify_tag, "title": title, "message": message},
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass

    async def async_log_charge(self, kwh: float, price: float, start_ts: Optional[float] = None) -> None:
        """Bestaetigt eine offene Fremdladung. Bei mehreren gleichzeitig
        offenen waehlt `start_ts` die gemeinte aus; ohne Angabe wird die
        aelteste bestaetigt (FIFO)."""
        kwh = round(float(kwh), 2)
        price = round(float(price), 4)
        rec = {
            "config_entry_id": self.entry.entry_id,
            "kwh": kwh, "preis_kwh": price, "kosten": round(kwh * price, 2),
            "erfasst_ts": int(time.time()),
        }
        pending_list = list(self.data.get("pending") or [])
        pend = pop_pending(pending_list, start_ts)
        if pend:
            rec.update({
                "start_ts": pend.get("start_ts"), "soc_start": pend.get("soc_start"),
                "soc_end": pend.get("soc_end"), "delta_soc": pend.get("delta_soc"),
                "schaetzung_kwh": pend.get("energy_kwh"), "quelle": pend.get("energy_source"),
            })
        elif start_ts is not None:
            rec["start_ts"] = start_ts
        self.data["pending"] = pending_list

        self.data.setdefault("history", []).insert(0, rec)
        self.data["history"] = self.data["history"][:HISTORY_MAX]
        totals = self.data["totals"]
        totals["kwh"] = round(totals.get("kwh", 0.0) + kwh, 2)
        totals["kosten"] = round(totals.get("kosten", 0.0) + rec["kosten"], 2)
        totals["count"] = totals.get("count", 0) + 1
        self.data["last_price"] = price
        await self._save()
        await self._publish(self._opt(CONF_PUBLISH_TOPIC, self._default_publish_topic) + "/erfasst", rec, retain=True)
        self.hass.bus.async_fire(EVENT_LOGGED, rec)
        if pending_list:
            await self._notify()
        else:
            await self._dismiss()
        self.async_set_updated_data(self.data)

    async def async_edit_charge(self, erfasst_ts: int, kwh: float, price: float) -> bool:
        """Korrigiert einen bereits bestaetigten Historien-Eintrag (z.B.
        Tippfehler bei kWh/Preis beim Erfassen bemerkt). Passt die
        laufenden Summen um die Differenz an statt sie aus der Historie neu
        zu berechnen, da aeltere, nicht mehr in der Historie gespeicherte
        Eintraege (siehe HISTORY_MAX) sonst aus den Summen herausfallen
        wuerden. Gibt False zurueck, wenn kein Eintrag mit erfasst_ts
        gefunden wurde."""
        history = self.data.get("history") or []
        for rec in history:
            if rec.get("erfasst_ts") == erfasst_ts:
                old_kwh = rec["kwh"]
                old_kosten = rec["kosten"]
                kwh = round(float(kwh), 2)
                price = round(float(price), 4)
                kosten = round(kwh * price, 2)
                totals = self.data["totals"]
                totals["kwh"] = round(totals.get("kwh", 0.0) - old_kwh + kwh, 2)
                totals["kosten"] = round(totals.get("kosten", 0.0) - old_kosten + kosten, 2)
                rec["kwh"] = kwh
                rec["preis_kwh"] = price
                rec["kosten"] = kosten
                if history[0] is rec:
                    self.data["last_price"] = price
                await self._save()
                self.hass.bus.async_fire(EVENT_EDITED, rec)
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_delete_charge(self, erfasst_ts: int) -> bool:
        """Loescht einen bereits bestaetigten Historien-Eintrag vollstaendig
        (z.B. eine faelschlich erkannte Fremdladung, die gar keine war).
        Passt die laufenden Summen um den geloeschten Betrag an; war der
        geloeschte Eintrag der juengste, wird last_price auf den neuen
        juengsten Eintrag zurueckgesetzt (oder 0.0, falls die Historie
        danach leer ist). Gibt False zurueck, wenn kein Eintrag mit
        erfasst_ts gefunden wurde."""
        history = self.data.get("history") or []
        for i, rec in enumerate(history):
            if rec.get("erfasst_ts") == erfasst_ts:
                was_newest = i == 0
                history.pop(i)
                totals = self.data["totals"]
                totals["kwh"] = round(totals.get("kwh", 0.0) - rec["kwh"], 2)
                totals["kosten"] = round(totals.get("kosten", 0.0) - rec["kosten"], 2)
                totals["count"] = max(0, totals.get("count", 0) - 1)
                if was_newest:
                    self.data["last_price"] = history[0]["preis_kwh"] if history else 0.0
                await self._save()
                self.hass.bus.async_fire(EVENT_DELETED, rec)
                self.async_set_updated_data(self.data)
                return True
        return False

    async def async_discard(self, start_ts: Optional[float] = None) -> None:
        """Verwirft eine offene Fremdladung. Bei mehreren gleichzeitig
        offenen waehlt `start_ts` die gemeinte aus; ohne Angabe wird die
        aelteste verworfen (FIFO)."""
        pending_list = list(self.data.get("pending") or [])
        pop_pending(pending_list, start_ts)
        self.data["pending"] = pending_list
        await self._save()
        if pending_list:
            await self._notify()
        else:
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
                "persistent_notification", "dismiss", {"notification_id": self._notify_tag}, blocking=False
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
