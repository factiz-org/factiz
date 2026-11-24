// Een naam die Factiz bewust weglaat (maatregel 2, PLAN #34.2bw, SPECS E9.S8 AC13): het platform geeft haar als
// ⟦naam weggelaten⟧ in de taal van de site (`i18n.gemerkt`); hier wordt dat een sticker in een kleur, geen zwarte balk.
// De naam zelf staat nergens in de pagina, ook niet verstopt: ze zit niet in de uitgave.
const MERK = /\u27e6([^\u27e6\u27e7]{1,60})\u27e7/g;

// De stukken van een tekst: [tekst, weggelaten].
export function stukken(tekst) {
  const uit = [];
  let vanaf = 0;
  for (const m of (tekst ?? '').matchAll(MERK)) {
    if (m.index > vanaf) uit.push([tekst.slice(vanaf, m.index), false]);
    uit.push([m[1], true]);
    vanaf = m.index + m[0].length;
  }
  if (vanaf < (tekst ?? '').length) uit.push([tekst.slice(vanaf), false]);
  return uit;
}
