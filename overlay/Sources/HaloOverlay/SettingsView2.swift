import AppKit
import AVFoundation
import SwiftUI

// MARK: - Microphone

extension Permissions {
    /// The microphone grant as a status chip: symbol + words.
    static var microphoneChip: (HaloStatus, String) {
        switch microphone {
        case .authorized: return (.ok, "Allowed")
        case .notDetermined: return (.warning, "Not asked yet")
        case .denied: return (.error, "Denied")
        case .restricted: return (.error, "Restricted by macOS")
        @unknown default: return (.info, "Unknown")
        }
    }
}

struct MicrophonePane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var devices = AudioDevices.shared
    @ObservedObject var tester = MicTester.shared

    private var missing: Bool {
        !store.micDevice.isEmpty && devices.device(named: store.micDevice) == nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Microphone",
                      subtitle: "Which input Halo records from. Changes apply to the next dictation — no restart.")

            Block(title: "Input device",
                  note: "System Default follows whatever macOS is set to. A chosen device that is "
                      + "unplugged falls back to the default, and the orb says so.") {
                SettingRow(title: "Record from") {
                    Picker("Record from", selection: $store.micDevice) {
                        Text("System Default (\(devices.defaultName))").tag("")
                        Divider()
                        ForEach(devices.devices) { d in
                            Text("\(d.name)  ·  \(d.kind)").tag(d.name)
                        }
                        if missing { Text("\(store.micDevice) (not connected)").tag(store.micDevice) }
                    }
                    .labelsHidden()
                    .frame(width: 280)
                }
                if missing {
                    HaloBanner(status: .warning,
                               title: "\(store.micDevice) is not connected",
                               message: "Halo will use the system default until it is plugged back in.")
                } else {
                    StateLabel(status: .ok,
                               text: store.micDevice.isEmpty
                                   ? "Using the system default"
                                   : "Using \(store.micDevice)")
                }
            }

            Block(title: "Level",
                  note: "Only while this pane is open does the Settings window itself listen. "
                      + "During dictation the engine owns the microphone.") {
                HStack(spacing: 10) {
                    LevelMeter(level: tester.level)
                        .frame(maxWidth: 320)
                        .frame(height: 10)
                    Text(tester.level > 0.85 ? "Loud" : "")
                        .font(HaloType.caption)
                        .foregroundStyle(HaloColor.text)
                        .frame(width: 40, alignment: .leading)
                }
                HStack(spacing: 8) {
                    Button(tester.recording ? "Recording…" : "Test recording (3 s)") { tester.record() }
                        .buttonStyle(.haloSecondary)
                        .disabled(!tester.running || tester.recording)
                    Button(tester.playing ? "Playing…" : "Play it back") { tester.play() }
                        .buttonStyle(.haloSecondary)
                        .disabled(!tester.hasRecording || tester.playing)
                }
                if let m = tester.message {
                    Note(text: m, failed: m.contains("silence") || m.contains("not") || m.contains("off"))
                }
            }

            Block(title: "Permission",
                  note: "Without it macOS hands Halo silence rather than an error.") {
                SettingRow(title: "Microphone access") {
                    HStack(spacing: 10) {
                        StateLabel(status: Permissions.microphoneChip.0, text: Permissions.microphoneChip.1)
                        if Permissions.microphone == .notDetermined {
                            Button("Allow") {
                                Permissions.requestMicrophone { _ in tester.start(deviceName: store.micDevice) }
                            }
                            .buttonStyle(.haloSmallPrimary)
                        } else if Permissions.microphone != .authorized {
                            Button("Open System Settings") { SystemSettings.open(.microphone) }
                                .buttonStyle(.haloSmall)
                        }
                    }
                }
            }
        }
        .onAppear {
            devices.start()
            tester.start(deviceName: store.micDevice)
        }
        .onDisappear { tester.stop() }
        .onChange(of: store.micDevice) { _, name in tester.start(deviceName: name) }
    }
}

struct LevelMeter: View {
    let level: Double

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(HaloColor.control)
                Capsule().strokeBorder(HaloColor.border, lineWidth: 1)
                Capsule()
                    .fill(level > 0.85 ? HaloColor.imperial : HaloColor.text)
                    .frame(width: max(4, geo.size.width * level))
                    .animation(.linear(duration: 0.08), value: level)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Input level")
        .accessibilityValue("\(Int((level * 100).rounded())) percent")
    }
}

enum SystemSettings {
    enum Pane: String {
        case microphone = "Privacy_Microphone"
        case accessibility = "Privacy_Accessibility"
        case inputMonitoring = "Privacy_ListenEvent"
    }

    static func open(_ pane: Pane) {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane.rawValue)") {
            NSWorkspace.shared.open(url)
        }
    }
}

// MARK: - Intelligence

struct IntelligencePane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI
    @ObservedObject var models = ModelsStore.shared

    private var selected: ModelsStore.Model? { models.cleanup.first { $0.id == store.localModel } }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Intelligence",
                      subtitle: "The optional language model, Context Awareness and Developer Mode — all on this Mac.")

            Block(title: "Where cleanup runs",
                  note: "Always on this Mac. With a model downloaded, Normal and Polished use it "
                      + "whenever it is ready and fall back to the local rules the moment it is "
                      + "not. Nothing you say is ever sent to a cloud service.") {
                RadioList(options: [
                    ("auto", "The model on this Mac, when ready", nil),
                    ("none", "Rules only, no model", nil),
                ], selection: $store.cleanupProvider, accessibilityName: "Where cleanup runs")
                RowDivider()
                DetailRow(title: "Language model", detail: localStatus) {
                    HStack(spacing: 10) {
                        StateLabel(status: localChip.0, text: localChip.1)
                        Button("Manage models") { ui.tab = .models }.buttonStyle(.haloSmall)
                    }
                }
            }

            Block(title: "Context Awareness",
                  note: "Halo looks at the app you are dictating into and a few hundred characters "
                      + "around the cursor, to spell names the way the screen does, skip the capital "
                      + "mid-sentence and pick the app's style. Held in memory for that one "
                      + "dictation, then cleared. Never reads password or other secure fields, "
                      + "never logs or saves the text, never sends it anywhere.") {
                ToggleRow(title: "Use context from the app you are dictating into",
                          isOn: $store.contextEnabled)
            }

            Block(title: "Developer Mode",
                  note: "Developer vocabulary (Supabase, SwiftUI, async/await), spoken case "
                      + "conventions (“camel case user id” → userId), file names, paths, flags, "
                      + "terminal commands, and names visible in your editor. Automatic turns it "
                      + "on in editors, terminals and developer sites.") {
                SegmentedChoice(options: [(tag: "auto", label: "Automatic"),
                                          (tag: "on", label: "Always on"),
                                          (tag: "off", label: "Off")],
                                selection: $store.developerMode,
                                accessibilityName: "Developer Mode")
                    .frame(maxWidth: 340)
            }

            Block(title: "Vocabulary learning",
                  note: "When you correct a word Halo typed (“Super Base” → “Supabase”), Halo "
                      + "notices and suggests adding it to your dictionary. Suggestions only — "
                      + "nothing is added without your click. Needs Context Awareness.") {
                ToggleRow(title: "Suggest words I correct", isOn: $store.learningEnabled,
                          disabled: !store.contextEnabled)
                if !store.contextEnabled {
                    InfoNote("Turn on Context Awareness to use this.")
                }
            }
        }
        .onAppear { models.refresh() }
    }

    private var localChip: (HaloStatus, String) {
        guard let m = selected else { return (.info, "No model chosen") }
        if !m.installed { return (.warning, "Not downloaded") }
        switch models.cleanupState {
        case "ready": return (.ok, "Ready")
        case "loading": return (.working, "Loading")
        case "failed": return (.error, "Failed")
        default: return (.info, "Downloaded")
        }
    }

    private var localStatus: String {
        guard let m = selected else { return "No local model chosen." }
        if !m.installed { return "\(m.id) is not downloaded — rules only until it is." }
        switch models.cleanupState {
        case "ready": return "\(m.id) is loaded and ready."
        case "loading": return "\(m.id) is loading…"
        case "failed": return "\(m.id) failed: \(models.cleanupDetail)"
        default: return "\(m.id) is downloaded — it loads when you next dictate."
        }
    }
}

// MARK: - Styles

struct StylesPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI
    @ObservedObject var styles = StylesStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Styles",
                      subtitle: "How Halo sounds in each kind of app. Stored in styles.json on this Mac; custom instructions go only to the local model.")

            if let e = styles.loadError { ProblemBanner(message: e).padding(.bottom, 12) }

            Block(title: "App-aware styles",
                  note: "A style's basic rules (closing full stop, lowercase, no em dashes) apply "
                      + "even without a model. Its instructions need the local model and Normal "
                      + "or Polished cleanup.") {
                ToggleRow(title: "Choose a writing style for each app", isOn: $store.stylesEnabled)
            }

            if !store.stylesEnabled {
                InfoNote("App-aware styles are off. Turn them on above to use the settings below.")
                    .padding(.bottom, 12)
            }

            Group {
                Block(title: "Style for each kind of app") {
                    ForEach(Array(StylesStore.categories.enumerated()), id: \.element.0) { i, cat in
                        if i > 0 { RowDivider() }
                        SettingRow(title: cat.1, detail: cat.2) {
                            Picker(cat.1, selection: Binding(
                                get: { styles.categories[cat.0] ?? "neutral" },
                                set: { styles.categories[cat.0] = $0; styles.save() })) {
                                ForEach(styles.all) { Text($0.name).tag($0.id) }
                            }
                            .labelsHidden()
                            .frame(width: 180)
                        }
                    }
                }

                Block(title: "Per-app overrides",
                      note: "An app's own style beats its category's. Use a bundle id (e.g. "
                          + "com.tinyspeck.slackmacgap) or host:docs.google.com for a website.") {
                    if styles.apps.isEmpty {
                        InfoNote("No overrides yet. Every app uses its category's style.")
                    }
                    ForEach(styles.apps.keys.sorted(), id: \.self) { key in
                        SettingRow(title: AppNames.label(key)) {
                            HStack(spacing: 6) {
                                Picker(AppNames.label(key), selection: Binding(
                                    get: { styles.apps[key] ?? "neutral" },
                                    set: { styles.apps[key] = $0; styles.save() })) {
                                    ForEach(styles.all) { Text($0.name).tag($0.id) }
                                }
                                .labelsHidden().frame(width: 180)
                                IconButton(symbol: "minus.circle",
                                           label: "Remove override for \(AppNames.label(key))") {
                                    styles.apps[key] = nil; styles.save()
                                }
                            }
                        }
                    }
                    RowDivider()
                    FieldLabel("Add an override")
                    HStack(spacing: 8) {
                        Picker("App", selection: $ui.newAppBundle) {
                            Text("Choose an app…").tag("")
                            ForEach(AppNames.running(), id: \.0) { Text($0.1).tag($0.0) }
                        }
                        .labelsHidden().frame(maxWidth: 230)
                        Picker("Style", selection: $ui.newAppStyle) {
                            ForEach(styles.all) { Text($0.name).tag($0.id) }
                        }
                        .labelsHidden().frame(maxWidth: 160)
                        Button("Add") {
                            styles.apps[ui.newAppBundle] = ui.newAppStyle
                            styles.save()
                            ui.newAppBundle = ""
                        }
                        .buttonStyle(.haloSmallPrimary)
                        .disabled(ui.newAppBundle.isEmpty)
                    }
                }

                Block(title: "Custom styles",
                      note: "Write instructions in plain English, e.g. “Never use em dashes. Use "
                          + "short paragraphs.” Start from a built-in to inherit its basic rules.") {
                    if styles.custom.isEmpty {
                        EmptyState(symbol: "textformat", title: "No custom styles yet",
                                   message: "A custom style lets Halo write the way you do in a given app — "
                                       + "for example, short paragraphs and no em dashes in email.") {
                            Button("New style") { ui.editingStyle = styles.create().id }
                                .buttonStyle(.haloSmallPrimary)
                        }
                    }
                    ForEach(styles.custom) { s in
                        CustomStyleRow(styles: styles, ui: ui, style: s)
                    }
                    if !styles.custom.isEmpty {
                        HStack(spacing: 8) {
                            Button("New style") { ui.editingStyle = styles.create().id }
                                .buttonStyle(.haloSmallPrimary)
                            duplicateMenu
                        }
                    } else {
                        duplicateMenu
                    }
                }

                Block(title: "Built-in styles") {
                    ForEach(Array(StylesStore.builtins.enumerated()), id: \.element.id) { i, s in
                        if i > 0 { RowDivider() }
                        VStack(alignment: .leading, spacing: 2) {
                            Text(s.name).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
                            Support(s.instructions)
                        }
                    }
                }
            }
            .disabled(!store.stylesEnabled)
            .opacity(store.stylesEnabled ? 1 : 0.5)
        }
    }

    private var duplicateMenu: some View {
        Menu("Duplicate a built-in") {
            ForEach(StylesStore.builtins) { b in
                Button(b.name) { ui.editingStyle = styles.create(from: b).id }
            }
        }
        .fixedSize()
    }
}

struct CustomStyleRow: View {
    @ObservedObject var styles: StylesStore
    @ObservedObject var ui: SettingsUI
    let style: StylesStore.Style

    private var editing: Bool { ui.editingStyle == style.id }

    private func binding<T>(_ key: WritableKeyPath<StylesStore.Style, T>) -> Binding<T> {
        Binding(get: { (styles.custom.first { $0.id == style.id } ?? style)[keyPath: key] },
                set: { v in
                    guard var s = styles.custom.first(where: { $0.id == style.id }) else { return }
                    s[keyPath: key] = v
                    styles.update(s)
                })
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 8) {
                    heading
                    Spacer(minLength: 8)
                    actions
                }
                VStack(alignment: .leading, spacing: 8) {
                    heading
                    actions
                }
            }
            if editing {
                FieldLabel("Name")
                TextField("Name", text: binding(\.name)).textFieldStyle(.halo)
                    .frame(maxWidth: 320)
                if binding(\.name).wrappedValue.trimmingCharacters(in: .whitespaces).isEmpty {
                    Note(text: "Give the style a name so you can pick it.", failed: true)
                }
                SettingRow(title: "Starts from") {
                    Picker("Starts from", selection: binding(\.base)) {
                        ForEach(StylesStore.builtins) { Text($0.name).tag($0.id) }
                    }
                    .labelsHidden()
                    .frame(width: 200)
                }
                FieldLabel("Instructions")
                HaloTextEditor(text: binding(\.instructions), label: "Instructions")
                if binding(\.instructions).wrappedValue.trimmingCharacters(in: .whitespaces).isEmpty {
                    InfoNote("With no instructions, only the basic rules of the style it starts from apply.")
                }
            } else if !style.instructions.isEmpty {
                Text(style.instructions).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                    .lineLimit(2)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius).fill(HaloColor.control))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
            .strokeBorder(editing ? HaloColor.accentText : HaloColor.subtleBorder,
                          lineWidth: editing ? 1.5 : 1))
    }

    private var heading: some View {
        HStack(spacing: 8) {
            Text(style.name.isEmpty ? "Untitled style" : style.name)
                .font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
            Text("based on \(styles.name(of: style.base))")
                .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
        }
    }

    private var actions: some View {
        HStack(spacing: 6) {
            Button(editing ? "Done" : "Edit") { ui.editingStyle = editing ? nil : style.id }
                .buttonStyle(.haloSmall)
            Button("Duplicate") { ui.editingStyle = styles.create(from: style).id }
                .buttonStyle(.haloSmall)
            Button(role: .destructive) { styles.delete(style.id) } label: {
                Label("Delete", systemImage: "trash")
            }
            .buttonStyle(.haloDestructive)
        }
    }
}

/// Friendly names for bundle ids, from whatever is installed or running.
enum AppNames {
    static func label(_ key: String) -> String {
        if key.hasPrefix("host:") { return String(key.dropFirst(5)) + " (website)" }
        if let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: key) {
            return FileManager.default.displayName(atPath: url.path)
                .replacingOccurrences(of: ".app", with: "")
        }
        return key
    }

    /// Regular apps that are running now, as (bundle id, name).
    static func running() -> [(String, String)] {
        NSWorkspace.shared.runningApplications
            .filter { $0.activationPolicy == .regular }
            .compactMap { app in
                guard let id = app.bundleIdentifier, id != Bundle.main.bundleIdentifier else { return nil }
                return (id, app.localizedName ?? id)
            }
            .sorted { $0.1.localizedCaseInsensitiveCompare($1.1) == .orderedAscending }
    }
}
