import AVFoundation
import ApplicationServices
import Foundation
import IOKit.hid

/// TCC state for THIS process. Authoritative for the whole system, because the
/// Python engine runs as our child and therefore inherits this bundle as its
/// responsible process. Checking from any other process (a shell, an editor)
/// reports that process's grants instead, which is misleading.
enum Permissions {
    static var accessibility: Bool { AXIsProcessTrusted() }

    /// 0 granted, 1 denied, 2 unknown
    static var inputMonitoring: UInt32 {
        IOHIDCheckAccess(kIOHIDRequestTypeListenEvent).rawValue
    }

    /// The Microphone pane in System Settings has no "+" button: an app only
    /// appears there once it has ASKED. A background agent that never asks is
    /// therefore un-grantable by hand, so we ask explicitly at startup.
    static var microphone: AVAuthorizationStatus {
        AVCaptureDevice.authorizationStatus(for: .audio)
    }

    static func requestMicrophone(_ done: @escaping (Bool) -> Void) {
        AVCaptureDevice.requestAccess(for: .audio) { granted in
            DispatchQueue.main.async { done(granted) }
        }
    }

    static var microphoneText: String {
        switch microphone {
        case .authorized:    return "OK"
        case .denied:        return "DENIED"
        case .restricted:    return "restricted"
        case .notDetermined: return "not yet requested"
        @unknown default:    return "unknown"
        }
    }

    static var summary: String {
        let im = inputMonitoring
        let imText = im == 0 ? "OK" : (im == 1 ? "denied" : "not granted")
        return """
        accessibility    : \(accessibility ? "OK" : "NOT GRANTED")
        input monitoring : \(imText)
        microphone       : \(microphoneText)
        """
    }
}
