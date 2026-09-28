import AppKit
import CoreText
import SwiftUI

// Halo's chrome: one palette, one type scale, a handful of shared pieces.
//
// Night #000F08 and Imperial #FB3640 are the only brand colors; everything
// else is neutral white or gray for legibility. The values are the handoff's
// design-tokens.json (revision 3). Nothing here touches the orb: VoiceOrb and
// ThinkingOrbsKit keep their own grayscale rendering on purpose.
//
// No SwiftUI macros (@State, @Binding, @Observable): Halo builds with the
// Command Line Tools alone -- see CONTRIBUTING.md. Components take plain
// `Binding` values.

// MARK: - Resources

/// Where bundled fonts and brand art live: Halo.app/Contents/Resources in a
/// built app (build_app.sh copies them there), the source tree when run with
/// `swift run` from a checkout.
enum HaloResources {
    static let root: URL? = {
        if let res = Bundle.main.resourceURL,
           FileManager.default.fileExists(atPath: res.appendingPathComponent("Fonts").path) {
            return res
        }
        // overlay/Sources/HaloOverlay/DesignSystem.swift -> overlay/Resources
        let src = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Resources")
        return FileManager.default.fileExists(atPath: src.path) ? src : nil
    }()

    static func url(_ path: String) -> URL? {
        guard let root else { return nil }
        let u = root.appendingPathComponent(path)
        return FileManager.default.fileExists(atPath: u.path) ? u : nil
    }

    static func image(_ name: String) -> NSImage? {
        url("Brand/\(name)").flatMap { NSImage(contentsOf: $0) }
    }
}

// MARK: - Fonts

/// Registers the bundled fonts for this process only, before any window is
/// built. No font is installed system-wide and nothing is downloaded. A
/// missing file falls back to the system font; missing glyphs fall back the
/// way macOS always does.
enum HaloFonts {
    static let files = ["Oswald[wght].ttf", "SourceSans3[wght].ttf",
                        "SourceSans3-Italic[wght].ttf", "SourceCodePro[wght].ttf",
                        "NotoSerif-Italic[wdth,wght].ttf"]
    private(set) static var registered: [String] = []
    private static var done = false

    static func register() {
        guard !done else { return }
        done = true
        for file in files {
            guard let url = HaloResources.url("Fonts/\(file)") else { continue }
            var error: Unmanaged<CFError>?
            if CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) {
                registered.append(file)
            } else if let e = error?.takeRetainedValue(),
                      CFErrorGetCode(e) == CTFontManagerError.alreadyRegistered.rawValue {
                registered.append(file)
            }
        }
    }

    /// A family at a weight. Variable fonts are resolved through their named
    /// instances by weight trait; if the family is not available the system
    /// font stands in at the same size and weight.
    static func nsFont(_ family: String, size: CGFloat, weight: NSFont.Weight,
                       italic: Bool = false) -> NSFont {
        register()
        var traits: [NSFontDescriptor.TraitKey: Any] = [.weight: weight.rawValue]
        if italic { traits[.symbolic] = NSFontDescriptor.SymbolicTraits.italic.rawValue }
        let desc = NSFontDescriptor(fontAttributes: [.family: family, .traits: traits])
        if let font = NSFont(descriptor: desc, size: size),
           font.familyName == family {
            return font
        }
        return .systemFont(ofSize: size, weight: weight)
    }
}

/// The type roles from the handoff. Sizes are real app points.
enum HaloType {
    static func heading(_ size: CGFloat = 28, _ weight: NSFont.Weight = .semibold) -> Font {
        Font(HaloFonts.nsFont("Oswald", size: size, weight: weight))
    }
    static func body(_ size: CGFloat = 13, _ weight: NSFont.Weight = .regular) -> Font {
        Font(HaloFonts.nsFont("Source Sans 3", size: size, weight: weight))
    }
    static func brand(_ size: CGFloat = 20) -> Font {
        Font(HaloFonts.nsFont("Noto Serif", size: size, weight: .regular, italic: true))
    }
    static func mono(_ size: CGFloat = 12, _ weight: NSFont.Weight = .medium) -> Font {
        Font(HaloFonts.nsFont("Source Code Pro", size: size, weight: weight))
    }

    static var pageTitle: Font { heading(28) }
    static var sectionTitle: Font { heading(17) }
    static var control: Font { body(13) }
    static var controlStrong: Font { body(13, .semibold) }
    static var support: Font { body(12) }
    static var caption: Font { body(11, .semibold) }
}

// MARK: - Colors

/// Semantic colors, resolved per appearance at draw time.
enum HaloColor {
    static let night = Color(nsColor: NSColor(hex: 0x000F08))
    static let imperial = Color(nsColor: NSColor(hex: 0xFB3640))
    /// Text on an Imperial fill is always Night (5.3:1).
    static let onImperial = night

    static let background = dynamic(light: 0xFFFFFF, dark: 0x000F08)
    static let sidebar = dynamic(light: 0xF2F2F2, dark: 0x000F08)
    static let surface = dynamic(light: 0xFFFFFF, dark: 0x181818)
    static let border = dynamic(light: 0xB8B8B8, dark: 0x666666, contrast: (0x4A4A4A, 0xB0B0B0))
    static let subtleBorder = dynamic(light: 0xDADADA, dark: 0x2E2E2E, contrast: (0x4A4A4A, 0xB0B0B0))
    static let text = dynamic(light: 0x000F08, dark: 0xFFFFFF)
    static let secondaryText = dynamic(light: 0x4A4A4A, dark: 0xD0D0D0)
    /// Imperial on dark, Night on light: small Imperial text on white is not
    /// legible enough, so light mode uses Night for accents in text.
    static let accentText = dynamic(light: 0x000F08, dark: 0xFB3640)
    static let selection = dynamic(light: 0xEBEBEB, dark: 0x101010)
    static let control = dynamic(light: 0xF2F2F2, dark: 0x242424)

    static func dynamic(light: UInt32, dark: UInt32,
                        contrast: (UInt32, UInt32)? = nil) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            if let contrast, NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast {
                return NSColor(hex: isDark ? contrast.1 : contrast.0)
            }
            return NSColor(hex: isDark ? dark : light)
        })
    }
}

extension NSColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
                  green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255, alpha: alpha)
    }
}

enum HaloMetrics {
    static let controlRadius: CGFloat = 7
    static let cardRadius: CGFloat = 12
    static let sidebarWidth: CGFloat = 192
    static let contentPadding: CGFloat = 28
    static let compactPadding: CGFloat = 20
}

// MARK: - Status

/// A state, always shown as symbol + words. Color alone never says error,
/// selection or success.
enum HaloStatus {
    case ok, info, warning, error, working

    var symbol: String {
        switch self {
        case .ok: return "checkmark.circle.fill"
        case .info: return "info.circle"
        case .warning: return "exclamationmark.triangle.fill"
        case .error: return "xmark.octagon.fill"
        case .working: return "arrow.triangle.2.circlepath"
        }
    }

    var tint: Color {
        switch self {
        case .warning, .error: return HaloColor.imperial
        case .ok: return HaloColor.text
        case .info, .working: return HaloColor.secondaryText
        }
    }

    /// Spoken by VoiceOver before the label, so the state is not only visual.
    var spoken: String {
        switch self {
        case .ok: return "OK"
        case .info: return "Note"
        case .warning: return "Warning"
        case .error: return "Error"
        case .working: return "In progress"
        }
    }
}

/// A compact state chip: icon + label, e.g. "Ready", "Model missing".
struct StateLabel: View {
    let status: HaloStatus
    let text: String

    var body: some View {
        HStack(spacing: 5) {
            if status == .working {
                ProgressView().controlSize(.mini)
            } else {
                Image(systemName: status.symbol).foregroundStyle(status.tint)
            }
            Text(text).foregroundStyle(HaloColor.text)
        }
        .font(HaloType.body(11.5, .semibold))
        .padding(.horizontal, 9)
        .padding(.vertical, 4)
        .background(Capsule().fill(HaloColor.control))
        .overlay(Capsule().strokeBorder(HaloColor.subtleBorder, lineWidth: 1))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(status.spoken): \(text)")
    }
}

/// A full-width message with a symbol, a title, readable detail and actions.
struct HaloBanner<Actions: View>: View {
    let status: HaloStatus
    let title: String
    var message: String? = nil
    @ViewBuilder var actions: Actions

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: status.symbol)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(status.tint)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
                if let message {
                    Text(message).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 8)
            actions
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius + 2)
            .fill(HaloColor.control))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius + 2)
            .strokeBorder(status == .error || status == .warning
                          ? HaloColor.imperial : HaloColor.subtleBorder, lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(status.spoken): \(title)")
    }
}

extension HaloBanner where Actions == EmptyView {
    init(status: HaloStatus, title: String, message: String? = nil) {
        self.init(status: status, title: title, message: message) { EmptyView() }
    }
}

// MARK: - Layout pieces

/// A card: the surface every settings group sits on.
struct HaloCard<Content: View>: View {
    var padding: CGFloat = 16
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) { content }
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: HaloMetrics.cardRadius)
                .fill(HaloColor.surface))
            .overlay(RoundedRectangle(cornerRadius: HaloMetrics.cardRadius)
                .strokeBorder(HaloColor.subtleBorder, lineWidth: 1))
    }
}

/// One setting: a label (and optional detail) on the left, its control on
/// the right. Wraps under the label when the window is narrow.
struct SettingRow<Control: View>: View {
    let title: String
    var detail: String? = nil
    @ViewBuilder var control: Control

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .center, spacing: 16) {
                labels
                Spacer(minLength: 8)
                control
            }
            VStack(alignment: .leading, spacing: 8) {
                labels
                control
            }
        }
    }

    private var labels: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(HaloType.control).foregroundStyle(HaloColor.text)
            if let detail {
                Text(detail).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// A keyboard key or shortcut, in Source Code Pro.
struct KeyCap: View {
    let text: String

    var body: some View {
        Text(text)
            .font(HaloType.mono(12, .semibold))
            .foregroundStyle(HaloColor.text)
            .padding(.horizontal, 9)
            .padding(.vertical, 4)
            .background(RoundedRectangle(cornerRadius: 6).fill(HaloColor.control))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(HaloColor.border, lineWidth: 1))
            .accessibilityLabel("Key \(text)")
    }
}

/// Deterministic sample copy, labelled so it is never mistaken for a live
/// result.
struct ExampleBox: View {
    let said: String
    let typed: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("EXAMPLE").font(HaloType.mono(10, .semibold)).foregroundStyle(HaloColor.secondaryText)
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text("“\(said)”").foregroundStyle(HaloColor.secondaryText)
                Image(systemName: "arrow.right").font(.system(size: 10)).foregroundStyle(HaloColor.secondaryText)
                    .accessibilityLabel("becomes")
                Text("“\(typed)”").foregroundStyle(HaloColor.text)
            }
            .font(HaloType.support)
            .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius).fill(HaloColor.selection))
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Buttons

/// Imperial fill, Night text. One per view, for the main action.
struct HaloPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        PrimaryBody(configuration: configuration)
    }

    private struct PrimaryBody: View {
        let configuration: ButtonStyleConfiguration
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            configuration.label
                .font(HaloType.controlStrong)
                .foregroundStyle(HaloColor.onImperial)
                .padding(.horizontal, 16)
                .padding(.vertical, 7)
                .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                    .fill(HaloColor.imperial.opacity(configuration.isPressed ? 0.82 : 1)))
                .opacity(enabled ? 1 : 0.45)
                .contentShape(Rectangle())
        }
    }
}

/// Neutral control fill with a visible border.
struct HaloSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        SecondaryBody(configuration: configuration)
    }

    private struct SecondaryBody: View {
        let configuration: ButtonStyleConfiguration
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            configuration.label
                .font(HaloType.controlStrong)
                .foregroundStyle(HaloColor.text)
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                    .fill(HaloColor.control.opacity(configuration.isPressed ? 0.7 : 1)))
                .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                    .strokeBorder(HaloColor.border, lineWidth: 1))
                .opacity(enabled ? 1 : 0.45)
                .contentShape(Rectangle())
        }
    }
}

extension ButtonStyle where Self == HaloPrimaryButtonStyle {
    static var haloPrimary: HaloPrimaryButtonStyle { HaloPrimaryButtonStyle() }
}

extension ButtonStyle where Self == HaloSecondaryButtonStyle {
    static var haloSecondary: HaloSecondaryButtonStyle { HaloSecondaryButtonStyle() }
}

// MARK: - Brand

/// The outlined HALO wordmark: white on dark, Night on light. Never
/// stretched; height sets the size.
struct HaloWordmark: View {
    var height: CGFloat = 22
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        if let img = HaloResources.image(scheme == .dark ? "halo-wordmark-white.png"
                                                        : "halo-wordmark-night.png") {
            Image(nsImage: img).resizable().interpolation(.high)
                .aspectRatio(contentMode: .fit).frame(height: height)
                .accessibilityLabel("Halo")
        } else {
            Text("HALO").font(HaloType.heading(height, .bold)).accessibilityLabel("Halo")
        }
    }
}

/// The seven-dot H in its open halo, in Imperial. For 32 pt and up; smaller
/// uses the menu template.
struct HaloMark: View {
    var size: CGFloat = 32

    var body: some View {
        if let img = HaloResources.image("halo-mark-imperial.png") {
            Image(nsImage: img).resizable().interpolation(.high)
                .aspectRatio(contentMode: .fit).frame(width: size, height: size)
                .accessibilityHidden(true)
        }
    }
}

/// A small uppercase group label (sidebar sections, onboarding phases).
struct GroupLabel: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(HaloType.body(10.5, .semibold))
            .tracking(0.8)
            .foregroundStyle(HaloColor.secondaryText)
            .accessibilityAddTraits(.isHeader)
    }
}
