"""Workflow regression tests using simulated OpenFOAM utilities (no CFD runtime)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'cases/aeratedTank/foamToVTK.sh'
FIELDS = ('U.liquid', 'alpha.gas', 'oxygen.liquid', 'p', 'U.gas')
STUB = r'''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
args = sys.argv[1:]
case = Path(args[args.index('-case') + 1])
t = args[args.index('-time') + 1]
name = Path(sys.argv[0]).name
with (case / 'calls').open('a') as log:
    log.write(json.dumps([name, args]) + '\n')
if name == 'reconstructPar':
    if '-noFields' in args:
        (case / 'mesh-ready').touch()
    else:
        assert (case / 'mesh-ready').exists()
        dest = case / t
        dest.mkdir(exist_ok=True)
        for field in (case / 'processor0' / t).iterdir():
            if field.is_file():
                (dest / field.name).write_text('reconstructed')
else:
    assert '-useTimeName' in args
    active = case / ('active.' + t)
    active.touch()
    time.sleep(.08)
    count = len(list(case.glob('active.*')))
    with (case / 'concurrency').open('a') as log:
        log.write(str(count) + '\n')
    active.unlink()
    vtk = case / 'VTK'
    vtk.mkdir(exist_ok=True)
    (vtk / (case.name + '_' + t + '.vtk')).write_text('mock vtk output')
if os.environ.get('FAIL_TIME') == t and '-noFields' not in args:
    sys.exit(1)
'''


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.case = self.base / 'tank'
        (self.case / 'system').mkdir(parents=True)
        (self.case / 'system/controlDict').touch()
        shutil.copy2(SCRIPT, self.case / SCRIPT.name)
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        for command in ('reconstructPar', 'foamToVTK'):
            path = self.bin / command
            path.write_text(STUB)
            path.chmod(0o755)
        self.env = dict(os.environ, WM_PROJECT_VERSION='13',
                        PATH=str(self.bin) + os.pathsep + os.environ['PATH'])

    def fields(self, directory, names=FIELDS):
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            (directory / name).write_text('field')

    def run_script(self, *args, ok=True, **env):
        result = subprocess.run(['bash', str(self.case / SCRIPT.name), *args],
                                env=dict(self.env, **env), capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def calls(self):
        path = self.case / 'calls'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def entries(self):
        return json.loads((self.case / 'VTK/tank.vtk.series').read_text())['files']

    def decomposed(self):
        for processor in ('processor0', 'processor1'):
            for t in ('0', '0.5', '2', '1e1'):
                self.fields(self.case / processor / t)
        self.fields(self.case / '0')
        self.fields(self.case / '2', ('U.liquid',))  # partial reconstruction
        self.fields(self.case / '1e1')  # Allrun reconstructs the latest only

    def test_decomposed_partial_incremental_and_worker_limit(self):
        self.decomposed()
        self.run_script('2')
        calls = self.calls()
        recon = [args[args.index('-time') + 1] for command, args in calls
                 if command == 'reconstructPar' and '-noFields' not in args]
        self.assertCountEqual(recon, ['0.5', '2'])
        self.assertIn('-noFields', calls[0][1])
        self.assertEqual([entry['time'] for entry in self.entries()], [0, .5, 2, 10])
        counts = [int(n) for n in (self.case / 'concurrency').read_text().splitlines()]
        self.assertGreater(max(counts), 1)
        self.assertLessEqual(max(counts), 2)
        for t in ('0', '0.5', '2', '1e1'):
            self.assertTrue((self.case / t).is_dir())
            self.assertTrue((self.case / 'processor1' / t).is_dir())
        self.run_script('all', '2')
        self.assertEqual(calls, self.calls())

    def test_serial_and_series_without_source_times(self):
        for t in ('0', '.5', '2e1'):
            self.fields(self.case / t, tuple(f + '.gz' for f in FIELDS))
        self.run_script('vtk', '1')
        self.assertTrue(all(name == 'foamToVTK' for name, _ in self.calls()))
        for t in ('0', '.5', '2e1'):
            shutil.rmtree(self.case / t)
        self.run_script('series', WM_PROJECT_VERSION='')
        self.assertEqual([entry['time'] for entry in self.entries()], [0, .5, 20])

    def test_conversion_failure_retries_partial_output(self):
        self.fields(self.case / '1')
        self.run_script('all', ok=False, FAIL_TIME='1')
        self.assertFalse((self.case / 'VTK/tank.vtk.series').exists())
        self.run_script('series', ok=False)
        self.run_script('all')
        self.assertEqual(len(self.calls()), 2)
        self.assertEqual(len(self.entries()), 1)

    def test_reconstruction_failure_retries_even_if_files_exist(self):
        self.decomposed()
        self.run_script('reconstruct', '1', ok=False, FAIL_TIME='0.5')
        self.run_script('reconstruct', '1')
        calls = [args for name, args in self.calls() if name == 'reconstructPar'
                 and '-noFields' not in args and args[args.index('-time') + 1] == '0.5']
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.case / 'VTK').exists())

    def test_missing_processor_time_fails_before_reconstruction(self):
        self.decomposed()
        shutil.rmtree(self.case / 'processor1/2')
        self.run_script(ok=False)
        self.assertEqual(self.calls(), [])

    def test_invalid_arguments_help_and_empty_case(self):
        for args in [('all', '0'), ('series', '2'), ('oops',), ('2', '3')]:
            self.run_script(*args, ok=False)
        self.run_script('--help', WM_PROJECT_VERSION='')
        self.run_script(ok=False)
        self.run_script('all', ok=False, WM_PROJECT_VERSION='12')

    def test_existing_series_survives_failure_and_new_times_append(self):
        self.fields(self.case / '1')
        self.run_script()
        before = self.entries()
        self.fields(self.case / '2')
        self.run_script(ok=False, FAIL_TIME='2')
        self.assertEqual(before, self.entries())
        self.run_script()
        self.assertEqual([entry['time'] for entry in self.entries()], [1, 2])

    def test_case_lock(self):
        import fcntl
        logs = self.case / 'log.foamToVTK'
        logs.mkdir()
        with (logs / 'lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = self.run_script('series', ok=False)
            self.assertIn('already running', result.stderr)


if __name__ == '__main__':
    unittest.main()
