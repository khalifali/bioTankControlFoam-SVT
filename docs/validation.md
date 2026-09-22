# Verification and physical validation

Run ./tests/Alltest for pure C++ reaction/actuator checks and strict compilation
of both controller choices. These do not compile the OpenFOAM module.

After ./Allwmake, run ./tests/Allnative for native closed-box serial, MPI and
restart verification. Results/logs remain in tests/results, which must not already
exist. The independent chemistry reference uses bisection of the implicit equation.
It checks delayed activation, phase-volume weighting and liquid inventory balance.

By default ./tests/Allnative additionally meshes the official geometry and
runs a short coupled tank calculation. This is a software/geometry smoke test,
not proof of a developed flow, calibrated oxygen transfer or successful control.
Set BIO_TANK_SMOKE=0 to run only the small verification cases.

Before thesis production runs:

- Establish the official hydrodynamic baseline and assess gas dispersion.
- Run long enough to assess gas holdup, mixing and probe histories before choosing
  oxygen/control activation times. The example times are provisional.
- Refine mesh and timestep; vary residualCapacity and transfer blend thresholds.
- Calibrate/justify solubility, bubble size, transfer correlation and uptake for
  the intended medium, temperature and microorganism.
- Check inlet/outlet oxygen accounting, actuator saturation, probe validity and
  deficiency fraction/duration under demand changes.
- Tune feedback gains and evaluate independent scenarios and alternative layouts.

## Executed native verification — 11 September 2026

The originating implementation passed the following native checks before this
student edition was prepared. This is a historical verification summary, not a
claim that every imported configuration change has been retested natively.
The runnable tests are included so the results can be checked locally.

Executed checks:

- Foundation 13 module and controller compilation, pure-kernel checks and syntax.
- Installer reuse mode and generated combined environment activation.
- 64-cell closed-box serial and two-rank calculations: independent implicit
  chemistry reference, frozen oxygen warm-up and inventory residual below 1e-10 mol.
- Serial/MPI comparison and checkpoint continuation within 1e-10 for logged
  balance columns, with test-controller state restored identically on both ranks.
- Gas-only case: zero physical liquid inventory, uptake and transfer; invalid
  probe flags and NaN concentration as intended.
- Official geometry: 254,380 cells, checkMesh passed, maximum nonorthogonality
  64.588 degrees and maximum skewness 3.496.
- Short upstream multiphaseEuler baseline on the same mesh, then eight-rank
  coupled oxygen/RANS–MRF run from 0 to 0.005 s, continued to 0.007 s.
- Prescribed speed/flow changes: applied speed increased from 20 to 20.04 rad/s
  during the initial run; integrated inlet gas flow matched commanded values
  0.001, 0.0012, 0.0014, 0.0016 and 0.0018 m3/s within 1e-8 m3/s.
- Tank balance residual below 1e-7 mol before and after continuation.

The tank restart test checks continuation and inventory, not bitwise equivalence
of the complete turbulent flow trajectory. The startup speed and duration are
verification settings, not the production schedule. A 60 s production run, full
mesh/time convergence study, biological calibration and controller tuning have
NOT been performed. The new-installation apt/cold OpenFOAM-build path was not
rerun; the tested installer reused the already-built pinned OpenFOAM source tree.

## Running verification in this edition

Run the included tests locally with the commands above. No repository-specific
runner configuration is required or bundled. Native CFD verification requires
an active Foundation OpenFOAM 13 installation and MPI.

## LES numerics verification — 22 September 2026

The optional midpoint oxygen implementation was compiled and tested on the
`lamfoam-local` self-hosted runner registered with LAMFOAM, using Foundation 13
revision `18870c24d21c6b982e2cdec27b2f59738cca5f90`. See the
[native order/regression run](https://github.com/khalifali/LAMFOAM/actions/runs/35777313776).
The original split-Euler native cases also passed: chemistry, warm-up, serial/MPI
agreement, restart/controller state, dry cells and oxygen conservation.

The actual midpoint solver produced these concentration errors against independent
references (mol/m3):

| Time step (s) | Monod uptake | Discrete cosine diffusion |
|---|---:|---:|
| 0.1 | 1.51111e-5 | 7.97256e-6 |
| 0.05 | 3.80415e-6 | 1.98689e-6 |
| 0.025 | 9.52715e-7 | 4.96332e-7 |

Successive observed orders were 1.990 and 1.997 for uptake, and 2.005 and 2.001
for diffusion. The diffusion reference is exact for the discrete spatial
operator, separating temporal error from spatial error. MPI restart differed
from uninterrupted serial integration by 3.61e-16 mol/m3; oxygen balance residuals
were below 1e-10 mol. These checks use stationary phases and do not establish
second-order accuracy of the complete Euler–Euler system. Its internal bounded
phase-fraction update remains Euler-based.

The refined exercise mesh contains 3,548,937 cells. Basic validity/topology and
face-tetrahedron checks pass, with maximum aspect ratio 13.00, non-orthogonality
64.99 degrees and skewness 3.82. The extended audit flags 75,013 concave cells
(2.11%), 87 warped faces and two very short edges. It is not a clean extended
geometry pass. Neither these metrics nor a short startup test establish adequate
LES resolution or wall modelling; use the [LES guide](les-exercise.md) for the
remaining resolution, wall-treatment and statistical checks.

The final eight-rank startup check advanced two steps, restarted, and advanced
two more steps to 0.0004 s at deltaT = 0.0001 s. The maximum advancing-step
Courant number was 0.0088092 and the maximum oxygen-balance residual was
8.39e-14 mol. Nonnegative inventory, nonzero uptake and the selected LES models
were verified. All five saved times (0 through 0.0004 s) exported successfully
into one `VTK/tankLES.vtk.series`. The exporter explicitly includes time zero
when reconstructing fields; its nine mock workflow regressions pass too.

See the [completed runner report](https://github.com/khalifali/LAMFOAM/actions/runs/35782019427)
and the [machine-readable measurements and provenance](verification/les-smoke-2026-09-22.json).
The CFD ran at commit `51809e4`; subsequent changes fixed export/report handling
without repeating or modifying those evolved CFD fields. The result is
`passed_with_mesh_caveat`, not a clean extended mesh pass.

Measured filter widths Delta = V^(1/3):

| Region | Minimum (mm) | Median (mm) | Maximum (mm) |
|---|---:|---:|---:|
| Whole mesh | 0.441 | 4.782 | 36.914 |
| Impeller envelope | 0.441 | 1.326 | 5.842 |
| Discharge and baffles | 2.999 | 6.620 | 9.113 |
| Central plume | 0.441 | 2.096 | 6.511 |

Regions overlap. Startup liquid y+ maxima were 4.96 on the tank walls, 0.141
on the stirrer, 2.21 on the shaft, 0.0177 on the sparger walls and about 4.64
on the baffles. These are nearly quiescent startup values, not evidence of
adequate wall resolution or valid developed-flow wall functions. This check
ends early in the speed ramp, before aeration begins. It does not validate the
500 rpm aerated operating point or turbulent statistics.

On the runner, the retained case is under
`persistent/biotank-les-35779452827-1/tankLES` in the LAMFOAM Actions workspace;
the final report is under `persistent/biotank-les-35782019427-1/summary.json`.
