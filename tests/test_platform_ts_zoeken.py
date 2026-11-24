"""Zoeken en suggesties in TypeScript naast Python (B80, PLAN #34.2bo stap 4): op de uitgaven van de toetsen van het
zoeken dezelfde antwoorden, en de tekstfuncties eronder (tekens zoals Python ze ziet, vormen, afstand, links, markeren,
de logaritme) gelijk aan Python."""

import json
import math
import random
import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from factiz_site import app as fa
from factiz_site import db
from factiz_site import gelijk, gelijk_zoeken
from tests import test_factiz_bericht as tb
from tests import test_factiz_randgevallen as tr
from tests import test_factiz_toetsenbord as tt
from tests import test_factiz_zoeken as tz
from tests.schriften import PANEEL
from tests.test_factiz_dossiers import _site as _dossiersite
from tests.test_factiz_namen import _site as _namensite

SITE = Path(__file__).resolve().parent.parent / "site"
PLATFORM = SITE / "src" / "platform"


def _ruw(fixture):
    """De functie achter een fixture van een andere toets, om dezelfde uitgave te bouwen."""
    return fixture._get_wrapped_function()


def _client(bestand):
    client = TestClient(fa.maak_app(bestand), follow_redirects=False)
    client.bestand = bestand
    return client


def _uit_de_uitgave(pub: db.Publicatie) -> list[dict]:
    """Per bewering van een kleine uitgave: de hele bewering, het eerste woord, twee woorden, een tikfout en elk begin van
    het eerste woord als suggestie."""
    uit = []
    for (bewering,) in pub._conn().execute("SELECT bewering FROM pagina ORDER BY nummer"):
        woorden = bewering.split()
        vragen = [bewering, woorden[0], " ".join(woorden[:2]), " ".join(woorden[-2:])]
        lang = max(woorden, key=len)
        if len(lang) > 4:
            vragen.append(lang[:2] + lang[3:])
        for vraag in vragen:
            uit += [gelijk_zoeken.zoek("en", vraag), gelijk_zoeken.zoek("nl", vraag, sorteer="oud"),
                    gelijk_zoeken.suggestie("en", vraag)]
        uit += [gelijk_zoeken.suggestie("nl", lang[:n]) for n in range(1, len(lang) + 1)]
    return uit


def _gelijk(client, extra=()):
    pub = gelijk_zoeken.klaar(client)
    lijst = gelijk_zoeken.verzoeken(pub) + _uit_de_uitgave(pub) + list(extra)
    fouten, n = gelijk_zoeken.verschillen(client, client.bestand, lijst)
    assert fouten == [], f"{len(fouten)} van {n} verschillen:\n" + "\n".join(fouten[:20])


@pytest.fixture(scope="module")
def zoeken(tmp_path_factory):
    return _client(_ruw(tz.site)(tmp_path_factory)[2])


@pytest.fixture(scope="module")
def randgevallen(tmp_path_factory):
    return _client(_ruw(tr.site)(tmp_path_factory)[3])


def test_search_and_suggestions_answer_the_same_on_the_search_release(zoeken):
    extra = [gelijk_zoeken.zoek(t, v) for t in ("en", "nl", "es", "zh", "ar", "hi") for v in
             ("Zelensky", "villa Florida", "泽连斯基", "疫苗", "زيلينسكي", "य\u0942क\u094dर\u0947न", "உக\u0bcdரைனில\u0bcd", "เซเลนสก\u0e35", "Ordinary claim",
              "weather", "claim number 7", "Eiffel", "zelenksy", "Paris", "mansión", "palacete")]
    _gelijk(zoeken, extra)


def test_search_and_suggestions_answer_the_same_on_the_edge_cases(randgevallen):
    vragen = [t for t, _ in tr.BEWERINGEN.values()] + [tr.LANG, "biolab", "Biolabor", "Zelenskiy", "Lukashenko", "Grigorevich",
                                                       "capital", "Kyjiw", "NAVO", "WHO", "WGO", "AFP", "Saied", "Said",
                                                       "Gesundheit", "Weltgesundheitsorganisation", "indien", "Indien",
                                                       "crime", "crimea", "kind", "kinder", "police", "policy"]
    extra = [gelijk_zoeken.zoek(t, v) for t in ("en", "nl", "de", "es", "fr") for v in vragen]
    extra += [gelijk_zoeken.suggestie(t, v) for t in ("en", "de") for v in vragen]
    _gelijk(randgevallen, extra)


def test_search_and_suggestions_answer_the_same_on_releases_with_dossiers_and_names(tmp_path_factory):
    for client in (_dossiersite(tmp_path_factory)[0], _namensite(tmp_path_factory)[0]):
        pub = client.app.state.publicatie
        extra = [gelijk_zoeken.zoek(t, d["naam"][t]) for d in pub.dossiers for t in ("nl", "en", "de", "ru")]
        extra += [gelijk_zoeken.zoek(t, n["naam"][t]) for n in pub._naam.values() for t in ("nl", "en", "es")]
        extra += [gelijk_zoeken.zoek("en", "Zelensky", thema=th["sleutel"]) for th in pub.themas]
        _gelijk(client, extra)


def test_search_answers_the_same_for_a_persian_or_arabic_keyboard_and_a_pasted_message(tmp_path_factory):
    toetsenbord = _client(_ruw(tt.pub)(tmp_path_factory)[0].pad)
    _gelijk(toetsenbord, [gelijk_zoeken.zoek(t, v) for t in ("fa", "ar", "en") for v in ("کرونا", "كرونا", "ایران", "ايران")])
    bericht = _client(_ruw(tb.pub_en_app)(tmp_path_factory)[0].pad)
    lang = "Forwarded as received. " * 12 + "Bill Gates admitted vaccines contain a microchip"
    vragen = [tb.BERICHT, tb.GEWOON, tb.GATES, lang, "microchip", "Gates microchip", "vaccines safe",
              "This is a claim about the moon that people share on the day, please share it with people"]
    _gelijk(bericht, [gelijk_zoeken.zoek(t, v) for t in ("en", "nl") for v in vragen])


# --- de tekstfuncties ------------------------------------------------------------------------------------------------------

def _node(script: str, invoer):
    """Een stuk TypeScript dat de modules van het platform inleest en op `invoer` antwoordt."""
    kop = (f"import * as u from {json.dumps((PLATFORM / 'zoeken-unicode.ts').as_uri())};\n"
           f"import * as t from {json.dumps((PLATFORM / 'zoeken-tekst.ts').as_uri())};\n"
           f"import * as m from {json.dumps((PLATFORM / 'zoeken-motor.ts').as_uri())};\n"
           "let invoer = ''; for await (const s of process.stdin) invoer += s; const x = JSON.parse(invoer);\n")
    uit = subprocess.run(["node", "--input-type=module", "-e", kop + script], input=json.dumps(invoer), capture_output=True,
                         text=True, cwd=SITE, timeout=600)
    assert uit.returncode == 0, uit.stderr[-3000:]
    return json.loads(uit.stdout)


def test_every_character_has_the_properties_python_gives_it():
    """Unicode 15.0 zoals Python 3.12 het kent, ook in een Node met een nieuwere Unicode."""
    js = _node("""
const uit = { alnum: [], alpha: [], upper: [], mn: [], m: [], space: [], fold: {}, lower: {}, nfkc: {}, nfd: {} };
for (let cp = 0; cp < 0x110000; cp++) {
  if (cp >= 0xd800 && cp <= 0xdfff) continue;
  const c = String.fromCodePoint(cp);
  if (u.isalnum(c)) uit.alnum.push(cp);
  if (u.isalpha(c)) uit.alpha.push(cp);
  if (u.isupper(c)) uit.upper.push(cp);
  if (u.isMn(c)) uit.mn.push(cp);
  if (u.isM(c)) uit.m.push(cp);
  if (u.isspace(c)) uit.space.push(cp);
  if (u.casefold(c) !== c) uit.fold[cp] = u.casefold(c);
  if (u.lower(c) !== c) uit.lower[cp] = u.lower(c);
  if (u.normaliseer(c, 'NFKC') !== c) uit.nfkc[cp] = u.normaliseer(c, 'NFKC');
  if (u.normaliseer(c, 'NFD') !== c) uit.nfd[cp] = u.normaliseer(c, 'NFD');
}
process.stdout.write(JSON.stringify(uit));
""", None)
    import unicodedata
    alle = [cp for cp in range(0x110000) if not 0xD800 <= cp <= 0xDFFF]
    assert js["alnum"] == [cp for cp in alle if chr(cp).isalnum()]
    assert js["alpha"] == [cp for cp in alle if chr(cp).isalpha()]
    assert js["upper"] == [cp for cp in alle if chr(cp).isupper()]
    assert js["mn"] == [cp for cp in alle if unicodedata.category(chr(cp)) == "Mn"]
    assert js["m"] == [cp for cp in alle if unicodedata.category(chr(cp)).startswith("M")]
    assert js["space"] == [cp for cp in alle if chr(cp).isspace()]
    for naam, f in (("fold", str.casefold), ("lower", str.lower), ("nfkc", lambda c: unicodedata.normalize("NFKC", c)),
                    ("nfd", lambda c: unicodedata.normalize("NFD", c))):
        assert js[naam] == {str(cp): f(chr(cp)) for cp in alle if f(chr(cp)) != chr(cp)}, naam


TEKSTEN = list(PANEEL.values()) + ["Straße STRASSE ΧΑΟΣ Σ ΌΣΟΣ İstanbul", "e\u0301lection ÉLECTION", "WHO's OMS UN HOMBRE",
                                   "THE WHO SAYS", "OMSzorg WHO", "\U000105c0 x \ue000", "ﬁnance ǅ ǈ", "covid-19 COVID‐19",
                                   "Kılıçdaroğlu", "ｖａｃｃｉｎｅ", "الله", "a" * 300, ""]


def test_the_text_functions_of_the_search_give_what_python_gives():
    paren = [(a, b) for a in TEKSTEN[:20] for b in TEKSTEN[:20]]
    woorden = sorted({w for t in TEKSTEN for w in t.split()}) + ["vaccine", "vaccines", "biolaboratories", "réseaux", "hôpital",
                                                                  "laboratorium", "criteria", "boss", "virus", "kind", "crimes"]
    js = _node("""
const w = x.woorden;
process.stdout.write(JSON.stringify({
  zoektermen: x.teksten.map((s) => t.zoektermen(s)), lang: x.teksten.map((s) => t.zoekdelen(s, true)),
  delen: x.teksten.map((s) => t.zoekdelen(s)), alfabet: x.teksten.map(t.alfabet), sleutel: x.teksten.map(t.sleutel),
  indexvorm: x.teksten.map(t.indexvorm), ascii: x.teksten.map(t.ascii),
  vormen: w.map((v) => [...t.vormen(v)].sort()), afkorting: w.map((v) => t.isAfkorting(v, 3)),
  toetsenbord: w.map(t.toetsenbordvormen), bijnaam: w.map((v) => t.bijnaamTelt(v, ['Kyiv', 'Zelensky'])),
  hoofd: x.teksten.map((s) => [...t.losInHoofdletters(s, new Set(['WHO', 'OMS', 'UN', 'EU', 'ÉU']))].sort()),
  afstand: x.paren.map(([a, b]) => t.afstand(a, b, 3)),
  markeer: x.teksten.map((s) => t.markeer(s, x.termen)), fragment: x.teksten.map((s) => t.fragment(s, x.termen, 60)),
}));
""", {"teksten": TEKSTEN, "woorden": woorden, "paren": paren,
      "termen": ["who", "vaccine", "covid 19", "biolab*", "Σ", "élection", "ب", "un"]})
    termen = ["who", "vaccine", "covid 19", "biolab*", "Σ", "élection", "ب", "un"]
    assert js["zoektermen"] == [db.zoektermen(s) for s in TEKSTEN]
    assert js["lang"] == [[list(d) for d in db.zoekdelen(s, lang=True)] for s in TEKSTEN]
    assert js["delen"] == [[list(d) for d in db.zoekdelen(s)] for s in TEKSTEN]
    assert js["alfabet"] == [db._alfabet(s) for s in TEKSTEN]
    assert js["sleutel"] == [db.sleutel(s) for s in TEKSTEN]
    assert js["indexvorm"] == [db._indexvorm(s) for s in TEKSTEN]
    assert js["ascii"] == [db._ascii(s) for s in TEKSTEN]
    assert js["vormen"] == [sorted(db.vormen(v)) for v in woorden]
    assert js["afkorting"] == [db._is_afkorting(v, 3) for v in woorden]
    assert js["toetsenbord"] == [db.toetsenbordvormen(v) for v in woorden]
    assert js["bijnaam"] == [db.bijnaam_telt(v, ["Kyiv", "Zelensky"]) for v in woorden]
    assert js["hoofd"] == [sorted(db.los_in_hoofdletters(s, {"WHO", "OMS", "UN", "EU", "ÉU"})) for s in TEKSTEN]
    assert js["afstand"] == [db._afstand(a, b, 3) for a, b in paren]
    assert js["markeer"] == [[list(s) for s in fa.markeer(s, termen)] for s in TEKSTEN]
    assert js["fragment"] == [fa.fragment(s, termen, 60) for s in TEKSTEN]


def test_a_pasted_link_is_read_like_python_reads_it():
    adressen = ["https://www.snopes.com/fact-check/x/", "snopes.com/fact-check/x?utm_source=a&id=3&fbclid=1#y",
                "HTTPS://M.Example.COM/A/B/?Q=1", "https://amp.www.example.com/a", "https://www.m.amp.example.com/a",
                "example.com", "example.com/", "https://[::1]/a.b", "https://[1.2.3.4]/x", "http://[v1.x]/p.q",
                "http://[v1.]/p.q", "https://a[b]/c.d", "https://[::ffff:1.2.3.4]/a", "https://[fe80::1%25eth0]/x",
                "https://[1:2:3:4:5:6:7:8:9]/x", "https://[::1::2]/x", "https://user:pw@Host.example.com:8080/x/",
                "https://Ａ.com/x", "https://exa℀mple.com/x", "https://例子.中国/路径?键=值", "x.y/%E2%82%ACz?a=%E2%82",
                "x.y/z?a=1&a=2&utm_x=3&ref=4&s=5&S=6&amp=7&mc_x=8&b=%ZZ&c=+d&e", "x.y/z?fbclid%0A=1&ref%0A=2",
                "x.y/z?%EF%BB%BFa=1", "  https://x.y/z  ", "ftp://x.y/z", "mailto:a@b.c/d", "x.y/z?" + "a" * 50,
                "https://x.y/z;p?q#f", "\x01https://x.y/z", "https://x.y\t/z", "https://[::1/x", "https://]x[/y",
                "javascript:alert(1)/x.y", "//x.y/z", "https://x.y/%7Euser", "https://x.y/z?q=%2B%20+&r=a%26b"]
    js = _node("process.stdout.write(JSON.stringify(x.map(t.adresvorm)))", adressen)
    assert js == [list(v) if v is not None else None for v in (db.adresvorm(a) for a in adressen)]


def test_the_weight_of_a_rare_word_is_the_logarithm_python_computes():
    """Het gewicht van een zeldzaam woord in een geplakt bericht is ln(n / df), met df hoogstens 2% van n. `Math.log` zit
    in ruim 1% van de gevallen een bit naast Python; `logPython` rondt juist af, en de libm van macOS onder Python doet dat
    bijna altijd. Gelijk op elke waarde van deze uitgave (106.073 pagina's) en van uitgaven tot 400 pagina's (de toetsen);
    daarbuiten kan een waarde vlak naast het midden tussen twee getallen een bit verschillen (3 op de 10.000 bij n tot
    3.000), en dat verandert alleen de volgorde van twee treffers met wiskundig hetzelfde gewicht."""
    nodig = [n / df for n in [106073, *range(1, 401)] for df in range(1, max(3, int(0.02 * n)) + 2)]
    verder = [n / df for n in range(401, 3001) for df in range(1, int(0.02 * n) + 2)]
    verder += [random.Random(7).uniform(1, 1e6) for _ in range(20000)]
    js = _node("process.stdout.write(JSON.stringify(x.map((v) => m.logPython(v))))", nodig + verder)
    assert js[:len(nodig)] == [math.log(v) for v in nodig]
    anders = sum(a != math.log(v) for a, v in zip(js[len(nodig):], verder))
    assert anders <= len(verder) / 1000, anders


def test_the_comparison_harness_itself_still_sees_a_difference(zoeken):
    """Als TypeScript iets anders zegt, merkt de vergelijking het: een ingang die niet bestaat geeft 404 tegen 404, maar een
    andere vraag aan beide kanten niet hetzelfde antwoord."""
    a = gelijk.ts_antwoorden(zoeken.bestand, [gelijk_zoeken.zoek("en", "Zelensky"), gelijk_zoeken.zoek("en", "weather")])
    assert gelijk.eerste_verschil(a[0]["body"], a[1]["body"]) is not None
