#!/usr/bin/env python3
"""Preserve the acquisition/processing boundary; never infer a user decision.

prepare checks and snapshots the gathered bundle, then leaves it awaiting the
user. resume accepts the user-submitted prompt only in a different host session.
resume requires a boundary-bound record of a later user message. This local
record is auditable evidence, not host-authenticated proof of a turn boundary.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys
import tempfile

from citation_manager import compute_source_id, FRONTMATTER_RE
from search_quality import check_acquisition
from workflow_guard import (unchanged_skill, workflow_digest, validate_decision,
                            current_session_id, DECISION)
from fact_check import (ContractError, digest, inside, load_json, load_rows, parse_json,
                        output_path, sha, validate_schema)

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = 'handoff/acquisition.json'
PROMPT = 'handoff/processing_prompt.md'
BOOKKEEPING = {'report_dir', 'finished_at', 'phases_completed', 'continuation',
               'processing_handoff'}


def require(condition, message):
    if not condition:
        raise ContractError(message)


def snapshot(run):
    manifest = unchanged_skill(run)
    validate_schema(manifest, 'run_manifest.schema.json')
    require(manifest['query'].strip(), 'research question is empty')
    require(manifest.get('research_contract'), 'persist the complete research_contract first')
    if manifest['mode'] in ('deep', 'ultradeep'):
        require(2 <= len(manifest.get('hypotheses', [])) <= 4,
                'deep/ultradeep require 2–4 persisted scope hypotheses')
    require(manifest.get('phases_completed') == ['scope', 'acquire'],
            'handoff requires completed scope/acquire only; never reset a processing run')
    require(manifest.get('finished_at') is None, 'run is already finished')

    paths = manifest['artifact_paths']
    files = {paths[k] for k in ('query_plan', 'query_log', 'sources', 'leads')}
    files.add('acquisition/source_map.json')
    plan = inside(run, paths['query_plan']).read_text(encoding='utf-8')
    require(plan.strip(), 'query plan is empty')
    plans = [parse_json(block) for block in re.findall(r'```json\s*\n(.*?)```', plan, re.DOTALL)]
    angle_plans = [item['angles'] for item in plans if isinstance(item, dict) and
                   isinstance(item.get('angles'), list) and item['angles']]
    require(len(angle_plans) == 1, 'query plan needs exactly one nonempty machine-readable angles block')
    source_map = load_json(inside(run, 'acquisition/source_map.json'))
    sources = load_rows(inside(run, paths['sources']))
    queries = load_rows(inside(run, paths['query_log']))
    load_rows(inside(run, paths['leads']))
    require(sources and queries, 'merged sources and query log must be nonempty')
    totals = source_map.get('totals') if isinstance(source_map, dict) else None
    require(isinstance(totals, dict) and totals.get('sources') == len(sources)
            and totals.get('queries') == len(queries),
            'source map is stale; rebuild it after merging')
    ids = set()
    quality = check_acquisition(run, queries, angle_plans[0])
    files.update(quality['response_files'])
    for source in sources:
        validate_schema(source, 'source.schema.json')
        sid = source['source_id']
        require(sid not in ids, f'duplicate source ID: {sid}')
        ids.add(sid)
        require(sid == compute_source_id(source['canonical_locator']), f'unstable source ID: {sid}')
        require(source.get('raw_file') and source.get('retrieval_record'),
                f'{sid}: missing extracted text or retrieval provenance')
        raw_name = 'acquisition/' + source['raw_file']
        record_name = 'acquisition/' + source['retrieval_record']
        raw = inside(run, raw_name)
        record = load_json(inside(run, record_name))
        validate_schema(record, 'retrieval.schema.json')
        require(record['source_id'] == sid and record['requested_url'] == source['raw_url'],
                f'{sid}: retrieval identity mismatch')
        original_name = 'acquisition/' + record['content_file']
        original = inside(run, original_name)
        require(original != raw, f'{sid}: original response and extracted text must be separate')
        require(original.stat().st_size > 0, f'{sid}: original response is empty')
        require(sha(original.read_bytes()) == record['content_sha256'], f'{sid}: original hash mismatch')
        text = raw.read_text(encoding='utf-8')
        frontmatter = FRONTMATTER_RE.match(text)
        require(frontmatter and text[frontmatter.end():].strip(), f'{sid}: missing frontmatter or source body')
        files.update((raw_name, record_name, original_name))

    inputs = {'run_manifest.json': digest({k: v for k, v in manifest.items() if k not in BOOKKEEPING})}
    for relative in sorted(files):
        path = inside(run, relative)
        if relative.startswith('acquisition/'):
            require(path.is_relative_to((run / 'acquisition').resolve()),
                    f'artifact escapes acquisition directory: {relative}')
        inputs[relative] = sha(path.read_bytes())
    return manifest, {'version': 3, 'inputs': inputs, 'workflow_sha256': workflow_digest(),
                      'search_quality': quality,
                      'source_count': len(sources), 'query_count': len(queries)}


def write_json(path, value):
    # Replace atomically rather than truncating a manifest or a hard-linked input.
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     delete=False) as temporary:
        name = Path(temporary.name)
        try:
            temporary.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            temporary.close()
            name.replace(path)
        finally:
            name.unlink(missing_ok=True)


def prepare(run):
    manifest, saved = snapshot(run)
    session_id = current_session_id()
    require(session_id == manifest['gathering_session_id'],
            'only the original gathering session may prepare its handoff')
    # Empty skeleton files are fine; substantive processing before the stop is not.
    for folder in ('triage', 'evidence', 'report', 'qa'):
        require(not any(p.is_file() and p.stat().st_size for p in (run / folder).rglob('*')),
                f'processing artifacts already exist in {folder}; disclose the boundary violation, never launder it')
    destination = output_path(run, SNAPSHOT)
    prompt_path = output_path(run, PROMPT)
    require(not destination.exists() and not prompt_path.exists() and
            manifest.get('processing_handoff') is None,
            'handoff already exists; check/resume it, or explicitly archive it before repairing acquisition')
    saved['prepared_at'] = datetime.now(timezone.utc).isoformat()
    saved['boundary_id'] = secrets.token_hex(16)
    saved['gathering_session_id'] = session_id
    saved['prepared_run_directory'] = str(run)
    prompt = (ROOT / 'templates/processing_handoff_prompt.md').read_text(encoding='utf-8')
    prompt = prompt.replace('<RUN_DIRECTORY>', str(run))
    prompt = prompt.replace('<BOUNDARY_ID>', saved['boundary_id'])
    saved['prompt_sha256'] = sha(prompt.encode('utf-8'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, saved)
    prompt_path.write_text(prompt, encoding='utf-8')
    manifest['processing_handoff'] = {'status': 'awaiting_user', 'next_phase': 'triage',
                                      'snapshot': SNAPSHOT, 'prompt': PROMPT,
                                      'boundary_id': saved['boundary_id'],
                                      'snapshot_sha256': digest(saved)}
    write_json(output_path(run, 'run_manifest.json'), manifest)
    return {'status': 'awaiting_user', 'next_phase': 'triage', 'prompt': str(prompt_path),
            'boundary_id': saved['boundary_id'],
            'required_action': 'Present the literal prompt for deep-research-processing and END THE TURN. '
                               'A fresh user-started session is mandatory. No same-session continuation exists.',
            'source_count': saved['source_count'], 'query_count': saved['query_count'],
            'search_quality': saved['search_quality']}


def check(run):
    manifest, current = snapshot(run)
    handoff = manifest.get('processing_handoff')
    require(handoff and handoff['status'] == 'awaiting_user', 'run is not awaiting a fresh-session user submission')
    saved = load_json(inside(run, SNAPSHOT))
    require(isinstance(saved, dict), 'handoff snapshot must contain an object')
    require(saved.get('version') == 3, 'legacy handoff requires explicit migration to version 3')
    require(digest(saved) == handoff['snapshot_sha256'], 'boundary snapshot changed')
    require(saved['boundary_id'] == handoff['boundary_id'], 'boundary identity changed')
    for key, value in current.items():
        require(saved.get(key) == value, f'acquisition snapshot changed: {key}; inspect and repair before resuming')
    require(sha(inside(run, PROMPT).read_bytes()) == saved.get('prompt_sha256'),
            'processing prompt changed; inspect and repair before resuming')
    return manifest


def resume(run, decision_path):
    manifest = check(run)
    require(current_session_id() != manifest['gathering_session_id'],
            'same-session processing is forbidden; open a fresh user-started session')
    require(decision_path is not None, 'resume requires --decision: the actual user-submitted fresh-session prompt')
    decision = load_json(decision_path)
    saved = load_json(inside(run, SNAPSHOT))
    validate_decision(run, saved, decision)
    destination = output_path(run, DECISION)
    require(not destination.exists(), 'user decision already exists; never overwrite boundary evidence')
    write_json(destination, decision)
    manifest['processing_handoff']['status'] = 'processing'
    continuation = manifest.get('continuation') or {}
    continuation.update(previous_run_manifest=str(run / 'run_manifest.json'),
                        resumed_at=datetime.now(timezone.utc).isoformat(),
                        processing_session_id=current_session_id(), decision_sha256=digest(decision))
    manifest['continuation'] = continuation
    write_json(output_path(run, 'run_manifest.json'), manifest)
    return {'status': 'processing', 'next_phase': 'triage', 'processing_session_id': current_session_id()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'check', 'resume'):
        command = sub.add_parser(name)
        command.add_argument('--run-dir', type=Path, required=True)
        if name == 'resume':
            command.add_argument('--decision', type=Path, help='JSON record of the actual later user message')
    args = parser.parse_args()
    run = args.run_dir.resolve()
    try:
        if args.command == 'prepare':
            result = prepare(run)
        elif args.command == 'resume':
            result = resume(run, args.decision)
        else:
            check(run)
            result = {'status': 'awaiting_user', 'next_phase': 'triage'}
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
