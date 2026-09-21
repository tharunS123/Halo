import AppKit
import SwiftUI

/// Hosts the Settings window, and handles the one genuinely awkward part:
/// showing a real, focusable window from an `.accessory` app.
///
/// Halo sets `NSApp.setActivationPolicy(.accessory)` so it has no Dock icon
/// and can never steal focus from the app you are dictating into. An accessory
/// app *can* open a window, but it cannot properly activate: the window comes
/// up behind whatever was in front, text fields do not take the caret, and
/// Cmd+Q goes to the wrong app.
///
/// The fix is to switch to `.regular` for exactly as long as the window is
/// open, then drop back to `.accessory` when it closes. While it is open Halo
/// looks like an ordinary app, with a Dock icon; the moment you close it the
/// Dock icon disappears again and the overlay's no-focus guarantee is
/// restored. Switching back is what `windowWillClose` is for, and it must run
/// even when the user closes the window with Cmd+W or the red button, which is
/// why this object is the window's delegate rather than trusting a button
/// action.
@MainActor
final class SettingsWindowController: NSObject, NSWindowDelegate {

    static let shared = SettingsWindowController()

    private var window: NSWindow?
    /// View-local state, owned here so switching tabs survives a close and
    /// reopen -- and because `@State` is unavailable under the Command Line
    /// Tools (see SettingsView).
    private let ui = SettingsUI()

    func show() {
        if let window {
            activate(window)
            return
        }

        // Re-read from disk first. The CLI and a text editor are equally
        // valid writers, so anything opened stale would show -- and then save
        // back -- values the user already changed elsewhere.
        SettingsStore.shared.load()

        let w = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 640, height: 520),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        w.title = "Halo Settings"
        w.isReleasedWhenClosed = false      // we keep the reference ourselves
        w.center()
        w.setFrameAutosaveName("HaloSettingsWindow")
        w.contentView = NSHostingView(
            rootView: SettingsView(store: SettingsStore.shared, ui: ui))
        w.delegate = self
        window = w
        activate(w)
    }

    private func activate(_ w: NSWindow) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        w.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ note: Notification) {
        // The vocabulary rows only commit on Return, so closing the window is
        // the last chance to keep a word someone typed and walked away from.
        SettingsStore.shared.saveDictionary()

        // Back to invisible. Deferred by one runloop turn because changing the
        // activation policy while the window is still tearing down leaves the
        // Dock icon behind until something else forces a refresh.
        DispatchQueue.main.async {
            NSApp.setActivationPolicy(.accessory)
        }
    }

    /// True while the window exists and is on screen -- the menu bar item uses
    /// it to decide between "open" and "bring forward".
    var isOpen: Bool { window?.isVisible ?? false }
}
