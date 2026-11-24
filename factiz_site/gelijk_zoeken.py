"""Zoeken en suggesties in TypeScript naast Python (B80, PLAN #34.2bo stap 4): dezelfde berichten naar `/api/<taal>/zoek`
en `/api/<taal>/suggesties` van beide kanten, en elk verschil in woorden.

    python -m factiz_site.gelijk_zoeken [<publicatie.db>]

De verzoeken komen uit de proeven van het zoeken (de randgevallen van #34.2y en #34.2ac, de zoekproef van #33.3 en de
berichtproef van #34.2au), elk begin van een paar woorden voor de suggesties, filters, volgordes, bladen, `letterlijk`,
lege vragen, stuurtekens, links, een te groot bericht, te veel velden en een GET, in zeven talen van de site.

Twee dingen wachten bij Python op een vaste stand. De index van afkortingen in hoofdletters bouwt Python in een eigen draad
(`afkortingen_klaar`): de vergelijking wacht erop, TypeScript rekent hem bij de eerste vraag. En de woorden die een
suggestie afmaken komen in Python uit een frozenset: bij een gelijk gewicht hangt hun volgorde af van de hash van het
proces. `vaste_volgorde` laat die frozensets lopen in de volgorde waarin hun woorden gevonden werden, zoals TypeScript.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path
from urllib.parse import urlencode

from factiz_site import berichtproef, db, gelijk, randproef, zoekproef

TALEN = ("en", "nl", "de", "ru", "hi", "ar", "zh")
WACHT = 180          # seconden die de vergelijking hoogstens op de index van afkortingen van Python wacht


class _Geordend(frozenset):
    """Dezelfde frozenset, maar doorlopen in de volgorde waarin de woorden gevonden werden."""

    def __new__(cls, rij):
        volg = tuple(dict.fromkeys(rij))
        uit = super().__new__(cls, volg)
        uit._volg = volg
        return uit

    def __iter__(self):
        return iter(self._volg)


def vaste_volgorde(pub: db.Publicatie) -> None:
    """De woorden van elke suggestie in een vaste volgorde (de talen van de site na elkaar), zodat woorden met een gelijk
    gewicht in Python niet per proces anders staan. Verandert wat de woorden zijn niet."""
    nieuw = []
    for woorden, wat in pub._suggestie:
        namen = wat["naam"].values() if isinstance(wat["naam"], dict) else [wat["naam"]]
        geordend = _Geordend([s for naam in namen for w in db.zoektermen(naam) if (s := db._alfabet(w).strip(db.LEESTEKENS))])
        if geordend != woorden or len(list(geordend)) != len(woorden):
            raise AssertionError(f"andere woorden voor {wat!r}")
        nieuw.append((geordend, wat))
    pub._suggestie = nieuw


def klaar(client) -> db.Publicatie:
    """De Publicatie achter een TestClient, met de index van afkortingen klaar en de suggesties in vaste volgorde."""
    pub = client.app.state.publicatie
    if not pub.afkortingen_klaar(WACHT):
        raise RuntimeError("de index van afkortingen in hoofdletters is niet klaar")
    if not isinstance(next(iter(pub._suggestie), (_Geordend(()),))[0], _Geordend):
        vaste_volgorde(pub)
    return pub


def _post(taal: str, ingang: str, bericht: str | list | dict) -> dict:
    tekst = bericht if isinstance(bericht, str) else urlencode(bericht)
    return {"pad": f"/api/{taal}/{ingang}", "methode": "POST", "bericht": tekst}


def zoek(taal: str, vraag: str, /, **velden) -> dict:
    """Een zoekvraag in de taal van de site, met velden van het formulier (een lijst is een veld met meer waarden)."""
    return _post(taal, "zoek", [("q", vraag), *((k, w) for k, v in velden.items() for w in (v if isinstance(v, list) else [v]))])


def suggestie(taal: str, vraag: str) -> dict:
    return _post(taal, "suggesties", [("q", vraag)])


def _randvragen(pub: db.Publicatie, zaad: int = randproef.ZAAD) -> list[tuple[str, str]]:
    """De vragen van de randproef (#34.2y, #34.2ac): (taal, vraag)."""
    uit = []
    for _, _, taal, vragen, _ in randproef.GELIJK:
        uit += [(taal, v) for v in vragen]
    for _, taal, vragen in randproef.ZELFDE:
        uit += [(taal, v) for v in vragen]
    for _, taal, vragen, _ in randproef.PRECIES:
        uit += [(taal, v) for v in vragen]
    uit += [(taal, tekens) for _, taal, tekens in randproef.KORT]
    uit += [("en", t) for t in randproef.KORT_LOS]
    for taal, vraag, _, _ in randproef.AFKORTINGEN:
        uit += [(taal, vraag), (taal, vraag.lower())]
    uit += [(taal, vraag) for taal, vraag, _, _ in randproef.VERRUIMD]
    uit += [(taal, vraag) for taal, vraag, _ in randproef.DOORSTUREN]
    if pub.dossiers:
        d = pub.dossiers[0]
        uit += [(t, d["naam"][t]) for t in ("nl", "en", "de")]
    c = pub._conn()
    alle_links = c.execute("SELECT pagina, url FROM check_ ORDER BY pagina, volg").fetchall()
    for i, (_, url) in enumerate(random.Random(zaad).sample(alle_links, min(randproef.LINKS, len(alle_links)))):
        uit.append(("en", url if i % 2 else url.replace("https://", "").replace("http://", "") + "?utm_source=whatsapp"))
    paginas = sorted({p for p, _ in alle_links})
    for pagina in random.Random(zaad + 1).sample(paginas, min(5, len(paginas))):
        uit.append(("nl", f"https://factiz.org/nl/fact-checks/{pagina}/"))
    uit += [(taal, vraag) for taal, vraag, _ in randproef.VASTE]
    lange = c.execute("SELECT nummer, bewering FROM pagina WHERE length(bewering) > ? ORDER BY nummer",
                      (db.MAX_VRAAG + 20,)).fetchall()
    for _, bewering in random.Random(zaad).sample(lange, min(randproef.LANGE_VRAGEN, len(lange))):
        uit.append(("nl", db.schoon(bewering)))
    return uit


def _zoekproef(pub: db.Publicatie) -> list[str]:
    """De vijftig vragen van de zoekproef (#33.3), op dezelfde manier getrokken."""
    per: dict[str, list] = {}
    for nummer, bewering, taal in pub._conn().execute("SELECT nummer, bewering, taal FROM pagina ORDER BY nummer"):
        per.setdefault(zoekproef.groep(taal), []).append((nummer, bewering, taal))
    rng = random.Random(zoekproef.ZAAD)
    uit = []
    for naam in sorted(per):
        for _, bewering, taal in rng.sample(per[naam], min(zoekproef.PER_GROEP, len(per[naam]))):
            uit.append(zoekproef.vraag_uit(db.schoon(bewering), taal))
    return uit


def _berichten(pub: db.Publicatie, aantal: int = berichtproef.AANTAL, zaad: int = berichtproef.ZAAD) -> list[str]:
    """De geplakte berichten van de berichtproef (#34.2au): de beweringen met ruis, en de gewone berichten."""
    rijen = [r for r in pub._conn().execute(
        f"SELECT nummer, bewering, taal FROM pagina WHERE taal IN ({','.join('?' * len(berichtproef.TALEN))}) ORDER BY nummer",
        berichtproef.TALEN) if 12 <= len(r[1].split()) <= 60]
    proef = random.Random(zaad).sample(rijen, min(aantal, len(rijen)))
    r = random.Random(zaad + 1)
    return [berichtproef.bericht_uit(b, t, r) for _, b, t in proef] + list(berichtproef.GEWOON)


def _filtervragen(pub: db.Publicatie) -> list[dict]:
    """Elke filter bij een paar vragen, met de waarden die de zoekpagina aanbiedt, volgordes en bladen."""
    uit = []
    for vraag in randproef.FILTERVRAGEN + ["vaccine", "trump"]:
        facetten = pub.zoek_ruim(vraag)["facetten"]
        for soort in ("taal", "jaar", "oordeel", "land", "thema", "redactie", "soort", "vorm"):
            top = [w for w, _ in sorted(facetten.get(soort, {}).items(), key=lambda x: -x[1])[:3]]
            for w in top[:2]:
                uit.append(zoek("en", vraag, **{soort: w}))
            if soort in db.MEER and len(top) >= 2:
                uit.append(zoek("nl", vraag, **{soort: [top[1], top[0], top[0], "bestaat-niet", ""]}))
        if pub.themas:
            th = pub.themas[0]
            uit.append(zoek("en", vraag, thema=th["sleutel"], onderdeel=[o["sleutel"] for o in th["onderdelen"][:1]] or ["x"]))
            uit.append(zoek("de", vraag, onderdeel=[o["sleutel"] for o in th["onderdelen"][:1]] or ["x"]))
        for sorteer in ("nieuw", "oud", "redacties", "x", ""):
            uit.append(zoek("en", vraag, sorteer=sorteer))
        for blad in ("2", "3", "0", "-1", "abc", "99999", "1234", "１", "1.0"):
            uit.append(zoek("en", vraag, p=blad))
        uit.append(zoek("en", vraag, letterlijk="1"))
        uit.append(zoek("en", vraag, letterlijk="ja"))
        if getattr(pub, "_naam", None):
            uit.append(zoek("en", vraag, naam=next(iter(pub._naam))))
        uit.append(zoek("en", vraag, naam="Q1", redactie="bestaat niet", land="XX", thema="bestaat-niet"))
    return uit


# Woorden waarvan elk begin naar de suggesties gaat (#34.2b, #34.2ac).
TYPEN = randproef.TYPEN + ["zelensky", "who", "Oekraïne", "covid vaccine", "bill gates", "vacc ", "  trump", "\"biolab",
                           "कोरोना", "疫苗", "кор"]

# Vragen met iets bijzonders: leeg, witruimte, stuurtekens, schriften, toetsenborden, spelfouten, links die geen link zijn.
BIJZONDER = ["", " ", "   \t ", "\u3000", "a", "ab", "\x00vaccine\x7f", "vac\u202ecine", "\ufeffvaccine", "va\u200dccine",
             "ｖａｃｃｉｎｅ", "Straße", "STRASSE", "ΧΑΟΣ", "İstanbul", "e\u0301lection", "کرونا", "كرونا", "करोना वायरस",
             "கொரோனா", "โคว\u0e34ด", "疫", "코로나", "🙂 vaccine", "\U000105c0 vaccine", "\ue000", "vaccin\u0301e", "zelenksy",
             "zelenksy vaccine", "vacinne", "\"Bill Gates\"", "\"vaccine", "«Moscou»", "“biolab”", "a\"b\"c\"d", "covid-19",
             "COVID-19", "5G", "G7", "e-mail", "Kılıçdaroğlu", "Oekraine", "Ucrania", "œuvre", "WHO", "who", "WHO's", "OMS",
             "AFP", "EU", "NATO", "OTAN", "India", "india vaccine", "Sri Lanka", "politifact trump", "Gezondheid",
             "Narendra Modi", "narendra modi", "Donald Trump", "trump", "privacy", "rédactions", "api", "Quellen",
             "fact-checkers", "a propos", "https://", "http://x", "x.y", "x.y/", "x.y/z", "www.example.com/a/b",
             "https://[::1]/a.b", "https://[1.2.3.4]/x", "http://[v1.x]/p.q", "https://a[b]/c.d", "https://exa mple.com/x",
             "https://example.com/x?utm_source=a&id=3", "factiz.org/fact-checks/0000000000000000",
             "https://www.factiz.org/de/fact-checks/0123456789abcdef/", "https://Ａ.com/x", "a" * 250, "word " * 30,
             "vaccine " * 13, "1 2 3 4 5 6 7", "! ? . ,", "--", "_", "%", "\\", "vac_cine", "100%", "\"\"", "''"]


def verzoeken(pub: db.Publicatie) -> list[dict]:
    """De verzoeken voor de vergelijking, met waarden uit deze uitgave."""
    uit: list[dict] = []
    rand = _randvragen(pub)
    for taal, vraag in rand:
        uit.append(zoek("en", vraag))
        if taal != "en":
            uit.append(zoek(taal if taal in db.SITETALEN else "nl", vraag))
        uit.append(suggestie(taal if taal in db.SITETALEN else "en", vraag))
    for taal, vraag, _, _ in randproef.VERRUIMD:
        uit.append(zoek(taal, vraag, letterlijk="1"))
    uit += [zoek("en", v) for v in _zoekproef(pub)]
    berichten = _berichten(pub)
    uit += [zoek("en", v) for v in berichten]
    uit += [zoek("nl", v) for v in berichten[::10]]
    uit += [zoek("en", v) for v in berichtproef.GEWOON_TOETS]
    for woord in TYPEN:
        for n in range(1, len(woord) + 1):
            uit.append(suggestie("nl", woord[:n]))
            uit.append(suggestie("en", woord[:n]))
    for vraag, _ in randproef.AANVULLEN:
        uit += [suggestie("en", vraag), zoek("en", vraag)]
    for taal in TALEN:
        for vraag in BIJZONDER:
            uit += [zoek(taal, vraag), suggestie(taal, vraag)]
    uit += _filtervragen(pub)
    # het bericht zelf: geen vraag, een lege vraag, een vraag twee keer, te veel velden, te groot, de verkeerde methode
    for ingang in ("zoek", "suggesties"):
        uit += [_post("en", ingang, ""), _post("en", ingang, "x=1"), _post("en", ingang, "q"), _post("en", ingang, "q=&q=vaccine"),
                _post("en", ingang, "q=vaccine&q=trump"), _post("en", ingang, "q=%ZZvaccine%2"), _post("en", ingang, "q=vac%E2%82cine"),
                _post("en", ingang, "&&q=vaccine&&"), _post("en", ingang, "q=vaccine;taal=en"),
                _post("en", ingang, "&".join(["q=vaccine"] + [f"x{i}=1" for i in range(95)])),
                _post("en", ingang, "&".join(["q=vaccine"] + [f"x{i}=1" for i in range(96)])),
                _post("en", ingang, "q=" + "a" * 8191), _post("en", ingang, "q=" + "a" * 8190),
                _post("en", ingang, "q=" + "vaccine+" * 180),
                {"pad": f"/api/en/{ingang}", "methode": "GET"}, {"pad": f"/api/en/{ingang}/extra", "methode": "POST", "bericht": "q=a"}]
    return uit


def verschillen(client, bestand: str | Path, lijst: list[dict] | None = None) -> tuple[list[str], int]:
    """De verschillen tussen Python en TypeScript op deze verzoeken (of `verzoeken`), en hoeveel er waren."""
    pub = klaar(client)
    lijst = verzoeken(pub) if lijst is None else lijst
    return gelijk.verschillen(client, bestand, lijst), len(lijst)


def main() -> None:  # pragma: no cover - CLI
    from starlette.testclient import TestClient

    from factiz_site import app as fa

    bestand = (Path(sys.argv[1]) if len(sys.argv) > 1 else fa._standaard_pad()).resolve()
    client = TestClient(fa.maak_app(bestand), follow_redirects=False)
    fouten, n = verschillen(client, bestand)
    for f in fouten:
        print(f)
    print(f"{n - len(fouten)} van {n} verzoeken gelijk ({bestand})")
    raise SystemExit(1 if fouten else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
