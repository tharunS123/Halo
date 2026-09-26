import AppKit
import ApplicationServices
import IOKit.hid
import SwiftUI

// MARK: - History

struct HistoryPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI
    @ObservedObject var history = HistoryStore.shared

    static let retentions: [(String, String)] = [
        ("never", "Never keep"), ("1h", "1 hour"), ("24h", "24 hours"), ("7d", "7 days"),
        ("30d", "30 days"), ("forever", "Forever"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "History",
                      subtitle: "Off unless you turn it on. Kept only on this Mac, never with the text around your cursor, never for password fields.")

            Block(title: "Keep a history",
                  note: "Turning it off deletes what was kept.") {
                Toggle("Keep a history of my dictations", isOn: $store.historyEnabled)
                Picker("Keep text for", selection: $store.historyRetention) {
                    ForEach(Self.retentions, id: \.0) { Text($0.1).tag($0.0) }
                }
                .frame(width: 280)
                .disabled(!store.historyEnabled)
                Toggle("Also keep the audio (lets you retry transcription)", isOn: $store.historyKeepAudio)
                    .disabled(!store.historyEnabled)
                if store.historyKeepAudio {
                    Picker("Keep audio for", selection: $store.historyAudioRetention) {
                        ForEach(Self.retentions, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    .frame(width: 280)
                    .disabled(!store.historyEnabled)
                }
            }

            HStack {
                TextField("Search", text: $history.query)
                    .textFieldStyle(.roundedBorder).frame(width: 240)
                    .onSubmit { history.load() }
                Button("Search") { history.load() }.controlSize(.small)
                Spacer()
                if history.busy { ProgressView().controlSize(.small) }
                Button("Clear all…", role: .destructive) { ui.confirmClearHistory = true }
                    .disabled(history.items.isEmpty)
            }
            .padding(.bottom, 8)
            if let m = history.message { Note(text: m, failed: m.contains("Not") || m.contains("not")).padding(.bottom, 6) }

            if history.items.isEmpty {
                Text(store.historyEnabled ? "Nothing yet. Dictate something." : "History is off.")
                    .font(.system(size: 12)).foregroundStyle(.secondary).padding(.vertical, 20)
            }
            VStack(spacing: 4) {
                ForEach(history.items) { item in HistoryRow(history: history, item: item) }
            }
        }
        .onAppear { history.load() }
        .onChange(of: store.historyEnabled) { _, _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { history.load() }
        }
        .alert("Delete all dictation history?", isPresented: $ui.confirmClearHistory) {
            Button("Delete", role: .destructive) { history.clearAll() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Every kept dictation and recording is removed from this Mac.")
        }
    }
}

struct HistoryRow: View {
    @ObservedObject var history: HistoryStore
    let item: HistoryStore.Item

    private var open: Bool { history.selected == item.id }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                history.selected = open ? nil : item.id
            } label: {
                HStack(spacing: 8) {
                    Text(item.created, style: .time).font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(.secondary).frame(width: 64, alignment: .leading)
                    Text(item.cleaned.isEmpty ? item.raw : item.cleaned)
                        .font(.system(size: 12)).lineLimit(1)
                    Spacer()
                    Text(item.app.isEmpty ? "—" : item.app).font(.system(size: 10)).foregroundStyle(.secondary)
                    Image(systemName: item.status == "inserted" ? "checkmark.circle" : "exclamationmark.circle")
                        .foregroundStyle(item.status == "inserted" ? Color.green : Color.orange)
                        .font(.system(size: 11))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if open {
                VStack(alignment: .leading, spacing: 4) {
                    Text(item.created.formatted(date: .abbreviated, time: .standard)
                         + String(format: " · %.1fs", item.duration)
                         + " · \(item.language) · \(item.mode) · \(item.status)"
                         + (item.reason.isEmpty ? "" : " (\(item.reason))"))
                        .font(.system(size: 10.5)).foregroundStyle(.secondary)
                    Text("Heard").font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                    Text(item.raw).font(.system(size: 12)).textSelection(.enabled)
                    Text("Typed").font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                    Text(item.cleaned).font(.system(size: 12)).textSelection(.enabled)
                    HStack(spacing: 6) {
                        Button("Copy") { history.copy(item) }
                        Button("Reinsert") { history.reinsert(item) }
                            .help("Hides this window and types it into the app underneath")
                        Button("Retry cleanup") { history.retry(item, transcription: false) }
                        Button("Retry transcription") { history.retry(item, transcription: true) }
                            .disabled(!item.hasAudio)
                        Spacer()
                        Button("Delete", role: .destructive) { history.delete(item) }
                    }
                    .controlSize(.small)
                    .disabled(history.busy)
                }
                .padding(.leading, 72)
            }
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 6)
            .fill(open ? Color.accentColor.opacity(0.06) : Color.primary.opacity(0.035)))
    }
}

// MARK: - Privacy

struct PrivacyPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI
    @ObservedObject var keys = KeyStore.shared

    private var openRouterPossible: Bool {
        store.cleanupEnabled && keys.stored && store.cleanupProvider != "local"
            && store.cleanupProvider != "none"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Privacy",
                      subtitle: "What stays on this Mac, what could leave it, and where your data lives.")

            Block(title: "Status") {
                statusRow(true, "Audio never leaves this Mac — whisper runs locally.")
                statusRow(true, "The text around your cursor never leaves this Mac"
                          + (store.contextEnabled ? " (Context Awareness is on, in memory only)."
                                                  : " (Context Awareness is off)."))
                statusRow(!openRouterPossible,
                          openRouterPossible
                            ? "Transcript text MAY be sent to OpenRouter when no local model is ready — unless Privacy Mode is on."
                            : "Transcript text stays on this Mac.")
                statusRow(true, store.historyEnabled
                          ? "History is on: kept on this Mac for \(store.historyRetention)."
                          : "History is off: no transcripts are kept.")
                statusRow(!store.debugLogContent, store.debugLogContent
                          ? "Debug content logging is ON: dictated text is written to engine.log."
                          : "Logs record lengths, never what you said.")
            }

            Block(title: "OpenRouter",
                  note: "Optional, and only used when no local model is ready. OpenRouter's free "
                      + "endpoints require allowing data training on your account, so a provider "
                      + "may retain what you send. Custom styles, context and your cursor text are "
                      + "never sent.") {
                Toggle("Allow transcripts to be sent to OpenRouter for cleanup", isOn: $store.cleanupEnabled)
                Toggle("Start with Privacy Mode on (say “privacy on” any time)", isOn: $store.privacyDefault)
                HStack(spacing: 10) {
                    Image(systemName: keys.stored ? "key.fill" : "key.slash")
                        .foregroundStyle(keys.stored ? .green : .secondary)
                    Text(keys.stored ? "An OpenRouter key is stored in your Keychain."
                                     : "No key stored.").font(.system(size: 12))
                    Spacer()
                    if keys.stored {
                        Button("Remove", role: .destructive) { keys.clear() }.controlSize(.small)
                    }
                }
                HStack(spacing: 8) {
                    SecureField(keys.stored ? "Paste a new key to replace it" : "sk-or-v1-…",
                                text: $keys.draft)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { keys.save() }
                    Button(keys.stored ? "Replace" : "Save") { keys.save() }
                        .disabled(keys.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                if let message = keys.message { Note(text: message, failed: keys.failed) }
            }

            Block(title: "Where your data lives") {
                location("Settings, dictionary, styles, transforms", HaloPaths.configDir)
                location("Models, history, state", HaloPaths.dataDir)
                location("Logs (no dictated text)", HaloPaths.logDir)
            }

            Block(title: "Clear stored data") {
                HStack(spacing: 8) {
                    Button("Clear history") { HistoryStore.shared.clearAll(); ui.dataMessage = "History cleared." }
                    Button("Clear word suggestions") {
                        try? FileManager.default.removeItem(at: HaloPaths.suggestions)
                        VocabularyStore.shared.loadSuggestions()
                        ui.dataMessage = "Suggestions cleared."
                    }
                    Button("Clear logs") {
                        for name in ["engine.log", "overlay.log"] {
                            try? Data().write(to: HaloPaths.logDir.appendingPathComponent(name))
                        }
                        ui.dataMessage = "Logs cleared."
                    }
                }
                if let m = ui.dataMessage { Note(text: m) }
            }
        }
        .onAppear { keys.refresh() }
    }

    private func statusRow(_ ok: Bool, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            StatusDot(ok: ok, warn: !ok).padding(.top, 4)
            Text(text).font(.system(size: 12)).fixedSize(horizontal: false, vertical: true)
        }
    }

    private func location(_ label: String, _ url: URL) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text(label).font(.system(size: 12))
                Text(url.path.replacingOccurrences(of: HaloPaths.home.path, with: "~"))
                    .font(.system(size: 10.5, design: .monospaced)).foregroundStyle(.secondary)
            }
            Spacer()
            Button("Reveal") { NSWorkspace.shared.activateFileViewerSelecting([url]) }
                .controlSize(.small)
        }
    }
}

// MARK: - Permissions

struct PermissionsPane: View {
    var body: some View {
        // Re-read every second while visible: grants happen in another app.
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            VStack(alignment: .leading, spacing: 0) {
                PaneTitle(title: "Permissions",
                          subtitle: "What macOS must allow for Halo to work. Granted to Halo.app, which runs the engine.")
                row("Microphone", "Recording while you hold the key.",
                    ok: Permissions.microphone == .authorized,
                    text: Permissions.microphoneText) {
                    if Permissions.microphone == .notDetermined {
                        Button("Allow") { Permissions.requestMicrophone { _ in } }
                    } else {
                        Button("Open System Settings") { SystemSettings.open(.microphone) }
                    }
                }
                row("Accessibility", "Typing the text, reading context, undo.",
                    ok: Permissions.accessibility,
                    text: Permissions.accessibility ? "OK" : "not granted") {
                    Button("Open System Settings") {
                        let opts = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
                        _ = AXIsProcessTrustedWithOptions(opts)
                        SystemSettings.open(.accessibility)
                    }
                }
                row("Input Monitoring", "Noticing the dictation key, anywhere.",
                    ok: Permissions.inputMonitoring == 0,
                    text: Permissions.inputMonitoring == 0 ? "OK" : "not granted") {
                    Button("Open System Settings") {
                        _ = IOHIDRequestAccess(kIOHIDRequestTypeListenEvent)
                        SystemSettings.open(.inputMonitoring)
                    }
                }
                Text("After granting Accessibility, Halo restarts its engine by itself within a "
                     + "couple of seconds. If macOS asks you to quit Halo, do — it comes back at login "
                     + "or with `halo start`.")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 4)
            }
        }
    }

    private func row<B: View>(_ title: String, _ why: String, ok: Bool, text: String,
                              @ViewBuilder action: () -> B) -> some View {
        HStack(spacing: 10) {
            StatusDot(ok: ok)
            VStack(alignment: .leading, spacing: 1) {
                Text(title).font(.system(size: 12.5, weight: .semibold))
                Text(why).font(.system(size: 11)).foregroundStyle(.secondary)
            }
            Spacer()
            Text(text).font(.system(size: 11)).foregroundStyle(ok ? Color.green : Color.orange)
            if !ok { action().controlSize(.small) }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 6).fill(Color.primary.opacity(0.04)))
        .padding(.bottom, 8)
    }
}

// MARK: - Advanced

struct AdvancedPane: View {
    @ObservedObject var store: SettingsStore
    @ObservedObject var ui: SettingsUI

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            PaneTitle(title: "Advanced", subtitle: "Engine health, diagnostics and the settings you rarely need.")

            Block(title: "Engine health") {
                if let sup = EngineSupervisor.current {
                    SupervisorStatus(supervisor: sup)
                } else {
                    Text("Running in terminal mode: `python halo.py` owns the engine.")
                        .font(.system(size: 12)).foregroundStyle(.secondary)
                }
                if let e = ui.healthError {
                    Note(text: e, failed: true)
                } else if !ui.health.isEmpty {
                    Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 3) {
                        ForEach(ui.health.keys.sorted(), id: \.self) { k in
                            GridRow {
                                Text(k.replacingOccurrences(of: "_", with: " "))
                                    .font(.system(size: 11)).foregroundStyle(.secondary)
                                Text(ui.health[k] ?? "").font(.system(size: 11, design: .monospaced))
                            }
                        }
                    }
                }
                HStack {
                    Button("Refresh") { refresh() }.controlSize(.small)
                    Button("Restart engine") {
                        EngineSupervisor.current?.restart()
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { refresh() }
                    }
                    .controlSize(.small).disabled(EngineSupervisor.current == nil)
                    Button("Open engine log") { NSWorkspace.shared.open(HaloPaths.engineLog) }
                        .controlSize(.small)
                }
            }

            Block(title: "Insertion",
                  note: "Automatic picks per app: Accessibility where the app honours it and the "
                      + "result can be verified, paste (with your clipboard restored) elsewhere, "
                      + "typed keystrokes for remote desktops.") {
                Picker("Method", selection: $store.insertionMethod) {
                    Text("Automatic (recommended)").tag("auto")
                    Text("Accessibility").tag("ax")
                    Text("Paste").tag("paste")
                    Text("Type").tag("type")
                }
                .frame(width: 300)
            }

            Block(title: "Debug content logging",
                  note: "For chasing a bug only. While on, what you dictate, selected text and "
                      + "commands are written to engine.log in plain text. Off by default; turn it "
                      + "off again when done.") {
                Toggle(isOn: $store.debugLogContent) {
                    Text("Write dictated text to the engine log")
                        .foregroundStyle(store.debugLogContent ? Color.orange : Color.primary)
                }
            }

            Block(title: "Reset",
                  note: "Every setting back to its default. Your dictionary, styles, transforms, "
                      + "history and models are not touched.") {
                Button("Reset all settings…", role: .destructive) { ui.confirmReset = true }
            }
        }
        .onAppear { refresh() }
        .alert("Reset all settings?", isPresented: $ui.confirmReset) {
            Button("Reset", role: .destructive) { store.resetToDefaults() }
            Button("Cancel", role: .cancel) {}
        }
    }

    private func refresh() {
        EngineClient.request(["op": "health"], timeout: 3) { reply in
            guard let reply, reply["ok"] as? Bool == true else {
                ui.health = [:]
                ui.healthError = "The engine is not answering."
                return
            }
            ui.healthError = nil
            var h: [String: String] = [:]
            for (k, v) in reply where k != "ok" { h[k] = "\(v)" }
            ui.health = h
        }
    }
}

struct SupervisorStatus: View {
    @ObservedObject var supervisor: EngineSupervisor

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 8) {
                StatusDot(ok: supervisor.state == "running", warn: supervisor.state.hasPrefix("waiting"))
                Text("Engine: \(supervisor.state)" + (supervisor.pid > 0 ? " (pid \(supervisor.pid))" : ""))
                    .font(.system(size: 12))
            }
            if let started = supervisor.startedAt {
                Text("Up since \(started.formatted(date: .omitted, time: .shortened))"
                     + " · \(supervisor.crashes.count) crash\(supervisor.crashes.count == 1 ? "" : "es") recorded"
                     + (supervisor.lastExit.map { " · last exit \($0)" } ?? ""))
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
        }
    }
}
