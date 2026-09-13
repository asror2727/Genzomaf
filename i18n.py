import json
import os

_LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")
_CACHE: dict[str, dict] = {}

SUPPORTED_LANGS = {
    "uz": "🇺🇿 O'zbekcha",
    "en": "🇬🇧 English",
    "ru": "🇷🇺 Русский",
    "uk": "🇺🇦 Українська",
    "kk": "🇰🇿 Қазақша",
    "tr": "🇹🇷 Türkçe",
}


def _load(lang: str) -> dict:
    if lang not in _CACHE:
        path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        if not os.path.exists(path):
            path = os.path.join(_LOCALES_DIR, "uz.json")
        with open(path, encoding="utf-8") as f:
            _CACHE[lang] = json.load(f)
    return _CACHE[lang]


def t(lang: str, key: str, **kwargs) -> str:
    data = _load(lang)
    text = data.get(key) or _load("uz").get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
