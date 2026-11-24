// In plaats van `react-style-singleton` (PLAN #34.2ad): dezelfde drie functies, maar de opmaak gaat in een stylesheet
// die het script zelf bouwt (`CSSStyleSheet`, `adoptedStyleSheets`), niet in een `<style>`-element. Radix gebruikt het
// pakket om de pagina achter een venster vast te zetten; zijn `<style>`-element weigert de opmaakregel van de site (B75),
// omdat het met de breedte van de schuifbalk verandert en dus geen vaste hash heeft. Een stylesheet uit het script valt
// niet onder die regel, en het script komt van de eigen site. Een browser zonder `adoptedStyleSheets` zet de pagina niet
// vast; het venster werkt daar gewoon. De bouw wijst het pakket hierheen (`astro.config.mjs`).
import { useEffect } from 'react';

function kan() {
  return typeof document !== 'undefined' && typeof CSSStyleSheet !== 'undefined' && 'adoptedStyleSheets' in document;
}

// Eén blad voor alle gebruikers tegelijk: erbij bij de eerste, weg bij de laatste (zoals het pakket).
export function stylesheetSingleton() {
  let teller = 0;
  let blad = null;
  return {
    add(opmaak) {
      if (teller === 0 && kan()) {
        try {
          blad = new CSSStyleSheet();
          blad.replaceSync(opmaak);
          document.adoptedStyleSheets = [...document.adoptedStyleSheets, blad];
        } catch {
          blad = null;
        }
      }
      teller += 1;
    },
    remove() {
      teller -= 1;
      if (!teller && blad) {
        document.adoptedStyleSheets = document.adoptedStyleSheets.filter((b) => b !== blad);
        blad = null;
      }
    },
  };
}

export function styleHookSingleton() {
  const blad = stylesheetSingleton();
  return (opmaak, veranderlijk) => {
    useEffect(() => {
      blad.add(opmaak);
      return () => blad.remove();
    }, [opmaak && veranderlijk]);
  };
}

export function styleSingleton() {
  const gebruik = styleHookSingleton();
  return function Blad({ styles, dynamic }) {
    gebruik(styles, dynamic);
    return null;
  };
}
