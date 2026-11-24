"""De site in tien talen erbij (PLAN #34.2be, B79): de vaste teksten, de thema's en de dossiers, vertaald door Sonnet
uit het Engels.

    python -m doublecheck.sitevertaling teksten [--taal pt,ru] | themas | dossiers | korter

Direct, niet via de Batch API (het zijn een paar tientallen vragen), met een grens van $5 voor alles samen. Elke vertaling
wordt nagekeken: dezelfde sleutels, dezelfde plekhouders, geen em-streepje, geen uitroepteken, niet leeg. Wat niet klopt,
gaat opnieuw, hoogstens drie keer; blijft het fout, dan stopt het commando. De maanden, de datumvorm, het duizendtalteken
en de namen van landen en talen komen uit CLDR (`doublecheck/cldr.swift`), niet hiervandaan. Alles wat hier gemaakt wordt,
draagt `nagelezen: false` (B74): een moedertaallezer heeft het nog niet gezien.
"""

from __future__ import annotations

import json
import re
import sys
import threading
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from doublecheck import dossiers as ds

WORTEL = Path(__file__).resolve().parent.parent
TEKSTEN = WORTEL / "factiz_site" / "teksten"
THEMAS = WORTEL / "content" / "themas.json"
DOSSIERS = WORTEL / "content" / "dossiers"
CLDR = WORTEL / "data" / "sitetalen" / "cldr.json"
MODEL = "claude-sonnet-5-5"
PRIJS = {"in": 3.00, "uit": 15.00}          # dollar per miljoen tokens, gewone vraag
GRENS = 5.00
VRAAG = "sitevertaling-v1"

# de nieuwe talen, met hoe de site de lezer aanspreekt
NIEUW = {
    "pt": ("Brazilian Portuguese (pt-BR)", "Address the reader as 'você'."),
    "ru": ("Russian", "Address the reader politely with 'вы' (lowercase)."),
    "uk": ("Ukrainian", "Address the reader with 'ви' (lowercase)."),
    "id": ("Indonesian", "Address the reader as 'Anda'."),
    "tr": ("Turkish", "Address the reader with the polite 'siz' forms."),
    "zh": ("Traditional Chinese as written in Taiwan (zh-Hant-TW)", "Address the reader as 你."),
    "ja": ("Japanese", "Use the polite です/ます style in sentences; short labels and buttons may be plain nouns or verbs."),
    "hi": ("Hindi in Devanagari", "Address the reader as 'आप'."),
    "ar": ("Modern Standard Arabic", "Address the reader in neutral forms; avoid gendered second-person forms where you can."),
    "fa": ("Persian as written in Iran", "Address the reader as 'شما'."),
}
MEERVOUD = {"ru", "uk", "ar"}       # talen waarin een getal de vorm van het woord bepaalt op een manier die de site niet kent

_PLEK = re.compile(r"\{(\w+)\}")
_slot = threading.Lock()
_kosten = {"dollar": 0.0}


# vaste woorden, per taal één keer gekozen en in elke vraag meegegeven, zodat elk stuk hetzelfde woord gebruikt
KERNWOORDEN = {"fact-check": "an article by a newsroom that checked a claim", "fact-checks": "the plural",
               "newsroom": "a fact-checking newsroom or organisation", "claim": "the statement that was checked",
               "verdict": "what the newsroom concluded", "theme": "a broad subject such as Elections",
               "topic": "a part of a theme", "dossier": "a page that follows one recurring story over time",
               "search": "the verb, on a button", "explore": "the section with charts and the world map"}
_woorden: dict[str, dict[str, str]] = {}


def kernwoorden(client, taal: str) -> dict[str, str]:
    """De vaste woorden van een taal, één keer gevraagd."""
    with _slot:
        if taal in _woorden:
            return _woorden[taal]
    naam, _ = NIEUW[taal]
    antwoord = client.messages.create(
        model=MODEL, max_tokens=4000,
        system=(f"Choose the standard {naam} word for each English term on the website of Factiz, a public archive of "
                "fact-checks by newsrooms. Pick the word that fact-checkers in this language use themselves. Answer with "
                "one JSON object: the same keys, each with the word only."),
        messages=[{"role": "user", "content": json.dumps(KERNWOORDEN, ensure_ascii=False)}])
    tekst = next(b.text for b in antwoord.content if b.type == "text").strip()
    with _slot:
        _woorden.setdefault(taal, json.loads(tekst[tekst.find("{"):tekst.rfind("}") + 1]))
        return _woorden[taal]


def _regels_vraag(taal: str, soort: str, woorden: dict[str, str] | None = None) -> str:
    naam, aanspreken = NIEUW[taal]
    vast = ("- Use these words for these terms, every time: " + "; ".join(f"{k} = {v}" for k, v in woorden.items())
            + ".\n") if woorden else ""
    meervoud = ("\n- Keys ending in _een are the singular form (used when the number is 1) and keys ending in _meer the plural "
                "form. This language picks the word form from the number in ways a singular/plural pair cannot cover, so "
                "write every _meer text so it is correct for any number: put the number after a colon, for example "
                "'<noun>: {n}', or use a construction whose noun does not agree with the number.") if taal in MEERVOUD else ""
    return (f"You translate {soort} of Factiz, a public archive of fact-checks made by newsrooms, from English into {naam}. "
            f"{aanspreken}\nRules:\n"
            "- Translate the meaning exactly, in plain, short, natural wording for a website. Never add or soften a verdict.\n"
            "- 'Known to be false' and the other labels mean: a newsroom checked it and found this. Keep that meaning.\n"
            "- Keep every placeholder in curly braces exactly as it is, for example {n}, {naam}, {redactie}; do not translate "
            "the word inside the braces.\n"
            "- Do not translate the names Factiz, factiz.org, EUvsDisinfo, Wikidata, Wikipedia, Natural Earth, CLDR, or the "
            "names of newsrooms and organisations.\n"
            "- Never use an em dash or an exclamation mark (also not the full-width one).\n"
            "- Use the punctuation and quotation marks that are normal in this language.\n"
            f"{meervoud}\n{vast}"
            "Answer with one JSON object only, with exactly the same keys as the input and the translations as values.")


def _vraag(client, taal: str, soort: str, invoer: dict[str, str]) -> dict[str, str]:
    antwoord = client.messages.create(
        model=MODEL, max_tokens=16000, system=_regels_vraag(taal, soort, kernwoorden(client, taal)),
        messages=[{"role": "user", "content": json.dumps(invoer, ensure_ascii=False, indent=0)}])
    with _slot:
        _kosten["dollar"] += (antwoord.usage.input_tokens * PRIJS["in"] + antwoord.usage.output_tokens * PRIJS["uit"]) / 1e6
        if _kosten["dollar"] > GRENS:
            raise SystemExit(f"grens van ${GRENS} bereikt")
    tekst = next(b.text for b in antwoord.content if b.type == "text").strip()
    try:                    # alleen het eerste object; wat erna komt telt niet, en wat niet te lezen is gaat opnieuw
        uit, _ = json.JSONDecoder().raw_decode(tekst[tekst.find("{"):])
    except json.JSONDecodeError:
        return {}
    return uit if isinstance(uit, dict) else {}


def fout(bron: str, vertaling, maximum: int | None = None) -> str:
    """Wat er aan een vertaling niet klopt, of leeg als ze klopt."""
    if not isinstance(vertaling, str) or not vertaling.strip():
        return "leeg"
    if maximum and len(vertaling.strip()) > maximum:
        return "te lang"
    if sorted(_PLEK.findall(bron)) != sorted(_PLEK.findall(vertaling)):
        return "plekhouders"
    if "—" in vertaling or "!" in vertaling or "！" in vertaling:
        return "em-streepje of uitroepteken"
    return ""


def vertaal(client, taal: str, soort: str, bron: dict[str, str], stuk: int = 80,
            maxima: dict[str, int] | None = None) -> dict[str, str]:
    """Alle regels van `bron` in `taal`; wat niet klopt, opnieuw, hoogstens drie keer."""
    klaar: dict[str, str] = {}
    open_ = dict(bron)
    for _ in range(3):
        if not open_:
            break
        sleutels = list(open_)
        delen = [{k: open_[k] for k in sleutels[i:i + stuk]} for i in range(0, len(sleutels), stuk)]
        with ThreadPoolExecutor(4) as pool:
            for deel, uit in zip(delen, pool.map(lambda d: _vraag(client, taal, soort, d), delen)):
                for k in deel:
                    if not fout(deel[k], uit.get(k), (maxima or {}).get(k)):
                        klaar[k] = uit[k].strip()
        open_ = {k: v for k, v in bron.items() if k not in klaar}
    if open_:
        raise SystemExit(f"{taal}: {len(open_)} regels blijven fout, bijvoorbeeld {list(open_)[:5]}")
    return klaar


def _cldr() -> dict:
    return json.loads(CLDR.read_text(encoding="utf-8"))


def datumvorm(voorbeeld: str, maand: str) -> str:
    """De datumvorm uit het voorbeeld van CLDR (28 oktober 2026): de maand, de dag en het jaar als plekhouders."""
    vorm = re.sub(r"[‎‏؜]", "", voorbeeld).replace(maand, "{maand}").replace("2026", "{jaar}")
    return vorm.replace("28", "{dag}")


def teksten(client, talen: list[str]) -> None:
    bron = json.loads((TEKSTEN / "en.json").read_text(encoding="utf-8"))["teksten"]
    gewoon = {k: v for k, v in bron.items() if isinstance(v, str) and k != "datum_vorm"}
    cldr = _cldr()
    for taal in talen:
        uit = vertaal(client, taal, "the fixed texts of the website (menus, buttons, labels, short explanations)", gewoon)
        maanden = cldr[taal]["maanden"]
        uit["maanden"] = maanden
        uit["datum_vorm"] = datumvorm(cldr[taal]["voorbeeld"], maanden[9])
        geordend = {k: uit[k] for k in bron}
        meta = {"taal": taal, "nagelezen": False,
                "herkomst": f"De vaste teksten van het platform (PLAN #34.2be, B79), vertaald door Sonnet 5.5 ({VRAAG}) uit het "
                            "Engels; de maanden en de datumvorm uit CLDR. Nog niet nagelezen door een moedertaallezer; zet "
                            "`nagelezen` op true als dat gebeurd is. Eigen werk, AGPL-3.0.",
                "kernwoorden": _woorden.get(taal, {})}
        (TEKSTEN / f"{taal}.json").write_text(json.dumps({"_meta": meta, "teksten": geordend}, ensure_ascii=False, indent=2)
                                              + "\n", encoding="utf-8")
        print(f"{taal}: {len(geordend)} teksten, ${_kosten['dollar']:.2f} tot nu")


def aanvullen(client, talen: list[str]) -> None:
    """Alleen de vaste teksten die een taal nog niet heeft, in de volgorde van het Engels; wat er al staat, blijft zoals
    het is (PLAN #34.2bp: een nieuwe sleutel zonder de andere 400 opnieuw te vertalen)."""
    bron = json.loads((TEKSTEN / "en.json").read_text(encoding="utf-8"))["teksten"]
    for taal in talen:
        pad = TEKSTEN / f"{taal}.json"
        ruw = pad.read_text(encoding="utf-8")
        d = json.loads(ruw)
        if json.dumps(d, ensure_ascii=False, indent=2) + "\n" != ruw:
            raise SystemExit(f"{taal}: het bestand is met de hand opgemaakt; vul het met de hand aan")
        ontbreekt = {k: v for k, v in bron.items() if k not in d["teksten"] and isinstance(v, str)}
        if not ontbreekt:
            print(f"{taal}: niets te doen")
            continue
        uit = vertaal(client, taal, "the fixed texts of the website (menus, buttons, labels, short explanations)", ontbreekt)
        d["teksten"] = {k: d["teksten"].get(k, uit.get(k)) for k in bron if k in d["teksten"] or k in uit}
        pad.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{taal}: {len(uit)} teksten erbij, ${_kosten['dollar']:.2f} tot nu")


def themas(client, talen: list[str]) -> None:
    lijst = json.loads(THEMAS.read_text(encoding="utf-8"))
    bron: dict[str, str] = {}
    for th in lijst["themas"]:
        bron[f"{th['sleutel']}.naam"] = th["naam"]["en"]
        if isinstance(th.get("omschrijving"), dict) and th["omschrijving"].get("en"):
            bron[f"{th['sleutel']}.omschrijving"] = th["omschrijving"]["en"]
        for o in th.get("onderdelen", []):
            bron[f"{th['sleutel']}/{o['sleutel']}.naam"] = o["naam"]["en"]
    for taal in talen:
        uit = vertaal(client, taal, "the names and short descriptions of themes and topics", bron)
        for th in lijst["themas"]:
            th["naam"][taal] = uit[f"{th['sleutel']}.naam"]
            if f"{th['sleutel']}.omschrijving" in uit:
                th["omschrijving"][taal] = uit[f"{th['sleutel']}.omschrijving"]
            for o in th.get("onderdelen", []):
                o["naam"][taal] = uit[f"{th['sleutel']}/{o['sleutel']}.naam"]
        print(f"{taal}: {len(uit)} namen, ${_kosten['dollar']:.2f} tot nu")
    meta = lijst.setdefault("_meta", {})
    meta["vertaald"] = {t: f"Sonnet 5.5 ({VRAAG}), niet nagelezen (PLAN #34.2be)" for t in NIEUW}
    THEMAS.write_text(json.dumps(lijst, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _toml_tekst(waarde: str, alinea: bool) -> str:
    if alinea:
        assert "'''" not in waarde
        return "'''\n" + waarde.strip("\n") + "'''"
    return json.dumps(waarde, ensure_ascii=False)


def voeg_talen_toe(toml: str, vertalingen: dict[str, dict[str, str]], talen: list[str]) -> str:
    """Zet in een dossier de nieuwe talen achter het Frans: in [naam], [inleiding], [nagelezen] (false) en elke
    [item.titel]. `vertalingen` per tabel ('naam', 'inleiding', 'item.<n>') per taal."""
    regels, uit, tabel, item = toml.split("\n"), [], "", -1
    i = 0
    while i < len(regels):
        regel = regels[i]
        kop = re.match(r"^\[\[?([\w.]+)\]\]?\s*$", regel)
        if kop:
            tabel = kop.group(1)
            if regel.startswith("[[item]]"):
                item += 1
        uit.append(regel)
        if re.match(r"^fr\s*=", regel) and tabel in ("naam", "inleiding", "nagelezen", "item.titel"):
            waarde = regel.split("=", 1)[1].strip()
            for haken in ('"""', "'''"):
                if waarde.startswith(haken) and not (len(waarde) > 3 and waarde.endswith(haken)):
                    while True:                         # een tekst over meer regels: tot de sluitende haken
                        i += 1
                        uit.append(regels[i])
                        if regels[i].rstrip().endswith(haken):
                            break
            for taal in talen:
                if tabel == "nagelezen":
                    uit.append(f"{taal} = false")
                else:
                    sleutel = f"item.{item}" if tabel == "item.titel" else tabel
                    uit.append(f"{taal} = {_toml_tekst(vertalingen[sleutel][taal], tabel == 'inleiding')}")
        i += 1
    return "\n".join(uit)


def dossiers(client, talen: list[str]) -> None:
    for map_ in sorted(p for p in DOSSIERS.iterdir() if (p / "dossier.toml").exists()):
        tekst = (map_ / "dossier.toml").read_text(encoding="utf-8")
        ruw = tomllib.loads(tekst)
        if set(talen) & set(ruw["naam"]):
            print(f"{map_.name}: heeft de talen al")
            continue
        bron = {"naam": ruw["naam"]["en"], "inleiding": ruw["inleiding"]["en"].strip()}
        for n, it in enumerate(ruw.get("item", [])):
            bron[f"item.{n}"] = it["titel"]["en"]
        maxima = {k: (ds.MAX_NAAM if k == "naam" else ds.MAX_ALINEA if k == "inleiding" else ds.MAX_TITEL) for k in bron}
        per_taal = {taal: vertaal(client, taal, "the name, introduction and timeline item titles of a dossier (a name stays under "
                                  f"{ds.MAX_NAAM} characters, an item title under {ds.MAX_TITEL})", bron, maxima=maxima)
                    for taal in talen}
        vertalingen = {k: {taal: per_taal[taal][k] for taal in talen} for k in bron}
        nieuw = voeg_talen_toe(tekst, vertalingen, talen)
        gelezen = tomllib.loads(nieuw)
        for taal in talen:
            assert gelezen["naam"][taal] and gelezen["inleiding"][taal] and gelezen["nagelezen"][taal] is False, taal
            assert all(it["titel"][taal] for it in gelezen.get("item", [])), taal
        (map_ / "dossier.toml").write_text(nieuw, encoding="utf-8")
        print(f"{map_.name}: {len(bron)} teksten in {len(talen)} talen, ${_kosten['dollar']:.2f} tot nu")


def korter(client, talen: list[str]) -> None:
    """Een vertaalde naam of titel van een dossier die langer is dan de grens: Sonnet maakt haar korter, met dezelfde
    betekenis, en ze komt in plaats van de oude in het bestand."""
    for map_ in sorted(p for p in DOSSIERS.iterdir() if (p / "dossier.toml").exists()):
        tekst = (map_ / "dossier.toml").read_text(encoding="utf-8")
        ruw = tomllib.loads(tekst)
        velden = [(ruw["naam"], ds.MAX_NAAM)] + [(it["titel"], ds.MAX_TITEL) for it in ruw.get("item", [])]
        for waarden, maximum in velden:
            for taal in talen:
                oud = waarden.get(taal, "")
                if len(oud) <= maximum:
                    continue
                for _ in range(3):
                    antwoord = client.messages.create(
                        model=MODEL, max_tokens=2000,
                        system=(f"Shorten this {NIEUW[taal][0]} text to at most {maximum - 10} characters. Keep the meaning, the "
                                "names and the facts; never use an em dash or an exclamation mark. Answer with the text only."),
                        messages=[{"role": "user", "content": oud}])
                    nieuw = next(b.text for b in antwoord.content if b.type == "text").strip()
                    if not fout(oud, nieuw, maximum):
                        break
                else:
                    raise SystemExit(f"{map_.name} {taal}: blijft te lang")
                regel = f"{taal} = {json.dumps(oud, ensure_ascii=False)}"
                assert tekst.count(regel) == 1, (map_.name, taal)
                tekst = tekst.replace(regel, f"{taal} = {json.dumps(nieuw, ensure_ascii=False)}")
                print(f"{map_.name} {taal}: {len(oud)} -> {len(nieuw)}")
        tomllib.loads(tekst)
        (map_ / "dossier.toml").write_text(tekst, encoding="utf-8")


def main() -> None:  # pragma: no cover - CLI
    import anthropic

    from doublecheck.varianten import laad_sleutel

    laad_sleutel()
    talen = sys.argv[sys.argv.index("--taal") + 1].split(",") if "--taal" in sys.argv else list(NIEUW)
    client = anthropic.Anthropic(max_retries=6)
    {"teksten": teksten, "aanvullen": aanvullen, "themas": themas, "dossiers": dossiers,
     "korter": korter}[sys.argv[1]](client, talen)
    print(f"samen ${_kosten['dollar']:.2f}")


if __name__ == "__main__":  # pragma: no cover
    main()
