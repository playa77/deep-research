#!/usr/bin/env python3
"""
Claim Linker — joins report claims to the evidence substrate.

The claim extractor (extract_claims.py) records each claim's [N] citation
numbers as `_citation_numbers`, but display numbers are report-local while
evidence is keyed by stable source_id. This script closes that gap: it maps
display numbers to source_ids via the curated corpus (same order as
`citation_manager.py assign-display-numbers`) and writes `cited_source_ids`
into claims.jsonl, so `verify_claim_support.py` can score support against
the evidence store.

Citation numbers that do not resolve to a corpus source are reported — they
are QA-check-1 findings (citation drift or an uncited-corpus reference).

CLI:
  link-claims --run-dir <run>          # resolves triage/corpus.jsonl
  link-claims --dir <evidence_dir> --sources <corpus.jsonl|sources.jsonl>
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citation_manager import read_jsonl, _dedup_sources, _curated_rows, _resolve_sources_path  # noqa: E402


def build_display_map(sources: list[dict]) -> dict[int, str]:
    """Display number -> source_id, identical ordering to assign-display-numbers."""
    mapping = {}
    for i, src in enumerate(_curated_rows(_dedup_sources(sources)), 1):
        sid = src.get('source_id')
        if sid and i not in mapping:
            mapping[i] = sid
    return mapping


def cmd_link(args: argparse.Namespace) -> None:
    claims_path = os.path.join(args.dir, 'claims.jsonl')
    if not os.path.exists(claims_path):
        print(json.dumps({'error': f'claims.jsonl not found in {args.dir}'}),
              file=sys.stderr)
        sys.exit(1)

    sources_path = _resolve_sources_path(args.run_dir or '.', args.sources)
    sources = read_jsonl(sources_path)
    if not sources:
        print(json.dumps({'error': f'no sources found at {sources_path}'}),
              file=sys.stderr)
        sys.exit(1)
    display_map = build_display_map(sources)

    claims = read_jsonl(claims_path)
    linked = 0
    already = 0
    no_citations = 0
    unresolvable: dict[str, list[int]] = {}

    for claim in claims:
        nums = claim.pop('_citation_numbers', None)
        if claim.get('cited_source_ids'):
            already += 1
            continue
        if not nums:
            no_citations += 1
            continue
        resolved = []
        missing = []
        for n in nums:
            sid = display_map.get(int(n))
            if sid:
                resolved.append(sid)
            else:
                missing.append(int(n))
        if missing:
            unresolvable[claim['claim_id']] = sorted(set(missing))
        if resolved:
            claim['cited_source_ids'] = sorted(set(resolved))
            linked += 1

    with open(claims_path, 'w', encoding='utf-8') as f:
        for claim in claims:
            f.write(json.dumps(claim, ensure_ascii=False) + '\n')

    print(json.dumps({
        'status': 'ok',
        'total_claims': len(claims),
        'newly_linked': linked,
        'already_linked': already,
        'no_citations_in_text': no_citations,
        'claims_with_unresolvable_numbers': unresolvable,
        'sources_path': sources_path,
    }, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(prog='link_claims',
                                     description='Link report claims to stable source_ids')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('link-claims', help='Resolve _citation_numbers to cited_source_ids')
    p.add_argument('--dir', required=True, help='Directory containing claims.jsonl (evidence/)')
    p.add_argument('--run-dir', default=None, help='Run directory (resolves curated corpus)')
    p.add_argument('--sources', default=None, help='Explicit corpus/sources JSONL')
    args = parser.parse_args()
    if not args.run_dir and not args.sources:
        parser.error('either --run-dir or --sources is required')
    cmd_link(args)


if __name__ == '__main__':
    main()
