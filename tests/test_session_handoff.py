"""Exercise the actual acquisition boundary and fresh-process continuation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from search_fixtures import search_record

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent


class SessionHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / 'original run'
        self.cli('citation_manager.py', 'init-run', '--out-dir', str(self.run),
                 '--query', 'What do the records show?', '--mode', 'deep')
        self.manifest_path = self.run / 'run_manifest.json'
        manifest = self.manifest()
        manifest.update(
            research_contract={'use_case': 'Inform a decision', 'audience': 'Technical',
                               'scope': 'EU, 2020–2026; exclude forecasts',
                               'constraints': 'Free primary sources; Markdown report',
                               'definition_of_done': 'Answer with reviewed evidence and disclose gaps'},
            hypotheses=[{'id': 'H1', 'statement': 'The records show an increase'},
                        {'id': 'H2', 'statement': 'The increase is confined to one region'}],
            phases_completed=['scope', 'acquire'])
        self.write_manifest(manifest)
        self.acq = self.run / 'acquisition'
        (self.acq / 'query_plan.md').write_text(
            'Stop: acquisition budget reached. Known gap: historic regional records.\n'
            '```json\n{"angles":[{"name":"official-records"}],"budgets":{"searches":1}}\n```\n')
        url = 'https://example.org/records'
        self.sid = hashlib.sha256(url.encode()).hexdigest()[:16]
        (self.acq / 'raw/source.md').write_text(
            f'---\nsource_id: {self.sid}\ntitle: Official records\n---\nRecorded value: 42.\n')
        original = b'<p>Recorded value: 42.</p>'
        (self.acq / 'original/source.html').write_bytes(original)
        record = {'source_id': self.sid, 'requested_url': url, 'final_url': url,
                  'tool': 'web_extract', 'execution_ref': 'synthetic-fixture:call-1',
                  'content_file': 'original/source.html', 'extraction_method': 'fixture-v1',
                  'retrieved_at': '2026-10-19T00:00:00Z', 'kind': 'tool_response',
                  'http_status': None, 'content_sha256': hashlib.sha256(original).hexdigest()}
        (self.acq / 'retrieval/source.json').write_text(json.dumps(record))
        agent = self.acq / 'agents'
        source = {'raw_url': url, 'title': 'Official records', 'origin': 'primary',
                  'medium': 'government', 'search_angle': 'official-records',
                  'raw_file': 'raw/source.md', 'retrieval_record': 'retrieval/source.json'}
        (agent / 'a01.sources.jsonl').write_text(json.dumps(source) + '\n')
        (agent / 'a01.queries.jsonl').write_text(
            json.dumps(search_record(self.run)) + '\n')
        (self.acq / 'leads.jsonl').write_text('{"lead":"regional archive","why":"coverage gap"}\n')
        for command in ('merge-sources', 'merge-query-log', 'build-source-map'):
            self.cli('citation_manager.py', command, '--acq-dir', str(self.acq))

    def cli(self, script, *args, success=True):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *args],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def handoff(self, command, *args, success=True):
        return self.cli('session_handoff.py', command, '--run-dir', str(self.run),
                        *args, success=success)

    def manifest(self):
        return json.loads(self.manifest_path.read_text())

    def write_manifest(self, manifest):
        self.manifest_path.write_text(json.dumps(manifest))

    def test_both_session_choices_preserve_inputs_and_all_processing_work(self):
        self.handoff('prepare')
        original = self.manifest()
        self.assertEqual(original['processing_handoff']['status'], 'awaiting_user')
        prompt = (self.run / 'handoff/processing_prompt.md').read_text()
        self.assertIn(str(self.run), prompt)
        self.assertIn('reference/fact-checking.md', prompt)
        self.assertIn('--choice new-session', prompt)
        self.assertIn('phases 3–8', prompt)
        self.assertIn('independent verification and red-team', prompt)
        self.handoff('check')
        self.assertEqual(self.manifest(), original)  # A check neither consents nor advances.
        saved_files = {str(p.relative_to(self.acq)): p.read_bytes()
                       for p in self.acq.rglob('*') if p.is_file()}
        for choice in ('same-session', 'new-session'):
            with self.subTest(choice=choice):
                self.write_manifest(original)
                result = self.handoff('resume', '--choice', choice)
                self.assertEqual(result['next_phase'], 'triage')
                manifest = self.manifest()
                self.assertEqual(manifest['continuation']['session_choice'], choice)
                self.assertEqual(manifest['processing_handoff']['status'], 'processing')
                self.assertEqual(manifest['phases_completed'], ['scope', 'acquire'])
                self.assertIsNone(manifest['finished_at'])
                self.assertEqual(manifest['research_contract'], original['research_contract'])
                schema = json.loads((ROOT / 'schemas/run_manifest.schema.json').read_text())
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
                self.assertFalse((self.run / 'triage/corpus.jsonl').exists())
                self.assertFalse((self.run / 'report/report.md').exists())
                self.assertFalse((self.run / 'qa/fact_check_result.json').exists())
                self.assertEqual({str(p.relative_to(self.acq)): p.read_bytes()
                                  for p in self.acq.rglob('*') if p.is_file()}, saved_files)

    def test_missing_task_context_or_material_blocks_preparation(self):
        for relative in ('run_manifest.json', 'acquisition/raw/source.md',
                         'acquisition/original/source.html', 'acquisition/retrieval/source.json'):
            with self.subTest(relative=relative):
                path = self.run / relative
                content = path.read_bytes()
                if relative == 'run_manifest.json':
                    manifest = self.manifest()
                    manifest['research_contract'] = None
                    self.write_manifest(manifest)
                else:
                    path.unlink()
                self.assertEqual(self.handoff('prepare', success=False)['status'], 'blocked')
                self.assertFalse((self.run / 'handoff/acquisition.json').exists())
                path.write_bytes(content)

    def test_changed_inputs_block_resume_without_mutating_pending_state(self):
        self.handoff('prepare')
        before = self.manifest_path.read_bytes()
        for relative in ('acquisition/raw/source.md', 'acquisition/original/source.html',
                         'acquisition/leads.jsonl', 'acquisition/query_plan.md',
                         'handoff/processing_prompt.md', 'acquisition/original/q_test.txt'):
            with self.subTest(relative=relative):
                path = self.run / relative
                content = path.read_bytes()
                path.write_bytes(content + b'\n')
                self.handoff('resume', '--choice', 'new-session', success=False)
                self.assertEqual(self.manifest_path.read_bytes(), before)
                path.write_bytes(content)
        manifest = self.manifest()
        manifest['research_contract']['scope'] = 'Changed geography'
        self.write_manifest(manifest)
        self.handoff('check', success=False)

    def test_failed_control_blocks_handoff_before_any_processing(self):
        control = search_record(self.run, 'failed-control', outcome='inconclusive',
                                query_role='positive_control', expected_match='Known catalogue entry')
        negative = search_record(self.run, 'negative', outcome='no_results',
                                 control_query_id='failed-control')
        (self.acq / 'query_log.jsonl').write_text(
            ''.join(json.dumps(q) + '\n' for q in (control, negative)))
        self.cli('citation_manager.py', 'build-source-map', '--acq-dir', str(self.acq))
        before = self.manifest_path.read_bytes()
        result = self.handoff('prepare', success=False)
        self.assertIn('positive control', result['error'])
        self.assertEqual(self.manifest_path.read_bytes(), before)
        self.assertFalse((self.run / 'handoff/acquisition.json').exists())
        self.assertFalse((self.run / 'triage/corpus.jsonl').exists())

    def test_required_native_search_cannot_be_omitted_from_handoff(self):
        path = self.acq / 'query_plan.md'
        path.write_text('```json\n' + json.dumps({'angles': [
            {'name': 'official-records', 'required_search_surfaces': ['native-catalogue']}]
        }) + '\n```\n')
        result = self.handoff('prepare', success=False)
        self.assertIn('required search surface', result['error'])

    def test_new_session_rejects_a_changed_installed_workflow(self):
        installed = Path(self.temp.name) / 'installed-skill'
        shutil.copytree(ROOT, installed, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        script = installed / 'scripts/session_handoff.py'
        prepared = subprocess.run([sys.executable, str(script), 'prepare', '--run-dir', str(self.run)],
                                  capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        before = self.manifest_path.read_bytes()
        reference = installed / 'reference/triage.md'
        reference.write_text(reference.read_text() + '\nChanged workflow contract.\n')
        resumed = subprocess.run([sys.executable, str(script), 'resume', '--run-dir', str(self.run),
                                  '--choice', 'new-session'], capture_output=True, text=True)
        self.assertEqual(resumed.returncode, 1, resumed.stdout + resumed.stderr)
        self.assertIn('workflow_sha256', resumed.stdout)
        self.assertEqual(self.manifest_path.read_bytes(), before)

    def test_unresolved_attempts_are_visible_in_the_handoff_summary(self):
        query = search_record(self.run)
        failed = search_record(self.run, 'failed-retry', outcome='blocked')
        (self.acq / 'query_log.jsonl').write_text(
            ''.join(json.dumps(q) + '\n' for q in (query, failed)))
        self.cli('citation_manager.py', 'build-source-map', '--acq-dir', str(self.acq))
        result = self.handoff('prepare')
        self.assertEqual(result['search_quality']['usable_query_ids'], ['q_test'])
        self.assertEqual(result['search_quality']['unresolved_searches'][0]['query_id'], 'failed-retry')
        saved = json.loads((self.run / 'handoff/acquisition.json').read_text())
        self.assertEqual(saved['version'], 2)
        self.assertEqual(saved['search_quality'], result['search_quality'])

    def test_relocated_bundle_resumes_with_relative_inputs(self):
        self.handoff('prepare')
        moved = Path(self.temp.name) / 'copied run'
        shutil.copytree(self.run, moved)
        shutil.rmtree(self.run)
        self.run = moved
        self.manifest_path = moved / 'run_manifest.json'
        self.handoff('resume', '--choice', 'new-session')
        self.assertEqual(self.manifest()['continuation']['previous_run_manifest'],
                         str(moved / 'run_manifest.json'))

    def test_preparation_cannot_overwrite_a_pending_or_processing_run(self):
        self.handoff('prepare')
        saved = (self.run / 'handoff/acquisition.json').read_bytes()
        self.handoff('prepare', success=False)
        self.assertEqual((self.run / 'handoff/acquisition.json').read_bytes(), saved)
        self.handoff('resume', '--choice', 'same-session')
        self.handoff('resume', '--choice', 'same-session', success=False)
        manifest = self.manifest()
        manifest['phases_completed'].append('triage')
        self.write_manifest(manifest)
        self.handoff('prepare', success=False)

    def test_bad_provenance_and_escaping_paths_block_preparation(self):
        record_path = self.acq / 'retrieval/source.json'
        original = json.loads(record_path.read_text())
        for change in ({'source_id': '0' * 16}, {'content_sha256': '0' * 64},
                       {'content_file': '../run_manifest.json'}):
            with self.subTest(change=change):
                record_path.write_text(json.dumps(dict(original, **change)))
                self.handoff('prepare', success=False)
        record_path.write_text(json.dumps(original))

    def test_all_modes_offer_the_same_boundary(self):
        original_run = self.run
        for mode in ('quick', 'standard', 'deep', 'ultradeep'):
            with self.subTest(mode=mode):
                self.run = Path(self.temp.name) / mode
                shutil.copytree(original_run, self.run)
                self.manifest_path = self.run / 'run_manifest.json'
                manifest = self.manifest()
                manifest['mode'] = mode
                self.write_manifest(manifest)
                self.assertEqual(self.handoff('prepare')['status'], 'awaiting_user')
                self.assertEqual(self.handoff('resume', '--choice', 'new-session')['next_phase'], 'triage')

    def test_malformed_snapshot_and_source_map_fail_cleanly(self):
        source_map_path = self.acq / 'source_map.json'
        original = source_map_path.read_bytes()
        for value in ([], {'totals': []}):
            source_map_path.write_text(json.dumps(value))
            self.handoff('prepare', success=False)
        source_map_path.write_bytes(original)
        self.handoff('prepare')
        (self.run / 'handoff/acquisition.json').write_text('[]')
        self.handoff('check', success=False)


if __name__ == '__main__':
    unittest.main()
