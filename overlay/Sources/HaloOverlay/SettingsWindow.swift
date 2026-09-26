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

    /// `tab` is a tab's name ("privacy"), so `halo settings privacy` can open
    /// straight to it -- the docs point at specific tabs, and "open Settings,
    /// then click Privacy" is one more step than it needs to be.
    func show(tab: String? = nil) {
        if let tab, let match = SettingsView.Tab.allCases.first(
            where: { $0.rawValue.lowercased() == tab.lowercased() }) {
            ui.tab = match
        }
        if let window {
            // The retained window outlives a close, so anything `halo config
            // set` or a text editor changed meanwhile is still stale in the
            // UI -- and the next control change would save that stale value
            // back over it.
            if !window.isVisible {
                SettingsStore.shared.load()
                KeyStore.shared.reset()
            }
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
        if NSApp.mainMenu == nil { NSApp.mainMenu = Self.menu() }
        NSApp.activate(ignoringOtherApps: true)
        w.makeKeyAndOrderFront(nil)
    }

    func windowWillClose(_ note: Notification) {
        // The vocabulary rows only commit on Return, so closing the window is
        // the last chance to keep a word someone typed and walked away from.
        SettingsStore.shared.saveDictionary()
        // An unsaved key should not sit in memory until the window reopens.
        KeyStore.shared.reset()

        // Back to invisible. Deferred by one runloop turn because changing the
        // activation policy while the window is still tearing down leaves the
        // Dock icon behind until something else forces a refresh.
        DispatchQueue.main.async {
            NSApp.setActivationPolicy(.accessory)
        }
    }

    /// Cmd+V, Cmd+C and friends are not handled by text fields themselves:
    /// AppKit finds them as key equivalents in the main menu and sends
    /// `paste:` etc. down the responder chain. Halo never needed a menu until
    /// it had a window, so without this nothing could be pasted into the key
    /// field or a vocabulary row.
    ///
    /// There is deliberately no Quit item. Cmd+Q here would stop dictation
    /// altogether, when what someone pressing it means is "close this window".
    private static func menu() -> NSMenu {
        let main = NSMenu()

        let app = NSMenu(title: "Halo")
        app.addItem(withTitle: "Close Settings",
                    action: #selector(NSWindow.performClose(_:)),
                    keyEquivalent: "w")
        main.addItem(withTitle: "Halo", action: nil, keyEquivalent: "")
            .submenu = app

        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")),
                     keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")),
                     keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)),
                     keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)),
                     keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)),
                     keyEquivalent: "v")
        edit.addItem(withTitle: "Select All",
                     action: #selector(NSText.selectAll(_:)),
                     keyEquivalent: "a")
        main.addItem(withTitle: "Edit", action: nil, keyEquivalent: "")
            .submenu = edit

        return main
    }

    /// True while the window exists and is on screen -- the menu bar item uses
    /// it to decide between "open" and "bring forward".
    var isOpen: Bool { window?.isVisible ?? false }
}
