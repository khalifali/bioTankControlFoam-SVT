# Ubuntu 24.04: install in your own account (no sudo)

This guide installs **OpenFOAM Foundation 13, the bioTank solver and the student
controller** under your home directory. It also shows how to view results with
ParaView. You do not need an administrator password or a GitHub account.

Use a normal **Bash terminal** on an Intel/AMD 64-bit Ubuntu 24.04 computer
(`uname -m` should print `x86_64`). Start a fresh terminal without another
OpenFOAM or Conda environment activated. Use directory names without spaces.
Allow several hours for the first build and plan for at least 20 GB of free
disk space before storing simulation results. These are planning allowances,
not a guarantee that a large LES run will fit on your computer.

Copy each block in order. **If a step reports an error, stop there** and use the
troubleshooting table below.

## 1. Install the build tools in your account

Micromamba is a small package manager. Here it supplies the compiler, OpenMPI,
Python and development libraries without installing Ubuntu system packages.
The download below uses Ubuntu's `wget`, `tar` and bzip2 support.

```bash
mkdir -p "$HOME/biotank-tools"
cd "$HOME/biotank-tools"
wget -O micromamba.tar.bz2 https://micro.mamba.pm/api/micromamba/linux-64/latest
tar -xjf micromamba.tar.bz2 bin/micromamba

export MAMBA_ROOT_PREFIX="$HOME/biotank-tools/mamba"
eval "$("$HOME/biotank-tools/bin/micromamba" shell hook -s bash)"
micromamba create -y -n biotank -c conda-forge --strict-channel-priority \
    'gcc=13' 'gxx=13' 'openmpi=4.1' 'python=3.12' \
    make flex bison cmake git zlib readline ncurses xorg-libxt curl
micromamba activate biotank
```

If `wget` is unavailable, download [this same archive](https://micro.mamba.pm/api/micromamba/linux-64/latest)
in your browser, save it as `~/biotank-tools/micromamba.tar.bz2`, and continue
with the `tar` command. This guide targets `x86_64`; do not use that binary on
an ARM computer. See the [official Micromamba installation instructions](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html)
for other architectures.

Check that the tools are available:

```bash
command -v gcc g++ mpicc mpirun git python3
gcc --version
mpirun --version
```

The printed tool paths should be inside
`$HOME/biotank-tools/mamba/envs/biotank/bin`. This keeps the compiler and MPI
libraries together. Do not switch to a different MPI installation later.

## 2. Download and build the project

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/khalifali/bioTankControlFoam-SVT.git
cd bioTankControlFoam-SVT
./scripts/setup-first-time.sh --skip-deps --git-protocol https --jobs 2
```

**Keep `--skip-deps`: it prevents all apt/sudo calls.** The tools from step 1
supply the dependencies. HTTPS avoids SSH-key setup. The script downloads the
repository's pinned OpenFOAM 13 and ThirdParty sources, builds them, then builds
the solver and controller. It does not mesh or run a tank.

`--jobs 2` means two compiler jobs; it is independent of the number of simulation
processors. Use `--jobs 1` if memory is limited. Wait for **Build complete**.
The build is stored in `~/OpenFOAM-bioTank`; do not move the project or dependency
directories afterwards because activation refers to their paths.

## 3. Activate and check the installation

With the `biotank` Micromamba environment still active:

```bash
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
echo "$WM_PROJECT_VERSION"
command -v foamRun bioTankControlFoam snappyHexMesh foamToVTK
cd "$BIOTANK_ROOT"
./tests/Alltest
```

The version must be **13** and each command must have a path. `Alltest` runs
quick code and exporter checks; it does not run a CFD simulation. This project
requires **Foundation OpenFOAM 13** from openfoam.org; OpenCFD releases such as
v2412 are a different distribution.

For an optional native solver check in small boxes (two MPI processes):

```bash
BIO_TANK_SMOKE=0 ./tests/Allnative
```

This checks serial, parallel and restart behaviour without meshing the tank.
It needs a fresh `tests/results` directory; preserve earlier results by renaming
that directory before repeating it. See [verification](validation.md) for details.

## 4. In every new terminal

Run these four lines, in this order, before building, meshing, running or exporting:

```bash
export MAMBA_ROOT_PREFIX="$HOME/biotank-tools/mamba"
eval "$("$HOME/biotank-tools/bin/micromamba" shell hook -s bash)"
micromamba activate biotank
source "$HOME/OpenFOAM-bioTank/activate-bioTankControlFoam.sh"
```

There is no need to download or rebuild again. The generated OpenFOAM activation
file does **not** activate Micromamba for you. These instructions do not edit
`.bashrc`. To leave the environment, simply close the terminal.

## 5. Prepare your exercise

Start with the [RANS tank walkthrough](aerated-tank-walkthrough.md). Preparation
makes a separate working copy; it leaves the source case unchanged:

```bash
cd "$BIOTANK_ROOT"
./cases/aeratedTank/Allprepare "$HOME/biotank-runs/tank"
```

For the [LES exercise](les-exercise.md), prepare a different directory instead:

```bash
cd "$BIOTANK_ROOT"
./cases/aeratedTankLES/Allprepare "$HOME/biotank-runs/tankLES"
```

LES defaults to **8 MPI processes**. For a computer with fewer available cores,
use a fresh destination and specify the count, for example:

```bash
./cases/aeratedTankLES/Allprepare "$HOME/biotank-runs/tankLES-4" exercise 4
```

Read the relevant walkthrough before `./Allmesh` and `./Allrun`. The LES mesh
can require considerable memory and runtime; successful installation does not
mean a laptop can run the full exercise efficiently. A `smoke` mesh is an
integration-test profile, not a validated LES resolution.

## 6. Install ParaView without sudo (optional)

Download a prebuilt **Linux x86_64** archive from the
[official ParaView download page](https://www.paraview.org/download/), rather than
its source-code archive. In Ubuntu Files, extract it into a directory such as
`~/Applications`, open the extracted folder, then run `bin/paraview`. No system
installation or OpenFOAM-specific ParaView build is required for VTK files.
If the GUI reports missing system graphics libraries, use ParaView on another
computer and copy your exported `VTK` folder there.

After a simulation has stopped, export from the activated OpenFOAM terminal:

```bash
cd "$HOME/biotank-runs/tankLES"  # use the directory you actually prepared
./foamToVTK.sh all 2
```

In ParaView, open `VTK/tankLES.vtk.series` (the name follows your run directory).
The `2` above limits concurrent export jobs; it does not change the simulation's
MPI processor count. See [export options](../README.md#export-all-saved-times-to-vtk).

## If something goes wrong

| Message or symptom | What to do |
| --- | --- |
| Setup asks for sudo | Stop and rerun step 2 with `--skip-deps`. |
| `gcc`, `mpicc` or `foamRun`: command not found | Repeat step 4 in order; check that step 1/2 completed successfully. |
| Compiler is killed | Rerun the same setup command with `--jobs 1`; it reuses completed compilation work. |
| Missing headers, `libmpi`, or `GLIBCXX` errors | Open a fresh terminal and repeat step 4; do not mix system MPI or another Conda/OpenFOAM environment into this build. |
| `Not enough slots` | Prepare a new LES case with a processor count no greater than the cores available to your account. |
| Destination already exists | Choose a new run-directory name; preparation intentionally preserves existing runs. |
| Download fails or disk quota is exceeded | Check internet access and `df -h "$HOME"`; university account quotas may need checking separately. |
| Build fails for another reason | Send your instructor the error and `~/OpenFOAM-bioTank/log.OpenFOAM13` or `log.bioTankControlFoam`. |

When you edit the student controller, activate as in step 4, enter
`$BIOTANK_ROOT`, and run `./Allwmake` before starting the next simulation.
Stop simulations using the libraries before rebuilding them.

### Already have the dependencies?

If your university provides the compiler, MPI and development libraries, you can
skip Micromamba and use the same `--skip-deps --git-protocol https` setup command.
The required Ubuntu package names are listed in
[`scripts/install-openfoam13.sh`](../scripts/install-openfoam13.sh). In that
route, load your university's environment first in every new terminal. If it
already provides Foundation OpenFOAM 13, use the
[existing-installation route](installation.md#using-your-existing-foundation-openfoam-13)
and compile only this project.

### Verification scope

The home-directory dependency environment was created successfully and checked
with GCC 13, OpenMPI 4.1, a zlib compile/link check, two-process MPI launch and
this repository's `Alltest`. A complete fresh OpenFOAM build with this Micromamba
environment has **not** been run. The existing native CFD verification used
system GCC/OpenMPI; those results do not certify this alternative toolchain.
The installer continues to use the same pinned OpenFOAM/ThirdParty revisions.
