import AppKit
import SwiftUI

@MainActor
final class OverlayController {
    let model = OverlayModel()
    private var panel: OverlayPanel?
    private var hideWorkItem: DispatchWorkItem?
    private var watchdog: DispatchWorkItem?
    private var dismissWorkItem: DispatchWorkItem?
    /// If the driving process dies mid-dictation we must not leave a pill
    /// stuck on screen forever.
    private let watchdogSeconds: TimeInterval = 90

    /// Distance from the bottom edge of the screen, in points.
    private let bottomInset: CGFloat = 140

    func makePanelIfNeeded() {
        guard panel == nil else { return }
        let rect = NSRect(x: 0, y: 0, width: Style.panelWidth, height: Style.panelHeight)
        let p = OverlayPanel(contentRect: rect)
        let host = NSHostingView(rootView: OverlayView(model: model))
        host.frame = rect
        // Let the panel's own rounded clip show through.
        host.wantsLayer = true
        host.layer?.backgroundColor = .clear
        p.contentView = host
        panel = p
    }

    /// Bottom-center of whichever screen currently contains the mouse, so the
    /// overlay follows the display you are actually working on.
    private func targetOrigin() -> NSPoint {
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first { NSMouseInRect(mouse, $0.frame, false) }
            ?? NSScreen.main
            ?? NSScreen.screens[0]
        let f = screen.visibleFrame
        return NSPoint(
            x: f.midX - Style.panelWidth / 2,
            y: f.minY + bottomInset
        )
    }

    func show(_ state: OverlayState) {
        makePanelIfNeeded()
        guard let panel else { return }

        hideWorkItem?.cancel()
        hideWorkItem = nil

        dismissWorkItem?.cancel()
        dismissWorkItem = nil

        let wasHidden = !panel.isVisible
        if wasHidden {
            panel.setFrameOrigin(targetOrigin())
            model.level = 0
            model.orb.reset()
            model.visible = false
        }

        withAnimation(.spring(response: 0.32, dampingFraction: 0.78)) {
            model.state = state
        }
        // The pill changes width between states. A transparent window's shadow
        // is traced from its content and never refreshed on its own, so redo it
        // once the spring has settled.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) { [weak self] in
            self?.panel?.invalidateShadow()
        }

        // orderFrontRegardless: show without activating this app at all.
        panel.orderFrontRegardless()

        if wasHidden {
            // Animate in on the next tick so the initial collapsed transform
            // is committed first; otherwise it pops in fully formed.
            DispatchQueue.main.async { [weak self] in
                withAnimation(.spring(response: 0.36, dampingFraction: 0.68)) {
                    self?.model.visible = true
                }
            }
        }
        armWatchdog()
    }

    /// Any inbound command resets the watchdog.
    func pushLevel(_ v: CGFloat) {
        model.level = Double(max(0, min(1, v)))
        armWatchdog()
    }

    private func armWatchdog() {
        watchdog?.cancel()
        let w = DispatchWorkItem { [weak self] in
            guard let self, self.model.state != .hidden else { return }
            self.hide()
        }
        watchdog = w
        DispatchQueue.main.asyncAfter(deadline: .now() + watchdogSeconds, execute: w)
    }

    func hide() {
        watchdog?.cancel()
        watchdog = nil
        dismissWorkItem?.cancel()

        guard let panel, panel.isVisible else {
            model.state = .hidden
            model.visible = false
            return
        }

        // Fade/shrink out, then actually order the window away. The content
        // keeps rendering during the exit, so it does not blank mid-animation.
        withAnimation(.easeOut(duration: 0.22)) { model.visible = false }
        let work = DispatchWorkItem { [weak self] in
            self?.panel?.orderOut(nil)
            self?.model.state = .hidden
        }
        dismissWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.24, execute: work)
    }

    /// Authoritative self-report: no Screen Recording permission required,
    /// because we are asking our own panel about itself.
    func status() -> String {
        guard let p = panel else { return "panel: NOT CREATED" }
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first { NSMouseInRect(mouse, $0.frame, false) }
        return """
        panel.isVisible      : \(p.isVisible)
        panel.frame          : \(p.frame)
        panel.level          : \(p.level.rawValue) (statusBar=\(NSWindow.Level.statusBar.rawValue))
        panel.alphaValue     : \(p.alphaValue)
        panel.isKeyWindow    : \(p.isKeyWindow)   <- must be false
        panel.canBecomeKey   : \(p.canBecomeKey)  <- must be false
        contentView          : \(String(describing: p.contentView?.frame))
        model.state          : \(model.state.rawValue)
        mouseLocation        : \(mouse)
        mouse on screen      : \(screen?.frame.debugDescription ?? "none")
        computed origin      : \(targetOrigin())
        activationPolicy     : \(NSApp.activationPolicy().rawValue) (accessory=1)
        \(Permissions.summary)
        """
    }

    func setPrivacy(_ on: Bool) {
        withAnimation(.spring(response: 0.3, dampingFraction: 0.75)) {
            model.privacy = on
        }
    }

    /// Neutral transient message (privacy toggles, confirmations).
    func flashInfo(_ message: String, after seconds: TimeInterval = 1.6) {
        model.message = message
        show(.info)
        let work = DispatchWorkItem { [weak self] in self?.hide() }
        hideWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: work)
    }

    /// Show a failure message, then auto-dismiss. Held longer than `.done`
    /// because the user has to actually read it.
    func flashError(_ message: String, after seconds: TimeInterval = 2.8) {
        model.message = message
        show(.error)
        let work = DispatchWorkItem { [weak self] in self?.hide() }
        hideWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: work)
    }

    /// Show `.done`, then auto-dismiss.
    func flashDone(after seconds: TimeInterval = 1.1) {
        show(.done)
        let work = DispatchWorkItem { [weak self] in self?.hide() }
        hideWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: work)
    }
}
