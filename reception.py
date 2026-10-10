"""Reception mode (LG chan_mode_name) as a stable code and a localized label.

LG keeps a separate channel list and number namespace per reception mode, e.g.
programme 60 can exist once for Satellite and once for Cable at the same time.
"""
from i18n import Message


class ReceptionMode:
    CODES = ('satellite', 'cable', 'terrestrial', 'other')
    _ALIASES = {'satellite': 'satellite', 'cable': 'cable',
                'terrestrial': 'terrestrial', 'antenna': 'terrestrial'}

    @classmethod
    def code(cls, mode_name):
        return cls._ALIASES.get(str(mode_name or '').strip().lower(), 'other')

    @classmethod
    def label(cls, mode_name):
        return Message('reception.' + cls.code(mode_name))

    @classmethod
    def order(cls, mode_name):
        return cls.CODES.index(cls.code(mode_name))
