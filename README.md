# bioTankControlFoam-SVT

Student edition for learning CFD oxygen transport and developing control strategies.
The solver and activation names remain `bioTankControlFoam`.

Educational dissolved-oxygen control framework for OpenFOAM Foundation 13,
based on the official `multiphaseEuler/aeratedStirredTankMRF` air–water tank.
The first model combines RANS–MRF flow, liquid oxygen transport, bubble-to-liquid
transfer and prescribed microbial uptake. It exposes sparse oxygen measurements
to a separate student controller commanding stirrer speed and inlet gas flow.

New to the model? Start with the [student introduction](docs/model.md#quick-introduction-for-students)
for a short explanation of the two-fluid model, turbulence, stirring and oxygen uptake.

## Build and activate

**No sudo access?** Follow the [Ubuntu 24.04 installation guide for students](docs/installation-no-sudo.md).
It installs the build tools, OpenFOAM and this project in your own account using HTTPS.

### First time: install and activate

Run these commands once on Ubuntu 24.04:

```bash
git clone git@github.com:khalifali/bioTankControlFoam-SVT.git
cd bioTankControlFoam-SVT
./scripts/setup-first-time.sh --jobs 4
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
```

The separate setup script installs system dependencies using sudo, downloads
the pinned OpenFOAM sources over SSH, and builds OpenFOAM and this project.
GitHub SSH access must already be configured. It does not run the tank case.

### Later: activate only

After installation, open a new Bash terminal and run only:

```bash
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
```

This activates both OpenFOAM 13 and bioTankControlFoam. You do not need to
clone again, rerun setup, or recompile for normal use. If you chose a custom
`--prefix`, use the activation path printed by the installer.

### If OpenFOAM is already installed

Reuse an existing Foundation OpenFOAM 13 installation:

```bash
./scripts/install-openfoam13.sh --foam-dir /path/to/OpenFOAM-13
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
```

The full upstream build can take substantial time. Reusing an existing
installation compiles only this project. The installer does not edit `.bashrc`.
You may add the printed activation command yourself. See [installation](docs/installation.md).

## Prepare and run the tank

Read the [detailed case walkthrough](docs/aerated-tank-walkthrough.md) for the
geometry, startup timeline, oxygen assumptions, measurements and ParaView steps.
While the solver is running, create `abort` in the run directory (`touch abort`)
to save and stop at the next scheduled write. Newly prepared cases enable this;
see the walkthrough to update an existing case.

```bash
./cases/aeratedTank/Allprepare "$PWD/runs/tank"
cd runs/tank
# Inspect constant/bioProperties and system/controlDict first.
./Allmesh
./Allrun
# Later, continue to 90 seconds without deleting the checkpoint:
./Allrestart 90
```

Preparation copies the official tutorial from the active OF13 installation,
then overlays the commented case files in this repository. The resulting run
directory contains all geometry, initial fields and dictionaries for inspection;
there is no private mesher dependency or hidden case template engine.

`Allclean --yes` deletes generated results inside a prepared run only. The source
case and `0.backup` are preserved. Open `mesh.foam` in ParaView after reconstruction,
select `internalMesh`, and display `alpha.gas`, `U.liquid` or `oxygen.liquid`.
Use liquid-dominated regions when displaying dissolved oxygen; dry-cell values
are numerical placeholders, not gas oxygen concentrations.

## Export all saved times to VTK

After the solver has stopped, activate OpenFOAM 13 and run in the prepared case:

```bash
cd runs/tank
./foamToVTK.sh all 8
```

`Allprepare` includes this script in new runs. For an existing run, copy
`cases/aeratedTank/foamToVTK.sh` from this repository into the run directory first.
The script always operates on the directory containing the script, regardless of
where you invoke it. It requires Python 3 (3.9 or newer).

This adapts LAMFOAM's `postprocessing/foamvtk.sh` workflow to the tank's case
layout and multiphase fields. It reconstructs missing or partial root times from
`processorN` directories, prepares meshes serially, then runs up to eight serial
utilities concurrently on different saved times. This is pseudo-parallel work
across times; it does not launch MPI. Use fewer workers if memory is limited.
The completeness check includes all files at the top level of `processor0/<time>`
(including compressed fields), and requires `U.liquid`, `alpha.gas` and
`oxygen.liquid`. Reconstruction and VTK conversion include all available fields.

Open `VTK/tank.vtk.series` in ParaView (replace `tank` with your run directory's
name). This single index spans all completed internal-mesh VTK files, sorted by
physical time, including output retained from previous invocations. Patch VTK
files are also written by OpenFOAM but are not included in the internal-mesh index.
All processor, original and reconstructed time directories are preserved.

```bash
./foamToVTK.sh 4                 # same as all 4; default is all 8
./foamToVTK.sh reconstruct 4     # only reconstruct missing fields
./foamToVTK.sh vtk 4             # only convert existing reconstructed/serial times
./foamToVTK.sh series            # rebuild the index without OpenFOAM utilities
```

Reruns skip complete reconstructed times and existing nonempty VTK files; failed
jobs leave markers so their output is retried. Logs and markers are stored in
`log.foamToVTK/`, with one log per utility/time. The series index is replaced only
after successful conversion. If you deliberately change fields at an already
converted time, remove that time's `VTK/<case>_<time>.vtk` and rerun to refresh it.
Do not rename a case between exports: VTK filenames use the case directory name.
The helper targets this fixed-mesh, single-region tank and its standard
`processorN` storage; collated `processors*` storage is rejected explicitly.

## LES exercise

A separate [LES-MRF exercise](docs/les-exercise.md) provides multiphase LES models,
volume-refined meshing profiles, higher-order numerics and native verification.
It uses coupled midpoint oxygen integration and BDF2 where supported by the flow
solver. OpenFOAM's internal phase-fraction update remains Euler-based: this is
not a fully second-order two-fluid solver. The default RANS exercise remains
unchanged. Read the LES mesh, wall-treatment and accuracy limits before using
its output.

## Read before interpreting results

- [Complete parameter reference](docs/aerated-tank-walkthrough.md#complete-bioproperties-parameter-reference)
- [Output files and units](docs/aerated-tank-walkthrough.md#understanding-postprocessing-files-and-units)
- [Rebuilding after source changes](docs/installation.md#rebuild-after-controller-or-solver-changes)


- [Physics, units and limits](docs/model.md)
- [Controller and measurements](docs/controller.md)
- [Verification and validation](docs/validation.md)

The default tank uses a prescribed aeration schedule, not feedback. The student
template holds applied commands; an optional PI example is provided separately.
Parameters and gains are educational starting values, not a calibrated culture.
The transfer model assumes fixed air oxygen composition and does not conserve a
transported gas oxygen inventory. No particle, biomass-growth, sliding-mesh or
wall-resolved LES model is included in this first version.
