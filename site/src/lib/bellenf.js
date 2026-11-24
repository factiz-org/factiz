// De F van het logo van Factiz: drie bellen, zoals in factiz_site/static/merk/logo.svg (de vormen van de PO), zonder het
// oranje vlak. Het zegel van de eigen redactie tekent ze in zijn eigen kleur (DESIGN §4x, D12; PO 2026-11-19: "en die f
// mag je bubbel F worden uit ons eigen logo").
export const BELLEN_F = [
  'M44.5315 60.0553C45.2234 64.9589 38.9613 69.7724 30.5447 70.8065C22.128 71.8407 14.7441 68.7039 14.0522 63.8003C13.3603 58.8967 19.6225 54.0832 28.0391 53.0491C36.4557 52.0149 43.8396 55.1518 44.5315 60.0553Z',
  'M59.3452 42.6011C60.1075 48.0033 50.906 53.5892 38.7932 55.0775C26.6804 56.5658 16.2431 53.3929 15.4808 47.9906C14.7186 42.5883 23.92 37.0024 36.0328 35.5142C48.1456 34.0259 58.5829 37.1988 59.3452 42.6011Z',
  'M70.9556 22.5986C71.794 28.9829 60.6688 35.7166 46.1068 37.6388C31.5447 39.561 19.06 35.9438 18.2215 29.5596C17.3831 23.1754 28.5083 16.4417 43.0703 14.5195C57.6324 12.5973 70.1171 16.2144 70.9556 22.5986Z',
];

// het midden van de drie bellen samen, in de maat van logo.svg
const MIDDEN = [42.5, 42.66];

// de transformatie die de bellen met hun midden op (x, y) zet, `maat` keer zo groot als in het logo
export function bellenOp(x, y, maat) {
  return `translate(${x} ${y}) scale(${maat}) translate(${-MIDDEN[0]} ${-MIDDEN[1]})`;
}
