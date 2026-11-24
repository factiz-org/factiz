// De tekeningen per thema en per dossier als gegevens (PLAN #34.2ap, #34.2aq; SPECS E9.S22, E9.S23): één bron voor de
// site (`Plaat.jsx` tekent ze als SVG) en voor het deelplaatje (het platform tekent ze met Pillow uit
// `factiz_site/static/platen.json`, uitgeschreven met `npm --prefix site run platen`). Gewone JavaScript, zonder JSX,
// zodat node het bestand zonder bouwstap leest.
//
// Een vorm is een van zes soorten, op een raster van 160 bij 68, het vel op (26, 13); hoogstens drie soorten per tekening:
//   regel {x, y, w, h, o}        een balk zonder woorden
//   blok  {x, y, w, h, o, r}     een vlak met ronde hoeken
//   stip  {x, y, r, o, open}     een punt, of open: een rondje in de kleur van het vel met een rand
//   lijn  {d, o, w, streep}      een lijn langs een pad (M, L, H, V, C, S, alleen absoluut)
//   ring  {x, y, r, o, w, streep} een cirkel als lijn
//   vlak  {d, o}                 een gevuld pad (M, L, C, Z), voor een kaart of een voorwerp (PO 2026-11-19: "Landkaartje van
//                                gaza ... wil je wat voorstellen doen?")
// `o` is de dekking; alleen de vorm die de betekenis draagt staat op 0,8 of meer. Geen woorden, geen vinkje, geen kruis,
// en nooit de bewering zelf (E9.S22 AC3).

const regel = (x, y, w, o = 0.24, h = 3) => ({ v: 'regel', x, y, w, h, o });
const blok = (x, y, w, h, o = 0.16, r = 2) => ({ v: 'blok', x, y, w, h, o, r });
const stip = (x, y, r = 3, o = 0.3, open = false) => ({ v: 'stip', x, y, r, o, open });
const lijn = (d, o = 0.9, w = 1.6, streep = null) => ({ v: 'lijn', d, o, w, streep });
const ring = (x, y, r, o = 0.3, w = 1, streep = null) => ({ v: 'ring', x, y, r, o, w, streep });
const vlak = (d, o = 0.9) => ({ v: 'vlak', d, o });
const reeks = (n) => Array.from({ length: n }, (_, i) => i);
const rond = (x) => Math.round(x * 100) / 100;
// een cirkel als pad (vier kwartbogen), als lijn of als vlak, voor een tekening die al drie soorten vormen heeft
const cirkel = (x, y, r) => {
  const k = rond(r * 0.5523);
  return `M${x + r} ${y} C ${x + r} ${y + k}, ${x + k} ${y + r}, ${x} ${y + r} C ${x - k} ${y + r}, ${x - r} ${y + k}, ${x - r} ${y} `
    + `C ${x - r} ${y - k}, ${x - k} ${y - r}, ${x} ${y - r} C ${x + k} ${y - r}, ${x + r} ${y - k}, ${x + r} ${y} Z`;
};
// een golfje, als teken voor water
const golfje = (x, y, o = 0.3) => lijn(`M${x} ${y} C ${x + 2} ${y - 2}, ${x + 4} ${y - 2}, ${x + 6} ${y} `
  + `C ${x + 8} ${y + 2}, ${x + 10} ${y + 2}, ${x + 12} ${y}`, o, 1.1);
// een rondje als blok, voor een tekening die al drie soorten vormen heeft
const bol = (x, y, r, o) => blok(rond(x - r), rond(y - r), 2 * r, 2 * r, o, r);
// een rechthoek met ronde hoeken als pad, voor een tekening die geen blok meer kan hebben
const kader = (x, y, w, h, r = 3) => `M${x + r} ${y} H${x + w - r} C ${x + w - r / 2} ${y}, ${x + w} ${y + r / 2}, ${x + w} ${y + r} `
  + `V${y + h - r} C ${x + w} ${y + h - r / 2}, ${x + w - r / 2} ${y + h}, ${x + w - r} ${y + h} H${x + r} `
  + `C ${x + r / 2} ${y + h}, ${x} ${y + h - r / 2}, ${x} ${y + h - r} V${y + r} C ${x} ${y + r / 2}, ${x + r / 2} ${y}, ${x + r} ${y} Z`;
// een reeks punten als pad, dicht of open
const veelhoek = (punten, dicht = true) => punten.map(([x, y], i) => `${i ? 'L' : 'M'}${rond(x)} ${rond(y)}`).join(' ')
  + (dicht ? ' Z' : '');

// De kaarten, uit lengte en breedte, elk op een kaartvel (PO 2026-11-19 bij de dossiermap van Epstein: "Dit is de beste,
// want heeft 3 lagen"): achteraan het vel, in het midden het land of de zee, vooraan wat de betekenis draagt.
// Gaza: x = 99 + (lengte - 34,39) * 113,1, y = 16 + (31,596 - breedte) * 132,6 (op 31,4 graden noord is een graad lengte 0,853
// graad breedte); de kust, de grens met Egypte bij Rafah en de oostgrens met haar knikken
const gaza = ([lengte, breedte]) => [99 + (lengte - 34.39) * 113.1, 16 + (31.596 - breedte) * 132.6];
const STROOK = veelhoek([[34.490, 31.596], [34.216, 31.323], [34.267, 31.219], [34.300, 31.265], [34.345, 31.320],
  [34.383, 31.373], [34.420, 31.420], [34.470, 31.460], [34.505, 31.500], [34.540, 31.540], [34.565, 31.580]].map(gaza));
// Oekraïne met de Krim: x = 66 + (lengte - 22) * 3,83, y = 14 + (52,4 - breedte) * 5,76; de frontlijn ruw, van de grens bij
// Koepjansk via Pokrovsk en Orichiv langs de Dnipro naar Cherson, en wat ten oosten ervan bezet is
const OEKRAINE = 'M66.6 35.9 L68.3 33 L74 22.6 L72.1 19.2 L73.7 16.9 L80.6 16.9 L87.1 18.6 L98.6 20.3 L103.5 15.7 L110.4 14.3 '
  + 'L113.5 18 L117.3 23.2 L123.4 25.5 L128 27.8 L135.3 30.1 L133.8 36.5 L128.4 41.6 L128 44.5 L125.4 45.1 L119.6 47.4 '
  + 'L115 49.7 L110.8 49.7 L116 52 L122 54 L121 56 L117 56.6 L112.7 59.5 L110 58.9 L109.6 55.5 L106.2 54.3 L108.5 52.5 '
  + 'L110.4 50.3 L106.2 48.9 L102.8 48 L99.3 48 L97.4 49.8 L95.5 54.3 L92 54.9 L89.7 54 L93.5 50.8 L95.6 48.6 L96.3 45.1 '
  + 'L93.6 39.3 L90.9 38.2 L87.4 36.8 L83.6 37.6 L82.1 39.3 L77.5 40.8 L73.7 39.6 L69.8 39.3 Z';
const FRONT = [[125.7, 28.4], [126.5, 33.6], [124.2, 37.6], [122.7, 40.5], [118.9, 41.6], [114.3, 42.2], [106.6, 47.4], [104.3, 48]];
const BEZET = `${veelhoek([...FRONT, [106.2, 48.9], [110.4, 50.3], [110.8, 49.7], [115, 49.7], [119.6, 47.4], [125.4, 45.1],
  [128, 44.5], [128.4, 41.6], [133.8, 36.5], [135.3, 30.1], [128, 27.8]])} ${veelhoek([[110.8, 49.7], [116, 52], [122, 54],
  [121, 56], [117, 56.6], [112.7, 59.5], [110, 58.9], [109.6, 55.5], [106.2, 54.3], [108.5, 52.5], [110.4, 50.3]])}`;
// de Middellandse Zee zelf als vorm: x = 40 + (lengte + 6) * 2,32, y = 15 + (45,6 - breedte) * 2,94; de noordkust van
// Gibraltar tot Iskenderun en de zuidkust terug, met Sicilië, Sardinië, Corsica, Kreta en Cyprus als lijn erop
const zee = ([lengte, breedte]) => [40 + (lengte + 6) * 2.32, 15 + (45.6 - breedte) * 2.94];
const NOORDKUST = [[-5.6, 36.0], [-4.4, 36.7], [-2.4, 36.8], [-1.0, 37.6], [-0.5, 38.3], [-0.3, 39.5], [0.9, 40.7], [2.2, 41.4],
  [3.3, 42.3], [3.0, 42.7], [3.9, 43.5], [5.4, 43.3], [7.3, 43.7], [8.9, 44.4], [10.3, 43.5], [10.5, 42.9], [11.8, 42.1],
  [13.5, 41.2], [14.2, 40.8], [15.3, 40.0], [16.0, 39.0], [15.65, 38.1], [16.1, 37.9], [17.1, 39.1], [17.2, 40.4], [18.4, 39.8],
  [18.5, 40.15], [17.9, 40.6], [16.9, 41.1], [16.2, 41.9], [14.2, 42.5], [13.5, 43.6], [12.6, 44.1], [12.3, 45.4], [13.8, 45.6],
  [13.9, 44.8], [15.2, 44.1], [16.4, 43.5], [18.1, 42.6], [19.4, 41.3], [19.4, 40.4], [20.7, 39.0], [21.7, 38.2], [21.7, 36.8],
  [22.5, 36.4], [23.2, 36.4], [22.8, 37.6], [23.7, 37.9], [24.0, 37.65], [22.9, 39.3], [22.9, 40.6], [23.8, 40.0], [24.4, 40.9],
  [25.9, 40.85], [26.3, 40.1], [27.1, 38.4], [27.4, 37.0], [28.3, 36.8], [29.1, 36.6], [30.7, 36.9], [32.0, 36.5], [32.8, 36.0],
  [34.6, 36.8], [36.2, 36.6]];
const ZUIDKUST = [[-5.9, 35.8], [-5.3, 35.9], [-3.9, 35.25], [-0.6, 35.7], [3.0, 36.8], [5.1, 36.75], [7.8, 36.9], [9.9, 37.3],
  [11.1, 37.1], [10.6, 35.8], [10.8, 34.7], [10.1, 33.9], [10.9, 33.8], [13.2, 32.9], [15.1, 32.4], [16.6, 31.2], [18.5, 30.4],
  [20.1, 32.1], [22.6, 32.8], [24.0, 32.1], [29.9, 31.2], [32.3, 31.3], [34.4, 31.5], [35.0, 32.8], [35.5, 33.9], [35.8, 35.5],
  [36.2, 36.6]];
const EILANDEN = [
  [[12.4, 38.0], [13.3, 38.2], [15.6, 38.3], [15.1, 37.3], [15.1, 36.7], [14.3, 36.8], [12.5, 37.6]],
  [[8.2, 40.9], [9.6, 41.1], [9.7, 40.1], [9.0, 39.0], [8.4, 39.0], [8.4, 40.0]],
  [[8.6, 42.0], [9.4, 43.0], [9.5, 42.0], [9.2, 41.4], [8.7, 41.6]],
  [[23.5, 35.6], [26.3, 35.3], [26.1, 35.0], [24.0, 35.2]],
  [[32.3, 35.0], [34.6, 35.7], [33.9, 35.1], [32.9, 34.6], [32.4, 34.8]],
];
const ZEE = veelhoek([...NOORDKUST, ...[...ZUIDKUST].reverse()].map(zee));
const LAMPEDUSA = zee([12.6, 35.5]).map(rond);

// het halfrond van een parlement: drie rijen zetels, de rechterkant vol
const zetels = () => [[16, 7], [25, 11], [34, 15]].flatMap(([straal, n]) => reeks(n).map((i) => {
  const hoek = Math.PI - (i * Math.PI) / (n - 1);
  return stip(rond(95 + straal * Math.cos(hoek)), rond(64 - straal * Math.sin(hoek)), 2.4, hoek < Math.PI / 3 ? 0.9 : 0.3);
}));

export const PLATEN = {
  'thema:politics': zetels(),
  'thema:elections': [
    ...[24, 34, 44, 54].flatMap((y, i) => [stip(44, y + 1.5, 2.8, 0.9, i !== 1), regel(51, y, i === 1 ? 30 : 22, i === 1 ? 0.6 : 0.22)]),
    blok(98, 26, 56, 44, 0.14),
    blok(116, 30, 22, 4, 0.9, 1),
  ],
  'thema:world': [
    lijn('M50 48 L96 28', 0.9, 1.8),
    lijn('M96 28 L142 50 M50 48 L142 50', 0.25, 1.2),
    stip(50, 48, 5, 0.3, true), stip(96, 28, 5, 0.3, true), stip(142, 50, 5, 0.3, true),
    regel(40, 62, 46, 0.2),
  ],
  'thema:war': [
    ...reeks(4).flatMap((i) => reeks(3).map((j) => blok(40 + i * 24, 24 + j * 20, 21, 17, (i + j) % 3 === 0 ? 0.28 : 0.12, 1.5))),
    lijn('M88 20 C 84 36, 96 46, 90 60 S 86 70, 92 80', 0.95, 1.8, '3 3'),
  ],
  'thema:crime': [
    ...[24, 32, 40, 48, 56, 64].map((y, i) => regel(40, y, [96, 80, 92, 70, 88, 60][i], 0.2)),
    blok(66, 39, 44, 6, 0.9, 1),
    blok(54, 55, 30, 6, 0.4, 1),
  ],
  'thema:disasters': [
    ...[10, 18, 26, 34, 42].map((r, i) => ring(98, 46, r, rond(0.38 - i * 0.06))),
    stip(98, 46, 4, 0.9),
  ],
  'thema:health': [
    regel(40, 24, 40, 0.3), regel(40, 32, 28, 0.2),
    lijn('M40 50 H78 L84 38 L90 60 L96 28 L102 50 H160', 0.95, 1.8),
    blok(40, 60, 120, 10, 0.1),
  ],
  'thema:science': [
    ...[[44, 60], [52, 54], [58, 58], [66, 48], [74, 50], [82, 42], [88, 46], [96, 36], [104, 38], [112, 30], [120, 33], [128, 26]]
      .map(([x, y]) => stip(x, y, 2.2, 0.35)),
    lijn('M40 62 L134 24', 0.9, 1.6),
  ],
  'thema:economy': [
    ...[12, 18, 15, 26, 36].map((h, i) => blok(44 + i * 20, 62 - h, 13, h, i === 4 ? 0.9 : 0.22, 1.5)),
    regel(40, 64, 110, 0.35, 1.5),
  ],
  'thema:climate': reeks(14).map((i) => blok(40 + i * 8, 24, 7, 40, i === 13 ? 0.9 : rond(0.08 + i * 0.05), 0.5)),
  'thema:migration': [
    lijn('M44 56 C 70 56, 72 32, 98 36 S 130 24, 150 28', 0.5, 1.4, '2 4'),
    stip(44, 56, 3.2, 0.35), stip(98, 36, 3.2, 0.35), stip(150, 28, 4.4, 0.95),
    regel(44, 64, 40, 0.2),
  ],
  'thema:society': reeks(8).flatMap((i) => reeks(4).map((j) => stip(44 + i * 13, 26 + j * 11, 3.4,
    i >= 4 && i <= 5 && j >= 1 && j <= 2 ? 0.9 : 0.2))),
  'thema:people': [
    stip(54, 40, 12, 0.3, true), stip(54, 36, 4, 0.3),
    regel(74, 32, 46, 0.5), regel(74, 40, 32, 0.22),
    blok(74, 49, 24, 6, 0.9, 3),
  ],
  // een erlenmeyer en een petrischaal op een werkblad: het blad, de fles en de schaal, vooraan de vloeistof op volle kleur
  'dossier:biolabs-oekraine': [
    vlak(kader(42, 14, 104, 48, 4), 0.12), vlak(cirkel(126, 46, 13), 0.2),
    lijn('M80 16 H92 M82 16 V27 L68 50 C 66 54, 68 57, 72 57 H100 C 104 57, 106 54, 104 50 L90 27 V16', 0.55, 1.3),
    lijn(`${cirkel(126, 46, 13)} ${cirkel(126, 46, 9)}`, 0.3, 1),
    vlak('M75 39 H97 L104 50 C 106 54, 104 57, 100 57 H72 C 68 57, 66 54, 68 50 Z', 0.95),
    stip(84, 33, 1.8, 0.35), stip(89, 28, 1.4, 0.3), stip(122, 44, 2, 0.35), stip(130, 49, 2.4, 0.35), stip(127, 41, 1.6, 0.35),
  ],
  'dossier:gates-vaccins-chips': reeks(4).flatMap((i) => [
    blok(48 + i * 24, 24, 12, 6, 0.4, 1),
    blok(46 + i * 24, 31, 16, 30, i === 2 ? 0.9 : 0.2, 3),
  ]),
  'dossier:navo-uitbreiding': [
    ring(86, 46, 22, 0.35, 1, '3 3'), ring(94, 46, 36, 0.2, 1, '3 3'),
    ...[[76, 40], [92, 36], [84, 54], [98, 50]].map(([x, y]) => stip(x, y, 3.6, 0.35)),
    stip(128, 40, 4.4, 0.9),
  ],
  'dossier:nazi-oekraine': [
    blok(40, 24, 52, 16, 0.14, 4), regel(47, 30.5, 30, 0.25),
    blok(70, 36, 52, 16, 0.2, 4), regel(77, 42.5, 30, 0.25),
    blok(100, 48, 52, 16, 0.9, 4), regel(107, 54.5, 30, 0.35),
  ],
  // een stembus in een stemhokje: het hokje, de bus, vooraan het biljet in de gleuf op volle kleur
  'dossier:verkiezing-vs-2020': [
    blok(46, 10, 88, 60, 0.12, 3), regel(52, 16, 76, 0.18, 2),
    blok(58, 30, 64, 36, 0.28, 3), blok(55, 26, 70, 6, 0.4, 2), regel(74, 27.5, 32, 0.75, 2.5),
    blok(80, 12, 20, 17, 0.95, 1.5), lijn('M84 17 H96 M84 21 H93', 0.35, 1), blok(76, 40, 28, 10, 0.18, 2),
  ],
  'dossier:zelensky-luxury': [
    blok(62, 20, 44, 52, 0.16, 2),
    ...[28, 35, 42, 49].map((y, i) => regel(68, y, [26, 20, 24, 16][i], 0.3)),
    regel(68, 58, 32, 0.9, 4),
  ],
  'dossier:aardbeving-verkeerde-ramp': [
    blok(40, 24, 54, 36, 0.16, 2),
    lijn('M44 52 L58 40 L68 48 L78 36 L90 52', 0.3, 1.2),
    blok(78, 32, 54, 36, 0.9, 2),
    stip(120, 41, 3, 0.3, true),
  ],
  // Oekraïne op een kaartvel: het vel, het land, het bezette gebied met de Krim, vooraan de frontlijn op volle kleur en Kyiv
  'dossier:oorlog-oekraine-2025-2026': [
    blok(60, 10, 82, 54, 0.14, 3), vlak(OEKRAINE, 0.22), vlak(BEZET, 0.2),
    lijn(veelhoek(FRONT, false), 0.95, 1.7, '3 2'), bol(98.6, 25.2, 2.4, 0.45),
  ],
  // de strook op een kaartvel: het vel, de zee, vooraan de strook op volle kleur met Gaza-stad, Khan Younis en Rafah (PO
  // 2026-11-19: "de gaza strook duidelijker als item nemen, de landkaart van boven dus als basis element")
  'dossier:gaza-oorlog': [
    blok(60, 13, 76, 56, 0.14, 3),
    vlak('M63 13 L112.9 13 L110.3 16 L79.3 52.2 C 72 55, 66 57, 60 58 L60 16 C 60 14.3, 61.3 13, 63 13 Z', 0.2),
    vlak(STROOK, 0.92),
    ...[[34.46, 31.51], [34.30, 31.345], [34.25, 31.29]].map((q) => { const [x, y] = gaza(q); return stip(rond(x), rond(y), 2.2, 0.3, true); }),
  ],
  // een radar in zijn kast: de kast, het ronde scherm met ringen, vooraan de straal en één stip op volle kleur
  'dossier:iran-oorlog': [
    blok(68, 13, 56, 56, 0.14, 6), vlak(cirkel(96, 40, 24), 0.2),
    lijn(`${cirkel(96, 40, 8)} ${cirkel(96, 40, 16)}`, 0.3, 1), lijn('M72 40 H120 M96 16 V64', 0.16, 1),
    vlak('M96 40 L113 23 C 108.5 18.5, 102.4 16, 96 16 Z', 0.18), lijn('M96 40 L113 23', 0.6, 1.4),
    bol(108, 28, 2.6, 0.95), bol(81, 31, 2, 0.35), bol(88, 52, 2, 0.3),
  ],
  // een dossiermap met een vel, regels tekst, twee zwartgemaakte regels en een paperclip (PO 2026-11-19)
  'dossier:epstein-stukken': [
    blok(44, 17, 24, 6, 0.16, 2), blok(44, 21, 76, 46, 0.14, 3), blok(54, 25, 58, 44, 0.2, 2),
    ...[31, 37, 43, 49, 55].map((y, i) => regel(60, y, [44, 40, 46, 32, 42][i], 0.3)),
    regel(60, 35.5, 32, 0.95, 5), regel(60, 47.5, 24, 0.95, 5),
    lijn('M106 20 V32 C 106 35, 102 35, 102 32 V24', 0.5, 1.1),
  ],
  // een spuit en een flesje op een blad: het blad, het flesje en de spuit, vooraan het vaccin op volle kleur
  'dossier:kennedy-vaccins': [
    blok(34, 22, 112, 38, 0.12, 4), blok(120, 18, 14, 30, 0.22, 3), blok(122, 14, 10, 5, 0.32, 1),
    blok(40, 31, 4, 18, 0.3, 1), regel(44, 38.5, 16, 0.3, 3), blok(58, 29, 3, 22, 0.3, 1),
    blok(61, 33, 46, 14, 0.24, 2), blok(80, 35, 27, 10, 0.95, 1),
    lijn('M68 33 V37 M74 33 V37 M80 33 V37 M86 33 V37 M92 33 V37 M98 33 V37', 0.35, 0.8),
    blok(107, 37, 6, 6, 0.3, 1), lijn('M113 40 H127', 0.55, 1.1),
  ],
  // een video die naar iemand wijst: een vlak voor de straat, de telefoon en de mensen, vooraan de video en wie hij aanwijst
  'dossier:migranten-zondebok': [
    blok(74, 16, 82, 50, 0.12, 4), blok(40, 15, 30, 52, 0.22, 5), blok(43, 21, 24, 32, 0.16, 2), vlak('M51 31 L60 37 L51 43 Z', 0.6),
    lijn('M68 37 C 80 37, 88 30, 101 31', 0.4, 1.1, '3 3'),
    ...reeks(5).flatMap((i) => [bol(84 + i * 13, 26, 3, i === 2 ? 0.95 : 0.25), blok(80 + i * 13, 31, 8, 11, i === 2 ? 0.95 : 0.22, 4)]),
    ...reeks(4).flatMap((i) => [bol(90 + i * 13, 46, 3, 0.2), blok(86 + i * 13, 51, 8, 11, 0.18, 4)]),
  ],
  // de Middellandse Zee op een kaartvel: het vel, de zee met de eilanden, vooraan de routes en die van Libië naar Lampedusa op
  // volle kleur (PO 2026-11-19, na het bootje: "die is net te kinderachtig")
  'dossier:migratie-europa': [
    vlak(kader(34, 12, 110, 52, 3), 0.14), vlak(ZEE, 0.22),
    lijn(EILANDEN.map((e) => veelhoek(e.map(zee))).join(' '), 0.45, 0.9),
    lijn(veelhoek([[12.4, 33.0], [12.5, 34.4], [12.6, 35.5]].map(zee), false), 0.95, 1.7, '2.5 2'),
    lijn(veelhoek([[27.2, 38.9], [26.3, 39.2]].map(zee), false), 0.55, 1.3, '2 2'),
    lijn(veelhoek([[-3.9, 35.3], [-3.5, 36.0], [-3.3, 36.7]].map(zee), false), 0.55, 1.3, '2 2'),
    stip(LAMPEDUSA[0], LAMPEDUSA[1], 2, 0.3, true),
  ],
  // het virus onder de microscoop: het ronde beeld, de lijnen naar drie mogelijke herkomsten die open blijven, vooraan het
  // virusdeeltje op volle kleur
  'dossier:herkomst-coronavirus': [
    vlak(cirkel(98, 40, 26), 0.12),
    ...[[52, 24], [144, 26], [60, 58]].flatMap(([x, y]) => [lijn(`M98 40 L${x} ${y}`, 0.3, 1.1, '2 3'), stip(x, y, 3.4, 0.3, true)]),
    ...reeks(10).flatMap((i) => {
      const h = (i * Math.PI) / 5;
      return [lijn(`M${rond(98 + 10 * Math.cos(h))} ${rond(40 + 10 * Math.sin(h))} L${rond(98 + 14 * Math.cos(h))} ${rond(40 + 14 * Math.sin(h))}`, 0.9, 1.3),
        stip(rond(98 + 15 * Math.cos(h)), rond(40 + 15 * Math.sin(h)), 1.6, 0.9)];
    }),
    vlak(cirkel(98, 40, 10), 0.22), lijn(cirkel(98, 40, 10), 0.95, 1.6),
  ],
};

// de uitsnede van het raster per plek: de kaart van een thema (breed), de kaart van een dossier (hoger, ingezoomd op waar de
// tekeningen staan, zodat ze het vak vullen in plaats van bovenin te hangen; PO 2026-11-19: "op de vierkante kaartjes zie je
// de visual maar boven in beeld. Die kan iets meer ingezoomd worden") en de kop
export const UITSNEDE = { kaart: [0, 0, 160, 68], vak: [20, 6, 126, 102], band: [0, 0, 160, 68] };

// de vormen van een dossier, anders die van zijn thema; zonder tekening niets (het veld blijft)
export function vormen(soort, sleutel, thema) {
  return PLATEN[`${soort}:${sleutel}`] ?? (thema ? PLATEN[`thema:${thema}`] : undefined) ?? null;
}
