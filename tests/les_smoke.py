#!/usr/bin/env python3
"""Short real-geometry LES-MRF integration test, not LES validation.

Usage: python3 tests/les_smoke.py --output /absolute/new/results --ranks 8
Requires an activated Foundation 13 installation and a built project.
Keeps the prepared case, mesh, solver logs and machine-readable summary.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--ranks', type=int, default=8)
    args = parser.parse_args()
    if args.ranks < 1:
        parser.error('--ranks must be positive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    case = output / 'tankLES'

    def run(name, command, cwd=ROOT):
        log = output / (name + '.log')
        with log.open('w') as stream:
            result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            print(log.read_text(errors='replace')[-6000:], flush=True)
            for path in case.glob('log.*'):
                if path.is_file():
                    tail = path.read_text(errors='replace')[-6000:]
                    if any(s in tail for s in ('FOAM FATAL', 'error:', 'FOAM exiting')):
                        print(path.name, tail, flush=True)
            raise RuntimeError(f'{name} failed; see {log}')

    def setentry(file, key, value):
        subprocess.run(['foamDictionary', str(case / file), '-entry', key, '-set', value],
                       check=True, stdout=subprocess.DEVNULL)

    run('prepare', ['bash', str(ROOT / 'cases/aeratedTankLES/Allprepare'),
                    str(case), 'smoke', str(args.ranks)])
    # Exercise oxygen immediately, both writes, demand change and a restart.
    setentry('system/controlDict', 'endTime', '0.004')
    setentry('system/controlDict', 'writeInterval', '0.002')
    for key, value in {'oxygenStartTime': '0', 'controlStartTime': '0',
                       'sampleInterval': '0.0001', 'demandChangeTime': '0.002'}.items():
        setentry('constant/bioProperties', key, '[0 0 1 0 0 0 0] ' + value)
    run('mesh', ['bash', './Allmesh'], case)
    mesh = (case / 'log.checkMesh').read_text()
    if 'Mesh OK' not in mesh:
        raise RuntimeError('Mesh check did not report Mesh OK')
    run('solve', ['bash', './Allrun'], case)
    run('restart', ['bash', './Allrestart', '0.006'], case)
    solver = (case / 'log.bioTankControlFoam').read_text()
    restart_logs = list(case.glob('log.restart.*'))
    history = solver + '\n'.join(p.read_text() for p in restart_logs)
    for model in ('SmagorinskyZhang', 'continuousGasKEqn'):
        if model not in solver:
            raise RuntimeError('LES model not confirmed in solver log: ' + model)
    rows = []
    for path in sorted(case.glob('postProcessing/bioControl/*/oxygenBalance.csv')):
        with path.open() as stream:
            rows.extend({k: float(v) for k, v in row.items()} for row in csv.DictReader(stream))
    if not rows or abs(max(r['time_s'] for r in rows) - .006) > 1e-9:
        raise RuntimeError('Missing final oxygen balance at 0.006 s')
    if any(not all(math.isfinite(v) for v in row.values()) for row in rows):
        raise RuntimeError('Non-finite oxygen balance')
    residual = max(abs(row['residual_mol']) for row in rows)
    if residual > 1e-7 or min(row['liquidInventory_mol'] for row in rows) < 0:
        raise RuntimeError('Oxygen inventory/balance check failed')
    if rows[-1]['cumulativeUptake_mol'] <= 0:
        raise RuntimeError('Oxygen biology was not exercised')
    courants = [float(v) for v in re.findall(r'Courant Number[^\n]*max:\s*([\d.eE+-]+)', history)]
    if not courants or not all(math.isfinite(v) for v in courants) or max(courants) > 1:
        raise RuntimeError(f'Missing or excessive Courant number: {max(courants, default=-1)}')
    run('vtk', ['bash', './foamToVTK.sh', 'all', str(min(args.ranks, 4))], case)
    series = json.loads((case / 'VTK/tankLES.vtk.series').read_text())
    converted = [entry['time'] for entry in series['files']]
    if converted != [0, .002, .004, .006]:
        raise RuntimeError(f'Unexpected series times: {converted}')
    for entry in series['files']:
        if (case / 'VTK' / entry['name']).stat().st_size == 0:
            raise RuntimeError('Empty VTK dataset')
    summary = {'status': 'passed', 'scope': 'short integration smoke; not converged LES',
               'meshProfile': 'smoke', 'ranks': args.ranks,
               'cells': re.findall(r'^\s*cells:\s*(\d+)', mesh, re.M),
               'deltaT_s': .0001, 'endTime_s': .006,
               'maxCourant': max(courants), 'maxOxygenBalanceResidual_mol': residual,
               'vtkTimes_s': converted,
               'openfoamVersion': os.environ.get('WM_PROJECT_VERSION')}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
