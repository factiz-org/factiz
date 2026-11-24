# Herkomst van de beelden (PLAN #23.14, DESIGN §4h)

Gemaakt met `python -m doublecheck.velden`, script velden-v1, op 2026-10-27.
Geen foto, geen beeldmodel, geen download, geen licentie: lichtstrepen, vervaagd en met
filmkorrel, uit een vaste seed. Hetzelfde commando geeft hetzelfde beeld, en witte tekst
haalt in elke tekstzone zijn contrast na de schaduwlaag van de pagina (`tests/test_velden.py`).

- `corpus.webp`: seed 1, 2000×900, 133 KB; bovenaan de homepage; een uitsnede is de afbeelding bij delen; wit in de tekstzones: balk 16,0:1, kop 15,6:1, tekst 12,6:1.
- `delen.jpg`: uitsnede van corpus, 1200×630, 105 KB, JPEG; de afbeelding bij delen (Open Graph), zonder tekst.
- `nacht.webp`: seed 3, 2000×900, 144 KB; de voet van elke pagina; wit in de tekstzones: kop 13,9:1, tekst 13,9:1, kaart 8,5:1.
- `groen.webp`: seed 11, 2000×600, 100 KB; de band bovenaan de andere pagina's en op try.factiz.org; wit in de tekstzones: balk 12,7:1, kop 6,5:1, tekst 10,1:1.
- `hemel.webp`: seed 5, 900×1125, 95 KB; de kaart Check a claim; wit in de tekstzones: kop 3,2:1, tekst 5,9:1.
- `olijf.webp`: seed 8, 900×1125, 105 KB; de kaart Ask a question; wit in de tekstzones: kop 4,1:1, tekst 6,9:1.
- `leisteen.webp`: seed 21, 900×1125, 97 KB; de kaart The numbers en de blog; wit in de tekstzones: kop 6,6:1, tekst 14,1:1.

Corpus is getekend uit de stand van de database op 2026-10-27: 109.558 checks in de index,
in 47 taalcodes. 98.396 checks tekenen een spoor, één per taal;
niet getekend: 9.789 zonder datum, 18 van vóór 2015, 1.355 zonder vastgestelde taal (und).
Bijschrift: "Each streak is one language, 2015 to 2026. The brighter, the more fact-checks that month."
