"""De stand voor het openbare repo (PLAN #34.2bl, PO 2026-11-24: "Ja, schone start met een nieuw openbaar repo").

Het lab blijft het repo waarin gewerkt wordt, met de hele geschiedenis; het openbare repo krijgt een stand daarvan zonder
wat intern is. `python -m doublecheck.openbaar maken [--van <ref>]` bouwt uit een commit van het lab een boom en zet die
als commit op de branch `openbaar`, met Factiz als auteur en zonder co-auteurregel; de eerste commit heeft geen ouder.
De werkmap verandert niet, en pushen doet het niet: dat gaat alleen met een ja van de PO.

Niet in die boom (keuzes van de PO, 2026-11-24):
- `docs/voorstellen/`, `docs/pers/` en `docs/HANDOFF.md`: mailconcepten, prijzen, outreach;
- elke eigen check die nog niet gepubliceerd is: `content/redactie/<sleutel>/`;
- de beelden van posts, `factiz_site/static/redactie/`: wat in git staat, blijft in elke kopie staan, ook als een check
  later wordt ingetrokken; de site haalt ze uit het lab;
- de opmerkingen van de PO in de duels en de kaartenbak, en de tekst van factchecks die we zelf van de sites van
  redacties lazen (de citaten uit hun oordelen, de koppen van AFP): alleen hun id of link blijft (`VELDEN_WEG`).

Een stand gaat alleen door zonder thuismap (`/Users/<naam>/`), zonder het adres uit `git config user.email`, zonder een
waarde uit `.env` en zonder een regel uit `data/openbaar/weiger.txt` (buiten git); anders weigert het, met de paden maar
nooit met wat er gevonden is.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

WORTEL = Path(__file__).resolve().parent.parent
BRANCH = "openbaar"
AUTEUR = ("Factiz", "info@factiz.org")
UIT = ("docs/voorstellen/", "docs/pers/", "docs/HANDOFF.md", "factiz_site/static/redactie/")
GEPUBLICEERD = "gepubliceerd"
ZELF_GELEZEN = "zonder de tekst van de factchecks die Factiz zelf van de sites van redacties las; alleen hun id of link"
VELDEN_WEG = (
    ("docs/steekproeven/duel-*.json", ("opmerking",), "zonder de opmerkingen van de PO"),
    ("docs/steekproeven/poproef-*.json", ("opmerking",), "zonder de opmerkingen van de PO"),
    ("docs/steekproeven/32.38-oordelen.json", ("reden",), ZELF_GELEZEN),
    ("docs/steekproeven/32.38-nakijken.json", ("reden",), ZELF_GELEZEN),
    ("docs/steekproeven/32.38-nakijken-po.json", ("notitie",), ZELF_GELEZEN + ", en zonder de notities van de PO"),
    ("docs/steekproeven/37.0-maatstaf.json", ("titel",), ZELF_GELEZEN),
)
THUISMAP = re.compile(rb"/Users/(?!you/|Shared/)[A-Za-z0-9._-]+/")
WEIGERLIJST = Path("data") / "openbaar" / "weiger.txt"
EERSTE_BERICHT = ("First public version of Factiz\n\nFactiz (factiz.org) is a free archive of fact-checks. This repository "
                  "starts here; the lab that came before it keeps its own history.\n")


class Geweigerd(Exception):
    """De stand bevat iets wat niet openbaar mag."""


def _git(wortel, *args, invoer=None, env=None, check=True):
    uit = subprocess.run(["git", "-C", str(wortel), *args], input=invoer, capture_output=True, check=False,
                         env={**os.environ, **(env or {})})
    if check and uit.returncode:
        raise RuntimeError(f"git {args[0]}: {uit.stderr.decode(errors='replace').strip()}")
    return uit


class _Blobs:
    """Leest blobs via één `git cat-file --batch`."""

    def __init__(self, wortel):
        self.proces = subprocess.Popen(["git", "-C", str(wortel), "cat-file", "--batch"], stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE)

    def lees(self, sha):
        self.proces.stdin.write(sha.encode() + b"\n")
        self.proces.stdin.flush()
        kop = self.proces.stdout.readline().split()
        inhoud = self.proces.stdout.read(int(kop[2]))
        self.proces.stdout.read(1)
        return inhoud

    def sluit(self):
        self.proces.stdin.close()
        self.proces.wait()


def _boom(wortel, ref):
    rijen = _git(wortel, "ls-tree", "-r", "-z", "--full-tree", ref).stdout.split(b"\0")
    for rij in filter(None, rijen):
        kop, pad = rij.split(b"\t", 1)
        modus, soort, sha = kop.decode().split()
        yield modus, soort, sha, pad.decode()


def _concepten(boom, blobs):
    """De sleutels van de eigen checks die nog niet gepubliceerd zijn."""
    uit = set()
    for _, _, sha, pad in boom:
        deel = pad.split("/")
        if len(deel) == 4 and deel[:2] == ["content", "redactie"] and deel[3] == "check.toml":
            status = tomllib.loads(blobs.lees(sha).decode()).get("status")
            if status != GEPUBLICEERD:
                uit.add(deel[2])
    return uit


def _zonder_velden(x, velden):
    if isinstance(x, dict):
        return {k: _zonder_velden(v, velden) for k, v in x.items() if k not in velden}
    if isinstance(x, list):
        return [_zonder_velden(v, velden) for v in x]
    return x


def _ontdaan(inhoud, velden, zin):
    data = json.loads(inhoud)
    kaal = _zonder_velden(data, set(velden))
    if kaal == data:
        return None
    if isinstance(kaal.get("toelichting"), str):
        kaal["toelichting"] = kaal["toelichting"].rstrip() + f" In het openbare repo {zin}."
    tekst = json.dumps(kaal, ensure_ascii=False, indent=1)
    return (tekst + ("\n" if inhoud.endswith(b"\n") else "")).encode()


def _verboden(wortel):
    """Wat nergens in de stand mag staan, als (soort, bytes, hoofdletters negeren)."""
    uit = []
    adres = _git(wortel, "config", "user.email", check=False).stdout.decode().strip()
    if adres:
        uit.append(("het eigen e-mailadres", adres.encode(), True))
    lijst = Path(wortel) / WEIGERLIJST
    if lijst.exists():
        for regel in lijst.read_text().splitlines():
            if regel.strip() and not regel.lstrip().startswith("#"):
                uit.append(("een regel uit de weigerlijst", regel.strip().encode(), True))
    env = Path(wortel) / ".env"
    if env.exists():
        for regel in env.read_text().splitlines():
            sleutel, _, waarde = regel.partition("=")
            waarde = waarde.strip().strip("'\"")
            if sleutel.strip() and not sleutel.lstrip().startswith("#") and len(waarde) >= 16:
                uit.append(("een waarde uit .env", waarde.encode(), False))
    return uit


def _controleer(stand, blobs, verboden):
    fouten = []
    for modus, soort, sha, pad, inhoud in stand:
        if soort != "blob" or modus == "120000":
            continue
        data = inhoud if inhoud is not None else blobs.lees(sha)
        klein = data.lower()
        if THUISMAP.search(data):
            fouten.append(f"{pad}: een pad naar een thuismap")
        for naam, waarde, geen_hoofd in verboden:
            if (waarde.lower() in klein) if geen_hoofd else (waarde in data):
                fouten.append(f"{pad}: {naam}")
    if fouten:
        raise Geweigerd("niet openbaar:\n  " + "\n  ".join(fouten[:40]) + (f"\n  en {len(fouten) - 40} meer"
                                                                             if len(fouten) > 40 else ""))


def bouwen(wortel=WORTEL, van="HEAD"):
    """De boom voor het openbare repo als lijst van (modus, soort, sha, pad, nieuwe inhoud of None), en wat eruit ging."""
    blobs = _Blobs(wortel)
    try:
        boom = list(_boom(wortel, van))
        concepten = _concepten(boom, blobs)
        stand, weg, ontdaan = [], {}, []
        for modus, soort, sha, pad in boom:
            reden = next((u for u in UIT if pad == u or pad.startswith(u)), None)
            deel = pad.split("/")
            if reden is None and deel[:2] == ["content", "redactie"] and len(deel) > 3 and deel[2] in concepten:
                reden = "content/redactie/<niet gepubliceerd>/"
            if reden:
                weg[reden] = weg.get(reden, 0) + 1
                continue
            inhoud = None
            for patroon, velden, zin in VELDEN_WEG:
                if fnmatch.fnmatch(pad, patroon):
                    inhoud = _ontdaan(blobs.lees(sha), velden, zin)
                    if inhoud is not None:
                        ontdaan.append(pad)
                    break
            stand.append((modus, soort, sha, pad, inhoud))
        _controleer(stand, blobs, _verboden(wortel))
        return stand, {"weg": weg, "concepten": sorted(concepten), "ontdaan": ontdaan}
    finally:
        blobs.sluit()


def maken(wortel=WORTEL, van="HEAD", bericht=None, stand=None):
    """Zet de stand van `van` als commit op de branch `openbaar`; None als er niets veranderde."""
    if stand is None:
        stand, _ = bouwen(wortel, van)
    rijen = []
    for modus, soort, sha, pad, inhoud in stand:
        if inhoud is not None:
            sha = _git(wortel, "hash-object", "-w", "--stdin", invoer=inhoud).stdout.decode().strip()
        rijen.append(f"{modus} {sha}\t{pad}".encode())
    with tempfile.TemporaryDirectory() as tmp:
        index = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
        _git(wortel, "update-index", "--add", "-z", "--index-info", invoer=b"\0".join(rijen) + b"\0", env=index)
        boom = _git(wortel, "write-tree", env=index).stdout.decode().strip()
    ouder = _git(wortel, "rev-parse", "--verify", "-q", f"refs/heads/{BRANCH}", check=False).stdout.decode().strip()
    if ouder and _git(wortel, "rev-parse", f"{ouder}^{{tree}}").stdout.decode().strip() == boom:
        return None
    naam, adres = AUTEUR
    env = {"GIT_AUTHOR_NAME": naam, "GIT_AUTHOR_EMAIL": adres, "GIT_COMMITTER_NAME": naam, "GIT_COMMITTER_EMAIL": adres}
    tekst = bericht or (EERSTE_BERICHT if not ouder else "Update from the lab\n")
    commit = _git(wortel, "commit-tree", boom, *(["-p", ouder] if ouder else []), invoer=tekst.encode(),
                  env=env).stdout.decode().strip()
    _git(wortel, "update-ref", f"refs/heads/{BRANCH}", commit, *([ouder] if ouder else []))
    return commit


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m doublecheck.openbaar", description=__doc__.split("\n\n")[0])
    p.add_argument("stap", choices=["bouwen", "maken"], help="bouwen: alleen nakijken en tellen; maken: ook de commit")
    p.add_argument("--van", default="HEAD", help="de commit van het lab (standaard HEAD)")
    p.add_argument("--wortel", default=str(WORTEL), help="het repo van het lab, met .env en data/")
    p.add_argument("--bericht", help="het commitbericht")
    a = p.parse_args(argv)
    try:
        stand, telling = bouwen(a.wortel, a.van)
    except Geweigerd as fout:
        print(f"geweigerd, {fout}", file=sys.stderr)
        return 1
    print(f"{len(stand)} bestanden; weg: " + ", ".join(f"{k} {v}" for k, v in sorted(telling["weg"].items())))
    print(f"niet gepubliceerde checks: {len(telling['concepten'])}; velden weggehaald in: {len(telling['ontdaan'])}")
    for pad in telling["ontdaan"]:
        print(f"  {pad}")
    if a.stap == "maken":
        commit = maken(a.wortel, a.van, a.bericht, stand)
        print(f"branch {BRANCH}: {commit}" if commit else f"branch {BRANCH}: niets nieuw")
    return 0


if __name__ == "__main__":
    sys.exit(main())
