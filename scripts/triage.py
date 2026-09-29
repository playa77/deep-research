#!/usr/bin/env python3
"""
Source Triage — dedupe, syndication detection, origin clustering, credibility
scoring, research-worthiness prioritization, and coverage-gap detection.

Sits between the ACQUISITION engine (which produces acquisition/) and the
EVIDENCE engine (which consumes triage/corpus.jsonl). Rationale: 200 raw
discoveries are excellent acquisition but terrible evidence input — five
articles derived from the same wire story are one source, not five.

CLI subcommands:
  dedupe    Flag exact duplicates and syndication clusters
  cluster   Assign independence groups (same origin = one group)
  score     Attach credibility scores (via source_evaluator)
  select    Compute research-worthiness and mark selected/reserve/dropped
  gaps      Compare planned angles against discovered sources
  run       Execute the full sequence; write corpus.jsonl + triage_report.md

All subcommands are deterministic and stdlib-only, so triage can be re-run
cheaply after delta-acquisition without losing decisions (re-running `run`
recomputes from scratch; overrides file preserves manual group assignments).
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citation_manager import now_iso, parse_frontmatter, read_jsonl  # noqa: E402
from source_evaluator import SourceEvaluator  # noqa: E402

# ccSLD second-level labels where the registrable domain has 3 labels
MULTI_PART_SUFFIXES = {
    'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'co.jp', 'com.au', 'com.br',
    'co.nz', 'com.mx', 'com.tr', 'com.cn',
}

ORIGIN_RANK = {'primary': 1.0, 'secondary': 0.6, 'tertiary': 0.25}

DEFAULT_MAX_SOURCES = {'quick': 15, 'standard': 40, 'deep': 70, 'ultradeep': 100}
DEFAULT_MIN_PER_ANGLE = 2

TITLE_SIMILARITY_THRESHOLD = 0.92
MIN_CREDIBILITY = 40.0     # below this: 'reserve' (verify before use)
DROP_CREDIBILITY = 20.0    # below this AND tertiary: dropped


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def registrable_domain(url: str) -> str:
    """Approximate registrable domain: last 2-3 labels of the hostname."""
    host = (urlparse_host(url) or '').lower()
    labels = [l for l in host.split('.') if l]
    if len(labels) >= 3 and '.'.join(labels[-2:]) in MULTI_PART_SUFFIXES:
        return '.'.join(labels[-3:])
    if len(labels) >= 2:
        return '.'.join(labels[-2:])
    return host


def urlparse_host(url: str) -> str:
    from urllib.parse import urlparse
    try:
        return urlparse(url).hostname or ''
    except ValueError:
        return ''


def normalize_title(title: str) -> str:
    t = (title or '').lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    for article in ('the ', 'a ', 'an '):
        if t.startswith(article):
            t = t[len(article):]
            break
    return t


def url_slug(url: str) -> str:
    from urllib.parse import urlparse
    try:
        path = urlparse(url).path
    except ValueError:
        return ''
    seg = [s for s in path.split('/') if s]
    if not seg:
        return ''
    slug = seg[-1]
    slug = re.sub(r'\.(html?|php|aspx?)$', '', slug)
    slug = re.sub(r'[^\w]+', '-', slug).strip('-').lower()
    return slug


def title_ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio()


def raw_body_text(run_dir: str, raw_file: str | None, limit: int = 8000) -> str:
    """Return normalized body text of a raw acquisition file (frontmatter stripped)."""
    if not raw_file:
        return ''
    path = os.path.join(run_dir, 'acquisition', raw_file)
    if not os.path.isfile(path):
        return ''
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read()
    except OSError:
        return ''
    # strip frontmatter
    m = re.match(r'\A---\s*\n.*?\n---\s*\n', text, re.DOTALL)
    if m:
        text = text[m.end():]
    text = text.lower()
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:limit]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def load_sources(run_dir: str) -> list[dict]:
    """Load merged sources, joining raw-file frontmatter for missing fields."""
    sources = read_jsonl(os.path.join(run_dir, 'acquisition', 'sources.jsonl'))
    for src in sources:
        if not src.get('raw_file'):
            continue
        fm = parse_frontmatter(os.path.join(run_dir, 'acquisition', src['raw_file']))
        for key in ('title', 'publisher', 'published', 'origin', 'medium', 'search_angle'):
            if not src.get(key) and fm.get(key):
                src[key] = fm[key]
    return sources


def load_plan_angles(run_dir: str) -> list[dict]:
    """Parse the ```json block of acquisition/query_plan.md for {"angles": [...]}."""
    path = os.path.join(run_dir, 'acquisition', 'query_plan.md')
    if not os.path.isfile(path):
        return []
    with open(path, encoding='utf-8') as f:
        text = f.read()
    for m in re.finditer(r'```json\s*\n(.*?)```', text, re.DOTALL):
        try:
            data = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get('angles'), list):
            return data['angles']
    return []


def load_overrides(run_dir: str) -> dict:
    path = os.path.join(run_dir, 'triage', 'overrides.json')
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_dedupe(sources: list[dict], run_dir: str) -> None:
    """Attach duplicate_of / syndication_with / content_hash flags in place."""
    by_id = {s['source_id']: s for s in sources}
    bodies = {}
    for s in sources:
        body = raw_body_text(run_dir, s.get('raw_file'))
        s['_body'] = body
        s['content_hash'] = content_hash(body) if body else None

    # 1. exact content duplicates
    by_hash: dict[str, str] = {}
    for s in sources:
        h = s.get('content_hash')
        if not h:
            continue
        if h in by_hash:
            s['duplicate_of'] = by_hash[h]
        else:
            by_hash[h] = s['source_id']

    # 2. same canonical id (raw files repeated across agents)
    seen_ids: dict[str, str] = {}
    for s in sources:
        sid = s['source_id']
        if sid in seen_ids and not s.get('duplicate_of'):
            s['duplicate_of'] = seen_ids[sid]
        else:
            seen_ids[sid] = sid

    # 3. syndication: same/similar title or same slug across different domains
    trivial = {'', 'untitled', 'home', 'news', 'article', 'blog'}
    for i, a in enumerate(sources):
        if a.get('duplicate_of') or not a.get('title') or a['title'].lower() in trivial:
            continue
        for b in sources[i + 1:]:
            if b.get('duplicate_of') or not b.get('title') or b['title'].lower() in trivial:
                continue
            if a.get('syndication_with') and a['source_id'] in (b.get('syndication_with') or []):
                continue
            if registrable_domain(a['raw_url']) == registrable_domain(b['raw_url']):
                continue  # same site handled by cluster step, not syndication
            slug_match = (
                url_slug(a['raw_url']) and url_slug(a['raw_url']) == url_slug(b['raw_url'])
            )
            title_match = title_ratio(a['title'], b['title']) >= TITLE_SIMILARITY_THRESHOLD
            if slug_match or title_match:
                a.setdefault('syndication_with', []).append(b['source_id'])
                b.setdefault('syndication_with', []).append(a['source_id'])

    # transitive syndication closure
    changed = True
    while changed:
        changed = False
        for s in sources:
            linked = set(s.get('syndication_with') or [])
            for peer_id in list(linked):
                peer = by_id.get(peer_id)
                if peer:
                    new = (peer.get('syndication_with') or set()) if isinstance(
                        peer.get('syndication_with'), set) else set(peer.get('syndication_with') or [])
                    if not new <= linked:
                        linked |= new
                        changed = True
            if linked:
                s['syndication_with'] = sorted(linked)

    for s in sources:
        s.pop('_body', None)


def step_cluster(sources: list[dict], run_dir: str) -> None:
    """Assign independence_group_id: same registrable domain or syndication
    cluster = one group. Manual overrides win."""
    overrides = load_overrides(run_dir)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_id = {s['source_id']: s for s in sources}
    for s in sources:
        find(s['source_id'])

    # same domain -> same group
    by_domain: dict[str, str] = {}
    for s in sources:
        d = registrable_domain(s.get('raw_url', ''))
        if d:
            if d in by_domain:
                union(by_domain[d], s['source_id'])
            else:
                by_domain[d] = s['source_id']

    # syndication -> same group
    for s in sources:
        for peer in s.get('syndication_with') or []:
            if peer in by_id:
                union(s['source_id'], peer)

    # collect members per root, name groups deterministically
    roots: dict[str, list[str]] = {}
    for s in sources:
        roots.setdefault(find(s['source_id']), []).append(s['source_id'])

    ordered_roots = sorted(roots.values(), key=lambda members: min(members))
    group_names: dict[str, str] = {}
    for i, members in enumerate(ordered_roots, 1):
        rep_domain = registrable_domain(
            by_id[members[0]].get('raw_url', '')) or 'group'
        name = f'G{i:03d}_{rep_domain}'
        for sid in members:
            group_names[sid] = name

    for s in sources:
        assigned = overrides.get(s['source_id']) or group_names.get(s['source_id'], 'G999_manual')
        s['independence_group_id'] = assigned


def step_score(sources: list[dict], run_dir: str) -> None:
    """Attach credibility 0-100 + recommendation via source_evaluator."""
    evaluator = SourceEvaluator()
    # bodies needed again for content-based signals
    for s in sources:
        body = raw_body_text(run_dir, s.get('raw_file'))
        result = evaluator.evaluate_source(
            url=s.get('raw_url', ''),
            title=s.get('title', ''),
            content=body or None,
            publication_date=s.get('published'),
            author=(s.get('authors') or [None])[0] if s.get('authors') else None,
        )
        s['credibility'] = round(float(result.overall_score), 1)
        s['trust_recommendation'] = result.recommendation


def step_select(sources: list[dict], run_dir: str, max_sources: int,
                min_credibility_reserve: float = MIN_CREDIBILITY) -> None:
    """Mark each source selected / reserve / dropped with a reason."""
    for s in sources:
        if s.get('duplicate_of'):
            s['triage_status'] = 'dropped'
            s['selection_reason'] = f"exact duplicate of {s['duplicate_of']}"

    # Syndication clusters (same underlying story) keep ONE representative —
    # the highest-ranked by origin, then credibility. NOTE: same-domain
    # sources without syndication lineage are NOT derivative copies; they
    # share an independence group for corroboration counting, but both stay
    # in the corpus.
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for s in sources:
        if s.get('triage_status'):
            continue
        for peer in s.get('syndication_with') or []:
            union(s['source_id'], peer)

    clusters: dict[str, list[dict]] = {}
    for s in sources:
        if s.get('triage_status'):
            continue
        clusters.setdefault(find(s['source_id']), []).append(s)
    for members in clusters.values():
        if len(members) == 1:
            continue
        members.sort(key=lambda s: (ORIGIN_RANK.get(s.get('origin') or 'secondary', 0.5),
                                    s.get('credibility') or 0), reverse=True)
        rep = members[0]
        for m in members[1:]:
            m['triage_status'] = 'dropped'
            m['selection_reason'] = (
                f"syndicated/derivative of {rep['source_id']} "
                f"(same underlying story)")

    def priority(s: dict) -> float:
        return (ORIGIN_RANK.get(s.get('origin') or 'secondary', 0.5)
                * 0.6 + (s.get('credibility') or 0) / 100.0 * 0.4)

    candidates = [s for s in sources if not s.get('triage_status')]
    candidates.sort(key=priority, reverse=True)

    selected_count = 0
    for s in candidates:
        cred = s.get('credibility', 0)
        if cred < DROP_CREDIBILITY and s.get('origin') == 'tertiary':
            s['triage_status'] = 'dropped'
            s['selection_reason'] = f'low credibility ({cred}) and tertiary origin'
            continue
        if selected_count >= max_sources:
            s['triage_status'] = 'reserve'
            s['selection_reason'] = 'corpus target reached'
            continue
        if cred < min_credibility_reserve:
            s['triage_status'] = 'reserve'
            s['selection_reason'] = f'credibility {cred} < {min_credibility_reserve}: verify before use'
            selected_count += 1
            continue
        s['triage_status'] = 'selected'
        s['selection_reason'] = (
            f"origin={s.get('origin')}, credibility={cred}, "
            f"angle={s.get('search_angle') or 'unassigned'}")
        selected_count += 1


def step_gaps(sources: list[dict], run_dir: str,
              min_per_angle: int = DEFAULT_MIN_PER_ANGLE) -> list[dict]:
    """Return gap list: planned angles with too few selected sources."""
    selected = [s for s in sources if s.get('triage_status') == 'selected']
    per_angle: dict[str, int] = {}
    for s in selected:
        angle = s.get('search_angle') or 'unassigned'
        per_angle[angle] = per_angle.get(angle, 0) + 1

    gaps = []
    for angle in load_plan_angles(run_dir):
        name = angle.get('name') or angle.get('id') or 'unnamed'
        count = per_angle.get(name, 0)
        if count == 0:
            gaps.append({'angle': name, 'selected_sources': 0, 'severity': 'uncovered'})
        elif count < min_per_angle:
            gaps.append({'angle': name, 'selected_sources': count,
                         'severity': 'undercovered', 'minimum': min_per_angle})
    return gaps


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(sources: list[dict], gaps: list[dict], run_dir: str,
                 max_sources: int) -> str:
    selected = [s for s in sources if s.get('triage_status') == 'selected']
    reserve = [s for s in sources if s.get('triage_status') == 'reserve']
    dropped = [s for s in sources if s.get('triage_status') == 'dropped']
    groups: dict[str, int] = {}
    for s in selected:
        groups[s['independence_group_id']] = groups.get(s['independence_group_id'], 0) + 1

    lines = [
        '# Source Triage Report', '',
        f'Generated: {now_iso()}', '',
        '## Totals', '',
        f'- Discovered (merged): **{len(sources)}**',
        f'- Selected for evidence work: **{len(selected)}** (target ≤ {max_sources})',
        f'- Reserve (verify before use): **{len(reserve)}**',
        f'- Dropped: **{len(dropped)}**',
        f'- Independence groups among selected: **{len(groups)}**', '',
        '## Duplication & Syndication', '',
    ]
    dupes = [s for s in sources if s.get('duplicate_of')]
    synd = [s for s in sources if s.get('syndication_with') and not s.get('duplicate_of')]
    lines.append(f'- Exact duplicates: {len(dupes)}')
    for s in dupes:
        lines.append(f'  - {s["source_id"]} ({s.get("title", "")[:60]}) → {s["duplicate_of"]}')
    lines.append(f'- Syndication clusters: {len(synd)} sources share origin material')
    for s in synd[:20]:
        lines.append(f'  - {s["source_id"]} ({s.get("title", "")[:60]}) ↔ {", ".join(s["syndication_with"])}')
    lines += ['', '## Independence Groups (selected)', '']
    for gid, count in sorted(groups.items(), key=lambda kv: -kv[1]):
        lines.append(f'- {gid}: {count} source(s)')
    lines += ['', '## Coverage Gaps', '']
    if not gaps:
        lines.append('None — every planned angle has selected sources.')
    else:
        for g in gaps:
            if g['severity'] == 'uncovered':
                lines.append(f'- **UNCOVERED**: {g["angle"]} — no selected sources; delta-acquisition required')
            else:
                lines.append(f'- **UNDERCOVERED**: {g["angle"]} — {g["selected_sources"]} selected (min {g.get("minimum", 2)})')
    lines += ['', '## Decisions', '',
              '| source_id | title | origin | cred | group | status | reason |',
              '|---|---|---|---|---|---|---|']
    for s in sorted(sources, key=lambda x: x.get('source_id', '')):
        lines.append(
            f'| {s["source_id"][:8]}… | {(s.get("title") or "")[:40]} '
            f'| {s.get("origin", "?")} | {s.get("credibility", "?")} '
            f'| {s.get("independence_group_id", "?")} | {s.get("triage_status", "?")} '
            f'| {(s.get("selection_reason") or "")[:50]} |')
    lines.append('')

    out = os.path.join(run_dir, 'triage', 'triage_report.md')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_triage(run_dir: str, mode: str, max_sources: int | None,
               min_per_angle: int) -> dict:
    sources = load_sources(run_dir)
    step_dedupe(sources, run_dir)
    step_cluster(sources, run_dir)
    step_score(sources, run_dir)
    cap = max_sources or DEFAULT_MAX_SOURCES.get(mode, 40)
    step_select(sources, run_dir, cap)
    gaps = step_gaps(sources, run_dir, min_per_angle)

    # write corpus (all sources with triage fields, selected first)
    corpus_path = os.path.join(run_dir, 'triage', 'corpus.jsonl')
    os.makedirs(os.path.dirname(corpus_path), exist_ok=True)
    order = {'selected': 0, 'reserve': 1, 'dropped': 2}
    sources.sort(key=lambda s: (
        order.get(s.get('triage_status') or '', 3),
        -(ORIGIN_RANK.get(s.get('origin') or 'secondary', 0.5)),
        -(s.get('credibility') or 0)))
    with open(corpus_path, 'w', encoding='utf-8') as f:
        for s in sources:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    report_path = write_report(sources, gaps, run_dir, cap)

    counts = {'selected': 0, 'reserve': 0, 'dropped': 0}
    for s in sources:
        st = s.get('triage_status')
        if st in counts:
            counts[st] += 1
    return {
        'status': 'ok', 'discovered': len(sources), 'counts': counts,
        'gaps': gaps, 'corpus': corpus_path, 'report': report_path,
        'max_sources': cap,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='triage',
        description='Source triage between acquisition and evidence phases')
    sub = parser.add_subparsers(dest='command', required=True)

    for name, help_txt in [
        ('dedupe', 'Flag duplicates and syndication'),
        ('cluster', 'Assign independence groups'),
        ('score', 'Attach credibility scores'),
        ('select', 'Mark selected/reserve/dropped'),
        ('gaps', 'Detect coverage gaps vs plan'),
    ]:
        p = sub.add_parser(name, help=help_txt)
        p.add_argument('--run-dir', required=True)

    p_run = sub.add_parser('run', help='Full triage: dedupe→cluster→score→select→gaps')
    p_run.add_argument('--run-dir', required=True)
    p_run.add_argument('--mode', default='standard',
                       choices=['quick', 'standard', 'deep', 'ultradeep'])
    p_run.add_argument('--max-sources', type=int, default=None,
                       help='Override corpus target for the mode')
    p_run.add_argument('--min-per-angle', type=int, default=DEFAULT_MIN_PER_ANGLE)

    args = parser.parse_args()

    if args.command == 'run':
        result = run_triage(args.run_dir, args.mode, args.max_sources, args.min_per_angle)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result['gaps']:
            sys.exit(2)  # signal: gaps need delta-acquisition
        return

    # single-step subcommands (print resulting rows for inspection)
    sources = load_sources(args.run_dir)
    if args.command == 'dedupe':
        step_dedupe(sources, args.run_dir)
    elif args.command == 'cluster':
        step_dedupe(sources, args.run_dir)
        step_cluster(sources, args.run_dir)
    elif args.command == 'score':
        step_score(sources, args.run_dir)
    elif args.command == 'select':
        step_dedupe(sources, args.run_dir)
        step_cluster(sources, args.run_dir)
        step_score(sources, args.run_dir)
        step_select(sources, args.run_dir, DEFAULT_MAX_SOURCES['standard'])
    elif args.command == 'gaps':
        print(json.dumps(step_gaps(sources, args.run_dir), indent=2))
        return
    for s in sources:
        print(json.dumps({k: v for k, v in s.items() if not k.startswith('_')},
                         ensure_ascii=False))


if __name__ == '__main__':
    main()
