"""Global input limits for NEW LG programme-number assignments.

The LG on-screen number editor displays 1–99 even for services whose existing
channel numbers are >99. The TV's Luna API can sometimes accept higher values,
but the editor intentionally follows the explicit UI limit for ALL new edits.
Existing imported programme numbers above 99 must remain untouched unless
explicitly renumbered into the allowed range.
"""

from i18n import LocalizedError, Message

MIN_CHANNEL_NUMBER = 1
MAX_CHANNEL_NUMBER = 99


def number_policy(channel_id=None, mode=None, original_number=None,
                  satellite_lcn=None, signal_id=None):
    """A uniform UI policy; parameters retained for API compatibility."""
    return {'kind': 'confirmed', 'min': MIN_CHANNEL_NUMBER,
            'max': MAX_CHANNEL_NUMBER,
            'message': Message('number.policy')}


def enforce_number_policy(policy, new_number):
    """Strictly validate each new target; old values above 99 are unaffected."""
    if type(new_number) is not int or not MIN_CHANNEL_NUMBER <= new_number <= MAX_CHANNEL_NUMBER:
        raise LocalizedError('error.number.out_of_range')


def number_warning(policy, new_number):
    """No more per-station advisories: the hard bound applies to all edits."""
    return None
