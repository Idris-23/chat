
import tkinter as tk

FONT = "Segoe UI"

PALETTES = {
    "dark": dict(
        BG="#0f172a",            # window background
        CARD="#1e293b",          # cards, header, input bar
        INPUT="#334155",         # input boxes
        TEXT="#f1f5f9",          # main text
        MUTED="#94a3b8",         # small grey text
        ACCENT="#6366f1",        # main buttons
        ACCENT_HOVER="#818cf8",  # main buttons on mouse-over / links
        GREEN="#34d399",         # the AI's name in the chat
        SIDEBAR="#0b1220",       # chat list panel
        BTN2="#334155",          # secondary buttons
        BTN2_HOVER="#475569",
        BTN2_FG="#f1f5f9",
        ERROR="#f87171",
    ),
    "light": dict(
        BG="#f1f5f9",
        CARD="#ffffff",
        INPUT="#e2e8f0",
        TEXT="#0f172a",
        MUTED="#64748b",
        ACCENT="#6366f1",
        ACCENT_HOVER="#4f46e5",
        GREEN="#059669",
        SIDEBAR="#e8edf3",
        BTN2="#e2e8f0",
        BTN2_HOVER="#cbd5e1",
        BTN2_FG="#0f172a",
        ERROR="#dc2626",
    ),
}


class _Theme:
    def __init__(self):
        self.mode = "dark"
        self.set_mode("dark")

    def set_mode(self, mode):
        if mode not in PALETTES:
            mode = "dark"
        self.mode = mode
        for name, value in PALETTES[mode].items():
            setattr(self, name, value)

    def toggle(self):
        self.set_mode("light" if self.mode == "dark" else "dark")


T = _Theme()  # the one shared theme object


# ---------------------------------------------------------------- helpers
def make_button(parent, text, command, primary=True, size=11, padx=0, pady=10):
    """A button made from a Label (labels keep their colors on every OS)."""
    bg = T.ACCENT if primary else T.BTN2
    fg = "white" if primary else T.BTN2_FG
    hover = T.ACCENT_HOVER if primary else T.BTN2_HOVER
    btn = tk.Label(parent, text=text, font=(FONT, size, "bold"), bg=bg, fg=fg,
                   cursor="hand2", padx=padx, pady=pady)
    btn.bind("<Button-1>", lambda e: command())
    btn.bind("<Enter>", lambda e: btn.config(bg=hover))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn


def make_field(parent, label, show=None, width=32, gap=12):
    """A label + input box stacked inside a card. Returns the Entry."""
    tk.Label(parent, text=label, font=(FONT, 10), bg=T.CARD,
             fg=T.MUTED).pack(anchor="w", pady=(0, 4))
    entry = tk.Entry(
        parent, width=width, font=(FONT, 11), bg=T.INPUT, fg=T.TEXT,
        insertbackground=T.TEXT, relief="flat", show=show,
        highlightthickness=2, highlightbackground=T.INPUT,
        highlightcolor=T.ACCENT,  # border turns purple when you click inside
    )
    entry.pack(ipady=8, pady=(0, gap))
    return entry


def theme_toggle(parent, command, bg):
    """The small  ☀ Light mode / 🌙 Dark mode  switch."""
    text = "☀️  Light mode" if T.mode == "dark" else "🌙  Dark mode"
    label = tk.Label(parent, text=text, font=(FONT, 9, "bold"), bg=bg,
                     fg=T.MUTED, cursor="hand2")
    label.bind("<Button-1>", lambda e: command())
    label.bind("<Enter>", lambda e: label.config(fg=T.TEXT))
    label.bind("<Leave>", lambda e: label.config(fg=T.MUTED))
    return label