"""
CLI Theme — Colors, styles, and branding constants for the interactive app.
"""

from rich.theme import Theme

# Color palette
ACCENT = "#51A084"       # Lochinvar green
PRIMARY = "#090E18"      # Bunker dark
MUTED = "#656F84"        # Blue Bayoux
LIGHT = "#DAE0E7"        # Zircon
BG = "#F9FAFB"           # Alabaster

# Rich theme
APP_THEME = Theme({
    "accent": f"bold {ACCENT}",
    "info": ACCENT,
    "muted": MUTED,
    "warning": "bold yellow",
    "error": "bold red",
    "success": "bold green",
    "heading": f"bold {ACCENT}",
    "dim": "dim",
    "highlight": f"bold white on {ACCENT}",
})

# Questionary styling
QUESTIONARY_STYLE = [
    ("qmark", f"fg:{ACCENT} bold"),
    ("question", "bold"),
    ("answer", f"fg:{ACCENT} bold"),
    ("pointer", f"fg:{ACCENT} bold"),
    ("highlighted", f"fg:{ACCENT} bold"),
    ("selected", f"fg:{ACCENT}"),
    ("instruction", "fg:#656F84"),
]

APP_VERSION = "0.5.2"
APP_NAME = "Investment Memo Orchestrator"
