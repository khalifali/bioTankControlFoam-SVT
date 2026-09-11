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
