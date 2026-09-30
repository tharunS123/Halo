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

    /// The grouped navigation. Order and grouping follow the design plan; the
    /// tabs, their names and `halo settings <tab>` routing are unchanged.
    static let groups: [(title: String, tabs: [Tab])] = [
        ("Everyday", [.general, .dictation, .microphone]),
        ("Personalize", [.intelligence, .styles, .dictionary, .commands]),
        ("Library", [.models, .history]),
        ("System", [.privacy, .permissions, .advanced]),
    ]

    var body: some View {
        HStack(spacing: 0) {
            sidebar
            Rectangle().fill(HaloColor.subtleBorder).frame(width: 1)
                .ignoresSafeArea(edges: .vertical)
            VStack(spacing: 0) {
                if let problem = store.loadError {
                    ProblemBanner(message: problem)
                    Rectangle().fill(HaloColor.subtleBorder).frame(height: 1)
                }
                GeometryReader { geo in
                    ScrollView {
                        pane
                            .padding(geo.size.width < 660 ? HaloMetrics.compactPadding
                                                          : HaloMetrics.contentPadding)
                            .frame(maxWidth: 820, alignment: .leading)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .id(ui.tab)
                }
                Rectangle().fill(HaloColor.subtleBorder).frame(height: 1)
                footer
            }
            .background(HaloColor.background.ignoresSafeArea())
        }
        .frame(minWidth: 760, minHeight: 520)
        .background(HaloColor.background.ignoresSafeArea())
        .tint(HaloColor.imperial)
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
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    HaloMark(size: 28)
                    HaloWordmark(height: 20)
                }
                Text("Your voice. Your Mac.")
                    .font(HaloType.brand(13))
                    .foregroundStyle(HaloColor.secondaryText)
            }
            .padding(.horizontal, 16)
            .padding(.top, 10)
            .padding(.bottom, 14)

            // Scrolls when the window is short or the text is large.
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(Self.groups, id: \.title) { group in
                        VStack(alignment: .leading, spacing: 2) {
                            GroupLabel(text: group.title)
                                .padding(.horizontal, 10)
                                .padding(.bottom, 3)
                            ForEach(group.tabs, id: \.self) { navRow($0) }
                        }
                    }
                }
                .padding(.horizontal, 10)
                .padding(.bottom, 10)
            }

            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 10))
                    .accessibilityHidden(true)
                Text("All processing on this Mac")
                    .font(HaloType.body(11.5, .medium))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .foregroundStyle(HaloColor.secondaryText)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
        }
        .frame(width: HaloMetrics.sidebarWidth)
        .background(HaloColor.sidebar.ignoresSafeArea(edges: .vertical))
    }

    /// A selected row has a fill, a leading bar and bolder text, so selection is
    /// never only a color.
    private func navRow(_ t: Tab) -> some View {
        let on = ui.tab == t
        return Button {
            ui.tab = t
        } label: {
            HStack(spacing: 8) {
                Image(systemName: t.icon)
                    .font(.system(size: 13))
                    .frame(width: 18)
                    .accessibilityHidden(true)
                Text(t.rawValue).font(HaloType.body(13, on ? .semibold : .regular))
                Spacer(minLength: 0)
            }
            .foregroundStyle(on ? HaloColor.accentText : HaloColor.text)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 6).fill(on ? HaloColor.selection : .clear))
            .overlay(alignment: .leading) {
                if on {
                    Capsule().fill(HaloColor.imperial).frame(width: 3, height: 16).padding(.leading, 2)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(t.rawValue)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// Every change here lands in ~/.config/halo. Saying so is the honest
    /// version of a Save button this window does not need.
    private var footer: some View {
        ViewThatFits(in: .horizontal) {
            HStack {
                footerText
                Spacer()
                revealButton
            }
            VStack(alignment: .leading, spacing: 6) {
                footerText
                revealButton
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    private var footerText: some View {
        Text("Saved to ~/.config/halo — picked up within a second.")
            .font(HaloType.support)
            .foregroundStyle(HaloColor.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var revealButton: some View {
        Button("Reveal in Finder") {
            NSWorkspace.shared.selectFile(
                SettingsStore.settingsURL.path,
                inFileViewerRootedAtPath: SettingsStore.configDir.path)
        }
        .buttonStyle(.haloSmall)
    }
}

// MARK: - Shared bits

/// A labelled group on a card, with a short explanation underneath. Used
/// everywhere so the panes read consistently.
struct Block<Content: View>: View {
    let title: String
    var note: String? = nil
    @ViewBuilder var content: Content

    var body: some View {
        HaloCard {
            Text(title).font(HaloType.sectionTitle).foregroundStyle(HaloColor.text)
                .accessibilityAddTraits(.isHeader)
            content
                .font(HaloType.control)
            if let note {
                Text(note)
                    .font(HaloType.support)
                    .foregroundStyle(HaloColor.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.bottom, 14)
    }
}

struct PaneTitle: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(HaloType.pageTitle).foregroundStyle(HaloColor.text)
                .accessibilityAddTraits(.isHeader)
            Text(subtitle).font(HaloType.control).foregroundStyle(HaloColor.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 18)
    }
}

struct ProblemBanner: View {
    let message: String

    var body: some View {
        HaloBanner(status: .warning, title: message,
                   message: "Nothing here will save until that file parses — fixing it by hand "
                       + "is safer than letting this window overwrite it.") {
            Button("Reveal") {
                NSWorkspace.shared.selectFile(SettingsStore.settingsURL.path,
                                              inFileViewerRootedAtPath: SettingsStore.configDir.path)
            }
            .buttonStyle(.haloSecondary)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }
}

/// Ready / attention / problem, as a symbol -- never a colored dot alone.
struct StatusDot: View {
    let ok: Bool
    var warn = false

    private var status: HaloStatus { ok ? .ok : (warn ? .warning : .error) }

    var body: some View {
        Image(systemName: status.symbol)
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(status.tint)
            .accessibilityLabel(status.spoken)
    }
}

/// A one-line result under a control: a symbol and the words.
struct Note: View {
    let text: String
    var failed = false

    var body: some View {
        Label {
            Text(text).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: failed ? HaloStatus.warning.symbol : HaloStatus.ok.symbol)
                .foregroundStyle(failed ? HaloColor.imperial : HaloColor.text)
        }
        .font(HaloType.support)
        .foregroundStyle(HaloColor.text)
    }
}

enum Hotkeys {
    // Only keys pynput can actually bind, so the picker cannot produce a
    // hotkey the engine will reject at startup.
    static let all = ["f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
                      "f13", "f14", "f15", "f16", "f17", "f18", "f19"]

    /// How to press `key` on a Mac keyboard. F5–F12 are brightness and media
    /// keys on a MacBook unless fn is held, so say so; F13–F19 only exist on
    /// full-size keyboards, where they need nothing extra.
    static func press(_ key: String, shift: Bool = false) -> String {
        let name = key.uppercased()
        let needsFn = (Int(key.dropFirst()) ?? 0) <= 12
        return (needsFn ? "fn + " : "") + (shift ? "Shift + " : "") + name
    }
}

// MARK: - General

struct GeneralPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "General", subtitle: "Starting Halo, the menu bar, the orb and sounds.")

            Block(title: "Startup") {
                ToggleRow(title: "Launch Halo at login",
                          detail: LoginItem.legacyInstalled
                            ? "Currently started by the login agent `halo setup` installed. Turning "
                              + "this off removes it; turning it on again uses a macOS login item."
                            : "Uses a macOS login item, listed in System Settings › General › Login Items.",
                          isOn: Binding(
                            get: { ui.loginEnabled },
                            set: { on in
                                ui.loginMessage = LoginItem.set(on)
                                ui.loginEnabled = LoginItem.enabled
                            }))
                Text(LoginItem.mechanism).font(HaloType.mono(11, .regular))
                    .foregroundStyle(HaloColor.secondaryText)
                if let m = ui.loginMessage { Note(text: m, failed: true) }
                RowDivider()
                ToggleRow(title: "Show a Halo icon in the menu bar",
                          detail: "Off by default: the hotkey is meant to be the whole interface. "
                              + "`halo settings` opens this window whether or not the icon is showing.",
                          isOn: $store.menuBar)
            }

            Block(title: "The orb",
                  note: "The orb never opens the microphone and never takes keyboard focus — it "
                      + "cannot intercept a click or a keystroke meant for the app you are in.") {
                ToggleRow(title: "Show the orb while dictating", isOn: $store.overlayEnabled)
                VStack(alignment: .leading, spacing: 12) {
                    RowDivider()
                    SliderRow(title: "Size", value: $store.orbScale, range: 0.6...1.6,
                              display: "\(Int((store.orbScale * 100).rounded()))%")
                    SettingRow(title: "Corner") {
                        Picker("Corner", selection: $store.orbPosition) {
                            Text("Bottom center").tag("bottom")
                            Text("Bottom left").tag("bottom-left")
                            Text("Bottom right").tag("bottom-right")
                            Text("Top center").tag("top")
                            Text("Top left").tag("top-left")
                            Text("Top right").tag("top-right")
                        }
                        .labelsHidden()
                        .frame(width: 200)
                    }
                    SliderRow(title: "Distance from that edge", value: $store.orbInset, range: 20...400,
                              display: "\(Int(store.orbInset)) pt")
                    ToggleRow(title: "Keep the orb visible while transcribing",
                              isOn: $store.orbWhileProcessing)
                }
                .disabled(!store.overlayEnabled)
                .opacity(store.overlayEnabled ? 1 : 0.5)
                if !store.overlayEnabled {
                    InfoNote("The orb is off, so these options do nothing until you turn it on.")
                }
            }

            Block(title: "Sounds") {
                ToggleRow(title: "Play sounds",
                          detail: "A soft tick when recording starts and a pop when the text lands.",
                          isOn: $store.sounds)
            }

            Block(title: "Setup guide",
                  note: "The first-run walkthrough: permissions, microphone, model, language, "
                      + "shortcut and a test dictation.") {
                Button("Open the setup guide") { OnboardingWindowController.shared.show() }
                    .buttonStyle(.haloSecondary)
            }
        }
        .onAppear { ui.loginEnabled = LoginItem.enabled }
    }
}

// MARK: - Dictation

/// "Ready", "Model missing", "Permission needed" -- only from real state.
/// Shows nothing when readiness cannot be told (the model list has not loaded,
/// or the supervised engine is not running yet), rather than a constant badge.
struct ReadinessChip: View {
    @ObservedObject var models = ModelsStore.shared

    var body: some View {
        // Grants happen in System Settings, so re-read while the pane is open.
        TimelineView(.periodic(from: .now, by: 2)) { _ in
            if let s = state {
                StateLabel(status: s.0, text: s.1)
            }
        }
        .onAppear { models.refresh() }
    }

    private var state: (HaloStatus, String)? {
        if Permissions.microphone != .authorized || !Permissions.accessibility
            || Permissions.inputMonitoring != 0 {
            return (.warning, "Permission needed")
        }
        guard models.loaded, let m = models.speech.first(where: { $0.selected }) else { return nil }
        if models.downloading == m.id { return (.working, "Model downloading") }
        if !m.installed { return (.error, "Model missing") }
        if let sup = EngineSupervisor.current, sup.state != "running" { return nil }
        return (.ok, "Ready on this Mac")
    }
}

struct DictationPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    /// (tag, label, what it does, example)
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

    /// Fixed sample copy, one per level. It is a description of what each level
    /// does, never a live result.
    static let sampleSaid = "um meet on thursday comma actually friday at three thirty"
    static let samples: [String: String] = [
        "off": "um meet on thursday comma actually friday at three thirty",
        "verbatim": "um meet on thursday, actually friday at three thirty",
        "light": "Meet on Thursday, actually Friday at three thirty.",
        "normal": "Meet on Friday at 3:30.",
        "polished": "Let’s meet on Friday at 3:30.",
    ]

    private var smart: Bool { store.cleanupMode == "normal" || store.cleanupMode == "polished" }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneHeader(title: "Dictation",
                       subtitle: "The shortcut, how much Halo tidies up, and your languages.") {
                ReadinessChip()
            }

            Block(title: "Start speaking") {
                DetailRow(title: "Dictation key",
                           detail: "F13–F19 exist only on full-size keyboards. On a MacBook, F-keys may be "
                               + "brightness or media keys unless you hold fn — the setup guide can test yours.") {
                    HStack(spacing: 10) {
                        KeyCap(text: store.hotkey.uppercased())
                        Picker("Dictation key", selection: $store.hotkey) {
                            ForEach(Hotkeys.all, id: \.self) { Text($0.uppercased()).tag($0) }
                        }
                        .labelsHidden()
                        .frame(width: 90)
                    }
                }
                RowDivider()
                FieldLabel("Recording")
                RadioList(options: [
                    ("hold", "Press and hold", nil),
                    ("toggle", "Press to start, press again to send", nil),
                ], selection: $store.activation, accessibilityName: "Recording mode")
                if store.activation == "toggle" {
                    Stepper(value: $store.maxRecordingSec, in: 10...600, step: 10) {
                        Text("Stop automatically after \(store.maxRecordingSec) seconds")
                            .font(HaloType.control).foregroundStyle(HaloColor.text).monospacedDigit()
                    }
                    .padding(.leading, 22)
                }
                Support(store.activation == "toggle"
                        ? "Press once to start, press again to send. Escape cancels at any stage."
                        : "Recording lasts exactly as long as the key is down, so the microphone "
                          + "can never be left open. Escape cancels at any stage.")
            }

            Block(title: "How much should Halo tidy up?") {
                SegmentedChoice(options: Self.modes.map { (tag: $0.0, label: $0.1) },
                                selection: $store.cleanupMode,
                                accessibilityName: "Cleanup level")
                Support(Self.modes.first { $0.0 == store.cleanupMode }?.2 ?? "")
                ExampleBox(said: Self.sampleSaid,
                           typed: Self.samples[store.cleanupMode] ?? Self.sampleSaid)
                Support("Your vocabulary is applied at every level. The example is fixed sample "
                        + "text; what you get depends on what you say.")
            }

            LanguageBlock(store: store, ui: ui)

            DisclosureCard(title: "More formatting options",
                           summary: "Smart formatting, spoken punctuation and accuracy.",
                           isOpen: $ui.moreFormatting) {
                VStack(alignment: .leading, spacing: 10) {
                    FieldLabel("Smart formatting and backtrack")
                    Support("Normal and Polished only. If a language model is missing, loading, slow "
                            + "or wrong, Halo types the rule-based result instead.")
                    VStack(alignment: .leading, spacing: 10) {
                        ToggleRow(title: "Fix self-corrections (“send it to John — no, Jake”)",
                                  isOn: $store.selfCorrection)
                        ToggleRow(title: "Format numbers, dates, times, money, phone numbers, emails, links and lists",
                                  isOn: $store.smartFormatting)
                        ToggleRow(title: "End short chat messages with a full stop",
                                  isOn: $store.chatPeriod)
                    }
                    .disabled(!smart)
                    .opacity(smart ? 1 : 0.5)
                    if !smart {
                        InfoNote("Switch the cleanup level to Normal or Polished to use these.")
                    }
                }
                RowDivider()
                VStack(alignment: .leading, spacing: 10) {
                    FieldLabel("Spoken punctuation")
                    Support("Say “comma”, “question mark”, “new line”, “open paren”. Ambiguous words "
                            + "are left alone when they read as ordinary speech.")
                    ToggleRow(title: "Turn spoken punctuation into marks", isOn: $store.spokenPunctuation)
                    ToggleRow(title: "Remove “um”, “uh” and “er”", isOn: $store.stripFillers)
                    ToggleRow(title: "End each utterance with a full stop", isOn: $store.terminalPunctuation)
                }
                RowDivider()
                VStack(alignment: .leading, spacing: 10) {
                    FieldLabel("Accuracy")
                    Support("Priming tells whisper your vocabulary and what you just said before it "
                            + "decodes — the biggest accuracy win available without a larger model.")
                    ToggleRow(title: "Prime whisper with your vocabulary and recent context",
                              isOn: $store.whisperPrompt)
                    ToggleRow(title: "Suppress non-speech tokens ([BLANK_AUDIO], (music))",
                              isOn: $store.suppressNST)
                }
            }
        }
    }
}

struct LanguageBlock: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Block(title: "Languages",
                  note: "Say “switch to Spanish” (or use the menu bar) to change on the fly. Any "
                      + "language but English needs the multilingual speech model (Settings › Models). "
                      + "Self-correction and number formatting are English-only for now.") {
                SettingRow(title: "Preferred language") {
                    Picker("Preferred language", selection: Binding(
                        get: { store.language }, set: { store.setLanguage($0) })) {
                        Text("Detect automatically").tag("auto")
                        Divider()
                        ForEach(LanguageInfo.all, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .labelsHidden()
                    .frame(width: 240)
                }
                let recent = store.recentLanguages()
                if !recent.isEmpty {
                    HStack(spacing: 6) {
                        Text("Recent:").font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                        ForEach(recent, id: \.self) { code in
                            Button(LanguageInfo.name(code)) { store.setLanguage(code) }
                                .buttonStyle(.haloSmall)
                        }
                    }
                }
            }

            DisclosureCard(title: "Languages you use",
                           summary: store.enabledLanguages.map { LanguageInfo.name($0) }
                               .joined(separator: ", "),
                           isOpen: $ui.languagesOpen) {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), alignment: .leading)],
                          alignment: .leading, spacing: 8) {
                    ForEach(LanguageInfo.all, id: \.0) { lang in
                        Toggle(lang.1, isOn: Binding(
                            get: { store.enabledLanguages.contains(lang.0) },
                            set: { on in
                                var list = store.enabledLanguages.filter { $0 != lang.0 }
                                if on { list.append(lang.0) }
                                store.enabledLanguages = list.isEmpty ? ["en"] : list
                            }))
                        .toggleStyle(.haloCheckbox)
                    }
                }
                ForEach(store.enabledLanguages.filter { !LanguageInfo.regions($0).isEmpty }, id: \.self) { code in
                    SettingRow(title: "\(LanguageInfo.name(code)) variant") {
                        Picker("\(LanguageInfo.name(code)) variant", selection: Binding(
                            get: { store.regions[code] ?? "" },
                            set: { store.regions[code] = $0.isEmpty ? nil : $0 })) {
                            Text("Default").tag("")
                            ForEach(LanguageInfo.regions(code), id: \.self) { Text($0).tag($0) }
                        }
                        .labelsHidden()
                        .frame(width: 200)
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
    @Published var moreFormatting = false
    @Published var languagesOpen = false
}
