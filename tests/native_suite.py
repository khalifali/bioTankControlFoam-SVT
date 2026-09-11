#!/usr/bin/env python3
"""Native closed-box chemistry, MPI/restart, and official tank mesh smoke checks.

These are numerical verification tests, not biological calibration or a claim
of fully developed aeration. All command logs remain in tests/results.
"""
import csv
import math
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'tests/results'

def run(case, name, *args):
    with (case / ('log.' + name)).open('w') as log:
        result = subprocess.run(args, cwd=case, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        print((case / ('log.' + name)).read_text()[-10000:], flush=True)
        for nested in sorted(case.glob('log.*')):
            content=nested.read_text(errors='replace')
            if 'FOAM FATAL' in content or 'error:' in content:
                print(str(nested),content[-12000:],flush=True)
        raise RuntimeError(f'{name} failed in {case}')

def setentry(case, file, key, value):
    subprocess.run(['foamDictionary', str(case / file), '-entry', key, '-set', value],
                   check=True, stdout=subprocess.DEVNULL)

def header(kind, name):
    return f'FoamFile {{ format ascii; class {kind}; object {name}; }}\n'

def prepare_box(name, ag=0.01):
    case = RESULTS / name
    subprocess.run(['bash', str(ROOT/'cases/aeratedTank/Allprepare'), str(case)], check=True)
    (case/'constant/geometry').rename(case/'constant/unusedGeometry')
    # Official function objects reference tank inlet/outlet patches absent here.
    functions=case/'system/functions'
    if functions.is_dir():shutil.rmtree(functions)
    elif functions.exists():functions.unlink()
    (case/'constant/MRFProperties').write_text(header('dictionary','MRFProperties'))
    setentry(case,'constant/g','value','(0 0 0)')
    for phase in ('liquid','gas'):
        (case/f'constant/momentumTransport.{phase}').write_text(
            header('dictionary',f'momentumTransport.{phase}')+'simulationType laminar;\n')
    (case/'constant/fvModels').write_text(header('dictionary','fvModels'))
    for path in (case/'0').iterdir():
        if not path.is_file(): continue
        if path.name.startswith('U.'):
            bc='{ walls { type fixedValue; value uniform (0 0 0); } }'
        elif path.name=='p':
            bc='{ walls { type calculated; value uniform 101300; } }'
        elif path.name=='p_rgh':
            bc='{ walls { type fixedFluxPressure; value uniform 101300; } }'
        else:
            bc='{ walls { type zeroGradient; } }'
        setentry(case,str(path.relative_to(case)),'boundaryField',bc)
    setentry(case,'0/alpha.gas','internalField',f'uniform {ag}')
    setentry(case,'0/alpha.liquid','internalField',f'uniform {1-ag}')
    for key,value in {'actuatorsEnabled':'false','controller':'constant',
        'oxygenStartTime':'[0 0 1 0 0 0 0] 0.002','controlStartTime':'[0 0 1 0 0 0 0] 0.002',
        'sampleInterval':'[0 0 1 0 0 0 0] 0.001',
        'measurements':'{ centre { position (0.4 0.4 0.4); } }'}.items():
        setentry(case,'constant/bioProperties',key,value)
    setentry(case,'system/fvSolution','PIMPLE/pRefCell','0')
    setentry(case,'system/fvSolution','PIMPLE/pRefValue','101300')
    setentry(case,'system/fvSolution','PIMPLE/correctPhi','no')
    setentry(case,'system/controlDict','endTime','0.01')
    setentry(case,'system/controlDict','writeInterval','0.005')
    setentry(case,'system/decomposeParDict','numberOfSubdomains','2')
    setentry(case,'system/decomposeParDict','method','simple')
    setentry(case,'system/decomposeParDict','simpleCoeffs','{ n (2 1 1); }')
    (case/'system/blockMeshDict').write_text(header('dictionary','blockMeshDict')+'''
convertToMeters 1;
vertices ((0 0 0)(1 0 0)(1 1 0)(0 1 0)(0 0 1)(1 0 1)(1 1 1)(0 1 1));
blocks (hex (0 1 2 3 4 5 6 7) (4 4 4) simpleGrading (1 1 1));
edges ();
boundary (walls { type wall; faces ((0 4 7 3)(1 2 6 5)(0 1 5 4)(3 7 6 2)(0 3 2 1)(4 5 6 7)); });
''')
    run(case,'blockMesh','blockMesh')
    return case

def table(case, name, segment='0'):
    with (case/f'postProcessing/bioControl/{segment}/{name}.csv').open() as f:
        return [{k:float(v) for k,v in r.items()} for r in csv.DictReader(f)]

def check(case, ag=0.01):
    rows=table(case,'oxygenBalance')
    for r in rows:
        assert abs(r['residual_mol'])<1e-10, r
        assert r['liquidInventory_mol']>=0
    readings=table(case,'measurements')
    c=0.15
    # Independent bisection of the implicit reaction equation; zero slip gives Sh=2.
    a=2*2e-9/0.001 * (6*ag/0.001)/(1-ag)
    sat=1.175e-5*0.21*101300
    for r in readings:
        t=r['time_s']
        if t>0.002+1e-10:
            old=c;lo=0.;hi=max(old,sat)
            for _ in range(100):
                mid=(lo+hi)/2
                f=mid-old-0.001*(a*(sat-mid)-0.002*mid/(0.01+mid))
                if f>0:hi=mid
                else:lo=mid
            c=(lo+hi)/2
        assert abs(r['centre_mol_m3']-c)<1e-9,(r,c)
    print('PASS: closed-box liquid inventory, warm-up and independent chemistry',case.name,flush=True)

def main():
    RESULTS.mkdir(exist_ok=False)
    serial=prepare_box('serial')
    run(serial,'solver','foamRun');check(serial)
    plugin=RESULTS/'state-controller.so'
    subprocess.run(['g++','-std=c++17','-shared','-fPIC','-I'+str(ROOT/'src/controller'),
                    str(ROOT/'tests/StateController.C'),'-o',str(plugin)],check=True)
    parallel=prepare_box('parallel')
    setentry(parallel,'constant/bioProperties','controller','student')
    setentry(parallel,'constant/bioProperties','studentLibrary','"'+str(plugin)+'"')
    run(parallel,'decompose','decomposePar')
    run(parallel,'solver','mpirun','-np','2','foamRun','-parallel');check(parallel)
    for a,b in zip(table(serial,'oxygenBalance'),table(parallel,'oxygenBalance')):
        for key in a:assert abs(a[key]-b[key])<1e-10,(key,a,b)
    restart=prepare_box('restart')
    setentry(restart,'constant/bioProperties','controller','student')
    setentry(restart,'constant/bioProperties','studentLibrary','"'+str(plugin)+'"')
    setentry(restart,'system/controlDict','endTime','0.005')
    run(restart,'decompose','decomposePar')
    run(restart,'first','mpirun','-np','2','foamRun','-parallel')
    run(restart,'restart','bash','Allrestart','0.01')
    last=table(restart,'oxygenBalance','0.005')[-1]
    for key,v in table(parallel,'oxygenBalance')[-1].items():assert abs(v-last[key])<1e-10,(key,v,last[key])
    for rank in (0,1):
        def saved(case):
            return subprocess.check_output(['foamDictionary',str(case/f'processor{rank}/0.01/uniform/bioControlState'),
                                            '-entry','studentState','-value'],text=True).strip()
        assert saved(parallel)==saved(restart),(saved(parallel),saved(restart))
    print('PASS: serial/MPI agreement and checkpoint continuation',flush=True)

    dry=prepare_box('gasOnly',ag=1)
    run(dry,'solver','foamRun')
    for row in table(dry,'oxygenBalance'):
        assert abs(row['liquidInventory_mol'])<1e-12
        assert abs(row['cumulativeSupply_mol'])<1e-12
        assert abs(row['cumulativeUptake_mol'])<1e-12
        assert abs(row['residual_mol'])<1e-10
    for row in table(dry,'measurements'):
        assert row['centre_valid']==0 and math.isnan(row['centre_mol_m3'])
    print('PASS: gas-only cells have no uptake/transfer and probes report invalid',flush=True)

    # Optional real-geometry verification; can be selected separately after kernels.
    if os.environ.get('BIO_TANK_SMOKE','0')=='1':
        tank=RESULTS/'tank'
        subprocess.run(['bash',str(ROOT/'cases/aeratedTank/Allprepare'),str(tank)],check=True)
        setentry(tank,'system/controlDict','endTime','0.005')
        setentry(tank,'system/controlDict','writeInterval','0.005')
        setentry(tank,'constant/bioProperties','oxygenStartTime','[0 0 1 0 0 0 0] 0')
        setentry(tank,'constant/bioProperties','sampleInterval','[0 0 1 0 0 0 0] 0.001')
        setentry(tank,'constant/bioProperties','initialOmega','[0 0 -1 0 0 0 0] 20')
        setentry(tank,'constant/bioProperties','initialGasFlow','[0 3 -1 0 0 0 0] 0.001')
        setentry(tank,'constant/bioProperties','schedule','((0 20 0.001)(0.005 21 0.002))')
        run(tank,'mesh','bash','Allmesh')
        mesh_report=(tank/'log.checkMesh').read_text()
        assert 'Mesh OK' in mesh_report,mesh_report[-5000:]
        print('\n'.join(line for line in mesh_report.splitlines() if any(k in line for k in ('cells:', 'non-orthogonality','skewness','Mesh OK'))),flush=True)
        # Same official geometry/closure baseline, before adding oxygen/control.
        baseline=RESULTS/'hydrodynamicBaseline'
        shutil.copytree(tank,baseline)
        setentry(baseline,'system/controlDict','solver','multiphaseEuler')
        setentry(baseline,'system/controlDict','libs','()')
        setentry(baseline,'system/controlDict','endTime','0.002')
        run(baseline,'baseline','mpirun','-np','8','foamRun','-parallel')
        print('PASS: upstream multiphaseEuler on official mesh',flush=True)
        run(tank,'run','bash','Allrun')
        for row in table(tank,'oxygenBalance'):
            assert abs(row['residual_mol'])<1e-7,row
        command_rows=table(tank,'actuators')
        assert command_rows[-1]['appliedOmega_rad_s']>command_rows[0]['appliedOmega_rad_s']
        assert command_rows[-1]['appliedGasFlow_m3_s']>command_rows[0]['appliedGasFlow_m3_s']
        print('Actuator implementation:',flush=True)
        import re
        diagnostics=re.findall(r'bioActuators: omega=(\S+) actualInletGasFlow=(\S+) requestedAppliedFlow=(\S+)',(tank/'log.bioTankControlFoam').read_text())
        assert len(diagnostics)>=2
        for omega,actual,request in diagnostics:
            assert abs(float(actual)-float(request))<1e-8,(actual,request)
            print(omega,actual,request,flush=True)
        # Exercise a changing-speed restart as well as the closed-box state test.
        run(tank,'continuation','bash','Allrestart','0.007')
        for row in table(tank,'oxygenBalance','0.005'):
            assert abs(row['residual_mol'])<1e-7,row
        print('PASS: official tank mesh and short coupled RANS-MRF run',flush=True)

if __name__=='__main__':main()
