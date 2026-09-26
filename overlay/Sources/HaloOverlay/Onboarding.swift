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
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 620, height: 520),
                             styleMask: [.titled, .closable, .miniaturizable],
                             backing: .buffered, defer: false)
            w.title = "Welcome to Halo"
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

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 5) {
                ForEach(0..<Onboarding.steps, id: \.self) { i in
                    Capsule().fill(i <= model.step ? Color.accentColor : Color.primary.opacity(0.12))
                        .frame(height: 4)
                }
            }
            .padding(.horizontal, 28).padding(.top, 18)

            ScrollView {
                page
                    .padding(.horizontal, 36).padding(.vertical, 24)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            Divider()
            HStack {
                if model.step > 0 && model.step < Onboarding.steps - 1 {
                    Button("Back") { model.go(model.step - 1) }
                }
                Spacer()
                Text("\(model.step + 1) of \(Onboarding.steps)")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                Spacer()
                if model.step == Onboarding.steps - 1 {
                    Button("Open Settings") {
                        model.finish()
                        SettingsWindowController.shared.show()
                    }
                    Button("Done") { model.finish() }.keyboardShortcut(.defaultAction)
                } else {
                    Button(nextLabel) { model.go(model.step + 1) }.keyboardShortcut(.defaultAction)
                }
            }
            .padding(16)
        }
        .frame(width: 620, height: 520)
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

    private func title(_ t: String, _ s: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(t).font(.system(size: 24, weight: .semibold))
            Text(s).font(.system(size: 13)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 18)
    }

    private func bullet(_ icon: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon).frame(width: 20).foregroundStyle(Color.accentColor)
            Text(text).font(.system(size: 13)).fixedSize(horizontal: false, vertical: true)
        }
        .padding(.bottom, 8)
    }

    private var welcome: some View {
        VStack(alignment: .leading) {
            title("Halo is local voice dictation for your Mac.",
                  "Hold a key, speak, let go — clean text appears wherever you were typing.")
            bullet("mic", "Your voice is transcribed on this Mac. Nothing is uploaded.")
            bullet("sparkles", "Cleanup, self-corrections and formatting happen here too.")
            bullet("clock", "About two minutes to set up: two permissions, a microphone, a model, a test.")
        }
    }

    private var privacy: some View {
        VStack(alignment: .leading) {
            title("Private by design", "What Halo does with what you say:")
            bullet("waveform", "Speech processing happens locally, with whisper.cpp on your Mac.")
            bullet("icloud.slash", "Audio is never uploaded.")
            bullet("text.bubble", "Transcript text is not sent to AI services. (An optional "
                   + "OpenRouter key can be added later; it is off unless you add one.)")
            bullet("eye.slash", "The text around your cursor stays in memory for one dictation and "
                   + "is never saved, logged or sent. Password fields are never read.")
            bullet("clock.arrow.circlepath", "History is off unless you turn it on.")
        }
    }

    private var microphonePermission: some View {
        VStack(alignment: .leading) {
            title("Microphone", "Halo records only while you hold the dictation key.")
            HStack(spacing: 10) {
                StatusDot(ok: Permissions.microphone == .authorized,
                          warn: Permissions.microphone == .notDetermined)
                Text("Microphone access: \(Permissions.microphoneText)")
                Spacer()
                if Permissions.microphone == .notDetermined {
                    Button("Allow microphone") { Permissions.requestMicrophone { _ in } }
                } else if Permissions.microphone != .authorized {
                    Button("Open System Settings") { SystemSettings.open(.microphone) }
                }
            }
            if Permissions.microphone == .denied {
                Text("Turn on Halo in System Settings › Privacy & Security › Microphone, then come back.")
                    .font(.system(size: 12)).foregroundStyle(.secondary).padding(.top, 6)
            }
        }
    }

    private var accessibility: some View {
        VStack(alignment: .leading) {
            title("Accessibility and Input Monitoring",
                  "Halo needs to notice your dictation key from any app, and to type the text "
                  + "where your cursor is. macOS asks you to allow both, once.")
            permissionRow("Accessibility", "Typing into the app you are using.",
                          ok: Permissions.accessibility) {
                let opts = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
                _ = AXIsProcessTrustedWithOptions(opts)
                SystemSettings.open(.accessibility)
            }
            permissionRow("Input Monitoring", "Hearing the dictation key anywhere.",
                          ok: Permissions.inputMonitoring == 0) {
                _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
                SystemSettings.open(.inputMonitoring)
            }
            Text("In System Settings, switch on Halo in each list. This page updates by itself. "
                 + "If macOS asks to quit Halo, allow it — this guide reopens where you left off.")
                .font(.system(size: 12)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true).padding(.top, 8)
        }
    }

    private func permissionRow(_ name: String, _ why: String, ok: Bool,
                               open: @escaping () -> Void) -> some View {
        HStack(spacing: 10) {
            StatusDot(ok: ok)
            VStack(alignment: .leading, spacing: 1) {
                Text(name).font(.system(size: 13, weight: .semibold))
                Text(why).font(.system(size: 11.5)).foregroundStyle(.secondary)
            }
            Spacer()
            if ok { Text("Allowed").foregroundStyle(.green) } else { Button("Open System Settings", action: open) }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.primary.opacity(0.05)))
        .padding(.bottom, 8)
    }

    private var microphone: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Choose a microphone", "Speak — the bar should move.")
            Picker("Microphone", selection: $store.micDevice) {
                Text("System Default (\(devices.defaultName))").tag("")
                ForEach(devices.devices) { Text("\($0.name) · \($0.kind)").tag($0.name) }
            }
            .frame(width: 420)
            .onAppear { devices.start() }
            .onChange(of: store.micDevice) { _, name in tester.start(deviceName: name) }
            LevelMeter(level: tester.level).frame(width: 420, height: 12)
            HStack {
                Button(tester.recording ? "Recording…" : "Record a test") { tester.record() }
                    .disabled(!tester.running || tester.recording)
                Button("Play it back") { tester.play() }.disabled(!tester.hasRecording)
            }
            if let m = tester.message { Note(text: m, failed: m.contains("silence") || m.contains("not")) }
        }
    }

    private var speechModel: some View {
        let rec = models.speech.first { $0.recommended }
        return VStack(alignment: .leading, spacing: 10) {
            title("Speech model",
                  "The model that turns your voice into text. "
                  + (rec.map { "For this Mac we recommend \($0.id) (\($0.sizeText))." } ?? ""))
            if !models.loaded { ProgressView() }
            ForEach(models.speech.filter { ["small.en", "base.en", "small"].contains($0.id) }) { m in
                ModelRow(models: models, model: m)
            }
            if let msg = models.message { Note(text: msg, failed: models.failed) }
            Text("Downloads are checked against a published checksum before Halo will use them. "
                 + "You can add the optional cleanup model later in Settings › Models.")
                .font(.system(size: 11.5)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var language: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Language", "What you will mostly dictate in. You can switch any time by saying "
                  + "“switch to Spanish”.")
            Picker("Language", selection: Binding(get: { store.language },
                                                  set: { store.setLanguage($0) })) {
                Text("Detect automatically").tag("auto")
                ForEach(LanguageInfo.all, id: \.0) { Text($0.1).tag($0.0) }
            }
            .frame(width: 320)
            if store.language != "en" {
                Text("Languages other than English need the multilingual speech model (small).")
                    .font(.system(size: 12)).foregroundStyle(.orange)
            }
        }
    }

    private var shortcut: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Your dictation key", "Hold it to talk, let go to send.")
            Picker("Key", selection: $store.hotkey) {
                ForEach(Hotkeys.all, id: \.self) { Text($0.uppercased()).tag($0) }
            }
            .frame(width: 220)
            HStack {
                Button(model.listeningForKey ? "Press your key now…" : "Test the key") { model.startKeyTest() }
                if model.keySeen == store.hotkey {
                    Label("\(store.hotkey.uppercased()) works.", systemImage: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                } else if model.keySeen == "media" {
                    Label("Your Mac sent a brightness or media key. Hold fn with it, or pick another key.",
                          systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                } else if !model.keySeen.isEmpty {
                    Label("That was \(model.keySeen.uppercased()), not \(store.hotkey.uppercased()).",
                          systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                }
            }
            Text("Hold Shift with it for Command Mode (edit selected text by voice). Escape cancels.")
                .font(.system(size: 12)).foregroundStyle(.secondary)
        }
    }

    private var test: some View {
        VStack(alignment: .leading, spacing: 10) {
            title("Try it", "Click in the box, hold \(store.hotkey.uppercased()), say “Hello Halo, "
                  + "this is a test”, and let go.")
            TextEditor(text: $model.testText)
                .font(.system(size: 14))
                .frame(height: 110)
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.primary.opacity(0.2)))
            if !model.testText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Label("It works — recording, transcription, cleanup and typing all went through.",
                      systemImage: "checkmark.seal.fill").foregroundStyle(.green)
            } else if EngineSupervisor.current?.state.hasPrefix("waiting") == true {
                Label("Halo is waiting for a permission or a model — go back a step.",
                      systemImage: "exclamationmark.triangle.fill").foregroundStyle(.orange)
            }
        }
    }

    private var complete: some View {
        VStack(alignment: .leading) {
            title("You're set.", "Halo runs in the background. The shortcuts:")
            bullet("keyboard", "Hold \(store.hotkey.uppercased()) and speak — let go to type it.")
            bullet("wand.and.stars", "Shift + \(store.hotkey.uppercased()): Command Mode — “make this shorter”.")
            bullet("escape", "Escape cancels, at any stage.")
            bullet("arrow.uturn.backward", "Say “scratch that” to remove what Halo just typed.")
            bullet("gearshape", "`halo settings`, or the menu bar icon, for everything else.")
        }
    }
}
