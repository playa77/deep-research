"""Exercise the actual acquisition boundary and fresh-process continuation."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from boundary_fixtures import user_decision, session_env
from search_fixtures import search_record

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent


class SessionHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = 'synthetic:gathering'
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
                                text=True, capture_output=True, env=session_env(self.session))
        self.assertEqual(result.returncode, 0 if success else 1, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def handoff(self, command, *args, success=True):
        if command == 'resume' and '--decision' not in args:
            self.session = 'synthetic:processing'
            decision = self.run / 'decision-input.json'
            decision.write_text(json.dumps(user_decision(self.run, self.session)))
            args += ('--decision', str(decision))
        return self.cli('session_handoff.py', command, '--run-dir', str(self.run),
                        *args, success=success)

    def manifest(self):
        return json.loads(self.manifest_path.read_text())

    def write_manifest(self, manifest):
        self.manifest_path.write_text(json.dumps(manifest))

    def test_fresh_session_preserves_inputs_and_all_processing_requirements(self):
        self.handoff('prepare')
        original = self.manifest()
        self.assertEqual(original['processing_handoff']['status'], 'awaiting_user')
        prompt = (self.run / 'handoff/processing_prompt.md').read_text()
        for required in (str(self.run), 'deep-research-processing', 'reference/fact-checking.md',
                         '--decision', 'phases 3–8', 'independent verification and red-team'):
            self.assertIn(required, prompt)
        self.assertNotIn('--choice', prompt)
        self.assertEqual(self.handoff('check')['status'], 'awaiting_user')
        self.assertEqual(self.manifest(), original)
        saved_files = {str(p.relative_to(self.acq)): p.read_bytes()
                       for p in self.acq.rglob('*') if p.is_file()}
        result = self.handoff('resume')
        self.assertEqual(result['next_phase'], 'triage')
        manifest = self.manifest()
        self.assertEqual(manifest['continuation']['processing_session_id'], 'synthetic:processing')
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
                self.handoff('resume', success=False)
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
                                  capture_output=True, text=True, env=session_env(self.session))
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        before = self.manifest_path.read_bytes()
        reference = installed / 'reference/triage.md'
        reference.write_text(reference.read_text() + '\nChanged workflow contract.\n')
        resumed = subprocess.run([sys.executable, str(script), 'resume', '--run-dir', str(self.run)], capture_output=True, text=True, env=session_env(self.session))
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
        self.assertEqual(saved['version'], 3)
        self.assertEqual(saved['search_quality'], result['search_quality'])

    def test_relocated_bundle_resumes_with_relative_inputs(self):
        self.handoff('prepare')
        moved = Path(self.temp.name) / 'copied run'
        shutil.copytree(self.run, moved)
        shutil.rmtree(self.run)
        self.run = moved
        self.manifest_path = moved / 'run_manifest.json'
        self.handoff('resume')
        self.assertEqual(self.manifest()['continuation']['previous_run_manifest'],
                         str(moved / 'run_manifest.json'))

    def test_preparation_cannot_overwrite_a_pending_or_processing_run(self):
        self.handoff('prepare')
        saved = (self.run / 'handoff/acquisition.json').read_bytes()
        self.handoff('prepare', success=False)
        self.assertEqual((self.run / 'handoff/acquisition.json').read_bytes(), saved)
        self.handoff('resume')
        self.handoff('resume', success=False)
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

    def test_all_modes_require_a_different_processing_session(self):
        original_run = self.run
        for mode in ('quick', 'standard', 'deep', 'ultradeep'):
            with self.subTest(mode=mode):
                self.session = 'synthetic:gathering'
                self.run = Path(self.temp.name) / mode
                shutil.copytree(original_run, self.run)
                self.manifest_path = self.run / 'run_manifest.json'
                manifest = self.manifest()
                manifest['mode'] = mode
                self.write_manifest(manifest)
                self.assertEqual(self.handoff('prepare')['status'], 'awaiting_user')
                self.assertEqual(self.handoff('resume')['next_phase'], 'triage')

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


    def tree_bytes(self):
        return {str(p.relative_to(self.run)): p.read_bytes()
                for p in self.run.rglob('*') if p.is_file()}

    def test_same_session_cannot_resume_even_with_complete_user_record(self):
        self.handoff('prepare')
        record = self.run / 'decision-input.json'
        record.write_text(json.dumps(user_decision(self.run, self.session)))
        before = self.tree_bytes()
        for args in ((), ('--decision', str(record))):
            result = self.cli('session_handoff.py', 'resume', '--run-dir', str(self.run), *args, success=False)
            self.assertIn('same-session processing is forbidden', result['error'])
            self.assertEqual(before, self.tree_bytes())
        self.assertEqual(self.handoff('check')['status'], 'awaiting_user')

    def test_fresh_session_still_needs_actual_user_prompt(self):
        self.handoff('prepare')
        self.session = 'synthetic:processing'
        before = self.tree_bytes()
        result = self.cli('session_handoff.py', 'resume', '--run-dir', str(self.run), success=False)
        self.assertIn('--decision', result['error'])
        self.assertEqual(before, self.tree_bytes())

    def test_old_choice_and_identity_override_flags_are_removed(self):
        self.handoff('prepare')
        before = self.tree_bytes()
        for args in (('--choice', 'same-session'), ('--choice', 'new-session'),
                     ('--session-id', 'pretend-fresh-session')):
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/session_handoff.py'),
                                   'resume', '--run-dir', str(self.run), *args],
                                  capture_output=True, text=True, env=session_env(self.session))
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertEqual(before, self.tree_bytes())

    def test_gathering_session_stays_barred_after_legitimate_fresh_session_resume(self):
        self.handoff('prepare')
        self.handoff('resume')
        self.session = 'synthetic:gathering'
        before = self.tree_bytes()
        for script, args in (
            ('triage.py', ('run', '--run-dir', str(self.run))),
            ('fact_check.py', ('prepare', '--run-dir', str(self.run))),
            ('evidence_store.py', ('add', '--dir', str(self.run / 'evidence'), '--json', '{}')),
        ):
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *args],
                                  capture_output=True, text=True, env=session_env(self.session))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('same-session processing is forbidden', proc.stdout + proc.stderr)
            self.assertEqual(before, self.tree_bytes())

    def test_another_chat_cannot_impersonate_the_recorded_processing_session(self):
        self.handoff('prepare')
        self.handoff('resume')
        self.session = 'synthetic:unrelated-chat'
        before = self.tree_bytes()
        result = self.cli('triage.py', 'run', '--run-dir', str(self.run), success=False)
        self.assertIn('different session', result['error'])
        self.assertEqual(before, self.tree_bytes())

    def test_missing_host_identity_blocks_initialization_and_processing(self):
        environment = session_env(self.session)
        for name in ('HERMES_SESSION_ID', 'CODEX_THREAD_ID'):
            environment.pop(name, None)
        target = Path(self.temp.name) / 'no-identity-run'
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/citation_manager.py'),
                               'init-run', '--out-dir', str(target)], capture_output=True,
                              text=True, env=environment)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('host session identity unavailable', proc.stdout + proc.stderr)
        self.assertFalse(target.exists())
        self.handoff('prepare')
        self.handoff('resume')
        before = self.tree_bytes()
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/triage.py'),
                               'run', '--run-dir', str(self.run)], capture_output=True,
                              text=True, env=environment)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('host session identity unavailable', proc.stdout + proc.stderr)
        self.assertEqual(before, self.tree_bytes())

    def test_missing_manifest_cannot_turn_evidence_writes_into_standalone_bypass(self):
        self.manifest_path.unlink()
        before = self.tree_bytes()
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/evidence_store.py'),
                               'add', '--dir', str(self.run / 'evidence'), '--json', '{}'],
                              capture_output=True, text=True, env=session_env(self.session))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('requires a run_manifest.json', proc.stdout + proc.stderr)
        self.assertEqual(before, self.tree_bytes())

    def test_pending_gathering_is_sealed_against_more_acquisition_commands(self):
        self.handoff('prepare')
        before = self.tree_bytes()
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/citation_manager.py'),
                               'merge-sources', '--acq-dir', str(self.acq)], capture_output=True,
                              text=True, env=session_env(self.session))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('gathering is sealed', proc.stdout + proc.stderr)
        self.assertEqual(before, self.tree_bytes())

    def test_imported_processing_commands_cannot_bypass_session_guards(self):
        self.handoff('prepare')
        before = self.tree_bytes()
        calls = [
            'triage.step_dedupe([], run)', 'triage.step_cluster([], run)',
            'triage.step_score([], run)', 'triage.step_select([], run, 10)',
            'triage.step_gaps([], run)', 'triage.write_report([], [], run, 10)',
            'evidence_store.cmd_init(Namespace(dir=run))',
            'evidence_store.cmd_add(Namespace(dir=run, json="{}"))',
            'extract_claims.cmd_add(Namespace(dir=run, json="{}"))',
        ]
        for call in calls:
            code = ('import sys; from argparse import Namespace; sys.path.insert(0, sys.argv[1]); '
                    'import triage, evidence_store, extract_claims; run=sys.argv[2]; ' + call)
            proc = subprocess.run([sys.executable, '-c', code, str(ROOT / 'scripts'), str(self.run)],
                                  capture_output=True, text=True, env=session_env(self.session))
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn('same-session processing is forbidden', proc.stdout + proc.stderr)
            self.assertEqual(before, self.tree_bytes())

    def test_missing_initial_skill_baseline_cannot_be_silently_upgraded(self):
        manifest = self.manifest()
        manifest.pop('workflow_sha256')
        self.write_manifest(manifest)
        before = self.tree_bytes()
        result = self.handoff('prepare', success=False)
        self.assertIn('workflow_sha256', result['error'])
        self.assertEqual(before, self.tree_bytes())

    def test_invalid_or_inferred_decisions_leave_pending_state_untouched(self):
        self.handoff('prepare')
        self.session = 'synthetic:processing'
        valid = user_decision(self.run, self.session)
        cases = []
        for field, value in (('role', 'assistant'), ('content', 'Execute the entire task autonomously.'),
                             ('content', 'Please deliver a complete report.'),
                             ('content', 'Continue processing here.'),
                             ('received_at', '2000-01-01T00:00:00Z'),
                             ('received_at', (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
                             ('session_id', 'synthetic:gathering')):
            record = deepcopy(valid)
            record['user_message'][field] = value
            cases.append(record)
        for field, value in (('boundary_id', '0' * 32),):
            record = deepcopy(valid)
            record[field] = value
            cases.append(record)
        cases.extend(([], {}, dict(valid, unexpected='untrusted')))
        record_path = self.run / 'decision-input.json'
        for record in cases:
            with self.subTest(record=record):
                record_path.write_text(json.dumps(record))
                before = self.tree_bytes()
                self.handoff('resume', '--decision', str(record_path), success=False)
                self.assertEqual(before, self.tree_bytes())

    def test_all_processing_cli_routes_block_before_the_user_choice_without_writes(self):
        self.handoff('prepare')
        before = self.tree_bytes()
        commands = [('triage.py', step, '--run-dir', str(self.run))
                    for step in ('run', 'dedupe', 'cluster', 'score', 'select', 'gaps', 'begin-delta')]
        commands += [
            ('evidence_store.py', 'init', '--dir', str(self.run / 'evidence')),
            ('evidence_store.py', 'add', '--dir', str(self.run / 'evidence'), '--json', '{}'),
            ('extract_claims.py', 'add', '--dir', str(self.run / 'evidence'), '--json', '{}'),
            ('extract_claims.py', 'extract', '--dir', str(self.run / 'evidence'),
             '--report', str(self.run / 'report/report.md')),
            ('link_claims.py', 'link-claims', '--dir', str(self.run / 'evidence'), '--run-dir', str(self.run)),
            ('citation_manager.py', 'export-bibliography', '--dir', str(self.run)),
            ('citation_manager.py', 'assign-display-numbers', '--dir', str(self.run)),
            ('fact_check.py', 'prepare', '--run-dir', str(self.run)),
            ('fact_check.py', 'inspect', '--run-dir', str(self.run)),
            ('fact_check.py', 'verify', '--run-dir', str(self.run)),
            ('verify_claim_support.py', 'verify', '--dir', str(self.run / 'evidence'), '--strict'),
            ('verify_claim_support.py', 'verify', '--dir', str(self.run / 'evidence')),
            ('verify_citations.py', '--report', str(self.run / 'report/report.md'), '--strict')]
        for command in commands:
            with self.subTest(command=command):
                proc = subprocess.run([sys.executable, str(ROOT / 'scripts' / command[0]), *command[1:]],
                                      text=True, capture_output=True, env=session_env(self.session))
                self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn('same-session processing is forbidden', proc.stdout + proc.stderr)
                self.assertEqual(before, self.tree_bytes())

    def test_missing_manifest_and_missing_handoff_cannot_bypass_triage(self):
        before = self.tree_bytes()
        result = self.cli('triage.py', 'run', '--run-dir', str(self.run), success=False)
        self.assertIn('same-session processing is forbidden', result['error'])
        self.assertEqual(before, self.tree_bytes())
        self.manifest_path.unlink()
        before = self.tree_bytes()
        self.cli('triage.py', 'run', '--run-dir', str(self.run), success=False)
        self.assertEqual(before, self.tree_bytes())

    def test_manifest_status_alone_cannot_fabricate_a_continuation(self):
        self.handoff('prepare')
        manifest = self.manifest()
        manifest['processing_handoff']['status'] = 'processing'
        manifest['continuation'] = {'processing_session_id': self.session}
        self.write_manifest(manifest)
        result = self.cli('triage.py', 'run', '--run-dir', str(self.run), success=False)
        self.assertIn('same-session processing is forbidden', result['error'])
        self.assertFalse((self.run / 'triage/triage_result.json').exists())

    def test_fresh_user_prompt_unlocks_real_triage_and_preserves_boundary_after_delta(self):
        self.handoff('prepare')
        self.handoff('resume')
        frozen = {name: (self.run / name).read_bytes() for name in
                  ('handoff/acquisition.json', 'handoff/user_decision.json', 'handoff/processing_prompt.md')}
        result = self.cli('triage.py', 'run', '--run-dir', str(self.run), '--min-per-angle', '1')
        self.assertEqual(result['status'], 'ok')
        # Approved processing may extend the acquisition bundle; never rewrite
        # the initial snapshot or demand the initial choice again.
        with (self.run / 'acquisition/leads.jsonl').open('a') as stream:
            stream.write('{"lead":"synthetic-delta"}\n')
        result = self.cli('triage.py', 'run', '--run-dir', str(self.run), '--min-per-angle', '1')
        self.assertEqual(result['status'], 'ok')
        for name, content in frozen.items():
            self.assertEqual((self.run / name).read_bytes(), content)

    def test_tampering_with_accepted_decision_blocks_further_processing(self):
        self.handoff('prepare')
        self.handoff('resume')
        path = self.run / 'handoff/user_decision.json'
        decision = json.loads(path.read_text())
        decision['user_message']['message_id'] = 'tampered'
        path.write_text(json.dumps(decision))
        before = self.tree_bytes()
        result = self.cli('triage.py', 'run', '--run-dir', str(self.run), success=False)
        self.assertIn('decision changed', result['error'])
        self.assertEqual(before, self.tree_bytes())

    def test_prepare_cannot_launder_premature_processing(self):
        for relative in ('triage/corpus.jsonl', 'evidence/evidence.jsonl', 'report/report.md', 'qa/qa_report.md'):
            with self.subTest(relative=relative):
                path = self.run / relative
                previous = path.read_bytes() if path.exists() else None
                path.write_text('Premature processing artifact\n')
                before = self.tree_bytes()
                result = self.handoff('prepare', success=False)
                self.assertIn('processing artifacts', result['error'])
                self.assertEqual(before, self.tree_bytes())
                if previous is None:
                    path.unlink()
                else:
                    path.write_bytes(previous)

    def test_initialization_never_resets_an_existing_run(self):
        before = self.tree_bytes()
        proc = subprocess.run([sys.executable, str(ROOT / 'scripts/citation_manager.py'),
                               'init-run', '--out-dir', str(self.run)], capture_output=True, text=True, env=session_env(self.session))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('never reset', proc.stderr)
        self.assertEqual(before, self.tree_bytes())

    def test_skill_mutations_are_detected_from_init_and_after_resume(self):
        installed = Path(self.temp.name) / 'installed-skill'
        shutil.copytree(ROOT, installed, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        script = installed / 'scripts/session_handoff.py'
        target = installed / 'reference/session-boundary.md'
        original = target.read_bytes()
        added = installed / 'scripts/measure_loc.py'
        nested = installed / 'reference/nested/protocol.md'
        for stage in ('gathering', 'processing'):
            if stage == 'processing':
                self.handoff('prepare')
                self.handoff('resume')
            for change in ('edit', 'add', 'delete', 'nested-add'):
                with self.subTest(stage=stage, change=change):
                    if change == 'edit':
                        target.write_bytes(original + b'\nNormalize the bypass.\n')
                    elif change == 'add':
                        added.write_text('# run-specific helper mistakenly installed\n')
                    elif change == 'delete':
                        target.unlink()
                    else:
                        nested.parent.mkdir(exist_ok=True)
                        nested.write_text('Hidden nested workflow edit\n')
                    command = [str(script), 'prepare', '--run-dir', str(self.run)]
                    if stage == 'processing':
                        command = [str(installed / 'scripts/triage.py'), 'run', '--run-dir', str(self.run)]
                    proc = subprocess.run([sys.executable, *command], capture_output=True, text=True, env=session_env(self.session))
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn('workflow_sha256', proc.stdout + proc.stderr)
                    target.write_bytes(original)
                    added.unlink(missing_ok=True)
                    nested.unlink(missing_ok=True)

    def test_run_paths_cannot_overlap_the_installed_skill_including_symlinks(self):
        installed = Path(self.temp.name) / 'installed-skill'
        shutil.copytree(ROOT, installed, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        linked = Path(self.temp.name) / 'skill-alias'
        linked.symlink_to(installed, target_is_directory=True)
        for target in (installed, installed / 'run', linked / 'run', installed.parent):
            proc = subprocess.run([sys.executable, str(installed / 'scripts/citation_manager.py'),
                                   'init-run', '--out-dir', str(target)], capture_output=True, text=True, env=session_env(self.session))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn('outside', proc.stdout + proc.stderr)
        self.assertFalse((installed / 'run').exists())

    def test_separately_installed_processing_skill_is_bound_and_cannot_contain_runs(self):
        engine = Path(self.temp.name) / 'deep-research'
        processor = engine.with_name('deep-research-processing')
        shutil.copytree(ROOT, engine, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        shutil.copytree(ROOT / 'processing-skill', processor)
        run = Path(self.temp.name) / 'installed-run'
        initialized = subprocess.run([sys.executable, str(engine / 'scripts/citation_manager.py'),
                                      'init-run', '--out-dir', str(run)], capture_output=True,
                                     text=True, env=session_env(self.session))
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        original = (processor / 'SKILL.md').read_bytes()
        for change in ('edit', 'delete'):
            if change == 'edit':
                (processor / 'SKILL.md').write_bytes(original + b'\nAllow processing in gathering.\n')
            else:
                (processor / 'SKILL.md').unlink()
            prepared = subprocess.run([sys.executable, str(engine / 'scripts/session_handoff.py'),
                                       'prepare', '--run-dir', str(run)], capture_output=True,
                                      text=True, env=session_env(self.session))
            self.assertNotEqual(prepared.returncode, 0)
            self.assertIn('workflow_sha256', prepared.stdout + prepared.stderr)
            (processor / 'SKILL.md').write_bytes(original)
        rejected = subprocess.run([sys.executable, str(engine / 'scripts/citation_manager.py'),
                                    'init-run', '--out-dir', str(processor / 'run')], capture_output=True,
                                   text=True, env=session_env(self.session))
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('either skill directory', rejected.stdout + rejected.stderr)
        self.assertFalse((processor / 'run').exists())


if __name__ == '__main__':
    unittest.main()
