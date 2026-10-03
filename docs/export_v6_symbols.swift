import AppKit
import Foundation
let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
let names = ["book", "book.fill", "chart.bar", "person.crop.circle", "mic.fill", "speaker.wave.2.fill", "chevron.right", "xmark", "ellipsis", "checkmark.circle.fill", "arrow.clockwise"]
for name in names {
    guard let symbol = NSImage(systemSymbolName: name, accessibilityDescription: nil)?.withSymbolConfiguration(NSImage.SymbolConfiguration(pointSize: 40, weight: .regular)) else { continue }
    let canvas = NSImage(size: NSSize(width: 150, height: 150))
    canvas.lockFocus()
    let scale = min(130 / symbol.size.width, 130 / symbol.size.height)
    let size = NSSize(width: symbol.size.width * scale, height: symbol.size.height * scale)
    symbol.draw(in: NSRect(x: (150-size.width)/2, y: (150-size.height)/2, width: size.width, height: size.height))
    canvas.unlockFocus()
    guard let tiff = canvas.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiff), let png = bitmap.representation(using: .png, properties: [:]) else { continue }
    try png.write(to: output.appendingPathComponent(name + ".png"))
}
print("SF Symbols exported")
