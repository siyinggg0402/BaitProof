"""Why an input (a screenshot, a voice note) could not be turned into text. `code` is stable and meant for programs; `message` is an English
sentence that is a key in the translation dictionaries (core/lang/i18n_inputs.py), so show it with core.lang.i18n.tr(message, lang)."""
from __future__ import annotations

CODES = ("too_big", "bad_type", "unreadable", "no_text", "unavailable", "too_long")


class InputError(Exception):
    def __init__(self, code: str, message: str) -> None:
        assert code in CODES, code
        super().__init__(message)
        self.code, self.message = code, message
