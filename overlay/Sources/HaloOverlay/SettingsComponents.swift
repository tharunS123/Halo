import AppKit
import SwiftUI

// Pieces the Settings panes share beyond DesignSystem.swift: smaller buttons,
// a text field style, custom radio / segmented / checkbox controls (the native
// ones ignore the brand palette on macOS), empty states, and a few rows.
//
// No SwiftUI macros: components take plain `Binding` values (see
// CONTRIBUTING.md).

// MARK: - Buttons

/// Compact buttons for rows and lists. `secondary` is the neutral one;
/// `primary` is Imperial with Night text; `destructive` keeps neutral text but
/// carries an Imperial outline and a symbol at the call site, so it is never
/// distinguished by color alone.
struct HaloSmallButtonStyle: ButtonStyle {
    enum Kind { case primary, secondary, destructive }
    var kind: Kind = .secondary

    func makeBody(configuration: Configuration) -> some View {
        SmallBody(configuration: configuration, kind: kind)
    }

    private struct SmallBody: View {
        let configuration: ButtonStyleConfiguration
        let kind: Kind
        @Environment(\.isEnabled) private var enabled

        var body: some View {
            let shape = RoundedRectangle(cornerRadius: HaloMetrics.controlRadius - 1)
            configuration.label
                .font(HaloType.body(12, .semibold))
                .foregroundStyle(kind == .primary ? HaloColor.onImperial : HaloColor.text)
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(shape.fill(fill))
                .overlay(shape.strokeBorder(stroke, lineWidth: 1))
                .opacity(enabled ? 1 : 0.45)
                .contentShape(Rectangle())
        }

        private var fill: Color {
            switch kind {
            case .primary: return HaloColor.imperial.opacity(configuration.isPressed ? 0.82 : 1)
            default: return HaloColor.control.opacity(configuration.isPressed ? 0.7 : 1)
            }
        }

        private var stroke: Color {
            switch kind {
            case .primary: return .clear
            case .secondary: return HaloColor.border
            case .destructive: return HaloColor.imperial
            }
        }
    }
}

extension ButtonStyle where Self == HaloSmallButtonStyle {
    static var haloSmall: HaloSmallButtonStyle { HaloSmallButtonStyle(kind: .secondary) }
    static var haloSmallPrimary: HaloSmallButtonStyle { HaloSmallButtonStyle(kind: .primary) }
    static var haloDestructive: HaloSmallButtonStyle { HaloSmallButtonStyle(kind: .destructive) }
}

/// A borderless icon button (remove, delete) with a required spoken label.
struct IconButton: View {
    let symbol: String
    let label: String
    var role: ButtonRole? = nil
    let action: () -> Void

    var body: some View {
        Button(role: role, action: action) {
            Image(systemName: symbol)
                .font(.system(size: 13))
                .foregroundStyle(HaloColor.secondaryText)
                .frame(width: 26, height: 26)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(label)
        .accessibilityLabel(label)
    }
}

// MARK: - Text input

struct HaloTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .textFieldStyle(.plain)
            .font(HaloType.control)
            .foregroundStyle(HaloColor.text)
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                .fill(HaloColor.control))
            .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                .strokeBorder(HaloColor.border, lineWidth: 1))
    }
}

extension TextFieldStyle where Self == HaloTextFieldStyle {
    static var halo: HaloTextFieldStyle { HaloTextFieldStyle() }
}

/// A multi-line editor that matches `HaloTextFieldStyle`.
struct HaloTextEditor: View {
    let text: Binding<String>
    var height: CGFloat = 76
    var label = "Text"

    var body: some View {
        TextEditor(text: text)
            .font(HaloType.control)
            .foregroundStyle(HaloColor.text)
            .scrollContentBackground(.hidden)
            .padding(5)
            .frame(height: height)
            .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                .fill(HaloColor.control))
            .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
                .strokeBorder(HaloColor.border, lineWidth: 1))
            .accessibilityLabel(label)
    }
}

/// A search field: magnifier, placeholder, clear button.
struct SearchField: View {
    let placeholder: String
    let text: Binding<String>
    var onSubmit: () -> Void = {}

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 12))
                .foregroundStyle(HaloColor.secondaryText)
                .accessibilityHidden(true)
            TextField(placeholder, text: text)
                .textFieldStyle(.plain)
                .font(HaloType.control)
                .foregroundStyle(HaloColor.text)
                .onSubmit(onSubmit)
                .accessibilityLabel(placeholder)
            if !text.wrappedValue.isEmpty {
                Button {
                    text.wrappedValue = ""
                    onSubmit()
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(HaloColor.secondaryText)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Clear search")
            }
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius).fill(HaloColor.control))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius)
            .strokeBorder(HaloColor.border, lineWidth: 1))
    }
}

// MARK: - Choice controls

/// One choice out of a few, shown as a row of buttons. The selected one has a
/// fill, an outline and bold text, so it is not signalled by color alone.
struct SegmentedChoice: View {
    let options: [(tag: String, label: String)]
    let selection: Binding<String>
    var accessibilityName = "Choice"

    var body: some View {
        HStack(spacing: 4) {
            ForEach(options, id: \.tag) { option in
                let on = selection.wrappedValue == option.tag
                Button {
                    selection.wrappedValue = option.tag
                } label: {
                    Text(option.label)
                        .font(HaloType.body(13, on ? .bold : .regular))
                        .foregroundStyle(on ? HaloColor.accentText : HaloColor.text)
                        .lineLimit(1)
                        .minimumScaleFactor(0.85)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 7)
                        .background(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius - 1)
                            .fill(on ? HaloColor.selection : HaloColor.control))
                        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.controlRadius - 1)
                            .strokeBorder(on ? HaloColor.accentText : HaloColor.subtleBorder,
                                          lineWidth: on ? 1.5 : 1))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(accessibilityName)
    }
}

/// A vertical list of radio choices, each with an optional explanation. The
/// chosen one is a filled ring, not just a different color.
struct RadioList: View {
    let options: [(tag: String, label: String, detail: String?)]
    let selection: Binding<String>
    var accessibilityName = "Choice"

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(options, id: \.tag) { option in
                let on = selection.wrappedValue == option.tag
                Button {
                    selection.wrappedValue = option.tag
                } label: {
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: on ? "largecircle.fill.circle" : "circle")
                            .font(.system(size: 14))
                            .foregroundStyle(on ? HaloColor.accentText : HaloColor.secondaryText)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(option.label)
                                .font(HaloType.body(13, on ? .semibold : .regular))
                                .foregroundStyle(HaloColor.text)
                            if let d = option.detail {
                                Text(d).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        Spacer(minLength: 0)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(accessibilityName)
    }
}

/// A checkbox whose on state is a checked square rather than a tinted one.
struct HaloCheckboxStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button {
            configuration.isOn.toggle()
        } label: {
            HStack(spacing: 7) {
                Image(systemName: configuration.isOn ? "checkmark.square.fill" : "square")
                    .font(.system(size: 14))
                    .foregroundStyle(configuration.isOn ? HaloColor.accentText : HaloColor.secondaryText)
                    .accessibilityHidden(true)
                configuration.label
                    .font(HaloType.control)
                    .foregroundStyle(HaloColor.text)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(.isToggle)
        .accessibilityValue(configuration.isOn ? "On" : "Off")
    }
}

extension ToggleStyle where Self == HaloCheckboxStyle {
    static var haloCheckbox: HaloCheckboxStyle { HaloCheckboxStyle() }
}

// MARK: - Rows

/// A setting whose label may be long: the label wraps in the space the control
/// leaves it, so a switch or picker always stays on the right.
struct DetailRow<Control: View>: View {
    let title: String
    var detail: String? = nil
    @ViewBuilder var control: Control

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(HaloType.control).foregroundStyle(HaloColor.text)
                    .fixedSize(horizontal: false, vertical: true)
                if let detail {
                    Text(detail).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 8)
            control.fixedSize().layoutPriority(1)
        }
    }
}

/// A setting that is an on/off switch: title, optional detail, switch on the
/// right. The title stays the accessibility label.
struct ToggleRow: View {
    let title: String
    var detail: String? = nil
    let isOn: Binding<Bool>
    var disabled = false

    var body: some View {
        DetailRow(title: title, detail: detail) {
            Toggle(title, isOn: isOn)
                .labelsHidden()
                .toggleStyle(.switch)
                .tint(HaloColor.imperial)
        }
        .disabled(disabled)
        .opacity(disabled ? 0.6 : 1)
    }
}

/// A slider with its current value spelled out on the right.
struct SliderRow: View {
    let title: String
    let value: Binding<Double>
    let range: ClosedRange<Double>
    let display: String

    var body: some View {
        SettingRow(title: title) {
            HStack(spacing: 10) {
                Slider(value: value, in: range)
                    .tint(HaloColor.imperial)
                    .frame(width: 180)
                    .accessibilityLabel(title)
                Text(display)
                    .font(HaloType.mono(12))
                    .foregroundStyle(HaloColor.secondaryText)
                    .frame(width: 52, alignment: .trailing)
            }
        }
    }
}

/// A hairline between rows inside a card.
struct RowDivider: View {
    var body: some View {
        Rectangle().fill(HaloColor.subtleBorder).frame(height: 1)
            .accessibilityHidden(true)
    }
}

/// A row of small print under a control, in secondary text.
struct Support: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(HaloType.support)
            .foregroundStyle(HaloColor.secondaryText)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// A small label above a group of fields.
struct FieldLabel: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text).font(HaloType.body(12, .semibold)).foregroundStyle(HaloColor.text)
    }
}

// MARK: - Page header

/// The pane title, with an optional trailing status (e.g. a readiness chip).
struct PaneHeader<Trailing: View>: View {
    let title: String
    let subtitle: String
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            PaneTitle(title: title, subtitle: subtitle)
            Spacer(minLength: 0)
            trailing.padding(.top, 6)
        }
    }
}

extension PaneHeader where Trailing == EmptyView {
    init(title: String, subtitle: String) {
        self.init(title: title, subtitle: subtitle) { EmptyView() }
    }
}

// MARK: - Empty states

/// Nothing here yet: what this is for, and one way to start.
struct EmptyState<Action: View>: View {
    let symbol: String
    let title: String
    let message: String
    @ViewBuilder var action: Action

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: symbol)
                .font(.system(size: 26, weight: .light))
                .foregroundStyle(HaloColor.secondaryText)
                .accessibilityHidden(true)
            Text(title).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
            Text(message)
                .font(HaloType.support)
                .foregroundStyle(HaloColor.secondaryText)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 380)
            action
        }
        .padding(.vertical, 22)
        .padding(.horizontal, 16)
        .frame(maxWidth: .infinity)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.cardRadius)
            .strokeBorder(HaloColor.subtleBorder, style: StrokeStyle(lineWidth: 1, dash: [4, 4])))
        .accessibilityElement(children: .contain)
    }
}

extension EmptyState where Action == EmptyView {
    init(symbol: String, title: String, message: String) {
        self.init(symbol: symbol, title: title, message: message) { EmptyView() }
    }
}

// MARK: - Disclosure

/// A card whose body opens and closes. The header is a real button, so it is
/// reachable from the keyboard and announced as expanded or collapsed.
struct DisclosureCard<Content: View>: View {
    let title: String
    var summary: String? = nil
    let isOpen: Binding<Bool>
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                isOpen.wrappedValue.toggle()
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: isOpen.wrappedValue ? "chevron.down" : "chevron.right")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(HaloColor.secondaryText)
                        .frame(width: 14)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(title).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
                        if let summary {
                            Text(summary).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityValue(isOpen.wrappedValue ? "Expanded" : "Collapsed")
            .accessibilityHint(isOpen.wrappedValue ? "Hides these options" : "Shows these options")

            if isOpen.wrappedValue {
                content
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: HaloMetrics.cardRadius).fill(HaloColor.surface))
        .overlay(RoundedRectangle(cornerRadius: HaloMetrics.cardRadius)
            .strokeBorder(HaloColor.subtleBorder, lineWidth: 1))
        .padding(.bottom, 14)
    }
}

// MARK: - Permission row

/// A system-derived permission: status chip, why it matters, one next action.
struct PermissionRow<Action: View>: View {
    let title: String
    let why: String
    let status: HaloStatus
    let statusText: String
    @ViewBuilder var action: Action

    var body: some View {
        HaloCard(padding: 14) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .center, spacing: 12) {
                    labels
                    Spacer(minLength: 8)
                    StateLabel(status: status, text: statusText)
                    action
                }
                VStack(alignment: .leading, spacing: 8) {
                    labels
                    HStack(spacing: 10) {
                        StateLabel(status: status, text: statusText)
                        action
                    }
                }
            }
        }
        .padding(.bottom, 10)
    }

    private var labels: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title).font(HaloType.controlStrong).foregroundStyle(HaloColor.text)
            Text(why).font(HaloType.support).foregroundStyle(HaloColor.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// An informational line (not a success, not a problem): info symbol + words.
struct InfoNote: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Label {
            Text(text).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: HaloStatus.info.symbol).foregroundStyle(HaloColor.secondaryText)
        }
        .font(HaloType.support)
        .foregroundStyle(HaloColor.secondaryText)
    }
}
