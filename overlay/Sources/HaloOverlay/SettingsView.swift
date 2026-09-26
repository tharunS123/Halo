import AppKit
import SwiftUI

/// The Settings window's contents.
///
/// Written with plain `ObservableObject` + `@ObservedObject` throughout --
/// no `@State`, no `@Observable`, no `#Preview` -- because Halo must build
/// with the Command Line Tools alone. In a current SDK `@State` is a macro
/// backed by a compiler plugin that only ships with Xcode, so a single
/// `@State private var` fails the build with "external macro implementation
/// type 'SwiftUIMacros.StateMacro' could not be found".
///
/// That is not a theoretical constraint: the Homebrew formula builds this app
/// from source on the user's machine, where Xcode may well be absent, and CI
/// runs `xcode-select -s /Library/Developer/CommandLineTools` before building
/// precisely to catch a macro sneaking back in. View-local state therefore
/// lives in `SettingsUI` below.
///
/// Twelve sections, so a sidebar rather than the old tab strip. Each pane is
/// in SettingsView*.swift by theme.
struct SettingsView: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    enum Tab: String, CaseIterable {
        case general = "General"
        case dictation = "Dictation"
        case microphone = "Microphone"
        case intelligence = "Intelligence"
        case styles = "Styles"
        case dictionary = "Dictionary"
        case commands = "Commands"
        case models = "Models"
        case history = "History"
        case privacy = "Privacy"
        case permissions = "Permissions"
        case advanced = "Advanced"

        /// What `halo settings <tab>` accepts.
        var key: String { rawValue.lowercased() }

        var icon: String {
            switch self {
            case .general: return "gearshape"
            case .dictation: return "text.quote"
            case .microphone: return "mic"
            case .intelligence: return "sparkles"
            case .styles: return "textformat"
            case .dictionary: return "character.book.closed"
            case .commands: return "wand.and.stars"
            case .models: return "shippingbox"
            case .history: return "clock.arrow.circlepath"
            case .privacy: return "lock.shield"
            case .permissions: return "hand.raised"
            case .advanced: return "wrench.and.screwdriver"
            }
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Divider()
            VStack(spacing: 0) {
                if let problem = store.loadError {
                    ProblemBanner(message: problem)
                    Divider()
                }
                ScrollView {
                    pane
                        .padding(20)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Divider()
                footer
            }
        }
        .frame(minWidth: 760, minHeight: 520)
    }

    @ViewBuilder
    private var pane: some View {
        switch ui.tab {
        case .general: GeneralPane(store: store, ui: ui)
        case .dictation: DictationPane(store: store, ui: ui)
        case .microphone: MicrophonePane(store: store)
        case .intelligence: IntelligencePane(store: store, ui: ui)
        case .styles: StylesPane(store: store, ui: ui)
        case .dictionary: DictionaryPane(ui: ui)
        case .commands: CommandsPane(store: store, ui: ui)
        case .models: ModelsPane(store: store)
        case .history: HistoryPane(store: store, ui: ui)
        case .privacy: PrivacyPane(store: store, ui: ui)
        case .permissions: PermissionsPane()
        case .advanced: AdvancedPane(store: store, ui: ui)
        }
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(Tab.allCases, id: \.self) { t in
                Button {
                    ui.tab = t
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: t.icon)
                            .font(.system(size: 13))
                            .frame(width: 18)
                        Text(t.rawValue).font(.system(size: 12.5))
                        Spacer()
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(ui.tab == t ? Color.accentColor.opacity(0.18) : .clear))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(ui.tab == t ? Color.accentColor : Color.primary)
            }
            Spacer()
        }
        .padding(10)
        .frame(width: 176)
        .background(Color.primary.opacity(0.03))
    }

    /// Every change here lands in ~/.config/halo. Saying so is the honest
    /// version of a Save button this window does not need.
    private var footer: some View {
        HStack {
            Text("Saved to ~/.config/halo — picked up within a second.")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
            Spacer()
            Button("Reveal in Finder") {
                NSWorkspace.shared.selectFile(
                    SettingsStore.settingsURL.path,
                    inFileViewerRootedAtPath: SettingsStore.configDir.path)
            }
            .controlSize(.small)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }
}

// MARK: - Shared bits

/// A labelled group with a short explanation underneath, used everywhere so
/// the panes read consistently.
struct Block<Content: View>: View {
    let title: String
    var note: String? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.system(size: 13, weight: .semibold))
            content
            if let note {
                Text(note)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.bottom, 18)
    }
}

struct PaneTitle: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.system(size: 18, weight: .semibold))
            Text(subtitle).font(.system(size: 11.5)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 16)
    }
}

struct ProblemBanner: View {
    let message: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(message).font(.system(size: 11, weight: .medium))
                Text("Nothing here will save until that file parses — fixing it by hand is "
                     + "safer than letting this window overwrite it.")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Reveal") {
                NSWorkspace.shared.selectFile(SettingsStore.settingsURL.path,
                                              inFileViewerRootedAtPath: SettingsStore.configDir.path)
            }
            .controlSize(.small)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.orange.opacity(0.12))
    }
}

struct StatusDot: View {
    let ok: Bool
    var warn = false

    var body: some View {
        Circle()
            .fill(ok ? Color.green : (warn ? Color.orange : Color.red))
            .frame(width: 8, height: 8)
    }
}

struct Note: View {
    let text: String
    var failed = false

    var body: some View {
        Text(text)
            .font(.system(size: 11))
            .foregroundStyle(failed ? Color.orange : Color.green)
            .fixedSize(horizontal: false, vertical: true)
    }
}

enum Hotkeys {
    // Only keys pynput can actually bind, so the picker cannot produce a
    // hotkey the engine will reject at startup.
    static let all = ["f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
                      "f13", "f14", "f15", "f16", "f17", "f18", "f19"]
}

// MARK: - General

struct GeneralPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "General", subtitle: "Starting Halo, the menu bar, the orb and sounds.")

            Block(title: "Launch at login",
                  note: LoginItem.legacyInstalled
                    ? "Currently started by the login agent `halo setup` installed. Turning "
                      + "this off removes it; turning it on again uses a macOS login item."
                    : "Uses a macOS login item, listed in System Settings › General › Login Items.") {
                Toggle("Launch Halo at login", isOn: Binding(
                    get: { ui.loginEnabled },
                    set: { on in
                        ui.loginMessage = LoginItem.set(on)
                        ui.loginEnabled = LoginItem.enabled
                    }))
                Text(LoginItem.mechanism).font(.system(size: 11)).foregroundStyle(.secondary)
                if let m = ui.loginMessage { Note(text: m, failed: true) }
            }

            Block(title: "Menu bar",
                  note: "Off by default: the hotkey is meant to be the whole interface. "
                      + "`halo settings` opens this window whether or not the icon is showing.") {
                Toggle("Show a Halo icon in the menu bar", isOn: $store.menuBar)
            }

            Block(title: "The orb",
                  note: "The orb never opens the microphone and never takes keyboard focus — it "
                      + "cannot intercept a click or a keystroke meant for the app you are in.") {
                Toggle("Show the orb while dictating", isOn: $store.overlayEnabled)
                Group {
                    HStack {
                        Text("Size")
                        Slider(value: $store.orbScale, in: 0.6...1.6).frame(width: 200)
                        Text("\(Int((store.orbScale * 100).rounded()))%")
                            .font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
                    }
                    Picker("Corner", selection: $store.orbPosition) {
                        Text("Bottom center").tag("bottom")
                        Text("Bottom left").tag("bottom-left")
                        Text("Bottom right").tag("bottom-right")
                        Text("Top center").tag("top")
                        Text("Top left").tag("top-left")
                        Text("Top right").tag("top-right")
                    }
                    .frame(width: 280)
                    HStack {
                        Text("Distance from that edge")
                        Slider(value: $store.orbInset, in: 20...400).frame(width: 180)
                        Text("\(Int(store.orbInset)) pt")
                            .font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
                    }
                    Toggle("Keep the orb visible while transcribing", isOn: $store.orbWhileProcessing)
                }
                .disabled(!store.overlayEnabled)
                .opacity(store.overlayEnabled ? 1 : 0.4)
            }

            Block(title: "Sounds",
                  note: "A soft tick when recording starts and a pop when the text lands.") {
                Toggle("Play sounds", isOn: $store.sounds)
            }

            Block(title: "Setup guide",
                  note: "The first-run walkthrough: permissions, microphone, model, language, "
                      + "shortcut and a test dictation.") {
                Button("Open the setup guide") { OnboardingWindowController.shared.show() }
            }
        }
        .onAppear { ui.loginEnabled = LoginItem.enabled }
    }
}

// MARK: - Dictation

struct DictationPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    static let modes: [(String, String, String)] = [
        ("off", "Off", "Exactly what whisper heard, with your vocabulary applied."),
        ("verbatim", "Verbatim",
         "Spoken punctuation and spacing only. Nothing you said is removed."),
        ("light", "Light",
         "Also removes “um” and stumbles like “the the”, adds capitals, a closing "
            + "full stop and obvious question marks."),
        ("normal", "Normal",
         "Also resolves self-corrections (“Thursday — actually Friday”), formats "
            + "lists, numbers, dates, money, emails and links, and — if a language "
            + "model is ready — repairs grammar without rewording you."),
        ("polished", "Polished",
         "Like Normal, but a language model may reword for readability. It is "
            + "checked so it can never add names, numbers or facts you did not say."),
    ]

    private var smart: Bool { store.cleanupMode == "normal" || store.cleanupMode == "polished" }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Dictation", subtitle: "The shortcut, how much Halo tidies up, and your languages.")

            Block(title: "Push-to-talk shortcut",
                  note: "F13–F19 exist only on full-size keyboards. On a MacBook, F-keys may be "
                      + "brightness or media keys unless you hold fn — the setup guide can test yours.") {
                Picker("Dictation key", selection: $store.hotkey) {
                    ForEach(Hotkeys.all, id: \.self) { Text($0.uppercased()).tag($0) }
                }
                .frame(width: 260)
            }

            Block(title: "Recording mode",
                  note: store.activation == "toggle"
                    ? "Press once to start, press again to send. Escape cancels at any stage."
                    : "Recording lasts exactly as long as the key is down, so the microphone "
                      + "can never be left open. Escape cancels at any stage.") {
                Picker("", selection: $store.activation) {
                    Text("Press and hold").tag("hold")
                    Text("Press to start, press again to send").tag("toggle")
                }
                .pickerStyle(.radioGroup)
                .labelsHidden()
                if store.activation == "toggle" {
                    Stepper(value: $store.maxRecordingSec, in: 10...600, step: 10) {
                        Text("Stop automatically after \(store.maxRecordingSec) seconds").monospacedDigit()
                    }
                    .padding(.leading, 20)
                }
            }

            Block(title: "Cleanup level",
                  note: Self.modes.first { $0.0 == store.cleanupMode }?.2 ?? "") {
                Picker("", selection: $store.cleanupMode) {
                    ForEach(Self.modes, id: \.0) { Text($0.1).tag($0.0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 440)
            }

            LanguageBlock(store: store)

            Block(title: "Smart formatting and backtrack",
                  note: "Normal and Polished only. If a language model is missing, loading, slow "
                      + "or wrong, Halo types the rule-based result instead.") {
                Toggle("Fix self-corrections (“send it to John — no, Jake”)",
                       isOn: $store.selfCorrection)
                Toggle("Format numbers, dates, times, money, phone numbers, emails, links and lists",
                       isOn: $store.smartFormatting)
                Toggle("End short chat messages with a full stop", isOn: $store.chatPeriod)
            }
            .disabled(!smart)
            .opacity(smart ? 1 : 0.4)

            Block(title: "Spoken punctuation",
                  note: "Say “comma”, “question mark”, “new line”, “open paren”. Ambiguous words "
                      + "are left alone when they read as ordinary speech.") {
                Toggle("Turn spoken punctuation into marks", isOn: $store.spokenPunctuation)
                Toggle("Remove “um”, “uh” and “er”", isOn: $store.stripFillers)
                Toggle("End each utterance with a full stop", isOn: $store.terminalPunctuation)
            }

            Block(title: "Accuracy",
                  note: "Priming tells whisper your vocabulary and what you just said before it "
                      + "decodes — the biggest accuracy win available without a larger model.") {
                Toggle("Prime whisper with your vocabulary and recent context", isOn: $store.whisperPrompt)
                Toggle("Suppress non-speech tokens ([BLANK_AUDIO], (music))", isOn: $store.suppressNST)
            }
        }
    }
}

struct LanguageBlock: View {
    @ObservedObject var store: SettingsStore

    var body: some View {
        Block(title: "Languages",
              note: "Say “switch to Spanish” (or use the menu bar) to change on the fly. Any "
                  + "language but English needs the multilingual speech model (Settings › Models). "
                  + "Self-correction and number formatting are English-only for now.") {
            Picker("Preferred language", selection: Binding(
                get: { store.language }, set: { store.setLanguage($0) })) {
                Text("Detect automatically").tag("auto")
                Divider()
                ForEach(LanguageInfo.all, id: \.0) { Text($0.1).tag($0.0) }
            }
            .frame(width: 320)
            Text("Languages you use").font(.system(size: 11, weight: .semibold)).padding(.top, 4)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), alignment: .leading)],
                      alignment: .leading, spacing: 4) {
                ForEach(LanguageInfo.all, id: \.0) { lang in
                    Toggle(lang.1, isOn: Binding(
                        get: { store.enabledLanguages.contains(lang.0) },
                        set: { on in
                            var list = store.enabledLanguages.filter { $0 != lang.0 }
                            if on { list.append(lang.0) }
                            store.enabledLanguages = list.isEmpty ? ["en"] : list
                        }))
                    .toggleStyle(.checkbox)
                }
            }
            ForEach(store.enabledLanguages.filter { !LanguageInfo.regions($0).isEmpty }, id: \.self) { code in
                Picker("\(LanguageInfo.name(code)) variant", selection: Binding(
                    get: { store.regions[code] ?? "" },
                    set: { store.regions[code] = $0.isEmpty ? nil : $0 })) {
                    Text("Default").tag("")
                    ForEach(LanguageInfo.regions(code), id: \.self) { Text($0).tag($0) }
                }
                .frame(width: 320)
            }
            let recent = store.recentLanguages()
            if !recent.isEmpty {
                HStack(spacing: 6) {
                    Text("Recent:").font(.system(size: 11)).foregroundStyle(.secondary)
                    ForEach(recent, id: \.self) { code in
                        Button(LanguageInfo.name(code)) { store.setLanguage(code) }
                            .controlSize(.small)
                    }
                }
            }
        }
    }
}

/// View-local state for the Settings window.
///
/// This exists only because `@State` is a macro the Command Line Tools cannot
/// expand (see the note on `SettingsView`). It holds nothing persistent --
/// everything durable lives in the stores and, through them, on disk.
@MainActor
final class SettingsUI: ObservableObject {
    @Published var tab: SettingsView.Tab = .general
    @Published var loginEnabled = false
    @Published var loginMessage: String?
    @Published var dictQuery = ""
    @Published var editingEntry: UUID?
    @Published var editingStyle: String?
    @Published var editingTransform: String?
    @Published var newAppBundle = ""
    @Published var newAppStyle = "neutral"
    @Published var confirmClearHistory = false
    @Published var confirmReset = false
    @Published var health: [String: String] = [:]
    @Published var healthError: String?
    @Published var dataMessage: String?
}
