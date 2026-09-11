"""Runtime UI preferences from the menu's Settings screen, saved in
config.json: the TEXT scale (panels, hints, messages, wave timer, help, the
menu) and the BUTTON scale (the toolbar and the Android on-screen buttons,
labels included). World numbers (belt items, deposits) never scale with
these. main.py / android entry call apply() at startup; the menu calls it
again when a value changes, so the HUD picks it up on the next frame.
"""

TEXT_SCALES = (0.8, 1.0, 1.2, 1.5, 1.8)      # "Text size" steps
BUTTON_SCALES = (0.8, 1.0, 1.25, 1.5, 2.0)   # "Button size" steps

text_scale = 1.0
button_scale = 1.0


def apply(config):
    """Read the scales out of a config dict (bad values fall back to 1.0,
    out-of-range ones are clamped to the tables)."""
    global text_scale, button_scale
    text_scale = _clamp(config.get("text_scale", 1.0), TEXT_SCALES)
    button_scale = _clamp(config.get("button_scale", 1.0), BUTTON_SCALES)


def _clamp(value, steps):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 1.0
    return min(steps[-1], max(steps[0], v))


def step(value, steps, direction):
    """The next (+1) or previous (-1) entry of a scale table, wrapping."""
    idx = min(range(len(steps)), key=lambda i: abs(steps[i] - value))
    return steps[(idx + direction) % len(steps)]


def percent(value):
    return f"{int(round(value * 100))}%"


def tpx(v):
    """Layout pixels scaled by the text size."""
    return int(round(v * text_scale))


def tsize(size):
    """A font size scaled by the text size (never below 6 px)."""
    return max(6, int(round(size * text_scale)))
