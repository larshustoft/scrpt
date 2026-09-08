import Foundation
import Vision
import AppKit
let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print("[]"); exit(1) }
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
try handler.perform([req])
var out: [[String: Any]] = []
for o in req.results ?? [] {
    guard let c = o.topCandidates(1).first else { continue }
    let b = o.boundingBox  // normalized, origin bottom-left
    out.append(["text": c.string, "conf": c.confidence, "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
}
let data = try JSONSerialization.data(withJSONObject: out)
print(String(data: data, encoding: .utf8)!)
