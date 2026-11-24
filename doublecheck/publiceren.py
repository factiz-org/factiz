"""De publicatiedatabase (PLAN #33.1, SPECS E9.S1, B73): één bestand per release met alleen wat gepubliceerd mag worden.

Het lab schrijft dit bestand, de site (`factiz_site/`) leest het; geen van beide leent code van de ander. Wat erin
komt: checks waarvan de herkomst herverdeeld mag worden (Data Commons CC BY, en een bron met `herverdeelbaar = 1`), van
een toegelaten uitgever, bij een bewering die niet vaag is. Eén pagina per bewering; dezelfde bewering bij meer
redacties (een cluster) is één pagina. Nooit erin: iets wat een gebruiker instuurde, sleutels, meetgegevens,
artikeltekst, beelden of vingerafdrukken.

    python -m doublecheck.publiceren bouwen [--uit data/publicatie/<datum>] [--concepten]
    python -m doublecheck.publiceren controleren <publicatie.db> [--concepten]

Met `--concepten` gaan ook de dossiers mee die de PO nog niet goedkeurde, en de eigen factchecks die nog een concept
zijn (`content/redactie/`, #37.4): een voorbeeld voor de eigen computer, dat
`controleren` zonder die vlag weigert (PLAN #33.6, B73). Het voorbeeld komt in `data/voorbeeld/`, nooit tussen de
uitgaven in `data/publicatie/`.

De database van het lab wordt alleen gelezen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from doublecheck import hoofdletters as hl
from doublecheck import soortvorm as sv
from doublecheck.feed import HERDISTRIBUEERBAAR

WORTEL = Path(__file__).resolve().parent.parent
VOORBEELD = WORTEL / "data" / "voorbeeld"   # een bestand met concepten: voor de eigen computer, geen uitgave
SCHEMA_VERSIE = 21           # 21: elke vertaling in het zoekregister en de woordenlijst als tabel `woord` (#37.16); 20: voorlopige vertalingen met een banner (B93); 19: de zinnen van de wereldlijst per taal (#37.12 punt 5); 18: de wereldlijst, wat de redacties vonden en waar het rondging (#37.12, B91); 17: pagina's buiten zoekmachines om een privépersoon (#34.2bw); 16: de zoekvraag per factcheck (#34.2cf, B87); 15: het adres van een eigen check met jaar en maand, en de vertalingen die de redactie las (#37.11); 14: de begrippen van een dossier (#34.2ca) en wie het oordeel draagt (#34.2cc); 13: de eigen factchecks (#37.4, B82); 12: dezelfde bewering bij een andere redactie (#34.2bp); 11: een kolom per sitetaal, vijftien talen (#34.2be, B79); 2: thema's en land per pagina (#33.4); 3: dossiers (#33.6); 4: versies in een dossier;
#                              5: namen (#33.7); 6: de vertaalde woorden van een redactie en lijkt op (#34.2o, #34.2p);
#                              7: waarom het niet klopt, de punten van EUvsDisinfo (#34.2j, B77); 8: de andere
#                              schrijfwijzen van een naam volgens Wikidata, voor het zoeken (#34.2z); 9: een bewering
#                              in hoofdletters in normaal schrift, naast het citaat (#34.2ae); 10: de soort volgens de
#                              redactie en de vorm uit de woorden van de bewering (#34.2ak)
from doublecheck.sitetalen import BASIS as BASISTALEN, SITETALEN  # noqa: E402  (B74, B79)
RTL = frozenset({"ar", "fa", "he", "ur", "ps", "sd", "ug", "yi", "dv", "ckb"})
# Bronnen die nooit in een publicatie mogen staan, wat een register ook zegt (B13, B73).
NOOIT = frozenset({"route-a", "communitynotes", "factchecktools-api"})
MAX_ZELFDE = 10              # hoogstens zoveel pagina's met dezelfde bewering per pagina (#34.2bp)
# de naam van een uitgave: de dag, en een letter voor een tweede op dezelfde dag (2026-11-16b); de naam van haar D1-database
# is factiz-<naam>, dus nooit twee keer dezelfde (#34.2bp)
RELEASE = re.compile(r"\d{4}-\d{2}-\d{2}[a-z]?")


def releasenaam(waarde: str | None = None) -> str:
    """De naam van een nieuwe uitgave: vandaag, of wat er gevraagd is als het die vorm heeft."""
    naam = waarde or date.today().isoformat()
    if not RELEASE.fullmatch(naam):
        raise Weigering(f"een uitgave heet naar haar dag, met hoogstens een letter erachter: {naam!r}")
    return naam
TABELLEN = ("bron", "thema", "land", "pagina", "formulering", "check_", "verwijzing", "opgedoken", "vertaling",
            "dossier", "dossier_item", "dossier_verwant", "naam", "pagina_naam", "naam_vorm", "oordeel_glos", "lijkt_op",
            "zelfde", "waarom", "bewering_normaal", "kenmerk", "eigen_check", "dossier_begrip", "zoekvraag", "afscherming",
            "samenvatting", "woord")
# De talen van de site zonder spaties tussen de woorden: hun vertalingen gaan ook in het register op drietallen (`zoek3`),
# want daar zoekt een vraag in zo'n schrift (`db._zoekbron`, #37.16).
ZONDER_SPATIES = ("ja", "zh")
ITEMSOORTEN = ("factcheck", "pers", "onderzoek", "besluit", "rapport")
DATACOMMONS = {
    "bron": HERDISTRIBUEERBAAR,
    "naam": "Data Commons, Fact Check Markup Tool data feed",
    # In het Engels: deze twee regels staan op elke taal van de site, onvertaald, zoals een licentie hoort.
    "licentie": "CC BY 4.0. Factiz added the language, the verdict category and the grouping of the same claim",
    "naamsvermelding": "Data Commons (ClaimReview feed), with the fact-check of the newsroom named",
    "url": "https://datacommons.org/factcheck/download",
}

def _kolommen(veld: str, leeg_mag: bool = False) -> str:
    """Een kolom per sitetaal (#34.2be, B79): naam_en, naam_nl, …, in de volgorde van SITETALEN."""
    return ", ".join(f"{veld}_{taal} TEXT NOT NULL" + (" DEFAULT ''" if leeg_mag else "") for taal in SITETALEN)


def _plekken(n: int) -> str:
    return "(" + ",".join("?" * n) + ")"


SCHEMA = f"""
CREATE TABLE meta (sleutel TEXT PRIMARY KEY, waarde TEXT NOT NULL) STRICT;
CREATE TABLE bron (
    bron TEXT PRIMARY KEY, naam TEXT NOT NULL, licentie TEXT NOT NULL CHECK (licentie <> ''),
    naamsvermelding TEXT NOT NULL CHECK (naamsvermelding <> ''), url TEXT NOT NULL) STRICT;
CREATE TABLE thema (
    sleutel TEXT PRIMARY KEY, ouder TEXT REFERENCES thema(sleutel), volg INTEGER NOT NULL, {_kolommen('naam')}) STRICT;
CREATE TABLE land (
    code TEXT PRIMARY KEY, {_kolommen('naam')}) STRICT;
CREATE TABLE pagina (
    nummer TEXT PRIMARY KEY, bewering TEXT NOT NULL, taal TEXT NOT NULL,
    richting TEXT NOT NULL CHECK (richting IN ('ltr', 'rtl')), label TEXT, eerder TEXT NOT NULL,
    checks INTEGER NOT NULL CHECK (checks >= 1), redacties INTEGER NOT NULL, talen TEXT NOT NULL,
    eerste_datum TEXT NOT NULL, laatste_datum TEXT NOT NULL,
    thema TEXT REFERENCES thema(sleutel), onderdeel TEXT NOT NULL DEFAULT '', tweede TEXT NOT NULL DEFAULT '',
    land TEXT NOT NULL DEFAULT '', volgens TEXT NOT NULL DEFAULT '[]') STRICT;
CREATE TABLE formulering (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), nummer TEXT NOT NULL, tekst TEXT NOT NULL, taal TEXT NOT NULL,
    richting TEXT NOT NULL CHECK (richting IN ('ltr', 'rtl')), PRIMARY KEY (pagina, nummer)) STRICT;
CREATE TABLE check_ (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), volg INTEGER NOT NULL, redactie TEXT NOT NULL,
    oordeel TEXT NOT NULL, oordeel_eigen TEXT NOT NULL, datum TEXT NOT NULL, taal TEXT NOT NULL, url TEXT NOT NULL,
    link TEXT NOT NULL, archief_url TEXT, archief_datum TEXT, bron TEXT NOT NULL REFERENCES bron(bron),
    PRIMARY KEY (pagina, volg)) STRICT;
CREATE TABLE verwijzing (nummer TEXT PRIMARY KEY, pagina TEXT NOT NULL REFERENCES pagina(nummer)) STRICT;
CREATE TABLE opgedoken (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), naam TEXT NOT NULL, soort TEXT NOT NULL, niveau TEXT NOT NULL,
    bron TEXT NOT NULL REFERENCES bron(bron), datum TEXT NOT NULL, url TEXT NOT NULL) STRICT;
CREATE TABLE vertaling (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), taal TEXT NOT NULL, tekst TEXT NOT NULL, maker TEXT NOT NULL,
    nagelezen INTEGER NOT NULL DEFAULT 0, voorlopig INTEGER NOT NULL DEFAULT 0 CHECK (voorlopig IN (0, 1)),
    PRIMARY KEY (pagina, taal)) STRICT;
CREATE TABLE bewering_normaal (pagina TEXT PRIMARY KEY REFERENCES pagina(nummer), tekst TEXT NOT NULL) STRICT;
CREATE TABLE zoekvraag (
    pagina TEXT PRIMARY KEY REFERENCES pagina(nummer), taal TEXT NOT NULL, vraag TEXT NOT NULL CHECK (vraag <> ''),
    onderwerp TEXT NOT NULL) STRICT;
CREATE TABLE afscherming (
    pagina TEXT PRIMARY KEY REFERENCES pagina(nummer),
    reden TEXT NOT NULL CHECK (reden IN ('privepersoon', 'niet_gelezen'))) STRICT;
CREATE TABLE kenmerk (
    pagina TEXT PRIMARY KEY REFERENCES pagina(nummer),
    soort TEXT NOT NULL CHECK (soort IN ('', 'ai', 'bewerkt', 'satire', 'verzonnen', 'context')),
    vorm TEXT NOT NULL CHECK (vorm IN ('', 'video', 'beeld')), CHECK (soort <> '' OR vorm <> '')) STRICT;
CREATE TABLE dossier (
    sleutel TEXT PRIMARY KEY, soort TEXT NOT NULL CHECK (soort IN ('verhaal', 'netwerk')),
    concept INTEGER NOT NULL DEFAULT 0, thema TEXT REFERENCES thema(sleutel), onderdeel TEXT NOT NULL DEFAULT '',
    {_kolommen('naam')}, {_kolommen('inleiding')}, vastgesteld_door TEXT NOT NULL DEFAULT '', vastgesteld_url TEXT NOT NULL DEFAULT '',
    vastgesteld_datum TEXT NOT NULL DEFAULT '') STRICT;
CREATE TABLE dossier_item (
    dossier TEXT NOT NULL REFERENCES dossier(sleutel), volg INTEGER NOT NULL,
    soort TEXT NOT NULL CHECK (soort IN ('factcheck', 'pers', 'onderzoek', 'besluit', 'rapport')),
    datum TEXT NOT NULL, pagina TEXT REFERENCES pagina(nummer), {_kolommen('titel', True)}, bron TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '',
    niveau TEXT NOT NULL DEFAULT '', versie TEXT NOT NULL DEFAULT '', PRIMARY KEY (dossier, volg)) STRICT;
CREATE TABLE dossier_verwant (
    dossier TEXT NOT NULL REFERENCES dossier(sleutel), verwant TEXT NOT NULL REFERENCES dossier(sleutel),
    PRIMARY KEY (dossier, verwant)) STRICT;
CREATE TABLE dossier_begrip (
    dossier TEXT NOT NULL REFERENCES dossier(sleutel), taal TEXT NOT NULL, volg INTEGER NOT NULL, begrip TEXT NOT NULL,
    PRIMARY KEY (dossier, taal, volg)) STRICT;
CREATE TABLE naam (
    nummer TEXT PRIMARY KEY, soort TEXT NOT NULL CHECK (soort IN ('persoon', 'organisatie', 'plaats')),
    {_kolommen('naam')}, wikis INTEGER NOT NULL, paginas INTEGER NOT NULL) STRICT;
CREATE TABLE pagina_naam (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), naam TEXT NOT NULL REFERENCES naam(nummer), volg INTEGER NOT NULL,
    PRIMARY KEY (pagina, naam)) STRICT;
CREATE TABLE naam_vorm (
    naam TEXT NOT NULL REFERENCES naam(nummer), vorm TEXT NOT NULL CHECK (vorm <> ''), PRIMARY KEY (naam, vorm)) STRICT;
CREATE TABLE woord (
    term TEXT PRIMARY KEY, doc INTEGER NOT NULL, lengte INTEGER NOT NULL, kandidaat INTEGER NOT NULL CHECK (kandidaat IN (0, 1)),
    gewoon TEXT) STRICT;
CREATE VIRTUAL TABLE zoek USING fts5(nummer UNINDEXED, tekst, tokenize = 'unicode61 remove_diacritics 2');
CREATE VIRTUAL TABLE zoek3 USING fts5(nummer UNINDEXED, tekst, tokenize = 'trigram');
CREATE INDEX idx_check_redactie ON check_(redactie);
CREATE INDEX idx_pagina_taal ON pagina(taal, laatste_datum);
CREATE INDEX idx_opgedoken_pagina ON opgedoken(pagina);
CREATE INDEX idx_pagina_thema ON pagina(thema, laatste_datum);
CREATE INDEX idx_pagina_tweede ON pagina(tweede, laatste_datum);
CREATE INDEX idx_pagina_land ON pagina(land, laatste_datum);
CREATE INDEX idx_dossier_item_pagina ON dossier_item(pagina);
CREATE INDEX idx_pagina_laatste ON pagina(laatste_datum DESC, nummer);
CREATE INDEX idx_pagina_redacties ON pagina(redacties DESC, laatste_datum DESC, nummer);
CREATE INDEX idx_pagina_naam_naam ON pagina_naam(naam, pagina);
CREATE INDEX idx_woord_gewoon ON woord(gewoon) WHERE gewoon IS NOT NULL;
-- de woorden van een redactie, letterlijk vertaald, onder hun sleutel (witruimte telt niet, #34.2o)
CREATE TABLE oordeel_glos (
    tekst TEXT NOT NULL, taal TEXT NOT NULL, glos TEXT NOT NULL CHECK (glos <> ''), PRIMARY KEY (tekst, taal)) STRICT;
-- andere pagina's over hetzelfde verhaal, de hoogste score eerst (#34.2p); een verwijzing, nooit een samenvoeging
CREATE TABLE lijkt_op (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), volg INTEGER NOT NULL, ander TEXT NOT NULL REFERENCES pagina(nummer),
    PRIMARY KEY (pagina, volg)) STRICT;
-- andere pagina's met dezelfde bewering bij een andere redactie, in beide richtingen (#34.2bp, SPECS E9.S31); een
-- verwijzing, nooit een samenvoeging: elke pagina houdt haar eigen bewering en oordeel
CREATE TABLE zelfde (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), volg INTEGER NOT NULL, ander TEXT NOT NULL REFERENCES pagina(nummer),
    PRIMARY KEY (pagina, volg)) STRICT;
-- waarom het niet klopt: hoogstens drie korte punten uit de weerlegging van EUvsDisinfo (CC BY 4.0), samengevat door
-- Factiz, met de link naar de case; alleen als de leesproef open is (#34.2j, B77); de meting staat in meta
CREATE TABLE waarom (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), volg INTEGER NOT NULL, punt TEXT NOT NULL CHECK (punt <> ''),
    url TEXT NOT NULL, PRIMARY KEY (pagina, volg)) STRICT;
-- de wereldlijst (B90, B91, #37.12): bij een overzicht van Factiz wat de redacties vonden ('vond') en waar het rondging
-- ('rondgang'), in de woorden van Factiz, elke zin met de links van de checks van die pagina die haar dragen
CREATE TABLE samenvatting (
    pagina TEXT NOT NULL REFERENCES pagina(nummer), taal TEXT NOT NULL, volg INTEGER NOT NULL,
    soort TEXT NOT NULL CHECK (soort IN ('vond', 'rondgang')), zin TEXT NOT NULL CHECK (zin <> ''),
    bronnen TEXT NOT NULL, PRIMARY KEY (pagina, taal, volg)) STRICT;
-- de eigen factchecks van Factiz (B82, #37.4): door een mens geschreven en door een ander nagelezen, gekeurd door
-- `redactie.controleer`; de check zelf als JSON. Een concept alleen in een voorbeeld (`bouwen --concepten`)
CREATE TABLE eigen_check (
    sleutel TEXT PRIMARY KEY, concept INTEGER NOT NULL DEFAULT 0, taal TEXT NOT NULL, datum TEXT NOT NULL,
    oordeel TEXT NOT NULL, gegevens TEXT NOT NULL) STRICT;
"""


# Geen vertaling bij een bewering die het lab Galicisch of onbekend noemde: daar vond de leesproef van B32 een fout
# (BENCHMARK §117), en een hersteld label maakt de vertaling niet nagelezen.
GEEN_VERTALING = frozenset({"gl", "und", ""})
VERTAALTAAL = "en"       # de vertalingen die er liggen (#25.17); de vertaalstap vult alleen aan wat ontbreekt (#34.2x)
_TAALCODE = re.compile(r"[a-z]{2,3}")


class Weigering(Exception):
    """Het bestand mag niet uitgegeven worden."""


def nummer(claim_id: str) -> str:
    """Het openbare nummer van een bewering: haar eigen, vaste nummer (het overleeft een nieuwe import). Alles wat
    die vorm niet heeft, krijgt een nummer uit een hash, zodat een nummer nooit een pad of een teken van buiten draagt."""
    if re.fullmatch(r"gfc-[0-9a-f]{16}", claim_id or ""):
        return claim_id[4:]
    return hashlib.sha256((claim_id or "").encode()).hexdigest()[:16]


def richting(taal: str) -> str:
    return "rtl" if (taal or "").split("-")[0].lower() in RTL else "ltr"


# De eigen redactie als bron van het archief (#37.4, B82, SPECS E10.S4 AC2): haar checks staan als redactie Factiz tussen
# de andere, met een link naar de eigen pagina. De licentie is een voorstel; de PO beslist vóór de eerste publicatie.
EIGEN_BRON = {"bron": "factiz-redactie", "naam": "Factiz", "licentie": "CC BY 4.0",
              "naamsvermelding": "Factiz, eigen factcheck (CC BY 4.0)", "url": "https://factiz.org/"}
# de schaal van de eigen redactie in de oordelen van het archief (`verdicts`): ontbrekende context telt als misleidend
EIGEN_NORMAAL = {"onwaar": "onwaar", "misleidend": "misleidend", "context": "misleidend", "grotendeels": "deels-waar",
                 "klopt": "waar", "onbewezen": "onbewezen"}


def eigen_adressen(c: dict, dag: str) -> dict:
    """Waar een eigen check op de site staat (PLAN #37.11, SPECS E10.S4 AC6 en AC7): de maand in haar adres, haar adres in
    elke taal waarin ze er is (haar eigen taal en elke geldige vertaling), en de talen waarin zoekmachines haar zien: haar
    eigen taal, en een vertaling die de redactie las. Een concept is nergens vindbaar. Zo hoeft de site niets af te leiden."""
    from doublecheck import redactie

    maand = redactie.maand(c, dag)
    vertalingen = c.get("vertalingen") or {}
    talen = [c["taal"]] + sorted(t for t in vertalingen if t != c["taal"] and t in redactie.SITETALEN)
    vindbaar = ([c["taal"]] + sorted(t for t in talen[1:] if vertalingen[t].get("nagelezen"))
                if c["status"] == "gepubliceerd" else [])
    return {"maand": maand, "paden": {t: redactie.pad_in(c, t, maand) for t in talen}, "vindbaar_in": vindbaar}


def eigen_paginas(checks: list[dict], concepten: bool, uitgave: str = "") -> list[dict]:
    """De eigen factchecks als pagina's van het archief (#37.4, SPECS E10.S4 AC2): per check één pagina met één check van
    de redactie Factiz, met hetzelfde soort oordeel als de andere redacties, de soort en vorm uit de check, en een link
    naar de eigen pagina (haar adres in haar eigen taal, PLAN #37.11). Wat `_eigen_erin` meeneemt, gaat ook hier mee: een
    concept alleen met `concepten`."""
    from doublecheck import redactie
    from doublecheck.redactie import oordeel_tekst
    from doublecheck.verdicts import labelklasse_in_tijd

    uit = []
    for c in sorted(checks, key=lambda c: c.get("sleutel", "")):
        fouten = redactie.controleer(c)
        if fouten:
            raise Weigering(f"eigen factcheck {c.get('sleutel')}: {'; '.join(fouten)}")
        if c["status"] != "gepubliceerd" and not concepten:
            continue
        dag = c.get("gepubliceerd") or c["eerst_gezien"]
        oordeel = EIGEN_NORMAAL[c["oordeel"]]
        label, eerder = labelklasse_in_tijd([(oordeel, dag)])
        pad = redactie.pad_in(c, c["taal"], redactie.maand(c, uitgave))
        uit.append({
            "nummer": nummer(f"factiz-{c['sleutel']}"), "bewering": c["bewering"], "taal": c["taal"],
            "richting": richting(c["taal"]), "label": label, "eerder": [list(e) for e in eerder],
            "checks": [{"redactie": EIGEN_BRON["naam"], "oordeel": oordeel,
                        "oordeel_eigen": oordeel_tekst(c["oordeel"], c["taal"]), "datum": dag,
                        "taal": c["taal"], "url": f"https://factiz.org{pad}", "link": "unchecked", "archief_url": None,
                        "archief_datum": None, "bron": EIGEN_BRON["bron"]}],
            "redacties": 1, "talen": [c["taal"]], "eerste_datum": dag, "laatste_datum": dag, "formuleringen": [],
            "leden": [], "kenmerk": (c.get("soort") or "", c.get("vorm") or ""),
            # de machinevertaling van de bewering (#37.8, B85): zo toont het archief haar in de taal van de site
            "vertaald": {taal: (v["velden"]["bewering"], v["maker"])
                         for taal, v in sorted((c.get("vertalingen") or {}).items()) if v["velden"].get("bewering")}})
    return uit


def _prefix(herkomst: str) -> str:
    """`euvsdisinfo:mendeley-…` hoort bij bron `euvsdisinfo`."""
    return (herkomst or "").split(":", 1)[0]


def vrije_bronnen(conn: sqlite3.Connection) -> dict[str, dict]:
    """De bronnen waarvan een check uitgegeven mag worden: Data Commons, en wat het register herverdeelbaar noemt.
    Een bron uit `NOOIT` komt er niet in, wat het register ook zegt."""
    vrij = {HERDISTRIBUEERBAAR: dict(DATACOMMONS)}
    for bron_id, naam, licentie, tekst, url in conn.execute(
            "SELECT bron_id, naam, licentie, attributietekst, url FROM bron WHERE herverdeelbaar = 1 ORDER BY bron_id"):
        if bron_id not in NOOIT:
            vrij[bron_id] = {"bron": bron_id, "naam": naam, "licentie": licentie, "naamsvermelding": tekst, "url": url}
    return vrij


def _link(rij: dict | None, uren: int) -> tuple[str, str | None, str | None]:
    from doublecheck.bonnetjes import link_status

    if rij is None:
        return "unchecked", None, None
    s = link_status(rij, uren)
    return s["status"], s["archive_url"], s["archived_on"]


def stel_samen(claims, checks, *, register: dict[str, str], vaag: frozenset[str], vrij: dict[str, dict],
               links: dict[str, dict], uren: int = 24, feed: frozenset[str] | None = None) -> dict:
    """De pagina's uit de beweringen en checks van het lab. Zuiver: geen database, geen klok behalve de datumregel.

    `claims`: (claim_id, tekst, taal, cluster_id). `checks`: dicts met claim_id, url, verdict_normalized,
    verdict_original, review_date, language en source. `feed`: de checks van Data Commons die nog mogen (B91,
    `feedstop.lees`); een andere check van de feed valt weg. Zonder `feed` (alleen in proeven) gaan ze allemaal mee."""
    from doublecheck.datums import geldige_review_datum
    from doublecheck.feedstop import sleutel as feedsleutel
    from doublecheck.evidence import _host
    from doublecheck.verdicts import labelklasse_in_tijd

    claim = {c[0]: {"tekst": c[1], "taal": c[2] or "und", "cluster": c[3]} for c in claims}
    weg = Counter()
    per_claim: dict[str, list[dict]] = {}
    for ch in checks:
        cid = ch["claim_id"]
        if cid not in claim:
            continue
        if _prefix(ch["source"]) not in vrij:
            weg["herkomst niet vrij"] += 1
        elif (feed is not None and _prefix(ch["source"]) == HERDISTRIBUEERBAAR
              and feedsleutel(cid, ch["url"]) not in feed):
            weg["feed gestopt (B91)"] += 1
        elif (_host(ch["url"]) or "") not in register:
            weg["uitgever niet toegelaten"] += 1
        elif cid in vaag:
            weg["vage bewering"] += 1
        else:
            status, archief, archief_op = _link(links.get(ch["url"]), uren)
            per_claim.setdefault(cid, []).append({
                "redactie": register[_host(ch["url"])], "oordeel": ch["verdict_normalized"],
                "oordeel_eigen": ch["verdict_original"] or "", "datum": geldige_review_datum(ch["review_date"] or ""),
                "taal": ch["language"] or "und", "url": ch["url"], "link": status, "archief_url": archief,
                "archief_datum": archief_op, "bron": _prefix(ch["source"])})
    groepen: dict[str, list[str]] = {}
    for cid in per_claim:                      # alleen beweringen met een check die mee mag
        groepen.setdefault(claim[cid]["cluster"] or cid, []).append(cid)
    paginas, verwijzingen = [], {}
    for leden in groepen.values():
        # de formulering met de meeste checks draagt de pagina; bij gelijk de oudste, dan het laagste nummer
        leden.sort(key=lambda c: (-len(per_claim[c]), min((k["datum"] for k in per_claim[c] if k["datum"]),
                                                          default="9999"), c))
        hoofd = leden[0]
        alle = sorted((k for c in leden for k in per_claim[c]),
                      key=lambda k: (k["datum"], k["redactie"], k["url"]), reverse=True)
        # dezelfde check kan via twee formuleringen binnenkomen: één keer tonen
        gezien, uniek = set(), []
        for k in alle:
            if k["url"] not in gezien:
                gezien.add(k["url"])
                uniek.append(k)
        label, eerder = labelklasse_in_tijd((k["oordeel"], k["datum"]) for k in uniek)
        datums = sorted(k["datum"] for k in uniek if k["datum"])
        talen = sorted(({k["taal"] for k in uniek} | {claim[c]["taal"] for c in leden}) - {"und"}) or ["und"]
        paginas.append({
            "nummer": nummer(hoofd), "bewering": claim[hoofd]["tekst"], "taal": claim[hoofd]["taal"],
            "richting": richting(claim[hoofd]["taal"]), "label": label, "eerder": [list(e) for e in eerder],
            "checks": uniek, "redacties": len({k["redactie"] for k in uniek}), "talen": talen,
            "eerste_datum": datums[0] if datums else "", "laatste_datum": datums[-1] if datums else "",
            "formuleringen": [{"nummer": nummer(c), "tekst": claim[c]["tekst"], "taal": claim[c]["taal"],
                               "richting": richting(claim[c]["taal"])} for c in sorted(leden[1:])],
            "leden": list(leden)})
        for c in leden[1:]:
            verwijzingen[nummer(c)] = nummer(hoofd)
    paginas.sort(key=lambda p: p["nummer"])
    return {"paginas": paginas, "verwijzingen": verwijzingen, "weggelaten": dict(weg)}


def wie_het_zegt(label: str | None, checks: list[dict]) -> list[str]:
    """De redacties achter het oordeel van een pagina, voor het stempel *Onwaar volgens ...* (PLAN #34.2cc, DESIGN §4y,
    PO 2026-11-19): wie tot dat oordeel kwam (bij onwaar of misleidend: wie een van beide zei); bij omstreden iedereen
    met een oordeel, want dan zijn ze het oneens; zonder oordeel, of als niemand het precies zo zei, iedereen. Wie het
    vaakst checkte eerst, dan op naam."""
    past = {"onwaar-of-misleidend": {"onwaar", "misleidend"}}.get(label or "", {label} if label else set())
    if label == "omstreden":
        wie = [k for k in checks if k["oordeel"] != "onbekend"]
    else:
        wie = [k for k in checks if k["oordeel"] in past]
    tel = Counter(k["redactie"] for k in (wie or checks))
    return sorted(tel, key=lambda r: (-tel[r], r))


def woordrijen(conn: sqlite3.Connection) -> list[tuple]:
    """De rijen van de tabel `woord` zoals ze uit het zoekregister volgen (`factiz_site.db.woordrij`, #37.16)."""
    from factiz_site.db import woordrij

    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS temp.zoek_woorden USING fts5vocab(main, zoek, row)")
    return [woordrij(term, doc) for term, doc in conn.execute("SELECT term, doc FROM temp.zoek_woorden ORDER BY term")]


def _woorden_erin(pub: sqlite3.Connection) -> int:
    """De woordenlijst van het zoekregister als tabel (#37.16): de Worker vraagt haar aan de database in plaats van haar in
    zijn geheugen van 128 MB te houden."""
    rijen = woordrijen(pub)
    pub.executemany("INSERT INTO woord VALUES (?, ?, ?, ?, ?)", rijen)
    return len(rijen)


def controlegetal(conn: sqlite3.Connection) -> str:
    """Een getal over de inhoud: elke rij van elke tabel, in vaste volgorde. Niet over het bestand zelf, dus twee
    keer bouwen op dezelfde gegevens geeft hetzelfde getal."""
    h = hashlib.sha256()
    for tabel in TABELLEN:
        h.update(tabel.encode())
        kolommen = len(conn.execute(f"PRAGMA table_info({tabel})").fetchall())
        volgorde = ", ".join(str(k) for k in range(1, kolommen + 1))
        for rij in conn.execute(f"SELECT * FROM {tabel} ORDER BY {volgorde}"):
            h.update(json.dumps(list(rij), ensure_ascii=False, separators=(",", ":")).encode())
    return h.hexdigest()


# --- begrippen in een dossier (SPECS E9.S7 AC9, PLAN #34.2ca) ------------------------------------------------------
MAX_BEGRIPPEN = 12
BEGRIP_MIN = 3            # in minstens zoveel factchecks van het dossier
BEGRIP_VERRIJKING = 8     # en daar minstens zoveel keer vaker dan in het hele archief in dezelfde taal
BEGRIP_GEWOON = 0.01      # een woord in meer dan 1% van het archief is een gewoon woord, nooit een begrip
BEGRIP_STIJL = 0.05       # een woord in meer dan 5% van de checks van één redactie is haar vaste zin, geen begrip
BEGRIP_DEKKING = 0.6      # een taal krijgt eigen begrippen als zoveel van het dossier in die taal te lezen is; anders Engels
# woorden die in beweringen overal staan en niets zeggen over het onderwerp; de rest doet de telling
BEGRIP_STOP = frozenset("""zouden zou zullen worden wordt werd werden hebben heeft had waren zijn wezen toont tonen getoond
beweert beweren bewering beweringen recent recente recentelijk nieuw nieuwe hier gearchiveerd wegens volgens zogenaamd
zogenaamde video foto beeld beelden afbeelding afbeeldingen post posts bericht berichten account accounts claim claims
shows showing show shown allegedly purportedly reportedly claiming claimed appears gave massive formerly twitter
image images photo photos picture pictures footage clip clips viral ongoing latest recently videos
zeigt zeigen angeblich soll sollen sollte bild bilder fotos muestra muestran supuestamente presuntamente imagen
imágenes montre montrent prétendant prétendument vidéo vidéos publication""".split())
BEGRIPTALEN = tuple(t for t in SITETALEN if t not in ("ja", "zh"))   # talen met spaties; de rest valt terug op het Engels
_WOORD = re.compile(r"[^\W\d_](?:[\w-]*\w)?")
_MAAND = re.compile(r"(?i)^(jan(uari|uary|vier|uar)?|feb(ruari|ruary|rero|ruar)?|maart|march|märz|marzo|mars|apr(il|ile)?|"
                    r"abril|avril|mei|may|mai|mayo|jun[ie]?|juni|junio|juin|jul[iy]?|juli|julio|juillet|aug(ustus|ust)?|"
                    r"agosto|août|sep(tember|tiembre|tembre)?|okt(ober)?|oct(ober|ubre|obre)?|nov(ember|iembre|embre)?|"
                    r"dec(ember|embre)?|dez(ember)?|dic(iembre)?|décembre|février|janvier)$")


def _woorden(tekst: str, taal: str) -> list[str]:
    """De woorden van een tekst zoals ze er staan, zonder getallen en leestekens; `taal` doet nu niets, maar houdt de
    deur open voor een taal die anders gelezen moet worden."""
    return _WOORD.findall(tekst or "")


def _termen(woorden: list[str]) -> list[tuple[str, str]]:
    """De woorden en de paren van opeenvolgende woorden, elk als (sleutel, zoals het er staat)."""
    een = [(w.casefold(), w) for w in woorden]
    return een + [(f"{a[0]} {b[0]}", f"{a[1]} {b[1]}") for a, b in zip(een, een[1:])]


def begrippen(teksten: list[str], df: Counter, n: int, uit: set[str], maximum: int = MAX_BEGRIPPEN,
              taal: str = "en", redacties: list[set[str]] | None = None, stijl: dict[str, set[str]] | None = None
              ) -> list[str]:
    """De begrippen van een dossier: de woorden en woordparen die in minstens `BEGRIP_MIN` van zijn teksten staan en daar
    minstens `BEGRIP_VERRIJKING` keer vaker voorkomen dan in het hele archief (`df` telt per sleutel in hoeveel van de
    `n` teksten van het archief hij staat). Nooit een gewoon woord, een getal, een maand of een woord dat begint met iets
    uit `uit` (de naam van het dossier, zijn zoekwoorden). Met `redacties` (per tekst wie hem checkte) en `stijl` (per
    woord de redacties bij wie het een vaste zin is) telt een tekst niet mee voor een woord dat de vaste zin is van al
    haar redacties. Een paar dat bijna altijd samen voorkomt, vervangt zijn woorden. In de spelling die het vaakst
    voorkomt, de sterkste eerst."""
    import math

    aantal, vorm = Counter(), {}
    for i, tekst in enumerate(teksten):
        gezien = set()
        for sleutel, zoals in _termen(_woorden(tekst, taal)):
            vorm.setdefault(sleutel, Counter())[zoals] += 1
            gezien.add(sleutel)
        if redacties is not None and stijl:
            gezien = {k for k in gezien if not (redacties[i] and redacties[i] <= stijl.get(k, set()))}
        aantal.update(gezien)

    def gewoon(woord: str) -> bool:
        return (df.get(woord, 0) / max(n, 1) > BEGRIP_GEWOON or len(woord) < 3 or woord in BEGRIP_STOP
                or _MAAND.match(woord) is not None or any(woord.startswith(u) for u in uit))

    score = {}
    for sleutel, a in aantal.items():
        delen = sleutel.split(" ")
        if a < BEGRIP_MIN or any(gewoon(d) for d in delen) or (len(delen) == 1 and len(sleutel) < 4
                                                                and not vorm[sleutel].most_common(1)[0][0].isupper()):
            continue
        verrijking = (a / len(teksten)) / ((df.get(sleutel, 0) + 1) / max(n, 1))
        if verrijking >= BEGRIP_VERRIJKING:
            score[sleutel] = a * math.log(verrijking)
    gekozen: list[str] = []
    stam = lambda k: k[:-1] if k.endswith("s") and len(k) > 4 else k
    for sleutel in sorted(score, key=lambda k: (-score[k], k)):
        if any(stam(g) == stam(sleutel) for g in gekozen):
            continue              # enkelvoud en meervoud zijn één begrip (strike, strikes)
        delen = sleutel.split(" ")
        if len(delen) == 2:
            if all(aantal[sleutel] >= 0.6 * aantal[d] for d in delen):
                gekozen = [g for g in gekozen if g not in delen]
            elif any(d in gekozen for d in delen):
                continue
        elif any(" " in g and sleutel in g.split(" ") and aantal[g] >= 0.6 * aantal[sleutel] for g in gekozen):
            continue
        gekozen.append(sleutel)
    return [vorm[k].most_common(1)[0][0] for k in gekozen[:maximum]]


def _begrippen_erin(pub: sqlite3.Connection, dossiers: list[dict]) -> int:
    """Rekent de begrippen van elk dossier in de uitgave, per taal van de site, uit de bewering in die taal of haar
    vertaling, tegen het hele archief in dezelfde taal. Zonder model."""
    sleutels = [r[0] for r in pub.execute("SELECT sleutel FROM dossier")]
    if not sleutels:
        return 0
    per = {d["sleutel"]: d for d in dossiers}
    redacties: dict[str, set[str]] = {}
    for nr, red in pub.execute("SELECT pagina, redactie FROM check_"):
        redacties.setdefault(nr, set()).add(red)
    rijen = 0
    for taal in BEGRIPTALEN:
        tekst = dict(pub.execute("SELECT nummer, bewering FROM pagina WHERE taal = ?", (taal,)))
        tekst.update(pub.execute("SELECT pagina, tekst FROM vertaling WHERE taal = ?", (taal,)))
        per_dossier = {}
        kandidaten: set[str] = set()
        for s in sleutels:
            alle = [r[0] for r in pub.execute("SELECT pagina FROM dossier_item WHERE dossier = ? AND soort = 'factcheck'", (s,))]
            paginas = [nr for nr in alle if tekst.get(nr)]
            if len(paginas) < max(BEGRIP_MIN, BEGRIP_DEKKING * len(alle)):
                continue          # te weinig in deze taal te lezen: de site toont de Engelse begrippen
            teksten = [tekst[nr] for nr in paginas]
            per_dossier[s] = (teksten, [redacties.get(nr, set()) for nr in paginas])
            for t in teksten:
                kandidaten.update(k for k, _ in _termen(_woorden(t, taal)))
        df: Counter = Counter()
        per_red: Counter = Counter()
        n_red: Counter = Counter()
        for nr, t in tekst.items():
            hier = {k for k, _ in _termen(_woorden(t, taal))} & kandidaten
            df.update(hier)
            for red in redacties.get(nr, ()):
                n_red[red] += 1
                per_red.update((red, k) for k in hier)
        stijl: dict[str, set[str]] = {}
        for (red, k), a in per_red.items():
            if n_red[red] >= 40 and a / n_red[red] > BEGRIP_STIJL:
                stijl.setdefault(k, set()).add(red)
        for s, (teksten, wie) in per_dossier.items():
            d = per.get(s, {})
            uit = {w.casefold() for w in _woorden((d.get("naam") or {}).get(taal, ""), taal) if len(w) >= 4}
            uit |= {w.casefold() for w in ((d.get("voorstel") or {}).get("woorden") or []) if len(w) >= 4}
            lijst = begrippen(teksten, df, len(tekst), uit, taal=taal, redacties=wie, stijl=stijl)
            pub.executemany("INSERT INTO dossier_begrip VALUES (?, ?, ?, ?)", [(s, taal, i, b) for i, b in enumerate(lijst)])
            rijen += len(lijst)
    return rijen


def _eigen_erin(pub: sqlite3.Connection, checks: list[dict], concepten: bool, dag: str = "") -> dict:
    """Zet de eigen factchecks in het bestand (#37.4, B82): een gepubliceerde altijd, een concept of een nagelezen check
    die nog niet uit is alleen met `concepten`. Elke check gaat eerst langs `redactie.controleer`; één fout stopt de bouw,
    en ook twee checks met hetzelfde adres in dezelfde maand (PLAN #37.11). De check gaat erin zoals de redactie haar
    schreef, als JSON, met haar adressen erbij (`eigen_adressen`), zodat de site niets hoeft af te leiden."""
    from doublecheck import redactie

    uit = {"gepubliceerd": 0, "concept": 0, "vindbaar": 0}
    mee = []
    for c in sorted(checks, key=lambda c: c.get("sleutel", "")):
        fouten = redactie.controleer(c)
        if fouten:
            raise Weigering(f"eigen factcheck {c.get('sleutel')}: {'; '.join(fouten)}")
        if c["status"] == "gepubliceerd" or concepten:
            mee.append(c)
    botsing = redactie.botsingen(mee, dag)
    if botsing:
        raise Weigering(f"eigen factcheck: {'; '.join(botsing)}")
    for c in mee:
        klaar = c["status"] == "gepubliceerd"
        g = {**c, **eigen_adressen(c, dag)}
        pub.execute("INSERT INTO eigen_check VALUES (?, ?, ?, ?, ?, ?)",
                    (c["sleutel"], 0 if klaar else 1, c["taal"], c.get("gepubliceerd") or "", c["oordeel"],
                     json.dumps(g, ensure_ascii=False, sort_keys=True)))
        uit["gepubliceerd" if klaar else "concept"] += 1
        uit["vindbaar"] += len(g["vindbaar_in"])
    return uit


def _indeling_ok(g: dict | None, per_thema: dict[str, set[str]], landen: dict[str, dict]) -> tuple:
    """Thema, onderdeel, tweede thema en land van één pagina, alleen uit de gesloten lijsten: een thema buiten de
    lijst is geen thema, een onderdeel van een ander thema vervalt, een land dat niet bestaat ook."""
    if not g or g.get("thema") not in per_thema:
        return None, "", "", ""
    thema = g["thema"]
    onderdeel = g.get("onderdeel") if g.get("onderdeel") in per_thema[thema] else ""
    tweede = g.get("tweede") if g.get("tweede") in per_thema and g.get("tweede") != thema else ""
    return thema, onderdeel, tweede, g.get("land") if g.get("land") in landen else ""


def _kaal(tekst: str | None) -> str:
    """Een tekst om te vergelijken: zonder hoofdletters, dubbele witruimte en aanhalingstekens of punten aan de rand."""
    return " ".join((tekst or "").casefold().split()).strip(" .\"'“”‘’«»„")


def _dossiers_erin(pub: sqlite3.Connection, dossiers: list[dict], concepten: bool, samen: dict,
                   per_thema: dict[str, set[str]]) -> dict[str, dict]:
    """Zet de dossiers in het bestand en zegt per dossier wat erin kwam. Een factcheck staat op de dag van zijn eerste
    check; die dag komt uit de pagina, nooit uit het dossier (E9.S7 AC5). Een nummer van een samengevoegde formulering
    volgt de verwijzing; een nummer dat deze uitgave niet heeft, valt weg en wordt genoemd. Eén factcheck in twee
    verhaaldossiers weigert de bouw (B72). Een versie (hetzelfde bericht in andere woorden, AC8) gaat mee als er in
    deze uitgave minstens twee factchecks van over zijn."""
    eerste = {p["nummer"]: p["eerste_datum"] for p in samen["paginas"]}
    mee = sorted((d for d in dossiers if d["status"] == "akkoord" or concepten), key=lambda d: d["sleutel"])
    sleutels = {d["sleutel"] for d in mee}
    verhaal_van: dict[str, str] = {}
    verslag: dict[str, dict] = {}
    for d in mee:
        thema = d["thema"] if d["thema"] in per_thema else None
        onderdeel = d["onderdeel"] if thema and d["onderdeel"] in per_thema[thema] else ""
        v = d["vastgesteld"] or {"door": "", "url": "", "datum": ""}
        pub.execute(f"INSERT INTO dossier VALUES {_plekken(8 + 2 * len(SITETALEN))}",
                    (d["sleutel"], d["soort"], int(d["status"] != "akkoord"), thema, onderdeel,
                     *(d["naam"][taal] for taal in SITETALEN), *(d["inleiding"][taal] for taal in SITETALEN),
                     v["door"], v["url"], v["datum"]))
        # de items van de mens eerst, in de volgorde van het bestand, dan de factchecks op nummer; daarna op datum, de
        # nieuwste boven en wat geen datum heeft onderaan. De volgorde in het bestand doet er zo niet toe.
        rijen = [(it["soort"], it["datum"], None, *(it["titel"][taal] for taal in SITETALEN), it["bron"], it["url"], "", "")
                 for it in d["items"]]
        gezien, weg, factchecks = set(), [], []
        for f in d["factchecks"]:
            nr = samen["verwijzingen"].get(f["nummer"], f["nummer"])
            if nr not in eerste:
                weg.append(f["nummer"])
                continue
            if nr in gezien:
                continue
            gezien.add(nr)
            if d["soort"] == "verhaal":
                if nr in verhaal_van:
                    raise Weigering(f"factcheck {nr} staat in twee verhaaldossiers: {verhaal_van[nr]} en {d['sleutel']}")
                verhaal_van[nr] = d["sleutel"]
            factchecks.append(("factcheck", eerste[nr], nr, *([""] * len(SITETALEN)), f.get("bron", ""), f.get("url", ""),
                               f.get("niveau", ""), f.get("versie", "") if d["soort"] == "verhaal" else ""))
        versie = 6 + len(SITETALEN)        # soort, datum, pagina, een titel per taal, bron, url, niveau, dan de versie
        per_versie = Counter(r[versie] for r in factchecks if r[versie])
        factchecks = [r if per_versie[r[versie]] >= 2 else (*r[:versie], "") for r in factchecks]
        rijen += sorted(factchecks, key=lambda r: r[2])
        rijen.sort(key=lambda r: r[1], reverse=True)          # stabiel: bij dezelfde dag blijft de volgorde van hierboven
        pub.executemany(f"INSERT INTO dossier_item VALUES {_plekken(9 + len(SITETALEN))}",
                        [(d["sleutel"], volg, *r) for volg, r in enumerate(rijen)])
        pub.executemany("INSERT INTO dossier_verwant VALUES (?, ?)",
                        [(d["sleutel"], w) for w in sorted(set(d["verwant"])) if w in sleutels])
        verslag[d["sleutel"]] = {"soort": d["soort"], "concept": d["status"] != "akkoord", "factchecks": len(factchecks),
                                 "items": len(d["items"]), "weggevallen": sorted(weg),
                                 "versies": len({r[versie] for r in factchecks if r[versie]})}
    return verslag


def _namen_erin(pub: sqlite3.Connection, namen: dict | None, samen: dict, niet: frozenset[str] | set[str],
                concept: bool, vormen: dict[str, list[str]] | None = None) -> dict:
    """Zet de namen in het bestand (PLAN #33.7, SPECS E9.S11), getoetst aan déze uitgave: een pagina die er niet in
    staat, telt niet; het nummer van een samengevoegde formulering volgt naar haar pagina; een naam die daarna te
    weinig pagina's heeft, een persoon bij te weinig redacties, een naam zonder nummer, soort of naam in elke taal, en
    wat een mens weghaalde, blijven eruit. De volgorde op een pagina is die waarin het model de namen noemde. Van wat
    erin gaat ook de bijnamen die Wikidata kent, zonder de vijf namen zelf (`namen.bijnamen`, PLAN #34.2z)."""
    from doublecheck import namen as nm

    redacties = {p["nummer"]: {k["redactie"] for k in p["checks"]} for p in samen["paginas"]}
    volgt = samen["verwijzingen"]
    mee: dict[str, tuple[dict, list[str]]] = {}
    weg = []
    for q, n in sorted(((namen or {}).get("namen") or {}).items()):
        paginas = sorted({volgt.get(x, x) for x in n.get("paginas") or []} & set(redacties))
        goed = (nm._NUMMER.fullmatch(q) and q not in niet and n.get("soort") in nm.SOORTEN
                and all((n.get("namen") or {}).get(taal) for taal in BASISTALEN)
                and isinstance(n.get("wikis"), int) and n["wikis"] >= nm.MIN_WIKIS and len(paginas) >= nm.MIN_PAGINAS
                and (n["soort"] != "persoon"
                     or len(set().union(*(redacties[x] for x in paginas))) >= nm.MIN_REDACTIES))
        if goed:
            mee[q] = (n, paginas)
        else:
            weg.append(q)
    pub.executemany(f"INSERT INTO naam VALUES {_plekken(4 + len(SITETALEN))}", [
        (q, n["soort"], *(n["namen"].get(taal) or n["namen"]["en"] for taal in SITETALEN), n["wikis"], len(paginas))
        for q, (n, paginas) in mee.items()])
    pub.executemany("INSERT INTO naam_vorm VALUES (?,?)", [
        (q, vorm) for q, (n, _) in mee.items() for vorm in nm.bijnamen((vormen or {}).get(q) or [], n["namen"])])
    orde: dict[str, list[str]] = {}
    for oud, lijst in sorted(((namen or {}).get("per_pagina") or {}).items()):
        pagina = volgt.get(oud, oud)
        for q in lijst:
            if q in mee and pagina in mee[q][1] and q not in orde.setdefault(pagina, []):
                orde[pagina].append(q)
    for q, (_, paginas) in mee.items():                     # een paar zonder volgorde sluit achteraan
        for pagina in paginas:
            if q not in orde.setdefault(pagina, []):
                orde[pagina].append(q)
    pub.executemany("INSERT INTO pagina_naam VALUES (?,?,?)", [
        (pagina, q, volg) for pagina, lijst in sorted(orde.items()) for volg, q in enumerate(lijst)])
    return {"mee": len(mee), "per_soort": dict(sorted(Counter(n["soort"] for n, _ in mee.values()).items())),
            "paren": sum(len(v) for v in orde.values()), "weggevallen": weg, "concept": bool(concept and mee)}


def _normaal(hoofdletters: dict | None, nummer: str, taal: str, tekst: str, teller: dict[str, int]) -> str | None:
    """Het normale schrift van een tekst in hoofdletters (#34.2ae), als het bij precies deze tekst hoort en alleen hoofd-
    en kleine letters verandert; anders niets. Telt wat erin gaat."""
    rij = (hoofdletters or {}).get((nummer, taal))
    if not rij or " ".join(rij["was"].split()) != " ".join(tekst.split()) or not hl.alleen_hoofdletters(tekst, rij["tekst"]):
        return None
    teller["vertalingen" if taal else "beweringen"] += 1
    return rij["tekst"]


def _afscherming(afscherming: dict[str, dict] | None, p: dict) -> tuple[str | None, str | None]:
    """De reden om een pagina buiten zoekmachines te houden, en de naam die het merkteken van de sticker *naam weggelaten* wordt (#34.2bw). Zonder lezing van
    het lab niets; een pagina zonder lezing van precies haar tekst is *niet gelezen*. Een eigen factcheck las de redactie
    zelf."""
    if afscherming is None or "kenmerk" in p:     # alleen een eigen factcheck heeft "kenmerk" (`_eigen_paginas`)
        return None, None
    lezing = afscherming.get(p["nummer"])
    if not lezing or " ".join(lezing["bron"].split()) != " ".join(p["bewering"].split()):
        return "niet_gelezen", None
    if not lezing["afschermen"]:
        return None, None
    naam = lezing.get("naam") or None
    return "privepersoon", naam if naam and _noemt(p["bewering"], naam) else None


def _naampatroon(naam: str) -> re.Pattern:
    return re.compile(r"\s+".join(re.escape(d) for d in naam.split()), re.IGNORECASE)


def _noemt(tekst: str, naam: str) -> bool:
    return bool(_naampatroon(naam).search(tekst))


def _maskeer(tekst: str, naam: str) -> str:
    """De naam weg, met op haar plek het merkteken dat het platform als sticker toont (`i18n.WEGGELATEN`)."""
    from factiz_site.i18n import WEGGELATEN

    return _naampatroon(naam).sub(lambda _: WEGGELATEN, tekst)


def bouw(conn: sqlite3.Connection, uit: Path, *, register: dict[str, str] | None = None,
         vaag: frozenset[str] | None = None, datum: str | None = None, uren: int = 24,
         indeling: dict[str, dict] | None = None, themas: list[dict] | None = None,
         landen: dict[str, dict] | None = None, talen: dict[str, str] | None = None,
         vertalingen: dict[str, dict[str, str]] | None = None, vertaalmaker: str | dict[str, str] = "",
         dossiers: list[dict] | None = None, concepten: bool = False, namen: dict | None = None,
         namen_concept: bool = False, namen_niet: frozenset[str] | set[str] = frozenset(),
         oordelen: dict[str, str] | None = None, glossen: dict[str, dict] | None = None,
         lijkt_op: dict[str, list[str]] | None = None, waarom: dict | None = None,
         zelfde: dict[str, list[str]] | None = None,
         naamvormen: dict[str, list[str]] | None = None, hoofdletters: dict[tuple[str, str], dict] | None = None,
         hoofdletters_concept: bool = False, soortwoorden: dict[str, str] | None = None,
         eigen: list[dict] | None = None, zoekvragen: dict[str, dict] | None = None, feed: frozenset[str] | None = None,
         wereldlijst: list[dict] | None = None, voorlopig: dict[str, dict[str, str]] | None = None,
         voorlopig_maker: dict[str, str] | None = None,
         afscherming: dict[str, dict] | None = None, particulier: dict[str, dict] | None = None) -> dict:
    """Bouwt `publicatie.db` en `manifest.json` in de map `uit`, uit de database van het lab (die alleen gelezen
    wordt). `register`, `vaag` en `datum` zijn in te vullen voor tests; anders het register, de lijst met vage
    beweringen en de dag van vandaag. `indeling` (per pagina het thema en het land), `themas` (de lijst) en `landen`
    (de namen) gaan alleen mee als de poort van de PO open is (PLAN #33.4); zonder hen heeft geen pagina een thema.
    `talen` zijn de nagelezen correcties op de taal van een bewering, per nummer (PLAN #33.5): ze gelden voor de
    bewering, haar checks en haar plek tussen de formuleringen. De Engelse vertaling die er ligt gaat mee waar B32
    het toelaat. `vertalingen` zijn de vertalingen voor weergave per doeltaal en nummer, alleen van een doeltaal die
    haar leesproef haalde (`weergave.geldige_vertalingen`); `vertaalmaker` zegt wie ze maakte, voor alle talen of per
    doeltaal (#34.2x: het Engels komt van Sonnet). `dossiers` zijn de
    gekeurde dossiers uit `content/dossiers/` (`dossiers.lees_alle`); alleen wat de PO goedkeurde gaat mee, tenzij
    `concepten` aan staat voor een voorbeeld op de eigen computer (PLAN #33.6). `namen` is wat `namen.stel_samen`
    en `namen.per_pagina` opleverden; het gaat alleen mee als de PO de namen las (`namen.poort`), of met
    `namen_concept` in een voorbeeld dat `controleer` als uitgave weigert. `namen_niet` zijn de nummers die een
    mens weghaalde (PLAN #33.7). `oordelen` zijn de oordelen die de tabel niet las, gelezen door
    `oordeellezer` (per sleutel van de woorden van de redactie), en `glossen` hun vertalingen; `lijkt_op` per pagina de
    andere pagina's over hetzelfde verhaal (`lijktop`), en `zelfde` per pagina de andere pagina's met dezelfde bewering
    bij een andere redactie (`zelfdebewering`). Elk alleen als zijn leesproef open is (PLAN #34.2o, #34.2p, #34.2bp).
    `waarom` is wat `waarom.geldige_punten` gaf: per pagina de punten en de link, en de meting (PLAN #34.2j, B77).
    `naamvormen` zijn per nummer de schrijfwijzen die Wikidata van een naam kent (`namen.vormen_van_wikidata`): ze
    gaan mee voor de namen die erin staan, alleen om te zoeken (PLAN #34.2z, E9.S11 AC8). `zoekvragen` zijn per nummer
    de vraag zoals een zoeker haar typt en een onderwerp (`zoekvragen.voor_de_uitgave`, PLAN #34.2cf, B87): alleen als de
    tekst waaruit ze kwamen, in hun taal, nog precies zo luidt."""
    from doublecheck import toelating

    register = toelating.register() if register is None else register
    vaag = toelating.vage_claims() if vaag is None else vaag
    datum = datum or date.today().isoformat()
    vrij = vrije_bronnen(conn)
    kolommen = ("claim_id", "url", "verdict_normalized", "verdict_original", "review_date", "language", "source")
    checks = [dict(zip(kolommen, r)) for r in conn.execute(f"SELECT {', '.join(kolommen)} FROM factcheck")]
    talen = {nr: t for nr, t in (talen or {}).items() if _TAALCODE.fullmatch(t or "")}

    def taal_van(claim_id: str, taal: str) -> str:
        return talen.get(nummer(claim_id), taal)

    for ch in checks:
        ch["language"] = taal_van(ch["claim_id"], ch["language"])
    # een oordeel dat de tabel niet kende, gelezen na een leesproef (#34.2o); nooit over de tabel heen, en nooit wat de
    # eigen lijst van een redactie geen oordeel noemt
    from doublecheck.evidence import _host
    from doublecheck.oordeellezer import sleutel as woordsleutel
    from doublecheck.verdicts import geen_oordeel

    oordelen, gelezen = oordelen or {}, 0
    for ch in checks:
        k = woordsleutel(ch["verdict_original"])
        if ch["verdict_normalized"] == "onbekend" and k in oordelen and not geen_oordeel(k, _host(ch["url"])):
            ch["verdict_normalized"] = oordelen[k]
            gelezen += 1
    lab_taal = dict(conn.execute("SELECT claim_id, language FROM claim"))
    from doublecheck.bonnetjes import VELDEN

    links = {r[0]: dict(zip(VELDEN, r)) for r in conn.execute(f"SELECT {', '.join(VELDEN)} FROM linkstatus")}
    samen = stel_samen(((cid, tekst, taal_van(cid, taal), cluster) for cid, tekst, taal, cluster in
                        conn.execute("SELECT claim_id, canonical_text, language, cluster_id FROM claim")),
                       checks, register=register, vaag=vaag, vrij=vrij, links=links, uren=uren, feed=feed)
    # alleen wat publiek is (#34.2ch, PO 2026-11-22: "Te particuliere dingen moeten er wat mij betreft uit"): een pagina die
    # Haiku particulier las, bij precies haar tekst, gaat eruit met haar andere formuleringen; een pagina in een dossier
    # (een mens keurde haar goed) blijft
    if particulier:
        in_dossier = {f.get("nummer") for d in (dossiers or []) for f in d.get("factchecks", [])}
        houden = []
        for p in samen["paginas"]:
            lezing = particulier.get(p["nummer"])
            # gelezen in een uitgave waarin de naam van een minderjarige al het merkteken was (#34.2bw): dezelfde tekst
            naam = ((afscherming or {}).get(p["nummer"]) or {}).get("naam")
            vormen = {" ".join(p["bewering"].split())} | ({" ".join(_maskeer(p["bewering"], naam).split())} if naam else set())
            if lezing and p["nummer"] not in in_dossier and " ".join(lezing["bron"].split()) in vormen:
                for lid in p["leden"][1:]:
                    samen["verwijzingen"].pop(nummer(lid), None)
                samen["weggelaten"]["particulier"] = samen["weggelaten"].get("particulier", 0) + 1
                continue
            houden.append(p)
        samen["paginas"] = houden
    # De Engelse vertaling van de bewering die de pagina draagt: de eerste variant die er ligt.
    variant: dict[str, tuple[str, str]] = {}
    for cid, tekst, maker, vraag in conn.execute(
            "SELECT claim_id, text, generator, prompt_version FROM claim_variant WHERE language = ? ORDER BY variant_id",
            (VERTAALTAAL,)):
        variant.setdefault(cid, (tekst, f"{maker}, {vraag}"))
    # per pagina: {taal: (tekst, maker)}. Nooit in de taal van de bewering zelf, en alleen in een taal van de site.
    weergave = {taal: per for taal, per in (vertalingen or {}).items() if taal in SITETALEN}
    vertalingen = {}
    for p in samen["paginas"]:
        hoofd, per_taal = p["leden"][0], {}
        if (hoofd in variant and p["taal"] not in (VERTAALTAAL, "und")
                and (lab_taal.get(hoofd) or "") not in GEEN_VERTALING):
            per_taal[VERTAALTAAL] = variant[hoofd]
        for taal, per in weergave.items():
            # een "vertaling" met dezelfde woorden als het origineel (een naam, een citaat dat bleef staan) is er geen
            # en nooit over een Engelse versie uit het lab heen (#34.2x)
            if (taal != p["taal"] and p["taal"] != "und" and taal not in per_taal and per.get(p["nummer"])
                    and _kaal(per[p["nummer"]]) != _kaal(p["bewering"])):
                per_taal[taal] = (per[p["nummer"]], vertaalmaker.get(taal, "") if isinstance(vertaalmaker, dict)
                                  else vertaalmaker)
        if per_taal:
            vertalingen[p["nummer"]] = per_taal
    gewijzigd = sum(1 for lid in (lid for p in samen["paginas"] for lid in p["leden"])
                    if nummer(lid) in talen and talen[nummer(lid)] != (lab_taal.get(lid) or "und"))
    pagina_van = {lid: p["nummer"] for p in samen["paginas"] for lid in p["leden"]}
    opgedoken = sorted({
        (pagina_van[cid], naam, soort, niveau, bron_id, dag or "", url)
        for cid, naam, soort, niveau, bron_id, dag, url in conn.execute(
            "SELECT a.claim_id, ac.naam, ac.soort, a.niveau, a.bron_id, a.datum, a.url FROM attributie a "
            "JOIN actor ac ON ac.actor_id = a.actor_id")
        if cid in pagina_van and bron_id in vrij})
    # de eigen factchecks als pagina's van het archief, met de eigen redactie als bron (#37.4, SPECS E10.S4 AC2)
    eigen_pag = eigen_paginas(eigen or [], concepten, datum[:10])
    if eigen_pag:
        samen["paginas"] = sorted(samen["paginas"] + eigen_pag, key=lambda p: p["nummer"])
        vrij = {**vrij, EIGEN_BRON["bron"]: dict(EIGEN_BRON)}
    # de wereldlijst (B90, B91, #37.12): elk overzicht een gewone factcheck met de checks van de redacties
    from doublecheck import wereldlijst as wl_

    try:
        wereld_pag, wereld = wl_.paginas(wereldlijst or [], register, concepten)
    except wl_.Weigering as fout:
        raise Weigering(str(fout)) from None
    if wereld_pag:
        # de vertalingen voor weergave die hun leesproef haalden, zoals bij elke pagina: nooit in de taal van de bewering,
        # en geen "vertaling" met dezelfde woorden als het origineel
        for p in wereld_pag:
            p["vertaald"] = {**{taal: (per[p["nummer"]], vertaalmaker.get(taal, "") if isinstance(vertaalmaker, dict)
                                       else vertaalmaker)
                                for taal, per in weergave.items()
                                if taal != p["taal"] and per.get(p["nummer"]) and _kaal(per[p["nummer"]]) != _kaal(p["bewering"])},
                             **{taal: x for taal, x in p.get("vertaald", {}).items() if taal != p["taal"]}}
        samen["paginas"] = sorted(samen["paginas"] + wereld_pag, key=lambda p: p["nummer"])
        vrij = {**vrij, wl_.BRON["bron"]: dict(wl_.BRON)}

    uit = Path(uit)
    uit.mkdir(parents=True, exist_ok=True)
    bestand = uit / "publicatie.db"
    bestand.unlink(missing_ok=True)
    pub = sqlite3.connect(bestand)
    pub.executescript(SCHEMA)
    gebruikt = {k["bron"] for p in samen["paginas"] for k in p["checks"]} | {o[4] for o in opgedoken}
    pub.executemany("INSERT INTO bron VALUES (:bron, :naam, :licentie, :naamsvermelding, :url)",
                    [vrij[b] for b in sorted(gebruikt)])
    indeling, themas, landen = indeling or {}, (themas or []) if indeling else [], (landen or {}) if indeling else {}
    per_thema = {t["sleutel"]: {o["sleutel"] for o in t.get("onderdelen", [])} for t in themas}
    volg = 0
    for t in themas:
        for ding, ouder in [(t, None)] + [(o, t["sleutel"]) for o in t.get("onderdelen", [])]:
            pub.execute(f"INSERT INTO thema VALUES {_plekken(3 + len(SITETALEN))}",
                        (ding["sleutel"], ouder, volg, *(ding["naam"].get(taal) or ding["naam"]["en"] for taal in SITETALEN)))
            volg += 1
    ingedeeld = {p["nummer"]: _indeling_ok(indeling.get(p["nummer"]), per_thema, landen) for p in samen["paginas"]}
    pub.executemany(f"INSERT INTO land VALUES {_plekken(1 + len(SITETALEN))}", [
        (code, *(landen[code].get(taal) or landen[code]["en"] for taal in SITETALEN)) for code in sorted({i[3] for i in ingedeeld.values() if i[3]})])
    n_letters = {"beweringen": 0, "vertalingen": 0}
    n_vragen = {"mee": 0, "verouderd": 0}
    n_afscherming = {"privepersoon": 0, "niet_gelezen": 0, "weggelaten": 0}
    n_kenmerk = {"versie": sv.VERSIE if soortwoorden else "", "soort": 0, "vorm": 0}
    n_voorlopig: dict[str, int] = {}
    for p in samen["paginas"]:
        # maatregel 2 (#34.2bw): buiten zoekmachines bij een privépersoon in een gevoelige context, en zolang de tekst niet
        # gelezen is; bij een minderjarige die twee lezingen zo noemden, op de plek van de naam het merkteken dat het
        # platform als sticker *naam weggelaten* toont, in elke tekst van de pagina
        reden, naam = _afscherming(afscherming, p)
        if reden:
            pub.execute("INSERT INTO afscherming VALUES (?, ?)", (p["nummer"], reden))
            n_afscherming[reden] += 1
        origineel = p["bewering"]
        if naam:
            p = {**p, "bewering": _maskeer(p["bewering"], naam),
                 "formuleringen": [{**f, "tekst": _maskeer(f["tekst"], naam)} for f in p["formuleringen"] if _noemt(f["tekst"], naam)]}
            n_afscherming["weggelaten"] += 1
        pub.execute("INSERT INTO pagina VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["nummer"], p["bewering"], p["taal"], p["richting"], p["label"],
                     json.dumps(p["eerder"], ensure_ascii=False), len(p["checks"]), p["redacties"],
                     json.dumps(p["talen"], ensure_ascii=False), p["eerste_datum"], p["laatste_datum"],
                     *ingedeeld[p["nummer"]], json.dumps(wie_het_zegt(p["label"], p["checks"]), ensure_ascii=False)))
        pub.executemany("INSERT INTO check_ VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
            (p["nummer"], volg, k["redactie"], k["oordeel"], k["oordeel_eigen"], k["datum"], k["taal"], k["url"],
             k["link"], k["archief_url"], k["archief_datum"], k["bron"]) for volg, k in enumerate(p["checks"])])
        pub.executemany("INSERT INTO formulering VALUES (?,?,?,?,?)", [
            (p["nummer"], f["nummer"], f["tekst"], f["taal"], f["richting"]) for f in p["formuleringen"]])
        per_taal = {**p.get("vertaald", {}), **vertalingen.get(p["nummer"], {})}
        # een voorlopige vertaling (B93): alleen waar geen geldige ligt, nooit in de taal van de bewering of met dezelfde
        # woorden; de site toont haar met een banner en houdt haar buiten zoekmachines
        hier_voorlopig = set()
        for taal_v, per_v in sorted((voorlopig or {}).items()):
            tekst_v = per_v.get(p["nummer"])
            if (tekst_v and taal_v in SITETALEN and taal_v not in per_taal and taal_v != p["taal"]
                    and _kaal(tekst_v) != _kaal(p["bewering"])):
                per_taal[taal_v] = (tekst_v, (voorlopig_maker or {}).get(taal_v, ""))
                hier_voorlopig.add(taal_v)
                n_voorlopig[taal_v] = n_voorlopig.get(taal_v, 0) + 1
        # een vertaling in hoofdletters in normaal schrift (#34.2ae): het is tekst van Factiz, en alleen als er niets
        # anders verandert dan hoofd- en kleine letters; de bewering zelf blijft het citaat, met haar normale schrift ernaast
        per_taal = {taal: (_normaal(hoofdletters, p["nummer"], taal, tekst, n_letters) or tekst, maker)
                    for taal, (tekst, maker) in per_taal.items()}
        ongemaskeerd = per_taal
        if naam:    # een vertaling waarin de naam niet letterlijk staat, kan haar anders schrijven: die blijft weg
            per_taal = {taal: (_maskeer(tekst, naam), maker) for taal, (tekst, maker) in per_taal.items() if _noemt(tekst, naam)}
        if (normaal := _normaal(hoofdletters, p["nummer"], "", p["bewering"], n_letters)) is not None:
            pub.execute("INSERT INTO bewering_normaal VALUES (?, ?)", (p["nummer"], normaal))
        # de soort volgens de redactie en de vorm uit de Engelse tekst van de bewering (#34.2ak): geen model, alleen
        # wat zeker is; de soort alleen met de nagelezen woorden
        soort = sv.soort_van([k["oordeel_eigen"] for k in p["checks"]], soortwoorden or {})
        vorm = sv.vorm_van(p["bewering"] if p["taal"] == "en" else per_taal.get("en", ("", ""))[0])
        if "kenmerk" in p:      # een eigen factcheck zegt haar soort en vorm zelf
            soort, vorm = p["kenmerk"]
        if soort or vorm:
            pub.execute("INSERT INTO kenmerk VALUES (?, ?, ?)", (p["nummer"], soort, vorm))
            n_kenmerk["soort"] += bool(soort)
            n_kenmerk["vorm"] += bool(vorm)
        pub.executemany("INSERT INTO vertaling VALUES (?,?,?,?,0,?)", [
            (p["nummer"], taal, tekst, maker, int(taal in hier_voorlopig)) for taal, (tekst, maker) in sorted(per_taal.items())])
        # de zoekvraag (#34.2cf, B87), alleen bij precies de tekst waaruit ze kwam: de bewering, of haar vertaling
        if zv := (zoekvragen or {}).get(p["nummer"]):
            nu = origineel if zv["taal"] == p["taal"] else ongemaskeerd.get(zv["taal"], (origineel, ""))[0]
            if " ".join(nu.split()) == " ".join(zv["bron"].split()) and (not naam or zv["taal"] == p["taal"] or zv["taal"] in per_taal):
                vraag, onderwerp = (_maskeer(zv["vraag"], naam), _maskeer(zv["onderwerp"], naam)) if naam else (zv["vraag"], zv["onderwerp"])
                pub.execute("INSERT INTO zoekvraag VALUES (?, ?, ?, ?)", (p["nummer"], zv["taal"], vraag, onderwerp))
                n_vragen["mee"] += 1
            else:
                n_vragen["verouderd"] += 1
        tekst = "\n".join([p["bewering"]] + [f["tekst"] for f in p["formuleringen"]])
        # Elke vertaling telt mee bij het zoeken op woorden, ook een voorlopige (B93): wie Portugees of Japans typt, vindt
        # ook de bewering in het Engels (#37.16). Het register op drietallen (voor schriften zonder spaties) houdt de
        # bewering zelf en haar vertalingen in zo'n schrift. De woorden staan daarna in de tabel `woord` (`_woorden_erin`).
        vertaald = sorted(per_taal.items())
        woorden = "\n".join([tekst] + [t for _, (t, _) in vertaald])
        tekens = "\n".join([tekst] + [t for taal, (t, _) in vertaald if taal in ZONDER_SPATIES])
        if naam:    # het merkteken van een weggelaten naam is geen woord om op te zoeken (#34.2bw)
            from factiz_site.i18n import WEGGELATEN

            woorden, tekens = woorden.replace(WEGGELATEN, " "), tekens.replace(WEGGELATEN, " ")
        pub.execute("INSERT INTO zoek (nummer, tekst) VALUES (?, ?)", (p["nummer"], woorden))
        pub.execute("INSERT INTO zoek3 (nummer, tekst) VALUES (?, ?)", (p["nummer"], tekens))
    pub.executemany("INSERT INTO verwijzing VALUES (?, ?)", sorted(samen["verwijzingen"].items()))
    op_pagina = {woordsleutel(k["oordeel_eigen"]) for p in samen["paginas"] for k in p["checks"]}
    met_glos = sorted(op_pagina & set(glossen or {}))
    pub.executemany("INSERT INTO oordeel_glos VALUES (?, ?, ?)", [
        (tekst, taal, glossen[tekst][taal]) for tekst in met_glos for taal in SITETALEN if (glossen[tekst].get(taal) or "")])
    bestaat = {p["nummer"] for p in samen["paginas"]}
    verwant = {pagina: [a for a in dict.fromkeys(andere) if a in bestaat and a != pagina][:5]
               for pagina, andere in sorted((lijkt_op or {}).items()) if pagina in bestaat}
    pub.executemany("INSERT INTO lijkt_op VALUES (?, ?, ?)", [
        (pagina, volg, ander) for pagina, andere in verwant.items() for volg, ander in enumerate(andere)])
    # dezelfde bewering (#34.2bp): alleen tussen pagina's die er zijn en geen redactie delen, in beide richtingen
    redacties_van: dict[str, set[str]] = {}
    for p in samen["paginas"]:
        redacties_van[p["nummer"]] = {k["redactie"] for k in p["checks"]}
    paren_zelfde = {frozenset((a, b)) for a, andere in (zelfde or {}).items() for b in andere
                    if a != b and a in bestaat and b in bestaat and not redacties_van[a] & redacties_van[b]}
    gelijk: dict[str, list[str]] = {}
    for paar_ in sorted(paren_zelfde, key=sorted):
        a, b = sorted(paar_)
        gelijk.setdefault(a, []).append(b)
        gelijk.setdefault(b, []).append(a)
    gelijk = {pagina: sorted(andere)[:MAX_ZELFDE] for pagina, andere in sorted(gelijk.items())}
    pub.executemany("INSERT INTO zelfde VALUES (?, ?, ?)", [
        (pagina, volg, ander) for pagina, andere in gelijk.items() for volg, ander in enumerate(andere)])
    met_waarom = {pagina: w for pagina, w in sorted(((waarom or {}).get("punten") or {}).items()) if pagina in bestaat}
    pub.executemany("INSERT INTO waarom VALUES (?, ?, ?, ?)", [
        (pagina, volg, punt, w["url"]) for pagina, w in met_waarom.items() for volg, punt in enumerate(w["punten"][:3])])
    pub.executemany("INSERT INTO opgedoken VALUES (?,?,?,?,?,?,?)", opgedoken)
    rijen_samen = []
    for pagina, zinnen in sorted(wereld["zinnen"].items()):
        if pagina in bestaat:
            per_taal: dict[str, int] = {}
            for taal, soort, zin, bronnen in zinnen:
                rijen_samen.append((pagina, taal, per_taal.get(taal, 0), soort, zin, json.dumps(bronnen)))
                per_taal[taal] = per_taal.get(taal, 0) + 1
    pub.executemany("INSERT INTO samenvatting VALUES (?, ?, ?, ?, ?, ?)", rijen_samen)
    in_dossiers = _dossiers_erin(pub, dossiers or [], concepten, samen, per_thema)
    in_begrippen = _begrippen_erin(pub, dossiers or [])
    in_namen = _namen_erin(pub, namen, samen, namen_niet, namen_concept, naamvormen)
    in_eigen = _eigen_erin(pub, eigen or [], concepten, datum[:10])
    n_woorden = _woorden_erin(pub)
    getal = controlegetal(pub)
    pub.executemany("INSERT INTO meta VALUES (?, ?)", [("schema", str(SCHEMA_VERSIE)), ("release", datum),
                                                       ("controlegetal", getal)])
    if waarom:     # de gemeten foutmarge, die de site bij het blok laat zien (B77)
        pub.execute("INSERT INTO meta VALUES ('waarom_meting', ?)", (json.dumps(waarom["meting"], sort_keys=True),))
    n_concepten = sum(d["concept"] for d in in_dossiers.values())
    if (n_concepten or in_namen["concept"] or in_eigen["concept"] or wereld["telling"]["concept"]
            or (hoofdletters_concept and any(n_letters.values()))):
        # een voorbeeld: `controleer` weigert dit bestand voor een uitgave
        pub.execute("INSERT INTO meta VALUES ('concepten', '1')")
    if in_namen["concept"]:
        pub.execute("INSERT INTO meta VALUES ('namen_concept', '1')")
    pub.commit()
    pub.close()

    manifest = {
        "bestand": str(bestand), "schema": SCHEMA_VERSIE, "release": datum,
        "gebouwd_op": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "paginas": len(samen["paginas"]), "checks": sum(len(p["checks"]) for p in samen["paginas"]),
        "paginas_met_meer_checks": sum(len(p["checks"]) >= 2 for p in samen["paginas"]),
        "formuleringen": sum(len(p["formuleringen"]) for p in samen["paginas"]),
        "opgedoken": len(opgedoken),
        "begrippen": in_begrippen,
        "per_bron": dict(sorted(Counter(k["bron"] for p in samen["paginas"] for k in p["checks"]).items())),
        "per_taal": dict(sorted(Counter(p["taal"] for p in samen["paginas"]).items())),
        "weggelaten": samen["weggelaten"], "woorden": n_woorden, "controlegetal": getal,
        "met_thema": sum(i[0] is not None for i in ingedeeld.values()),
        "per_thema": dict(sorted(Counter(i[0] for i in ingedeeld.values() if i[0]).items())),
        "met_land": sum(bool(i[3]) for i in ingedeeld.values()),
        "taalcorrecties": gewijzigd, "vertalingen": sum(len(v) for v in vertalingen.values()),
        "vertalingen_per_taal": dict(sorted(Counter(t for v in vertalingen.values() for t in v).items())),
        "dossiers": in_dossiers, "concepten": n_concepten, "namen": in_namen,
        "oordelen_gelezen": gelezen, "glossen": len(met_glos),
        "lijkt_op": {"paginas": sum(bool(v) for v in verwant.values()), "verwijzingen": sum(len(v) for v in verwant.values())},
        "zelfde": {"paginas": len(gelijk), "verwijzingen": sum(len(v) for v in gelijk.values())},
        "waarom": {"paginas": len(met_waarom), "punten": sum(len(w["punten"][:3]) for w in met_waarom.values())},
        "hoofdletters": {"versie": hl.VERSIE, **n_letters},
        "kenmerk": n_kenmerk, "eigen": in_eigen, "zoekvragen": n_vragen, "afscherming": n_afscherming,
        "wereldlijst": wereld["telling"], "voorlopig": dict(sorted(n_voorlopig.items())),
    }
    (uit / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return manifest


def controleer(bestand: str | Path, concepten: bool = False, namen_niet: frozenset[str] | set[str] | None = None,
               waarom_niet: list[dict] | None = None) -> dict:
    """Weigert een bestand dat niet uitgegeven mag worden: een ander schema, een vreemde tabel, een bron die nooit
    mag, een check zonder bron, een pagina zonder check, een verwijzing naar niets, een dossier dat niet klopt of dat
    de PO nog niet goedkeurde, een naam die de regels niet haalt of die een mens weghaalde, een punt bij waarom het
    niet klopt dat een mens weghaalde (B77), of een inhoud die niet meer bij het controlegetal past. Met `concepten` mag een voorbeeld voor de eigen computer erdoor; uitgeven mag
    het daarmee niet."""
    from doublecheck import namen as nm

    namen_niet = nm.niet_lijst() if namen_niet is None else namen_niet
    if waarom_niet is None:
        from doublecheck import waarom

        waarom_niet = waarom.niet_lijst()
    conn = sqlite3.connect(f"file:{bestand}?mode=ro", uri=True)
    try:
        meta = dict(conn.execute("SELECT sleutel, waarde FROM meta"))
        if meta.get("schema") != str(SCHEMA_VERSIE):
            raise Weigering(f"schema {meta.get('schema')!r}, verwacht {SCHEMA_VERSIE}")
        tabellen = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                    if not r[0].startswith(("zoek_", "zoek3_", "sqlite_"))}
        if tabellen != set(TABELLEN) | {"meta", "zoek", "zoek3"}:
            raise Weigering(f"onverwachte tabellen: {sorted(tabellen ^ (set(TABELLEN) | {'meta', 'zoek', 'zoek3'}))}")
        if woordrijen(conn) != conn.execute("SELECT term, doc, lengte, kandidaat, gewoon FROM woord ORDER BY term").fetchall():
            raise Weigering("de tabel woord past niet bij het zoekregister (#37.16)")
        bronnen = {r[0] for r in conn.execute("SELECT bron FROM bron")}
        if bronnen & NOOIT:
            raise Weigering(f"een bron die nooit uitgegeven mag worden: {sorted(bronnen & NOOIT)}")
        for vraag, wat in (
                ("SELECT COUNT(*) FROM check_ WHERE bron NOT IN (SELECT bron FROM bron)", "checks zonder bron"),
                ("SELECT COUNT(*) FROM opgedoken WHERE bron NOT IN (SELECT bron FROM bron)", "koppelingen zonder bron"),
                ("SELECT COUNT(*) FROM pagina WHERE nummer NOT IN (SELECT pagina FROM check_)", "pagina's zonder check"),
                ("SELECT COUNT(*) FROM verwijzing WHERE pagina NOT IN (SELECT nummer FROM pagina)",
                 "verwijzingen naar niets"),
                ("SELECT COUNT(*) FROM samenvatting s WHERE s.pagina NOT IN (SELECT nummer FROM pagina) OR bronnen = '[]' "
                 "OR EXISTS (SELECT 1 FROM json_each(s.bronnen) j WHERE j.value NOT IN "
                 "(SELECT url FROM check_ c WHERE c.pagina = s.pagina))",
                 "zinnen van de wereldlijst zonder pagina of met een link die geen check van die pagina is"),
                ("SELECT COUNT(*) FROM pagina WHERE checks <> (SELECT COUNT(*) FROM check_ c WHERE c.pagina = nummer)",
                 "pagina's met een verkeerde telling"),
                ("SELECT COUNT(*) FROM pagina WHERE thema IS NOT NULL AND thema NOT IN "
                 "(SELECT sleutel FROM thema WHERE ouder IS NULL)", "pagina's met een thema dat het bestand niet kent"),
                ("SELECT COUNT(*) FROM pagina WHERE onderdeel <> '' AND onderdeel NOT IN "
                 "(SELECT sleutel FROM thema t WHERE t.ouder = pagina.thema)", "pagina's met een onderdeel buiten hun thema"),
                ("SELECT COUNT(*) FROM pagina WHERE tweede <> '' AND tweede NOT IN "
                 "(SELECT sleutel FROM thema WHERE ouder IS NULL)", "pagina's met een tweede thema dat niet bestaat"),
                ("SELECT COUNT(*) FROM pagina WHERE land <> '' AND land NOT IN (SELECT code FROM land)",
                 "pagina's met een land dat het bestand niet kent"),
                ("SELECT COUNT(*) FROM vertaling WHERE pagina NOT IN (SELECT nummer FROM pagina) OR tekst = ''",
                 "vertalingen zonder bewering of zonder tekst"),
                (f"SELECT COUNT(*) FROM vertaling WHERE taal NOT IN ({', '.join(repr(t) for t in SITETALEN)})",
                 "vertalingen in een taal die de site niet heeft"),
                (f"SELECT COUNT(*) FROM oordeel_glos WHERE taal NOT IN ({', '.join(repr(t) for t in SITETALEN)})",
                 "vertaalde woorden van een redactie in een taal die de site niet heeft"),
                ("SELECT COUNT(*) FROM lijkt_op WHERE pagina NOT IN (SELECT nummer FROM pagina) OR ander NOT IN "
                 "(SELECT nummer FROM pagina) OR pagina = ander", "verwijzingen bij lijkt op naar niets of naar zichzelf"),
                ("SELECT COUNT(*) FROM zelfde WHERE pagina NOT IN (SELECT nummer FROM pagina) OR ander NOT IN "
                 "(SELECT nummer FROM pagina) OR pagina = ander", "dezelfde bewering naar niets of naar zichzelf"),
                ("SELECT COUNT(*) FROM zelfde z WHERE EXISTS (SELECT 1 FROM check_ a JOIN check_ b ON a.redactie = b.redactie "
                 "WHERE a.pagina = z.pagina AND b.pagina = z.ander)", "dezelfde bewering bij een redactie die beide checkte"),
                ("SELECT COUNT(*) FROM zelfde z WHERE NOT EXISTS (SELECT 1 FROM zelfde y WHERE y.pagina = z.ander "
                 "AND y.ander = z.pagina)", "dezelfde bewering maar één kant op"),
                ("SELECT COUNT(*) FROM waarom WHERE pagina NOT IN (SELECT nummer FROM pagina) OR volg NOT BETWEEN 0 AND 2 "
                 "OR url NOT LIKE 'https://euvsdisinfo.eu/%'",
                 "punten bij waarom het niet klopt zonder pagina, meer dan drie, of met een link die niet naar EUvsDisinfo wijst"),
                ("SELECT COUNT(*) FROM vertaling v JOIN pagina p ON p.nummer = v.pagina WHERE p.taal = v.taal",
                 "vertalingen in de taal van de bewering zelf"),
                ("SELECT COUNT(*) FROM bewering_normaal WHERE pagina NOT IN (SELECT nummer FROM pagina) OR tekst = ''",
                 "normaal schrift zonder bewering of zonder tekst"),
                ("SELECT COUNT(*) FROM kenmerk WHERE pagina NOT IN (SELECT nummer FROM pagina)",
                 "een soort of vorm zonder bewering"),
                ("SELECT COUNT(*) FROM zoekvraag WHERE pagina NOT IN (SELECT nummer FROM pagina) OR length(vraag) > 160 "
                 "OR NOT (vraag LIKE '%?' OR vraag LIKE '%？' OR vraag LIKE '%؟')",
                 "een zoekvraag zonder bewering, te lang of zonder vraagteken"),
                # een weggelaten naam (#34.2bw) alleen op een pagina die om een privépersoon buiten zoekmachines blijft
                ("SELECT COUNT(*) FROM pagina p WHERE NOT EXISTS (SELECT 1 FROM afscherming a WHERE a.pagina = p.nummer AND "
                 "a.reden = 'privepersoon') AND (instr(p.bewering, '\u27e6redacted\u27e7') OR EXISTS (SELECT 1 FROM "
                 "vertaling v WHERE v.pagina = p.nummer AND instr(v.tekst, '\u27e6redacted\u27e7')) OR EXISTS (SELECT 1 "
                 "FROM zoekvraag z WHERE z.pagina = p.nummer AND instr(z.vraag || z.onderwerp, '\u27e6redacted\u27e7')))",
                 "een weggelaten naam op een pagina die niet afgeschermd is"),
                ("SELECT COUNT(*) FROM dossier_item WHERE dossier NOT IN (SELECT sleutel FROM dossier)",
                 "items zonder dossier"),
                ("SELECT COUNT(*) FROM dossier_item WHERE soort = 'factcheck' AND (pagina IS NULL OR pagina NOT IN "
                 "(SELECT nummer FROM pagina))", "factchecks in een dossier zonder pagina"),
                ("SELECT COUNT(*) FROM dossier_item WHERE soort <> 'factcheck' AND (pagina IS NOT NULL OR bron = '' OR "
                 "url NOT LIKE 'http%' OR datum = '' OR "
                 + " OR ".join(f"titel_{t} = ''" for t in SITETALEN) + ")", "items zonder bron, link of titel"),
                ("SELECT COUNT(*) FROM dossier WHERE " + " OR ".join(f"naam_{t} = '' OR inleiding_{t} = ''"
                                                                     for t in SITETALEN),
                 "dossiers zonder naam of inleiding in een van de talen"),
                ("SELECT COUNT(*) FROM dossier WHERE soort = 'netwerk' AND (vastgesteld_door = '' OR "
                 "vastgesteld_url NOT LIKE 'http%' OR vastgesteld_datum = '')",
                 "netwerkdossiers zonder wie het netwerk vaststelde"),
                ("SELECT COUNT(*) FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier WHERE d.soort = 'netwerk' "
                 "AND i.soort = 'factcheck' AND (i.bron = '' OR i.url NOT LIKE 'http%' OR "
                 "i.niveau NOT IN ('waargenomen', 'toegeschreven'))",
                 "factchecks in een netwerkdossier zonder bron of niveau"),
                ("SELECT COUNT(*) FROM (SELECT i.pagina FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier "
                 "WHERE d.soort = 'verhaal' AND i.soort = 'factcheck' GROUP BY i.pagina "
                 "HAVING COUNT(DISTINCT i.dossier) > 1)", "factchecks in twee verhaaldossiers"),
                ("SELECT COUNT(*) FROM dossier_item i JOIN dossier d ON d.sleutel = i.dossier WHERE i.versie <> '' AND "
                 "(i.soort <> 'factcheck' OR d.soort <> 'verhaal')", "items met een versie buiten een verhaaldossier"),
                ("SELECT COUNT(*) FROM (SELECT 1 FROM dossier_item WHERE versie <> '' GROUP BY dossier, versie "
                 "HAVING COUNT(*) < 2)", "versies met één factcheck"),
                ("SELECT COUNT(*) FROM dossier WHERE thema IS NOT NULL AND thema NOT IN "
                 "(SELECT sleutel FROM thema WHERE ouder IS NULL)", "dossiers met een thema dat het bestand niet kent"),
                ("SELECT COUNT(*) FROM dossier d WHERE onderdeel <> '' AND onderdeel NOT IN "
                 "(SELECT sleutel FROM thema t WHERE t.ouder = d.thema)", "dossiers met een onderdeel buiten hun thema"),
                ("SELECT COUNT(*) FROM dossier_verwant WHERE dossier NOT IN (SELECT sleutel FROM dossier) OR verwant NOT IN "
                 "(SELECT sleutel FROM dossier) OR dossier = verwant", "verwijzingen tussen dossiers naar niets"),
                ("SELECT COUNT(*) FROM pagina_naam WHERE pagina NOT IN (SELECT nummer FROM pagina) OR naam NOT IN "
                 "(SELECT nummer FROM naam)", "namen bij een pagina of een naam die het bestand niet kent"),
                ("SELECT COUNT(*) FROM naam_vorm WHERE naam NOT IN (SELECT nummer FROM naam)",
                 "bijnamen bij een naam die het bestand niet kent"),
                ("SELECT COUNT(*) FROM naam WHERE nummer NOT GLOB 'Q[1-9]*' OR substr(nummer, 2) GLOB '*[^0-9]*' OR "
                 + " OR ".join(f"naam_{t} = ''" for t in SITETALEN), "namen zonder nummer of zonder naam in een van de talen"),
                (f"SELECT COUNT(*) FROM naam n WHERE paginas < {int(nm.MIN_PAGINAS)} OR paginas <> "
                 "(SELECT COUNT(*) FROM pagina_naam k WHERE k.naam = n.nummer)",
                 "namen op te weinig pagina's of met een verkeerde telling"),
                (f"SELECT COUNT(*) FROM naam WHERE wikis < {int(nm.MIN_WIKIS)}", "namen in te weinig talen van Wikipedia"),
                ("SELECT COUNT(*) FROM naam n WHERE soort = 'persoon' AND (SELECT COUNT(DISTINCT c.redactie) FROM "
                 f"pagina_naam k JOIN check_ c ON c.pagina = k.pagina WHERE k.naam = n.nummer) < {int(nm.MIN_REDACTIES)}",
                 "personen bij te weinig redacties")):
            n = conn.execute(vraag).fetchone()[0]
            if n:
                raise Weigering(f"{n} {wat}")
        # het normale schrift verandert alleen hoofd- en kleine letters van het citaat (#34.2ae)
        anders = [nr for nr, bewering, tekst in conn.execute(
            "SELECT p.nummer, p.bewering, n.tekst FROM bewering_normaal n JOIN pagina p ON p.nummer = n.pagina")
            if not hl.alleen_hoofdletters(bewering, tekst)]
        if anders:
            raise Weigering(f"normaal schrift dat meer verandert dan hoofdletters: {', '.join(anders[:5])}")
        # één naam per redactie (#34.2ao): een naam die alleen in kast, spaties of leestekens verschilt, maakt van één
        # redactie er twee, met elk een deel van haar checks; het lab telt al zo (`evidence._uitgeversleutel`, DR7)
        from doublecheck.evidence import _uitgeversleutel
        per_sleutel: dict[str, set[str]] = {}
        for (naam,) in conn.execute("SELECT DISTINCT redactie FROM check_"):
            per_sleutel.setdefault(_uitgeversleutel(naam), set()).add(naam)
        dubbel = sorted(" / ".join(sorted(namen)) for namen in per_sleutel.values() if len(namen) > 1)
        if dubbel:
            raise Weigering(f"een redactie onder meer namen: {'; '.join(dubbel[:5])}")
        if controlegetal(conn) != meta.get("controlegetal"):
            raise Weigering("de inhoud past niet meer bij het controlegetal")
        weggehaald = sorted({r[0] for r in conn.execute("SELECT nummer FROM naam")} & set(namen_niet))
        if weggehaald:
            raise Weigering(f"een naam die is weggehaald, staat er nog in: {', '.join(weggehaald)}")
        hele = {r["pagina"] for r in waarom_niet if not r.get("punt")}
        punten = {(r["pagina"], r["punt"]) for r in waarom_niet if r.get("punt")}
        nog = sorted({p for p, punt in conn.execute("SELECT pagina, punt FROM waarom") if p in hele or (p, punt) in punten})
        if nog:
            raise Weigering(f"een punt bij waarom het niet klopt dat is weggehaald, staat er nog in: {', '.join(nog)}")
        if meta.get("namen_concept") and not concepten:
            raise Weigering("de namen zijn nog niet door de PO gelezen: dit is een voorbeeld, geen uitgave")
        from doublecheck import redactie

        eigen = []
        for sleutel, concept, gegevens in conn.execute("SELECT sleutel, concept, gegevens FROM eigen_check ORDER BY sleutel"):
            if concept and not concepten:
                raise Weigering(f"eigen factcheck {sleutel} is een concept: dit is een voorbeeld, geen uitgave")
            g = json.loads(gegevens)
            fouten = redactie.controleer(g)
            # het adres en de vindbare talen opnieuw uit de check zelf (PLAN #37.11): een adres dat niet klopt, of een
            # vertaling die vindbaar heet zonder dat de redactie haar las, gaat niet uit
            verwacht = eigen_adressen(g, (g.get("maand") or "") + "-01")
            if any(g.get(k) != v for k, v in verwacht.items()):
                fouten.append("het adres of de vindbare talen passen niet bij de check")
            if fouten:
                raise Weigering(f"eigen factcheck {sleutel}: {'; '.join(fouten)}")
            eigen.append(g)
        if botsing := redactie.botsingen(eigen, ""):
            raise Weigering(f"eigen factcheck: {'; '.join(botsing)}")
        n_concepten = conn.execute("SELECT COUNT(*) FROM dossier WHERE concept <> 0").fetchone()[0]
        if (n_concepten or meta.get("concepten")) and not concepten:
            raise Weigering(f"{n_concepten} dossiers zonder akkoord van de PO: dit is een voorbeeld, geen uitgave")
        return {"paginas": conn.execute("SELECT COUNT(*) FROM pagina").fetchone()[0],
                "checks": conn.execute("SELECT COUNT(*) FROM check_").fetchone()[0], "bronnen": sorted(bronnen),
                "release": meta.get("release"), "dossiers": conn.execute("SELECT COUNT(*) FROM dossier").fetchone()[0],
                "namen": conn.execute("SELECT COUNT(*) FROM naam").fetchone()[0],
                "eigen": conn.execute("SELECT COUNT(*) FROM eigen_check").fetchone()[0]}
    finally:
        conn.close()


def main() -> None:  # pragma: no cover - CLI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stap", choices=["bouwen", "controleren"])
    p.add_argument("bestand", nargs="?", help="controleren: het bestand")
    p.add_argument("--uit", help="bouwen: de map (standaard data/publicatie/<vandaag>; met --concepten data/voorbeeld)")
    p.add_argument("--lab", default=str(WORTEL / "doublecheck.db"))
    p.add_argument("--release", help="bouwen: de naam (standaard vandaag); een tweede op dezelfde dag met een letter: 2026-11-16b")
    p.add_argument("--concepten", action="store_true",
                   help="ook dossiers zonder akkoord van de PO: een voorbeeld voor de eigen computer, geen uitgave")
    a = p.parse_args()
    try:
        if a.stap == "controleren":
            if not a.bestand:
                raise SystemExit("controleren vraagt een bestand")
            print("in orde:", controleer(a.bestand, concepten=a.concepten))
            return
        from doublecheck.config import load_config

        lab = sqlite3.connect(f"file:{a.lab}?mode=ro", uri=True)
        release = releasenaam(a.release)
        uit = (Path(a.uit) if a.uit else VOORBEELD if a.concepten
               else WORTEL / "data" / "publicatie" / release)
        if a.concepten and (WORTEL / "data" / "publicatie") in uit.resolve().parents:
            raise SystemExit("geweigerd: een voorbeeld met concepten hoort niet tussen de uitgaven in data/publicatie/")
        from doublecheck import themas as th

        open_, waarom = th.poort()
        extra = {}
        if open_:
            extra = {"indeling": {r["nummer"]: r["uit"] for r in th._jsonl(th.MAP / "indeling.jsonl") if r["uit"]},
                     "themas": th.lees_lijst(th.LIJST_PAD),
                     "landen": json.loads((WORTEL / "content" / "landen.json").read_text(encoding="utf-8"))["landen"]}
        print(f"thema's: {'mee' if open_ else 'niet mee'} ({waarom})")
        from doublecheck import taallabels

        extra["talen"], taalreden = taallabels.geldige_correcties()
        from doublecheck import weergave

        extra["vertalingen"], waarom_per_taal = weergave.geldige_vertalingen()
        # de voorlopige vertalingen tot de ronde van 3 december (B93)
        extra["voorlopig"] = weergave.voorlopige(extra["vertalingen"])
        extra["voorlopig_maker"] = {taal: weergave.maker(taal) for taal in extra["voorlopig"]}
        print("voorlopige vertalingen (B93):", {t: len(v) for t, v in extra["voorlopig"].items()})
        extra["vertaalmaker"] = {taal: weergave.maker(taal) for taal in weergave.DOELTALEN}
        print("vertalingen voor weergave:", "; ".join(f"{t}: {w}" for t, w in waarom_per_taal.items()))
        from doublecheck import dossiers as ds

        # zonder thema's in de uitgave wordt het thema van een dossier niet getoetst en ook niet getoond
        extra["dossiers"] = ds.lees_alle(ds.MAP, extra.get("themas"))
        from doublecheck import redactie

        from doublecheck import eigenvertaling, redactiebeeld

        try:    # het beeld dat rondgaat, met pad en maat, als het gemaakt is (#37.5), en de geldige vertalingen (#37.8)
            extra["eigen"] = [{**redactiebeeld.erbij(c), "vertalingen": eigenvertaling.geldige(c)} for c in redactie.lees_alle()]
        except redactie.Weigering as e:
            raise SystemExit(f"geweigerd: {e}") from None
        from doublecheck import namen as nm

        namen_open, namen_waarom = nm.poort()
        samen_pad = nm.MAP / "samen.json"
        if samen_pad.exists() and (namen_open or a.concepten):
            extra.update(namen=json.loads(samen_pad.read_text(encoding="utf-8")), namen_concept=not namen_open,
                         namen_niet=nm.niet_lijst(), naamvormen=nm.vormen_van_wikidata())
        print(f"namen: {'mee' if namen_open else 'alleen in een voorbeeld' if a.concepten else 'niet mee'} ({namen_waarom})")
        from doublecheck import lijktop, oordeellezer

        extra["oordelen"], extra["glossen"], poorten = oordeellezer.geldige_lezingen()
        print("oordelen gelezen:", "; ".join(f"{k}: {'open' if v[0] else 'dicht'} ({v[1]})" for k, v in poorten.items()))
        extra["lijkt_op"], lijkt_reden = lijktop.geldige_paren()
        print("lijkt op:", lijkt_reden)
        from doublecheck import zelfdebewering

        extra["zelfde"], zelfde_reden = zelfdebewering.geldige_paren()
        print("dezelfde bewering:", zelfde_reden)
        from doublecheck import waarom

        extra["waarom"], waarom_reden = waarom.geldige_punten()
        print("waarom het niet klopt:", waarom_reden)
        from doublecheck import hoofdletters as hl_

        letters, letterreden = hl_.voor_de_uitgave()
        if not letters and a.concepten:     # de poort dicht: alleen in een voorbeeld (SPECS E9.S15 AC5)
            letters, extra["hoofdletters_concept"] = hl_.alles(), True
        extra["hoofdletters"] = letters
        from doublecheck import zoekvragen as zv_

        vragen, vraagreden = zv_.voor_de_uitgave()
        if not vragen and a.concepten:      # de poort dicht: alleen in een voorbeeld
            vragen = zv_.alles()
        extra["zoekvragen"] = vragen
        print("zoekvragen:", vraagreden, f"({len(vragen)})")
        from doublecheck import privepersonen as pp_

        extra["afscherming"] = pp_.voor_de_uitgave()
        print(f"privépersonen gelezen: {len(extra['afscherming'])} pagina's ({pp_.VERSIE})")
        from doublecheck import relevantie as rv_

        extra["particulier"], particulierreden = rv_.voor_de_uitgave()
        print("particulier:", particulierreden, f"({len(extra['particulier'])})")
        from doublecheck import feedstop as fs_

        try:                                 # de feed is gestopt (B91): zonder het bestand geen uitgave
            extra["feed"] = fs_.lees()
        except fs_.Weigering as fout:
            raise Weigering(str(fout)) from None
        print(f"feed van Data Commons: gestopt, {len(extra['feed'])} checks van 2026-11-23 mogen nog mee")
        from doublecheck import wereldlijst as wl_

        from doublecheck import wereldvertaling as wv_

        extra["wereldlijst"] = [{**o, "vertalingen": wv_.geldige(o)} for o in wl_.lees_alle()]
        print(f"wereldlijst: {len(extra['wereldlijst'])} overzichten in content/wereldlijst/")
        extra["soortwoorden"] = sv.lees_woorden()
        print(f"soort volgens de redactie: {len(extra['soortwoorden'])} nagelezen woorden ({sv.VERSIE})")
        print("hoofdletters:", letterreden)
        m = bouw(lab, uit, uren=load_config(None).bonnetjes.offline_na_uren, concepten=a.concepten, datum=release, **extra)
        for sleutel, d in m["dossiers"].items():
            print(f"dossier {sleutel}: {d['factchecks']} factchecks, {d['items']} andere items"
                  + (", CONCEPT" if d["concept"] else "")
                  + (f", weggevallen: {', '.join(d['weggevallen'])}" if d["weggevallen"] else ""))
        print(f"eigen factchecks: {m['eigen']['gepubliceerd']} gepubliceerd, {m['eigen']['concept']} concept, "
              f"{m['eigen']['vindbaar']} vindbare pagina's")
        print(f"met een thema: {m['met_thema']}, met een land: {m['met_land']}")
        print(f"namen: {m['namen']['mee']} ({m['namen']['per_soort']}), {m['namen']['paren']} paren, "
              f"{len(m['namen']['weggevallen'])} weggevallen" + (", CONCEPT" if m["namen"]["concept"] else ""))
        print(f"taallabels: {m['taalcorrecties']} hersteld ({taalreden}); vertalingen: {m['vertalingen_per_taal']}")
        print(f"oordelen gelezen: {m['oordelen_gelezen']} checks; vertaalde woorden: {m['glossen']}; "
              f"lijkt op: {m['lijkt_op']}; dezelfde bewering: {m['zelfde']}; waarom het niet klopt: {m['waarom']}")
        print(f"{m['paginas']} pagina's, {m['checks']} checks, {len(m['per_taal'])} talen; per bron {m['per_bron']}")
        print(f"weggelaten: {m['weggelaten']}; pagina's met meer dan één check: {m['paginas_met_meer_checks']}; "
              f"waar het opdook: {m['opgedoken']}")
        print("gecontroleerd:", controleer(m["bestand"], concepten=a.concepten))
        if m["concepten"] or m["namen"]["concept"]:
            print(f"LET OP: een voorbeeld met {m['concepten']} dossier(s) zonder akkoord van de PO"
                  + (" en met namen die de PO nog niet las" if m["namen"]["concept"] else "") + "; geen uitgave")
        print(m["bestand"])
    except Weigering as e:
        raise SystemExit(f"geweigerd: {e}") from None


if __name__ == "__main__":  # pragma: no cover
    main()
