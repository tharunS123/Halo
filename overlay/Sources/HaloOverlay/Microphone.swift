import AVFoundation
import CoreAudio
import Foundation

/// Input devices, straight from CoreAudio, kept current as things are
/// plugged in and out -- so the list in Settings never needs a restart.
///
/// The engine records through PortAudio and picks the device by NAME
/// (audio.py), which is what CoreAudio reports here too; that shared name is
/// the whole contract between the two.
@MainActor
final class AudioDevices: ObservableObject {
    static let shared = AudioDevices()

    struct Device: Identifiable, Equatable {
        let id: AudioDeviceID
        let uid: String
        let name: String
        let kind: String        // Built-in, Bluetooth, USB, Virtual, ...
    }

    @Published var devices: [Device] = []
    @Published var defaultName = ""
    private var listening = false

    func start() {
        refresh()
        guard !listening else { return }
        listening = true
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices, mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        let block: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
            Task { @MainActor in self?.refresh() }
        }
        AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &addr,
                                            DispatchQueue.main, block)
        var def = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &def,
                                            DispatchQueue.main, block)
    }

    func refresh() {
        devices = Self.inputDevices()
        if let d = Self.defaultInput() { defaultName = Self.string(d, kAudioObjectPropertyName) }
    }

    func device(named name: String) -> Device? { devices.first { $0.name == name } }

    private static func inputDevices() -> [Device] {
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices, mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil,
                                             &size) == noErr else { return [] }
        var ids = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil,
                                         &size, &ids) == noErr else { return [] }
        return ids.compactMap { id in
            guard inputChannels(id) > 0 else { return nil }
            return Device(id: id, uid: string(id, kAudioDevicePropertyDeviceUID),
                          name: string(id, kAudioObjectPropertyName), kind: transport(id))
        }
    }

    static func defaultInput() -> AudioDeviceID? {
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
        var id = AudioDeviceID(0)
        var size = UInt32(MemoryLayout<AudioDeviceID>.size)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &addr, 0, nil,
                                         &size, &id) == noErr, id != 0 else { return nil }
        return id
    }

    private static func inputChannels(_ id: AudioDeviceID) -> Int {
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamConfiguration, mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(id, &addr, 0, nil, &size) == noErr, size > 0 else { return 0 }
        let raw = UnsafeMutableRawPointer.allocate(byteCount: Int(size),
                                                   alignment: MemoryLayout<AudioBufferList>.alignment)
        defer { raw.deallocate() }
        guard AudioObjectGetPropertyData(id, &addr, 0, nil, &size, raw) == noErr else { return 0 }
        let list = UnsafeMutableAudioBufferListPointer(raw.assumingMemoryBound(to: AudioBufferList.self))
        return list.reduce(0) { $0 + Int($1.mNumberChannels) }
    }

    private static func string(_ id: AudioDeviceID, _ selector: AudioObjectPropertySelector) -> String {
        var addr = AudioObjectPropertyAddress(mSelector: selector,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        var value: Unmanaged<CFString>?
        var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &value) == noErr,
              let s = value?.takeRetainedValue() else { return "" }
        return s as String
    }

    private static func transport(_ id: AudioDeviceID) -> String {
        var addr = AudioObjectPropertyAddress(mSelector: kAudioDevicePropertyTransportType,
                                              mScope: kAudioObjectPropertyScopeGlobal,
                                              mElement: kAudioObjectPropertyElementMain)
        var t: UInt32 = 0
        var size = UInt32(MemoryLayout<UInt32>.size)
        guard AudioObjectGetPropertyData(id, &addr, 0, nil, &size, &t) == noErr else { return "Other" }
        switch t {
        case kAudioDeviceTransportTypeBuiltIn: return "Built-in"
        case kAudioDeviceTransportTypeBluetooth, kAudioDeviceTransportTypeBluetoothLE: return "Bluetooth"
        case kAudioDeviceTransportTypeUSB: return "USB"
        case kAudioDeviceTransportTypeVirtual: return "Virtual"
        case kAudioDeviceTransportTypeAggregate: return "Aggregate"
        case kAudioDeviceTransportTypeThunderbolt: return "Thunderbolt"
        case kAudioDeviceTransportTypeFireWire: return "FireWire"
        case kAudioDeviceTransportTypeContinuityCaptureWired,
             kAudioDeviceTransportTypeContinuityCaptureWireless: return "iPhone"
        default: return "Other"
        }
    }
}

/// The Microphone pane's live meter, test recording and playback.
///
/// The one place the app itself opens the microphone -- and only while that
/// pane or the onboarding screen is on screen. The orb still never does:
/// during dictation the engine owns the microphone and streams levels to it.
@MainActor
final class MicTester: ObservableObject {
    static let shared = MicTester()

    @Published var level: Double = 0
    @Published var running = false
    @Published var recording = false
    @Published var hasRecording = false
    @Published var playing = false
    @Published var peak: Double = 0
    @Published var message: String?

    private var engine: AVAudioEngine?
    private var file: AVAudioFile?
    private var player: AVAudioPlayer?
    private var stopAt: Date?
    private let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("halo-mic-test.caf")

    /// Start metering `deviceName` ("" = system default).
    func start(deviceName: String) {
        stop()
        guard Permissions.microphone == .authorized else {
            message = Permissions.microphone == .notDetermined
                ? "Halo needs permission to use the microphone."
                : "Microphone access is off for Halo in System Settings."
            return
        }
        let e = AVAudioEngine()
        let input = e.inputNode
        if !deviceName.isEmpty, let d = AudioDevices.shared.device(named: deviceName) {
            try? input.auAudioUnit.setDeviceID(d.id)
        }
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0 else {
            message = "That microphone is not delivering audio."
            return
        }
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let ch = buffer.floatChannelData?[0] else { return }
            var sum: Float = 0
            var top: Float = 0
            for i in 0..<Int(buffer.frameLength) {
                sum += ch[i] * ch[i]
                top = max(top, abs(ch[i]))
            }
            let rms = sqrt(sum / Float(max(buffer.frameLength, 1)))
            Task { @MainActor [weak self] in self?.push(buffer: buffer, rms: Double(rms), peak: Double(top)) }
        }
        do {
            try e.start()
            engine = e
            running = true
            message = nil
        } catch {
            message = "Could not open that microphone."
        }
    }

    private func push(buffer: AVAudioPCMBuffer, rms: Double, peak: Double) {
        // Same shape as the orb: a little gain, a curve, fast rise, slow fall.
        let target = min(1, pow(min(1, rms * 12), 0.6))
        level = target > level ? target : level * 0.8 + target * 0.2
        if recording, let file {
            try? file.write(from: buffer)
            self.peak = max(self.peak, peak)
            if let stopAt, Date() >= stopAt { finishRecording() }
        }
    }

    func stop() {
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        running = false
        recording = false
        level = 0
    }

    /// Record three seconds for playback.
    func record() {
        guard let e = engine else { return }
        try? FileManager.default.removeItem(at: url)
        file = try? AVAudioFile(forWriting: url, settings: e.inputNode.outputFormat(forBus: 0).settings)
        peak = 0
        recording = true
        hasRecording = false
        stopAt = Date().addingTimeInterval(3)
        message = "Recording… say something."
    }

    private func finishRecording() {
        recording = false
        file = nil
        hasRecording = true
        message = peak < 0.01
            ? "That was silence. Check the microphone is not muted, or pick another."
            : "Recorded. Play it back to hear how Halo hears you."
    }

    func play() {
        player = try? AVAudioPlayer(contentsOf: url)
        playing = player?.play() ?? false
        DispatchQueue.main.asyncAfter(deadline: .now() + (player?.duration ?? 0) + 0.1) { [weak self] in
            self?.playing = false
        }
    }
}
