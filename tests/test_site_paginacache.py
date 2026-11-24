"""De paginacache van de Worker (B80, PLAN #34.2bo stap 8): een pagina die klaar is gaat in de cache van Cloudflare, en
alleen wat niemand zelf intypt (B78). Getoetst in Node met een nagemaakte cache; de echte zit alleen in de Worker."""

import json
import subprocess
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

PROEF = r"""
import { metCache } from './src/lib/paginacache.js';

// een nagemaakte cache zoals caches.default: match en put op het adres van de sleutel
const bewaard = new Map();
const cache = { match: async (k) => bewaard.get(k.url)?.clone() ?? undefined, put: async (k, r) => { bewaard.set(k.url, r); } };
const wachten = [];
const geteld = [];
const omgeving = (versie) => ({ cache, versie, waitUntil: (p) => wachten.push(p), tel: (s, t, r) => geteld.push([s, t, r.headers.get('user-agent')]) });
let gerenderd = 0;
const pagina = (status = 200, soort = 'text/html; charset=utf-8', telling = ['factcheck', 'nl']) => async (locals) => {
  gerenderd++;
  if (telling) locals.telling = telling;
  return new Response(`<p>pagina ${gerenderd}</p>`, { status, headers: { 'content-type': soort } });
};
const vraag = async (adres, { methode = 'GET', ua = 'Mozilla/5.0', versie = 'v1', maak = pagina() } = {}) => {
  const locals = {};
  const r = await metCache(new Request(adres, { method: methode, headers: { 'user-agent': ua } }), locals, () => maak(locals), omgeving(versie));
  await Promise.all(wachten.splice(0));
  return { status: r.status, tekst: await r.text(), cache: r.headers.get('x-factiz-cache'), merk: r.headers.get('x-factiz-tel'),
           browser: r.headers.get('cache-control') };
};
const uit = {};
uit.eerste = await vraag('https://factiz.org/nl/fact-checks/0001a6a32a1c4f18/');
uit.tweede = await vraag('https://factiz.org/nl/fact-checks/0001a6a32a1c4f18/');
uit.robot = await vraag('https://factiz.org/nl/fact-checks/0001a6a32a1c4f18/', { ua: 'Googlebot' });
uit.nieuwe_versie = await vraag('https://factiz.org/nl/fact-checks/0001a6a32a1c4f18/', { versie: 'v2' });
uit.met_vraag_1 = await vraag('https://factiz.org/fact-checks/?taal=nl');
uit.met_vraag_2 = await vraag('https://factiz.org/fact-checks/?taal=nl');
uit.post_1 = await vraag('https://factiz.org/', { methode: 'POST' });
uit.post_2 = await vraag('https://factiz.org/', { methode: 'POST' });
uit.fout_1 = await vraag('https://factiz.org/bestaat-niet/', { maak: pagina(404, 'text/html', ['fout', 'en']) });
uit.fout_2 = await vraag('https://factiz.org/bestaat-niet/', { maak: pagina(404, 'text/html', ['fout', 'en']) });
uit.json_1 = await vraag('https://factiz.org/en/api/archief', { maak: pagina(200, 'application/json', null) });
uit.json_2 = await vraag('https://factiz.org/en/api/archief', { maak: pagina(200, 'application/json', null) });
uit.beeld_1 = await vraag('https://factiz.org/deelbeeld/en/0001a6a32a1c4f18.jpg', { maak: pagina(200, 'image/jpeg', null) });
uit.beeld_2 = await vraag('https://factiz.org/deelbeeld/en/0001a6a32a1c4f18.jpg', { maak: pagina(200, 'image/jpeg', null) });
uit.beeld_v_1 = await vraag('https://factiz.org/deelbeeld/en/0001a6a32a1c4f18.jpg?v=2026-11-16b', { maak: pagina(200, 'image/jpeg', null) });
uit.beeld_v_2 = await vraag('https://factiz.org/deelbeeld/en/0001a6a32a1c4f18.jpg?v=2026-11-16b', { maak: pagina(200, 'image/jpeg', null) });
uit.beeld_raar_2 = await vraag('https://factiz.org/deelbeeld/en/0001a6a32a1c4f18.jpg?v=iets', { maak: pagina(200, 'image/jpeg', null) });
uit.pagina_v_1 = await vraag('https://factiz.org/nl/?v=2026-11-16b');
uit.pagina_v_2 = await vraag('https://factiz.org/nl/?v=2026-11-16b');
const zonder = await metCache(new Request('https://factiz.org/'), {}, async () => new Response('zonder cache'), null);
uit.zonder_cache = await zonder.text();
uit.geteld = geteld;
uit.sleutels = [...bewaard.keys()];
uit.bewaartijd = [...new Set([...bewaard.values()].map((r) => r.headers.get('cache-control')))];
process.stdout.write(JSON.stringify(uit));
"""


def _proef() -> dict:
    uit = subprocess.run(["node", "--input-type=module", "-e", PROEF], capture_output=True, text=True, cwd=SITE, timeout=60)
    assert uit.returncode == 0, uit.stderr[-3000:]
    return json.loads(uit.stdout)


def test_a_finished_page_comes_from_the_cache_the_second_time_and_is_still_counted():
    u = _proef()
    assert u["eerste"]["cache"] == "miss" and u["tweede"]["cache"] == "hit"
    assert u["tweede"]["tekst"] == u["eerste"]["tekst"]                      # niet opnieuw gemaakt
    # een bezoek uit de cache telt met de soort en taal die de pagina toen telde (een pagina die gemaakt wordt, telt
    # zichzelf); een robot apart, op zijn eigen user-agent
    assert [g[:2] for g in u["geteld"]] == [["factcheck", "nl"]] * 2
    assert [g[2] for g in u["geteld"]] == ["Mozilla/5.0", "Googlebot"]
    # het merk voor het tellen gaat nooit naar de bezoeker
    assert all(v["merk"] is None for k, v in u.items() if isinstance(v, dict))


def test_a_new_deploy_starts_with_an_empty_cache():
    u = _proef()
    assert u["nieuwe_versie"]["cache"] == "miss" and u["nieuwe_versie"]["tekst"] != u["eerste"]["tekst"]
    assert all("v1" in s or "v2" in s for s in u["sleutels"])


def test_nothing_a_visitor_sends_and_no_error_or_data_goes_into_the_cache():
    u = _proef()
    for naam in ("met_vraag", "post", "fout", "json"):
        assert u[f"{naam}_2"]["cache"] is None, naam                        # langs de cache, elke keer opnieuw
        assert u[f"{naam}_2"]["tekst"] != u[f"{naam}_1"]["tekst"], naam
    assert not any("?" in s for s in u["sleutels"] if "/deelbeeld/" not in s)
    assert u["beeld_2"]["cache"] == "hit"                                     # een deelplaatje wel


def test_without_a_cache_it_simply_renders_as_in_node():
    assert _proef()["zonder_cache"] == "zonder cache"


def test_the_browser_keeps_a_page_five_minutes_while_the_worker_keeps_it_for_the_whole_deploy():
    u = _proef()
    # na een nieuwe uitgave ziet een terugkerende bezoeker binnen vijf minuten de nieuwe pagina (#34.2bq)
    assert u["eerste"]["browser"] == u["tweede"]["browser"] == "public, max-age=300"
    assert u["beeld_2"]["browser"] == "public, max-age=86400"
    assert u["bewaartijd"] == ["public, max-age=604800"]


def test_a_share_image_with_the_release_in_its_address_comes_from_the_cache_but_nothing_else_with_a_question():
    u = _proef()
    assert u["beeld_v_1"]["cache"] == "miss" and u["beeld_v_2"]["cache"] == "hit"
    assert u["beeld_raar_2"]["cache"] is None                                # alleen de vorm van een uitgave
    assert u["pagina_v_2"]["cache"] is None and u["pagina_v_2"]["tekst"] != u["pagina_v_1"]["tekst"]   # een pagina nooit
    assert [s for s in u["sleutels"] if "?" in s] == [
        "https://factiz.org/__pagina/v1/deelbeeld/en/0001a6a32a1c4f18.jpg?v=2026-11-16b"]
