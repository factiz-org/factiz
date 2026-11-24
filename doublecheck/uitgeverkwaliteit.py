"""Uitgevers waarvan de eigen claims op elkaar lijken (PLAN.md #17.1).

Ontdekt via de vetosteekproef: Koreaans en Amhaars leverden 44% van alle
vetoblokkades uit 0,3% van het corpus (BENCHMARK.md §42c). De oorzaak zat niet
in de taal — die halen de onderscheidingsmaat ruim — maar bij de uitgever.

**De staart, niet de mediaan.** Clustering wordt gedreven door paren bóven de
drempel. Een uitgever kan een gewone mediaan hebben terwijl enkele procenten van
zijn paren tegen elkaar aan liggen; de mediaan ziet dat niet. Over 149 uitgevers
is de mediaan van deze maat 0,0000% en p90 0,08% — de uitschieters zitten
honderden malen daarboven (§43).

De maat vindt twee verschillende dingen, en dat onderscheid is inhoudelijk en
niet met een getal te maken:

- **rommel** — markup die geen factcheck is. `Stancu Print` publiceert claims als
  "Google,Yandex,Bing", `FactStream` publiceert "asdfgsahgsagasr" en "This is a
  sample claim in English for testing purposes". Iedereen mag ClaimReview
  publiceren en niemand controleert het (§43b);
- **sjabloon** — echte factchecks met een huisstijl die de embedding overheerst.
  Koreaanse koppen eindigen stelselmatig op "…확인해보니"; de vorm domineert de
  bewering.

Alleen de eerste categorie wordt geweerd. De tweede is echt materiaal en hoort
in de index; dat die uitgever slecht clustert is een cluster-probleem, geen reden
om zijn checks weg te gooien.
"""

from __future__ import annotations

import numpy as np

_MIN_CLAIMS = 5

# Gemeten op 2026-08-30; herbaar met `python -m doublecheck.uitgeverkwaliteit`.
# Aandeel eigen paren boven de clusterdrempel, tegen een mediaan van 0,0000%:
#
#   Stancu Print   28,52%   claims als "Google,Yandex,Bing" — SEO-markup
#   FactStream      1,13%   "asdfgsahgsagasr", "Something", testdata
#
# Bewust op naam en niet op een drempel: de maat vindt óók echte uitgevers met
# een sjabloonmatige huisstijl (JTBC 2,37%), en die horen wél in de index.
#
# Toegevoegd 2026-10-11 (#25.19), gevonden met de meting onder bge-m3: een
# webwinkelnetwerk (halfrain.com, coreyz.com) dat licentieverkoop voor Windows
# Server en klantrecensies als ClaimReview publiceert, onder zes namen. Onder
# MiniLM viel het niet op; bge-m3 zette HalfRain bovenaan (0,92%).
GEWEERDE_UITGEVERS = frozenset({
    "Stancu Print", "FactStream",
    "HalfRain eStore LLC", "HalfRain eStore", "HRC", "HRC: Attribution project",
    "GarbageFile ORG", "CoreYZ Network",
})


def zelfgelijkenis(vectoren, drempel: float) -> float | None:
    """Aandeel eigen paren boven `drempel`; `None` bij te weinig materiaal."""
    matrix = np.asarray(vectoren, dtype=np.float32)
    if len(matrix) < _MIN_CLAIMS:
        return None
    gelijkenis = matrix @ matrix.T
    boven = gelijkenis[np.triu_indices(len(matrix), k=1)]
    return float((boven >= drempel).mean())


# Hosts waarvan alle ClaimReview proefinvoer of een kopie is (#25.19 b).
# factstream.co was de app van het Duke Reporters' Lab: "This is a test",
# "Testing push notifications", en PolitiFact-kopieën met de verkeerde claim
# eraan. Weren op naam ("FactStream") lekte, want dezelfde proefinvoer staat er
# onder "Someone", "SDomeone" en "FactStream test". Subdomeinen tellen mee
# (biffud-dev.factstream.co).
#
# tripatourium.com (2026-10-13, BENCHMARK §95): een webwinkel waarvan de
# klantrecensies als ClaimReview in de feed staan, onder "Etsy", "etsy" en
# "eBay". De stiltetoets vond er een `matched` mee op een gewone recensie.
#
# Bij het nalopen daarna (PO 2026-10-13: "haal ze er allemaal uit"): ook
# geen factchecks, maar ClaimReview-opmaak op recensies (YotPo op
# dufranewatches.com, een kattenfokker), biografieën (modelpeeps.com),
# zelfreclame (een SEO-bureau, een SEO-blog), blogbeweringen (een apotheek,
# een therapiecentrum, een veganistische site) en eigen nieuws van twee Thaise
# lokale sites, die er ook onder andere spellingen van hun naam staan.
#
# Bij de trekkers van #25.26 (BENCHMARK §99; PO 2026-10-13): recensies van een
# casino-app, twee dakdekkers, een metaalbedrijf en drie winkels; vier
# persoonlijke sites (van samszo.univ-paris8.fr alleen die ene server); een
# gezondheidsblog dat zich "Pubmed" noemt; een stichting die de eigen
# artikelen "scientifically sound" noemt; en een proefsite ("This is the
# claim", oordeel "And the rating").
GEWEERDE_HOSTS = frozenset({
    "factstream.co", "tripatourium.com",
    "modelpeeps.com", "emporiumdigital.online", "osochicragdolls.co.uk", "dufranewatches.com",
    "nutricionyfarmacia.com", "centresukha.com", "vegnsocial.com", "pro100blogger.com",
    "songkhlatoday.com", "tratonline.info",
    "app-live567.com", "americanroofingsolutions.org", "roofingrepairsmanchester.co.uk", "metal2000.fr",
    "dienmayminhphuong.com", "giatotqua.vn", "shizenhouse.com", "davidbsantos.com", "worldchatlink.com",
    "imstilljosh.com", "samszo.univ-paris8.fr", "biozdrowy.pl", "fatherhoodchannel.com", "fct.sens3.com",
})


def is_geweerd(uitgever: str | None) -> bool:
    return (uitgever or "").strip() in GEWEERDE_UITGEVERS


def is_geweerde_host(url: str | None) -> bool:
    """Op host, met subdomeinen: de hosts hierboven, en wat bij het nalopen
    van de witte lijst rommel bleek (`geweerd` in uitgevers.json, #25.29)."""
    from doublecheck.evidence import _host
    from doublecheck.uitgevers import load_geweerd

    host = _host(url or "") or ""
    geweerd = GEWEERDE_HOSTS | frozenset(load_geweerd())
    # De host zelf of een domein erboven: gelijk aan `host == h or
    # host.endswith("." + h)`, maar zonder elke check langs alle hosts.
    delen = host.split(".")
    return any(".".join(delen[i:]) in geweerd for i in range(len(delen)))


def vectoren_per_uitgever(conn, model_version: str, register=None) -> tuple[dict[str, list], dict[str, str]]:
    """De claimvectoren per uitgever, uitsluitend van `model_version` (DR6).

    Na een modelwissel staan oude en nieuwe vingerafdrukken naast elkaar
    (#25.14c); de meting rekent alleen met het model dat nu draait. De
    uitgever is de redactie van de host (#25.19 b): de feed zet soms de
    claimant als uitgever, en "Donald Trump" werd zo een uitgever met 40
    claims. Een host buiten het register houdt de naam uit de feed.
    """
    from doublecheck.evidence import _host
    from doublecheck.uitgevers import load_hosts

    if register is None:
        register = load_hosts()
    per: dict[str, list] = {}
    taal_van: dict[str, str] = {}
    for uitgever, url, taal, payload in conn.execute(
        "SELECT f.publisher, f.url, c.language, fp.payload"
        " FROM claim c JOIN factcheck f ON f.claim_id = c.claim_id"
        " JOIN fingerprint fp ON fp.claim_id = c.claim_id AND fp.kind = 'text'"
        " AND fp.model_version = ?", (model_version,)
    ):
        uitgever = register.get(_host(url) or "", uitgever)
        per.setdefault(uitgever, []).append(np.frombuffer(payload, dtype=np.float32))
        taal_van[uitgever] = taal
    return per, taal_van


def main() -> None:
    """Meet de zelfgelijkenis van élke uitgever (#17.1).

    Bestaat om dezelfde reden als de taalmeting: een lijst die je kunt hermeten
    blijft kloppen, een lijst die je moet onthouden niet.
    """
    import argparse
    import random
    import sqlite3

    parser = argparse.ArgumentParser(
        description="Doublecheck: welke uitgevers lijken op zichzelf?"
    )
    parser.add_argument("--db", default="doublecheck.db")
    parser.add_argument("--drempel", type=float, default=None,
                        help="clusterdrempel; standaard die uit config")
    parser.add_argument("--minimum", type=int, default=40,
                        help="uitgevers met minder claims overslaan")
    args = parser.parse_args()

    if args.drempel is None:
        from doublecheck.config import load_config

        args.drempel = load_config().thresholds.cluster_same

    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    from doublecheck.config import load_config

    per, taal_van = vectoren_per_uitgever(conn, load_config().model_versions.text_embedding)

    rng = random.Random(3)
    uitkomsten = []
    for uitgever, vectoren in per.items():
        if len(vectoren) < args.minimum:
            continue
        steek = np.vstack(rng.sample(vectoren, min(200, len(vectoren))))
        aandeel = zelfgelijkenis(steek, args.drempel)
        if aandeel is not None:
            uitkomsten.append((aandeel, uitgever, len(vectoren), taal_van[uitgever]))

    uitkomsten.sort(reverse=True)
    aandelen = [a for a, *_ in uitkomsten]
    print(f"{len(uitkomsten)} uitgevers met >= {args.minimum} claims,"
          f" drempel {args.drempel}")
    print(f"mediaan {np.median(aandelen):.4%} · p90 {np.percentile(aandelen, 90):.4%}")
    print()
    print(f"{'aandeel':>9}  {'claims':>7}  {'taal':<5} uitgever")
    for aandeel, uitgever, aantal, taal in uitkomsten[:20]:
        merk = "  GEWEERD" if is_geweerd(uitgever) else ""
        print(f"{aandeel:>9.2%}  {aantal:>7}  {taal:<5} {uitgever[:40]}{merk}")
    print()
    print("Hoog betekent níét automatisch weren: de maat vindt zowel rommel als")
    print("echte uitgevers met een sjabloonmatige huisstijl. Lees de claims.")
    conn.close()


if __name__ == "__main__":
    main()
