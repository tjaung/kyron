#!/usr/bin/env python3
"""Generate and seed the fictional Kyron dataset. Defaults to the Compose database."""
import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def write_fixtures():
    from server.core.demo_data import build_dataset
    data = ROOT / 'server' / 'data'
    blueprint = json.loads((data / 'seed_blueprint.json').read_text())
    context, sources = build_dataset(blueprint['context'], blueprint['sources'])
    for name, value in [('context.json', context), ('conversations.json', sources)]:
        (data / name).write_text(json.dumps(value, indent=2) + '\n')
    print(f'Generated {len(context["patients"])} patients and {len(sources)} linked calls.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-fixtures', action='store_true', help='Regenerate checked-in JSON only; no database needed')
    parser.add_argument('--fixtures-only', action='store_true', help=argparse.SUPPRESS)  # Legacy alias; all seeding is fixture-only.
    args = parser.parse_args()
    if args.write_fixtures:
        write_fixtures()
        return
    if not os.environ.get('DATABASE_URL'):
        command = ['docker', 'compose', 'exec', '-T', 'server', 'python', '/workspace/seed_data.py']
        subprocess.run(command, cwd=ROOT, check=True)
        return
    from server.core.seed import initialize_database
    initialize_database()
    print('Seed complete. Supporting records and simulation samples are ready. Run a simulation to create conversations.')


if __name__ == '__main__':
    main()
