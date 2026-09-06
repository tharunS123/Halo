import AppKit

/// A borderless, non-activating floating panel.
///
/// The two overrides below are the whole ballgame for "must not steal focus":
/// a panel that cannot become key or main will never pull keyboard focus away
/// from the app being dictated into, even when ordered front.
final class OverlayPanel: NSPanel {

    init(contentRect: NSRect) {
        super.init(
            contentRect: contentRect,
            // .nonactivatingPanel is what keeps the owning app from activating
            // when this window is ordered front.
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )

        isFloatingPanel = true
        level = .statusBar                 // above normal + floating windows
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        hidesOnDeactivate = false
        isMovable = false

        // Never intercept clicks: the user is interacting with another app.
        ignoresMouseEvents = true

        // Visible on every Space and over full-screen apps, without following
        // Space switches (.stationary).
        collectionBehavior = [
            .canJoinAllSpaces,
            .fullScreenAuxiliary,
            .stationary,
            .ignoresCycle,
        ]

        // Not a window the user should ever tab to or see in Exposé.
        animationBehavior = .none
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}
