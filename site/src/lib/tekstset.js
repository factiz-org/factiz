// De teksten die de eilanden nodig hebben, uit de woordenlijst van het platform; een richting schrijft geen eigen tekst,
// behalve een paar regels die erbij staan (DESIGN §4h, VOICE).
import { maakT } from './teksten.js';

export function tekstset(extra = {}, taal = 'nl') {
  const t = maakT(taal);
  const sleutels = ['sorteer_kop', 'filters_knop', 'filter_thema', 'filter_alles', 'filter_wis', 'filter_meer_n',
    'start_nieuwste', 'lijst_leeg', 'chip_weg', 'filters_toon', 'held_hint', 'zoek_knop', 'zoek_voor', 'zoek_niets',
    'ingang_kop', 'check_lees', 'bronnen_kop', 'zoek_titel'];
  // een plek als {n} blijft staan: die vult het eiland zelf in
  return { ...Object.fromEntries(sleutels.map((k) => [k, t(k, { n: '{n}', totaal: '{totaal}' })])), ...extra };
}

// De teksten van de suggesties bij elk zoekveld en het zoekvenster (PLAN #34.2ac).
export function zoektekst(taal = 'nl', extra = {}) {
  const t = maakT(taal);
  return {
    titel: t('zoek_label'), hint: t('held_hint'), groep_zoeken: t('palet_zoekvragen'), groep_ingangen: t('palet_paginas'),
    groep_factchecks: t('nav_lijst'), groep_themas: t('nav_themas'), in: t('palet_in'), niets: t('zoek_niets'),
    kiezen: t('palet_kiezen'), openen: t('palet_openen'), aanvullen: t('palet_aanvullen'), privacy: t('zoek_privacy'), ...extra,
  };
}

// De teksten van de lijst met zoeken en filters (`Bibliotheek.jsx`), voor Factchecks en voor een thema (PLAN #34.2bb).
export function bibliotheektekst(taal = 'nl') {
  const t = maakT(taal);
  const plek = { n: '{n}', totaal: '{totaal}' };
  return tekstset({
    lijst_titel: t('lijst_titel'), zoek_label: t('zoek_label'), zoek_deels: t('zoek_deels'), zoek_tip: t('zoek_tip'),
    filters_kop: t('filters_kop'), filter_land: t('filter_land'), filter_redactie: t('filter_redactie'), themas_kop: t('nav_themas'),
    filteren: t('filteren'), sorteer_op: t('sorteer_kop'), wis_alles: t('wis_alles'), toon: t('toon_n', plek), meer_laden: t('meer_laden'),
    laden: t('laden'), getoond: t('getoond', plek), lijst_zoeken: t('lijst_zoeken'), sluiten: t('sluiten'),
    zoek_niets_voor: t('zoek_niets_voor'), zoek_resultaten_voor: t('zoek_resultaten_voor'),
    zoek_alleen_woorden: t('zoek_alleen_woorden'), zoek_niets_klopt: t('zoek_niets_klopt'), zoek: zoektekst(taal),
    nav_dossiers: t('nav_dossiers'), nav_namen: t('nav_namen'), filter_onderdeel: t('filter_onderdeel'),
  }, taal);
}
