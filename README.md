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
