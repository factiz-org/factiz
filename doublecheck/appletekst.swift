// Leest de tekst van een beeld met Apple Vision (P4, PLAN #32.0b): de tekstherkenning
// van macOS zelf, zonder download. Eén pad per regel op stdin; per beeld één JSON-regel
// op stdout met de tekst, regel voor regel van boven naar onder. Het beeld wordt
// nergens heen geschreven.
import AppKit
import Foundation
import Vision

func lees(_ pad: String) -> String {
    guard let beeld = NSImage(contentsOfFile: pad),
          let cg = beeld.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return "" }
    let verzoek = VNRecognizeTextRequest()
    verzoek.recognitionLevel = .accurate
    verzoek.usesLanguageCorrection = true
    verzoek.automaticallyDetectsLanguage = true
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([verzoek])
    // Vision rekent y van onder; banden van 2% van de hoogte gelden als één regel.
    let gezien = (verzoek.results ?? []).sorted {
        let (a, b) = (Int((1 - $0.boundingBox.midY) * 50), Int((1 - $1.boundingBox.midY) * 50))
        return a != b ? a < b : $0.boundingBox.minX < $1.boundingBox.minX
    }
    return gezien.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

while let pad = readLine() {
    let data = try! JSONSerialization.data(withJSONObject: ["pad": pad, "tekst": lees(pad)])
    print(String(data: data, encoding: .utf8)!)
    fflush(stdout)
}
