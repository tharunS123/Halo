import Foundation

enum OverlayState: String {
    case hidden
    case listening
    case processing
    case done
    case error
    case info
}

/// Shared, observable state the SwiftUI view renders. Mutated only on main.
final class OverlayModel: ObservableObject {
    @Published var state: OverlayState = .hidden
    /// Drives the entrance/exit transform. Separate from `state` so the pill
    /// can animate out while still rendering its last content.
    @Published var visible: Bool = false
    /// Short failure text for `.error`. With no terminal and no menu bar, the
    /// pill is the only place a problem can surface.
    @Published var message: String = ""
    /// Privacy Mode: shown as a lock badge on the orb, so the guarantee is
    /// visible at the moment you are speaking.
    @Published var privacy: Bool = false
    /// Latest mic level, 0...1, streamed from Python at ~60Hz. Deliberately
    /// not @Published: the orb reads it every display frame anyway, and
    /// publishing would re-render the whole view 60 times a second.
    var level: Double = 0
    /// Voice-driven clock and wave depth for the orb.
    let orb = OrbDriver()
}
