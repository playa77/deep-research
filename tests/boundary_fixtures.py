"""Synthetic processing state for isolated unit tests, never real consent.

End-to-end boundary tests use actual prepare/check/resume. These fixtures avoid
making unrelated scoring/formatting tests acquire a complete research bundle.
"""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from fact_check import digest, sha
from workflow_guard import workflow_digest, decision_line, current_session_id

# Isolated tests also run outside a chat host. This synthetic identity is test
# harness setup only; production never falls back to a fabricated session.
if not (os.environ.get('HERMES_SESSION_ID') or os.environ.get('CODEX_THREAD_ID')):
    os.environ['HERMES_SESSION_ID'] = 'synthetic:unit-processing'


def session_env(session_id):
    return dict(os.environ, HERMES_SESSION_ID=session_id, CODEX_THREAD_ID=session_id)


def user_decision(run, session_id=None):
    run = Path(run)
    saved = json.loads((run / 'handoff/acquisition.json').read_text())
    content = (run / 'handoff/processing_prompt.md').read_text().replace(
        saved['prepared_run_directory'], str(run))
    return {
        'version': 1, 'boundary_id': saved['boundary_id'],
        'boundary_notice': {'session_id': saved['gathering_session_id'], 'message_id': 'synthetic:notice'},
        'user_message': {'role': 'user', 'session_id': session_id or current_session_id(),
                         'message_id': 'synthetic:later-user',
                         'received_at': datetime.now(timezone.utc).isoformat(), 'content': content}}


def processing_fixture(run):
    run = Path(run)
    run.mkdir(parents=True, exist_ok=True)
    path = run / 'run_manifest.json'
    manifest = json.loads(path.read_text()) if path.exists() else {}
    manifest.setdefault('version', '1.0.0')
    manifest.setdefault('query', 'Synthetic unit fixture')
    manifest.setdefault('mode', 'standard')
    manifest.setdefault('started_at', '2026-01-01T00:00:00Z')
    manifest.setdefault('report_dir', str(run))
    manifest.setdefault('artifact_paths', {
        'query_plan': 'acquisition/query_plan.md', 'query_log': 'acquisition/query_log.jsonl',
        'sources': 'acquisition/sources.jsonl', 'leads': 'acquisition/leads.jsonl',
        'raw_dir': 'acquisition/raw', 'corpus': 'triage/corpus.jsonl',
        'evidence': 'evidence/evidence.jsonl', 'claims': 'evidence/claims.jsonl', 'report': 'report/report.md'})
    manifest['workflow_sha256'] = workflow_digest()
    manifest['gathering_session_id'] = 'synthetic:gathering'
    folder = run / 'handoff'
    folder.mkdir(exist_ok=True)
    boundary_id = 'f' * 32
    prompt = decision_line(boundary_id)
    (folder / 'processing_prompt.md').write_text(prompt)
    saved = {'version': 3, 'workflow_sha256': manifest['workflow_sha256'], 'boundary_id': boundary_id,
             'prepared_at': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
             'gathering_session_id': 'synthetic:gathering', 'prepared_run_directory': str(run),
             'prompt_sha256': sha(prompt.encode())}
    (folder / 'acquisition.json').write_text(json.dumps(saved))
    decision = user_decision(run)
    (folder / 'user_decision.json').write_text(json.dumps(decision))
    manifest['processing_handoff'] = {'status': 'processing', 'next_phase': 'triage',
                                      'snapshot': 'handoff/acquisition.json', 'prompt': 'handoff/processing_prompt.md',
                                      'boundary_id': boundary_id, 'snapshot_sha256': digest(saved)}
    manifest['continuation'] = {'processing_session_id': current_session_id(), 'decision_sha256': digest(decision)}
    path.write_text(json.dumps(manifest))
