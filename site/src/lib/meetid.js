// Het meet-ID van Google Analytics (B88, SPECS E9.S36 AC1): uit `FACTIZ_GA` (in de Worker uit `vars` in wrangler.jsonc).
// Zonder geldig ID geen banner en niets van Google. Zonder imports: de layout leest het op de server.
export function meetId() {
  const id = process.env.FACTIZ_GA;
  return id && /^G-[A-Z0-9]{4,12}$/.test(id) ? id : null;
}
