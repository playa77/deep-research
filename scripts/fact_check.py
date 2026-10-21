#!/usr/bin/env python3
"""Fail-closed release contract. Checks audit artifacts, never certifies truth.

prepare creates an UNREVIEWED inventory; verify is read-only except for its
machine result. No network, paid API, model calls, eval, or automatic approvals.
"""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext, ROUND_HALF_EVEN, ROUND_HALF_UP
import hashlib
from itertools import combinations
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CORE = ('run_manifest.json', 'report/report.md', 'triage/corpus.jsonl',
        'evidence/evidence.jsonl', 'acquisition/query_log.jsonl')
CLAIM_CHECKS = ('atomicity', 'entailment', 'entities_roles', 'polarity_modality',
                'numbers_units_denominators', 'time_geography_population',
                'causality_comparisons', 'source_quality', 'independence',
                'counterevidence', 'uncertainty', 'calculations')
ATTACK_CHECKS = ('omitted_claims', 'citation_laundering', 'negation_role_reversal',
                 'wrong_number_unit_denominator', 'stale_or_wrong_scope',
                 'correlation_to_causation', 'shared_origin', 'cherry_picking',
                 'strongest_counterexample', 'calculation_reproduction')
SOURCE_CHECKS = ('retrieval_authenticity', 'metadata_identity', 'full_context',
                 'corrections_retractions', 'fitness_for_claim', 'origin_lineage')
COVERAGE_CHECKS = ('all_content', 'atomic_decomposition', 'non_assertive_exclusions',
                   'bibliography_mapping')


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(obj):
    return sha(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8'))


def claim_digest(claim):
    return digest({k: v for k, v in claim.items() if k not in ('verification', 'red_team')})


def no_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ContractError(f'duplicate JSON key: {key}')
        obj[key] = value
    return obj


def parse_json(text):
    def invalid_constant(value):
        raise ContractError(f'invalid number: {value}')

    return json.loads(text, object_pairs_hook=no_duplicates,
                      parse_constant=invalid_constant)


def load_json(path):
    return parse_json(path.read_text(encoding='utf-8'))


def load_rows(path):
    rows = []
    for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if line.strip():
            row = parse_json(line)
            if not isinstance(row, dict):
                raise ContractError(f'{path.name}:{n}: expected object')
            rows.append(row)
    return rows


def inside(run, relative):
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ContractError(f'expected relative path: {relative!r}')
    p = (run / relative).resolve()
    if not p.is_relative_to(run.resolve()) or not p.is_file():
        raise ContractError(f'missing file or path escapes run: {relative}')
    return p


def output_path(run, relative):
    from workflow_guard import external_run
    external_run(run)
    candidate = run / relative
    for part in (candidate, *candidate.parents):
        if part == run:
            break
        if part.is_symlink():
            raise ContractError(f'output symlink is not allowed: {relative}')
    path = candidate.resolve()
    if not path.is_relative_to(run.resolve()):
        raise ContractError(f'output path escapes run: {relative}')
    return path


def write_result(run, result):
    path = output_path(run, 'qa/fact_check_result.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement avoids partial successes and overwriting a hard-linked
    # input file in place. Temporary files never contain credentials.
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.fact-check-', delete=False) as f:
            tmp = Path(f.name)
            json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n')
        tmp.replace(path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def indexed(rows, key):
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value or value in result:
            raise ContractError(f'missing/duplicate {key}: {value!r}')
        result[value] = row
    return result


def inventory(text):
    # Physical lines are intentionally conservative: headings, tables, footnotes,
    # code, captions, frontmatter and bibliography ALL require a disposition.
    return [{'line': n, 'text_sha256': sha(line.encode('utf-8')),
             'kind': 'pending', 'claim_ids': [], 'reason': ''}
            for n, line in enumerate(text.splitlines(), 1) if line.strip()]


def bundle(run, reviewer=False):
    from workflow_guard import require_processing, SNAPSHOT, PROMPT, DECISION
    require_processing(run, reviewer=reviewer)
    paths = {p: inside(run, p) for p in CORE}
    for relative in (SNAPSHOT, PROMPT, DECISION):
        paths[relative] = inside(run, relative)
    corpus = load_rows(paths['triage/corpus.jsonl'])
    evidence = load_rows(paths['evidence/evidence.jsonl'])
    sources = indexed(corpus, 'source_id')
    evs = indexed(evidence, 'evidence_id')
    for ev in evidence:
        src = sources.get(ev.get('source_id'))
        if src is None:
            raise ContractError(f'evidence {ev["evidence_id"]}: unknown source')
        raw = src.get('raw_file')
        if not raw:
            raise ContractError(f'source {src["source_id"]}: no raw_file')
        relative = 'acquisition/' + raw
        paths[relative] = inside(run, relative)
        record_name = src.get('retrieval_record')
        if not record_name:
            raise ContractError(f'source {src["source_id"]}: no retrieval_record/original response')
        record_path = 'acquisition/' + record_name
        paths[record_path] = inside(run, record_path)
        record = load_json(paths[record_path])
        original = 'acquisition/' + record['content_file']
        paths[original] = inside(run, original)
    from search_quality import assess_queries
    quality = assess_queries(run, load_rows(paths['acquisition/query_log.jsonl']))
    for relative in quality['response_files']:
        paths[relative] = inside(run, relative)
    if (run / 'triage/lineage.json').exists():
        paths['triage/lineage.json'] = inside(run, 'triage/lineage.json')
        for source in sources.values():
            if source.get('raw_file'):
                relative = 'acquisition/' + source['raw_file']
                paths[relative] = inside(run, relative)
    inputs = {p: sha(file.read_bytes()) for p, file in sorted(paths.items())}
    acquisition_root = (run / 'acquisition').resolve()
    for relative, path in paths.items():
        if relative.startswith('acquisition/') and not path.is_relative_to(acquisition_root):
            raise ContractError(f'acquisition artifact escapes acquisition directory: {relative}')
    manifest = load_json(paths['run_manifest.json'])
    if not isinstance(manifest, dict):
        raise ContractError('run_manifest.json must contain an object')
    # Closing out a successful run must not invalidate its scientific review.
    # All research/scope fields stay bound; only these bookkeeping fields vary.
    inputs['run_manifest.json'] = digest({k: v for k, v in manifest.items()
                                         if k not in ('finished_at', 'phases_completed', 'continuation')})
    report = paths['report/report.md'].read_text(encoding='utf-8')
    if not report.strip() or not corpus or not evidence:
        raise ContractError('report, corpus and evidence must be nonempty')
    return inputs, report, sources, evs, manifest


def origin_content_hash(run, source):
    text = inside(run, 'acquisition/' + source['raw_file']).read_text(encoding='utf-8')
    # Ignore provenance headers and layout when detecting duplicate content.
    return sha(' '.join(text[body_start(text):].casefold().split()).encode('utf-8'))


def body_start(text):
    if text.startswith('---\n') or text.startswith('---\r\n'):
        match = re.search(r'^---\s*$', text[4:], re.M)
        if not match:
            raise ContractError('unclosed raw frontmatter')
        return 4 + match.end()
    return 0


def anchor_for(run, source, ev):
    path = 'acquisition/' + source['raw_file']
    raw = inside(run, path).read_bytes()
    text = raw.decode('utf-8')
    quote = ev.get('quote', '')
    if not isinstance(quote, str) or not quote.strip():
        raise ContractError('empty evidence quote')
    positions = []
    pos = body_start(text)
    while (pos := text.find(quote, pos)) != -1:
        # Agent annotations are not source evidence.
        line_start = text.rfind('\n', 0, pos) + 1
        if '[KEY PASSAGE]' not in text[line_start:pos]:
            positions.append(pos)
        pos += max(1, len(quote))
    if len(positions) != 1:
        raise ContractError(f'{ev["evidence_id"]}: quote has {len(positions)} exact body matches; provide/inspect offsets')
    return {'evidence_id': ev['evidence_id'], 'raw_file': path,
            'raw_sha256': sha(raw), 'start': positions[0], 'end': positions[0] + len(quote)}


def blank_checks(names):
    return {n: {'result': 'pending', 'rationale': ''} for n in names}


def prepare(run):
    inputs, report, sources, evs, _ = bundle(run)
    anchors, warnings = [], []
    for ev in evs.values():
        try:
            anchors.append(anchor_for(run, sources[ev['source_id']], ev))
        except ContractError as exc:
            warnings.append(str(exc))
    return {'version': 1, 'inputs': inputs, 'author_id': '', 'reviewers': [],
            'coverage': inventory(report),
            'coverage_review': {'reviewer_id': '', 'verdict': 'pending',
                                'inputs_sha256': digest(inputs),
                                'checks': blank_checks(COVERAGE_CHECKS)},
            'anchors': anchors, 'source_reviews': [], 'claims': []}, warnings


def validate_schema(document, schema_name='fact_check.schema.json'):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise ContractError('install free dependency: python -m pip install -r requirements.txt') from exc
    schema = load_json(ROOT / 'schemas' / schema_name)
    errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
                    key=lambda e: str(list(e.absolute_path)))
    if errors:
        raise ContractError(schema_name + ': ' + '; '.join(f'{list(e.absolute_path)}: {e.message}' for e in errors[:12]))


def numeric_input(item, evs):
    ev = evs[item['evidence_id']]
    token = item['token']
    if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', token):
        raise ContractError('numeric token must be an exact plain decimal; document any locale conversion separately')
    if not re.search(r'(?<![\w.,])' + re.escape(token) + r'(?![\w.,])', ev['quote']):
        raise ContractError(f'calculation token {token!r} absent from evidence')
    scale = {'one': 1, 'thousand': 1000, 'million': 10**6, 'billion': 10**9,
             'trillion': 10**12}[item['scale']]
    return Decimal(token) * scale


def quantities(text):
    """Conservative numeric veto, not a semantic approval heuristic.

    Keep signs, magnitudes and percent vs percentage points distinct. A locale
    or unit conversion needs an explicit calculation and reviewer justification.
    """
    text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text).replace('\N{MINUS SIGN}', '-')
    pattern = r'(?<![\w.])[+-]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:percentage points?|basis points?|percent|%|thousand|million|billion|trillion))?'
    found = set()
    for m in re.finditer(pattern, text, re.I):
        token = m.group().lower()
        n = re.match(r'[+-]?\d+(?:,\d{3})*(?:\.\d+)?', token).group()
        suffix = token[len(n):].strip().replace('percent', '%')
        found.add((Decimal(n.replace(',', '')), suffix))
    return found


def calculate(calc, evs):
    with localcontext() as ctx:
        ctx.prec = 80
        op = calc['operation']
        if op in ('elapsed_days', 'completed_years'):
            if len(calc['inputs']) != 2:
                raise ContractError('date operation needs exactly two inputs')
            dates = []
            for item in calc['inputs']:
                if item['token'] not in evs[item['evidence_id']]['quote'] or item['scale'] != 'one':
                    raise ContractError('date input not in evidence, or invalid date scale')
                dates.append(date.fromisoformat(item['token']))
            start, end = dates
            if end < start:
                raise ContractError('date interval reversed')
            value = Decimal((end - start).days if op == 'elapsed_days' else
                            end.year - start.year - ((end.month, end.day) < (start.month, start.day)))
        else:
            values = [numeric_input(i, evs) for i in calc['inputs']]
            if op == 'sum':
                value = sum(values, Decimal(0))
            elif op == 'product':
                value = Decimal(1)
                for v in values:
                    value *= v
            else:
                if len(values) != 2:
                    raise ContractError(f'{op} needs exactly two inputs')
                a, b = values
                if op == 'difference':
                    value = a - b
                elif op == 'ratio':
                    value = a / b
                elif op == 'percentage':
                    value = a / b * 100
                elif op == 'percent_change':
                    value = (b - a) / a * 100
                else:
                    raise ContractError(f'unknown calculation: {op}')
        rounding = {'half_even': ROUND_HALF_EVEN, 'half_up': ROUND_HALF_UP}[calc['rounding']]
        value = value.quantize(Decimal(1).scaleb(-calc['decimal_places']), rounding=rounding)
        reported = Decimal(calc['reported_value'])
        if not reported.is_finite() or reported != value:
            raise ContractError(f'calculation mismatch: computed {value}, reported {reported}')
        return str(value)


def verify(run, doc):
    validate_schema(doc)
    inputs, report, sources, evs, manifest = bundle(run)
    from citation_manager import bibliography_title_link, canonicalize_locator, compute_source_id
    from evidence_store import compute_evidence_id
    from validate_report import bibliography_presentation_errors, verdict_presentation_errors
    for source in sources.values():
        validate_schema(source, 'corpus.schema.json')
        if source['source_id'] != compute_source_id(source['canonical_locator']):
            raise ContractError('source identity hash mismatch')
        if source['canonical_locator'] != canonicalize_locator(source['raw_url']):
            raise ContractError('source canonical identity disagrees with raw URL')
        if not source['independence_group_id'].strip():
            raise ContractError('source independence group cannot be blank')
        if source.get('retrieval_record'):
            record = load_json(inside(run, 'acquisition/' + source['retrieval_record']))
            validate_schema(record, 'retrieval.schema.json')
            if record['source_id'] != source['source_id'] or record['requested_url'] != source['raw_url']:
                raise ContractError('retrieval record identity mismatch')
            original = inside(run, 'acquisition/' + record['content_file'])
            if record['content_sha256'] != sha(original.read_bytes()):
                raise ContractError('original retrieval response hash mismatch')
            if original == inside(run, 'acquisition/' + source['raw_file']):
                raise ContractError('preserve original response separately from extracted source text')
            if record['kind'] == 'http_response' and (record['http_status'] is None or not 200 <= record['http_status'] < 300):
                raise ContractError('unsuccessful HTTP retrieval is not evidence')
    for ev in evs.values():
        validate_schema(ev, 'evidence.schema.json')
        if ev['evidence_id'] != compute_evidence_id(ev['source_id'], ev['quote'], ev.get('locator')):
            raise ContractError('evidence identity hash mismatch')
    errors = verdict_presentation_errors(report)

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(doc['inputs'] == inputs, 'input snapshot changed; prepare again and repeat reviews')
    require(manifest.get('mode') in ('quick', 'standard', 'deep', 'ultradeep'), 'unknown run mode')
    reviewers = indexed(doc['reviewers'], 'reviewer_id')
    require(doc['author_id'] in reviewers, 'unknown author_id')
    require(doc['author_id'] in reviewers and reviewers[doc['author_id']]['role'] == 'author', 'author role missing')
    require(len({r['execution_ref'].strip() for r in reviewers.values()}) == len(reviewers),
            'reviewer execution references must identify distinct sessions')

    def reviewer(rid, role):
        require(rid in reviewers and reviewers[rid]['role'] == role, f'{rid}: expected {role} reviewer')
        require(rid != doc['author_id'], f'{rid}: author cannot approve own work')

    def checks(obj, required, prefix):
        require(set(obj) == set(required), f'{prefix}: missing/unexpected checks')
        for key, item in obj.items():
            require(item['result'] == 'pass', f'{prefix}/{key}: not passed')
            require(len(item['rationale'].strip()) >= 12, f'{prefix}/{key}: blank or trivial rationale')

    coverage = indexed([dict(x, _id=str(x['line'])) for x in doc['coverage']], '_id')
    expected = inventory(report)
    require(set(coverage) == {str(u['line']) for u in expected}, 'report coverage incomplete or has stale lines')
    claims = indexed(doc['claims'], 'claim_id')
    require(bool(claims), 'no claims registered')
    locations = {}
    for c in claims.values():
        for loc in c['locations']:
            locations.setdefault(loc['line'], set()).add(c['claim_id'])
            lines = report.splitlines()
            require(0 < loc['line'] <= len(lines) and loc['excerpt'] in lines[loc['line'] - 1],
                    f'{c["claim_id"]}: excerpt not present at report line')
    for unit in expected:
        row = coverage.get(str(unit['line']))
        if row is None:
            continue
        require(row['text_sha256'] == unit['text_sha256'], f'line {unit["line"]}: stale coverage')
        ids = set(row['claim_ids'])
        require(ids <= claims.keys(), f'line {unit["line"]}: unknown claim reference')
        require(ids == locations.get(unit['line'], set()), f'line {unit["line"]}: coverage/claim location mismatch')
        if row['kind'] == 'claims':
            require(bool(ids), f'line {unit["line"]}: claims missing')
        elif row['kind'] == 'non_assertive':
            require(not ids and bool(row['reason'].strip()), f'line {unit["line"]}: unjustified exclusion')
        else:
            require(False, f'line {unit["line"]}: unreviewed')
    cr = doc['coverage_review']
    reviewer(cr['reviewer_id'], 'red_team')
    require(cr['verdict'] == 'approved', 'coverage review not approved')
    require(cr['inputs_sha256'] == digest(inputs), 'stale coverage review')
    checks(cr['checks'], COVERAGE_CHECKS, 'coverage')

    anchors = indexed(doc['anchors'], 'evidence_id')
    for eid, anchor in anchors.items():
        require(eid in evs, f'anchor {eid}: unknown evidence')
        if eid not in evs:
            continue
        ev = evs[eid]
        src = sources[ev['source_id']]
        expected_path = 'acquisition/' + src['raw_file']
        require(anchor['raw_file'] == expected_path, f'{eid}: anchor points to wrong source')
        raw = inside(run, expected_path).read_bytes()
        text = raw.decode('utf-8')
        a, b = anchor['start'], anchor['end']
        require(anchor['raw_sha256'] == sha(raw), f'{eid}: raw hash mismatch')
        require(body_start(text) <= a < b <= len(text) and text[a:b] == ev['quote'], f'{eid}: fabricated or stale quote offsets')
        line_start = text.rfind('\n', 0, a) + 1
        require('[KEY PASSAGE]' not in text[line_start:a], f'{eid}: agent annotation used as source')
    sr = indexed(doc['source_reviews'], 'source_id')
    for sid, review in sr.items():
        require(sid in sources, f'{sid}: unknown source review')
        reviewer(review['reviewer_id'], 'verifier')
        require(review['verdict'] == 'approved', f'{sid}: source review not approved')
        require(review['inputs_sha256'] == digest(inputs), f'{sid}: stale source review')
        checks(review['checks'], SOURCE_CHECKS, sid)

    query_rows = load_rows(inside(run, 'acquisition/query_log.jsonl'))
    for q in query_rows:
        validate_schema(q, 'query_log.schema.json')
        require(bool(q['query_text'].strip()) and bool(q['tool'].strip()), 'empty search query/tool')
    from search_quality import assess_queries
    quality = assess_queries(run, query_rows)
    usable = set(quality['usable_query_ids'])
    queries = {digest(q) for q in query_rows if q['query_id'] in usable}
    # The display map must agree with the rendered bibliography, not just corpus order.
    eligible = [s for s in sources.values() if s.get('triage_status') != 'dropped']
    display = {n: s for n, s in enumerate(eligible, 1)}
    bib = {}
    bib_lines = []
    in_bib = False
    for line in report.splitlines():
        heading = re.match(r'^#{1,6}\s+(.+?)\s*#*$', line)
        if heading:
            in_bib = heading.group(1).strip().lower() == 'bibliography'
        elif in_bib:
            bib_lines.append(line)
            m = re.match(r'^\[(\d+)\]\s+(.+)$', line)
            if m:
                n = int(m.group(1))
                require(n not in bib, f'duplicate bibliography number {n}')
                bib[n] = m.group(2)
    errors.extend(bibliography_presentation_errors('\n'.join(bib_lines)))
    for n, text in bib.items():
        targets = [a or b for a, b in re.findall(r'\]\((?:<([^>\n]+)>|([^\s]+))\)', text)]
        require(n in display and display[n]['raw_url'] in targets,
                f'bibliography [{n}]: URL disagrees with corpus display map')
        if n in display:
            require(bibliography_title_link(display[n]) in text or
                    f'[{display[n]["title"]}]({display[n]["raw_url"]})' in text,
                    f'bibliography [{n}]: title/URL must match generated bibliography')
    require(bool(bib), 'no bibliography mapping')

    from triage import registrable_domain
    origin_keys = {}

    def keys_for(sid):
        if sid not in origin_keys:
            src = sources[sid]
            origin_keys[sid] = {k for k in (
                ('group', src['independence_group_id'].strip().casefold()),
                ('domain', registrable_domain(src['raw_url'])),
                ('origin', sr.get(sid, {}).get('origin_key', '').strip().casefold()),
                ('content', origin_content_hash(run, src))) if k[1]}
        return origin_keys[sid]

    for cid, c in claims.items():
        require(c['kind'] != 'run_metadata' or bool(c['evidence_links']) or bool(c['premise_ids']),
                f'{cid}: run metadata requires evidence or reviewed premises')
        links = indexed(c['evidence_links'], 'evidence_id')
        require(set(c['premise_ids']) <= claims.keys() and cid not in c['premise_ids'], f'{cid}: invalid premises')
        linked_sources = set()
        supporting = set()
        support_quotes = []
        for eid, link in links.items():
            ev = evs.get(eid)
            require(ev is not None and eid in anchors, f'{cid}/{eid}: missing evidence or exact anchor')
            if ev is None:
                continue
            sid = ev['source_id']
            linked_sources.add(sid)
            require(sid in sr and sources[sid].get('triage_status') == 'selected', f'{cid}/{sid}: source not reviewed/selected')
            require(ev.get('evidence_type') != 'paraphrase' and bool(ev.get('locator') and ev['locator'].strip()),
                    f'{eid}: evidence must be verbatim with locator')
            if link['relation'] == 'supports':
                supporting.add(sid)
                support_quotes.append(ev['quote'])
        if c['kind'] in ('factual', 'attribution'):
            available = set().union(*(quantities(q) for q in support_quotes))
            for calc in c['calculations']:
                available.update(quantities(calc['rendered']))
            require(quantities(c['text']) <= available, f'{cid}: numeric literal/sign/magnitude mismatch; supply evidence or a reproducible calculation')
            require(set().union(*(quantities(l['excerpt']) for l in c['locations'])) <= quantities(c['text']),
                    f'{cid}: report numbers absent from the atomic assertion')
        if c['kind'] in ('factual', 'attribution'):
            require(bool(supporting), f'{cid}: no supporting evidence')
        elif c['kind'] in ('inference', 'recommendation', 'speculation'):
            require(bool(c['premise_ids']), f'{cid}: nonfactual claim needs reviewed premises')
            require(bool(c['qualification'].strip()) and any(c['qualification'] in l['excerpt'] for l in c['locations']),
                    f'{cid}: explicit inference/uncertainty label missing from report')
        else:  # Run metadata must still have traceable claim-level review.
            require(bool(c['qualification'].strip()), f'{cid}: run metadata needs artifact explanation')
        if c['kind'] == 'attribution':
            require(bool(c['qualification'].strip()) and any(c['qualification'] in l['excerpt'] for l in c['locations']),
                    f'{cid}: attribution must be explicit in report')
        if c['importance'] == 'major' and c['kind'] == 'factual':
            # Count connected origin clusters: renamed groups, shared domains,
            # identical content and shared original data do not multiply support.
            parents = {sid: sid for sid in supporting}

            def find(sid):
                while parents[sid] != sid:
                    sid = parents[sid]
                return sid

            for a, b in combinations(sorted(supporting), 2):
                sa, sb = sources[a], sources[b]
                if (keys_for(a) & keys_for(b) or sa.get('duplicate_of') == b or sb.get('duplicate_of') == a
                        or b in (sa.get('lineage_with') or []) or a in (sb.get('lineage_with') or [])
                        or b in (sa.get('syndication_with') or []) or a in (sb.get('syndication_with') or [])):
                    parents[find(a)] = find(b)
            needed = 2 if manifest['mode'] == 'quick' else 3
            require(len({find(s) for s in supporting}) >= needed, f'{cid}: fewer than {needed} independent origins')
        require(bool(c['countersearch_ids']) and set(c['countersearch_ids']) <= queries,
                f'{cid}: missing/unknown or unusable countersearch log references')
        nums = set()
        for loc in c['locations']:
            for match in re.finditer(r'\[(\d+(?:,\s*\d+)*)\]', loc['excerpt']):
                nums.update(int(n.strip()) for n in match.group(1).split(','))
        cited = set()
        for n in nums:
            require(n in display and n in bib, f'{cid}: unresolved citation [{n}]')
            if n in display:
                cited.add(display[n]['source_id'])
        require(linked_sources <= cited, f'{cid}: evidence source absent from report citations')
        require(cited <= linked_sources, f'{cid}: citation has no claim-specific evidence link')
        for calc in c['calculations']:
            rendered_quantities = quantities(calc['rendered'])
            require(len(rendered_quantities) == 1 and
                    all(n == Decimal(calc['reported_value']) for n, _ in rendered_quantities),
                    f'{cid}: rendered calculation must contain only its reported result')
            require(all(i['evidence_id'] in links and links[i['evidence_id']]['relation'] == 'supports' for i in calc['inputs']),
                    f'{cid}: calculation input lacks supporting evidence link')
            try:
                calculate(calc, evs)
            except (ValueError, KeyError, ArithmeticError) as exc:
                require(False, f'{cid}: {exc}')
            require(any(calc['rendered'] in l['excerpt'] for l in c['locations']) and
                    calc['reported_value'] in calc['rendered'], f'{cid}: calculation result not rendered in report')
        for field, role, required in (('verification', 'verifier', CLAIM_CHECKS), ('red_team', 'red_team', ATTACK_CHECKS)):
            review = c[field]
            reviewer(review['reviewer_id'], role)
            require(review['claim_sha256'] == claim_digest(c), f'{cid}/{field}: stale claim review')
            require(review['inputs_sha256'] == digest(inputs), f'{cid}/{field}: stale evidence/input review')
            require(review['verdict'] == 'approved', f'{cid}/{field}: not approved')
            checks(review['checks'], required, f'{cid}/{field}')
            link_reviews = indexed(review['link_reviews'], 'evidence_id')
            require(set(link_reviews) == set(links), f'{cid}/{field}: every evidence link needs review')
            for eid, lr in link_reviews.items():
                require(eid in links and lr['relation'] == links[eid]['relation'] and lr['verdict'] == 'approved',
                        f'{cid}/{field}/{eid}: evidence relationship rejected/unreviewed')
        require(c['verification']['reviewer_id'] != c['red_team']['reviewer_id'], f'{cid}: reviewer independence missing')
    # Detect cycles, including mutually fabricated recommendations/premises.
    visited, active = set(), set()

    def visit(cid):
        if cid in active:
            require(False, f'{cid}: cyclic premise graph')
            return
        if cid in visited or cid not in claims:
            return
        active.add(cid)
        for p in claims[cid]['premise_ids']:
            visit(p)
        active.remove(cid)
        visited.add(cid)
    for cid in claims:
        visit(cid)
    require(bundle(run)[0] == inputs, 'inputs changed while verification was running')
    return {'status': 'blocked' if errors else 'contract_pass', 'errors': errors,
            'claims': len(claims), 'report_lines': len(expected),
            'assurance': 'Artifact integrity and recorded review completeness; not proof of truth.',
            'inputs': inputs, 'contract_sha256': digest(doc),
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'verifier_sha256': sha(Path(__file__).read_bytes()),
            'schema_sha256': sha((ROOT / 'schemas/fact_check.schema.json').read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'verify', 'inspect'):
        p = sub.add_parser(name)
        p.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    boundary_verified = False
    try:
        from workflow_guard import require_processing
        require_processing(run, reviewer=args.command == 'inspect')
        boundary_verified = True
        output = output_path(run, 'qa/fact_check.json')
        if args.command == 'verify':
            write_result(run, {'status': 'blocked', 'errors': ['verification has not completed']})
        if args.command == 'prepare':
            if output.exists():
                raise ContractError('fact_check.json exists; archive it explicitly before preparing a new review')
            doc, warnings = prepare(run)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open('x', encoding='utf-8') as f:
                json.dump(doc, f, indent=2, ensure_ascii=False, allow_nan=False)
                f.write('\n')
            write_result(run, {'status': 'blocked', 'errors': ['new review snapshot is unreviewed']})
            result = {'status': 'unreviewed', 'contract': str(output), 'warnings': warnings}
        elif args.command == 'inspect':
            inputs, _, _, _, _ = bundle(run, reviewer=True)
            doc = load_json(output)
            result = {'status': 'diagnostic_only', 'inputs_sha256': digest(inputs),
                      'claim_sha256': {c['claim_id']: claim_digest(c) for c in doc['claims']},
                      'queries': [{'query_id': digest(q), 'record': q} for q in
                                  load_rows(inside(run, 'acquisition/query_log.jsonl'))]}
        else:
            result = verify(run, load_json(output))
    except Exception as exc:
        # A malformed bundle or an unexpected implementation failure must never
        # leave the previous success as the current machine-readable decision.
        result = {'status': 'blocked', 'errors': [f'{type(exc).__name__}: {exc}']}
    if args.command == 'verify' and (boundary_verified or (run / 'qa/fact_check_result.json').exists()):
        # Also overwrite a stale prior success when parsing/input checks fail.
        try:
            write_result(run, result)
        except (OSError, ContractError) as exc:
            result = {'status': 'blocked', 'errors': [f'cannot persist QA result: {exc}']}
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 1 if result['status'] == 'blocked' else 0


if __name__ == '__main__':
    sys.exit(main())
