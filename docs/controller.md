# Student controller and measurements

Edit `studentController/StudentController.C`; build with `./Allwmake`. The solver
loads `createBioController` from the configured shared library. Keep the solver
core unchanged while developing the control law. C++17 and the same compiler ABI
as OpenFOAM are required. Do not replace a loaded library during a running job.

`Observation` supplies physical time, elapsed sample time, previous applied
omega and gasFlow, and named probe readings. Each reading includes concentration,
liquid fraction and a validity flag. Dry probes report NaN in CSV and to the
controller. Out-of-mesh probes fail at startup. Sampling uses the containing cell
value, with the lowest MPI rank owning an interface point deterministically.
The current version has ideal instantaneous sensors: no filtering, lag or noise.

The student returns `Command{omega_rad_per_s, gasFlow_m3_per_s}`. Gas flow refers
to volumetric flow at inlet conditions with the configured constant gas density,
not a standard-volume air-flow conversion. The solver enforces bounds and slew
limits and logs requests and applied values. The API deliberately does not expose
the complete oxygen field, global minimum or deficiency volume. Controller calls
execute only on the MPI master; commands and checkpoint state are broadcast.

`controller constant` holds initial commands. `prescribed` interpolates schedule
rows and is useful for actuator experiments. `student` calls the plug-in after
controlStartTime. Samples occur on the fixed timestep grid; t=0 has elapsed=0.
A command produced at t_n applies to the next flow step. Before control activation,
student mode holds its initial commands. For a baseline developed at nonzero air
flow, set initialGasFlow appropriately rather than assuming the prescribed
schedule still executes in student mode.

At a changed speed, MRF zones are reconstructed: OpenFOAM 13 MRFZone::read does
not rebuild its angular-speed function. Existing phase and mixture volumetric
fluxes are transformed from the previous frame to the new frame. Shaft
rotatingWallVelocity conditions are updated too. Gas commands rebuild the
flowRateInletVelocity inlet condition. Geometry, axes and zone names are retained.

## Choose the operating mode

Edit `constant/bioProperties` in the prepared run before starting a fresh case.
The file groups shared actuator settings separately from mode-only settings.
Use one `controller` entry; the inactive mode's entries may remain in the file.

| Mode | What to edit | What determines commands | Ignored mode-only settings |
|---|---|---|---|
| `constant` | `initialOmega`, `initialGasFlow` | Holds initial commands (restored commands on restart) | `schedule`, `studentLibrary`, `controlStartTime` |
| `prescribed` | `schedule`, plus initial commands | Interpolated schedule at sample times from the beginning | `studentLibrary`, `controlStartTime` |
| `student` | Controller source, `studentLibrary`, initial commands, `controlStartTime` | Holds initial/restored commands until activation; then calls `update()` at sample times | `schedule` |

`actuatorsEnabled`, `gasInlet`, bounds and rate limits are shared across modes.
`sampleInterval` sets the sampling cadence. `actuatorsEnabled false` bypasses
application of commands to MRF and the inlet; it is not a fourth controller mode.
`oxygenStartTime` controls oxygen physics independently of actuator mode.
With the default `initialGasFlow = 0`, switching to constant mode means no air
injection; student mode also starts without air until the controller changes it.

To implement student feedback:

1. Fill in `update()` in [studentController/StudentController.C](../studentController/StudentController.C),
   relative to the repository root. The template returns the previous commands.
2. Activate the installation and run `./Allwmake` from the repository root.
3. In the prepared run's `constant/bioProperties`, set `controller student;`,
   check `studentLibrary`, and choose initial commands and activation time.
4. Start a fresh case with `./Allmesh` and `./Allrun`; inspect `actuators.csv`
   to compare requested and applied commands. Follow the restart rules above
   when continuing a compatible existing case.

## Optional PI example

Change the source line in `studentController/Make/files` to
`examples/OxygenPI.C`, keeping the LIB line unchanged, then rebuild. Select
`controller student`. Compile only one factory implementation at a time.
The example controls the mean valid probe concentration with gas flow and holds
stirring fixed. If every probe is invalid, it holds both commands and its integral.
Gains are illustrative. Match its amplitude bounds to the case and extend its
anti-windup if solver slew limits are restrictive. A new simulation is required
when switching between state-incompatible controllers.

Override save()/restore() for integrators, observers or other state. Checkpoints
write this vector and actuator/sample/budget state in each processor time's
uniform/bioControlState. Keep controller type, probe definitions, sample interval
and deltaT unchanged on restart. Preserve all other physical settings for an
equivalence test. Allrestart continues the same decomposition; changing processor
count or controller state format is not supported by this first workflow.

## Sparse sensors and oxygen-poor regions

An acceptable mean does not guarantee local oxygen adequacy: 0.30 and 0.06 mol/m3
average to 0.18. Controlling the lowest probe reading protects only the sampled
locations. Use uncontrolled CFD fields to identify vulnerable regions, compare
layouts and test them under changed demand/operating conditions. Evaluate the
controller against full-field deficiency volume/time without exposing that ground
truth online. Observer-based and adaptive strategies are student extensions,
not features claimed for the default hold controller or fixed-gain PI example.
