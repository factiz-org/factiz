// Kleur en icoon per onderwerp (PLAN #34.2ag, SPECS E9.S16, DESIGNSYSTEEM §4): een vierkante tegel met de kleur van de
// familie en het icoon van het thema. Het oordeel blijft een rondje met een woord; een land krijgt nooit een kleur. De
// familie is die van het veld van het thema (`doublecheck/velden.py`, THEMA_VELDEN); `tests/test_site_themakleur.py` eist
// dat ze gelijk zijn en meet de kleuren in `site.css`. De tegel is voor schermlezers verborgen: de naam staat er altijd naast.
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

export const THEMA = {
  politics: { familie: 'leisteen', icoon: 'landmark' },
  elections: { familie: 'leisteen', icoon: 'vote' },
  world: { familie: 'leisteen', icoon: 'handshake' },
  war: { familie: 'nacht', icoon: 'shield' },
  crime: { familie: 'nacht', icoon: 'gavel' },
  disasters: { familie: 'nacht', icoon: 'siren' },
  health: { familie: 'groen', icoon: 'heart-pulse' },
  science: { familie: 'groen', icoon: 'flask-conical' },
  economy: { familie: 'olijf', icoon: 'coins' },
  climate: { familie: 'olijf', icoon: 'leaf' },
  society: { familie: 'hemel', icoon: 'users' },
  migration: { familie: 'hemel', icoon: 'footprints' },
  people: { familie: 'hemel', icoon: 'mic' },
};

const ICONEN = {
  'landmark': [["line",{"x1":"3","x2":"21","y1":"22","y2":"22"}],["line",{"x1":"6","x2":"6","y1":"18","y2":"11"}],["line",{"x1":"10","x2":"10","y1":"18","y2":"11"}],["line",{"x1":"14","x2":"14","y1":"18","y2":"11"}],["line",{"x1":"18","x2":"18","y1":"18","y2":"11"}],["polygon",{"points":"12 2 20 7 4 7"}]],
  'vote': [["path",{"d":"m9 12 2 2 4-4"}],["path",{"d":"M5 7c0-1.1.9-2 2-2h10a2 2 0 0 1 2 2v12H5V7Z"}],["path",{"d":"M22 19H2"}]],
  'handshake': [["path",{"d":"m11 17 2 2a1 1 0 1 0 3-3"}],["path",{"d":"m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"}],["path",{"d":"m21 3 1 11h-2"}],["path",{"d":"M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3"}],["path",{"d":"M3 4h8"}]],
  'shield': [["path",{"d":"M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"}]],
  'gavel': [["path",{"d":"m14.5 12.5-8 8a2.119 2.119 0 1 1-3-3l8-8"}],["path",{"d":"m16 16 6-6"}],["path",{"d":"m8 8 6-6"}],["path",{"d":"m9 7 8 8"}],["path",{"d":"m21 11-8-8"}]],
  'siren': [["path",{"d":"M7 18v-6a5 5 0 1 1 10 0v6"}],["path",{"d":"M5 21a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-1a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2z"}],["path",{"d":"M21 12h1"}],["path",{"d":"M18.5 4.5 18 5"}],["path",{"d":"M2 12h1"}],["path",{"d":"M12 2v1"}],["path",{"d":"m4.929 4.929.707.707"}],["path",{"d":"M12 12v6"}]],
  'heart-pulse': [["path",{"d":"M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"}],["path",{"d":"M3.22 12H9.5l.5-1 2 4.5 2-7 1.5 3.5h5.27"}]],
  'flask-conical': [["path",{"d":"M10 2v7.527a2 2 0 0 1-.211.896L4.72 20.55a1 1 0 0 0 .9 1.45h12.76a1 1 0 0 0 .9-1.45l-5.069-10.127A2 2 0 0 1 14 9.527V2"}],["path",{"d":"M8.5 2h7"}],["path",{"d":"M7 16h10"}]],
  'coins': [["circle",{"cx":"8","cy":"8","r":"6"}],["path",{"d":"M18.09 10.37A6 6 0 1 1 10.34 18"}],["path",{"d":"M7 6h1v4"}],["path",{"d":"m16.71 13.88.7.71-2.82 2.82"}]],
  'leaf': [["path",{"d":"M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"}],["path",{"d":"M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"}]],
  'users': [["path",{"d":"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"}],["circle",{"cx":"9","cy":"7","r":"4"}],["path",{"d":"M22 21v-2a4 4 0 0 0-3-3.87"}],["path",{"d":"M16 3.13a4 4 0 0 1 0 7.75"}]],
  'footprints': [["path",{"d":"M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z"}],["path",{"d":"M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z"}],["path",{"d":"M16 17h4"}],["path",{"d":"M4 13h4"}]],
  'mic': [["path",{"d":"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"}],["path",{"d":"M19 10v2a7 7 0 0 1-14 0v-2"}],["line",{"x1":"12","x2":"12","y1":"19","y2":"22"}]],
};

// klein: in een regel tekst (een kaart, een filter); midden: in een lijst of menu; groot: bij de naam van een thema
export default function ThemaTegel({ thema, maat = 'klein' }) {
  const t = THEMA[thema];
  if (!t) return null;
  return (
    <span className={`tegel tegel-${maat}`} data-familie={t.familie} aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {ICONEN[t.icoon].map(([vorm, eigen], i) => {
          const Vorm = vorm;
          return <Vorm key={i} {...eigen} />;
        })}
      </svg>
    </span>
  );
}
