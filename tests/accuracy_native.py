#!/usr/bin/env python3
"""Verify midpoint temporal order in the native solver, not a reimplementation.

Usage: python3 tests/accuracy_native.py --output /absolute/new/results
Runs zero-flow 4^3 boxes: Monod uptake and a Neumann cosine diffusion mode.
The diffusion reference is exact for the *discrete* spatial operator, so spatial
error cannot masquerade as time error. These tests do not certify phase order.
"""
import argparse
import json
import math
from pathlib import Path
import native_suite as native


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native.RESULTS = args.output.resolve()
    native.RESULTS.mkdir(parents=True, exist_ok=False)
    errors = {}

    def prepare(name, dt, diffusion=False):
        case = native.prepare_box(name, ag=0)
        for key, value in {'oxygenIntegration': 'midpoint',
                           'oxygenStartTime': '[0 0 1 0 0 0 0] 0',
                           'controlStartTime': '[0 0 1 0 0 0 0] 0',
                           'sampleInterval': f'[0 0 1 0 0 0 0] {dt}',
                           'biomass': '[1 -3 0 0 0 0 0] 1',
                           'specificUptake': '[ -1 0 -1 0 1 0 0] '+('0' if diffusion else '0.2'),
                           'molecularDiffusivity': '[0 2 -1 0 0 0 0] '+('0.2' if diffusion else '2e-9'),
                           }.items():
            native.setentry(case, 'constant/bioProperties', key, value)
        for key, value in {'deltaT': str(dt), 'endTime': '0.4', 'writeInterval': '0.2',
                           'writePrecision': '16'}.items():
            native.setentry(case, 'system/controlDict', key, value)
        native.setentry(case, 'system/fvSchemes', 'ddtSchemes', '{ default backward; }')
        native.setentry(case, 'system/fvSchemes', 'divSchemes/div(alphaPhi.liquid,oxygen.liquid)', 'Gauss limitedLinear 1')
        native.setentry(case, 'system/fvSchemes', 'laplacianSchemes/laplacian(oxygenDiffusivity,oxygen.liquid)', 'Gauss linear corrected')
        if diffusion:
            values = [.15+.02*math.cos(math.pi*(i+.5)/4) for k in range(4) for j in range(4) for i in range(4)]
            native.setentry(case, '0/oxygen.liquid', 'internalField',
                            'nonuniform List<scalar> 64 ('+' '.join(map(str, values))+')')
        return case

    def monod(t):
        target = .15+.01*math.log(.15)-.2*t
        lo, hi = 1e-15, .15
        for _ in range(100):
            c = (lo+hi)/2
            if c+.01*math.log(c) > target:
                hi = c
            else:
                lo = c
        return (lo+hi)/2

    def validate(case, segment='0'):
        balance = native.table(case, 'oxygenBalance', segment)
        assert all(abs(r['residual_mol']) < 1e-10 for r in balance), balance[-1]
        assert all(r['liquidInventory_mol'] >= 0 for r in balance)
        return native.table(case, 'measurements', segment)[-1]['centre_mol_m3']

    for problem in ('monod', 'diffusion'):
        observed = []
        for dt in (.1, .05, .025):
            case = prepare(f'{problem}-{dt}', dt, problem == 'diffusion')
            native.run(case, 'solver', 'foamRun')
            final = validate(case)
            if problem == 'monod':
                exact = monod(.4)
            else:
                lam = 4*.2*math.sin(math.pi/8)**2/(.25**2)
                exact = .15+.02*math.cos(math.pi*.375)*math.exp(-lam*.4)
            observed.append(abs(final-exact))
        orders = [math.log(a/b, 2) for a, b in zip(observed, observed[1:])]
        assert all(1.85 < p < 2.15 for p in orders), (problem, observed, orders)
        errors[problem] = {'deltaT_s': [.1, .05, .025], 'errors_mol_m3': observed, 'observedOrder': orders}
        print(problem, errors[problem], flush=True)

    # A one-step method must reproduce continuation without hidden old-time state.
    serial = prepare('restart-reference', .025)
    native.run(serial, 'solver', 'foamRun')
    reference = validate(serial)
    restart = prepare('restart-mpi', .025)
    native.setentry(restart, 'system/controlDict', 'endTime', '0.2')
    native.run(restart, 'decompose', 'decomposePar')
    native.run(restart, 'first', 'mpirun', '-np', '2', 'foamRun', '-parallel')
    native.run(restart, 'restart', 'bash', 'Allrestart', '0.4')
    actual = validate(restart, '0.2')
    assert abs(actual-reference) < 1e-10, (actual, reference)
    errors['restartMpiDifference_mol_m3'] = abs(actual-reference)
    errors['scope'] = 'oxygen temporal order with stationary phases; full Euler-Euler order not established'
    (native.RESULTS/'summary.json').write_text(json.dumps(errors, indent=2)+'\n')
    print(json.dumps(errors, indent=2), flush=True)


if __name__ == '__main__':
    main()
