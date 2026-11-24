// De namen van landen en talen, de maanden, de datumvorm en het duizendtalteken van de tien nieuwe sitetalen uit de
// taalgegevens van macOS (Unicode CLDR, Unicode-licentie), zoals bij content/landen.json (33.4) en talen.json (33.5).
// PLAN #34.2be, B79. Vertalen en draaien:
//   swiftc -O doublecheck/cldr.swift -o /tmp/cldr && /tmp/cldr <codes.json> data/sitetalen/cldr.json
// codes.json: {"landen": [...ISO 3166-1...], "talen": [...ISO 639-1...]}, uit content/landen.json en talen.json.

import Foundation
let pad = CommandLine.arguments[1]
let ruw = try! JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: pad))) as! [String: Any]
let codes: [String: [String]] = ["landen": ruw["landen"] as! [String], "talen": ruw["talen"] as! [String]]
let talen = ["pt": "pt-BR", "ru": "ru", "uk": "uk", "id": "id", "tr": "tr", "zh": "zh-Hant-TW", "ja": "ja", "hi": "hi", "ar": "ar", "fa": "fa"]
var uit: [String: Any] = [:]
var cal = Calendar(identifier: .gregorian)
cal.timeZone = TimeZone(identifier: "UTC")!
let datum = cal.date(from: DateComponents(year: 2026, month: 10, day: 28))!
for (code, id) in talen {
  let loc = Locale(identifier: ["ar", "fa", "hi"].contains(code) ? id + "-u-nu-latn" : id)
  let f = DateFormatter(); f.locale = loc; f.calendar = cal; f.timeZone = cal.timeZone
  f.setLocalizedDateFormatFromTemplate("dMMMMy")
  let n = NumberFormatter(); n.locale = loc; n.numberStyle = .decimal
  var landen: [String: String] = [:]
  for c in codes["landen"]! { landen[c] = loc.localizedString(forRegionCode: c) ?? "" }
  var namen: [String: String] = [:]
  for c in codes["talen"]! { namen[c] = loc.localizedString(forLanguageCode: c) ?? "" }
  uit[code] = ["voorbeeld": f.string(from: datum), "maanden": { var c = cal; c.locale = loc; return c.monthSymbols }(), "duizendtal": n.groupingSeparator ?? ",",
               "landen": landen, "talen": namen, "eigen": loc.localizedString(forIdentifier: id) ?? ""]
}
let data = try! JSONSerialization.data(withJSONObject: uit, options: [.sortedKeys])
FileManager.default.createFile(atPath: CommandLine.arguments[2], contents: data)
