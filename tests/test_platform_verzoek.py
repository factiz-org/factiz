"""Werk dat de Worker tussen verzoeken deelt (PLAN #34.2bq): een verzoek wacht nooit rechtstreeks op werk dat een ander
verzoek nog doet, want dan breekt Workers het af ("the Workers runtime canceled this request because it detected that your
Worker's code had hung"). Wat af is, wordt gedeeld; wat nog bezig is, deelt alleen hetzelfde verzoek, en een ander kijkt
telkens even of het af is, zodat het niet dubbel gebeurt. In Node is er één soort verzoek en verandert er niets."""

import json
import subprocess
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

PROEF = r"""
import { Voorraad, zetVerzoek } from './src/platform/verzoek.ts';

let wie = 'A';
zetVerzoek(() => wie);
const traag = (ms, w, fout = false) => new Promise((ok, nee) => setTimeout(() => (fout ? nee(new Error(w)) : ok(w)), ms));
const uit = {};

// hetzelfde verzoek deelt wat bezig is; een ander krijgt nooit die belofte, maar wel het resultaat, zonder het werk over te doen
let gemaakt = 0;
const v = new Voorraad();
const a1 = v.haal('k', () => { gemaakt++; return traag(40, 'van A'); });
const a2 = v.haal('k', () => { gemaakt++; return traag(1, 'tweede keer'); });
wie = 'B';
const b = v.haal('k', () => { gemaakt++; return traag(1, 'van B'); });
uit.zelfde_belofte = a1 === a2;
uit.ander_krijgt_andere_belofte = b !== a1;
uit.waarden = await Promise.all([a1, a2, b]);
uit.gemaakt = gemaakt;
wie = 'C';
uit.na_afloop = await v.haal('k', () => { gemaakt++; return traag(1, 'niet nodig'); });
uit.gemaakt_na_afloop = gemaakt;

// mislukt het werk van A, dan doet B het zelf
const w = new Voorraad();
wie = 'A';
const fa = w.haal('x', () => traag(20, 'stuk', true)).catch((e) => `A: ${e.message}`);
wie = 'B';
uit.na_een_fout = await Promise.all([fa, w.haal('x', () => traag(5, 'B deed het zelf'))]);

// komt het werk van A nooit af, dan doet B het na de wachttijd zelf
const nooit = new Voorraad({ wachtrondes: 4, wachtMs: 5 });
wie = 'A';
nooit.haal('y', () => new Promise(() => {}));
wie = 'B';
uit.na_wachten = await nooit.haal('y', () => traag(1, 'zelf gedaan'));

// hoogstens zoveel bewaard, de oudste eerst weg; alles op volgorde van beginnen
const klein = new Voorraad({ max: 2 });
wie = 'A';
for (const k of ['p', 'q', 'r']) await klein.haal(k, () => traag(1, k.toUpperCase()));
uit.bewaard = (await klein.alle()).map(([k]) => k);
let opnieuw = 0;
await klein.haal('p', () => { opnieuw++; return traag(1, 'P'); });
uit.oudste_opnieuw = opnieuw;
process.stdout.write(JSON.stringify(uit));
"""


def _proef() -> dict:
    uit = subprocess.run(["node", "--input-type=module", "-e", PROEF], capture_output=True, text=True, cwd=SITE, timeout=60)
    assert uit.returncode == 0, uit.stderr[-3000:]
    return json.loads(uit.stdout)


def test_another_request_never_waits_on_unfinished_work_but_gets_the_result_without_doing_it_again():
    u = _proef()
    assert u["zelfde_belofte"] is True and u["ander_krijgt_andere_belofte"] is True
    assert u["waarden"] == ["van A", "van A", "van A"] and u["gemaakt"] == 1
    assert u["na_afloop"] == "van A" and u["gemaakt_na_afloop"] == 1


def test_when_the_other_request_fails_or_never_finishes_a_request_does_the_work_itself():
    u = _proef()
    assert u["na_een_fout"] == ["A: stuk", "B deed het zelf"]
    assert u["na_wachten"] == "zelf gedaan"


def test_a_bounded_store_drops_the_oldest_and_lists_in_the_order_work_began():
    u = _proef()
    assert u["bewaard"] == ["q", "r"] and u["oudste_opnieuw"] == 1


def test_every_cache_of_unfinished_work_in_the_platform_goes_through_the_store():
    """Een Map of variabele met een belofte erin, buiten één functie, deelt werk tussen verzoeken: alleen via `Voorraad`."""
    import re
    fout = []
    for pad in sorted((SITE / "src" / "platform").glob("*.ts")) + [SITE / "src" / "lib" / "gegevens-worker.js"]:
        tekst = pad.read_text(encoding="utf-8")
        for m in re.finditer(r"(?:private|let|const)\s+\w+\s*(?::\s*[^=;]*)?=\s*new (?:Weak)?Map<[^>]*Promise", tekst):
            fout.append(f"{pad.name}: {m.group(0)}")
        for m in re.finditer(r"^let \w+: Promise<[^\n]*= null", tekst, re.M):
            fout.append(f"{pad.name}: {m.group(0)}")
    assert fout == []
