// Voorgesteld in de taalkiezer (PLAN #34.2bi, DESIGNSYSTEEM: de taalkiezer): de talen die de browser van de bezoeker zelf
// noemt (`navigator.languages`), omgezet naar een taal van de site, zonder de huidige en zonder dubbele, hoogstens `max`.
// Elke variant telt: `de-AT` is Duits, `pt-PT` wijst naar het Portugees van Brazilië en elke `zh` naar traditioneel
// Chinees, de enige vormen die de site heeft. Alleen in de browser; niets wordt bewaard of verstuurd (B78).
export function voorstel(browsertalen, codes, huidig, max = 3) {
  const uit = [];
  for (const tag of browsertalen ?? []) {
    const hoofd = String(tag).toLowerCase().split(/[-_]/)[0];
    if (codes.includes(hoofd) && hoofd !== huidig && !uit.includes(hoofd)) uit.push(hoofd);
    if (uit.length >= max) break;
  }
  return uit;
}
