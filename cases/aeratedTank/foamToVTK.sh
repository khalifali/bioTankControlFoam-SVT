#!/usr/bin/env bash
# Adapted from LAMFOAM's postprocessing/foamvtk.sh workflow for Foundation 13.
# Self-contained so Allprepare can copy it into each run directory.
#
# USAGE (after the solver has stopped; activate Foundation OpenFOAM 13 first)
#   ./foamToVTK.sh all 8        reconstruct missing/partial times, convert, index
#   ./foamToVTK.sh 4            shorthand for "all 4"
#   ./foamToVTK.sh reconstruct 4  reconstruct only; no VTK conversion
#   ./foamToVTK.sh vtk 4        convert already reconstructed/serial times, index
#   ./foamToVTK.sh series       rebuild index from existing VTK; no OF required
#   ./foamToVTK.sh --help
# No arguments means "all 8". Requires Python 3.9+ on Linux.
#
# LOCATION AND OUTPUT
# Allprepare copies this file to new run directories. For an existing run,
# copy cases/aeratedTank/foamToVTK.sh into its root (beside system/constant).
# The case is ALWAYS the directory containing this script, not the current
# working directory. Example: in runs/tank, run ./foamToVTK.sh all 8 and open
# VTK/tank.vtk.series in ParaView. The basename follows the case directory name.
# One index covers all completed internal-mesh VTK times, sorted numerically;
# patch output is separate. Do not rename the case between exports.
#
# PSEUDO-PARALLEL WORK AND RERUNS
# Mesh preparation is serial; each worker runs a serial OpenFOAM utility on a
# separate saved time (no MPI). Reduce workers if memory is limited. This helper
# targets the fixed-mesh, single-region tank with processorN storage, not
# collated processors* storage. It checks multiphase fields, including oxygen.
# Complete reconstructed times and nonempty completed VTK files are skipped.
# Failed jobs leave retry markers; per-time logs are in log.foamToVTK/.
# All original, reconstructed and processor time directories are preserved.
# If fields at an already exported time change, remove VTK/<case>_<time>.vtk
# and rerun to refresh it. "series" also includes retained older VTK output
# whose original time directories no longer exist.
# See docs/aerated-tank-walkthrough.md in the repository for the full workflow.
set -euo pipefail
exec python3 - "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" "$@" <<'PY'
import concurrent.futures
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main():
    case = Path(sys.argv[1])
    args = sys.argv[2:]
    usage = """Usage: ./foamToVTK.sh [all|reconstruct|vtk] [workers]
       ./foamToVTK.sh series
       ./foamToVTK.sh [workers]       # shorthand for all

Default: all, 8 workers. Run after the solver has stopped.
Each worker runs a serial utility for a separate saved time (no MPI).
all: reconstruct missing fields, convert, then write VTK/<case>.vtk.series.
reconstruct: reconstruct only. vtk: convert existing root times only.
series: rebuild the index from existing internal-mesh VTK files only.
All original and reconstructed time directories are preserved.
Requires Python 3; all/reconstruct/vtk require active Foundation OpenFOAM 13.
"""
    if args and args[0] in ("-h", "--help", "help"):
        print(usage)
        return
    mode = "all"
    if args and args[0] in ("all", "reconstruct", "vtk", "series"):
        mode = args.pop(0)
    workers = 8
    if args:
        if mode == "series" or len(args) != 1 or not re.fullmatch(r"[1-9][0-9]*", args[0]):
            raise ValueError(usage)
        workers = int(args[0])
    if not (case / "system/controlDict").is_file():
        raise ValueError("Use the script in a prepared run directory (missing system/controlDict).")
    if mode != "series" and os.environ.get("WM_PROJECT_VERSION") != "13":
        raise ValueError("Activate Foundation OpenFOAM 13 first.")

    logs = case / "log.foamToVTK"
    logs.mkdir(exist_ok=True)
    # Keep the lock file: unlinking it could allow a second lock on a new inode.
    lock = (logs / "lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError("Another foamToVTK.sh is already running for this case.") from None

    number = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

    def times(directory):
        return sorted((p.name for p in directory.iterdir()
                       if p.is_dir() and number.fullmatch(p.name)), key=float)

    def fields(directory):
        return {p.name.removesuffix(".gz") for p in directory.iterdir() if p.is_file()}

    def complete(t, expected):
        directory = case / t
        return directory.is_dir() and expected <= fields(directory)

    vtk = case / "VTK"
    prefix = case.name + "_"

    def dataset(t):
        return vtk / (prefix + t + ".vtk")

    def pending(t):
        return logs / ("pending." + t)

    def converted(t):
        path = dataset(t)
        return path.is_file() and path.stat().st_size > 0 and not pending(t).exists()

    def run(command, label):
        logfile = logs / (label + ".log")
        with logfile.open("w") as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f"{command[0]} failed; see {logfile}")

    def parallel(function, selected):
        # Every future is joined before errors propagate or the case lock is released.
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(function, t) for t in selected]
            for future in futures:
                future.result()

    def require(command):
        if not shutil.which(command):
            raise ValueError(f"Missing {command}; activate Foundation OpenFOAM 13.")

    processors = sorted(p for p in case.iterdir()
                        if p.is_dir() and re.fullmatch(r"processor[0-9]+", p.name))
    if any(p.is_dir() and re.fullmatch(r"processors[0-9]+.*", p.name) for p in case.iterdir()):
        raise ValueError("Collated processors* storage is unsupported; use the tank's processorN layout.")
    required = {"U.liquid", "alpha.gas", "oxygen.liquid"}
    if mode in ("all", "reconstruct") and processors:
        if not (case / "processor0").is_dir():
            raise ValueError("Missing processor0.")
        source = sorted({t for p in processors for t in times(p)}, key=float)
        selected = []
        for t in source:
            if any(not (p / t).is_dir() for p in processors):
                raise ValueError(f"Time {t} is missing on a processor; stop the solver and check the write.")
            expected = fields(case / "processor0" / t)
            if not required <= expected or any(not expected <= fields(p / t) for p in processors):
                raise ValueError(f"Incomplete processor fields at time {t}.")
            if not complete(t, expected) or (logs / ("reconstruct.pending." + t)).exists():
                selected.append(t)
        if selected:
            require("reconstructPar")
            # Mesh/addressing writes must finish before concurrent field reconstruction.
            print("Preparing meshes serially for:", ", ".join(selected), flush=True)
            run(["reconstructPar", "-case", str(case), "-time", ",".join(selected),
                 "-noFields", "-noLagrangian", "-noSets"], "mesh")

            def reconstruct(t):
                marker = logs / ("reconstruct.pending." + t)
                marker.touch()
                # An existing VTK may predate a partially reconstructed field set.
                pending(t).touch()
                run(["reconstructPar", "-case", str(case), "-time", t,
                     "-noLagrangian", "-noSets"], "reconstruct." + t)
                if not complete(t, fields(case / "processor0" / t)):
                    raise RuntimeError(f"Reconstruction left missing fields at {t}.")
                marker.unlink()

            parallel(reconstruct, selected)
        else:
            print("All processor times already have reconstructed fields.")
    elif mode in ("all", "reconstruct"):
        print("Serial case: reconstruction is unnecessary.")

    if mode in ("all", "vtk"):
        require("foamToVTK")
        vtk.mkdir(exist_ok=True)
        selected = []
        for t in times(case):
            if not complete(t, required):
                raise ValueError(f"Incomplete tank fields at root time {t}; reconstruct them first.")
            if (logs / ("reconstruct.pending." + t)).exists():
                raise ValueError(f"Interrupted reconstruction at {t}; run reconstruct or all first.")
            if not converted(t):
                selected.append(t)
        print(f"Converting {len(selected)} times with up to {workers} workers.", flush=True)

        def convert(t):
            pending(t).touch()
            # -time preserves existing VTK output; -useTimeName avoids index collisions.
            run(["foamToVTK", "-case", str(case), "-time", t, "-useTimeName"], "vtk." + t)
            if not dataset(t).is_file() or dataset(t).stat().st_size == 0:
                raise RuntimeError(f"No nonempty internal-mesh VTK produced for {t}.")
            pending(t).unlink()

        parallel(convert, selected)

    if mode in ("all", "vtk", "series"):
        entries = []
        for path in vtk.glob("*.vtk"):
            if not path.name.startswith(prefix):
                continue
            t = path.name[len(prefix):-4]
            if number.fullmatch(t) and converted(t):
                value = float(t)
                if not math.isfinite(value):
                    raise ValueError(f"Non-finite time: {t}")
                entries.append({"name": path.name, "time": value})
        entries.sort(key=lambda entry: (entry["time"], entry["name"]))
        if not entries:
            raise ValueError("No completed internal-mesh VTK datasets found; index not changed.")
        series = vtk / (case.name + ".vtk.series")
        temporary = series.with_suffix(".series.tmp")
        temporary.write_text(json.dumps({"file-series-version": "1.0", "files": entries},
                                        indent=2, allow_nan=False) + "\n")
        temporary.replace(series)
        print(f"Open {series} in ParaView ({len(entries)} times).")


try:
    main()
except (ValueError, RuntimeError, OSError) as error:
    sys.exit(str(error))
PY
