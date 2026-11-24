// Het lijnicoon van een soort of vorm (PLAN #34.2ak, SPECS E9.S19, DESIGNSYSTEEM §4): een lijn zonder kleur, altijd met
// het woord ernaast, zodat het nooit lijkt op de tegel van een onderwerp (kleur) of het rondje van een oordeel (E9.S16 AC1).
// Voor een schermlezer verborgen: het woord zegt het al.
//
// De iconen zijn van Lucide (https://lucide.dev), versie 0.460.0, overgenomen als gegevens, zonder het pakket.
// ISC License. Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other
// copyright (c) for Lucide are held by Lucide Contributors 2022. Permission to use, copy, modify, and/or distribute this
// software for any purpose with or without fee is hereby granted, provided that the above copyright notice and this
// permission notice appear in all copies. THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
// REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE
// LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE,
// DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION
// WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

export const KENMERK = {
  'soort:bewerkt': 'scissors',
  'soort:context': 'scan-eye',
  'soort:verzonnen': 'pen-line',
  'soort:satire': 'drama',
  'soort:ai': 'sparkles',
  'vorm:video': 'video',
  'vorm:beeld': 'image',
};

const ICONEN = {
  'scissors': [["circle",{"cx":"6","cy":"6","r":"3"}],["path",{"d":"M8.12 8.12 12 12"}],["path",{"d":"M20 4 8.12 15.88"}],["circle",{"cx":"6","cy":"18","r":"3"}],["path",{"d":"M14.8 14.8 20 20"}]],
  'drama': [["path",{"d":"M10 11h.01"}],["path",{"d":"M14 6h.01"}],["path",{"d":"M18 6h.01"}],["path",{"d":"M6.5 13.1h.01"}],["path",{"d":"M22 5c0 9-4 12-6 12s-6-3-6-12c0-2 2-3 6-3s6 1 6 3"}],["path",{"d":"M17.4 9.9c-.8.8-2 .8-2.8 0"}],["path",{"d":"M10.1 7.1C9 7.2 7.7 7.7 6 8.6c-3.5 2-4.7 3.9-3.7 5.6 4.5 7.8 9.5 8.4 11.2 7.4.9-.5 1.9-2.1 1.9-4.7"}],["path",{"d":"M9.1 16.5c.3-1.1 1.4-1.7 2.4-1.4"}]],
  'pen-line': [["path",{"d":"M12 20h9"}],["path",{"d":"M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z"}]],
  'sparkles': [["path",{"d":"M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"}],["path",{"d":"M20 3v4"}],["path",{"d":"M22 5h-4"}],["path",{"d":"M4 17v2"}],["path",{"d":"M5 18H3"}]],
  'scan-eye': [["path",{"d":"M3 7V5a2 2 0 0 1 2-2h2"}],["path",{"d":"M17 3h2a2 2 0 0 1 2 2v2"}],["path",{"d":"M21 17v2a2 2 0 0 1-2 2h-2"}],["path",{"d":"M7 21H5a2 2 0 0 1-2-2v-2"}],["circle",{"cx":"12","cy":"12","r":"1"}],["path",{"d":"M18.944 12.33a1 1 0 0 0 0-.66 7.5 7.5 0 0 0-13.888 0 1 1 0 0 0 0 .66 7.5 7.5 0 0 0 13.888 0"}]],
  'video': [["path",{"d":"m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5"}],["rect",{"x":"2","y":"6","width":"14","height":"12","rx":"2"}]],
  'image': [["rect",{"width":"18","height":"18","x":"3","y":"3","rx":"2","ry":"2"}],["circle",{"cx":"9","cy":"9","r":"2"}],["path",{"d":"m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"}]],
};

export default function LijnIcoon({ wat, waarde }) {
  const icoon = ICONEN[KENMERK[`${wat}:${waarde}`]];
  if (!icoon) return null;
  return (
    <svg className="lijnicoon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true" focusable="false">
      {icoon.map(([Vorm, eigen], i) => <Vorm key={i} {...eigen} />)}
    </svg>
  );
}
