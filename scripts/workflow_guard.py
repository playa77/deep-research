"""Local workflow checks, not authentication of user messages.

The host must enforce read-only skill access and attest message provenance to
protect against an agent that can fabricate files or bypass these helpers.
"""
from datetime import datetime, timezone
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = 'handoff/acquisition.json'
PROMPT = 'handoff/processing_prompt.md'
DECISION = 'handoff/user_decision.json'


def current_session_id():
    """Use runtime identity, never a caller-selected --session-id/--choice.

    Hosts must protect identity injection for adversarial enforcement. Setting
    or replacing these variables in agent commands is a protocol violation.
    """
    session = os.environ.get('HERMES_SESSION_ID') or os.environ.get('CODEX_THREAD_ID')
    if not session or not session.strip():
        raise ValueError('host session identity unavailable; configure HERMES_SESSION_ID or '
                         'CODEX_THREAD_ID in the runtime, never invent a session or bypass the boundary')
    return session


def external_run(run):
    run = Path(run).resolve()
    roots = [ROOT]
    if ROOT.name == 'deep-research':
        roots.append((ROOT.parent / 'deep-research-processing').resolve())
    for root in roots:
        if run.is_relative_to(root) or root.is_relative_to(run):
            raise ValueError('research run must be outside and must not contain either skill directory')
    return run


def workflow_digest():
    from fact_check import digest, sha
    files = [ROOT / name for name in ('SKILL.md', 'README.md', 'requirements.txt')]
    for folder in ('scripts', 'schemas', 'reference', 'templates', 'processing-skill'):
        for path in sorted((ROOT / folder).rglob('*')):
            if '__pycache__' in path.parts:
                continue
            if path.is_symlink():
                raise ValueError(f'skill symlink is not allowed: {path.relative_to(ROOT)}')
            if path.is_file():
                files.append(path)
    # The separately installed processor entry must match the version bundled
    # with its shared engine. Editing either copy invalidates research.
    installed = ROOT.parent / 'deep-research-processing' / 'SKILL.md'
    installed_hash = None
    if ROOT.name == 'deep-research' and installed.exists():
        if installed.is_symlink() or installed.read_bytes() != (ROOT / 'processing-skill/SKILL.md').read_bytes():
            raise ValueError('workflow_sha256 changed: installed processing skill differs from the engine release')
        installed_hash = sha(installed.read_bytes())
    for path in files:
        if path.is_symlink():
            raise ValueError(f'skill symlink is not allowed: {path.relative_to(ROOT)}')
    fingerprints = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in files}
    fingerprints['installed_processor_sha256'] = installed_hash
    return digest(fingerprints)


def unchanged_skill(run):
    from fact_check import inside, load_json, require
    run = external_run(run)
    manifest = load_json(inside(run, 'run_manifest.json'))
    require(isinstance(manifest, dict), 'run manifest must be an object')
    require(manifest.get('workflow_sha256') == workflow_digest(),
            'workflow_sha256 changed or missing: skill is read-only during research; '
            'stop and report, never refresh the baseline during a run')
    return manifest


def decision_line(boundary_id):
    return f'Process this bundle in this fresh session. Boundary: {boundary_id}'


def validate_decision(run, saved, decision, processing_session=None):
    from fact_check import require, validate_schema
    validate_schema(decision, 'user_decision.schema.json')
    require(decision['boundary_id'] == saved['boundary_id'], 'decision belongs to another boundary')
    notice, message = decision['boundary_notice'], decision['user_message']
    require(notice['session_id'] == saved['gathering_session_id'], 'wrong gathering session')
    require((notice['session_id'], notice['message_id']) !=
            (message['session_id'], message['message_id']), 'decision must be a later user message')
    require(message['session_id'] != notice['session_id'],
            'same-session processing is forbidden; the user must open a fresh session')
    require(message['session_id'] == (processing_session or current_session_id()),
            'user message does not belong to the current processing session')
    prepared = datetime.fromisoformat(saved['prepared_at'].replace('Z', '+00:00'))
    received = datetime.fromisoformat(message['received_at'].replace('Z', '+00:00'))
    require(prepared < received <= datetime.now(timezone.utc),
            'user decision must follow preparation and cannot be future-dated')
    # The user may update the absolute path when moving the bundle.
    from fact_check import inside
    expected = inside(run, PROMPT).read_text(encoding='utf-8').replace(
        saved['prepared_run_directory'], str(run))
    require(message['content'].strip() == expected.strip(),
            'quote the actual user-submitted fresh-session prompt; '
            'standing autonomy, the initial brief, and an agent-selected choice do not qualify')
    return decision


def require_processing(run, reviewer=False):
    """Check before reading/scoring sources or writing processing artifacts.

    Do not rehash acquisition inputs here: authorized delta acquisition can
    extend them. The original boundary and user-decision record stay frozen.
    """
    from fact_check import digest, inside, load_json, require, sha, validate_schema
    run = external_run(run)
    manifest = unchanged_skill(run)
    validate_schema(manifest, 'run_manifest.schema.json')
    require(current_session_id() != manifest['gathering_session_id'],
            'same-session processing is forbidden; the gathering session can never process its run')
    handoff = manifest.get('processing_handoff')
    require(handoff and handoff['status'] == 'processing',
            'processing blocked: gathering must stop and await a later user decision')
    saved = load_json(inside(run, SNAPSHOT))
    require(isinstance(saved, dict) and saved.get('version') == 3,
            'processing requires a version-3 boundary; legacy runs need explicit migration')
    require(digest(saved) == handoff['snapshot_sha256'], 'boundary snapshot changed')
    require(saved['boundary_id'] == handoff['boundary_id'], 'boundary identity changed')
    require(saved['gathering_session_id'] == manifest['gathering_session_id'], 'gathering identity changed')
    require(saved['workflow_sha256'] == manifest['workflow_sha256'], 'workflow_sha256 changed')
    require(sha(inside(run, PROMPT).read_bytes()) == saved['prompt_sha256'], 'handoff prompt changed')
    continuation = manifest.get('continuation') or {}
    author_session = continuation.get('processing_session_id')
    require(author_session and (reviewer or author_session == current_session_id()),
            'processing belongs to a different session; do not impersonate or silently transfer it')
    decision = load_json(inside(run, DECISION))
    require(digest(decision) == continuation.get('decision_sha256'), 'user decision changed or missing')
    validate_decision(run, saved, decision, processing_session=author_session)
    return manifest


def require_acquisition(run):
    """Gather in its owner session, or append sanctioned processor deltas."""
    from fact_check import require
    manifest = unchanged_skill(run)
    handoff = manifest.get('processing_handoff')
    if handoff and handoff.get('status') == 'processing':
        return require_processing(run)
    require(not handoff, 'gathering is sealed; only display the handoff and end the turn')
    require(current_session_id() == manifest.get('gathering_session_id'),
            'acquisition belongs to the original gathering session')
    return manifest


def processing_for_paths(*paths):
    """Resolve every run used by a processing CLI; no missing-manifest bypass."""
    runs = set()
    for name in paths:
        if name is None:
            continue
        path = Path(name).resolve()
        candidates = (path, *path.parents)
        run = next((p for p in candidates if (p / 'run_manifest.json').is_file()), None)
        if run is None:
            raise ValueError(f'processing requires a run_manifest.json: {path}')
        runs.add(run)
    for run in sorted(runs):
        require_processing(run)
