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
    parser.add_argument('--profile', choices=('smoke', 'exercise'), default='smoke')
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
                    str(case), args.profile, str(args.ranks)])
    # Exercise oxygen immediately, both writes, demand change and a restart.
    setentry('system/controlDict', 'endTime', '0.004')
    setentry('system/controlDict', 'writeInterval', '0.002')
    for key, value in {'oxygenStartTime': '0', 'controlStartTime': '0',
                       'sampleInterval': '0.0001', 'demandChangeTime': '0.002'}.items():
        setentry('constant/bioProperties', key, '[0 0 1 0 0 0 0] ' + value)
    run('mesh', ['bash', './Allmesh'], case)
    mesh = (case / 'log.checkMesh').read_text()
    print(mesh, flush=True)
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
    # The function objects write ASCII cell volume/centres at the final time.
    def internal(path, vector=False):
        content = path.read_text()
        match = re.search(r'internalField\s+nonuniform\s+List<[^>]+>\s+(\d+)\s*\((.*?)\)\s*;', content, re.S)
        if not match:
            raise RuntimeError('Missing nonuniform diagnostic field: ' + str(path))
        if vector:
            values = [tuple(map(float, row.split())) for row in re.findall(r'\(([^()]+)\)', match[2])]
        else:
            values = list(map(float, match[2].split()))
        if len(values) != int(match[1]):
            raise RuntimeError('Diagnostic cell count mismatch')
        return values

    volumes = internal(case / '0.006/V')
    centres = internal(case / '0.006/C', vector=True)
    if len(volumes) != len(centres) or not volumes or min(volumes) <= 0:
        raise RuntimeError('Invalid cell volumes/centres')
    widths = [v**(1/3) for v in volumes]
    regions = {
        'wholeMesh': lambda x, y, z: True,
        'impellerEnvelope': lambda x, y, z: x*x+y*y < .18**2 and .04 < z < .76,
        'dischargeAndBaffles': lambda x, y, z: .18**2 < x*x+y*y < .46**2 and .04 < z < .76,
        'centralPlume': lambda x, y, z: x*x+y*y < .20**2 and .02 < z < .80,
    }
    sizes = {}
    for name, selected in regions.items():
        values = sorted(w for w, c in zip(widths, centres) if selected(*c))
        if not values:
            raise RuntimeError('Empty mesh audit region: ' + name)
        sizes[name] = {'cells': len(values), 'minDelta_m': values[0],
                       'medianDelta_m': values[len(values)//2], 'maxDelta_m': values[-1]}
    wall = list(case.glob('postProcessing/yPlus.liquid/*/yPlus.liquid.dat'))
    if not wall:
        wall = list(case.glob('postProcessing/**/yPlus*.dat'))
    if not wall:
        raise RuntimeError('Missing liquid y+ diagnostic')
    wall_values = {}
    for path in wall:
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            parts = line.split()
            if len(parts) != 5:
                raise RuntimeError('Unexpected y+ diagnostic row: ' + line)
            time, low, high, mean = map(float, (parts[0], *parts[2:]))
            if not all(math.isfinite(v) and v >= 0 for v in (time, low, high, mean)):
                raise RuntimeError('Invalid wall y+ values')
            if parts[1] not in wall_values or time >= wall_values[parts[1]]['time_s']:
                wall_values[parts[1]] = {'time_s': time, 'min': low, 'max': high, 'mean': mean}
    if not wall_values:
        raise RuntimeError('Empty wall y+ diagnostics')
    quality = [line.strip() for line in mesh.splitlines() if any(term in line.lower()
               for term in ('aspect ratio', 'non-orthogonality', 'skewness', 'volume =', 'mesh ok'))]
    summary = {'status': 'passed' , 'scope': 'short integration smoke; not converged LES',
               'meshProfile': args.profile, 'ranks': args.ranks,
               'cells': re.findall(r'^\s*cells:\s*(\d+)', mesh, re.M),
               'deltaT_s': .0001, 'endTime_s': .006,
               'maxCourant': max(courants), 'maxOxygenBalanceResidual_mol': residual,
               'vtkTimes_s': converted,
               'openfoamVersion': os.environ.get('WM_PROJECT_VERSION'),
               'meshQuality': quality, 'filterWidthByRegion': sizes,
               'wallDiagnostics': [str(p.relative_to(case)) for p in wall],
               'startupLiquidYPlusByPatch': wall_values,
               'wallAssessment': 'startup y+ only; developed-flow wall adequacy unverified'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
