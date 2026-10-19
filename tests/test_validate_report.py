"""Regression checks for reports that must stand alone on paper."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from validate_report import ReportValidator, verdict_presentation_errors

FIXTURE = Path(__file__).parent / 'fixtures/valid_report.md'


class PaperReportTests(unittest.TestCase):
    def validator(self, content):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        report = Path(temp.name) / 'report.md'
        report.write_text(content, encoding='utf-8')
        return ReportValidator(report)

    def test_complete_fixture_passes_cli(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / 'validate_report.py'),
                                 '--report', str(FIXTURE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_hidden_link_destinations_are_not_printable_urls(self):
        content = FIXTURE.read_text().replace('URL: <https://example.com/paper1>', '')
        validator = self.validator(content)
        self.assertFalse(validator._check_bibliography())
        self.assertIn('display the full URL', ' '.join(validator.errors))

    def test_visible_url_must_match_destination_including_query_and_fragment(self):
        content = FIXTURE.read_text().replace('paper1>', 'paper1?version=2&lang=en#results>', 1)
        validator = self.validator(content)
        self.assertFalse(validator._check_bibliography())
        self.assertIn('display the full URL', ' '.join(validator.errors))

    def test_soft_newlines_cannot_merge_source_paragraphs(self):
        content = FIXTURE.read_text().replace('\n\n[2]', '\n[2]')
        validator = self.validator(content)
        self.assertFalse(validator._check_bibliography())
        self.assertIn('blank line', ' '.join(validator.errors))

    def test_multiple_sources_on_one_entry_line_fail(self):
        content = FIXTURE.read_text().replace('\n\n[2]', ' [2]')
        validator = self.validator(content)
        self.assertFalse(validator._check_bibliography())
        self.assertIn('one source per entry line', ' '.join(validator.errors))

    def test_reference_only_verdicts_fail(self):
        for value in (
                'Verdict: see qa/fact_check_result.json',
                '**Verdict:** See `qa/fact_check_result.json` for the final decision.',
                'Verdict:\n\nRefer to qa/fact_check_result.json',
                '## Verdict\n\nSee qa/fact_check_result.json',
                'Verification status: [See the audit](qa/fact_check_result.json)',
                'Verdict: `qa/fact_check_result.json`',
                '| Claim | Verifier verdict |\n|---|---|\n| Enrollment | See qa/fact_check_result.json |',
                '| Claim | Verdict |\n|---|---|\n| Enrollment | |'):
            with self.subTest(value=value):
                self.assertTrue(verdict_presentation_errors(value))

    def test_self_contained_outcomes_allow_supplementary_audit_references(self):
        for value in (
                '**Verdict:** Supported within the trial population; long-term outcomes remain uncertain. See qa/fact_check_result.json.',
                'Verdict: Inconclusive because follow-up was incomplete.',
                '## Verdict\n\nBlocked because the independent review is incomplete.',
                '| Claim | Verifier verdict | Red-team verdict |\n|---|---|---|\n| Enrollment | Approved: count matches the registry. | Approved: no conflicting enrollment record found. |'):
            with self.subTest(value=value):
                self.assertEqual(verdict_presentation_errors(value), [])

    def test_file_only_verdict_causes_nonzero_cli_exit(self):
        validator = self.validator(FIXTURE.read_text() + '\nVerdict: see qa/fact_check_result.json\n')
        result = subprocess.run([sys.executable, str(SCRIPTS / 'validate_report.py'),
                                 '--report', str(validator.report_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('verdict must state the outcome', result.stdout)
