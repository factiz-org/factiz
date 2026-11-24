"""De proef op de randgevallen van het zoeken (PLAN #34.2y): vindt een lezer wat hij verwacht?

    python -m factiz_site.randproef [<publicatie.db>]

Naast de zoekproef van #33.3, die meet of zoeken in elk schrift werkt, meet deze proef wat een lezer in de vijf talen
van de site als hetzelfde ziet: enkelvoud en meervoud, samenstellingen, accenten en bijzondere letters, schrijfwijzen
van namen, streepjes en getallen, hoofdletters en aanhalingstekens, heel korte en heel lange vragen, de aantallen bij
de filters, en of het antwoord binnen een seconde komt.

Bij een geval van het soort "gelijk" is het doel de beweringen waarin een van de doelwoorden letterlijk staat (zoals
het register op woorden het leest: zonder hoofdletters en accenten). Elke vraag moet minstens 90% van dat doel vinden.
Wat een vraag daarbuiten vindt, staat er als "extra" bij: dat kan een andere vorm zijn die er ook bij hoort, of ruis.
De eis van de hele proef is per geval vastgelegd; de uitslag is het aantal gehaalde gevallen.
"""

from __future__ import annotations

import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path

from factiz_site import db

EIS_DEKKING = 0.9          # elke vraag vindt minstens 90% van het doel
EIS_SECONDEN = 1.0         # elke vraag binnen een seconde
ZAAD = 3420
LANGE_VRAGEN = 20          # beweringen langer dan een zoekvraag mag zijn, in hun geheel geplakt
EIS_LANG = 18              # waarvan er minstens zoveel bij de eerste tien staan

# (soort, groep, taal, vragen, doelwoorden). Een doelwoord met een spatie is een reeks woorden achter elkaar.
GELIJK = [
    ("gelijk", "buiging", "en", ("biolab", "biolabs"), ("biolab", "biolabs")),
    ("gelijk", "buiging", "en", ("vaccine", "vaccines"), ("vaccine", "vaccines")),
    ("gelijk", "buiging", "en", ("laboratory", "laboratories"), ("laboratory", "laboratories")),
    ("gelijk", "buiging", "en", ("election", "elections"), ("election", "elections")),
    ("gelijk", "buiging", "nl", ("vaccin", "vaccins"), ("vaccin", "vaccins")),
    ("gelijk", "buiging", "nl", ("verkiezing", "verkiezingen"), ("verkiezing", "verkiezingen")),
    ("gelijk", "buiging", "nl", ("laboratorium", "laboratoria"), ("laboratorium", "laboratoria")),
    ("gelijk", "buiging", "de", ("Impfstoff", "Impfstoffe", "Impfstoffen"), ("impfstoff", "impfstoffe", "impfstoffen")),
    ("gelijk", "buiging", "de", ("Wahl", "Wahlen"), ("wahl", "wahlen")),
    ("gelijk", "buiging", "es", ("vacuna", "vacunas"), ("vacuna", "vacunas")),
    ("gelijk", "buiging", "es", ("vacunación", "vacunaciones"), ("vacunacion", "vacunaciones")),
    ("gelijk", "buiging", "es", ("elección", "elecciones"), ("eleccion", "elecciones")),
    ("gelijk", "buiging", "fr", ("élection", "élections"), ("election", "elections")),
    ("gelijk", "buiging", "fr", ("réseau", "réseaux"), ("reseau", "reseaux")),
    ("gelijk", "buiging", "fr", ("hôpital", "hôpitaux"), ("hopital", "hopitaux")),
    ("gelijk", "samenstelling", "de", ("Biolabor", "Biolabore", "Biolaboren"), ("biolabor", "biolabore", "biolaboren")),
    ("gelijk", "samenstelling", "nl", ("biolaboratorium", "biolaboratoria"), ("biolaboratorium", "biolaboratoria")),
    ("gelijk", "samenstelling", "de", ("Coronavirus", "Corona-Virus"), ("coronavirus", "corona virus")),
    ("gelijk", "samenstelling", "nl", ("covidvaccin", "covid-vaccin"), ("covidvaccin", "covid vaccin")),
    ("gelijk", "samenstelling", "en", ("biolab", "biolabs", "Biolabor"),
     ("biolab", "biolabs", "biolabo", "biolabos", "biolabor", "biolabore", "biolaboren", "biolaboratorium",
      "biolaboratoria", "biolaboratory", "biolaboratories", "biolaboratorio", "biolaboratorios", "biolaboratoire",
      "biolaboratoires")),
    ("gelijk", "accent", "nl", ("Oekraïne", "Oekraine"), ("oekraine",)),
    ("gelijk", "accent", "es", ("vacunación", "vacunacion"), ("vacunacion",)),
    ("gelijk", "accent", "fr", ("œuvre", "oeuvre"), ("œuvre", "oeuvre")),
    ("gelijk", "accent", "fr", ("cœur", "coeur"), ("cœur", "coeur")),
    ("gelijk", "accent", "de", ("Straße", "Strasse"), ("straße", "strasse")),
    ("gelijk", "accent", "en", ("Kılıçdaroğlu", "Kilicdaroglu"), ("kılıcdaroglu", "kilicdaroglu")),
    ("gelijk", "naam", "en", ("Zelensky", "Zelenskyy", "Selenskyj", "Zelenski"),
     ("zelensky", "zelenskyy", "selenskyj", "zelenski")),
    ("gelijk", "naam", "en", ("Zelenskiy",), ("zelensky", "zelenskyy", "selenskyj", "zelenski")),
    ("gelijk", "naam", "en", ("Kyiv", "Kiev", "Kiew"), ("kyiv", "kiev", "kiew")),
    ("gelijk", "naam", "nl", ("Poetin", "Putin", "Poutine"), ("poetin", "putin", "poutine")),
    ("gelijk", "naam", "nl", ("Moskou", "Moscow", "Moskau", "Moscú", "Moscou"),
     ("moskou", "moscow", "moskau", "moscu", "moscou")),
    ("gelijk", "naam", "nl", ("Oekraïne", "Ukraine", "Ucrania"), ("oekraine", "ukraine", "ucrania")),
    ("gelijk", "naam", "nl", ("NAVO", "NATO", "OTAN"), ("navo", "nato", "otan")),
    ("gelijk", "naam", "en", ("Lukashenko", "Lukashenka", "Loekasjenko", "Loukachenko"),
     ("lukashenko", "lukashenka", "loekasjenko", "loukachenko")),
    ("gelijk", "streepje", "en", ("COVID-19", "covid19"), ("covid19", "covid 19")),
    ("gelijk", "streepje", "en", ("G7", "G-7"), ("g7", "g 7")),
    ("gelijk", "streepje", "en", ("5G", "5-G"), ("5g", "5 g")),
    ("gelijk", "streepje", "en", ("e-mail", "email"), ("email", "e mail")),
]
# Hoofdletters doen er niet toe: deze vragen vinden precies hetzelfde.
ZELFDE = [("hoofdletters", "en", ("biolab", "Biolab", "BIOLAB", "bIoLaB")),
          ("hoofdletters", "de", ("Impfstoff", "impfstoff", "IMPFSTOFF"))]
# Tussen aanhalingstekens: precies dat woord of die woorden achter elkaar, en niets anders.
PRECIES = [("aanhalingstekens", "en", ('"biolab"', "“biolab”", "«biolab»", "„biolab“"), "biolab"),
           ("aanhalingstekens", "en", ('"Bill Gates"', '"bill gates"'), "bill gates"),
           ("aanhalingstekens", "fr", ("« Moscou »",), "moscou")]
# Eén of twee tekens in een schrift zonder spaties: waar die tekens in de bewering staan.
KORT = [("kort", "zh", "疫"), ("kort", "zh", "疫苗")]
# Een afkorting in hoofdletters (#34.2ab): (taal, vraag, nummer bij Wikidata, wat een lezer verwacht). Bij een naam vindt
# de vraag minstens EIS_DEKKING van de pagina's die het namenregister aan die naam koppelt, en daarbuiten hoogstens
# evenveel; bij een woord vindt de vraag in hoofdletters wat ze in kleine letters vindt. Gekozen op wat er in de uitgave
# is, vóór de meting.
AFKORTINGEN = [("en", "WHO", "Q7817", "naam"), ("es", "OMS", "Q7817", "naam"), ("nl", "WGO", "Q7817", "naam"),
               ("en", "UN", "Q1065", "naam"), ("fr", "ONU", "Q1065", "naam"), ("nl", "EU", "Q458", "naam"),
               ("es", "UE", "Q458", "naam"), ("en", "US", "Q30", "naam"), ("nl", "VS", "Q30", "naam"),
               ("en", "FBI", "Q8333", "naam"), ("en", "CIA", "Q37230", "naam"), ("en", "BBC", "Q9531", "naam"),
               ("en", "IMF", "Q7804", "naam"), ("en", "AFP", "Q438061", "woord")]
# Eén of twee tekens in een schrift met spaties: een antwoord zonder fout, binnen een seconde (het aantal staat erbij).
KORT_LOS = ["a", "EU", "UE", "AI"]
# De aantallen bij de filters kloppen met de lijst die je krijgt als je zo'n filter kiest.
FILTERVRAGEN = ["biolab", "Oekraïne", "COVID-19", "Zelensky", "vaccin", "Impfstoffe"]
FILTERS = ("taal", "jaar", "oordeel", "land", "thema", "redactie")


# Zoeken dat meedenkt (PLAN #34.2ac, SPECS E9.S14), gekozen vóór de meting op wat er in de uitgave is. Een land,
# redactie, thema of onderdeel verruimt: de vraag vindt alles wat ze letterlijk vindt, en meer; tussen aanhalingstekens
# niets anders dan letterlijk.
VERRUIMD = [("nl", "India", "land", "IN"), ("en", "Russia", "land", "RU"), ("de", "Sri Lanka", "land", "LK"),
            ("en", "vaccine india", "land", "IN"), ("en", "politifact trump", "redactie", "PolitiFact"),
            ("nl", "Gezondheid", "thema", "health"), ("en", "Covid-19", "onderdeel", "covid"), ("en", '"India"', None, None)]
# Meteen naar een pagina: de volledige naam van een persoon of een dossier; geen deel van een naam, geen plaats, geen thema,
# niets tussen aanhalingstekens. Het dossier en de links kiest de proef zelf uit de uitgave (het eerste dossier, links
# met het zaad).
DOORSTUREN = [("nl", "Narendra Modi", "naam:Q1058"), ("en", "Donald Trump", "naam:Q22686"), ("en", "trump", None),
              ("en", "India", None), ("en", '"Narendra Modi"', None), ("nl", "Gezondheid", None), ("en", "NATO", None)]
LINKS = 20
# Het woord afmaken: wat de aanvulling geeft begint met wat je typte en vindt iets; niets bij een bestaand woord, na een
# spatie, onder drie letters. Een bekend woord staat erbij als het vóór de meting vaststond.
AANVULLEN = [("vacc", "vaccine"), ("zelen", None), ("covid vacc", "covid vaccine"), ("biola", None), ("narend", "narendra"),
             ("vaccine", ""), ("vacc ", ""), ("va", "")]
# Een vraag naar de site zelf wijst naar die pagina.
VASTE = [("nl", "privacy", "about"), ("en", "api", "platform"), ("de", "Quellen", "sources"), ("fr", "rédactions", "newsrooms")]
# Suggesties tijdens het typen: elk begin van deze vragen, letter voor letter, met alles wat de suggesties vragen.
TYPEN = ["vaccine india", "narendra modi", "covid-19", "gezondheid", "biolab"]
EIS_SUGGESTIE = 0.1


def _doel(conn: sqlite3.Connection, woorden) -> set[str]:
    uit: set[str] = set()
    for w in woorden:
        uit |= {r[0] for r in conn.execute("SELECT nummer FROM zoek WHERE zoek MATCH ?", ('"' + w + '"',))}
    return uit


def _stuk(conn: sqlite3.Connection, tekens: str) -> set[str]:
    patroon = "%" + tekens.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return {r[0] for r in conn.execute("SELECT nummer FROM zoek3 WHERE tekst LIKE ? ESCAPE '\\'", (patroon,))}


def meet(bestand: str | Path, lang: int = LANGE_VRAGEN, zaad: int = ZAAD) -> dict:
    pub = db.Publicatie(bestand)
    pub.afkortingen_klaar(60)      # de server draait al voor er een vraag komt; meet zoals hij dan is (#34.2ab)
    conn = sqlite3.connect(f"{Path(bestand).resolve().as_uri()}?mode=ro", uri=True)
    tijden: list[tuple[float, str]] = []

    def vind(vraag: str) -> set[str]:
        begin = time.perf_counter()
        uit = pub.zoek_ruim(vraag)
        tijden.append((time.perf_counter() - begin, vraag))
        alle = set(pub.treffers(vraag))
        if len(alle) != uit["zonder_filters"]:
            raise AssertionError(f"de treffers en het aantal zonder filters lopen uiteen bij {vraag!r}")
        return alle

    gevallen: list[dict] = []
    for soort, groep, taal, vragen, woorden in GELIJK:
        doel = _doel(conn, woorden)
        rijen = []
        for v in vragen:
            t = vind(v)
            rijen.append({"vraag": v, "aantal": len(t), "dekking": len(t & doel) / len(doel) if doel else 1.0,
                          "extra": len(t - doel)})
        gevallen.append({"soort": soort, "groep": groep, "taal": taal, "doel": len(doel), "vragen": rijen,
                         "gehaald": bool(doel) and all(r["dekking"] >= EIS_DEKKING for r in rijen)})
    for groep, taal, vragen in ZELFDE:
        sets = [vind(v) for v in vragen]
        gevallen.append({"soort": "zelfde", "groep": groep, "taal": taal, "doel": len(sets[0]),
                         "vragen": [{"vraag": v, "aantal": len(s)} for v, s in zip(vragen, sets)],
                         "gehaald": all(s == sets[0] for s in sets)})
    for groep, taal, vragen, woorden in PRECIES:
        doel = _doel(conn, [woorden])
        sets = [vind(v) for v in vragen]
        gevallen.append({"soort": "precies", "groep": groep, "taal": taal, "doel": len(doel),
                         "vragen": [{"vraag": v, "aantal": len(s), "extra": len(s - doel)} for v, s in zip(vragen, sets)],
                         "gehaald": bool(doel) and all(s == doel for s in sets)})
    for groep, taal, tekens in KORT:
        doel, t = _stuk(conn, tekens), vind(tekens)
        dekking = len(t & doel) / len(doel) if doel else 1.0
        gevallen.append({"soort": "gelijk", "groep": groep, "taal": taal, "doel": len(doel),
                         "vragen": [{"vraag": tekens, "aantal": len(t), "dekking": dekking, "extra": len(t - doel)}],
                         "gehaald": bool(doel) and dekking >= EIS_DEKKING})
    for tekens in KORT_LOS:
        vind(tekens)
    for taal, vraag, nummer, verwacht in AFKORTINGEN:
        t = vind(vraag)
        if verwacht == "naam":
            doel = {r[0] for r in conn.execute("SELECT pagina FROM pagina_naam WHERE naam = ?", (nummer,))}
            dekking = len(t & doel) / len(doel) if doel else 1.0
            gehaald = bool(doel) and dekking >= EIS_DEKKING and len(t - doel) <= len(doel)
        else:
            doel = vind(vraag.lower())
            dekking = len(t & doel) / len(doel) if doel else 1.0
            gehaald = t == doel
        gevallen.append({"soort": "afkorting", "groep": "afkorting", "taal": taal, "doel": len(doel),
                         "vragen": [{"vraag": vraag, "aantal": len(t), "dekking": dekking, "extra": len(t - doel)}],
                         "gehaald": gehaald})

    # Zoeken dat meedenkt (#34.2ac)
    for taal, vraag, soort, waarde in VERRUIMD:
        # letterlijk met een deel van de woorden (geen enkele bewering heeft ze allemaal) zijn geen treffers: dan niets
        t = vind(vraag)
        letterlijk = set() if pub._keuze(vraag, True)[1] else set(pub.treffers(vraag, letterlijk=True))
        gelezen = [(g["soort"], g["waarde"]) for g in pub.zoek_ruim(vraag)["gelezen"]]
        verwacht = [(soort, waarde)] if soort else []
        gevallen.append({"soort": "verruimd", "groep": "verruimd", "taal": taal, "doel": len(letterlijk),
                         "vragen": [{"vraag": vraag, "aantal": len(t), "letterlijk": len(letterlijk), "gelezen": gelezen}],
                         "gehaald": letterlijk <= t and gelezen == verwacht and (len(t) > len(letterlijk)) == bool(soort)})
    dossier = pub.dossiers[0] if pub.dossiers else None
    for taal, vraag, verwacht in DOORSTUREN + ([("nl", dossier["naam"]["nl"], f"dossier:{dossier['sleutel']}")] if dossier else []):
        doel = pub.doorsturen(vraag)
        kreeg = f"{doel['soort']}:{doel.get('nummer') or doel.get('sleutel')}" if doel else None
        gevallen.append({"soort": "doorsturen", "groep": "doorsturen", "taal": taal, "doel": 1,
                         "vragen": [{"vraag": vraag, "kreeg": kreeg, "verwacht": verwacht}], "gehaald": kreeg == verwacht})
    alle_links = conn.execute("SELECT pagina, url FROM check_ ORDER BY pagina, volg").fetchall()
    per_link: dict[str, set[str]] = {}
    for pagina, url in alle_links:
        per_link.setdefault(url, set()).add(pagina)
    goed, fout = 0, []
    for i, (pagina, url) in enumerate(random.Random(zaad).sample(alle_links, min(LINKS, len(alle_links)))):
        geplakt = url if i % 2 else url.replace("https://", "").replace("http://", "") + "?utm_source=whatsapp"
        doel = pub.doorsturen(geplakt)
        if doel and doel["soort"] == "factcheck" and doel["nummer"] in per_link[url]:
            goed += 1
        else:
            fout.append(geplakt)
    for pagina in random.Random(zaad + 1).sample(sorted({p for p, _ in alle_links}), 5):
        doel = pub.doorsturen(f"https://factiz.org/nl/fact-checks/{pagina}/")
        goed, fout = (goed + 1, fout) if doel and doel["nummer"] == pagina else (goed, fout + [pagina])
    gevallen.append({"soort": "link", "groep": "link", "taal": "alle", "doel": LINKS + 5,
                     "vragen": [{"vraag": f"{LINKS} links van redacties en 5 van Factiz", "aantal": goed, "fouten": fout}],
                     "gehaald": not fout})
    for vraag, verwacht in AANVULLEN:
        kreeg = pub.aanvulling(vraag)
        if verwacht == "":
            gehaald = kreeg is None
        else:
            gehaald = bool(kreeg) and kreeg.startswith(vraag) and pub.tel(kreeg) > 0 and (verwacht is None or kreeg == verwacht)
        gevallen.append({"soort": "aanvullen", "groep": "aanvullen", "taal": "alle", "doel": 1,
                         "vragen": [{"vraag": vraag, "kreeg": kreeg}], "gehaald": gehaald})
    from factiz_site.app import vaste_ingangen
    for taal, vraag, pagina in VASTE:
        kreeg = [i["pagina"] for i in vaste_ingangen(vraag, taal)]
        gevallen.append({"soort": "vaste pagina", "groep": "vaste pagina", "taal": taal, "doel": 1,
                         "vragen": [{"vraag": vraag, "kreeg": kreeg}], "gehaald": kreeg == [pagina]})
    suggestietijden: list[tuple[float, str]] = []
    for vraag in TYPEN:
        for n in range(1, len(vraag) + 1):
            begin_ = vraag[:n]
            start = time.perf_counter()
            pub.suggesties(begin_, "nl")
            if len(begin_.strip()) >= 2:
                pub.zoek_ruim(begin_, 1, "nl")
            if (aan := pub.aanvulling(begin_)) is not None:
                pub.tel(aan)
            suggestietijden.append((time.perf_counter() - start, begin_))
    traag = max(suggestietijden)
    gevallen.append({"soort": "suggesties", "groep": "suggesties", "taal": "alle", "doel": len(suggestietijden),
                     "vragen": [{"vraag": f"{len(suggestietijden)} keer typen", "mediaan_ms": round(statistics.median(
                         t for t, _ in suggestietijden) * 1000), "traagste_ms": round(traag[0] * 1000), "traagste": traag[1]}],
                     "gehaald": traag[0] <= EIS_SUGGESTIE})

    # Heel lange vragen: een bewering in haar geheel geplakt, langer dan de site een vraag leest.
    lange = [(n, b) for n, b in conn.execute("SELECT nummer, bewering FROM pagina WHERE length(bewering) > ? "
                                             "ORDER BY nummer", (db.MAX_VRAAG + 20,))]
    proef = random.Random(zaad).sample(lange, min(lang, len(lange)))
    gevonden, midden, missers = 0, 0, []
    for nummer, bewering in proef:
        tekst = db.schoon(bewering)
        midden += tekst[db.MAX_VRAAG - 1].isalnum() and tekst[db.MAX_VRAAG].isalnum()
        begin = time.perf_counter()
        rijen = pub.zoek_ruim(tekst)["rijen"]
        tijden.append((time.perf_counter() - begin, tekst[:40] + "…"))
        if nummer in [r["nummer"] for r in rijen[:10]]:
            gevonden += 1
        else:
            missers.append(nummer)
    gevallen.append({"soort": "lang", "groep": "lang", "taal": "alle", "doel": len(proef),
                     "vragen": [{"vraag": f"{len(proef)} beweringen in hun geheel", "aantal": gevonden,
                                 "midden_in_een_woord": midden, "missers": missers}],
                     "gehaald": gevonden >= min(EIS_LANG, len(proef))})

    # De aantallen bij de filters: elke waarde die de zoekpagina aanbiedt, geeft zo veel treffers als er staat.
    fouten, getoetst = [], 0
    for vraag in FILTERVRAGEN:
        facetten = pub.zoek_ruim(vraag)["facetten"]
        for soort in FILTERS:
            for waarde, aantal in sorted(facetten.get(soort, {}).items(), key=lambda x: -x[1])[:3]:
                getoetst += 1
                totaal = pub.zoek_ruim(vraag, **{soort: waarde})["totaal"]
                if totaal != aantal:
                    fouten.append((vraag, soort, waarde, aantal, totaal))
    gevallen.append({"soort": "filters", "groep": "filters", "taal": "alle", "doel": getoetst,
                     "vragen": [{"vraag": f"{getoetst} filterwaarden bij {len(FILTERVRAGEN)} vragen", "aantal": getoetst - len(fouten),
                                 "fouten": fouten}], "gehaald": not fouten})

    traagste = max(tijden)
    gevallen.append({"soort": "snelheid", "groep": "snelheid", "taal": "alle", "doel": len(tijden),
                     "vragen": [{"vraag": f"{len(tijden)} vragen", "mediaan_ms": round(statistics.median(t for t, _ in tijden) * 1000),
                                 "traagste_ms": round(traagste[0] * 1000), "traagste": traagste[1]}],
                     "gehaald": traagste[0] <= EIS_SECONDEN})
    conn.close()
    return {"gevallen": gevallen, "gehaald": sum(g["gehaald"] for g in gevallen), "totaal": len(gevallen)}


def main() -> None:  # pragma: no cover - CLI
    from factiz_site.app import _standaard_pad

    bestand = sys.argv[1] if len(sys.argv) > 1 else _standaard_pad()
    u = meet(bestand)
    for g in u["gevallen"]:
        teken = "ja " if g["gehaald"] else "NEE"
        print(f"{teken} {g['groep']:14} {g['taal']:4} doel {g['doel']:5}")
        for r in g["vragen"]:
            rest = "  ".join(f"{k} {v:.0%}" if k == "dekking" else f"{k} {v}" for k, v in r.items() if k != "vraag")
            print(f"      {r['vraag']!s:28} {rest}")
    per_groep: dict[str, list[int]] = {}
    for g in u["gevallen"]:
        per_groep.setdefault(g["groep"], [0, 0])
        per_groep[g["groep"]][0] += g["gehaald"]
        per_groep[g["groep"]][1] += 1
    print("per groep: " + ", ".join(f"{k} {a} van {b}" for k, (a, b) in per_groep.items()))
    print(f"samen {u['gehaald']} van {u['totaal']} gevallen gehaald")


if __name__ == "__main__":  # pragma: no cover
    main()
