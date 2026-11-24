"""De sets per taal voor de controle in het Spaans, het Portugees en het Duits (PLAN #32.42).

Per taal vijf sets in `data/talen/meting/<taal>.jsonl`, de bron van het meetplan `docs/meetplannen/32.42-<taal>.json`:
- *O*, verse onware berichten: de bewering van een check met *onwaar* of *misleidend* uit de recentste jaren die er zijn;
- *K*, bekende onware berichten: ouder, met de adressen van de eigen checks (een alarm met zo'n bron bewijst zichzelf);
- *W*, ware berichten: de kop en het begin van een artikel van Wikinews in die taal;
- *W-merk*, echte koppen van de afgelopen week onder de naam van het medium, uit de RSS van vijf grote media;
- *G*, gewone teksten: webtekst uit mC4 van de stiltetoets.

Bij het Duits geeft een check zonder categorie het oordeel dat Haiku uit de oordeelzin haalde (`data/talen/duits.jsonl`,
§161). Alles lokaal, behalve één verzoek per feed.

`vers` (#32.43) maakt per taal, ook het Engels, een nieuwe O, W en W-merk voor de meting van `lezer-v10`, in
`data/talen/vers/<taal>.jsonl`: niets wat de metingen gebruikten waarop de regels van §223 gebouwd zijn (`GEBRUIKT`),
Wikinews zonder de balk met koppen, en in het Portugees de kop en het begin van de pagina zelf (§224).

    python -m doublecheck.talenset bouwen --taal es|pt|de
    python -m doublecheck.talenset vers --taal en|es|pt|de
"""

from __future__ import annotations

import collections
import json
import random
import re
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "talen" / "meting"
ONWAAR = ("onwaar", "misleidend")
MIN_TEKENS, MAX_TEKENS = 25, 600
ZAAD = 3248
AANTAL = {"O": 100, "K": 50, "W": 100, "W-merk": 50, "G": 40}
MAX_PER_UITGEVER = {"O": 70, "K": 20}
PER_MERK, DAGEN = 10, 7
TALEN = {
    "es": {"vers": ("2025", "2026"), "bekend": ("2019", "2020", "2021", "2022", "2023"),
           "feeds": {"El País": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada",
                     "RTVE": "https://api2.rtve.es/rss/temas_noticias.xml",
                     "El Mundo": "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml",
                     "La Vanguardia": "https://www.lavanguardia.com/rss/home.xml",
                     "20minutos": "https://www.20minutos.es/rss/"}},
    "pt": {"vers": ("2024", "2025", "2026"), "bekend": ("2019", "2020", "2021", "2022", "2023"),
           "feeds": {"Público": "https://feeds.feedburner.com/PublicoRSS",
                     "RTP": "https://www.rtp.pt/noticias/rss",
                     "Observador": "https://observador.pt/feed/",
                     "Folha": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml",
                     "g1": "https://g1.globo.com/rss/g1/"}},
    "de": {"vers": ("2023", "2024", "2025", "2026"), "bekend": ("2019", "2020", "2021", "2022"),
           "feeds": {"Tagesschau": "https://www.tagesschau.de/xml/rss2/",
                     "Der Spiegel": "https://www.spiegel.de/schlagzeilen/index.rss",
                     "Die Zeit": "https://newsfeed.zeit.de/index",
                     "DW": "https://rss.dw.com/xml/rss-de-all",
                     "FAZ": "https://www.faz.net/rss/aktuell/"}},
    # B63 (#32.59): Nederland en Vlaanderen, Frankrijk en Wallonië; elk medium met band goed, de feeds op 2026-11-08 gelezen
    "nl": {"vers": ("2023", "2024", "2025", "2026"), "bekend": ("2019", "2020", "2021", "2022"),
           "feeds": {"NOS": "https://feeds.nos.nl/nosnieuwsalgemeen",
                     "NRC": "https://www.nrc.nl/rss/",
                     "de Volkskrant": "https://www.volkskrant.nl/voorpagina/rss.xml",
                     "VRT NWS": "https://www.vrt.be/vrtnws/nl.rss.articles.xml",
                     "HLN": "https://www.hln.be/home/rss.xml"}},
    "fr": {"vers": ("2024", "2025", "2026"), "bekend": ("2019", "2020", "2021", "2022", "2023"),
           "feeds": {"Le Monde": "https://www.lemonde.fr/rss/une.xml",
                     "franceinfo": "https://www.francetvinfo.fr/titres.rss",
                     "France 24": "https://www.france24.com/fr/rss",
                     "Le Soir": "https://www.lesoir.be/rss2/2/cible_principale",
                     "La Libre": "https://www.lalibre.be/arc/outboundfeeds/rss/?outputType=xml"}},
}


# Het oordeel dat een factchecker achter de bewering zette ("...: #Falso", Fast Check CL), nooit mee naar de controle
_OORDEEL_ACHTERAAN = re.compile(r"[\s:,.-]*#(?:falso|falsa|engañoso|engañosa|impreciso|imprecisa|añejo|real|irreal|"
                                r"verdadero|verdadera|cuidado|exagerado|inchequeable|discutible|falsch|irreführend)\s*$",
                                re.IGNORECASE)


def _kort(tekst: str) -> str:
    return _OORDEEL_ACHTERAAN.sub("", " ".join(tekst.split()))[:MAX_TEKENS]


# De eigen datum van een artikel op pt.wikinews.org: een alinea met alleen de datum ("9 de maio de 2016")
_DATUMALINEA_PT = re.compile(r"<p>\s*<span[^>]*>\s*(\d{1,2}º? de (?:janeiro|fevereiro|março|abril|maio|junho|julho|"
                             r"agosto|setembro|outubro|novembro|dezembro) de \d{4})\s*</span>\s*</p>", re.IGNORECASE)
# Bij oudere artikelen (tot ~2012) staat die alinea er niet; dan is de datum de categorie van de publicatiedag, onderaan
# de pagina ("Categoria:8 de janeiro de 2009", #32.44)
_DATUMCATEGORIE_PT = re.compile(r'title="Categoria:(\d{1,2}º? de (?:janeiro|fevereiro|março|abril|maio|junho|julho|'
                                r'agosto|setembro|outubro|novembro|dezembro) de \d{4})"', re.IGNORECASE)
# De vaste oproep van de site onder elk artikel, geen deel van het artikel
_OPROEP_PT = re.compile(r"\s*Tem uma opinião sobre a notícia\?\s*Diga-nos!?")


def artigo_wikinews(pagina: str) -> str:
    """De datum en de alineatekst van een artikel op pt.wikinews.org, zonder de balk met de laatste koppen van het land
    of het onderwerp: die staat in de dump tussen de kop en het artikel, soms langer dan de 2.000 bewaarde tekens (§223,
    §224). De datum is de alinea met alleen de datum, en anders de categorie van de publicatiedag (#32.44). Zonder
    alineatekst leeg; nooit HTML."""
    from doublecheck.screeningmeting import alineatekst

    tekst = _OPROEP_PT.sub("", alineatekst(pagina))
    if not tekst.strip():
        return ""
    datum = _DATUMALINEA_PT.search(pagina) or _DATUMCATEGORIE_PT.search(pagina)
    return f"{datum.group(1)} {tekst}" if datum else tekst


def zonder_jaartal(rijen: list[dict]) -> list[dict]:
    """De artikelen van W zonder jaartal in hun tekst (`zoekcontrole.JAARTAL`): daar kan de regel van het oude jaartal
    niet werken (#32.44)."""
    from doublecheck.zoekcontrole import JAARTAL

    return [r for r in rijen if r["set"] == "W" and not JAARTAL.search(r["tekst"])]


def herstelde_w(oud: list[dict], kop: dict[str, str], artikel: dict[str, str]) -> list[dict]:
    """Dezelfde steekproef W, nu met de kop en het begin van het artikel van de pagina zelf. Een artikel zonder
    alineatekst valt eruit en wordt gemeld; nooit stil een andere tekst."""
    return [{"id": r["id"], "set": "W", "tekst": _kort(f"{kop[r['id']]}\n{artikel[r['id']]}"), "datum": r.get("datum")}
            for r in oud if artikel.get(r["id"])]


def met_omzetting(rijen: list[dict], omzetting: dict[str, str]) -> list[dict]:
    """Een check zonder categorie krijgt het oordeel dat Haiku uit de oordeelzin haalde (het Duits, §161)."""
    return [{**r, "oordeel": omzetting.get(str(r["factcheck_id"]), r["oordeel"])} if r["oordeel"] == "onbekend" else r
            for r in rijen]


def kies_checks(rijen: list[dict], jaren: tuple[str, ...], n: int, set_naam: str, max_per: int | None = None,
                eigen: bool = False, uitgesloten: set[str] = frozenset(), zaad: int = ZAAD) -> list[dict]:
    """Beweringen van checks met *onwaar* of *misleidend* uit `jaren`, één per bewering, hoogstens `max_per` per
    uitgever, niet uit `uitgesloten`. Met `eigen` de adressen van alle checks van die bewering erbij. Vast zaad; de
    volgorde van de invoer telt niet."""
    per_claim = collections.defaultdict(list)
    for r in rijen:
        per_claim[r["claim_id"]].append(r)
    kandidaten = sorted(
        (rs for c, rs in per_claim.items() if c not in uitgesloten
         and any(r["oordeel"] in ONWAAR and r["datum"][:4] in jaren for r in rs)
         and len(" ".join(rs[0]["tekst"].split())) >= MIN_TEKENS),
        key=lambda rs: rs[0]["claim_id"])
    random.Random(zaad).shuffle(kandidaten)
    uit, per_uitgever = [], collections.Counter()
    for rs in kandidaten:
        if len(uit) >= n:
            break
        r = next(x for x in sorted(rs, key=lambda x: x["datum"], reverse=True) if x["oordeel"] in ONWAAR)
        if max_per and per_uitgever[r["publisher"]] >= max_per:
            continue
        per_uitgever[r["publisher"]] += 1
        item = {"id": f"{set_naam}:{r['claim_id']}", "set": set_naam, "claim_id": r["claim_id"], "tekst": _kort(r["tekst"]),
                "datum": r["datum"][:10], "publisher": r["publisher"], "oordeel": r["oordeel"]}
        if eigen:
            item["eigen_urls"] = sorted({x["url"] for x in rs})
        uit.append(item)
    return uit


_JAARTAL = re.compile(r"(?<!\d)(?:1[89]\d\d|20\d\d)(?!\d)")
_SUBPAGINA = re.compile(r"[^\W\d_]/[^\W\d_]")  # "Main Page/Sandbox4", niet "2004/2005"


def wikinews_artikel(r: dict) -> bool:
    """Of een pagina van Wikinews een artikel is: geen subpagina (een / tussen letters in de titel) en een datumregel met een jaartal
    meteen na de kop; een categorie, een testpagina of een overzicht zonder datum valt eruit (§243)."""
    if _SUBPAGINA.search(r.get("titel") or ""):
        return False
    rest = (r.get("tekst") or "").split("\n", 1)
    return len(rest) == 2 and bool(_JAARTAL.search(rest[1][:80]))


def kies_wikinews(rijen: list[dict], n: int, zaad: int = ZAAD) -> list[dict]:
    """De kop en het begin van een artikel van Wikinews, een vaste steekproef."""
    alle = sorted((r for r in rijen if r.get("tekst")), key=lambda r: r["sleutel"])
    return [{"id": f"W:{r['sleutel']}", "set": "W", "tekst": _kort(r["tekst"]), "datum": r.get("datum")}
            for r in sorted(random.Random(zaad).sample(alle, min(n, len(alle))), key=lambda r: r["sleutel"])]


def kies_gewoon(rijen: list[dict], taal: str, n: int, zaad: int = ZAAD) -> list[dict]:
    """Gewone webtekst uit mC4 in die taal (de stiltetoets), een vaste steekproef."""
    alle = sorted((r for r in rijen if r["taal"] == taal and r["varianten"]), key=lambda r: r["claim_id"])
    return [{"id": f"G:{r['claim_id']}", "set": "G", "tekst": _kort(r["varianten"][0]["tekst"]), "datum": None}
            for r in sorted(random.Random(zaad).sample(alle, min(n, len(alle))), key=lambda r: r["claim_id"])]


# --- verse sets voor lezer-v10 (#32.43) --------------------------------------------------------------------------

ZAAD_VERS = 3249
AANTAL_VERS = {"O": 100, "W": 100, "W-merk": 50}
RESERVE_PT = 10  # een pagina van pt.wikinews.org zonder alineatekst valt eruit (§224); de volgende in de steekproef komt erbij
VERS = {"en": ("2026",), **{taal: t["vers"] for taal, t in TALEN.items()}}
# De sets waarop de regels van §223 en §224 gebouwd zijn; bij het Engels ook de 200 artikelen van W2 (#32.32)
GEBRUIKT = {"en": ("data/meting/32.41/set.jsonl", "data/uitkomsten/lezer-v7/set.jsonl"),
            "es": ("data/meting/32.42-es/set.jsonl",),
            "pt": ("data/meting/32.42-pt/set.jsonl", "data/meting/32.42-pt-w/set.jsonl"),
            "de": ("data/meting/32.42-de/set.jsonl",), "nl": (), "fr": ()}


def gebruikte_paden(taal: str, ronde: int = 1) -> list[str]:
    """Wat een verse set van deze ronde niet mag bevatten: bij ronde 2 (#32.56, de meting van B61, die op de verse set van
    ronde 1 bedacht is) ook die set, en de berichten van het duel."""
    paden = list(GEBRUIKT[taal])
    if ronde >= 2:
        paden += [f"data/talen/vers/{taal}.jsonl", "data/duel/duel-2026-11-07-berichten.jsonl"]
        paden += [f"data/talen/vers{r}/{taal}.jsonl" for r in range(2, ronde)]
    return paden


def zaad_vers(ronde: int = 1) -> int:
    return ZAAD_VERS if ronde == 1 else ZAAD_VERS + 7 * (ronde - 1)


def vers_pad(taal: str, ronde: int = 1) -> Path:
    return UIT.parent / ("vers" if ronde == 1 else f"vers{ronde}") / f"{taal}.jsonl"


def gebruikt(rijen: list[dict]) -> dict[str, set[str]]:
    """Wat eerdere metingen al gebruikten: de beweringen (`gfc-` in de id), de artikelen van Wikinews (de sleutel), de
    ids (de koppen van W-merk) en de teksten, zonder hoofdletters en dubbele spaties."""
    uit: dict[str, set[str]] = {"claims": set(), "sleutels": set(), "ids": set(), "teksten": set()}
    for r in rijen:
        staart = r["id"].split(":", 1)[-1]
        if staart.startswith("gfc-"):
            uit["claims"].add(staart)
        for sleutel in (staart, r.get("bron") or ""):
            if sleutel.startswith("wikinews:"):
                uit["sleutels"].add(sleutel)
        uit["ids"].add(r["id"])
        uit["teksten"].add(" ".join(r["tekst"].split()).lower())
    return uit


def verse_set(checks: list[dict], wikinews: list[dict], w_merk: list[dict], jaren: tuple[str, ...],
              weg: dict[str, set[str]], aantal: dict[str, int] = AANTAL_VERS, zaad: int = ZAAD_VERS) -> list[dict]:
    """O, W en W-merk met een nieuw zaad, zonder iets uit `weg`: O zoals in `bouwen` uit `jaren`; W van Wikinews zonder
    een tekst die de balk met recente koppen is (`narekening.met_kopjesbalk`, §223); W-merk in de volgorde van de
    feeds."""
    from doublecheck.narekening import met_kopjesbalk

    o = kies_checks([r for r in checks if _kort(r["tekst"]).lower() not in weg["teksten"]], jaren, aantal["O"], "O",
                    max_per=MAX_PER_UITGEVER["O"], uitgesloten=weg["claims"], zaad=zaad)
    w = kies_wikinews([r for r in wikinews if r["sleutel"] not in weg["sleutels"] and wikinews_artikel(r)
                       and not met_kopjesbalk({"datum": r.get("datum"), "tekst": r.get("tekst") or ""})],
                      aantal["W"], zaad)
    return o + w + [r for r in w_merk if r["id"] not in weg["ids"]][:aantal["W-merk"]]


# --- bekende nepbeelden per taal uit M4FC (#32.46, stap 3) ---------------------------------------------------------

M4FC_TAAL = {"es": "Spanish", "pt": "Portuguese", "de": "German", "nl": "Dutch", "fr": "French",  # nl, fr: #32.54
             "en": "English"}  # en: de verse sets van versie 2 (#32.54)
AANTAL_BEELD = 60


def _bewering(r: dict) -> str:
    """De bewering zoals ze rondging: `multilingual_claim`; bij een Engelse bewering zet M4FC daar "not enough
    information" en staat ze in `claim`."""
    mc = (r.get("multilingual_claim") or "").strip()
    if mc and mc != "not enough information":
        return " ".join(mc.split())
    return " ".join((r.get("claim") or "").split()) if r.get("claim_language") == "English" else ""


def kies_m4fc(rijen: list[dict], taal: str, n: int = AANTAL_BEELD, zaad: int = ZAAD_VERS,
              uitsluiten: set[str] = frozenset()) -> list[dict]:
    """Bekende nepbeelden in één taal: het beeld uit het factcheckartikel (`image_url`, met de kopie in de Wayback
    Machine als reserve), de bewering zoals ze rondging in die taal (`multilingual_claim`), en het artikel als de eigen
    check. Een vaste steekproef; de volgorde van de invoer telt niet. Het beeld wordt pas bij het meten opgehaald, en
    alleen in het geheugen."""
    import hashlib

    alle = sorted((r for r in rijen if r.get("claim_language") == M4FC_TAAL[taal] and r.get("verdict_coarse") == "false"
                   and r.get("image_url") and r["image_url"] not in uitsluiten and _bewering(r)),
                  key=lambda r: r["image_url"])
    gekozen = sorted(random.Random(zaad).sample(alle, min(n, len(alle))), key=lambda r: r["image_url"])
    return [{"id": "N:" + hashlib.sha1(r["image_url"].encode()).hexdigest()[:12], "set": "N",
             "tekst": _bewering(r), "datum": r.get("fc_pub_date"), "beeld": r["image_url"],
             "beeld_reserve": r.get("wayback_image_url"), "eigen_urls": [r["article_url"]], "redactie": r.get("fc_org")}
            for r in gekozen]


def kies_m4fc_waar(rijen: list[dict], taal: str, al_in_w: set[str], n: int = AANTAL_BEELD,
                   zaad: int = ZAAD_VERS) -> list[dict]:
    """Echte foto's met een ware bewering in één taal (#32.54), als de Engelse W: het beeld uit het factcheckartikel,
    de bewering in die taal, en het artikel als de eigen check. Wat al in W staat (`al_in_w`, de beeldadressen) valt
    eruit, en een rij waarvan de factcheck in een andere taal is (M4FC noemt één Frans bijschrift van Congo Check
    Portugees). Een vaste steekproef; het beeld pas bij het meten, alleen in het geheugen."""
    import hashlib

    alle = sorted((r for r in rijen if r.get("claim_language") == M4FC_TAAL[taal] and r.get("verdict_coarse") == "true"
                   and (r.get("fc_language") or M4FC_TAAL[taal]).lower() == M4FC_TAAL[taal].lower()
                   and r.get("image_url") and r["image_url"] not in al_in_w and _bewering(r)),
                  key=lambda r: r["image_url"])
    gekozen = sorted(random.Random(zaad).sample(alle, min(n, len(alle))), key=lambda r: r["image_url"])
    return [{"id": "W:" + hashlib.sha1(r["image_url"].encode()).hexdigest()[:12], "set": "W",
             "tekst": _bewering(r), "datum": r.get("fc_pub_date"), "beeld": r["image_url"],
             "beeld_reserve": r.get("wayback_image_url"), "eigen_urls": [r["article_url"]], "redactie": r.get("fc_org")}
            for r in gekozen]


# --- de bestanden en het netwerk -------------------------------------------------------------------------------

def _checks(taal: str) -> list[dict]:  # pragma: no cover - op de database
    import sqlite3

    conn = sqlite3.connect(f"file:{WORTEL / 'doublecheck.db'}?mode=ro", uri=True)
    rijen = [{"factcheck_id": f, "claim_id": c, "tekst": t, "datum": d, "url": u, "publisher": p, "oordeel": o}
             for f, c, t, d, u, p, o in conn.execute(
                 "SELECT f.factcheck_id, f.claim_id, c.canonical_text, f.review_date, f.url, f.publisher, "
                 "f.verdict_normalized FROM factcheck f JOIN claim c USING (claim_id) WHERE f.language = ?", (taal,))]
    if taal in ("de", "nl", "fr"):  # de oordelen in zinsvorm, omgezet door Haiku (§161; B63, #32.59)
        from doublecheck.talen import omzetting_pad

        omzetting = {}
        for regel in (WORTEL / omzetting_pad(taal)).read_text(encoding="utf-8").split("\n"):
            if regel.strip():
                r = json.loads(regel)
                omzetting[str(r["id"])] = r["oordeel"]
        rijen = met_omzetting(rijen, omzetting)
    return rijen


def _bouwen(taal: str) -> None:  # pragma: no cover - op de bestanden en het netwerk
    import datetime

    from doublecheck.sheffield import regels
    from doublecheck.speuren import _feeds, w_merk_uit

    pad = UIT / f"{taal}.jsonl"
    if pad.exists():
        raise SystemExit(f"{pad.name} ligt al vast")
    t = TALEN[taal]
    checks = _checks(taal)
    o = kies_checks(checks, t["vers"], AANTAL["O"], "O", max_per=MAX_PER_UITGEVER["O"])
    k = kies_checks(checks, t["bekend"], AANTAL["K"], "K", max_per=MAX_PER_UITGEVER["K"], eigen=True,
                    uitgesloten={r["claim_id"] for r in o})
    w = kies_wikinews([r for r in regels(WORTEL / "data" / "echtnieuws" / f"wikinews-{taal}.jsonl")
                       if wikinews_artikel(r)], AANTAL["W"])
    sinds = (datetime.date.today() - datetime.timedelta(days=DAGEN)).isoformat()
    wm = w_merk_uit(_feeds(sinds, t["feeds"]), per_merk=PER_MERK, sinds=sinds)[:AANTAL["W-merk"]]
    g = kies_gewoon(regels(WORTEL / "data" / "stiltetoets" / "regels.jsonl"), taal, AANTAL["G"])
    UIT.mkdir(parents=True, exist_ok=True)
    alle = o + k + w + wm + g
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in alle), encoding="utf-8")
    print(taal, collections.Counter(r["set"] for r in alle),
          "| O per uitgever:", collections.Counter(r["publisher"] for r in o).most_common(4),
          "| O per jaar:", collections.Counter(r["datum"][:4] for r in o).most_common())


AGENT = "FactizResearch/1.0 (https://factiz.org; alleen tekst, PLAN #32.42)"  # het beleid van Wikimedia
PAUZE = 2.0


def _paginas(taal: str, oud: list[dict], ruw: dict[str, dict]) -> tuple[dict, collections.Counter]:  # pragma: no cover
    """Per artikel één keer de pagina van Wikinews, één verzoek per `PAUZE` seconden, met robots.txt; alleen de datum
    en de alineatekst, nooit HTML (§224)."""
    import time
    import urllib.robotparser

    import httpx

    artikel, fouten = {}, collections.Counter()
    with httpx.Client(headers={"User-Agent": AGENT}, timeout=30, follow_redirects=True) as web:
        robots = urllib.robotparser.RobotFileParser()
        robots.parse(web.get(f"https://{taal}.wikinews.org/robots.txt").text.splitlines())
        for r in oud:
            url = ruw[r["id"]]["url"]
            if not robots.can_fetch(AGENT, url):
                fouten["robots.txt verbiedt"] += 1
                continue
            time.sleep(PAUZE)
            antwoord = web.get(url)
            if antwoord.status_code != 200:
                fouten[f"status {antwoord.status_code}"] += 1
                continue
            artikel[r["id"]] = artigo_wikinews(antwoord.text)
            if not artikel[r["id"]]:
                fouten["geen alineatekst"] += 1
    return artikel, fouten


def _herstellen(taal: str) -> None:  # pragma: no cover - op de bestanden en het netwerk
    """W opnieuw, met dezelfde steekproef, met de tekst van de pagina zelf (§224)."""
    from doublecheck.sheffield import regels

    pad = UIT / f"{taal}-w.jsonl"
    if pad.exists():
        raise SystemExit(f"{pad.name} ligt al vast")
    oud = [r for r in regels(UIT / f"{taal}.jsonl") if r["set"] == "W"]
    ids = {r["id"].removeprefix("W:") for r in oud}
    ruw = {f"W:{r['sleutel']}": r for r in regels(WORTEL / "data" / "echtnieuws" / f"wikinews-{taal}.jsonl")
           if r["sleutel"] in ids}
    artikel, fouten = _paginas(taal, oud, ruw)
    nieuw = herstelde_w(oud, {i: r["titel"] for i, r in ruw.items()}, artikel)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in nieuw), encoding="utf-8")
    print(f"{len(nieuw)} van {len(oud)} hersteld in {pad.name}; niet: {dict(fouten)}; anders dan voorheen: "
          f"{sum(n['tekst'] != o['tekst'] for n, o in zip(nieuw, oud))}")


def _datum(taal: str) -> None:  # pragma: no cover - op de bestanden en het netwerk
    """De artikelen van W uit de verse set zonder jaartal opnieuw, met de datum van de pagina (#32.44): dezelfde ids, in
    `data/talen/vers/<taal>-w-datum.jsonl`; weigert als dat bestand al vastligt."""
    from doublecheck.sheffield import regels

    pad = UIT.parent / "vers" / f"{taal}-w-datum.jsonl"
    if pad.exists():
        raise SystemExit(f"{pad.name} ligt al vast")
    oud = zonder_jaartal(regels(UIT.parent / "vers" / f"{taal}.jsonl"))
    ids = {r["id"] for r in oud}
    ruw = {f"W:{r['sleutel']}": r for r in regels(WORTEL / "data" / "echtnieuws" / f"wikinews-{taal}.jsonl")
           if f"W:{r['sleutel']}" in ids}
    artikel, fouten = _paginas(taal, oud, ruw)
    nieuw = herstelde_w(oud, {i: r["titel"] for i, r in ruw.items()}, artikel)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in nieuw), encoding="utf-8")
    print(f"{len(nieuw)} van {len(oud)} opnieuw in {pad.name}; niet: {dict(fouten)}; nog zonder jaartal: "
          f"{len(zonder_jaartal(nieuw))}")


def _waar(taal: str) -> None:  # pragma: no cover - op de bestanden
    """Echte foto's met een ware bewering in één taal voor `docs/meetplannen/32.54.json` (#32.54), zonder wat al in de
    Engelse W staat; weigert als de set al vastligt. Alleen adressen, nooit een beeld."""
    pad = UIT.parent / "beeld" / f"{taal}-w.jsonl"
    if pad.exists():
        raise SystemExit(f"{pad.name} ligt al vast")
    m4fc = json.loads((WORTEL / "data" / "extern" / "m4fc" / "M4FC.json").read_text(encoding="utf-8"))
    w = [json.loads(r) for r in (WORTEL / "data" / "screenshotlezer" / "lezer-v7-beeld" / "set.jsonl").read_text(
        encoding="utf-8").splitlines() if r.strip()]
    al = {m4fc[int(r["id"][2:])]["image_url"] for r in w if r["set"] == "W"}
    uit = kies_m4fc_waar(m4fc, taal, al)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    print(taal, len(uit), collections.Counter(r["redactie"] for r in uit).most_common(3))


def _vers_beeld(taal: str) -> None:  # pragma: no cover - op de bestanden
    """De verse sets van versie 2 (#32.54): N2, bekende nepbeelden, en W2, echte foto's met een ware bewering, zonder de
    beelden van N, W en de sets van §234 en §248; weigert als ze al vastliggen. Alleen adressen."""
    uit_n, uit_w = UIT.parent / "beeld" / f"{taal}-n2.jsonl", UIT.parent / "beeld" / f"{taal}-w2.jsonl"
    if uit_n.exists() or uit_w.exists():
        raise SystemExit("de verse sets liggen al vast")
    m4fc = json.loads((WORTEL / "data" / "extern" / "m4fc" / "M4FC.json").read_text(encoding="utf-8"))
    nw = [json.loads(r) for r in (WORTEL / "data" / "screenshotlezer" / "lezer-v7-beeld" / "set.jsonl").read_text(
        encoding="utf-8").splitlines() if r.strip()]
    gebruikt = {m4fc[int(Path(r["beeld"]).stem)]["image_url"] for r in nw}
    for pad in (UIT.parent / "beeld").glob("*.jsonl"):
        gebruikt |= {json.loads(r)["beeld"] for r in pad.read_text(encoding="utf-8").splitlines() if r.strip()}
    n2 = [{**r, "id": "N2:" + r["id"][2:]} for r in kies_m4fc(m4fc, taal, zaad=ZAAD_VERS + 2, uitsluiten=gebruikt)]
    w2 = [{**r, "id": "W2:" + r["id"][2:]} for r in kies_m4fc_waar(m4fc, taal, gebruikt, zaad=ZAAD_VERS + 2)]
    for pad, rijen in ((uit_n, n2), (uit_w, w2)):
        pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rijen), encoding="utf-8")
        print(pad.name, len(rijen), collections.Counter(r["redactie"] for r in rijen).most_common(3))


def _beeld(taal: str) -> None:  # pragma: no cover - op de bestanden
    """De set bekende nepbeelden van één taal voor `docs/meetplannen/32.46-beeld-<taal>.json`; weigert als hij al
    vastligt. Alleen adressen, nooit een beeld."""
    pad = UIT.parent / "beeld" / f"{taal}.jsonl"
    if pad.exists():
        raise SystemExit(f"{pad.name} ligt al vast")
    uit = kies_m4fc(json.loads((WORTEL / "data" / "extern" / "m4fc" / "M4FC.json").read_text(encoding="utf-8")), taal)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in uit), encoding="utf-8")
    print(taal, len(uit), collections.Counter(r["redactie"] for r in uit).most_common(3))


def _vers(taal: str, ronde: int = 1) -> None:  # pragma: no cover - op de bestanden, de database en het netwerk
    """De verse set van één taal voor `docs/meetplannen/32.43-<taal>.json` (ronde 2: #32.56); weigert als hij al
    vastligt."""
    import datetime

    from doublecheck.sheffield import regels
    from doublecheck.speuren import FEEDS, _feeds, w_merk_uit

    pad = vers_pad(taal, ronde)
    if pad.exists():
        raise SystemExit(f"{pad} ligt al vast")
    weg = gebruikt([r for p in gebruikte_paden(taal, ronde) for r in regels(WORTEL / p)])
    wikinews = regels(WORTEL / "data" / "echtnieuws" / f"wikinews-{taal}.jsonl")
    sinds = (datetime.date.today() - datetime.timedelta(days=DAGEN)).isoformat()
    feeds = FEEDS if taal == "en" else TALEN[taal]["feeds"]
    wm = w_merk_uit(_feeds(sinds, feeds), per_merk=PER_MERK, sinds=sinds)
    aantal = {**AANTAL_VERS, "W": AANTAL_VERS["W"] + (RESERVE_PT if taal == "pt" else 0)}
    alle = verse_set(_checks(taal), wikinews, wm, VERS[taal], weg, aantal, zaad=zaad_vers(ronde))
    if taal == "pt":  # de dump heeft de balk met koppen tussen kop en artikel: de pagina zelf (§224)
        w = [r for r in alle if r["set"] == "W"]
        ids = {r["id"] for r in w}
        ruw = {f"W:{r['sleutel']}": r for r in wikinews if f"W:{r['sleutel']}" in ids}
        artikel, fouten = _paginas(taal, w, ruw)
        hersteld = herstelde_w(w, {i: r["titel"] for i, r in ruw.items()}, artikel)[:AANTAL_VERS["W"]]
        alle = [r for r in alle if r["set"] != "W"] + hersteld
        print(f"W van de pagina zelf: {len(hersteld)}; niet: {dict(fouten)}")
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in alle), encoding="utf-8")
    print(taal, collections.Counter(r["set"] for r in alle),
          "| O per uitgever:", collections.Counter(r["publisher"] for r in alle if r["set"] == "O").most_common(4))


def main() -> None:  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="De sets per taal (PLAN #32.42, #32.43, #32.44)")
    parser.add_argument("stap", choices=("bouwen", "herstel", "vers", "datum", "beeld", "waar", "vers-beeld"))
    parser.add_argument("--taal", choices=tuple(VERS), required=True)
    parser.add_argument("--ronde", type=int, default=1, help="vers: 2 voor een tweede verse set (#32.56)")
    args = parser.parse_args()
    if args.stap == "vers":
        _vers(args.taal, args.ronde)
        return
    if args.stap not in ("vers", "datum", "beeld", "waar", "vers-beeld") and args.taal not in TALEN:
        raise SystemExit(f"{args.stap} kent alleen {', '.join(TALEN)}")
    {"bouwen": _bouwen, "herstel": _herstellen, "vers": _vers, "datum": _datum, "beeld": _beeld, "waar": _waar,
     "vers-beeld": _vers_beeld}[args.stap](args.taal)


if __name__ == "__main__":
    main()
