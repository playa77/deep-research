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
  gaps      Compare planned angles against freshly selected sources
  run       Execute the full sequence; write corpus, report, and JSON result

All subcommands are deterministic and local (review schemas use jsonschema),
so triage can be re-run
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


def raw_body_text(run_dir: str, raw_file: str | None, limit: int | None = 8000, normalize: bool = True) -> str:
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
    if normalize:
        text = re.sub(r'\s+', ' ', text.lower()).strip()
    return text[:limit]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


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


def plan_angle_aliases(run_dir: str) -> dict[str, str]:
    """Resolve either a planned angle's ID or its name to the display name."""
    angles = load_plan_angles(run_dir)
    aliases = {a.get('name') or a.get('id') or 'unnamed':
               a.get('name') or a.get('id') or 'unnamed' for a in angles}
    for angle in angles:
        if angle.get('id'):
            aliases.setdefault(angle['id'], angle.get('name') or angle['id'])
    return aliases


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step_dedupe(sources: list[dict], run_dir: str) -> None:
    """Only full, substantive content equality can remove a source.

    Titles, URL slugs and near-duplicate bodies are review leads, never proof
    that publishers share an origin. No transitive closure of guesses.
    """
    bodies = {}
    for source in sources:
        for key in ('duplicate_of', 'syndication_with', 'lineage_with',
                    'similarity_candidates', 'triage_status', 'selection_reason'):
            source.pop(key, None)
        body = raw_body_text(run_dir, source.get('raw_file'), limit=None, normalize=False)
        bodies[source['source_id']] = body
        source['content_hash'] = content_hash(body) if body else None

    if len(bodies) != len(sources):
        raise ValueError('duplicate source IDs; repair merged acquisition before triage')
    by_hash = {}
    # Prefer original material as representative, with a stable tie-break.
    for source in sorted(sources, key=lambda s: (
            -ORIGIN_RANK.get(s.get('origin'), 0.5), s['source_id'])):
        body = bodies[source['source_id']]
        # Identical access-denied messages and short snippets are not documents.
        if len(body) < 200 or len(body.split()) < 40:
            continue
        if body in by_hash:
            source['duplicate_of'] = by_hash[body]
        else:
            by_hash[body] = source['source_id']

    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            if a.get('duplicate_of') or b.get('duplicate_of'):
                continue
            if registrable_domain(a['raw_url']) == registrable_domain(b['raw_url']):
                continue
            title_match = (normalize_title(a.get('title', '')) and
                           title_ratio(a.get('title', ''), b.get('title', '')) >= TITLE_SIMILARITY_THRESHOLD)
            slug_match = url_slug(a['raw_url']) and url_slug(a['raw_url']) == url_slug(b['raw_url'])
            if title_match or slug_match:
                a.setdefault('similarity_candidates', []).append(b['source_id'])
                b.setdefault('similarity_candidates', []).append(a['source_id'])

    # Optional substantive lineage review, bound to the exact extracted files.
    from pathlib import Path
    from fact_check import inside, load_json, sha, validate_schema, require
    run = Path(run_dir).resolve()
    path = run / 'triage/lineage.json'
    if path.exists():
        reviews = load_json(inside(run, 'triage/lineage.json'))
        validate_schema(reviews, 'lineage.schema.json')
        by_id = {s['source_id']: s for s in sources}
        seen_pairs = set()
        for review in reviews:
            ids = review['source_ids']
            pair = tuple(sorted(ids))
            require(pair not in seen_pairs, 'duplicate/conflicting lineage review')
            seen_pairs.add(pair)
            require(ids[0] != ids[1] and set(ids) <= by_id.keys(), 'unknown/self lineage link')
            for sid in ids:
                raw = inside(run, 'acquisition/' + by_id[sid]['raw_file']).read_bytes()
                require(sid in review['raw_sha256'] and sid in review['passages'],
                        f'{sid}: incomplete lineage review')
                require(sha(raw) == review['raw_sha256'][sid], f'{sid}: stale lineage review')
                text = raw.decode('utf-8')
                frontmatter = re.match(r'\A---\s*\n.*?\n---\s*\n', text, re.DOTALL)
                body = text[frontmatter.end():] if frontmatter else text
                require(review['passages'][sid] in body,
                        f'{sid}: lineage passage missing from source body')
            if review['relation'] == 'shared_origin':
                for sid, peer in ((ids[0], ids[1]), (ids[1], ids[0])):
                    by_id[sid].setdefault('lineage_with', []).append(peer)


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

    # Reviewed lineage and exact duplicate content -> same group
    for s in sources:
        for peer in (s.get('lineage_with') or []) + ([s['duplicate_of']] if s.get('duplicate_of') else []):
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
                min_credibility_reserve: float = MIN_CREDIBILITY,
                min_per_angle: int = DEFAULT_MIN_PER_ANGLE) -> None:
    """Cover planned angles with eligible sources, then fill by global rank."""
    if max_sources < 1 or min_per_angle < 1:
        raise ValueError('max_sources and min_per_angle must be positive')
    for s in sources:
        if s.get('duplicate_of'):
            s['triage_status'] = 'dropped'
            s['selection_reason'] = f"exact duplicate of {s['duplicate_of']}"

    # Shared origin affects corroboration counting, not whether a document
    # contains useful or unique evidence. Keep nonidentical derivatives.

    def priority(s: dict) -> float:
        return (ORIGIN_RANK.get(s.get('origin') or 'secondary', 0.5)
                * 0.6 + (s.get('credibility') or 0) / 100.0 * 0.4)

    candidates = [s for s in sources if not s.get('triage_status')]
    candidates.sort(key=priority, reverse=True)

    eligible = []
    for s in candidates:
        cred = s.get('credibility', 0)
        if cred < DROP_CREDIBILITY and s.get('origin') == 'tertiary':
            s['triage_status'] = 'dropped'
            s['selection_reason'] = f'low credibility ({cred}) and tertiary origin'
            continue
        if cred < min_credibility_reserve:
            s['triage_status'] = 'reserve'
            s['selection_reason'] = f'credibility {cred} < {min_credibility_reserve}: verify before use'
            continue
        eligible.append(s)

    # Allocate one source per planned angle before allocating a second. Within
    # each round, ranking breaks ties if the cap cannot cover every angle.
    # Reserve rows never consume selected capacity or satisfy coverage quotas.
    aliases = plan_angle_aliases(run_dir)
    per_angle: dict[str, list[dict]] = {}
    for s in eligible:
        angle = aliases.get(s.get('search_angle'))
        if angle:
            per_angle.setdefault(angle, []).append(s)
    chosen: set[str] = set()
    rounds = min(min_per_angle, max((len(rows) for rows in per_angle.values()), default=0))
    for i in range(rounds):
        round_candidates = [rows[i] for rows in per_angle.values() if len(rows) > i]
        for s in sorted(round_candidates, key=priority, reverse=True):
            if len(chosen) >= max_sources:
                break
            chosen.add(s['source_id'])
        if len(chosen) >= max_sources:
            break
    coverage_chosen = set(chosen)
    for s in eligible:
        if len(chosen) >= max_sources:
            break
        chosen.add(s['source_id'])

    for s in eligible:
        if s['source_id'] not in chosen:
            s['triage_status'] = 'reserve'
            s['selection_reason'] = 'corpus target reached'
            continue
        s['triage_status'] = 'selected'
        s['selection_reason'] = (
            f"origin={s.get('origin')}, credibility={s.get('credibility', 0)}, "
            f"angle={s.get('search_angle') or 'unassigned'}")
        if s['source_id'] in coverage_chosen:
            s['selection_reason'] += '; planned-angle minimum'


def step_gaps(sources: list[dict], run_dir: str,
              min_per_angle: int = DEFAULT_MIN_PER_ANGLE) -> list[dict]:
    """Distinguish genuine acquisition shortfalls from corpus-cap constraints."""
    aliases = plan_angle_aliases(run_dir)
    per_angle: dict[str, list[dict]] = {}
    for s in sources:
        angle = s.get('search_angle') or 'unassigned'
        per_angle.setdefault(aliases.get(angle, angle), []).append(s)

    gaps = []
    for name in dict.fromkeys(aliases.values()):
        rows = per_angle.get(name, [])
        count = sum(s.get('triage_status') == 'selected' for s in rows)
        if count >= min_per_angle:
            continue
        eligible = count + sum(s.get('triage_status') == 'reserve'
                               and s.get('selection_reason') == 'corpus target reached'
                               for s in rows)
        cap_limited = eligible >= min_per_angle
        gaps.append({
            'angle': name, 'selected_sources': count,
            'severity': 'uncovered' if count == 0 else 'undercovered',
            'minimum': min_per_angle, 'deficit': min_per_angle - count,
            'eligible_sources': eligible,
            'reserve_sources': sum(s.get('triage_status') == 'reserve' for s in rows),
            'dropped_sources': sum(s.get('triage_status') == 'dropped' for s in rows),
            'additional_sources_needed': max(0, min_per_angle - eligible),
            'cause': 'corpus_cap' if cap_limited else 'insufficient_eligible_sources',
            'next_action': 'review_corpus_cap' if cap_limited else 'delta_acquisition',
        })
    return gaps


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def write_report(sources: list[dict], gaps: list[dict], run_dir: str,
                 max_sources: int, min_per_angle: int = DEFAULT_MIN_PER_ANGLE) -> str:
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
    synd = [s for s in sources if s.get('lineage_with')]
    candidates = [s for s in sources if s.get('similarity_candidates')]
    lines.append(f'- Exact duplicates: {len(dupes)}')
    for s in dupes:
        lines.append(f'  - {s["source_id"]} ({s.get("title", "")[:60]}) → {s["duplicate_of"]}')
    lines.append(f'- Reviewed shared-origin links: {len(synd)} sources')
    lines.append(f'- Title/slug similarity leads: {len(candidates)} sources (no deletion or group merge)')
    for s in synd[:20]:
        lines.append(f'  - {s["source_id"]} ({s.get("title", "")[:60]}) ↔ {", ".join(s["lineage_with"])}')
    lines += ['', '## Independence Groups (selected)', '']
    for gid, count in sorted(groups.items(), key=lambda kv: -kv[1]):
        lines.append(f'- {gid}: {count} source(s)')
    lines += ['', '## Coverage Gaps', '']
    required = len(set(plan_angle_aliases(run_dir).values())) * min_per_angle
    if required > max_sources:
        lines.append(f'Capacity constraint: {required} selected slots are needed for all planned minima, but the cap is {max_sources}. Review the cap against the agreed scope before delta-acquisition; do not lower coverage or quality requirements to clear the gate.')
        lines.append('')
    if not gaps:
        lines.append('None — every planned angle meets minimum selected-source coverage.')
    else:
        for g in gaps:
            if g['severity'] == 'uncovered':
                lines.append(f'- **UNCOVERED**: {g["angle"]} — no selected sources (min {g["minimum"]})')
            else:
                lines.append(f'- **UNDERCOVERED**: {g["angle"]} — {g["selected_sources"]} selected (min {g.get("minimum", 2)})')
            lines.append(f'  - Eligible: {g["eligible_sources"]}; reserve: {g["reserve_sources"]}; dropped: {g["dropped_sources"]}.')
            if g['next_action'] == 'review_corpus_cap':
                lines.append('  - Review the corpus cap against the agreed scope: enough eligible sources already exist; additional searches cannot resolve this capacity constraint.')
            else:
                lines.append(f'  - Delta-acquisition target: {g["additional_sources_needed"]} additional eligible source(s), within the single bounded wave budget.')
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
    from pathlib import Path
    from fact_check import output_path, require
    result_path = output_path(Path(run_dir).resolve(), 'triage/triage_result.json')
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps({'status': 'blocked', 'error': 'triage has not completed'}) + '\n')
    if not load_plan_angles(run_dir):
        raise ValueError('missing or empty planned angles; coverage cannot be assessed')
    input_digest = triage_input_digest(run_dir)
    sources = load_sources(run_dir)
    step_dedupe(sources, run_dir)
    step_cluster(sources, run_dir)
    step_score(sources, run_dir)
    cap = max_sources if max_sources is not None else DEFAULT_MAX_SOURCES.get(mode, 40)
    step_select(sources, run_dir, cap, min_per_angle=min_per_angle)
    gaps = step_gaps(sources, run_dir, min_per_angle)
    require(triage_input_digest(run_dir) == input_digest, 'triage inputs changed during processing')

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

    report_path = write_report(sources, gaps, run_dir, cap, min_per_angle)

    counts = {'selected': 0, 'reserve': 0, 'dropped': 0}
    for s in sources:
        st = s.get('triage_status')
        if st in counts:
            counts[st] += 1
    result_path = os.path.join(run_dir, 'triage', 'triage_result.json')
    required = len(set(plan_angle_aliases(run_dir).values())) * min_per_angle
    result = {
        'status': 'coverage_gaps' if gaps else 'ok',
        'discovered': len(sources), 'counts': counts,
        'gaps': gaps, 'corpus': corpus_path, 'report': report_path,
        'lineage_policy': 'full_content_duplicates_only; reviewed_shared_origins_retain_unique_material',
        'similarity_candidate_sources': sum(bool(s.get('similarity_candidates')) for s in sources),
        'max_sources': cap, 'minimum_per_angle': min_per_angle,
        'coverage_capacity': {'minimum_required_sources': required,
                              'sufficient': cap >= required},
        'result': result_path,
        'inputs_sha256': input_digest,
    }
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return result


def triage_input_digest(run_dir: str) -> str:
    """Bind diagnostics to the plan, source registry, raw material and reviews."""
    from pathlib import Path
    from fact_check import digest, inside, sha
    run = Path(run_dir).resolve()
    names = {'acquisition/sources.jsonl', 'acquisition/query_plan.md'}
    for source in load_sources(run_dir):
        if source.get('raw_file'):
            names.add('acquisition/' + source['raw_file'])
    for relative in ('triage/lineage.json', 'triage/overrides.json'):
        if (run / relative).exists():
            names.add(relative)
    return digest({name: sha(inside(run, name).read_bytes()) for name in sorted(names)})


def begin_delta(run_dir: str) -> dict:
    """Reserve the single triage wave on disk BEFORE any dispatch."""
    from pathlib import Path
    from fact_check import inside, load_json, output_path, require
    from search_quality import check_acquisition
    run = Path(run_dir).resolve()
    result = load_json(inside(run, 'triage/triage_result.json'))
    require(result.get('inputs_sha256') == triage_input_digest(run_dir),
            'stale triage result; rerun triage before considering delta acquisition')
    require(result['coverage_capacity']['sufficient'], 'resolve corpus capacity before dispatch')
    targets = [g['angle'] for g in result['gaps'] if g['next_action'] == 'delta_acquisition']
    require(targets, 'no genuine acquisition shortfalls to dispatch')
    check_acquisition(run, read_jsonl(str(inside(run, 'acquisition/query_log.jsonl'))),
                      load_plan_angles(run_dir))
    attempt = {'status': 'attempt_reserved', 'reserved_at': now_iso(), 'angles': targets,
               'max_searches_per_angle': 3, 'max_fetches_per_angle': 3,
               'triage_inputs_sha256': result['inputs_sha256']}
    path = output_path(run, 'triage/delta_attempt.json')
    # O_EXCL makes retries, interrupted dispatch and new sessions consume the
    # same attempt. Never remove this file to manufacture a fresh budget.
    with open(path, 'x', encoding='utf-8') as stream:
        json.dump(attempt, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    return attempt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='triage',
        description='Source triage between acquisition and evidence phases')
    sub = parser.add_subparsers(dest='command', required=True)

    delta = sub.add_parser('begin-delta', help='Reserve the single triage-triggered acquisition wave')
    delta.add_argument('--run-dir', required=True)

    for name, help_txt in [
        ('dedupe', 'Flag duplicates and syndication'),
        ('cluster', 'Assign independence groups'),
        ('score', 'Attach credibility scores'),
        ('select', 'Mark selected/reserve/dropped'),
    ]:
        p = sub.add_parser(name, help=help_txt)
        p.add_argument('--run-dir', required=True)

    for name, help_txt in [('run', 'Full triage: dedupe→cluster→score→select→gaps'),
                           ('gaps', 'Detect coverage gaps using current triage decisions')]:
        p = sub.add_parser(name, help=help_txt)
        p.add_argument('--run-dir', required=True)
        p.add_argument('--mode', default='standard',
                       choices=['quick', 'standard', 'deep', 'ultradeep'])
        p.add_argument('--max-sources', type=positive_int, default=None,
                       help='Override corpus target for the mode')
        p.add_argument('--min-per-angle', type=positive_int, default=DEFAULT_MIN_PER_ANGLE)

    args = parser.parse_args()

    if args.command == 'begin-delta':
        print(json.dumps(begin_delta(args.run_dir), indent=2))
        return

    if args.command == 'run':
        result = run_triage(args.run_dir, args.mode, args.max_sources, args.min_per_angle)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result['gaps']:
            sys.exit(2)  # signal: unresolved coverage; inspect next_action/capacity
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
        step_dedupe(sources, args.run_dir)
        step_cluster(sources, args.run_dir)
        step_score(sources, args.run_dir)
        cap = args.max_sources if args.max_sources is not None else DEFAULT_MAX_SOURCES[args.mode]
        step_select(sources, args.run_dir, cap, min_per_angle=args.min_per_angle)
        print(json.dumps(step_gaps(sources, args.run_dir, args.min_per_angle), indent=2))
        return
    for s in sources:
        print(json.dumps({k: v for k, v in s.items() if not k.startswith('_')},
                         ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'error': str(exc)}))
        sys.exit(1)
