// De versie van een bestand van het platform in zijn adres (?v=…), uit zijn inhoud bij het bouwen. Een nieuwe inhoud is
// een nieuw adres, dus een browser houdt nooit een oude versie vast, ook geen doorverwijzing die hij ooit onthield
// (PO 2026-11-15: "Ik zie dat de achtergrond weg is, nu alleen de ruis over").
import velden from '../../../factiz_site/static/velden.css?raw';

// FNV-1a, 32 bits: genoeg om twee versies van een bestand uit elkaar te houden
function vingerafdruk(tekst) {
  let h = 0x811c9dc5;
  for (let i = 0; i < tekst.length; i += 1) {
    h ^= tekst.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, '0');
}

export const VELDEN_VERSIE = vingerafdruk(velden);
