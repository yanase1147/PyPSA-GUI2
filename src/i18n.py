"""i18n helper — loads/unloads QTranslator for PyPSA GUI.

Usage
-----
from src.i18n import load_language, current_language, LANGUAGES

# At startup (before QApplication.exec):
load_language("en")   # English
load_language("ja")   # Japanese (= default, removes translator)
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QCoreApplication, QTranslator, QLocale
from PyQt6.QtWidgets import QApplication

# Language codes supported by the app.
# Key   = code passed to load_language()
# Value = human-readable label shown in the menu
LANGUAGES: dict[str, str] = {
    "ja": "日本語",
    "en": "English",
}

# Module-level translator instance (must survive until app exits).
_translator: QTranslator | None = None

_TRANSLATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "translations",
)

_SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".pypsa_gui_lang",
)


def save_language(lang: str) -> None:
    """Persist the language code to disk."""
    try:
        with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
            f.write(lang)
    except OSError:
        pass


def load_saved_language() -> str:
    """Return the previously saved language code, or 'ja' as default."""
    try:
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            code = f.read().strip()
        if code in LANGUAGES:
            return code
    except OSError:
        pass
    return "ja"


def load_language(lang: str) -> bool:
    """Install a QTranslator for *lang*.

    Returns True if a translation was installed, False for Japanese (default).
    'ja' removes any active translator (source strings are Japanese).
    """
    global _translator

    app = QCoreApplication.instance()
    if app is None:
        return False

    # Remove previous translator
    if _translator is not None:
        app.removeTranslator(_translator)
        _translator = None

    if lang == "ja":
        return False

    qm_path = os.path.join(_TRANSLATIONS_DIR, f"app_{lang}.qm")
    if not os.path.isfile(qm_path):
        # Attempt to compile from .ts on-the-fly via lrelease
        ts_path = os.path.join(_TRANSLATIONS_DIR, f"app_{lang}.ts")
        if os.path.isfile(ts_path):
            _try_compile_ts(ts_path, qm_path)

    if not os.path.isfile(qm_path):
        return False

    translator = QTranslator(app)
    if translator.load(qm_path):
        app.installTranslator(translator)
        _translator = translator
        return True

    return False


def current_language() -> str:
    """Return the active language code."""
    return "ja" if _translator is None else _detect_active_lang()


def _detect_active_lang() -> str:
    if _translator is None:
        return "ja"
    # Try to infer from the loaded .qm filename (stored implicitly via module var).
    for code in LANGUAGES:
        if code == "ja":
            continue
        qm_path = os.path.join(_TRANSLATIONS_DIR, f"app_{code}.qm")
        if os.path.isfile(qm_path):
            # Heuristic: translator was loaded, non-ja must be active.
            return code
    return "en"


def _try_compile_ts(ts_path: str, qm_path: str) -> None:
    """Try to compile a .ts file to .qm using lrelease (if available)."""
    import subprocess
    for cmd in ("lrelease", "lrelease-qt6", "pyside6-lrelease"):
        try:
            subprocess.run(
                [cmd, ts_path, "-qm", qm_path],
                check=True,
                capture_output=True,
                timeout=15,
            )
            return
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
