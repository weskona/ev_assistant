"""Ladekarten (Abo-Karten von Fremdlade-Anbietern): Verwaltung, Preisstufen, Kosten.

Aus coordinator.py ausgelagert (Umbau vor der 1.0, siehe Issue #12). Der Zustand
(data['ladekarten']) bleibt im Coordinator ("host"); diese Klasse haelt keinen
eigenen Zustand. Die oeffentlichen Methoden des Coordinators bestehen unveraendert
und rufen hierher durch.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from homeassistant.util import dt as dt_util

from .const import LADEKARTE_AVG_DAYS_PER_MONTH
from .engine import ladekarte_legacy_gebuehren, ladekarten_summary

if TYPE_CHECKING:
    from .coordinator import EvAssistantCoordinator


class ChargeCards:
    """Ladekarten fuer genau einen Coordinator (siehe Modul-Docstring)."""

    def __init__(self, host: EvAssistantCoordinator) -> None:
        self._host = host

    async def async_add_ladekarte(
        self, name: str, monatliche_gebuehr: float, start_datum: str,
        end_datum: Optional[str] = None,
    ) -> None:
        """Legt eine neue Ladekarte an -- reiner Kostenposten (siehe
        engine.ladekarte_accrued_cost()), keine Verknuepfung mit
        Fremdladungen noetig (die optionale karte_id auf einzelnen
        Ladungen, siehe async_log_charge(), ist rein informativ). id ist
        ein simpler Millisekunden-Zeitstempel -- analog erfasst_ts bei
        Fremdladungen/Fahrten, hier ausreichend, da Karten einzeln von
        Hand angelegt werden (kein Tight-Loop-Kollisionsrisiko wie beim
        Bulk-Import von Fahrten). `monatliche_gebuehr` wird als erste
        Gebuehrenstufe ab `start_datum` gespeichert (siehe "gebuehren" in
        engine.ladekarte_accrued_cost()) -- weitere Stufen (z.B. Ende eines
        reduzierten Einfuehrungspreises) kommen ueber
        async_add_ladekarte_preisstufe() dazu."""
        host = self._host
        karte = {
            "id": int(time.time() * 1000),
            "name": name.strip(),
            "gebuehren": [{"ab_datum": start_datum, "gebuehr": round(float(monatliche_gebuehr), 2)}],
            "start_datum": start_datum,
            "end_datum": end_datum,
        }
        karten = list(host.data.get("ladekarten") or [])
        karten.append(karte)
        host.data["ladekarten"] = karten
        await host._save()
        host.async_set_updated_data(host.data)

    @staticmethod
    def _ladekarte_gebuehren(karte: dict) -> list:
        """Gebuehrenstufen einer Karte, mit Ruecklauf-Kompatibilitaet fuer
        Karten aus der Zeit vor Gebuehrenstufen (siehe engine.
        ladekarte_legacy_gebuehren()) -- gibt IMMER die tatsaechliche Liste
        zurueck (nicht nur zur Berechnung wie im engine-Pendant), damit
        Schreibzugriffe (Stufe hinzufuegen/loeschen) sie direkt mutieren
        koennen."""
        gebuehren = karte.get("gebuehren")
        if not gebuehren:
            gebuehren = ladekarte_legacy_gebuehren(karte)
            karte["gebuehren"] = gebuehren
        return gebuehren

    async def async_edit_ladekarte(
        self,
        karte_id: int,
        name: Optional[str] = None,
        monatliche_gebuehr: Optional[float] = None,
        start_datum: Optional[str] = None,
        end_datum: Optional[str] = None,
    ) -> bool:
        """Korrigiert eine bestehende Ladekarte -- alle Felder optional,
        nur mitgegebene Werte werden geaendert (analog async_edit_charge()).
        end_datum: None laesst das Feld unveraendert, ein LEERER String
        loescht ein zuvor gesetztes Enddatum (z.B. eine gekuendigte Karte
        reaktivieren) -- unterscheidbar, weil ein Service-Aufruf ohne
        end_datum-Feld ueberhaupt None liefert, waehrend ein explizit
        geleertes Formularfeld "" liefert. monatliche_gebuehr korrigiert die
        Gebuehr der ZEITLICH FRUEHESTEN Stufe (typischerweise ein Tippfehler
        beim Anlegen) -- ein PREISWECHSEL (z.B. Ende eines reduzierten
        Einfuehrungspreises) laeuft stattdessen ueber
        async_add_ladekarte_preisstufe(), da hier nicht klar waere, welche
        von mehreren Stufen gemeint ist. Gibt False zurueck, wenn keine
        Karte mit dieser id gefunden wurde."""
        host = self._host
        karten = host.data.get("ladekarten") or []
        for karte in karten:
            if karte.get("id") == karte_id:
                if name is not None:
                    karte["name"] = name.strip()
                if monatliche_gebuehr is not None:
                    gebuehren = self._ladekarte_gebuehren(karte)
                    if gebuehren:
                        fruehste = min(gebuehren, key=lambda s: s.get("ab_datum") or "")
                        fruehste["gebuehr"] = round(float(monatliche_gebuehr), 2)
                if start_datum is not None:
                    karte["start_datum"] = start_datum
                if end_datum is not None:
                    karte["end_datum"] = end_datum or None
                await host._save()
                host.async_set_updated_data(host.data)
                return True
        return False

    async def async_add_ladekarte_preisstufe(self, karte_id: int, gebuehr: float, ab_datum: str) -> bool:
        """Fuegt einer bestehenden Ladekarte eine neue Gebuehrenstufe hinzu
        (siehe engine.ladekarte_accrued_cost()) -- z.B. wenn ein reduzierter
        Einfuehrungspreis nach einigen Monaten auf den regulaeren Preis
        steigt. Existiert bereits eine Stufe mit exakt diesem ab_datum,
        wird deren Gebuehr ersetzt statt eine doppelte Stufe anzulegen
        (Korrektur eines Tippfehlers bei einem bereits erfassten
        Preiswechsel). Gibt False zurueck, wenn keine Karte mit dieser id
        gefunden wurde."""
        host = self._host
        karten = host.data.get("ladekarten") or []
        for karte in karten:
            if karte.get("id") == karte_id:
                gebuehren = self._ladekarte_gebuehren(karte)
                for stufe in gebuehren:
                    if stufe.get("ab_datum") == ab_datum:
                        stufe["gebuehr"] = round(float(gebuehr), 2)
                        break
                else:
                    gebuehren.append({"ab_datum": ab_datum, "gebuehr": round(float(gebuehr), 2)})
                await host._save()
                host.async_set_updated_data(host.data)
                return True
        return False

    async def async_delete_ladekarte_preisstufe(self, karte_id: int, ab_datum: str) -> bool:
        """Entfernt eine Gebuehrenstufe wieder (siehe
        async_add_ladekarte_preisstufe()) -- z.B. eine versehentlich
        angelegte. Die zeitlich fruehste Stufe kann nicht geloescht werden
        (eine Karte braucht immer mindestens eine bekannte Gebuehr, siehe
        engine.ladekarte_accrued_cost()) -- der Aufruf gibt dafuer False
        zurueck, genau wie wenn Karte oder Stufe nicht gefunden wurden."""
        host = self._host
        karten = host.data.get("ladekarten") or []
        for karte in karten:
            if karte.get("id") == karte_id:
                gebuehren = self._ladekarte_gebuehren(karte)
                if len(gebuehren) <= 1:
                    return False
                fruehste = min(gebuehren, key=lambda s: s.get("ab_datum") or "")
                if fruehste.get("ab_datum") == ab_datum:
                    return False
                for i, stufe in enumerate(gebuehren):
                    if stufe.get("ab_datum") == ab_datum:
                        gebuehren.pop(i)
                        await host._save()
                        host.async_set_updated_data(host.data)
                        return True
                return False
        return False

    async def async_delete_ladekarte(self, karte_id: int) -> bool:
        """Loescht eine Ladekarte vollstaendig. Bereits zugeordnete
        Fremdladungen (rec["karte_id"], siehe async_log_charge()) behalten
        ihre Referenz -- eine verwaiste karte_id wird beim Anzeigen einfach
        ignoriert, nicht rueckwirkend aus der Historie entfernt. Gibt False
        zurueck, wenn keine Karte mit dieser id gefunden wurde."""
        host = self._host
        karten = host.data.get("ladekarten") or []
        for i, karte in enumerate(karten):
            if karte.get("id") == karte_id:
                karten.pop(i)
                await host._save()
                host.async_set_updated_data(host.data)
                return True
        return False

    def _ladekarten_cost_total(self) -> float:
        """Aufgelaufene Summe aller Ladekarten-Grundgebuehren bis heute
        (siehe engine.ladekarten_summary()) -- 0.0 ohne jede Karte. Eigene
        Methode statt Inline-Code, da mehrere Stellen (_ev_cost_total_
        since_setup(), savings(), charging_location_stats()) sie
        brauchen."""
        return self.ladekarten_stats().get("gesamt", 0.0)

    def ladekarten_stats(self) -> dict:
        """Ladekarten-Uebersicht (siehe engine.ladekarten_summary()) --
        leeres dict ohne jede angelegte Karte (macht das Feature komplett
        inaktiv/unsichtbar, analog leasing_stats()). Absichtlich UNGECACHT:
        die Berechnung ist trivial billig (kurze Liste, reine Datums-
        arithmetik), anders als z.B. rolling_km_per_day() bei leasing_stats()."""
        host = self._host
        karten = host.data.get("ladekarten") or []
        if not karten:
            return {}
        heute = dt_util.now().date().isoformat()
        return ladekarten_summary(karten, heute, LADEKARTE_AVG_DAYS_PER_MONTH)
