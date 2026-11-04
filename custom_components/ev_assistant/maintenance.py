"""Wartungsplan: Anlegen, Bearbeiten, Loeschen, Faelligkeit, Erinnerungen, Migrationen.

Aus coordinator.py ausgelagert (Umbau vor der 1.0, siehe Issue #12). Der Zustand
(data['wartung'] u. a.) bleibt im Coordinator ("host"); diese Klasse haelt keinen
eigenen Zustand. Die oeffentlichen Methoden des Coordinators bestehen unveraendert
und rufen hierher durch.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from homeassistant.util import dt as dt_util

from .const import (
    NOTIFY_EVENT_WARTUNG,
    WARTUNG_BALD_FAELLIG_KM,
    WARTUNG_BALD_FAELLIG_TAGE,
    WARTUNG_PRESETS,
    WARTUNG_ROLLING_WINDOW_DAYS,
    WARTUNG_TAGE_PRO_MONAT,
)
from .engine import rolling_km_per_day, wartung_festes_datum_fortschreiben, wartung_uebersicht

if TYPE_CHECKING:
    from .coordinator import EvAssistantCoordinator

_LOGGER = logging.getLogger(__name__)


# Rangfolge fuer die Hysterese in _check_wartung_thresholds() -- analog
# _LEASING_STATUS_RANK (leasing.py), aber je Wartungspunkt-id einzeln gefuehrt (siehe
# self.data["wartung_notified"]) statt einmal global wie beim Leasing-Vertrag.
_WARTUNG_STATUS_RANK = {"ok": 0, "unbekannt": 0, "bald_faellig": 1, "ueberfaellig": 2}


class Maintenance:
    """Wartungsplan fuer genau einen Coordinator (siehe Modul-Docstring)."""

    def __init__(self, host: EvAssistantCoordinator) -> None:
        self._host = host

    def _migrate_wartung_zeit_einheiten(self) -> bool:
        """Einmalige Migration bestehender Wartungspunkte von
        zeit_intervall_tage (Tage, vor der Umstellung auf Monats-Intervalle)
        auf zeit_intervall_monate (siehe engine.wartung_status()). Tage
        lassen sich nicht exakt auf Kalendermonate abbilden -- gerundet
        ueber WARTUNG_TAGE_PRO_MONAT (fuer die alten glatten Presets, z.B.
        730 Tage, ergibt das exakt 24 Monate). Idempotent OHNE eigenes
        Flag: nach dem ersten Lauf existiert kein zeit_intervall_tage mehr,
        ein zweiter Lauf findet also nichts mehr zu tun. Gibt True zurueck,
        wenn mindestens ein Punkt migriert wurde (der Aufrufer muss dann
        sofort speichern, siehe async_setup())."""
        host = self._host
        geaendert = False
        for punkt in host.data.get("wartung") or []:
            if "zeit_intervall_tage" not in punkt:
                continue
            alte_tage = punkt.pop("zeit_intervall_tage")
            if alte_tage:
                punkt["zeit_intervall_monate"] = max(1, round(alte_tage / WARTUNG_TAGE_PRO_MONAT))
            geaendert = True
        return geaendert

    def _migrate_wartung_erledigt_anzahl(self) -> bool:
        """Einmalige Migration (Issue #48): Wartungspunkte ohne Erledigt-
        Zaehler bekommen `erledigt_anzahl` = 1, wenn sie ein last_done haben,
        sonst 0. So aendert sich bei Bestandspunkten nichts, auch wenn spaeter
        ein Erstintervall eingetragen wird (ein reines Startwert-last_done
        zaehlt dann als erledigt, korrigierbar ueber edit_maintenance).
        Idempotent ohne Flag: nach dem ersten Lauf tragen alle Punkte den
        Zaehler. Gibt True zurueck, wenn etwas geaendert wurde."""
        host = self._host
        geaendert = False
        for punkt in host.data.get("wartung") or []:
            if "erledigt_anzahl" not in punkt:
                punkt["erledigt_anzahl"] = 1 if punkt.get("last_done") else 0
                geaendert = True
        return geaendert

    def _migrate_wartung_hu_typ(self) -> bool:
        """Einmalige Migration bestehender HU/TUEV-Wartungspunkte von vor
        Einfuehrung des "typ"-Markers (siehe async_add_maintenance()) --
        erkannt am WOERTLICHEN historischen Namen "HU/TÜV" (Presets wurden
        vor diesem Feld nicht am Punkt gespeichert, nur beim Anlegen
        gelesen). Bewusst der feste Alt-Name statt WARTUNG_PRESETS["tuev"]
        ["name"] -- die Vorlage heisst inzwischen nur noch "HU" (siehe
        _migrate_wartung_hu_name() unten), Bestandspunkte aus der Zeit davor
        tragen aber noch woertlich "HU/TÜV". Bewusst nur HU/TUEV betroffen:
        Inspektion/freie Punkte brauchen keinen Marker, da das Panel-
        Bearbeiten-Formular "kein typ" identisch zu "nicht HU" behandelt
        (alle Felder zeigen) -- also unveraendertes Verhalten fuer sie.
        Idempotent OHNE eigenes Flag: nach dem ersten Lauf tragen migrierte
        Punkte "typ", ein zweiter Lauf findet dort nichts mehr zu tun. Gibt
        True zurueck, wenn mindestens ein Punkt migriert wurde (der
        Aufrufer muss dann sofort speichern, siehe async_setup())."""
        host = self._host
        geaendert = False
        for punkt in host.data.get("wartung") or []:
            if "typ" not in punkt and punkt.get("name") == "HU/TÜV":
                punkt["typ"] = "tuev"
                geaendert = True
        return geaendert

    def _migrate_wartung_hu_name(self) -> bool:
        """Einmalige Umbenennung bestehender HU-Punkte von "HU/TÜV" auf das
        seitdem kuerzere Preset "HU" (siehe const.py::WARTUNG_PRESETS).
        Laeuft NACH _migrate_wartung_hu_typ() (siehe async_setup()), damit
        ein Punkt, der in genau diesem Setup-Durchlauf erst seinen "typ"-
        Marker bekommen hat, hier sofort mit erfasst wird. Nur Punkte mit
        typ == "tuev" UND dem woertlichen Alt-Namen -- ein frei benannter
        Punkt, der zufaellig "HU/TÜV" heisst, aber kein HU-Preset-Punkt ist
        (kein typ), bleibt unangetastet; ein HU-Punkt, den der Nutzer selbst
        schon anders umbenannt hat, ebenso (dessen Name ist dann nicht mehr
        der woertliche Alt-Name). Idempotent OHNE eigenes Flag: nach dem
        ersten Lauf lautet der Name nicht mehr "HU/TÜV", ein zweiter Lauf
        findet nichts mehr zu tun."""
        host = self._host
        geaendert = False
        for punkt in host.data.get("wartung") or []:
            if punkt.get("typ") == "tuev" and punkt.get("name") == "HU/TÜV":
                punkt["name"] = WARTUNG_PRESETS["tuev"]["name"]
                geaendert = True
        return geaendert

    async def async_add_maintenance(
        self,
        name: Optional[str] = None,
        preset: Optional[str] = None,
        km_intervall: Optional[float] = None,
        zeit_intervall_monate: Optional[int] = None,
        festes_datum: Optional[str] = None,
        kosten: Optional[float] = None,
        last_done_km: Optional[float] = None,
        last_done_datum: Optional[str] = None,
        reminder_monate: Optional[float] = None,
        reminder_km: Optional[float] = None,
        erst_km_intervall: Optional[float] = None,
        erst_zeit_intervall_monate: Optional[int] = None,
    ) -> Optional[int]:
        """Legt einen neuen Wartungspunkt an (siehe engine.wartung_status()
        fuer die Faelligkeitsberechnung) -- id ist ein simpler Millisekunden-
        Zeitstempel, analog async_add_ladekarte(). `preset` referenziert
        optional eine Vorlage (siehe const.py::WARTUNG_PRESETS, z.B. "tuev"):
        liefert deren km_intervall/zeit_intervall_monate/name als FALLBACK,
        wo das jeweilige Feld hier nicht explizit gesetzt ist -- Presets
        sind nur Startwerte, jedes einzeln ueberschreibbar. `last_done_km`/
        `last_done_datum` seeden optional einen bereits in der Vergangenheit
        liegenden letzten Service (z.B. beim Nacherfassen eines Termins von
        vor ein paar Monaten) -- fuer den Normalfall "gerade erledigt" siehe
        stattdessen async_mark_maintenance_done(). `reminder_monate`/
        `reminder_km` ueberschreiben pro Punkt die globalen
        WARTUNG_BALD_FAELLIG_TAGE/-_KM-Schwellen (siehe
        engine.wartung_uebersicht()) -- `reminder_monate` wird EINMALIG ueber
        WARTUNG_TAGE_PRO_MONAT in Tage umgerechnet und als reminder_tage
        gespeichert (die Schwelle selbst braucht keine Kalenderpraezision,
        anders als zeit_intervall_monate).

        `erst_km_intervall`/`erst_zeit_intervall_monate` (Issue #48) ersetzen
        das regulaere Intervall, solange der Punkt noch nie erledigt wurde
        (`erledigt_anzahl` 0, siehe engine.wartung_status()) -- z.B. erste
        Inspektion nach 12.500 km, danach alle 25.000 km. Zaehlen nicht als
        eigenes Faelligkeitskriterium.

        Ohne Namen (auch nicht aus dem Preset) oder ohne mindestens ein
        Faelligkeitskriterium (km_intervall/zeit_intervall_monate/
        festes_datum, auch nach Preset-Vorbefuellung) wird NICHTS angelegt
        (Warnung im Log, analog async_log_trip() ohne offene Fahrt) -- ein
        Wartungspunkt ganz ohne jedes Kriterium waere nie faellig und daher
        sinnlos. Gibt die neue id zurueck, oder None bei Ablehnung."""
        host = self._host
        vorlage = WARTUNG_PRESETS.get(preset, {}) if preset else {}
        effektiver_name = (name or vorlage.get("name") or "").strip()
        effektiv_km = km_intervall if km_intervall is not None else vorlage.get("km_intervall")
        effektiv_zeit = (
            zeit_intervall_monate if zeit_intervall_monate is not None else vorlage.get("zeit_intervall_monate")
        )
        effektiv_fest = festes_datum if festes_datum is not None else vorlage.get("festes_datum")
        if not effektiver_name:
            _LOGGER.warning("ev_assistant: Wartungspunkt ohne Namen (auch nicht aus Preset) abgelehnt")
            return None
        if not (effektiv_km or effektiv_zeit or effektiv_fest):
            _LOGGER.warning(
                "ev_assistant: Wartungspunkt '%s' ohne jedes Faelligkeitskriterium abgelehnt", effektiver_name
            )
            return None
        punkt = {
            "id": int(time.time() * 1000),
            "name": effektiver_name,
            # Roher preset-Wert (z.B. "tuev"/"inspektion"), None ohne Preset --
            # anders als vorlage/effektiv_* oben (nur transiente Default-
            # Quelle) bleibt dieser Marker dauerhaft am Punkt erhalten, damit
            # das Panel-Bearbeiten-Formular praesetabhaengige Felder (z.B.
            # kein km bei HU) rendern kann, ohne aus den gesetzten Kriterien
            # raten zu muessen (siehe _migrate_wartung_hu_typ() fuer
            # Bestandseintraege von vor diesem Feld).
            "typ": preset,
            "km_intervall": effektiv_km,
            "zeit_intervall_monate": effektiv_zeit,
            "festes_datum": effektiv_fest,
            "last_done": (
                {"km": last_done_km, "datum": last_done_datum}
                if last_done_km is not None or last_done_datum is not None else None
            ),
            "kosten": kosten,
            "aktiv": True,
            "reminder_tage": round(reminder_monate * WARTUNG_TAGE_PRO_MONAT, 1) if reminder_monate is not None else None,
            "reminder_km": reminder_km,
            "erst_km_intervall": erst_km_intervall or None,
            "erst_zeit_intervall_monate": erst_zeit_intervall_monate or None,
            "erledigt_anzahl": 0,
        }
        punkte = list(host.data.get("wartung") or [])
        punkte.append(punkt)
        host.data["wartung"] = punkte
        await host._save()
        host.async_set_updated_data(host.data)
        return punkt["id"]

    async def async_edit_maintenance(
        self,
        wartung_id: int,
        name: Optional[str] = None,
        km_intervall: Optional[float] = None,
        zeit_intervall_monate: Optional[int] = None,
        festes_datum: Optional[str] = None,
        kosten: Optional[float] = None,
        last_done_km: Optional[float] = None,
        last_done_datum: Optional[str] = None,
        aktiv: Optional[bool] = None,
        reminder_monate: Optional[float] = None,
        reminder_km: Optional[float] = None,
        erst_km_intervall: Optional[float] = None,
        erst_zeit_intervall_monate: Optional[int] = None,
        erledigt_anzahl: Optional[int] = None,
    ) -> bool:
        """Korrigiert einen bestehenden Wartungspunkt -- alle Felder
        optional, nur mitgegebene Werte werden geaendert (analog
        async_edit_ladekarte()). km_intervall/zeit_intervall_monate/
        festes_datum/kosten/reminder_monate/reminder_km: None laesst das
        Feld unveraendert, ein LEERER STRING loescht ein zuvor gesetztes
        Kriterium (bzw. die Kosten/den Reminder-Override) wieder -- z.B. um
        von "km ODER Zeit" auf nur noch "Zeit" umzustellen. Nach Anwenden
        aller Aenderungen muss mindestens ein Faelligkeitskriterium uebrig
        bleiben, sonst wird die GESAMTE Aenderung verworfen (Warnung, False)
        statt einen nutzlosen Wartungspunkt ohne jedes Kriterium zu
        erzeugen -- reminder_monate/reminder_km zaehlen dabei NICHT als
        Faelligkeitskriterium. `last_done_km`/`last_done_datum` korrigieren
        den zuletzt erfassten Service direkt (z.B. ein Tippfehler) -- fuer
        "gerade jetzt erledigt" siehe async_mark_maintenance_done(). Gibt
        False zurueck, wenn keine id gefunden wurde oder die Aenderung
        mangels Kriterium verworfen wurde. `erst_km_intervall`/`erst_zeit_
        intervall_monate` (Erstintervall, Issue #48): leerer String loescht;
        `erledigt_anzahl` korrigiert den Erledigt-Zaehler (0 = Erstintervall
        gilt wieder, z.B. bei einem migrierten Punkt, dessen last_done nur ein
        Startwert war)."""
        host = self._host
        punkte = host.data.get("wartung") or []
        for punkt in punkte:
            if punkt.get("id") != wartung_id:
                continue
            alt = dict(punkt)
            if name is not None:
                punkt["name"] = name.strip()
            if km_intervall is not None:
                punkt["km_intervall"] = None if km_intervall == "" else float(km_intervall)
            if zeit_intervall_monate is not None:
                punkt["zeit_intervall_monate"] = None if zeit_intervall_monate == "" else int(zeit_intervall_monate)
            if festes_datum is not None:
                punkt["festes_datum"] = festes_datum or None
            if kosten is not None:
                punkt["kosten"] = None if kosten == "" else float(kosten)
            if reminder_monate is not None:
                punkt["reminder_tage"] = (
                    None if reminder_monate == "" else round(float(reminder_monate) * WARTUNG_TAGE_PRO_MONAT, 1)
                )
            if reminder_km is not None:
                punkt["reminder_km"] = None if reminder_km == "" else float(reminder_km)
            if erst_km_intervall is not None:
                punkt["erst_km_intervall"] = None if erst_km_intervall == "" else float(erst_km_intervall)
            if erst_zeit_intervall_monate is not None:
                punkt["erst_zeit_intervall_monate"] = (
                    None if erst_zeit_intervall_monate == "" else int(erst_zeit_intervall_monate)
                )
            if erledigt_anzahl is not None:
                punkt["erledigt_anzahl"] = max(0, int(erledigt_anzahl))
            if last_done_km is not None or last_done_datum is not None:
                last_done = dict(punkt.get("last_done") or {})
                if last_done_km is not None:
                    last_done["km"] = last_done_km
                if last_done_datum is not None:
                    last_done["datum"] = last_done_datum
                punkt["last_done"] = last_done
            if aktiv is not None:
                punkt["aktiv"] = aktiv
            if not (punkt.get("km_intervall") or punkt.get("zeit_intervall_monate") or punkt.get("festes_datum")):
                punkt.clear()
                punkt.update(alt)
                _LOGGER.warning(
                    "ev_assistant: Aenderung an Wartungspunkt '%s' verworfen -- kein Kriterium mehr uebrig",
                    alt.get("name"),
                )
                return False
            await host._save()
            host.async_set_updated_data(host.data)
            return True
        return False

    async def async_delete_maintenance(self, wartung_id: int) -> bool:
        """Loescht einen Wartungspunkt vollstaendig. Gibt False zurueck,
        wenn keine id gefunden wurde."""
        host = self._host
        punkte = host.data.get("wartung") or []
        for i, punkt in enumerate(punkte):
            if punkt.get("id") == wartung_id:
                punkte.pop(i)
                host.data.setdefault("wartung_notified", {}).pop(str(wartung_id), None)
                await host._save()
                host.async_set_updated_data(host.data)
                return True
        return False

    async def async_mark_maintenance_done(
        self, wartung_id: int, km: Optional[float] = None, datum: Optional[str] = None,
    ) -> bool:
        """Setzt last_done auf den aktuellen Kilometerstand + heute (oder
        auf `km`/`datum`, falls uebergeben -- z.B. um einen vor ein paar
        Tagen tatsaechlich durchgefuehrten Termin nachzutragen). Aendert
        last_done immer, auch wenn km/datum zufaellig mit dem vorherigen
        Stand uebereinstimmen sollten -- das setzt gleichzeitig die
        Benachrichtigungs-Hysterese fuer diesen Punkt zurueck (siehe
        _check_wartung_thresholds()). Hat der Punkt ZUSAETZLICH sowohl
        festes_datum als auch zeit_intervall_monate gesetzt (z.B. HU/TUEV:
        ein bekannter naechster Termin mit Wiederholungs-Intervall), wird
        festes_datum auf den naechsten Termin AB DIESEM Erledigungszeitpunkt
        fortgeschrieben (siehe engine.wartung_festes_datum_fortschreiben())
        -- bewusst auch bei einer VERFRUEHTEN Erledigung, die den Takt dann
        nach vorne zieht, statt den urspruenglichen Rhythmus beizubehalten.
        Gibt False zurueck, wenn keine id gefunden wurde."""
        host = self._host
        punkte = host.data.get("wartung") or []
        for punkt in punkte:
            if punkt.get("id") == wartung_id:
                effektiv_km = km if km is not None else host._odo_km()
                effektiv_datum = datum or dt_util.now().date().isoformat()
                punkt["last_done"] = {"km": effektiv_km, "datum": effektiv_datum}
                # Erledigt-Zaehler (Erstintervall, Issue #48): ab dem ersten
                # Erledigen gelten die regulaeren Intervalle.
                punkt["erledigt_anzahl"] = int(punkt.get("erledigt_anzahl") or 0) + 1
                neues_festes_datum = wartung_festes_datum_fortschreiben(
                    punkt.get("festes_datum"), punkt.get("zeit_intervall_monate"), effektiv_datum,
                )
                if neues_festes_datum is not None:
                    punkt["festes_datum"] = neues_festes_datum
                await host._save()
                host.async_set_updated_data(host.data)
                return True
        return False

    def wartung_stats(self) -> dict:
        """Faelligkeit aller Wartungspunkte (siehe engine.wartung_uebersicht()).
        Leeres dict ohne jeden Wartungspunkt (analog leasing_stats()).
        `km_pro_tag` kommt aus demselben rollierenden-Fenster-Prinzip wie
        die Leasing-Hochrechnung (rolling_km_per_day()), aber ueber eine
        eigene, isolierte Konstante (WARTUNG_ROLLING_WINDOW_DAYS) -- bewusst
        NICHT mit der bestehenden Leasing-Fensterkonstante geteilt/
        umbenannt, um deren getesteten Code nicht anzufassen."""
        host = self._host
        punkte = host.data.get("wartung") or []
        if not punkte:
            return {}
        fahrten = host.data.get("fahrten") or []
        km_pro_tag = rolling_km_per_day(fahrten, time.time(), WARTUNG_ROLLING_WINDOW_DAYS)
        heute = dt_util.now().date().isoformat()
        return wartung_uebersicht(
            punkte, host._odo_km(), km_pro_tag, heute,
            WARTUNG_BALD_FAELLIG_TAGE, WARTUNG_BALD_FAELLIG_KM,
        )

    def _check_wartung_thresholds(self) -> None:
        """Benachrichtigung, wenn ein Wartungspunkt erstmals "bald_faellig"
        oder "ueberfaellig" wird -- Hysterese analog
        _check_leasing_thresholds(), aber JE WARTUNGSPUNKT einzeln
        (host.data["wartung_notified"], keyed nach str(id)) statt einmal
        global: mehrere Wartungspunkte werden unabhaengig voneinander
        faellig. Der gespeicherte Zustand eines Punkts wird zurueckgesetzt,
        sobald sich dessen last_done aendert (z.B. durch
        async_mark_maintenance_done()/eine last_done-Korrektur) -- ein
        gerade erledigter Punkt verdient wieder eigene Benachrichtigungen
        ab "ok". Inaktive Punkte (siehe "aktiv") werden ignoriert.
        Geloeschte Punkte werden aus wartung_notified entfernt, sonst
        waechst es unbegrenzt mit toten ids."""
        host = self._host
        punkte = self.wartung_stats().get("punkte", [])
        notified = host.data.setdefault("wartung_notified", {})
        for punkt in punkte:
            if punkt.get("aktiv") is False:
                continue
            key = str(punkt["id"])
            identity = punkt.get("last_done")
            eintrag = notified.get(key)
            if eintrag is None or eintrag.get("identity") != identity:
                eintrag = {"identity": identity, "rank": 0}
                notified[key] = eintrag
            rang = _WARTUNG_STATUS_RANK.get(punkt.get("status"), 0)
            if rang <= eintrag["rank"]:
                continue
            eintrag["rank"] = rang
            if rang > 0:
                host.hass.async_create_task(self._notify_wartung(punkt))
        live_ids = {str(p["id"]) for p in punkte}
        for key in list(notified):
            if key not in live_ids:
                del notified[key]

    async def _notify_wartung(self, punkt: dict) -> None:
        """Push + persistent_notification, wenn ein Wartungspunkt
        "bald_faellig" oder "ueberfaellig" wird -- siehe
        _check_wartung_thresholds()."""
        host = self._host
        en = host._en()
        name = punkt.get("name") or "?"
        if punkt.get("status") == "ueberfaellig":
            title = f"Maintenance overdue: {name}" if en else f"Wartung ueberfaellig: {name}"
        else:
            title = f"Maintenance due soon: {name}" if en else f"Wartung bald faellig: {name}"
        rest_tage = punkt.get("rest_tage")
        rest_km = punkt.get("rest_km")
        if rest_tage is not None:
            message = f"Due in {rest_tage} day(s)." if en else f"Faellig in {rest_tage} Tag(en)."
        elif rest_km is not None:
            message = f"Due in {rest_km:.0f} km." if en else f"Faellig in {rest_km:.0f} km."
        else:
            message = "Check the maintenance tab for details." if en else "Details siehe Wartung-Tab."
        await host._push(NOTIFY_EVENT_WARTUNG, title, message)
        await host._persistent_notification(
            "create",
            {
                "notification_id": f"{host._notify_tag}_wartung_{punkt['id']}",
                "title": title, "message": message,
            },
        )
