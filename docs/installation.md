# Installation and activation

**Using a university account without sudo?** Start with the
[step-by-step Ubuntu 24.04 student guide](installation-no-sudo.md), including
home-directory dependencies, activation, verification and ParaView. The default
setup below uses sudo for system dependencies.

Target Ubuntu 24.04, Foundation OpenFOAM 13, GCC and system OpenMPI. The pinned
OpenFOAM revision is 18870c24d21c6b982e2cdec27b2f59738cca5f90 and ThirdParty revision
ba1e22d69da30817a29cedfde3ea276719bec4e8. Do not mix OpenCFD releases or libraries
from another OpenFOAM installation in the same terminal.

## First time: install and activate once

Open a fresh Bash terminal and clone using your configured GitHub SSH key:

```bash
git clone git@github.com:khalifali/bioTankControlFoam-SVT.git
cd bioTankControlFoam-SVT
./scripts/setup-first-time.sh --jobs 4
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
echo "$WM_PROJECT_VERSION"  # Expected: 13
command -v foamRun
command -v bioTankControlFoam
```

Run setup as your normal user. It uses sudo only for apt dependencies, then
compiles in your home directory. Source compilation can take hours; reduce
`--jobs` to 1 or 2 if compilation exhausts memory. ParaView is installed separately.
Setup creates no mesh and starts no simulation.

The commented standalone `scripts/setup-first-time.sh` delegates compilation
to the existing installer, so both entry points use the same pinned revisions.
It defaults to SSH for upstream downloads too. `--git-protocol https` is available
for users without GitHub SSH access. `--skip-deps` avoids apt/sudo when an
administrator has already installed the dependencies listed in the installer.

Use `--prefix /absolute/path` to choose another installation directory; source
the activation file at the exact path printed after a successful build.
Paths must not contain whitespace. Rerunning setup reuses matching source
checkouts and incremental build output; it rejects differing revisions or
tracked source edits rather than resetting them. Build logs are in the prefix:
`log.OpenFOAM13` and `log.bioTankControlFoam`.

Execute setup, **do not source it**. An executed script cannot activate its
parent terminal, so the separate `source` step is required after installation
and in every new terminal. Shell startup files are not changed automatically.

## Later: activate the environment only

In each new Bash terminal, run:

```bash
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
```

This activates the installed OpenFOAM 13 environment and this project's launcher.
It can be run from any directory. With a custom installation `--prefix`, use
that directory's `activate-bioTankControlFoam.sh` instead.

For normal use, there is no need to clone again, rerun the setup script, install
packages, or compile anything. You can now enter your case directory and run
its scripts. Recompile only when you change compiled source code or install
an update that requires rebuilding.

## Existing installation and advanced options

Run scripts/install-openfoam13.sh --help for options. With --foam-dir, the script
reports the source revision, reuses the existing Foundation OpenFOAM 13 build,
and compiles this module/controller. Without it, the installer clones pinned
upstream sources and calls their full Allwmake. --install-deps explicitly opts
into apt/sudo dependency installation. No LAMMPS or O-grid mesher is needed.

Source the generated activate-bioTankControlFoam.sh in each new Bash terminal.
It activates the chosen OF installation and project launcher. The libraries use
FOAM_USER_LIBBIN, so rebuilding this project replaces its own libraries there;
do not rebuild while a simulation using those libraries is running.

For an already active installation, ./Allwmake followed by
source scripts/activate.sh is sufficient. The run command is foamRun with the
case's solver selection, or the equivalent bioTankControlFoam launcher.

Allprepare copies the official geometry and case from the active Foundation
OpenFOAM 13 installation. A different or unavailable Git revision produces an
informational message and does not block preparation. The required tutorial
files must be installed. Existing destinations are rejected, preserving
local case edits and results. The generated run contains the upstream revision.

## Using your existing Foundation OpenFOAM 13

You do not need to reinstall OpenFOAM just because its Git revision differs
from the revision used for our tests. The revision message is informational;
other Foundation OpenFOAM 13 revisions should normally work, although they
have not all been tested. Non-Git installations can also be used.

```bash
# Run from the bioTankControlFoam repository root.
./scripts/install-openfoam13.sh --foam-dir /path/to/OpenFOAM-13
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
```

This compiles the project against your existing installation and creates its
activation file. It does not rebuild or modify the OpenFOAM sources. Its build
tools, development headers/libraries and the official aeratedStirredTankMRF
tutorial must be available. Rebuild this project when switching installations.
The optional fresh-install route continues to use pinned upstream revisions.

## Rebuild after controller or solver changes

Activation sets environment variables; it does not compile edited code.
Stop simulations using these libraries, then run:

```bash
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
cd "$BIOTANK_ROOT"
./Allwmake
```

This builds the solver module and student controller against the active OF13
installation, without rebuilding OpenFOAM. Wait for successful compilation
before starting or restarting a case. Case-dictionary edits need no compilation.
Use the generated activation path if you chose a custom installation prefix.

