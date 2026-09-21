import AppKit

/// The optional menu bar item.
///
/// Opt-in, and off by default. Halo's whole premise is that the hotkey is the
/// interface, and README says in as many words that there is no menu bar icon.
/// But "no window, no icon" also meant a Settings window would be unreachable
/// without reading the docs, so this exists for people who want a visible
/// handle -- and `halo settings` exists for people who do not.
///
/// It is created and destroyed live when the checkbox changes, so the setting
/// does not need a restart to take effect.
@MainActor
final class MenuBarItem: NSObject {

    private var item: NSStatusItem?
    private let onSettings: () -> Void
    private let onRestart: () -> Void
    private let onPrivacy: (Bool) -> Void

    /// Mirrors the engine's Privacy Mode so the checkmark is honest. Pushed in
    /// by the same `privacy` socket command that badges the orb.
    private(set) var privacy = false

    init(onSettings: @escaping () -> Void,
         onRestart: @escaping () -> Void,
         onPrivacy: @escaping (Bool) -> Void) {
        self.onSettings = onSettings
        self.onRestart = onRestart
        self.onPrivacy = onPrivacy
    }

    var isVisible: Bool { item != nil }

    func setVisible(_ visible: Bool) {
        if visible { install() } else { remove() }
    }

    func setPrivacy(_ on: Bool) {
        privacy = on
        refreshIcon()
    }

    private func install() {
        guard item == nil else { return }
        let i = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item = i
        refreshIcon()
        i.menu = buildMenu()
    }

    private func remove() {
        guard let i = item else { return }
        NSStatusBar.system.removeStatusItem(i)
        item = nil
    }

    private func refreshIcon() {
        guard let button = item?.button else { return }
        // A template image so macOS inverts it correctly in light, dark and
        // the "reduce transparency" menu bar without shipping three assets.
        let name = privacy ? "lock.circle" : "circle.dashed"
        let image = NSImage(systemSymbolName: name,
                            accessibilityDescription: "Halo")
        image?.isTemplate = true
        button.image = image
        button.toolTip = privacy ? "Halo — Privacy Mode on" : "Halo"
    }

    private func buildMenu() -> NSMenu {
        let menu = NSMenu()

        let settings = NSMenuItem(title: "Settings…",
                                  action: #selector(openSettings),
                                  keyEquivalent: ",")
        settings.target = self
        menu.addItem(settings)

        menu.addItem(.separator())

        let privacyItem = NSMenuItem(title: "Privacy Mode",
                                     action: #selector(togglePrivacy),
                                     keyEquivalent: "")
        privacyItem.target = self
        privacyItem.state = privacy ? .on : .off
        menu.addItem(privacyItem)

        let restart = NSMenuItem(title: "Restart Dictation",
                                 action: #selector(restartEngine),
                                 keyEquivalent: "")
        restart.target = self
        menu.addItem(restart)

        menu.addItem(.separator())

        let quit = NSMenuItem(title: "Quit Halo",
                              action: #selector(quit),
                              keyEquivalent: "q")
        quit.target = self
        menu.addItem(quit)

        // Rebuilt on open so the Privacy checkmark is current: the engine can
        // flip it by voice while the menu is closed.
        menu.delegate = self
        return menu
    }

    @objc private func openSettings() { onSettings() }
    @objc private func restartEngine() { onRestart() }
    @objc private func togglePrivacy() { onPrivacy(!privacy) }
    @objc private func quit() { NSApp.terminate(nil) }
}

extension MenuBarItem: NSMenuDelegate {
    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.item(withTitle: "Privacy Mode")?.state = privacy ? .on : .off
    }
}
