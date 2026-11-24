// Licht, donker of systeem (PLAN #34.2c, DESIGNSYSTEEM §6). Een keuze voor licht of donker onthoudt de browser van de
// bezoeker zelf, onder één sleutel; ze gaat nooit naar de server, en "systeem" wist haar. Dit stukje staat in de kop van
// elke pagina en zet de keuze vóór het tekenen, zodat de pagina niet eerst in de verkeerde kleur verschijnt. De hash ervan
// staat in de beveiligingsregel (astro.config.mjs).
export const SLEUTEL = 'factiz-weergave';
export const KOPSCRIPT =
  `try{var w=localStorage.getItem('${SLEUTEL}');if(w==='licht'||w==='donker')document.documentElement.dataset.weergave=w}catch(e){}`;
