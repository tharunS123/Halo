// Halo addition -- NOT part of upstream ThinkingOrbsKit.
//
// Upstream keeps mode options internal, so a host app cannot bend a preset.
// Dictation drives the `composing` ribbon's `wobMul` (undulation depth) from
// the live mic level, which needs exactly one public entry point. Kept in its
// own file so the upstream files stay byte-identical and updating the vendored
// copy remains a straight directory copy (keep this file when you do).

import Foundation

/// Geometry for one instant, with per-frame overrides merged over the
/// resolved (state x size) preset. Keys are the engine's option names, e.g.
/// `["wobMul": 2]` for a deeper ribbon undulation.
public func orbFrame(
    state: OrbState,
    size: OrbSize,
    t: Double,
    overrides: [String: Double]
) -> OrbFrame {
    let base = resolvePreset(state, size)
    guard !overrides.isEmpty else {
        return orbFrame(base, size: size.value, t: t)
    }
    var opts = base.opts
    for (k, v) in overrides { opts[k] = v }
    let tuned = ResolvedPreset(mode: base.mode, speed: base.speed, opts: opts)
    return orbFrame(tuned, size: size.value, t: t)
}
