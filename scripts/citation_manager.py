#!/usr/bin/env python3
"""
Citation Manager — stable source identity, acquisition-bundle merging, and
run manifest management for the merged deep-research pipeline.

Pipeline layout created by `init-run`:

  <run_dir>/
    run_manifest.json
    acquisition/
      query_plan.md          # plan output (angles, queries, budgets)
      query_log.jsonl        # every search executed (merged from agents)
      sources.jsonl          # source registry (merged from agents)
      leads.jsonl            # new search leads surfaced during acquisition
      raw/                   # one markdown file per fetched source
      agents/                # per-agent fragments (*.sources.jsonl, *.queries.jsonl)
    triage/
      triage_report.md
      corpus.jsonl           # curated corpus (the evidence engine's input)
    evidence/
      evidence.jsonl         # append-only evidence rows
      claims.jsonl           # atomic claim ledger
    report/
      report.md
    qa/
      qa_report.md

CLI subcommands:
  init-run                  Create run dir skeleton + run_manifest.json + empty artifacts
  register-source           Append a source to sources.jsonl, return source_id
  merge-sources             Merge agents/*.sources.jsonl fragments into acquisition/sources.jsonl
  merge-query-log           Merge agents/*.queries.jsonl fragments into acquisition/query_log.jsonl
  build-source-map          Write acquisition/source_map.json (angles, raw files, agents)
  assign-display-numbers    Map stable source_ids to [1], [2], ... display numbers
  export-bibliography       Render bibliography from the curated corpus

Source identity (from 199-biotechnologies):
  source_id = sha256(canonical_locator)[:16]
  canonical_locator = doi:..., arxiv:..., or normalized URL (scheme+host+path,
  no fragment, no tracking params)

All state is append-only JSONL. No mutable citation numbers in state files.
Display numbers are derived at render time from the curated corpus.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

PIPELINE_VERSION = '1.0.0'

# Valid enum values (mirrored in schemas/*.json)
ORIGINS = ('primary', 'secondary', 'tertiary')
MEDIUMS = ('web', 'academic', 'documentation', 'code', 'news', 'government', 'book')

FRONTMATTER_RE = re.compile(r'\A---\s*\n(.*?)\n---\s*\n', re.DOTALL)


# ---------------------------------------------------------------------------
# Canonical locator normalization
# ---------------------------------------------------------------------------

DOI_RE = re.compile(r'(?:https?://(?:dx\.)?doi\.org/|doi:)(10\.\d{4,}/\S+)', re.IGNORECASE)
ARXIV_RE = re.compile(r'(?:https?://arxiv\.org/abs/|arxiv:)(\d{4}\.\d{4,}(?:v\d+)?)', re.IGNORECASE)

# URL query params that are tracking noise, not content identifiers
TRACKING_PARAMS = frozenset([
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'ref', 'source', 'fbclid', 'gclid', 'mc_cid', 'mc_eid',
])


def canonicalize_locator(raw_url: str) -> str:
    """Derive a canonical locator from a raw URL or identifier string.

    Priority: DOI > arXiv > normalized URL.
    """
    # DOI
    m = DOI_RE.search(raw_url)
    if m:
        return f'doi:{m.group(1).rstrip(".")}'

    # arXiv
    m = ARXIV_RE.search(raw_url)
    if m:
        return f'arxiv:{m.group(1)}'

    # Normalized URL: lowercase scheme+host, strip fragment and tracking params
    parsed = urlparse(raw_url)
    scheme = (parsed.scheme or 'https').lower()
    host = (parsed.hostname or '').lower()
    path = parsed.path.rstrip('/')
    # Filter query params
    if parsed.query:
        pairs = []
        for part in parsed.query.split('&'):
            kv = part.split('=', 1)
            if kv[0].lower() not in TRACKING_PARAMS:
                pairs.append(part)
        query = '&'.join(sorted(pairs))
    else:
        query = ''
    return urlunparse((scheme, host, path, '', query, ''))


def compute_source_id(canonical_locator: str) -> str:
    """sha256(canonical_locator)[:16] hex."""
    return hashlib.sha256(canonical_locator.encode('utf-8')).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSONL / frontmatter helpers
# ---------------------------------------------------------------------------

def append_jsonl(path: str, obj: dict) -> None:
    with open(path, 'a') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')


def read_jsonl(path: str) -> list[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_frontmatter(path: str) -> dict:
    """Parse a simple YAML-ish frontmatter block (key: value lines)."""
    try:
        with open(path, encoding='utf-8') as f:
            m = FRONTMATTER_RE.match(f.read())
    except OSError:
        return {}
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ':' not in line or line.lstrip().startswith('#'):
            continue
        key, _, val = line.partition(':')
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_source_record(data: dict, registered_at: str | None = None) -> tuple[dict, str]:
    """Build a normalized source record from raw input fields.

    Returns (record, canonical_locator).
    """
    raw_url = data.get('raw_url', data.get('url', ''))
    if not raw_url:
        raise ValueError('raw_url is required')
    canonical = data.get('canonical_locator') or canonicalize_locator(raw_url)
    source_id = compute_source_id(canonical)

    # `source_type` (199-biotech legacy name) maps onto `medium`.
    medium = data.get('medium') or data.get('source_type') or 'web'
    if medium not in MEDIUMS:
        medium = 'web'
    origin = data.get('origin') or 'secondary'
    if origin not in ORIGINS:
        origin = 'secondary'

    record = {
        'source_id': source_id,
        'canonical_locator': canonical,
        'raw_url': raw_url,
        'title': data.get('title', ''),
        'authors': data.get('authors'),
        'year': data.get('year'),
        'publisher': data.get('publisher'),
        'published': data.get('published'),
        'retrieved': data.get('retrieved'),
        'origin': origin,
        'medium': medium,
        'metadata_status': data.get('metadata_status', 'unverified'),
        'search_angle': data.get('search_angle'),
        'discovered_by': data.get('discovered_by'),
        'raw_file': data.get('raw_file'),
        'registered_at': registered_at or now_iso(),
    }
    return record, canonical


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_init_run(args: argparse.Namespace) -> None:
    """Create run dir skeleton, run_manifest.json, and empty artifact files."""
    out_dir = os.path.abspath(args.out_dir)
    for sub in ('acquisition/raw', 'acquisition/agents', 'triage', 'evidence', 'report', 'qa'):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)

    artifact_paths = {
        'query_plan': 'acquisition/query_plan.md',
        'query_log': 'acquisition/query_log.jsonl',
        'sources': 'acquisition/sources.jsonl',
        'leads': 'acquisition/leads.jsonl',
        'raw_dir': 'acquisition/raw',
        'corpus': 'triage/corpus.jsonl',
        'triage_report': 'triage/triage_report.md',
        'evidence': 'evidence/evidence.jsonl',
        'claims': 'evidence/claims.jsonl',
        'report': 'report/report.md',
        'qa_report': 'qa/qa_report.md',
    }

    manifest = {
        'version': PIPELINE_VERSION,
        'query': args.query or '',
        'mode': args.mode,
        'started_at': now_iso(),
        'finished_at': None,
        'assumptions': [],
        'provider_config': {
            'primary': 'web_search',
            'scholarly': None,
        },
        'report_dir': out_dir,
        'artifact_paths': artifact_paths,
        'phases_completed': [],
        'continuation': None,
    }

    manifest_path = os.path.join(out_dir, 'run_manifest.json')
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write('\n')

    # Create empty JSONL artifacts
    for name in ('query_log', 'sources', 'leads', 'evidence', 'claims'):
        p = os.path.join(out_dir, artifact_paths[name])
        if not os.path.exists(p):
            open(p, 'w').close()

    print(json.dumps({'status': 'ok', 'manifest': manifest_path, 'dir': out_dir}))


def cmd_register_source(args: argparse.Namespace) -> None:
    """Register a source, append to sources.jsonl, print source_id."""
    data = json.loads(args.json)
    sources_path = os.path.join(args.dir, 'sources.jsonl')
    _register_into(sources_path, data)


def _register_into(sources_path: str, data: dict) -> None:
    try:
        record, canonical = _make_source_record(data)
    except ValueError as e:
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        sys.exit(1)

    # Duplicate check by canonical identity
    for row in read_jsonl(sources_path):
        if row.get('source_id') == record['source_id']:
            print(json.dumps({
                'status': 'duplicate',
                'source_id': record['source_id'],
                'canonical_locator': canonical,
            }))
            return

    append_jsonl(sources_path, record)
    print(json.dumps({
        'status': 'registered',
        'source_id': record['source_id'],
        'canonical_locator': canonical,
    }))


def _fragment_files(agents_dir: str, suffix: str) -> list[str]:
    if not os.path.isdir(agents_dir):
        return []
    return sorted(
        os.path.join(agents_dir, f) for f in os.listdir(agents_dir)
        if f.endswith(suffix)
    )


def cmd_merge_sources(args: argparse.Namespace) -> None:
    """Merge agents/*.sources.jsonl fragments into acquisition/sources.jsonl.

    Dedupe by canonical source_id; first fragment to discover a source wins
    `discovered_by`, later discoverers recorded in `also_found_by`.
    """
    acq_dir = os.path.abspath(args.acq_dir)
    sources_path = os.path.join(acq_dir, 'sources.jsonl')
    agents_dir = os.path.join(acq_dir, 'agents')

    existing_ids = {row.get('source_id') for row in read_jsonl(sources_path)}
    added = 0
    skipped = 0
    malformed = 0

    for frag in _fragment_files(agents_dir, '.sources.jsonl'):
        agent = os.path.basename(frag).replace('.sources.jsonl', '')
        for row in read_jsonl(frag):
            data = dict(row)
            data.setdefault('discovered_by', agent)
            try:
                record, _ = _make_source_record(data)
            except (ValueError, AttributeError):
                malformed += 1
                continue
            if record['source_id'] in existing_ids:
                skipped += 1
                continue
            append_jsonl(sources_path, record)
            existing_ids.add(record['source_id'])
            added += 1

    print(json.dumps({
        'status': 'ok', 'added': added, 'skipped_duplicates': skipped,
        'malformed_rows': malformed, 'sources_path': sources_path,
    }))


def cmd_merge_query_log(args: argparse.Namespace) -> None:
    """Merge agents/*.queries.jsonl fragments into acquisition/query_log.jsonl."""
    acq_dir = os.path.abspath(args.acq_dir)
    log_path = os.path.join(acq_dir, 'query_log.jsonl')
    agents_dir = os.path.join(acq_dir, 'agents')

    existing = read_jsonl(log_path)
    seen = {(r.get('agent'), r.get('query_text'), r.get('tool')) for r in existing}
    added = 0
    skipped = 0

    for frag in _fragment_files(agents_dir, '.queries.jsonl'):
        agent = os.path.basename(frag).replace('.queries.jsonl', '')
        for row in read_jsonl(frag):
            q = dict(row)
            q.setdefault('agent', agent)
            key = (q.get('agent'), q.get('query_text'), q.get('tool'))
            if key in seen:
                skipped += 1
                continue
            if not q.get('query_id'):
                q['query_id'] = 'q_' + hashlib.sha1(
                    f"{q.get('agent')}|{q.get('query_text')}|{q.get('tool')}".encode()
                ).hexdigest()[:10]
            if not q.get('ts'):
                q['ts'] = now_iso()
            append_jsonl(log_path, q)
            seen.add(key)
            added += 1

    print(json.dumps({
        'status': 'ok', 'added': added, 'skipped_duplicates': skipped,
        'query_log_path': log_path,
    }))


def cmd_build_source_map(args: argparse.Namespace) -> None:
    """Write acquisition/source_map.json: angles, raw files, agent stats."""
    acq_dir = os.path.abspath(args.acq_dir)
    sources = read_jsonl(os.path.join(acq_dir, 'sources.jsonl'))
    queries = read_jsonl(os.path.join(acq_dir, 'query_log.jsonl'))

    raw_dir = os.path.join(acq_dir, 'raw')
    raw_files = {}
    if os.path.isdir(raw_dir):
        for fname in sorted(os.listdir(raw_dir)):
            if not fname.endswith('.md'):
                continue
            fm = parse_frontmatter(os.path.join(raw_dir, fname))
            if fm.get('source_id'):
                raw_files[f'raw/{fname}'] = {
                    'source_id': fm['source_id'],
                    'title': fm.get('title', ''),
                    'search_angle': fm.get('search_angle', ''),
                }

    angles: dict[str, dict] = {}
    for src in sources:
        angle = src.get('search_angle') or 'unassigned'
        entry = angles.setdefault(angle, {'source_count': 0, 'source_ids': []})
        entry['source_count'] += 1
        entry['source_ids'].append(src['source_id'])

    agents: dict[str, dict] = {}
    for src in sources:
        a = src.get('discovered_by') or 'unknown'
        agents.setdefault(a, {'sources_discovered': 0, 'queries': 0})
        agents[a]['sources_discovered'] += 1
    for q in queries:
        a = q.get('agent') or 'unknown'
        agents.setdefault(a, {'sources_discovered': 0, 'queries': 0})
        agents[a]['queries'] += 1

    source_map = {
        'generated_at': now_iso(),
        'totals': {
            'sources': len(sources),
            'queries': len(queries),
            'raw_files': len(raw_files),
            'angles': len(angles),
        },
        'angles': angles,
        'raw_files': raw_files,
        'agents': agents,
    }
    out_path = os.path.join(acq_dir, 'source_map.json')
    with open(out_path, 'w') as f:
        json.dump(source_map, f, indent=2, ensure_ascii=False)
        f.write('\n')
    print(json.dumps({'status': 'ok', 'source_map': out_path, 'totals': source_map['totals']}))


def _resolve_sources_path(run_dir: str, explicit: str | None) -> str:
    """Order: --sources flag > triage/corpus.jsonl > acquisition/sources.jsonl > flat."""
    if explicit:
        return os.path.abspath(explicit)
    candidates = [
        os.path.join(run_dir, 'triage', 'corpus.jsonl'),
        os.path.join(run_dir, 'acquisition', 'sources.jsonl'),
        os.path.join(run_dir, 'sources.jsonl'),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    # Default to curated corpus path (may not exist yet — caller will error)
    return candidates[0]


def _dedup_sources(sources: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for src in sources:
        if src.get('source_id') not in seen:
            seen.add(src.get('source_id'))
            unique.append(src)
    return unique


def _curated_rows(sources: list[dict]) -> list[dict]:
    """Rows eligible for citation numbering: everything except corpus rows
    triage dropped. Files without triage_status (raw acquisition registry)
    pass through unchanged."""
    return [s for s in sources if s.get('triage_status') != 'dropped']


def cmd_assign_display_numbers(args: argparse.Namespace) -> None:
    """Read the curated corpus, assign stable display numbers in order."""
    sources_path = _resolve_sources_path(args.dir, args.sources)
    sources = _curated_rows(_dedup_sources(read_jsonl(sources_path)))

    mapping = {}
    for i, src in enumerate(sources, 1):
        sid = src.get('source_id')
        if sid and sid not in mapping:
            mapping[sid] = i

    print(json.dumps(mapping, indent=2))


def cmd_export_bibliography(args: argparse.Namespace) -> None:
    """Generate bibliography from the curated corpus."""
    sources_path = _resolve_sources_path(args.dir, args.sources)
    sources = _curated_rows(_dedup_sources(read_jsonl(sources_path)))

    style = args.style

    if style == 'markdown':
        lines = ['## Bibliography', '']
        for i, src in enumerate(sources, 1):
            author_str = ''
            if src.get('authors'):
                authors = src['authors']
                if len(authors) == 1:
                    author_str = f'{authors[0]}. '
                elif len(authors) == 2:
                    author_str = f'{authors[0]} & {authors[1]}. '
                else:
                    author_str = f'{authors[0]} et al. '

            year_str = f'({src["year"]})' if src.get('year') else '(n.d.)'
            title = src.get('title', 'Untitled')
            url = src.get('raw_url', '')
            lines.append(f'[{i}] {author_str}{year_str}. [{title}]({url})')
        print('\n'.join(lines))

    elif style == 'json':
        out = []
        for i, src in enumerate(sources, 1):
            out.append({
                'display_number': i,
                'source_id': src.get('source_id'),
                'canonical_locator': src.get('canonical_locator'),
                'title': src.get('title', ''),
                'authors': src.get('authors'),
                'year': src.get('year'),
                'publisher': src.get('publisher'),
                'origin': src.get('origin'),
                'raw_url': src.get('raw_url', ''),
            })
        print(json.dumps(out, indent=2, ensure_ascii=False))

    else:
        print(f'Unknown style: {style}', file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='citation_manager',
        description='Stable source identity, bundle merging, and manifest management '
                    'for the merged deep-research pipeline',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    # init-run
    p_init = sub.add_parser('init-run', help='Create run dir skeleton and run manifest')
    p_init.add_argument('--out-dir', required=True, help='Output directory for the research run')
    p_init.add_argument('--query', default='', help='Original research question')
    p_init.add_argument('--mode', default='standard', choices=['quick', 'standard', 'deep', 'ultradeep'])

    # register-source
    p_reg = sub.add_parser('register-source', help='Register a source and return its stable ID')
    p_reg.add_argument('--json', required=True, help='JSON object with at least raw_url and title')
    p_reg.add_argument('--dir', required=True, help='Directory containing sources.jsonl (usually acquisition/)')

    # merge-sources
    p_ms = sub.add_parser('merge-sources', help='Merge agents/*.sources.jsonl into acquisition/sources.jsonl')
    p_ms.add_argument('--acq-dir', required=True, help='The acquisition/ directory of the run')

    # merge-query-log
    p_mq = sub.add_parser('merge-query-log', help='Merge agents/*.queries.jsonl into acquisition/query_log.jsonl')
    p_mq.add_argument('--acq-dir', required=True, help='The acquisition/ directory of the run')

    # build-source-map
    p_sm = sub.add_parser('build-source-map', help='Write acquisition/source_map.json')
    p_sm.add_argument('--acq-dir', required=True, help='The acquisition/ directory of the run')

    # assign-display-numbers
    p_num = sub.add_parser('assign-display-numbers', help='Map stable source IDs to display numbers')
    p_num.add_argument('--dir', required=True, help='Run directory')
    p_num.add_argument('--sources', default=None, help='Explicit sources JSONL (default: curated corpus)')

    # export-bibliography
    p_bib = sub.add_parser('export-bibliography', help='Generate bibliography from curated corpus')
    p_bib.add_argument('--dir', required=True, help='Run directory')
    p_bib.add_argument('--sources', default=None, help='Explicit sources JSONL (default: curated corpus)')
    p_bib.add_argument('--style', default='markdown', choices=['markdown', 'json'])

    args = parser.parse_args()

    dispatch = {
        'init-run': cmd_init_run,
        'register-source': cmd_register_source,
        'merge-sources': cmd_merge_sources,
        'merge-query-log': cmd_merge_query_log,
        'build-source-map': cmd_build_source_map,
        'assign-display-numbers': cmd_assign_display_numbers,
        'export-bibliography': cmd_export_bibliography,
    }
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
