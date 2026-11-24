// HarfBuzz voor het deelplaatje (B80, PLAN #34.2bo stap 5): zetten met `harfbuzzjs/dist/harfbuzz.wasm`, zonder de lijm
// van Emscripten. Die lijm haalt de wasm zelf op en maakt terugroepfuncties door bij het draaien wasm te compileren; een
// Worker staat dat niet toe. Hier komt de wasm van buiten (`WasmBron`), en de vijf terugroepfuncties voor de omtrek van een
// teken komen uit een klein vast wasm-blok (`TEKEN_WASM`) dat een Worker als module kan importeren.

export type WasmBron = WebAssembly.Module | BufferSource;

// Een wasm-module die vijf functies van JavaScript importeert en weer uitvoert, met de soorten die HarfBuzz voor tekenen
// verwacht (move_to en line_to `viiiffi`, quadratic_to `viiiffffi`, cubic_to `viiiffffffi`, close_path `viiii`). Uitgevoerd
// zijn het wasm-functies, en die mogen in de tabel van HarfBuzz.
export const TEKEN_WASM = new Uint8Array([
  0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00,
  0x01, 0x29, 0x04,
  0x60, 0x06, 0x7f, 0x7f, 0x7f, 0x7d, 0x7d, 0x7f, 0x00,
  0x60, 0x08, 0x7f, 0x7f, 0x7f, 0x7d, 0x7d, 0x7d, 0x7d, 0x7f, 0x00,
  0x60, 0x0a, 0x7f, 0x7f, 0x7f, 0x7d, 0x7d, 0x7d, 0x7d, 0x7d, 0x7d, 0x7f, 0x00,
  0x60, 0x04, 0x7f, 0x7f, 0x7f, 0x7f, 0x00,
  0x02, 0x1f, 0x05,
  0x01, 0x65, 0x01, 0x6d, 0x00, 0x00,
  0x01, 0x65, 0x01, 0x6c, 0x00, 0x00,
  0x01, 0x65, 0x01, 0x71, 0x00, 0x01,
  0x01, 0x65, 0x01, 0x63, 0x00, 0x02,
  0x01, 0x65, 0x01, 0x7a, 0x00, 0x03,
  0x07, 0x15, 0x05,
  0x01, 0x6d, 0x00, 0x00,
  0x01, 0x6c, 0x00, 0x01,
  0x01, 0x71, 0x00, 0x02,
  0x01, 0x63, 0x00, 0x03,
  0x01, 0x7a, 0x00, 0x04,
]);

type Fn = (...a: number[]) => number;
const LTR = 4;
const RTL = 5;
const WGHT = 0x77676874;

async function maak(bron: WasmBron, imports: WebAssembly.Imports): Promise<WebAssembly.Instance> {
  if (bron instanceof WebAssembly.Module) return WebAssembly.instantiate(bron, imports);
  return (await WebAssembly.instantiate(bron, imports)).instance;
}

// Een gezet stuk tekst: per teken het nummer in het lettertype, de plek (26.6, vanaf het begin) en de verschuiving.
export type Gezet = { glyph: Uint32Array; x: Int32Array; dy: Int32Array; breedte: number };

export class HarfBuzz {
  private f: Record<string, Fn>;
  private geheugen: WebAssembly.Memory;
  private tekenfuncties: number;
  private pad: string[] = [];
  private schaal = 1;
  private ox = 0;
  private oy = 0;

  private constructor(f: Record<string, Fn>, geheugen: WebAssembly.Memory, tekenfuncties: number) {
    this.f = f;
    this.geheugen = geheugen;
    this.tekenfuncties = tekenfuncties;
  }

  static async laad(hb: WasmBron, teken: WasmBron): Promise<HarfBuzz> {
    let geheugen: WebAssembly.Memory | null = null;
    const instantie = await maak(hb, {
      env: {
        _emscripten_runtime_keepalive_clear: () => {},
        _abort_js: () => { throw new Error('harfbuzz: abort'); },
        _setitimer_js: () => 0,
        // het geheugen groeit zoals Emscripten het laat groeien: tot wat gevraagd is, met wat ruimte erbij
        emscripten_resize_heap: (gevraagd: number) => {
          const nu = geheugen!.buffer.byteLength;
          const doel = Math.max(gevraagd >>> 0, Math.floor(nu * 1.2));
          try {
            geheugen!.grow(Math.ceil((doel - nu) / 65536));
            return 1;
          } catch {
            return 0;
          }
        },
      },
      wasi_snapshot_preview1: { proc_exit: (code: number) => { throw new Error(`harfbuzz: exit ${code}`); } },
    });
    const f = instantie.exports as unknown as Record<string, Fn>;
    geheugen = instantie.exports.memory as WebAssembly.Memory;
    f.__wasm_call_ctors();
    // de omtrek van een teken komt binnen via vijf functies in de tabel van HarfBuzz
    let hb_: HarfBuzz | null = null;
    const punt = (x: number, y: number) => `${(hb_!.ox + x * hb_!.schaal).toFixed(2)} ${(hb_!.oy - y * hb_!.schaal).toFixed(2)}`;
    const terug = await maak(teken, { e: {
      m: (_d: number, _p: number, _s: number, x: number, y: number) => { hb_!.pad.push(`M${punt(x, y)}`); },
      l: (_d: number, _p: number, _s: number, x: number, y: number) => { hb_!.pad.push(`L${punt(x, y)}`); },
      q: (_d: number, _p: number, _s: number, cx: number, cy: number, x: number, y: number) => {
        hb_!.pad.push(`Q${punt(cx, cy)} ${punt(x, y)}`);
      },
      c: (_d: number, _p: number, _s: number, ax: number, ay: number, bx: number, by: number, x: number, y: number) => {
        hb_!.pad.push(`C${punt(ax, ay)} ${punt(bx, by)} ${punt(x, y)}`);
      },
      z: () => { hb_!.pad.push('Z'); },
    } });
    const tabel = instantie.exports.__indirect_function_table as WebAssembly.Table;
    const begin = tabel.grow(5);
    ['m', 'l', 'q', 'c', 'z'].forEach((n, i) => tabel.set(begin + i, terug.exports[n] as never));
    const funcs = f.hb_draw_funcs_create();
    f.hb_draw_funcs_set_move_to_func(funcs, begin, 0, 0);
    f.hb_draw_funcs_set_line_to_func(funcs, begin + 1, 0, 0);
    f.hb_draw_funcs_set_quadratic_to_func(funcs, begin + 2, 0, 0);
    f.hb_draw_funcs_set_cubic_to_func(funcs, begin + 3, 0, 0);
    f.hb_draw_funcs_set_close_path_func(funcs, begin + 4, 0, 0);
    hb_ = new HarfBuzz(f, geheugen, funcs);
    return hb_;
  }

  private get u8() { return new Uint8Array(this.geheugen.buffer); }
  private get i32() { return new Int32Array(this.geheugen.buffer); }
  private get u32() { return new Uint32Array(this.geheugen.buffer); }

  // Een lettertypebestand (TTF) als face; de bytes blijven in het geheugen van HarfBuzz zolang de Worker leeft.
  face(bytes: Uint8Array): number {
    const plek = this.f.malloc(bytes.byteLength);
    this.u8.set(bytes, plek);
    const blob = this.f.hb_blob_create(plek, bytes.byteLength, 1, 0, 0);
    const face = this.f.hb_face_create(blob, 0);
    this.f.hb_blob_destroy(blob);
    return face;
  }

  // Een font op een grootte en een gewicht: posities in 26.6, zoals FreeType ze aan Pillow geeft.
  font(face: number, grootte: number, gewicht: number): number {
    const font = this.f.hb_font_create(face);
    this.f.hb_font_set_scale(font, grootte * 64, grootte * 64);
    const v = this.f.malloc(8);
    this.u32[v >> 2] = WGHT;
    new Float32Array(this.geheugen.buffer)[(v >> 2) + 1] = gewicht;
    this.f.hb_font_set_variations(font, v, 1);
    this.f.free(v);
    return font;
  }

  // ascender en descender in 26.6
  hoogte(font: number): [number, number] {
    const p = this.f.malloc(48);
    this.f.hb_font_get_h_extents(font, p);
    const uit: [number, number] = [this.i32[p >> 2], this.i32[(p >> 2) + 1]];
    this.f.free(p);
    return uit;
  }

  // Zet `lengte` code units vanaf `begin` van `tekst` in één richting; de rest van de tekst is de context (Arabisch verbindt
  // zo over de grens van een stuk heen, zoals raqm het doet).
  zet(font: number, tekst: string, begin: number, lengte: number, rtl: boolean): Gezet {
    const t = this.f.malloc(tekst.length * 2 + 2);
    const u16 = new Uint16Array(this.geheugen.buffer, t, tekst.length);
    for (let i = 0; i < tekst.length; i++) u16[i] = tekst.charCodeAt(i);
    const buf = this.f.hb_buffer_create();
    this.f.hb_buffer_add_utf16(buf, t, tekst.length, begin, lengte);
    this.f.hb_buffer_set_direction(buf, rtl ? RTL : LTR);
    this.f.hb_buffer_guess_segment_properties(buf);
    this.f.hb_shape(font, buf, 0, 0);
    const n = this.f.hb_buffer_get_length(buf);
    const info = this.f.hb_buffer_get_glyph_infos(buf, 0) >> 2;
    const pos = this.f.hb_buffer_get_glyph_positions(buf, 0) >> 2;
    const u32 = this.u32;
    const i32 = this.i32;
    const uit: Gezet = { glyph: new Uint32Array(n), x: new Int32Array(n), dy: new Int32Array(n), breedte: 0 };
    let pen = 0;
    for (let i = 0; i < n; i++) {
      uit.glyph[i] = u32[info + i * 5];
      uit.x[i] = pen + i32[pos + i * 5 + 2];
      uit.dy[i] = i32[pos + i * 5 + 3];
      pen += i32[pos + i * 5];
    }
    uit.breedte = pen;
    this.f.hb_buffer_destroy(buf);
    this.f.free(t);
    return uit;
  }

  // De omtrek van een teken als SVG-pad, in pixels, met de oorsprong op (x, y) en y naar beneden.
  omtrek(font: number, glyph: number, x: number, y: number): string {
    this.pad = [];
    this.schaal = 1 / 64;
    this.ox = x;
    this.oy = y;
    this.f.hb_font_draw_glyph(font, glyph, this.tekenfuncties, 0);
    return this.pad.join('');
  }
}
