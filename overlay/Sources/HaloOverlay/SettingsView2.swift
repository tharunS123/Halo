import AppKit
import AVFoundation
import SwiftUI

// MARK: - Microphone

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
                Picker("Record from", selection: $store.micDevice) {
                    Text("System Default (\(devices.defaultName))").tag("")
                    Divider()
                    ForEach(devices.devices) { d in
                        Text("\(d.name)  ·  \(d.kind)").tag(d.name)
                    }
                    if missing { Text("\(store.micDevice) (not connected)").tag(store.micDevice) }
                }
                .frame(width: 420)
                if missing {
                    Label("\(store.micDevice) is not connected — Halo will use the system default.",
                          systemImage: "exclamationmark.triangle.fill")
                        .font(.system(size: 11)).foregroundStyle(.orange)
                }
            }

            Block(title: "Level",
                  note: "Only while this pane is open does the Settings window itself listen. "
                      + "During dictation the engine owns the microphone.") {
                LevelMeter(level: tester.level)
                    .frame(width: 320, height: 10)
                HStack(spacing: 8) {
                    Button(tester.recording ? "Recording…" : "Test recording (3 s)") { tester.record() }
                        .disabled(!tester.running || tester.recording)
                    Button(tester.playing ? "Playing…" : "Play it back") { tester.play() }
                        .disabled(!tester.hasRecording || tester.playing)
                }
                if let m = tester.message {
                    Note(text: m, failed: m.contains("silence") || m.contains("not") || m.contains("off"))
                }
            }

            Block(title: "Permission",
                  note: "Without it macOS hands Halo silence rather than an error.") {
                HStack(spacing: 8) {
                    StatusDot(ok: Permissions.microphone == .authorized,
                              warn: Permissions.microphone == .notDetermined)
                    Text("Microphone access: \(Permissions.microphoneText)").font(.system(size: 12))
                    Spacer()
                    if Permissions.microphone == .notDetermined {
                        Button("Allow") {
                            Permissions.requestMicrophone { _ in tester.start(deviceName: store.micDevice) }
                        }
                    } else if Permissions.microphone != .authorized {
                        Button("Open System Settings") { SystemSettings.open(.microphone) }
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
                Capsule().fill(Color.primary.opacity(0.08))
                Capsule()
                    .fill(LinearGradient(colors: [.green, level > 0.85 ? .orange : .green],
                                         startPoint: .leading, endPoint: .trailing))
                    .frame(width: max(4, geo.size.width * level))
                    .animation(.linear(duration: 0.08), value: level)
            }
        }
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
                  note: "Automatic uses the model on this Mac when one is downloaded, then "
                      + "OpenRouter if you allow it in Privacy, and otherwise the local rules. A "
                      + "downloaded model that is still loading never hands your text to "
                      + "OpenRouter instead.") {
                Picker("", selection: $store.cleanupProvider) {
                    Text("Automatic").tag("auto")
                    Text("This Mac only").tag("local")
                    Text("OpenRouter").tag("openrouter")
                    Text("Rules only, no model").tag("none")
                }
                .pickerStyle(.radioGroup)
                .labelsHidden()
                HStack(spacing: 8) {
                    StatusDot(ok: models.cleanupState == "ready",
                              warn: selected?.installed == true && models.cleanupState != "failed")
                    Text(localStatus).font(.system(size: 12))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("Manage models") { ui.tab = .models }.controlSize(.small)
                }
            }

            Block(title: "Context Awareness",
                  note: "Halo looks at the app you are dictating into and a few hundred characters "
                      + "around the cursor, to spell names the way the screen does, skip the capital "
                      + "mid-sentence and pick the app's style. Held in memory for that one "
                      + "dictation, then cleared. Never reads password or other secure fields, "
                      + "never logs or saves the text, never sends it anywhere.") {
                Toggle("Use context from the app you are dictating into", isOn: $store.contextEnabled)
            }

            Block(title: "Developer Mode",
                  note: "Developer vocabulary (Supabase, SwiftUI, async/await), spoken case "
                      + "conventions (“camel case user id” → userId), file names, paths, flags, "
                      + "terminal commands, and names visible in your editor. Automatic turns it "
                      + "on in editors, terminals and developer sites.") {
                Picker("", selection: $store.developerMode) {
                    Text("Automatic").tag("auto")
                    Text("Always on").tag("on")
                    Text("Off").tag("off")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 300)
            }

            Block(title: "Vocabulary learning",
                  note: "When you correct a word Halo typed (“Super Base” → “Supabase”), Halo "
                      + "notices and suggests adding it to your dictionary. Suggestions only — "
                      + "nothing is added without your click. Needs Context Awareness.") {
                Toggle("Suggest words I correct", isOn: $store.learningEnabled)
                    .disabled(!store.contextEnabled)
            }
        }
        .onAppear { models.refresh() }
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
                Toggle("Choose a writing style for each app", isOn: $store.stylesEnabled)
            }

            Group {
                Block(title: "Style for each kind of app") {
                    ForEach(StylesStore.categories, id: \.0) { cat in
                        HStack {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(cat.1).font(.system(size: 12))
                                Text(cat.2).font(.system(size: 10)).foregroundStyle(.secondary)
                            }
                            .frame(width: 260, alignment: .leading)
                            Picker("", selection: Binding(
                                get: { styles.categories[cat.0] ?? "neutral" },
                                set: { styles.categories[cat.0] = $0; styles.save() })) {
                                ForEach(styles.all) { Text($0.name).tag($0.id) }
                            }
                            .labelsHidden()
                            .frame(width: 200)
                        }
                    }
                }

                Block(title: "Per-app overrides",
                      note: "An app's own style beats its category's. Use a bundle id (e.g. "
                          + "com.tinyspeck.slackmacgap) or host:docs.google.com for a website.") {
                    ForEach(styles.apps.keys.sorted(), id: \.self) { key in
                        HStack {
                            Text(AppNames.label(key)).font(.system(size: 12))
                                .frame(width: 260, alignment: .leading)
                            Picker("", selection: Binding(
                                get: { styles.apps[key] ?? "neutral" },
                                set: { styles.apps[key] = $0; styles.save() })) {
                                ForEach(styles.all) { Text($0.name).tag($0.id) }
                            }
                            .labelsHidden().frame(width: 200)
                            Button { styles.apps[key] = nil; styles.save() } label: {
                                Image(systemName: "minus.circle")
                            }
                            .buttonStyle(.borderless)
                        }
                    }
                    HStack {
                        Picker("", selection: $ui.newAppBundle) {
                            Text("Choose an app…").tag("")
                            ForEach(AppNames.running(), id: \.0) { Text($0.1).tag($0.0) }
                        }
                        .labelsHidden().frame(width: 260)
                        Picker("", selection: $ui.newAppStyle) {
                            ForEach(styles.all) { Text($0.name).tag($0.id) }
                        }
                        .labelsHidden().frame(width: 200)
                        Button("Add") {
                            styles.apps[ui.newAppBundle] = ui.newAppStyle
                            styles.save()
                            ui.newAppBundle = ""
                        }
                        .disabled(ui.newAppBundle.isEmpty)
                    }
                }

                Block(title: "Custom styles",
                      note: "Write instructions in plain English, e.g. “Never use em dashes. Use "
                          + "short paragraphs.” Start from a built-in to inherit its basic rules.") {
                    ForEach(styles.custom) { s in
                        CustomStyleRow(styles: styles, ui: ui, style: s)
                    }
                    HStack {
                        Button("New style") { ui.editingStyle = styles.create().id }
                        Menu("Duplicate a built-in") {
                            ForEach(StylesStore.builtins) { b in
                                Button(b.name) { ui.editingStyle = styles.create(from: b).id }
                            }
                        }
                        .frame(width: 180)
                    }
                }

                Block(title: "Built-in styles") {
                    ForEach(StylesStore.builtins) { s in
                        HStack(alignment: .top) {
                            Text(s.name).font(.system(size: 12, weight: .medium))
                                .frame(width: 140, alignment: .leading)
                            Text(s.instructions).font(.system(size: 11)).foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .disabled(!store.stylesEnabled)
            .opacity(store.stylesEnabled ? 1 : 0.45)
        }
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
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(style.name).font(.system(size: 12, weight: .medium))
                Text("based on \(styles.name(of: style.base))")
                    .font(.system(size: 10)).foregroundStyle(.secondary)
                Spacer()
                Button(editing ? "Done" : "Edit") { ui.editingStyle = editing ? nil : style.id }
                    .controlSize(.small)
                Button("Duplicate") { ui.editingStyle = styles.create(from: style).id }
                    .controlSize(.small)
                Button("Delete", role: .destructive) { styles.delete(style.id) }
                    .controlSize(.small)
            }
            if editing {
                TextField("Name", text: binding(\.name)).textFieldStyle(.roundedBorder)
                    .frame(width: 300)
                Picker("Starts from", selection: binding(\.base)) {
                    ForEach(StylesStore.builtins) { Text($0.name).tag($0.id) }
                }
                .frame(width: 300)
                Text("Instructions").font(.system(size: 11, weight: .semibold))
                TextEditor(text: binding(\.instructions))
                    .font(.system(size: 12))
                    .frame(height: 70)
                    .overlay(RoundedRectangle(cornerRadius: 5).stroke(Color.primary.opacity(0.15)))
            } else if !style.instructions.isEmpty {
                Text(style.instructions).font(.system(size: 11)).foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 6).fill(Color.primary.opacity(0.04)))
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
