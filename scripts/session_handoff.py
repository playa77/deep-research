#!/usr/bin/env python3
"""Preserve the acquisition/processing boundary; no research or approvals.

prepare checks and snapshots the gathered bundle, then leaves it awaiting the
user. resume checks the snapshot and records a user-selected session choice.
The skill, not this CLI, must obtain that choice before calling resume.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import tempfile

from citation_manager import compute_source_id, FRONTMATTER_RE
from search_quality import check_acquisition
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
    manifest = load_json(inside(run, 'run_manifest.json'))
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
    workflow = {str(p.relative_to(ROOT)): sha(p.read_bytes())
                for folder in ('scripts', 'schemas', 'reference', 'templates')
                for p in sorted((ROOT / folder).glob('*')) if p.is_file()}
    workflow['SKILL.md'] = sha((ROOT / 'SKILL.md').read_bytes())
    return manifest, {'version': 2, 'inputs': inputs, 'workflow_sha256': digest(workflow),
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
    destination = output_path(run, SNAPSHOT)
    prompt_path = output_path(run, PROMPT)
    require(not destination.exists() and not prompt_path.exists() and
            manifest.get('processing_handoff') is None,
            'handoff already exists; check/resume it, or explicitly archive it before repairing acquisition')
    saved['prepared_at'] = datetime.now(timezone.utc).isoformat()
    prompt = (ROOT / 'templates/processing_handoff_prompt.md').read_text(encoding='utf-8')
    prompt = prompt.replace('<RUN_DIRECTORY>', str(run))
    saved['prompt_sha256'] = sha(prompt.encode('utf-8'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, saved)
    prompt_path.write_text(prompt, encoding='utf-8')
    manifest['processing_handoff'] = {'status': 'awaiting_user', 'next_phase': 'triage',
                                      'snapshot': SNAPSHOT, 'prompt': PROMPT}
    write_json(output_path(run, 'run_manifest.json'), manifest)
    return {'status': 'awaiting_user', 'next_phase': 'triage', 'prompt': str(prompt_path),
            'source_count': saved['source_count'], 'query_count': saved['query_count'],
            'search_quality': saved['search_quality']}


def check(run):
    manifest, current = snapshot(run)
    handoff = manifest.get('processing_handoff')
    require(handoff and handoff['status'] == 'awaiting_user', 'run is not awaiting a processing choice')
    saved = load_json(inside(run, SNAPSHOT))
    require(isinstance(saved, dict), 'handoff snapshot must contain an object')
    for key, value in current.items():
        require(saved.get(key) == value, f'acquisition snapshot changed: {key}; inspect and repair before resuming')
    require(sha(inside(run, PROMPT).read_bytes()) == saved.get('prompt_sha256'),
            'processing prompt changed; inspect and repair before resuming')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'check', 'resume'):
        command = sub.add_parser(name)
        command.add_argument('--run-dir', type=Path, required=True)
        if name == 'resume':
            command.add_argument('--choice', choices=('same-session', 'new-session'), required=True,
                                 help='Record the choice already made by the user')
    args = parser.parse_args()
    run = args.run_dir.resolve()
    try:
        if args.command == 'prepare':
            result = prepare(run)
        else:
            manifest = check(run)
            result = {'status': 'ready_for_processing', 'next_phase': 'triage'}
            if args.command == 'resume':
                manifest['processing_handoff']['status'] = 'processing'
                continuation = manifest.get('continuation') or {}
                continuation.update(previous_run_manifest=str(run / 'run_manifest.json'),
                                    resumed_at=datetime.now(timezone.utc).isoformat(),
                                    session_choice=args.choice)
                manifest['continuation'] = continuation
                write_json(output_path(run, 'run_manifest.json'), manifest)
                result['session_choice'] = args.choice
        print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}))
        sys.exit(1)


if __name__ == '__main__':
    main()
