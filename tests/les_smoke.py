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
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--ranks', type=int, default=8)
    parser.add_argument('--profile', choices=('smoke', 'exercise'), default='smoke')
    parser.add_argument('--existing-case', type=Path, help='audit/export an already completed retained smoke case without rerunning CFD')
    parser.add_argument('--reuse-mesh', type=Path, help='copy a retained mesh with the identical Allmesh recipe')
    args = parser.parse_args()
    if args.ranks < 1:
        parser.error('--ranks must be positive')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    case = args.existing_case.resolve() if args.existing_case else output / 'tankLES'
    if args.existing_case and (case/'les-mesh-profile').read_text().strip() != args.profile:
        parser.error('--profile must match the existing case')

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

    if not args.existing_case:
        run('prepare', ['bash', str(ROOT / 'cases/aeratedTankLES/Allprepare'),
                        str(case), args.profile, str(args.ranks)])
        # Exercise oxygen immediately, both writes, demand change and a restart.
        setentry('system/controlDict', 'endTime', '0.0002')
        setentry('system/controlDict', 'writeInterval', '0.0001')
        for key, value in {'oxygenStartTime': '0', 'controlStartTime': '0',
                           'sampleInterval': '0.0001', 'demandChangeTime': '0.0001'}.items():
            setentry('constant/bioProperties', key, '[0 0 1 0 0 0 0] ' + value)
        if args.reuse_mesh:
            source = args.reuse_mesh.resolve()
            if (source / 'Allmesh').read_bytes() != (case / 'Allmesh').read_bytes():
                raise RuntimeError('Mesh reuse refused: Allmesh recipe differs')
            if (source / 'les-mesh-profile').read_text().strip() != args.profile:
                raise RuntimeError('Mesh reuse refused: profile differs')
            source_processors = list(source.glob('processor[0-9]*'))
            if len(source_processors) != args.ranks:
                raise RuntimeError('Mesh reuse refused: rank count differs')
            for geometry in (case / 'constant/geometry').glob('*.obj'):
                if geometry.read_bytes() != (source / 'constant/geometry' / geometry.name).read_bytes():
                    raise RuntimeError('Mesh reuse refused: geometry differs')
            # Only copy initial fields and the fixed mesh, never evolved snapshots.
            shutil.copytree(source / 'constant/polyMesh', case / 'constant/polyMesh')
            shutil.rmtree(case / '0')  # owned, freshly prepared destination only
            shutil.copytree(source / '0', case / '0')
            for processor in source_processors:
                for part in ('constant', '0'):
                    shutil.copytree(processor / part, case / processor.name / part)
            for name in ('blockMeshDict', 'snappyHexMeshDict', 'meshQualityDict'):
                shutil.copy2(source / 'system' / name, case / 'system' / name)
            shutil.copy2(source / 'log.checkMesh', case / 'log.checkMesh')
            print('Reused identical retained mesh:', source, flush=True)
        else:
            run('mesh', ['bash', './Allmesh'], case)
    mesh = (case / 'log.checkMesh').read_text()
    print(mesh, flush=True)
    # Concavity alone is retained as an explicit LES caveat, never hidden as
    # a full geometry pass. All other extended check failures remain blockers.
    failed = re.search(r'Failed (\d+) mesh checks', mesh)
    concave = re.search(r'Concave cells.*number of cells:\s*(\d+)', mesh)
    concavity_only = failed and int(failed[1]) == 1 and concave
    if 'Mesh OK' not in mesh and not concavity_only:
        raise RuntimeError('Extended mesh audit has defects beyond concave cells')
    run('basic-mesh-check', ['mpirun', '-np', str(args.ranks), 'checkMesh',
                            '-parallel', '-constant', '-allTopology'], case)
    basic_mesh = (output / 'basic-mesh-check.log').read_text()
    if 'Mesh OK' not in basic_mesh:
        raise RuntimeError('Basic mesh validity/topology check failed')
    if not args.existing_case:
        run('solve', ['bash', './Allrun'], case)
        run('restart', ['bash', './Allrestart', '0.0004'], case)
    solver = (case / 'log.bioTankControlFoam').read_text()
    restart_logs = list(case.glob('log.restart.*'))
    segments = [solver] + [p.read_text() for p in restart_logs if not p.name.endswith('.reconstruct')]
    for segment in segments:
        print('Courant/timing audit:', '\n'.join(line for line in segment.splitlines()
              if any(t in line for t in ('Courant Number', 'Starting time loop', 'Time =', 'bioActuators:'))), flush=True)
    # Report constructor diagnostics separately. Gate EVERY advancing-step
    # Courant value, including the first preSolve call after actuator setup.
    if any('Starting time loop' not in segment for segment in segments):
        raise RuntimeError('Missing solver time-loop marker')
    history = '\n'.join(segment.split('Starting time loop', 1)[1] for segment in segments)
    startup_history = '\n'.join(segment.split('Starting time loop', 1)[0] for segment in segments)
    for model in ('SmagorinskyZhang', 'continuousGasKEqn', 'Oxygen integration: midpoint'):
        if model not in solver:
            raise RuntimeError('LES model not confirmed in solver log: ' + model)
    rows = []
    for path in sorted(case.glob('postProcessing/bioControl/*/oxygenBalance.csv')):
        with path.open() as stream:
            rows.extend({k: float(v) for k, v in row.items()} for row in csv.DictReader(stream))
    if not rows or abs(max(r['time_s'] for r in rows) - .0004) > 1e-9:
        raise RuntimeError('Missing final oxygen balance at 0.0004 s')
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
    if converted != [0, .0001, .0002, .0003, .0004]:
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

    # Foundation 13 names mesh.V() 'Vc'; accept V from older installations.
    volume_path = case / '0.0004/Vc'
    if not volume_path.exists():
        volume_path = case / '0.0004/V'
    volumes = internal(volume_path)
    centres = internal(case / '0.0004/C', vector=True)
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
    summary = {'status': 'passed_with_mesh_caveat' if concavity_only else 'passed' , 'scope': 'short integration smoke; not converged LES',
               'meshProfile': args.profile, 'ranks': args.ranks,
               'cells': re.findall(r'^\s*cells:\s*(\d+)', mesh, re.M),
               'deltaT_s': .0001, 'endTime_s': .0004,
               'maxCourant': max(courants),
               'constructorCourants': [float(v) for v in re.findall(r'Courant Number[^\n]*max:\s*([\d.eE+-]+)', startup_history)], 'maxOxygenBalanceResidual_mol': residual,
               'vtkTimes_s': converted,
               'openfoamVersion': os.environ.get('WM_PROJECT_VERSION'),
               'meshQuality': quality, 'filterWidthByRegion': sizes,
               'extendedGeometryAudit': 'concave cells flagged' if concavity_only else 'passed',
               'concaveCells': int(concave[1]) if concave else 0,
               'basicValidityAndTopology': 'passed',
               'wallDiagnostics': [str(p.relative_to(case)) for p in wall],
               'startupLiquidYPlusByPatch': wall_values,
               'wallAssessment': 'startup y+ only; developed-flow wall adequacy unverified'}
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == '__main__':
    main()
