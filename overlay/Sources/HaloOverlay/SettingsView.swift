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
struct SettingsView: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    enum Tab: String, CaseIterable {
        case general = "General"
        case orb = "Orb"
        case dictation = "Dictation"
        case vocabulary = "Vocabulary"
        case privacy = "Privacy"

        var icon: String {
            switch self {
            case .general: return "keyboard"
            case .orb: return "circle.circle"
            case .dictation: return "text.quote"
            case .vocabulary: return "character.book.closed"
            case .privacy: return "lock.shield"
            }
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            tabStrip
            Divider()
            // Saving is refused while a config file will not parse, so the
            // window would otherwise just ignore every click with no
            // explanation.
            if let problem = store.loadError {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(problem).font(.system(size: 11, weight: .medium))
                        Text("Nothing here will save until that file parses — "
                             + "fixing it by hand is safer than letting this "
                             + "window overwrite it.")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Reveal") {
                        NSWorkspace.shared.selectFile(
                            SettingsStore.settingsURL.path,
                            inFileViewerRootedAtPath: SettingsStore.configDir.path)
                    }
                    .controlSize(.small)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color.orange.opacity(0.12))
                Divider()
            }
            ScrollView {
                Group {
                    switch ui.tab {
                    case .general: GeneralTab(store: store)
                    case .orb: OrbTab(store: store)
                    case .dictation: DictationTab(store: store)
                    case .vocabulary: VocabularyTab(store: store)
                    case .privacy: PrivacyTab(store: store)
                    }
                }
                .padding(20)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Divider()
            footer
        }
        .frame(minWidth: 560, minHeight: 460)
    }

    private var tabStrip: some View {
        HStack(spacing: 2) {
            ForEach(Tab.allCases, id: \.self) { t in
                Button {
                    ui.tab = t
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: t.icon).font(.system(size: 15))
                        Text(t.rawValue).font(.system(size: 10))
                    }
                    .frame(width: 74, height: 46)
                    .background(
                        RoundedRectangle(cornerRadius: 6)
                            .fill(ui.tab == t ? Color.primary.opacity(0.10) : .clear))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .foregroundStyle(ui.tab == t ? Color.accentColor : Color.primary)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
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
/// the tabs read consistently.
private struct Section<Content: View>: View {
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

// MARK: - General

private struct GeneralTab: View {
    @ObservedObject var store: SettingsStore

    // Only keys pynput can actually bind, so the picker cannot produce a
    // hotkey the engine will reject at startup.
    private let hotkeys = ["f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
                           "f13", "f14", "f15", "f16", "f17", "f18", "f19"]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Section(title: "Hotkey",
                    note: "F13–F19 exist only on full-size external keyboards. "
                        + "F9 is the default because it is confirmed free of "
                        + "media-key interception on a MacBook's own keyboard.") {
                Picker("Hold this key to talk", selection: $store.hotkey) {
                    ForEach(hotkeys, id: \.self) { Text($0.uppercased()).tag($0) }
                }
                .frame(width: 260)
            }

            Section(title: "How to start dictating",
                    note: store.activation == "toggle"
                        ? "Press once to start, press again to send. Escape "
                          + "throws the recording away."
                        : "Recording lasts exactly as long as the key is down, "
                          + "so the microphone can never be left open.") {
                Picker("", selection: $store.activation) {
                    Text("Press and hold").tag("hold")
                    Text("Press to start, press again to send").tag("toggle")
                }
                .pickerStyle(.radioGroup)
                .labelsHidden()

                if store.activation == "toggle" {
                    HStack {
                        Text("Stop automatically after")
                        Stepper(value: $store.maxRecordingSec, in: 10...600, step: 10) {
                            Text("\(store.maxRecordingSec) seconds")
                                .monospacedDigit()
                        }
                    }
                    .padding(.leading, 20)
                    .padding(.top, 2)
                }
            }

            Section(title: "Speech",
                    note: "English uses an English-only model, which is "
                        + "measurably better at English than the multilingual "
                        + "one. Any other language needs the multilingual "
                        + "model: download it with `halo model download small`.") {
                Picker("Language", selection: $store.language) {
                    Text("English").tag("en")
                    Text("Detect automatically").tag("auto")
                    Divider()
                    ForEach(Self.languages, id: \.0) { Text($0.1).tag($0.0) }
                }
                .frame(width: 300)

                Picker("Model", selection: $store.model) {
                    Text("small.en — 487 MB, the default").tag("small.en")
                    Text("base.en — 148 MB, faster and rougher").tag("base.en")
                    Text("medium.en — 1.5 GB, slower and sharper").tag("medium.en")
                }
                .frame(width: 300)
            }

            Section(title: "Menu bar",
                    note: "Off by default: the hotkey is meant to be the whole "
                        + "interface. `halo settings` opens this window "
                        + "whether or not the icon is showing.") {
                Toggle("Show a Halo icon in the menu bar", isOn: $store.menuBar)
            }
        }
    }

    static let languages: [(String, String)] = [
        ("es", "Spanish"), ("fr", "French"), ("de", "German"), ("it", "Italian"),
        ("pt", "Portuguese"), ("nl", "Dutch"), ("ru", "Russian"),
        ("ja", "Japanese"), ("ko", "Korean"), ("zh", "Chinese"),
        ("hi", "Hindi"), ("ta", "Tamil"), ("te", "Telugu"), ("ar", "Arabic"),
        ("tr", "Turkish"), ("pl", "Polish"), ("sv", "Swedish"),
        ("uk", "Ukrainian"), ("vi", "Vietnamese"),
    ]
}

// MARK: - Orb

private struct OrbTab: View {
    @ObservedObject var store: SettingsStore

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Section(title: "The orb",
                    note: "The orb never opens the microphone and never takes "
                        + "keyboard focus — it cannot intercept a click or a "
                        + "keystroke meant for the app you are dictating into.") {
                Toggle("Show the orb while dictating", isOn: $store.overlayEnabled)
            }

            Group {
                Section(title: "Size") {
                    HStack(spacing: 12) {
                        Text("Small").font(.system(size: 11)).foregroundStyle(.secondary)
                        Slider(value: $store.orbScale, in: 0.6...1.6)
                            .frame(width: 240)
                        Text("Large").font(.system(size: 11)).foregroundStyle(.secondary)
                        Text(String(format: "%.0f%%", store.orbScale * 100))
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(width: 44, alignment: .trailing)
                    }
                    OrbPreview(scale: store.orbScale)
                }

                Section(title: "Position",
                        note: "The orb appears on whichever display currently "
                            + "has the pointer.") {
                    Picker("", selection: $store.orbPosition) {
                        Text("Bottom center").tag("bottom")
                        Text("Bottom left").tag("bottom-left")
                        Text("Bottom right").tag("bottom-right")
                        Text("Top center").tag("top")
                        Text("Top left").tag("top-left")
                        Text("Top right").tag("top-right")
                    }
                    .labelsHidden()
                    .frame(width: 260)

                    HStack {
                        Text("Distance from that edge")
                        Slider(value: $store.orbInset, in: 20...400).frame(width: 200)
                        Text("\(Int(store.orbInset)) pt")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(.secondary)
                            .frame(width: 52, alignment: .trailing)
                    }
                }

                Section(title: "Behaviour",
                        note: "Turn this off and the orb disappears the moment "
                            + "you stop speaking, instead of staying up while "
                            + "Halo transcribes.") {
                    Toggle("Keep the orb visible while transcribing",
                           isOn: $store.orbWhileProcessing)
                }
            }
            .disabled(!store.overlayEnabled)
            .opacity(store.overlayEnabled ? 1 : 0.4)
        }
    }
}

/// A static stand-in for the real orb: same bubble, same glass, no animation.
/// Running the actual `VoiceOrb` here would mean a second Canvas redrawing at
/// 60fps inside a settings window nobody is looking at.
private struct OrbPreview: View {
    let scale: Double

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10)
                .fill(Color.primary.opacity(0.06))
                .frame(height: 120)
            Circle()
                .fill(Color.black.opacity(0.72))
                .overlay(Circle().strokeBorder(Color.white.opacity(0.12), lineWidth: 1))
                .overlay(
                    Circle()
                        .strokeBorder(Color.white.opacity(0.85), lineWidth: 2)
                        .padding(Style.bubbleSize * 0.18))
                .frame(width: Style.bubbleSize * scale,
                       height: Style.bubbleSize * scale)
                .animation(.spring(response: 0.25, dampingFraction: 0.8),
                           value: scale)
        }
        .frame(maxWidth: 420)
    }
}

// MARK: - Dictation

private struct DictationTab: View {
    @ObservedObject var store: SettingsStore

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
            Section(title: "Cleanup",
                    note: Self.modes.first { $0.0 == store.cleanupMode }?.2
                        ?? "") {
                Picker("", selection: $store.cleanupMode) {
                    ForEach(Self.modes, id: \.0) { Text($0.1).tag($0.0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .frame(width: 420)
            }

            Section(title: "Smart cleanup",
                    note: "Normal and Polished only. If a language model is "
                        + "missing, still loading, slow or wrong, Halo types "
                        + "the rule-based result instead — you never lose a "
                        + "dictation to it. Choose where the model runs in "
                        + "Privacy.") {
                Toggle("Fix self-corrections (“send it to John — no, Jake”)",
                       isOn: $store.selfCorrection)
                Toggle("Format numbers, dates, times, money, phone numbers, "
                       + "emails, links and spoken lists",
                       isOn: $store.smartFormatting)
                Toggle("End short chat messages with a full stop",
                       isOn: $store.chatPeriod)
            }
            .disabled(!smart)
            .opacity(smart ? 1 : 0.4)

            Section(title: "Spoken punctuation",
                    note: "Say “comma”, “question mark”, “new line”, “open "
                        + "paren”. Ambiguous words are left alone when they "
                        + "read as ordinary speech — “the Jurassic period was "
                        + "long” types as written.") {
                Toggle("Turn spoken punctuation into marks",
                       isOn: $store.spokenPunctuation)
            }

            Section(title: "Formatting",
                    note: "All of this runs on this Mac, with no key and no "
                        + "network, so it applies in Privacy Mode too.") {
                Toggle("Remove “um”, “uh” and “er”", isOn: $store.stripFillers)
                Toggle("End each utterance with a full stop",
                       isOn: $store.terminalPunctuation)
            }

            Section(title: "Accuracy",
                    note: "Priming tells whisper your vocabulary and what you "
                        + "just said before it decodes, which is the single "
                        + "biggest accuracy win available without a larger "
                        + "model. Turn it off only if you see your own "
                        + "vocabulary being typed back at you.") {
                Toggle("Prime whisper with your vocabulary and recent context",
                       isOn: $store.whisperPrompt)
                Toggle("Suppress non-speech tokens ([BLANK_AUDIO], (music))",
                       isOn: $store.suppressNST)
            }
        }
    }
}

// MARK: - Vocabulary

private struct VocabularyTab: View {
    @ObservedObject var store: SettingsStore

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Words Halo gets wrong")
                .font(.system(size: 13, weight: .semibold))
            Text("Left: the spelling you want typed. Right: what whisper "
                 + "actually says, separated by commas. The first thing worth "
                 + "adding is your own name — whisper will not guess it.")
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 10)

            HStack(spacing: 8) {
                Text("Type this").frame(width: 150, alignment: .leading)
                Text("When you hear").frame(maxWidth: .infinity, alignment: .leading)
                Spacer().frame(width: 24)
            }
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 6)

            ScrollView {
                LazyVStack(spacing: 4) {
                    // Indices, not the elements: each row needs a write-back
                    // Binding into the store's array, and a `Term` copy would
                    // silently edit a temporary.
                    ForEach(store.terms.indices, id: \.self) { i in
                        TermRow(store: store, index: i)
                    }
                }
                .padding(.vertical, 4)
            }
            .frame(minHeight: 200)
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(Color.primary.opacity(0.04)))

            HStack(spacing: 8) {
                Button {
                    store.addTerm()
                } label: {
                    Label("Add word", systemImage: "plus")
                }
                Spacer()
                Text("\(store.terms.count) word\(store.terms.count == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                // Explicit, because the rows only commit on Return and nobody
                // presses Return in the last field they touch. Closing the
                // window saves too.
                Button("Save vocabulary") { store.saveDictionary() }
                    .keyboardShortcut("s")
            }
            .padding(.top, 8)

            Divider().padding(.vertical, 16)

            Section(title: "Catch near misses",
                    note: "Also corrects words that merely sound close to one "
                        + "of your terms. Three separate vetoes keep it off "
                        + "ordinary English, but a lower threshold is more "
                        + "eager and more likely to be wrong.") {
                Toggle("Fuzzy matching", isOn: $store.fuzzyEnabled)
                HStack {
                    Text("Only when at least")
                    Slider(value: $store.fuzzyThreshold, in: 0.80...0.99)
                        .frame(width: 180)
                    Text(String(format: "%.0f%% similar", store.fuzzyThreshold * 100))
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.secondary)
                }
                .disabled(!store.fuzzyEnabled)
                .opacity(store.fuzzyEnabled ? 1 : 0.4)
            }
        }
    }
}

private struct TermRow: View {
    @ObservedObject var store: SettingsStore
    let index: Int

    var body: some View {
        // The array can shrink between a delete and the next render pass.
        if index < store.terms.count {
            HStack(spacing: 8) {
                TextField("term", text: Binding(
                    get: { store.terms[index].term },
                    set: { store.terms[index].term = $0 }))
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 150)
                    .onSubmit { store.saveDictionary() }

                TextField("what whisper says, comma separated", text: Binding(
                    get: { store.terms[index].variantText },
                    set: { store.terms[index].variantText = $0 }))
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { store.saveDictionary() }

                Button {
                    store.removeTerms(at: IndexSet(integer: index))
                } label: {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.secondary)
                .help("Remove this word")
            }
            .padding(.horizontal, 6)
        }
    }
}

// MARK: - Privacy

private struct PrivacyTab: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var keys = KeyStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Section(title: "Context Awareness",
                    note: "When on, Halo looks at the app you are dictating "
                        + "into and a few hundred characters around the cursor, "
                        + "to spell names the way the screen does, skip the "
                        + "capital mid-sentence and format for the app. It is "
                        + "held in memory for that one dictation and then "
                        + "cleared. It never reads password or other secure "
                        + "fields, never writes that text to a log or to "
                        + "disk, and never sends it to OpenRouter. "
                        + "Dictation works the same with it off.") {
                Toggle("Use context from the app you are dictating into",
                       isOn: $store.contextEnabled)
            }

            Section(title: "Where cleanup runs",
                    note: "Automatic uses the model on this Mac when one is "
                        + "downloaded, then OpenRouter if you allow it below, "
                        + "and otherwise the local rules. A downloaded model "
                        + "that is still loading never hands your text to "
                        + "OpenRouter instead.") {
                Picker("", selection: $store.cleanupProvider) {
                    Text("Automatic").tag("auto")
                    Text("This Mac only").tag("local")
                    Text("OpenRouter").tag("openrouter")
                    Text("Rules only, no model").tag("none")
                }
                .pickerStyle(.radioGroup)
                .labelsHidden()
                LocalModelRow(store: store)
                    .disabled(store.cleanupProvider == "openrouter"
                              || store.cleanupProvider == "none")
            }

            Section(title: "What leaves this Mac",
                    note: "Your audio never leaves the machine under any "
                        + "setting — whisper.cpp runs locally, and so does the "
                        + "model above. The only thing that can leave is the "
                        + "transcript text, and only when this is on, a key is "
                        + "stored, and Privacy Mode is off.") {
                Toggle("Allow transcripts to be sent to OpenRouter for cleanup",
                       isOn: $store.cleanupEnabled)
            }

            Section(title: "Privacy Mode",
                    note: "When on, the network call is skipped entirely. "
                        + "Punctuation, capitalization and your vocabulary "
                        + "still apply — those are local. Say “privacy on” to "
                        + "flip it mid-session; that choice persists.") {
                Toggle("Start with Privacy Mode on", isOn: $store.privacyDefault)
            }

            Section(title: "OpenRouter key",
                    note: "Optional. Get one at openrouter.ai/keys — the free "
                        + "tier is enough. Then in OpenRouter's privacy "
                        + "settings turn Zero Data Retention › Non-frontier "
                        + "OFF and “Allow free endpoints that train on request "
                        + "data” ON; free models refuse requests without "
                        + "both.") {
                HStack(spacing: 10) {
                    Image(systemName: keys.stored ? "key.fill" : "key.slash")
                        .foregroundStyle(keys.stored ? .green : .secondary)
                    Text(keys.stored
                         ? "An OpenRouter key is stored in your Keychain."
                         : "No key stored — transcripts stay on this Mac.")
                        .font(.system(size: 12))
                    Spacer()
                    if keys.stored {
                        Button("Remove", role: .destructive) { keys.clear() }
                            .controlSize(.small)
                    }
                }
                HStack(spacing: 8) {
                    SecureField(keys.stored ? "Paste a new key to replace it"
                                            : "sk-or-v1-…",
                                text: $keys.draft)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { keys.save() }
                    Button(keys.stored ? "Replace" : "Save") { keys.save() }
                        .disabled(keys.draft.trimmingCharacters(
                            in: .whitespacesAndNewlines).isEmpty)
                }
                HStack(spacing: 14) {
                    Link("Get a key", destination: URL(
                        string: "https://openrouter.ai/keys")!)
                    Link("OpenRouter privacy settings", destination: URL(
                        string: "https://openrouter.ai/settings/privacy")!)
                }
                .font(.system(size: 11))
                if let message = keys.message {
                    Text(message)
                        .font(.system(size: 11))
                        .foregroundStyle(keys.failed ? .orange : .green)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Section(title: "The honest version",
                    note: "OpenRouter's free endpoints require data-training "
                        + "to be allowed on your account, so a provider may "
                        + "retain and train on the transcripts you send. That "
                        + "is why the key is optional and why Halo works "
                        + "without one.") {
                EmptyView()
            }
        }
        // Probed on appear rather than on every render: it spawns a process,
        // and `halo key` in Terminal can change the answer while the window
        // is closed.
        .onAppear { keys.refresh() }
    }
}


/// The model on this Mac: which one, whether it is here, and a button to get it.
private struct LocalModelRow: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var models = LocalModelStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Picker("Model on this Mac", selection: $store.localModel) {
                ForEach(LocalModelStore.catalog) { Text($0.label).tag($0.id) }
            }
            .frame(width: 420)
            HStack(spacing: 10) {
                Image(systemName: models.installed(store.localModel)
                      ? "cpu.fill" : "arrow.down.circle")
                    .foregroundStyle(models.state == "ready" ? .green : .secondary)
                Text(models.describe(store.localModel))
                    .font(.system(size: 12))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
                if models.downloading != nil {
                    ProgressView(value: models.progress).frame(width: 90)
                    Button("Stop") { models.cancelDownload() }.controlSize(.small)
                } else if models.installed(store.localModel) {
                    Button("Remove", role: .destructive) { models.remove(store.localModel) }
                        .controlSize(.small)
                } else {
                    Button("Download") { models.download(store.localModel) }
                        .controlSize(.small)
                }
            }
            if let message = models.message {
                Text(message)
                    .font(.system(size: 11))
                    .foregroundStyle(models.failed ? .orange : .green)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 4)
        .onAppear { models.startWatching() }
        .onDisappear { models.stopWatching() }
    }
}


/// View-local state for the Settings window.
///
/// This exists only because `@State` is a macro the Command Line Tools cannot
/// expand (see the note on `SettingsView`). It holds nothing persistent --
/// everything durable lives in `SettingsStore` and, through it, on disk.
@MainActor
final class SettingsUI: ObservableObject {
    @Published var tab: SettingsView.Tab = .general
}
