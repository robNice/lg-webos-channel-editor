"""Localization: one folder per language under ``locales/`` (``<lang>/messages.json``).

Adding a folder adds a language; a regional variant is ``<lang>-<REGION>``
(e.g. ``pt-BR``) and falls back to its language, then to the default language
(English); unknown keys render as the key itself. Messages use a subset of
ICU MessageFormat: ``{name}`` and ``{count, plural, one {# channel} other {#
channels}}`` (``=0`` exact matches, ``#`` = the number). ``language.dir``
(ltr/rtl) is the writing direction, ``language.intl`` the locale for the
plural rules if it differs from the folder name (``pt`` = European: pt-PT).
"""
import json
import re
import threading
from http.cookies import CookieError, SimpleCookie
from pathlib import Path

LOCALES = Path(__file__).resolve().parent / 'locales'
DEFAULT_LANGUAGE = 'en'
# Language chosen in the header (static/app.js LanguageChoice); wins over Accept-Language.
LANGUAGE_COOKIE = 'lang'
# Accept-Language tags without a folder of their own.
LANGUAGE_ALIASES = {'no': 'nb', 'nn': 'nb'}
LANGUAGE_FOLDER = re.compile(r'[a-z]{2,3}(?:-[A-Z]{2})?')


class PluralRules:
    """CLDR cardinal plural categories for whole numbers (as Intl.PluralRules
    in the browser; tests/test_languages_080.py compares both)."""

    @staticmethod
    def _one(n):
        return 'one' if n == 1 else 'other'

    @staticmethod
    def _one_many(n):  # es, it, pt-PT: 1 000 000 is "many" (de un millón)
        return 'one' if n == 1 else 'many' if n and n % 1000000 == 0 else 'other'

    @staticmethod
    def _zero_one_many(n):  # fr, pt (Brazil): 0 and 1 are "one"
        return 'one' if n in (0, 1) else 'many' if n and n % 1000000 == 0 else 'other'

    @staticmethod
    def _slavic(n):  # ru, uk
        if n % 10 == 1 and n % 100 != 11:
            return 'one'
        return 'few' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'many'

    @staticmethod
    def _polish(n):
        if n == 1:
            return 'one'
        return 'few' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'many'

    @staticmethod
    def _arabic(n):
        if n in (0, 1, 2):
            return ('zero', 'one', 'two')[n]
        return 'few' if 3 <= n % 100 <= 10 else 'many' if 11 <= n % 100 <= 99 else 'other'

    @staticmethod
    def _icelandic(n):
        return 'one' if n % 10 == 1 and n % 100 != 11 else 'other'

    @staticmethod
    def _other(n):
        return 'other'

    RULES = {'en': _one, 'de': _one, 'el': _one, 'nl': _one, 'sv': _one, 'nb': _one, 'da': _one, 'fi': _one, 'tr': _one,
             'es': _one_many, 'it': _one_many, 'pt-PT': _one_many, 'fr': _zero_one_many, 'pt': _zero_one_many,
             'pl': _polish, 'ru': _slavic, 'uk': _slavic, 'ar': _arabic, 'is': _icelandic, 'ja': _other, 'ko': _other}

    @classmethod
    def select(cls, locale, n):
        rule = cls.RULES.get(locale) or cls.RULES.get(str(locale).split('-')[0]) or cls._one
        return rule(abs(int(n)))


class MessageFormat:
    """The ICU subset used by the locale files; the same parser exists in
    static/app.js (Translator). A template that does not parse is returned as
    plain text with its simple ``{name}`` placeholders filled in."""
    ARGUMENT = re.compile(r'\{\s*(\w+)\s*(?:(\})|,\s*plural\s*,)')
    OPTION = re.compile(r'\s*(=\d+|zero|one|two|few|many|other)\s*\{')
    _cache = {}

    @classmethod
    def parse(cls, text):
        if text not in cls._cache:
            nodes, end = cls._parse(text, 0, False)
            cls._cache[text] = nodes
        return cls._cache[text]

    @classmethod
    def _parse(cls, text, i, in_plural):
        nodes, buffer = [], []
        def flush():
            if buffer:
                nodes.append(''.join(buffer))
                buffer.clear()
        while i < len(text):
            char = text[i]
            if char == '{':
                match = cls.ARGUMENT.match(text, i)
                if not match:
                    raise ValueError(text)
                flush()
                if match.group(2):
                    nodes.append(('arg', match.group(1)))
                    i = match.end()
                    continue
                i, options = match.end(), {}
                while True:
                    while i < len(text) and text[i].isspace():
                        i += 1
                    if i < len(text) and text[i] == '}':
                        i += 1
                        break
                    option = cls.OPTION.match(text, i)
                    if not option:
                        raise ValueError(text)
                    options[option.group(1)], i = cls._parse(text, option.end(), True)
                if 'other' not in options:
                    raise ValueError(text)
                nodes.append(('plural', match.group(1), options))
            elif char == '}':
                if not in_plural:
                    raise ValueError(text)
                flush()
                return nodes, i + 1
            elif char == '#' and in_plural:
                flush()
                nodes.append(('hash',))
                i += 1
            else:
                buffer.append(char)
                i += 1
        if in_plural:
            raise ValueError(text)
        flush()
        return nodes, i

    @classmethod
    def valid(cls, text):
        try:
            cls.parse(text)
            return True
        except ValueError:
            return False

    @staticmethod
    def number(value):
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        return int(value) if isinstance(value, str) and re.fullmatch(r'-?\d+', value.strip()) else None

    @classmethod
    def format(cls, text, params, plural, render=str):
        """``plural(n)`` -> category; ``render(value)`` -> text of a parameter."""
        try:
            nodes = cls.parse(text)
        except ValueError:
            return re.sub(r'\{(\w+)\}', lambda m: render(params[m.group(1)]) if m.group(1) in params else m.group(0), text)
        return cls._render(nodes, params, plural, render, None)

    @classmethod
    def _render(cls, nodes, params, plural, render, hash_value):
        out = []
        for node in nodes:
            if isinstance(node, str):
                out.append(node)
            elif node[0] == 'arg':
                out.append(render(params[node[1]]) if node[1] in params else '{' + node[1] + '}')
            elif node[0] == 'hash':
                out.append(hash_value)
            else:
                _, name, options = node
                value = params.get(name)
                n = cls.number(value)
                branch = options.get(f'={n}') if n is not None else None
                if branch is None:
                    branch = options.get(plural(n)) if n is not None else None
                if branch is None:
                    branch = options['other']
                shown = str(n) if n is not None else render(value) if name in params else '{' + name + '}'
                out.append(cls._render(branch, params, plural, render, shown))
        return ''.join(out)

    @classmethod
    def names(cls, text):
        try:
            return cls._names(cls.parse(text))
        except ValueError:
            return set(re.findall(r'\{(\w+)\}', text))

    @classmethod
    def _names(cls, nodes):
        found = set()
        for node in nodes:
            if isinstance(node, tuple) and node[0] in ('arg', 'plural'):
                found.add(node[1])
                if node[0] == 'plural':
                    for branch in node[2].values():
                        found |= cls._names(branch)
        return found

    @classmethod
    def plural_options(cls, text):
        """Option lists of every plural argument (empty if there is none)."""
        try:
            return cls._plural_options(cls.parse(text))
        except ValueError:
            return []

    @classmethod
    def _plural_options(cls, nodes):
        found = []
        for node in nodes:
            if isinstance(node, tuple) and node[0] == 'plural':
                found.append(list(node[2]))
                for branch in node[2].values():
                    found += cls._plural_options(branch)
        return found


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
                      if p.is_dir() and LANGUAGE_FOLDER.fullmatch(p.name) and (p / 'messages.json').is_file())

    def messages(self, lang):
        with self._lock:
            if lang not in self._cache:
                path = self.root / lang / 'messages.json'
                self._cache[lang] = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
            return self._cache[lang]

    @staticmethod
    def _chain(lang):
        """``pt-BR`` -> pt-BR, pt (the default language is added by the callers)."""
        primary = str(lang).split('-')[0]
        return [lang] if primary == lang else [lang, primary]

    def catalog(self, lang):
        """All keys for ``lang``, completed from its language and the default language."""
        catalog = dict(self.messages(self.default))
        for code in reversed(self._chain(lang)):
            catalog.update(self.messages(code))
        return catalog

    def intl(self, lang):
        """Locale for the plural rules (``language.intl``, else the folder name)."""
        return self.catalog(lang).get('language.intl') or lang

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
                ranked.append((-quality, position, tag))
        for _, _, tag in sorted(ranked):
            primary, _, region = tag.partition('-')
            for candidate in (f'{primary}-{region.upper()}' if region else None, primary, LANGUAGE_ALIASES.get(primary)):
                if candidate in available:
                    return candidate
        return self.default

    def direction(self, lang):
        """Writing direction of a language (``language.dir`` in its messages.json)."""
        return 'rtl' if self.catalog(lang).get('language.dir') == 'rtl' else 'ltr'

    def chosen(self, cookie_header):
        """Language the user chose (cookie), or None if none or not available."""
        cookies = SimpleCookie()
        try:
            cookies.load(str(cookie_header or ''))
        except CookieError:
            return None
        morsel = cookies.get(LANGUAGE_COOKIE)
        return morsel.value if morsel is not None and morsel.value in self.languages() else None

    def choose(self, cookie_header, accept_language):
        """The user's choice first, otherwise the browser's Accept-Language."""
        return self.chosen(cookie_header) or self.negotiate(accept_language)

    def negotiate_posix(self, value):
        """Language from a POSIX locale such as ``de_DE.UTF-8`` (for console output)."""
        return self.negotiate(re.split(r'[_.@]', str(value or ''))[0])

    def _template(self, lang, key):
        for code in self._chain(lang) + [self.default]:
            text = self.messages(code).get(key)
            if text:
                return text
        return None

    def translate(self, lang, key, **params):
        template = self._template(lang, key)
        if template is None:
            return key
        locale = self.intl(lang)
        return MessageFormat.format(template, params, lambda n: PluralRules.select(locale, n),
                                    lambda value: self.render(value, lang))

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
