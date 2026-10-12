"""Fill a favorite list from channel IDs (v0.7.0).

Used by "paste list" (IDs copied from another list of the working copy) and
"import into list" (IDs of one list of a file, already matched onto the
working copy by ``RestorePlanner``). Only membership and order of the target
list change; numbers and the other lists stay untouched.
"""
from i18n import LocalizedError


class ListFill:
    """Computes the new member order of a target list.

    ``replace``: the target becomes exactly the incoming channels in their
    order. ``append``: the target keeps its members and order; incoming
    channels it does not hold yet are added at the end. Incoming IDs unknown
    in the working copy (e.g. deleted since copying) are skipped and counted.
    """
    MODES = ('replace', 'append')

    def __init__(self, known_ids, target_ids):
        self.known = set(known_ids)
        self.target = list(target_ids)

    def plan(self, ids, mode):
        if mode not in self.MODES:
            raise LocalizedError('error.list.mode_invalid')
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise LocalizedError('error.list.ids_invalid')
        incoming = list(dict.fromkeys(i for i in ids if i in self.known))
        skipped = len(set(ids) - self.known)
        target = set(self.target)
        if mode == 'replace':
            result = incoming
        else:
            result = self.target + [i for i in incoming if i not in target]
        return {'ids': result,
                'added': sum(i not in target for i in result),
                'removed': sum(i not in set(result) for i in self.target),
                'present': sum(i in target for i in incoming),
                'skipped': skipped}
