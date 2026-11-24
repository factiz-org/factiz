"""De minimale paren van Wikipedia (B34, PLAN #30.1b stap 3).

Een edit die op Wikipedia is teruggedraaid, is een nepzin naast de ware zin,
op dezelfde plek in hetzelfde artikel. Maar een losse terugdraaiing is nog geen
uitspraak: een bewerkingsoorlog wordt beslist. Daarom telt een paar alleen als
de teruggezette zin 90 dagen later nog in het artikel staat, en de nepzin niet.

Een paar is *minimaal* als de edit precies één zin verandert en die zin grotendeels
blijft staan (een datum, een naam, wie wat deed). Vandalisme dat de tekst
vervangt, en een edit die meer verandert, tellen niet.

Wat er bewaard wordt: het artikel, het revisienummer, de datum, de ware en de
nepzin. Nooit wie de edit deed: de naam of het adres van een bewerker wordt niet
eens opgevraagd, en de bewerkingssamenvatting ook niet (die noemt vaak namen).
Eén verzoek tegelijk, met een eigen User-Agent, zoals de API vraagt.

    python -m doublecheck.minimaleparen oogsten [--per-artikel 100]
    python -m doublecheck.minimaleparen tellen
"""

from __future__ import annotations

import html as _html
import json
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "FactizFeitenbasis/0.1 (https://factiz.org; https://github.com/factiz-org/factiz)"
TERMIJN_DAGEN = 90
MIN_LENGTE = 20
MIN_GELIJK = 0.6
WORTEL = Path(__file__).resolve().parent.parent
UIT = WORTEL / "data" / "feitenbasis" / "minimaleparen.jsonl"

_REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
_SJABLOON = re.compile(r"\{\{[^{}]*\}\}")
_BESTAND = re.compile(r"\[\[(?:File|Image|Category):[^\]]*\]\]", re.I)
_LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")
_EXTERN = re.compile(r"\[https?://\S+\s*([^\]]*)\]")
_TAG = re.compile(r"<[^>]+>")
_ZIN = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")


def schoon(wikitekst: str) -> str:
    """Wikitekst als leesbare tekst: zonder voetnoten, sjablonen, bestanden en
    opmaak, met de zichtbare tekst van links."""
    tekst = _REF.sub("", wikitekst)
    vorige = None
    while vorige != tekst:
        vorige, tekst = tekst, _SJABLOON.sub("", tekst)
    tekst = _BESTAND.sub("", tekst)
    tekst = _LINK.sub(r"\1", tekst)
    tekst = _EXTERN.sub(r"\1", tekst)
    tekst = _TAG.sub("", tekst).replace("'''", "").replace("''", "")
    tekst = re.sub(r"\s+([.,;:!?])", r"\1", tekst)
    return " ".join(tekst.split())


def zinnen(tekst: str) -> list[str]:
    return [z.strip() for z in _ZIN.split(tekst) if z.strip()]


def paar(oud: str, nieuw: str) -> tuple[str, str] | None:
    """(ware zin, nepzin) als de edit precies één zin verandert en die zin
    grotendeels blijft staan; anders None."""
    oud_z, nieuw_z = zinnen(schoon(oud)), zinnen(schoon(nieuw))
    weg = [z for z in oud_z if z not in set(nieuw_z)]
    erbij = [z for z in nieuw_z if z not in set(oud_z)]
    if len(weg) != 1 or len(erbij) != 1:
        return None
    waar, nep = weg[0], erbij[0]
    if min(len(waar), len(nep)) < MIN_LENGTE:
        return None
    if SequenceMatcher(None, waar.split(), nep.split()).ratio() < MIN_GELIJK:
        return None
    return waar, nep


def beslist(waar: str, nep: str, latere_wikitekst: str) -> bool:
    """Staat de ware zin er na de termijn nog, en de nepzin niet?"""
    tekst = schoon(latere_wikitekst)
    return waar in tekst and nep not in tekst


def _cel(td: str) -> str:
    return " ".join(_html.unescape(_TAG.sub("", td)).split())


_RIJ = re.compile(r"<tr>(.*?)</tr>", re.S)
_WEG = re.compile(r'<td class="diff-deletedline[^"]*">(.*?)</td>', re.S)
_ERBIJ = re.compile(r'<td class="diff-addedline[^"]*">(.*?)</td>', re.S)


def regels_uit_diff(html: str) -> list[tuple[str, str]]:
    """De gewijzigde regels uit een vergelijking van MediaWiki: (oud, nieuw)
    voor elke rij met een weggehaalde én een toegevoegde kant."""
    uit = []
    for rij in _RIJ.findall(html):
        weg, erbij = _WEG.search(rij), _ERBIJ.search(rij)
        if weg and erbij:
            uit.append((_cel(weg.group(1)), _cel(erbij.group(1))))
    return uit


def revisie_params(titel: str, limiet: int) -> dict:
    """De vraag naar teruggedraaide edits: nummers, datum en labels, nooit de
    bewerker of de samenvatting."""
    return {"action": "query", "format": "json", "formatversion": "2", "prop": "revisions", "titles": titel,
            "rvprop": "ids|timestamp|tags", "rvtag": "mw-reverted", "rvlimit": str(limiet), "maxlag": "5"}


def artikelen(kern: list[dict]) -> dict[str, list[str]]:
    """Per feit de Engelse Wikipedia-artikelen uit zijn bronnen, of uit het
    veld `artikelen`."""
    uit = {}
    for feit in kern:
        titels = list(feit.get("artikelen") or [])
        for b in feit.get("bronnen") or []:
            m = re.match(r"https://en\.wikipedia\.org/wiki/(.+)$", b.get("vindplaats") or "")
            if m:
                from urllib.parse import unquote

                titels.append(unquote(m.group(1)).replace("_", " "))
        if titels:
            uit[feit["id"]] = sorted(set(titels))
    return uit


def _vraag(client, params: dict) -> dict:  # pragma: no cover - netwerk
    import time

    antwoord = client.get(API, params=params)
    antwoord.raise_for_status()
    time.sleep(1.0)
    return antwoord.json()


def oogsten(kern: list[dict], per_artikel: int, uitpad: Path = UIT) -> dict:  # pragma: no cover - netwerk
    import httpx

    uitpad.parent.mkdir(parents=True, exist_ok=True)
    gedaan = set()
    if uitpad.exists():
        gedaan = {json.loads(r)["revid"] for r in uitpad.read_text(encoding="utf-8").splitlines() if r.strip()}
    grens = datetime.now(timezone.utc) - timedelta(days=TERMIJN_DAGEN)
    telling = {"edits": 0, "paren": 0, "beslist": 0}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30.0) as client, \
            uitpad.open("a", encoding="utf-8") as uit:
        for feit, titels in artikelen(kern).items():
            for titel in titels:
                data = _vraag(client, revisie_params(titel, per_artikel))
                pagina = (data.get("query", {}).get("pages") or [{}])[0]
                for rev in pagina.get("revisions") or []:
                    if rev["revid"] in gedaan:
                        continue
                    moment = datetime.fromisoformat(rev["timestamp"].replace("Z", "+00:00"))
                    if moment > grens:
                        continue  # nog niet beslist
                    telling["edits"] += 1
                    diff = _vraag(client, {"action": "compare", "format": "json", "formatversion": "2",
                                           "fromrev": rev["parentid"], "torev": rev["revid"], "prop": "diff"})
                    paren = [p for p in (paar(o, n) for o, n in regels_uit_diff(diff.get("compare", {}).get("body", "")))
                             if p]
                    if len(paren) != 1:
                        continue
                    waar, nep = paren[0]
                    telling["paren"] += 1
                    later = _vraag(client, {"action": "query", "format": "json", "formatversion": "2",
                                            "prop": "revisions", "titles": titel, "rvprop": "content",
                                            "rvslots": "main", "rvlimit": "1", "rvdir": "older",
                                            "rvstart": (moment + timedelta(days=TERMIJN_DAGEN)).strftime("%Y-%m-%dT%H:%M:%SZ")})
                    lp = (later.get("query", {}).get("pages") or [{}])[0].get("revisions") or [{}]
                    tekst = lp[0].get("slots", {}).get("main", {}).get("content", "")
                    besl = beslist(waar, nep, tekst)
                    telling["beslist"] += besl
                    uit.write(json.dumps({"feit": feit, "artikel": titel, "revid": rev["revid"],
                                          "parentid": rev["parentid"], "datum": rev["timestamp"][:10],
                                          "waar": waar, "nep": nep, "beslist": besl}, ensure_ascii=False) + "\n")
                    uit.flush()
                print(f"  {feit} · {titel}: {telling}", flush=True)
    return telling


def main() -> None:  # pragma: no cover
    import argparse

    from doublecheck.feitenbasis import lees_kern

    parser = argparse.ArgumentParser(description="De minimale paren van Wikipedia (B34, PLAN #30.1b)")
    parser.add_argument("stap", choices=("oogsten", "tellen"))
    parser.add_argument("--per-artikel", type=int, default=100)
    args = parser.parse_args()
    if args.stap == "oogsten":
        print(oogsten(lees_kern(), args.per_artikel))
        return
    regels = [json.loads(r) for r in UIT.read_text(encoding="utf-8").splitlines() if r.strip()]
    beslist_ = [r for r in regels if r["beslist"]]
    print(f"{len(regels)} minimale paren, {len(beslist_)} beslist (de ware zin staat er na {TERMIJN_DAGEN} dagen nog)")


if __name__ == "__main__":
    main()
