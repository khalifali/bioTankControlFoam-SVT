# LES-MRF aerated tank exercise

This separate exercise selects liquid `SmagorinskyZhang` (including bubble-induced
turbulence) and gas `continuousGasKEqn`, with `cubeRootVol` filter width. The gas
model follows Foundation OpenFOAM 13's `bubbleColumnLES` tutorial. The original
`cases/aeratedTank` RANS exercise is unchanged.

The impellers still use MRF: they do not physically rotate past the baffles.
This is an initial LES-MRF exercise, not a validated blade-passing simulation.
The geometry, two-fluid closures, oxygen transfer and biology remain the same.

## Prepare and run

With Foundation OpenFOAM 13 and this project's library activated:

```bash
./Allwmake
./cases/aeratedTankLES/Allprepare "$PWD/runs/tankLES" exercise 8
cd runs/tankLES
# Inspect constant/bioProperties and system/controlDict.
./Allmesh
./Allrun
./foamToVTK.sh all 4
```

Open `VTK/tankLES.vtk.series` in ParaView. `Allrestart`, `Allclean` and the export
helper follow the original exercise's conventions. Preparation requires a new
absolute destination; it never converts an existing RANS run in place.

The LES exercise defaults to a constant 500 rpm and 0.0186667 m3/s air flow from
the start. Oxygen activation remains at 10 s. The controller modes and student
extension point are described in [the controller guide](controller.md).

## Mesh profiles

`Allprepare /absolute/new/run [exercise|smoke] [ranks]` records the profile in
`les-mesh-profile`. `Allmesh` generates editable OpenFOAM dictionaries from the
official geometry; generated dictionaries and mesh logs stay in the run.

| Setting | exercise (default) | smoke (integration only) |
|---|---|---|
| Cylindrical background counts | (8 24 72) | (5 15 44) |
| Stirrer/sparger surface levels | 4 | 3 |
| Baffle surface level | 3 | 2 |
| Impeller/wake and central-plume volume levels | 2 | 1 |
| Transition cells between levels | 4 | 4 |

The refinement boxes extend across the two impellers, their discharge region and
central plume. They supplement surface refinement, rather than refining only
blade faces. These are candidate grids for a sensitivity study, not established
LES resolution criteria. The smoke grid is deliberately cheaper and must not be
used as evidence of resolved turbulent statistics. Inspect actual cell sizes,
blade/gap resolution, wakes and gas distribution after meshing.

The first version retains the tutorial's `nutkWallFunction` wall treatment and
does not add prism layers. It is not wall-resolved LES. Before quantitative use,
review the automatic liquid y+ output, assess wall-function validity and design suitable wall-normal
resolution/layers; check sensitivity of torque and mixing to those choices.

## Time, numerics and interpretation

The fixed time step is 0.0001 s (0.3 degrees at 500 rpm); output is every 0.1 s.
This is a starting value, not a Courant guarantee. Reduce it if necessary and
keep sampling/activation times aligned with the time-step grid. The solver
currently rejects automatic time-step adjustment.

Momentum uses linear-upwind with an un-limited linear velocity gradient, instead
of the baseline cell-limited gradient. Euler time integration and upwind oxygen
advection are retained for the existing split reaction/balance implementation.
This conservative initial setup can dissipate resolved fluctuations: temporal
and spatial sensitivity tests, and a separately verified higher-order scalar
scheme, are required before interpreting LES mixing predictions.

`nut.liquid/turbulentSchmidt` now represents modelled subgrid scalar diffusivity.
The existing Schmidt number and transfer closure are not automatically validated
by selecting LES. Individual bubble surfaces remain unresolved.

Compare at least mean flow, velocity fluctuations, gas holdup, impeller torque,
probe histories and oxygen deficiency across grids and time steps. Allow flow
development and collect statistics over many revolutions. A rotating-mesh/NCC
extension would require revising the MRF actuator implementation as well.

## Mesh quality and resolution report

`Allmesh` runs `checkMesh -allGeometry -allTopology`. A failed mesh check must be
resolved before interpreting the simulation. The native check also writes
`summary.json` containing checkMesh geometry metrics and min/median/max
$\Delta=V^{1/3}$ in the whole mesh, impeller envelope, discharge/baffle region,
and central plume. Overlapping regions are intentional. This filter width does
not measure directional stretching; also inspect the aspect-ratio report and
mesh slices through blade gaps and wakes.

Each LES run writes cell centres (`C`), volumes (`V`), and liquid `yPlus` at
output times. The report includes final startup y+ min/max/mean by wall patch.
These startup values are diagnostic only: assess wall resolution again after
flow development. `Mesh OK` does not establish resolved turbulent energy,
adequate wall modelling, or grid-independent oxygen mixing.

## Short native check

```bash
python3 tests/les_smoke.py --output "$PWD/tests/results/les-smoke" --ranks 8
# Check the finer exercise grid instead:
python3 tests/les_smoke.py --profile exercise --output "$PWD/tests/results/les-exercise" --ranks 8
```

Use a new output directory each time. The default builds the smoke-profile mesh; `--profile exercise` builds the finer
exercise grid. Both run
40 steps to 0.004 s, then restarts for 20 more steps to 0.006 s. Oxygen starts at
zero and demand changes at 0.002 s for this test only. It checks mesh quality,
selection of both LES models, finite oxygen balances, nonnegative inventory,
nonzero uptake, a maximum logged Courant number no greater than 1, restart and
VTK export of all four saved times. Logs, generated dictionaries and `summary.json`
are retained. It does not establish developed turbulence or grid-independent LES accuracy.

Model references: [SmagorinskyZhang](https://cpp.openfoam.org/v13/SmagorinskyZhang_8H_source.html),
[official bubbleColumnLES](https://github.com/OpenFOAM/OpenFOAM-13/tree/master/tutorials/multiphaseEuler/bubbleColumnLES).
