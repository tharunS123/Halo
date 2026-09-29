import AppKit
import AVFoundation
import IOKit.hid
import SwiftUI

/// The first-run guide: ten short screens from "what is this" to a real
/// dictation that lands in a text box on the last-but-one screen.
///
/// Resumable: the current step is written to state.json on every move, so
/// quitting halfway -- often to restart after granting Accessibility --
/// brings you back to where you were. `halo setup` still works for people
/// who prefer Terminal; someone who has already set Halo up that way is
/// never sent through this again.
enum Onboarding {
    static let steps = 10

    static func state() -> [String: Any] {
        JSONFile.object(HaloPaths.state)["onboarding"] as? [String: Any] ?? [:]
    }

    static func save(step: Int, done: Bool = false) {
        var root = JSONFile.object(HaloPaths.state)
        root["onboarding"] = ["step": step, "done": done]
        JSONFile.write(root, to: HaloPaths.state)
    }

    /// Only for the background app, only until finished once, and never for
    /// an install `halo setup` already walked through.
    static func needed(supervised: Bool) -> Bool {
        guard supervised else { return false }
        let st = state()
        if st["done"] as? Bool == true { return false }
        let root = JSONFile.object(HaloPaths.state)
        if st.isEmpty && (root["granted_identity"] != nil || root["granted_cdhash"] != nil) {
            save(step: steps - 1, done: true)
            return false
        }
        return true
    }
}

@MainActor
final class OnboardingModel: ObservableObject {
    @Published var step: Int
    @Published var testText = ""
    @Published var keySeen = ""
    @Published var listeningForKey = false
    @Published var tick = 0          // bumped each second so permission rows refresh
    /// "Open Halo at login" on the last page. On by default for the
    /// downloaded app, where nothing else would start Halo again after a
    /// restart; a `halo setup` install already has its login agent.
    @Published var openAtLogin = AppBundle.isSelfContained || LoginItem.enabled

    private var monitor: Any?
    private var timer: Timer?

    init() {
        step = min(max(Onboarding.state()["step"] as? Int ?? 0, 0), Onboarding.steps - 1)
    }

    func go(_ n: Int) {
        step = min(max(n, 0), Onboarding.steps - 1)
        Onboarding.save(step: step)
        stopKeyTest()
        if step == 4 { MicTester.shared.start(deviceName: SettingsStore.shared.micDevice) }
        else { MicTester.shared.stop() }
        if step == 5 { ModelsStore.shared.refresh() }
    }

    func startTicking() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.tick += 1 }
        }
    }

    func stopTicking() {
        timer?.invalidate()
        timer = nil
        stopKeyTest()
        MicTester.shared.stop()
    }

    /// What the dictation key actually sends here. On a MacBook an F-key
    /// is often brightness or volume unless fn is held; that is the conflict
    /// worth catching before someone decides Halo is broken.
    func startKeyTest() {
        stopKeyTest()
        keySeen = ""
        listeningForKey = true
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .systemDefined]) { [weak self] ev in
            Task { @MainActor in self?.saw(ev) }
            return ev.type == .keyDown ? nil : ev
        }
    }

    private func saw(_ ev: NSEvent) {
        guard listeningForKey else { return }
        if ev.type == .systemDefined {
            if ev.subtype.rawValue == 8 {        // media / brightness keys
                keySeen = "media"
                stopKeyTest()
            }
            return
        }
        let fkeys: [UInt16: String] = [96: "f5", 97: "f6", 98: "f7", 100: "f8", 101: "f9",
                                       109: "f10", 103: "f11", 111: "f12", 105: "f13", 107: "f14",
                                       113: "f15", 106: "f16", 64: "f17", 79: "f18", 80: "f19"]
        keySeen = fkeys[ev.keyCode] ?? "other"
        stopKeyTest()
    }

    func stopKeyTest() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
        listeningForKey = false
    }

    func finish() {
        // Needing approval opens System Settings › Login Items by itself.
        if openAtLogin != LoginItem.enabled { _ = LoginItem.set(openAtLogin) }
        Onboarding.save(step: Onboarding.steps - 1, done: true)
        stopTicking()
        OnboardingWindowController.shared.close()
    }
}

@MainActor
final class OnboardingWindowController: NSObject, NSWindowDelegate {
    static let shared = OnboardingWindowController()
    private var window: NSWindow?
    private let model = OnboardingModel()

    /// `step` is 0-based; nil resumes where the guide was left.
    func show(step: Int? = nil) {
        if let step { model.step = min(max(step, 0), Onboarding.steps - 1) }
        if window == nil {
            // 900 x 700 by default, never smaller than 760 x 520.
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 900, height: 700),
                             styleMask: [.titled, .closable, .miniaturizable, .resizable],
                             backing: .buffered, defer: false)
            w.title = "Welcome to Halo"
            w.contentMinSize = NSSize(width: 760, height: 520)
            w.isReleasedWhenClosed = false
            w.center()
            w.contentView = NSHostingView(rootView: OnboardingView(model: model, store: SettingsStore.shared))
            w.delegate = self
            window = w
        }
        model.go(model.step)
        model.startTicking()
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    func close() { window?.close() }

    func windowWillClose(_ notification: Notification) {
        model.stopTicking()
        // Closing early is fine: the step is saved, and the guide comes back
        // at the next launch until it is finished.
        DispatchQueue.main.async {
            if !(SettingsWindowController.shared.isOpen) { NSApp.setActivationPolicy(.accessory) }
        }
    }
}

struct OnboardingView: View {
    @ObservedObject var model: OnboardingModel
    @ObservedObject var store: SettingsStore
    @ObservedObject var models = ModelsStore.shared
    @ObservedObject var devices = AudioDevices.shared
    @ObservedObject var tester = MicTester.shared

    private let column: CGFloat = 640

    var body: some View {
        VStack(spacing: 0) {
            OnboardingProgressHeader(step: model.step)
                .padding(.horizontal, 36).padding(.top, 14).padding(.bottom, 14)
                .frame(maxWidth: column + 72)
                .frame(maxWidth: .infinity)

            Divider().overlay(HaloColor.subtleBorder)

            ScrollView {
                page
                    .frame(maxWidth: column, alignment: .leading)
                    .padding(.horizontal, 36).padding(.vertical, 24)
                    .frame(maxWidth: .infinity)
            }

            Divider().overlay(HaloColor.subtleBorder)
            footer
                .padding(.horizontal, 36).padding(.vertical, 14)
                .frame(maxWidth: column + 72)
                .frame(maxWidth: .infinity)
        }
        .frame(minWidth: 760, idealWidth: 900, maxWidth: .infinity,
               minHeight: 520, idealHeight: 700, maxHeight: .infinity)
        .background(HaloColor.background)
        .foregroundStyle(HaloColor.text)
        .font(HaloType.control)
        .tint(HaloColor.imperial)
    }

    private var footer: some View {
        HStack(spacing: 10) {
            if model.step > 0 && model.step < Onboarding.steps - 1 {
                Button("Back") { model.go(model.step - 1) }.buttonStyle(.haloSecondary)
            }
            Spacer(minLength: 8)
            if model.step == Onboarding.steps - 1 {
                Button("Open Settings") {
                    model.finish()
                    SettingsWindowController.shared.show()
                }
                .buttonStyle(.haloSecondary)
                Button("Done") { model.finish() }
                    .buttonStyle(.haloPrimary).keyboardShortcut(.defaultAction)
            } else {
                Button(nextLabel) { model.go(model.step + 1) }
                    .buttonStyle(.haloPrimary).keyboardShortcut(.defaultAction)
            }
        }
    }

    private var nextLabel: String {
        switch model.step {
        case 0: return "Get started"
        case 2 where Permissions.microphone != .authorized: return "Skip for now"
        case 3 where !Permissions.accessibility: return "Skip for now"
        default: return "Continue"
        }
    }

    @ViewBuilder
    private var page: some View {
        let _ = model.tick
        switch model.step {
        case 0: welcome
        case 1: privacy
        case 2: microphonePermission
        case 3: accessibility
        case 4: microphone
        case 5: speechModel
        case 6: language
        case 7: shortcut
        case 8: test
        default: complete
        }
    }

    /// A page: its title, then the content, with room between.
    private func pageStack<Content: View>(_ title: String, _ subtitle: String? = nil,
                                          @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            OnboardingTitle(title: title, subtitle: subtitle)
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func bullet(_ icon: String, _ text: String) -> OnboardingBullet {
        OnboardingBullet(icon: icon, text: Text(text))
    }

    /// A key or command inside a sentence, in Source Code Pro.
    private func mono(_ s: String) -> Text {
        Text(s).font(HaloType.mono(12.5, .semibold))
    }

    private var key: String { store.hotkey.uppercased() }

    // MARK: Welcome, privacy

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 22) {
            HStack(spacing: 16) {
                HaloMark(size: 64)
                VStack(alignment: .leading, spacing: 6) {
                    HaloWordmark(height: 24)
                    Text("Your voice, kept close.")
                        .font(HaloType.brand(20))
                        .foregroundStyle(HaloColor.text)
                }
            }
            OnboardingTitle(title: "Halo is local voice dictation for your Mac.",
                            subtitle: "Hold a key, speak, let go — clean text appears wherever you were typing.",
                            size: 26)
            VStack(alignment: .leading, spacing: 12) {
                bullet("mic", "Your voice is transcribed on this Mac. Nothing is uploaded.")
                bullet("sparkles", "Cleanup, self-corrections and formatting happen here too.")
                bullet("clock", "About two minutes to set up: two permissions, a microphone, a model, a test.")
            }
        }
    }

    private var privacy: some View {
        pageStack("Private by design", "What Halo does with what you say:") {
            VStack(alignment: .leading, spacing: 12) {
                bullet("waveform", "Speech processing happens locally, with whisper.cpp on your Mac.")
                bullet("icloud.slash", "Audio is never uploaded.")
                bullet("text.bubble", "Transcript text is never sent to AI services. Cleanup runs on "
                       + "your Mac, and Halo works with the network switched off.")
                bullet("eye.slash", "The text around your cursor stays in memory for one dictation and "
                       + "is never saved, logged or sent. Password fields are never read.")
                bullet("clock.arrow.circlepath", "History is off unless you turn it on.")
            }
        }
    }

    // MARK: Access

    private var microphonePermission: some View {
        let status = Permissions.microphone
        return pageStack("Microphone", "Halo records only while you hold the dictation key.") {
            HaloCard {
                SettingRow(title: "Microphone access",
                           detail: "Needed to hear you while the dictation key is held.") {
                    HStack(spacing: 10) {
                        micState(status)
                        if status == .notDetermined {
                            Button("Allow microphone") { Permissions.requestMicrophone { _ in } }
                                .buttonStyle(.haloSecondary)
                        } else if status != .authorized {
                            Button("Open System Settings") { SystemSettings.open(.microphone) }
                                .buttonStyle(.haloSecondary)
                        }
                    }
                }
            }
            if status == .denied {
                HaloBanner(status: .warning, title: "Microphone is turned off for Halo",
                           message: "Turn on Halo in System Settings › Privacy & Security › Microphone, "
                                    + "then come back.")
            }
        }
    }

    @ViewBuilder
    private func micState(_ status: AVAuthorizationStatus) -> some View {
        switch status {
        case .authorized: StateLabel(status: .ok, text: "Allowed")
        case .notDetermined: StateLabel(status: .warning, text: "Not asked yet")
        case .denied: StateLabel(status: .error, text: "Not allowed")
        case .restricted: StateLabel(status: .error, text: "Restricted")
        @unknown default: StateLabel(status: .warning, text: "Unknown")
        }
    }

    private var accessibility: some View {
        pageStack("Accessibility and Input Monitoring",
                  "Halo needs to notice your dictation key from any app, and to type the text "
                  + "where your cursor is. macOS asks you to allow both, once.") {
            HaloCard {
                permissionRow("Accessibility", "Typing into the app you are using.",
                              ok: Permissions.accessibility) {
                    let opts = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
                    _ = AXIsProcessTrustedWithOptions(opts)
                    SystemSettings.open(.accessibility)
                }
                Divider().overlay(HaloColor.subtleBorder)
                permissionRow("Input Monitoring", "Hearing the dictation key anywhere.",
                              ok: Permissions.inputMonitoring == 0) {
                    _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
                    SystemSettings.open(.inputMonitoring)
                }
            }
            HaloBanner(status: .info, title: "This page updates by itself",
                       message: "In System Settings, switch on Halo in each list. If macOS asks to "
                                + "quit Halo, allow it — this guide reopens where you left off.")
        }
    }

    private func permissionRow(_ name: String, _ why: String, ok: Bool,
                               open: @escaping () -> Void) -> some View {
        SettingRow(title: name, detail: why) {
            HStack(spacing: 10) {
                if ok {
                    StateLabel(status: .ok, text: "Allowed")
                } else {
                    StateLabel(status: .warning, text: "Not allowed yet")
                    Button("Open System Settings", action: open).buttonStyle(.haloSecondary)
                }
            }
        }
    }

    // MARK: Voice

    private var microphone: some View {
        pageStack("Choose a microphone", "Speak — the bar should move.") {
            HaloCard {
                SettingRow(title: "Microphone") {
                    Picker("Microphone", selection: $store.micDevice) {
                        Text("System Default (\(devices.defaultName))").tag("")
                        ForEach(devices.devices) { Text("\($0.name) · \($0.kind)").tag($0.name) }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 340)
                    .onAppear { devices.start() }
                    .onChange(of: store.micDevice) { _, name in tester.start(deviceName: name) }
                }
                Divider().overlay(HaloColor.subtleBorder)
                HStack(spacing: 10) {
                    Text("Input level").font(HaloType.control)
                    Spacer(minLength: 8)
                    if tester.running {
                        StateLabel(status: .ok, text: "Listening to input")
                    } else {
                        StateLabel(status: .warning, text: "Not listening")
                    }
                }
                OnboardingLevelMeter(level: tester.level)
                HStack(spacing: 8) {
                    Button(tester.recording ? "Recording…" : "Record a test") { tester.record() }
                        .buttonStyle(.haloSecondary)
                        .disabled(!tester.running || tester.recording)
                    Button("Play it back") { tester.play() }
                        .buttonStyle(.haloSecondary).disabled(!tester.hasRecording)
                }
            }
            if let m = tester.message {
                Note(text: m, failed: m.contains("silence") || m.contains("not"))
            }
        }
    }

    private var speechModel: some View {
        let rec = models.speech.first { $0.recommended }
        return pageStack("Speech model",
                         "The model that turns your voice into text. "
                         + (rec.map { "For this Mac we recommend \($0.id) (\($0.sizeText))." } ?? "")) {
            if !models.loaded { ProgressView().accessibilityLabel("Loading models") }
            VStack(alignment: .leading, spacing: 10) {
                ForEach(models.speech.filter { ["small.en", "base.en", "small"].contains($0.id) }) { m in
                    OnboardingModelRow(models: models, model: m)
                }
            }
            if let msg = models.message { Note(text: msg, failed: models.failed) }
            Text("Downloads are checked against a published checksum before Halo will use them. "
                 + "You can add the optional cleanup model later in Settings › Models.")
                .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var language: some View {
        pageStack("Language",
                  "What you will mostly dictate in. You can switch any time by saying “switch to Spanish”.") {
            HaloCard {
                SettingRow(title: "Dictation language") {
                    Picker("Language", selection: Binding(get: { store.language },
                                                          set: { store.setLanguage($0) })) {
                        Text("Detect automatically").tag("auto")
                        ForEach(LanguageInfo.all, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 300)
                }
            }
            if store.language != "en" {
                HaloBanner(status: .warning,
                           title: "Languages other than English need the multilingual speech model (small).")
            }
        }
    }

    private var shortcut: some View {
        pageStack("Your dictation key", "Hold it to talk, let go to send.") {
            HaloCard {
                SettingRow(title: "Dictation key") {
                    Picker("Key", selection: $store.hotkey) {
                        ForEach(Hotkeys.all, id: \.self) { Text($0.uppercased()).tag($0) }
                    }
                    .labelsHidden()
                    .frame(maxWidth: 140)
                }
                Divider().overlay(HaloColor.subtleBorder)
                Button(model.listeningForKey ? "Press your key now…" : "Test the key") { model.startKeyTest() }
                    .buttonStyle(.haloSecondary)
                if model.keySeen == store.hotkey {
                    HaloBanner(status: .ok, title: "\(key) works.")
                } else if model.keySeen == "media" {
                    HaloBanner(status: .warning,
                               title: "Your Mac sent a brightness or media key. Hold fn with it, or pick another key.")
                } else if !model.keySeen.isEmpty {
                    HaloBanner(status: .warning,
                               title: "That was \(model.keySeen.uppercased()), not \(key).")
                }
            }
            HaloCard {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    HStack(spacing: 4) { KeyCap(text: "Shift"); Text("+"); KeyCap(text: key) }
                    Text("Command Mode: edit selected text by voice.")
                        .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    KeyCap(text: "Escape")
                    Text("Cancels, at any stage.")
                        .font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                }
            }
        }
    }

    // MARK: Try it

    private var test: some View {
        pageStack("Try it", "Click in the box, hold \(key), say “Hello Halo, this is a test”, and let go.") {
            TextEditor(text: $model.testText)
                .font(HaloType.body(14))
                .scrollContentBackground(.hidden)
                .padding(8)
                .frame(minHeight: 110, maxHeight: 180)
                .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                    .fill(HaloColor.surface))
                .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                    .strokeBorder(HaloColor.border, lineWidth: 1))
                .accessibilityLabel("Test dictation")
            if !model.testText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                HaloBanner(status: .ok, title: "It works",
                           message: "Recording, transcription, cleanup and typing all went through.")
            } else if EngineSupervisor.current?.state.hasPrefix("waiting") == true {
                HaloBanner(status: .warning, title: "Halo is waiting for a permission or a model",
                           message: "Go back a step.")
            } else {
                StateLabel(status: .info, text: "Nothing dictated yet")
            }
        }
    }

    private var complete: some View {
        pageStack("You're set.", "Halo runs in the background. The shortcuts:") {
            VStack(alignment: .leading, spacing: 12) {
                OnboardingBullet(icon: "keyboard",
                                 text: Text("Hold \(mono(key)) and speak — let go to type it."))
                OnboardingBullet(icon: "wand.and.stars",
                                 text: Text("\(mono("Shift + \(key)")): Command Mode — “make this shorter”."))
                OnboardingBullet(icon: "escape",
                                 text: Text("\(mono("Escape")) cancels, at any stage."))
                bullet("arrow.uturn.backward", "Say “scratch that” to remove what Halo just typed.")
                bullet("gearshape", "Open Halo again from Applications for Settings and everything else.")
            }
            ToggleRow(title: "Open Halo at login",
                      detail: "So F9 works after a restart without opening anything.",
                      isOn: $model.openAtLogin)
        }
    }
}
