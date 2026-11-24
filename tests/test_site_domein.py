"""De site op factiz.org (B80, PLAN #34.2bo stap 8): één adres (www stuurt blijvend door), dezelfde beveiligingskoppen
als het platform in Python, en een robots.txt die zoekmachines buiten houdt tot de PO de site opent (#33.9, B73)."""

import json
import re
import subprocess
from pathlib import Path

from factiz_site.app import KOPPEN as PYTHON_KOPPEN

SITE = Path(__file__).resolve().parent.parent / "site"

PROEF = r"""
import { KOPPEN, naarHoofdadres, metKoppen, kopbestand, weigerMethode, securityTxt, SECURITY_VERLOOPT } from './src/lib/koppen.js';
import { GET } from './src/pages/robots.txt.js';

const uit = {};
const www = naarHoofdadres(new URL('https://www.factiz.org/nl/fact-checks/?taal=nl&jaar=2024'));
uit.www = { status: www.status, naar: www.headers.get('location') };
uit.hoofd = naarHoofdadres(new URL('https://factiz.org/nl/'));
uit.lokaal = naarHoofdadres(new URL('http://127.0.0.1:8796/'));
const http = naarHoofdadres(new URL('http://factiz.org/nl/fact-checks/?taal=nl'), 'http');
uit.http_lokaal = naarHoofdadres(new URL('http://factiz.org/nl/'));                 // wrangler dev: geen kop van Cloudflare
uit.http_https = naarHoofdadres(new URL('http://factiz.org/nl/'), 'https');
uit.http = { status: http.status, naar: http.headers.get('location') };
const httpWww = naarHoofdadres(new URL('http://www.factiz.org/'));
uit.http_www = { status: httpWww.status, naar: httpWww.headers.get('location') };
uit.koppen = KOPPEN;
// een pagina die zelf al een kop zet, houdt die; een antwoord uit de cache (onveranderbare koppen) krijgt ze ook
const eigen = metKoppen(new Response('x', { headers: { 'Referrer-Policy': 'no-referrer' } }));
uit.eigen = Object.fromEntries(eigen.headers);
const vast = Response.redirect('https://factiz.org/', 301);
uit.vast = Object.fromEntries(metKoppen(vast).headers);
uit.kopbestand = kopbestand();
uit.methodes = Object.fromEntries(['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'TRACE'].map((m) => {
  const r = weigerMethode(m);
  return [m, r ? [r.status, r.headers.get('allow')] : null];
}));
uit.charset = metKoppen(new Response('<p>x</p>', { headers: { 'content-type': 'text/html' } })).headers.get('content-type');
uit.charset_jpeg = metKoppen(new Response('x', { headers: { 'content-type': 'image/jpeg' } })).headers.get('content-type');
const sec = securityTxt();
uit.security = { soort: sec.headers.get('content-type'), tekst: await sec.text(), verloopt: SECURITY_VERLOOPT };
const robots = GET();
uit.robots = { status: robots.status, soort: robots.headers.get('content-type'), tekst: await robots.text() };
process.stdout.write(JSON.stringify(uit));
"""


def _proef() -> dict:
    uit = subprocess.run(["node", "--input-type=module", "-e", PROEF], capture_output=True, text=True, cwd=SITE, timeout=60)
    assert uit.returncode == 0, uit.stderr[-3000:]
    return json.loads(uit.stdout)


def test_www_sends_every_page_permanently_to_factiz_org_with_its_path_and_question():
    u = _proef()
    assert u["www"] == {"status": 301, "naar": "https://factiz.org/nl/fact-checks/?taal=nl&jaar=2024"}
    assert u["hoofd"] is None and u["lokaal"] is None


def test_every_answer_carries_the_same_security_headers_as_the_python_platform():
    u = _proef()
    # de CSP schrijft Astro zelf, met de hashes van zijn eigen stukjes script (astro.config.mjs)
    verwacht = {k: v for k, v in PYTHON_KOPPEN.items() if k != "Content-Security-Policy"}
    assert u["koppen"] == verwacht
    vast = {k.lower(): v for k, v in verwacht.items()}
    assert {k: u["vast"][k] for k in vast} == vast and u["vast"]["location"] == "https://factiz.org/"
    assert u["eigen"]["referrer-policy"] == "no-referrer"                       # wat een pagina zelf zet, blijft


def test_the_static_files_of_the_worker_get_the_same_headers():
    regels = _proef()["kopbestand"].splitlines()
    assert regels[0] == "/*"
    koppen = dict(re.match(r"^  ([^:]+): (.+)$", r).groups() for r in regels[1:])
    assert koppen == {k: v for k, v in PYTHON_KOPPEN.items() if k != "Content-Security-Policy"}
    voorraad = (SITE / "scripts" / "worker-voorraad.mjs").read_text()
    assert "kopbestand()" in voorraad and "_headers" in voorraad


def test_the_worker_takes_the_memory_of_the_edition_it_reads_not_the_newest_on_disk():
    # 2026-11-23: de routine bouwde 2026-11-23b naast de uitgave die live ging, en de bouw van de Worker nam het nieuwste
    # geheugen op schijf; het geheugen hoort bij de database in wrangler.jsonc
    voorraad = (SITE / "scripts" / "worker-voorraad.mjs").read_text()
    assert "releases[releases.length - 1]" not in voorraad
    assert re.search(r"process\.argv\[2\] \?\? database\.replace\(/\^factiz-/, ''\)", voorraad)


def test_robots_keeps_search_engines_out_like_the_python_platform():
    assert _proef()["robots"] == {"status": 200, "soort": "text/plain; charset=utf-8", "tekst": "User-agent: *\nDisallow: /\n"}


def test_the_worker_answers_on_factiz_org_and_www_and_not_on_workers_dev():
    tekst = re.sub(r"^\s*//.*$", "", (SITE / "wrangler.jsonc").read_text(), flags=re.M)
    config = json.loads(tekst)
    assert config["workers_dev"] is False and config["preview_urls"] is False
    assert config["routes"] == [{"pattern": "factiz.org", "custom_domain": True},
                                {"pattern": "www.factiz.org", "custom_domain": True}]


def test_plain_http_goes_permanently_to_https_and_the_own_computer_is_left_alone():
    u = _proef()
    assert u["http"] == {"status": 301, "naar": "https://factiz.org/nl/fact-checks/?taal=nl"}
    assert u["http_www"] == {"status": 301, "naar": "https://factiz.org/"}
    assert u["hoofd"] is None and u["lokaal"] is None
    # alleen als Cloudflare zegt dat het gewone http was: lokaal geeft wrangler elk verzoek als http door
    assert u["http_lokaal"] is None and u["http_https"] is None


def test_our_own_checking_tools_are_counted_as_robots_never_as_visitors():
    import re
    from doublecheck import uitrol
    from factiz_site import gelijk_worker
    platform = (SITE / "src" / "lib" / "platform.js").read_text(encoding="utf-8")
    robot = re.compile(re.search(r"const ROBOT = /(.+)/i;", platform).group(1), re.IGNORECASE)
    for afzender in (gelijk_worker.AFZENDER, uitrol.AFZENDER):
        assert robot.search(afzender), afzender
    assert not robot.search("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 Chrome/131 Safari/537.36")


def test_only_reading_and_searching_are_allowed_every_other_method_gets_405():
    m = _proef()["methodes"]
    assert m["GET"] is None and m["HEAD"] is None and m["POST"] is None
    for naam in ("PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"):
        assert m[naam] == [405, "GET, HEAD, POST"], naam


def test_a_page_says_its_character_set_in_the_header():
    u = _proef()
    assert u["charset"] == "text/html; charset=utf-8" and u["charset_jpeg"] == "image/jpeg"


def test_security_txt_names_the_contact_and_does_not_expire_within_a_month():
    from datetime import datetime, timedelta, timezone
    s = _proef()["security"]
    regels = dict(r.split(": ", 1) for r in s["tekst"].strip().splitlines())
    assert s["soort"] == "text/plain; charset=utf-8"
    assert regels["Contact"] == "mailto:info@factiz.org" and regels["Canonical"] == "https://factiz.org/.well-known/security.txt"
    verloopt = datetime.fromisoformat(regels["Expires"].replace("Z", "+00:00"))
    assert verloopt - datetime.now(timezone.utc) > timedelta(days=30), "security.txt verloopt binnen een maand: vernieuwen"
    assert verloopt - datetime.now(timezone.utc) < timedelta(days=400)        # RFC 9116: niet verder dan een jaar vooruit
