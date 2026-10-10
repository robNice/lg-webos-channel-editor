"""Localization: one folder per language under ``locales/`` (``<lang>/messages.json``).

Adding a folder adds a language. Missing keys fall back to the default
language (English); unknown keys render as the key itself.
"""
import json
import re
import string
import threading
from pathlib import Path

LOCALES = Path(__file__).resolve().parent / 'locales'
DEFAULT_LANGUAGE = 'en'


class Message:
    """Translatable text: a key plus named parameters, rendered per request language."""
    __slots__ = ('key', 'params')

    def __init__(self, key, **params):
        self.key = key
        self.params = params

    def _identity(self):
        return self.key, tuple(sorted((k, repr(v)) for k, v in self.params.items()))

    def __eq__(self, other):
        return isinstance(other, Message) and self._identity() == other._identity()

    def __hash__(self):
        return hash(self._identity())

    def __repr__(self):
        return f'Message({self.key!r}, {self.params!r})'

    def __str__(self):
        return I18N.render(self, I18N.default)


class LocalizedError(ValueError):
    """A ValueError whose text is resolved in the language of the request."""

    def __init__(self, key, **params):
        self.message = Message(key, **params)
        super().__init__(key)

    def __str__(self):
        return str(self.message)


class Joined:
    """Several texts joined by a separator, each rendered in the target language."""
    __slots__ = ('separator', 'parts')

    def __init__(self, separator, parts):
        self.separator = separator
        self.parts = list(parts)

    def __repr__(self):
        return f'Joined({self.separator!r}, {self.parts!r})'

    def __str__(self):
        return I18N.render(self, I18N.default)


class _SafeParams(dict):
    def __missing__(self, key):
        return '{' + key + '}'


class Localization:
    def __init__(self, root=LOCALES, default=DEFAULT_LANGUAGE):
        self.root = Path(root)
        self.default = default
        self._cache = {}
        self._lock = threading.Lock()

    def languages(self):
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and re.fullmatch(r'[a-z]{2,3}', p.name) and (p / 'messages.json').is_file())

    def messages(self, lang):
        with self._lock:
            if lang not in self._cache:
                path = self.root / lang / 'messages.json'
                self._cache[lang] = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
            return self._cache[lang]

    def catalog(self, lang):
        """All keys for ``lang``, completed from the default language."""
        return {**self.messages(self.default), **self.messages(lang)}

    def negotiate(self, header):
        """Pick the best available language from an HTTP Accept-Language header."""
        available = set(self.languages())
        ranked = []
        for position, part in enumerate(str(header or '').split(',')):
            fields = [f.strip() for f in part.split(';')]
            tag = fields[0].lower()
            quality = 1.0
            for field in fields[1:]:
                if field.startswith('q='):
                    try:
                        quality = float(field[2:])
                    except ValueError:
                        quality = 0.0
            if tag and quality > 0:
                ranked.append((-quality, position, tag.split('-')[0]))
        for _, _, primary in sorted(ranked):
            if primary in available:
                return primary
        return self.default

    def negotiate_posix(self, value):
        """Language from a POSIX locale such as ``de_DE.UTF-8`` (for console output)."""
        return self.negotiate(re.split(r'[_.@]', str(value or ''))[0])

    def _template(self, lang, key):
        return self.messages(lang).get(key) or self.messages(self.default).get(key)

    def translate(self, lang, key, **params):
        template = self._template(lang, key)
        if template is None:
            return key
        rendered = {name: self.render(value, lang) for name, value in params.items()}
        return string.Formatter().vformat(template, (), _SafeParams(rendered))

    def render(self, value, lang):
        if isinstance(value, Message):
            return self.translate(lang, value.key, **value.params)
        if isinstance(value, LocalizedError):
            return self.render(value.message, lang)
        if isinstance(value, Joined):
            return value.separator.join(self.render(part, lang) for part in value.parts)
        return str(value)

    def localize(self, data, lang):
        """Replace every Message/LocalizedError in a JSON-like structure by its text."""
        if isinstance(data, (Message, LocalizedError, Joined)):
            return self.render(data, lang)
        if isinstance(data, dict):
            return {k: self.localize(v, lang) for k, v in data.items()}
        if isinstance(data, (list, tuple)):
            return [self.localize(v, lang) for v in data]
        return data


I18N = Localization()
