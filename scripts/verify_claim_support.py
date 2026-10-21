#!/usr/bin/env python3
"""Legacy lexical diagnostics. --strict runs the authoritative release contract.

Overlap is retrieval similarity, never entailment or truth. Non-strict output
cannot approve a report and never assigns `supported`, even for identical text.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

from fact_check import load_rows

NUMBER_RE = re.compile(r'(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:%|[xX])?(?!\w)')
YEAR_RE = re.compile(r'\b(?:19|20)\d{2}\b')
ENTITY_RE = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b')


def extract_tokens(text):
    return set(re.findall(r'\b\w+\b', text.casefold()))


def extract_numbers(text):
    return set(NUMBER_RE.findall(text))


def extract_years(text):
    return set(YEAR_RE.findall(text))


def extract_entities(text):
    return set(ENTITY_RE.findall(text))


def compute_support_score(claim_text, evidence_quotes):
    if not evidence_quotes:
        return 'unsupported', 0.0, 'no evidence linked'
    tokens = extract_tokens(claim_text)
    score = max((len(tokens & extract_tokens(q)) / max(1, len(tokens)) for q in evidence_quotes), default=0)
    return 'needs_review', round(score, 3), 'lexical similarity only; semantic verification and red team required'


def cmd_verify(args):
    directory = Path(args.dir).resolve()
    if args.strict:
        run = Path(args.run_dir).resolve() if args.run_dir else (directory.parent if directory.name == 'evidence' else directory)
        return subprocess.call([sys.executable, str(Path(__file__).with_name('fact_check.py')),
                                'verify', '--run-dir', str(run)])
    from workflow_guard import processing_for_paths
    processing_for_paths(args.dir, args.run_dir)
    claims = load_rows(directory / 'claims.jsonl')
    evidence = load_rows(directory / 'evidence.jsonl')
    index = {e['evidence_id']: e for e in evidence}
    for c in claims:
        # Only explicit claim-to-evidence links; never borrow every quote from a source.
        quotes = [index[e]['quote'] for e in c.get('evidence_ids', []) if e in index]
        status, score, notes = compute_support_score(c['text'], quotes)
        c.update(support_status=status, _support_score=score, _support_notes=notes)
    (directory / 'claims.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in claims), encoding='utf-8')
    print(json.dumps({'status': 'diagnostic_only', 'verified': 0, 'claims': len(claims),
                      'factual_unsupported': sum(c.get('claim_type') == 'factual' and c['support_status'] == 'unsupported' for c in claims),
                      'support_status_counts': dict(Counter(c['support_status'] for c in claims)),
                      'release_command': 'fact_check.py verify --run-dir <run>'}, indent=2))
    return 0


def cmd_report(args):
    claims = load_rows(Path(args.dir) / 'claims.jsonl')
    print('# Lexical diagnostics (not a release decision)\n')
    print(f'{len(claims)} candidate claims. Run fact_check.py verify for the complete contract.')
    for c in claims:
        print(f'- [{c.get("support_status", "unverified")}] {c["text"]}')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('verify')
    p.add_argument('--dir', required=True)
    p.add_argument('--strict', action='store_true')
    p.add_argument('--run-dir', help='Explicit run root for the strict release contract')
    p = sub.add_parser('report')
    p.add_argument('--dir', required=True)
    args = parser.parse_args()
    try:
        return cmd_verify(args) if args.command == 'verify' else cmd_report(args)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'blocked', 'errors': [str(exc)]}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
