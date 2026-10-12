"""Regression (v0.6.4 → v0.7.0): opening the settings dialog threw
"ReferenceError: count is not defined" – the backup hint used the shorthand
{count} after the per-TV refactoring removed the local variable."""
import re
import unittest
from pathlib import Path

JS = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text(encoding='utf-8')


class SettingsDialogTests(unittest.TestCase):
    def source(self):
        return JS[JS.index('class SettingsDialog{'):JS.index('class BackupHistoryDialog{')]

    def test_backup_hint_uses_server_count(self):
        self.assertIn("t('settings.backups_hint',{count:current.backups.count,", self.source())

    def test_no_shorthand_count_without_local_variable(self):
        source = self.source()
        if re.search(r'\{count[,}]', source):
            self.assertRegex(source, r'\b(?:const|let|var)\s+(?:[^;]*[,\s])?count\b')


if __name__ == '__main__':
    unittest.main()
