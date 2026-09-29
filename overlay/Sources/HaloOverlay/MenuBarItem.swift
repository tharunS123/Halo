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
    private let onTransform: (String) -> Void
    private let onLanguage: (String) -> Void

    /// Mirrors the engine's Privacy Mode so the checkmark is honest. Pushed in
    /// by the same `privacy` socket command that badges the orb.
    private(set) var privacy = false

    init(onSettings: @escaping () -> Void,
         onRestart: @escaping () -> Void,
         onPrivacy: @escaping (Bool) -> Void,
         onTransform: @escaping (String) -> Void,
         onLanguage: @escaping (String) -> Void) {
        self.onSettings = onSettings
        self.onRestart = onRestart
        self.onPrivacy = onPrivacy
        self.onTransform = onTransform
        self.onLanguage = onLanguage
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
        let image = Self.icon(privacy: privacy, failed: failed)
        button.image = image
        button.imagePosition = .imageOnly
        let state = failed ? "a dictation needs attention" : privacy ? "Privacy Mode on" : nil
        button.toolTip = state.map { "Halo — \($0)" } ?? "Halo"
        button.setAccessibilityLabel(state.map { "Halo, \($0)" } ?? "Halo")
    }

    /// The seven-dot H (halo-menu-template.svg), drawn as a template. Failed
    /// and Privacy states keep a visible glyph: it is set to the right of the
    /// mark rather than over it, so the seven dots stay legible.
    private static func icon(privacy: Bool, failed: Bool) -> NSImage {
        let height: CGFloat = 18
        let mark = markImage()
        let badgeName = failed ? "exclamationmark.circle.fill" : privacy ? "lock.fill" : nil
        let badge = badgeName.flatMap {
            NSImage(systemSymbolName: $0, accessibilityDescription: nil)?
                .withSymbolConfiguration(.init(pointSize: 10, weight: .bold))
        }
        let gap: CGFloat = 2
        let badgeWidth = badge.map { min($0.size.width, 12) + gap } ?? 0
        let size = NSSize(width: height + badgeWidth, height: height)
        let image = NSImage(size: size, flipped: false) { _ in
            mark.draw(in: NSRect(x: 0, y: 0, width: height, height: height),
                      from: .zero, operation: .sourceOver, fraction: 1)
            if let badge {
                let w = min(badge.size.width, 12)
                let h = badge.size.height * (w / max(badge.size.width, 1))
                badge.draw(in: NSRect(x: height + gap, y: (height - h) / 2, width: w, height: h),
                           from: .zero, operation: .sourceOver, fraction: 1)
            }
            return true
        }
        image.isTemplate = true
        image.accessibilityDescription = "Halo"
        return image
    }

    /// The template art: the SVG (vector, crisp at 1x and 2x) when this macOS
    /// renders it, else the PNG, else the same seven dots drawn by hand.
    private static func markImage() -> NSImage {
        for name in ["halo-menu-template.svg", "halo-menu-template.png"] {
            if let img = HaloResources.image(name),
               img.isValid, img.size.width > 0, !img.representations.isEmpty {
                return img
            }
        }
        // (x, y, radius) in the template's 16-unit grid, y down.
        let dots: [(CGFloat, CGFloat, CGFloat)] = [
            (4.5, 3, 2), (4.5, 8, 2), (4.5, 13, 2),
            (11.5, 3, 2), (11.5, 8, 2), (11.5, 13, 2), (8, 8, 1.45),
        ]
        return NSImage(size: NSSize(width: 16, height: 16), flipped: true) { _ in
            NSColor.black.setFill()
            for (x, y, r) in dots {
                NSBezierPath(ovalIn: NSRect(x: x - r, y: y - r, width: 2 * r, height: 2 * r)).fill()
            }
            return true
        }
    }

    private func buildMenu() -> NSMenu {
        let menu = NSMenu()

        let settings = NSMenuItem(title: "Settings…",
                                  action: #selector(openSettings),
                                  keyEquivalent: ",")
        settings.target = self
        menu.addItem(settings)

        menu.addItem(.separator())

        // Transforms act on the selection in the app you were in: a status
        // menu never takes focus from it.
        let failedItem = NSMenuItem(title: "Last Dictation Didn’t Make It", action: nil, keyEquivalent: "")
        failedItem.submenu = NSMenu(title: "Last Dictation")
        failedItem.isHidden = true
        menu.addItem(failedItem)

        let transforms = NSMenuItem(title: "Transform Selection", action: nil, keyEquivalent: "")
        transforms.submenu = NSMenu(title: "Transform Selection")
        menu.addItem(transforms)
        let language = NSMenuItem(title: "Language", action: nil, keyEquivalent: "")
        language.submenu = NSMenu(title: "Language")
        menu.addItem(language)
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

    /// A failed dictation is waiting: offer it from the menu, and mark the
    /// icon so it is noticed without opening anything.
    private(set) var failed = false

    func setFailed(_ on: Bool) {
        failed = on
        refreshIcon()
    }

    @objc private func failedAction(_ sender: NSMenuItem) {
        if let action = sender.representedObject as? String { FailedStore.shared.run(action) }
    }

    @objc private func openSettings() { onSettings() }
    @objc private func restartEngine() { onRestart() }
    @objc private func togglePrivacy() { onPrivacy(!privacy) }
    @objc private func quit() { NSApp.terminate(nil) }
    @objc private func transform(_ sender: NSMenuItem) {
        if let id = sender.representedObject as? String { onTransform(id) }
    }
    @objc private func pickLanguage(_ sender: NSMenuItem) {
        if let code = sender.representedObject as? String { onLanguage(code) }
    }

    fileprivate func fill(_ menu: NSMenu) {
        if let entry = menu.item(withTitle: "Last Dictation Didn’t Make It"), let sub = entry.submenu {
            sub.removeAllItems()
            let item = FailedStore.shared.item
            entry.isHidden = item == nil
            if let item {
                let why = NSMenuItem(title: item.reason, action: nil, keyEquivalent: "")
                why.isEnabled = false
                sub.addItem(why)
                sub.addItem(.separator())
                let hasText = !(item.text.isEmpty && item.raw.isEmpty)
                for (title, action, enabled) in [
                    ("Retry Insertion Here", "retry_insertion", hasText),
                    ("Copy Text", "copy", hasText),
                    ("Retry Transcription", "retry_transcription", item.hasAudio),
                    ("Retry Cleanup", "retry_cleanup", !item.raw.isEmpty),
                    ("Discard", "discard", true),
                ] {
                    let m = NSMenuItem(title: title, action: enabled ? #selector(failedAction(_:)) : nil,
                                       keyEquivalent: "")
                    m.target = self
                    m.representedObject = action
                    m.isEnabled = enabled
                    sub.addItem(m)
                }
            }
        }
        if let sub = menu.item(withTitle: "Transform Selection")?.submenu {
            sub.removeAllItems()
            let store = TransformsStore.shared
            store.load()
            for t in store.all {
                let item = NSMenuItem(title: t.name, action: #selector(transform(_:)), keyEquivalent: "")
                item.target = self
                item.representedObject = t.id
                sub.addItem(item)
            }
        }
        if let sub = menu.item(withTitle: "Language")?.submenu {
            sub.removeAllItems()
            let store = SettingsStore.shared
            var codes = ["auto"] + store.enabledLanguages
            for c in store.recentLanguages() where !codes.contains(c) { codes.append(c) }
            for code in codes {
                let item = NSMenuItem(title: LanguageInfo.name(code),
                                      action: #selector(pickLanguage(_:)), keyEquivalent: "")
                item.target = self
                item.representedObject = code
                item.state = store.language == code ? .on : .off
                sub.addItem(item)
            }
        }
    }
}

extension MenuBarItem: NSMenuDelegate {
    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.item(withTitle: "Privacy Mode")?.state = privacy ? .on : .off
        fill(menu)
    }
}
