import Foundation

enum OverlayState: String {
    case hidden
    case listening
    case processing
    case done
    case error
}

/// Shared, observable state the SwiftUI view renders. Mutated only on main.
let kBarCount = 24

final class OverlayModel: ObservableObject {
    @Published var state: OverlayState = .hidden {
        didSet { stateChangedAt = Date() }
    }
    /// Drives the entrance/exit transform. Separate from `state` so the pill
    /// can animate out while still rendering its last content.
    @Published var visible: Bool = false
    /// When the current state began -- used to blend one animation into the
    /// next instead of hard-cutting between them.
    @Published var stateChangedAt: Date = Date()
    /// Levels captured at the moment we left `.listening`, so the processing
    /// animation can grow out of the waveform the user was just watching.
    @Published var levelsAtHandoff: [CGFloat] = Array(repeating: 0, count: kBarCount)
    /// Short failure text for `.error`. With no terminal and no menu bar, the
    /// pill is the only place a problem can surface.
    @Published var message: String = ""
    /// Most recent mic levels, 0...1, oldest first. Streamed from Python.
    @Published var levels: [CGFloat] = Array(repeating: 0, count: kBarCount)

    static let barCount = kBarCount

    func push(level: CGFloat) {
        var l = levels
        l.removeFirst()
        l.append(max(0, min(1, level)))
        levels = l
    }

    func resetLevels() {
        levels = Array(repeating: 0, count: kBarCount)
    }
}
