# Aerated tank: student walkthrough

## Purpose and model

This case is an educational starting point for controlling dissolved oxygen in
a stirred, aerated vessel with microbial consumption. First run the prescribed
operating schedule to understand the flow and oxygen response. The student can
then develop a controller using a configurable set of measurement points.

The geometry and hydrodynamic dictionaries come from the installed Foundation
OpenFOAM 13 tutorial `multiphaseEuler/aeratedStirredTankMRF`; our case adds oxygen
transport, consumption, measurements and actuator commands. The baseline uses
SI units throughout. This is a numerical teaching case, not a calibrated
bioreactor or a completed validation study.

See the [model introduction and equations](model.md) for Euler–Euler, RANS and
MRF definitions. Both phases use constant density and isothermal phase models:
energy transport is disabled, although `T.gas` and `T.liquid` remain required
thermophysical input fields. Keep those files.

## Geometry: where water and air go

The reference tank has a radius of about 0.5 m and overall geometry extending
approximately from z = -0.216 to 1.25 m. It contains wall baffles, a lower Rushton
turbine, an upper pitched-blade impeller, a shaft, a sparger and a top outlet.
The sparger is below the lower impeller. Its gas inlet faces are approximately
at z = 0 m, with horizontal extents of about +/-0.1175 m. The lower impeller
geometry starts near z = 0.084 m.

The initial water level is approximately z = 0.8 m. Above that level is an
initial air headspace. The vessel is vented through the top outlet: it is not
a sealed tank. Supplied gas can rise through the liquid and leave at the top.
The constant-density gas model does not describe sealed-vessel pressurisation.

These dimensions describe the inspected upstream baseline. When using another
OF13 installation, inspect its copied geometry and dictionaries too.

## Initial fields and the first picture

`alpha.gas` is the fraction of a cell occupied by gas. A value of 1 is gas,
a value of 0 is liquid, and intermediate values indicate cells containing both
phases in the two-fluid representation. It is not oxygen concentration.

A red headspace above blue liquid when plotting `alpha.gas` immediately after
startup is expected. That gas is present initially; it has not travelled from
the inlet in one step. The default inlet gas flow is initially zero. Individual
bubbles are not geometrically resolved; later aeration appears as a distributed
gas-fraction plume.

The initial `oxygen.liquid` concentration is 0.15 mol/m3 of liquid (4.8 mg/L).
It is frozen during the oxygen warm-up interval even while the liquid fraction
and velocity change. Its value in gas-only cells is a numerical placeholder,
not an oxygen measurement in air.

## Default operating timeline

The following settings are in `constant/bioProperties` and
`system/controlDict` in the prepared run directory.

| Physical time | Default behaviour |
|---|---|
| 0–5 s | Stirring at 500 rpm; no inlet air flow. |
| 5–5.1 s | Prescribed air flow ramps from zero to 0.0186667 m3/s. |
| After 5.1 s | Air flow stays at 0.0186667 m3/s (1.12 m3/min). |
| First 10 s | Oxygen concentration remains frozen while flow develops. |
| After oxygen activation at 10 s | Oxygen transport, gas-to-liquid transfer and microbial uptake evolve. |
| 15 s | Student control becomes eligible **only if** `controller student` is selected. |
| 30 s | Prescribed microbial demand increases by a factor of 1.5. |
| 60 s | Default simulation end time. |

The default is `controller prescribed`, so there is no feedback controller
switching on at 15 s. Stirrer speed remains 52.35987756 rad/s (500 rpm) in this
schedule. Command bounds and rate limits still apply.

In `student` mode the prescribed schedule does not run; initial commands are
held before control activation. Set `initialGasFlow` to the intended value
for that experiment. Otherwise its default zero value means no aeration before
student control starts.

The flow time step is fixed at 0.001 s, measurement interval is 0.1 s and full
fields are written every 1 s. ParaView's first saved nonzero time is therefore
not necessarily the first computational step. Activation and sampling times
must align with the fixed time-step grid. Startup times are provisional: they
do not prove that the flow is fully developed.

## Oxygen supply, equilibrium and consumption

The inlet supplies air at the commanded volumetric flow rate. Oxygen enters
the liquid through the distributed transfer model in bubbly liquid regions;
there is no imposed dissolved-oxygen inlet supplying the entire tank.

The equilibrium dissolved concentration is
`Cstar = Hcp * yO2 * pAbsolute`. Here Hcp is the solubility coefficient, yO2
the gas oxygen mole fraction and pAbsolute the local absolute pressure.
The default Hcp is 1.175e-5 mol/(m3 Pa) and yO2 is 0.21. Around atmospheric
pressure this gives approximately 0.25 mol/m3, or 8 mg/L.

Transfer is proportional to `kL*a*(Cstar-C)`: undersaturated liquid gains
oxygen, equilibrium gives zero net transfer, and supersaturated liquid can
release oxygen. This equilibrium is distinct from a balance between supply
and microbial consumption. Bubble transfer fades out between gas fractions
0.3 and 0.7; no separate free-surface transfer model is included.

There is no transported `oxygen.gas` field. Gas composition is assumed to
remain at 21% oxygen even after dissolution. Increasing inlet air flow affects
gas holdup, interfacial area and mixing, so it changes liquid oxygen supply,
but gas-phase oxygen depletion is not accounted for. The model does not enforce
a finite gas oxygen budget limiting dissolution. It cannot predict exhaust
oxygen composition or oxygen utilisation efficiency reliably.

### Microbial uptake: what the sink term does

Microorganisms remove dissolved oxygen from the liquid. Their collective
consumption is represented by a prescribed, spatially uniform biomass
concentration. No explicit microbial particles, biomass transport or growth,
cell death, or depletion of another substrate are simulated.

The oxygen uptake rate **per unit liquid volume** is

$$
r_L(C,t)=m(t)\,q_{\max}\,X\,\frac{C}{K_O+C}.
$$

| Symbol | Meaning and units | Parameter / baseline |
|---|---|---|
| $C$ | Local dissolved oxygen [mol O2/m3 liquid] | oxygen.liquid field |
| $X$ | Uniform biomass [kg biomass/m3 liquid] | biomass = 1 |
| $q_{\max}$ | Maximum specific uptake [mol O2/(kg biomass s)] | specificUptake = 0.002 |
| $K_O$ | Half-saturation concentration [mol/m3 liquid] | halfSaturation = 0.01 |
| $m(t)$ | Dimensionless demand factor | 1 initially; demandMultiplier = 1.5 after demandChangeTime = 30 s |
| $r_L$ | Positive oxygen consumption rate [mol O2/(m3 liquid s)] | Calculated locally |

The multiplier changes prescribed demand; it does not simulate growth.
It applies to time intervals beginning at the demand-change time.
All uptake is inactive during the initial oxygen warm-up.

The factor $C/(K_O+C)$ describes oxygen limitation:

- At $C=0$, uptake is zero: no oxygen is available.
- At $C=K_O$, uptake is half the current maximum.
- At $C\gg K_O$, uptake approaches $m q_{\max}X$.
- For $0<C\ll K_O$, uptake is approximately proportional to $C$.

This is a saturating consumption law, not a fixed subtraction independent
of available oxygen. It does not model the biological consequences of starvation.

### Worked example

Before the demand increase, $q_{\max}X=0.002$ mol/(m3 liquid s).

| $C$ (mol/m3 liquid) | $C/(0.01+C)$ | $r_L$ (mol/(m3 liquid s)) |
|---|---|---|
| 0 | 0 | 0 |
| 0.001 | 0.0909 | 0.000182 |
| 0.01 | 0.5 | 0.001 |
| 0.10 | 0.9091 | 0.001818 |
| 0.15 (initial value) | 0.9375 | 0.001875 |

These are instantaneous rates at the listed concentrations. After the demand
factor becomes 1.5, each rate is 50% higher **at the same concentration**.
Concentration itself evolves through consumption, supply and transport.

### Liquid-fraction weighting and the negative source

Let $\alpha_L$ be liquid volume fraction and $V_i$ the volume of cell $i$.
The oxygen equation stores oxygen per mixture volume as $\alpha_L C$.
Its microbial source is therefore

$$
S_{\mathrm{uptake}}=-\alpha_L r_L
=-\alpha_L m(t)q_{\max}X\frac{C}{K_O+C}.
$$

The minus sign means oxygen is removed. Cell consumption is
$\dot n_{\mathrm{uptake},i}=\alpha_{L,i}V_i r_{L,i}$ in mol/s.
Pure-gas cells have $\alpha_L=0$ and no microbial consumption.

For a cell of volume $10^{-6}$ m3, liquid fraction 0.8 and concentration
0.15 mol/m3 before the demand increase, consumption is
$0.8\times10^{-6}\times0.001875=1.5\times10^{-9}$ mol/s.
Its time integral contributes positively to cumulativeUptake_mol
in oxygenBalance.csv.

The physical balance is

$$
\frac{\partial(\alpha_L C)}{\partial t}
+\nabla\cdot(\alpha_L\mathbf{U}_L C)
=
\nabla\cdot(\alpha_L D_{\mathrm{eff}}\nabla C)
+k_La(C^*-C)-\alpha_L r_L.
$$

Here $\mathbf{U}_L$ is liquid velocity, $D_{\mathrm{eff}}$ is molecular plus
turbulent oxygen diffusivity, $k_L$ is the transfer coefficient, $a$ is bubble
area per mixture volume, and $C^*$ is equilibrium dissolved oxygen.
The implementation uses the phase solver's actual liquid flux and a small
numerical capacity in nearly dry cells; see the [model guide](model.md).

In uniform pure liquid without transport or oxygen supply, the balance reduces
to $dC/dt=-r_L(C,t)$: oxygen decreases and consumption slows as it becomes scarce.
With aeration and mixing, supply can offset uptake. Local reactions are solved
implicitly; the tabulated rates are not an explicit subtraction recipe for
arbitrarily large time steps.

### Half-saturation and critical oxygen serve different purposes

**halfSaturation** ($K_O=0.01$ mol/m3) determines the consumption curve.
**criticalOxygen** ($C_{\mathrm{crit}}=0.10$ mol/m3, or 3.2 mg/L) identifies
poorly supplied liquid for evaluation. It does not switch uptake off and is
not automatically a controller setpoint.

A cell below the critical threshold can still consume oxygen. Reduced uptake
caused by starvation is not successful control. These baseline parameters
are illustrative and require justification for the organism and conditions.

## Measurements, controller and output files

Three default probes sample the containing cell, without interpolation:

| Name | Position (x, y, z), metres |
|---|---|
| lowerBulk | (0.20, 0.05, 0.20) |
| middleBulk | (0.20, 0.05, 0.45) |
| upperBulk | (0.20, 0.05, 0.70) |

Add or remove named entries in `measurements` before running. A point must
be inside the mesh. A sample with liquid fraction below 0.5 is invalid and
reports NaN for oxygen. The controller must handle invalid measurements.

The controller can request stirrer angular speed and inlet gas flow. The
default limits are 0–62.83185 rad/s (0–600 rpm) and 0–0.025 m3/s, with rate
limits of 10 rad/s2 and 0.2 m3/s2 respectively. Requested and applied commands
are logged separately. Full-field oxygen-deficiency diagnostics are available
for evaluation but are not passed to the student controller.

Look in `postProcessing/bioControl/<segment-start-time>/`:

| File | What to examine |
|---|---|
| measurements.csv | Time, named oxygen readings, liquid fractions and validity flags. |
| actuators.csv | Requested and applied stirrer speed and air flow. |
| oxygenBalance.csv | Liquid oxygen inventory, supply, uptake, boundary exchange and balance residual, including numerical/warm-up accounting. |
| evaluation.csv | Liquid volume below the critical concentration and cumulative deficiency measure. |

A good mean probe concentration does not guarantee adequate oxygen everywhere.
Compare controller performance against the full-field deficiency measures.
See [controller development](controller.md) for the interface and restart rules.

## Prepare, inspect, mesh and run

After [installing or activating the environment](installation.md), run from the
repository root:

```bash
# Create a new, independent run directory.
./cases/aeratedTank/Allprepare "$PWD/runs/tank"
cd runs/tank

# Inspect constant/bioProperties and system/controlDict before proceeding.
# Generate and check the mesh using the default eight-way decomposition.
./Allmesh

# Run the simulation and reconstruct its latest saved fields.
./Allrun

# Later, continue the same case to 90 s from its saved checkpoint.
./Allrestart 90
```

`Allprepare` copies the official tutorial and applies the oxygen settings using
`foamDictionary`. Its "New entry" messages are normal confirmations of edits,
not solver errors. A different OF13 Git revision produces an informational
notice. It records the revision in `upstream-revision.txt`.

Edit files in the prepared run to change that experiment. Editing repository
templates does not update an existing run. Case dictionary edits require no
compilation; C++ solver/controller edits require activation followed by
`cd "$BIOTANK_ROOT"` and `./Allwmake`. Stop jobs using the libraries before
rebuilding. A restart must retain compatible controller state, probe definitions,
sampling interval, time step and processor count; see the controller guide.

`Allclean --yes` removes generated results in a prepared case. Use it only
when deliberately discarding that run's results, not when continuing a run.

## Stop safely while a simulation is running

From a second terminal, create the trigger in the **run directory**:

```bash
cd /path/to/bioTankControlFoam-SVT/runs/tank
touch abort
```

The configured `stopAtFile` function uses `action nextWrite`. It requests
saving and normal exit at the next scheduled output, not an immediate kill.
The default write interval is 1 s of simulation time, not wall-clock time.
Normal writes include solver fields and controller checkpoint state; Allrun
then performs its usual latest-time reconstruction.

In MPI runs, create one file in the main case directory, not in processor0.
Create it after solver startup: OpenFOAM removes old triggers at startup and
cleans up at normal termination. Polling works with `runTimeModifiable false`.
Wait for completion, then use `./Allrestart 90` to continue to a later end time.

Newly prepared cases enable this automatically. For an existing case, add the
following entry inside `functions` in its `system/controlDict` before launching
or restarting. Create the enclosing `functions { ... }` dictionary if absent:

```cpp
abort
{
    type            stopAtFile;
    libs            ("libutilityFunctionObjects.so");
    file            "$FOAM_CASE/abort";
    action          nextWrite;
    executeControl  timeStep;
    executeInterval 1;
}
```

No recompilation is required. An already-running case without this function
will not gain it merely by pulling repository updates.
Reference: [Foundation OF13 stopAtFile](https://cpp.openfoam.org/v13/stopAtFile_8H_source.html).

## Export every saved time to VTK

`Allrun` and `Allrestart` reconstruct only the latest time. To reconstruct missing
or partial times and export the whole saved history, stop the solver, activate
Foundation OpenFOAM 13, and run from the prepared case:

```bash
cd runs/tank
./foamToVTK.sh all 8
```

`Allprepare` copies the helper into new runs. For an older run, copy
[`cases/aeratedTank/foamToVTK.sh`](../cases/aeratedTank/foamToVTK.sh) into its root
beside `system/` and `constant/`. The script always uses its own directory as the
case, even when invoked from elsewhere. Python 3.9 or newer is required.

Open **`VTK/tank.vtk.series`** in ParaView; replace `tank` with the run directory's
name. This one index contains all completed internal-mesh exports ordered by
physical time, including earlier retained VTK output. Patch datasets are separate.
Display `alpha.gas`, `U.liquid` and `oxygen.liquid` as described below.

| Command | Work performed |
|---|---|
| `./foamToVTK.sh` | Full workflow with eight workers |
| `./foamToVTK.sh all 4` or `./foamToVTK.sh 4` | Full workflow with four workers |
| `./foamToVTK.sh reconstruct 4` | Reconstruct missing/partial fields only |
| `./foamToVTK.sh vtk 4` | Convert existing root times and rebuild the index |
| `./foamToVTK.sh series` | Rebuild the index from existing VTK without OpenFOAM utilities |

Mesh preparation is serial. Workers then run serial utilities on different times
concurrently: pseudo-parallel processing without MPI. Reduce the worker count
when memory is limited. The helper supports the fixed-mesh, single-region tank
with `processorN` storage; collated `processors*` storage is not supported.

Reruns skip complete reconstructed fields and completed nonempty VTK files.
Failed jobs retain retry markers; inspect per-time logs in `log.foamToVTK/` and
rerun after fixing the cause. All source and reconstructed time directories are
preserved. To refresh deliberately changed fields at an exported time, remove
`VTK/<case>_<time>.vtk` and rerun. Do not rename the case between exports.

## What to inspect in ParaView

Open `mesh.foam` in the prepared run. After reconstruction, select the
reconstructed case rather than individual processor directories.

1. Display `alpha.gas` with a colour range of 0–1 to locate liquid and headspace.
2. Add a vertical Slice through the tank centre (for example, plane x = 0).
   The outer surface alone can hide an internal gas plume.
3. Examine saved times after 5.1 s to see the developing aeration distribution.
   It need not establish a fully developed plume immediately.
4. Display `U.liquid` to examine circulation around the impellers.
5. After oxygen activation, display `oxygen.liquid` in liquid-dominated regions
   and compare it with the probe time histories.

Unsupported `#includeEtc`, unresolved variables or missing included files in
ParaView indicate a reader/input-expansion problem, not evidence that the energy
equation is enabled. Do not remove required temperature fields to hide it.
Such reader errors must be resolved before interpreting the affected fields.

## Before using the case for thesis conclusions

The default RANS exercise's implicit Euler time integration and upwind oxygen advection are
robust starting choices. Upwind can smear oxygen-poor regions, while the time
step and first-order reaction splitting can affect response times. A stable
run or a passing mesh check alone does not establish accuracy.

Compare time steps, meshes and appropriate higher-order formulations using
probe concentrations, deficient liquid volume and controller response as
metrics. Changing the time scheme alone does not automatically make the
complete split oxygen algorithm second order. Check oxygen positivity and
inventory conservation too. Read the [verification report](validation.md) to
distinguish completed checks from remaining physical validation. The separate
[LES exercise](les-exercise.md) includes a coupled midpoint oxygen method,
higher-order spatial schemes and native time-order tests. Its phase-fraction
update still prevents a full-system second-order time-accuracy claim.

## Complete bioProperties parameter reference

Edit `constant/bioProperties` **inside the prepared run directory**. The tables
below describe every entry in the supplied file. Values are the tutorial
defaults, not calibrated biological or control parameters.

### Reading the units and file header

A dimensioned entry contains a name, seven unit exponents, and a value:

```cpp
molecularDiffusivity [0 2 -1 0 0 0 0] 2e-9;
```

The exponent order is **mass, length, time, temperature, amount of substance,
electric current, luminous intensity**. Thus this example is m2/s. The numbers
are already in SI units; the bracket does not perform a unit conversion.
Dissolved oxygen is mol O2 per m3 of **liquid**, not per m3 of mixture.
Multiply mol/m3 by 32 to obtain mg/L for O2.

The `FoamFile` entries are metadata: `format ascii` selects text,
`class dictionary` identifies a settings dictionary, and `object bioProperties`
names it. They are not physical parameters.

### Phase selection

| Parameter | Default | Meaning and use |
|---|---|---|
| `liquidPhase` | `liquid` | Name of the phase supplying liquid fraction, velocity, turbulent diffusivity and physical properties. Must match a phase in phaseProperties. |
| `gasPhase` | `gas` | Name of the phase supplying gas fraction, velocity and bubble diameter. Must match a phase in phaseProperties. |

These select existing phases; they do not create phases or rename input fields.
The oxygen input field is currently named `oxygen.liquid` explicitly in the
solver, even if the liquid phase selection is changed.

### Oxygen transport

| Parameter | Default / units | Meaning and effect |
|---|---|---|
| `oxygenIntegration` | `splitEuler` if omitted; LES preparation sets `midpoint` | Optional integration method. `splitEuler` retains the positive local implicit reaction split; `midpoint` couples transport and reactions in a second-order scalar step. Midpoint may require a smaller time step for positivity. Preserve the choice on restart; see the [LES numerical method](les-exercise.md#coupled-midpoint-oxygen-update). |
| `molecularDiffusivity` | 2e-9 m2/s | Molecular diffusion coefficient D. Must be positive. Increasing it strengthens diffusion and also changes the gas-to-liquid transfer calculation, which uses D. |
| `turbulentSchmidt` | 0.7, dimensionless | Turbulent Schmidt number Sc_t. Turbulent oxygen diffusivity is nut/Sc_t; reducing Sc_t increases turbulent mixing of oxygen for a given eddy viscosity nut. Must be positive. |
| `residualCapacity` | 1e-8, dimensionless | Minimum numerical storage capacity in nearly gas-only cells: capacity = max(alpha_liquid, residualCapacity). Avoids a singular oxygen equation. It is not a minimum oxygen concentration. Must be greater than zero and at most 1e-3. Its artificial inventory is logged separately. |

The effective liquid diffusivity is D + nut/Sc_t when the liquid nut field is
available; the conservative diffusion term also contains liquid volume fraction.
Do not tune residualCapacity as a physical transport coefficient.

### Gas-to-liquid oxygen transfer

| Parameter | Default / units | Meaning and effect |
|---|---|---|
| `henrySolubility` | 1.175e-5 mol/(m3 Pa) | Hcp in Cstar = Hcp*yO2*(p + pressureOffset). Increasing it raises the equilibrium dissolved concentration at fixed pressure/composition. Nonnegative. This is the concentration/pressure convention, not its reciprocal. |
| `gasOxygenFraction` | 0.21, dimensionless | Prescribed oxygen mole fraction yO2 in gas, between 0 and 1. Represents air in the baseline. It sets saturation, not inlet gas flow, and is not depleted by dissolution. |
| `pressureOffset` | 0 Pa | Offset added to the solved p field to obtain absolute pressure for Henry's law. The supplied p is already absolute, so leave zero. The resulting absolute pressure must be positive. |
| `fadeBegin` | 0.3, dimensionless | Gas volume fraction below which the full dispersed-bubble area formula is used. Above this value its contribution begins to decrease smoothly. |
| `fadeEnd` | 0.7, dimensionless | Gas volume fraction at and above which dispersed-bubble transfer is zero, avoiding a bubble-area model in the headspace. Must exceed fadeBegin; both thresholds lie between 0 and 1. |

Between fadeBegin and fadeEnd a smooth cubic weighting reduces bubble area.
These are gas-fraction thresholds, not oxygen thresholds. They do not describe
free-surface transfer. Transfer coefficient kL and area a are calculated from
the phase solution; there is no user-prescribed kLa entry in this file.
See [the transfer equations](model.md#gas-to-liquid-oxygen-transfer).

### Microbial uptake and evaluation

The uptake rate per liquid volume is
`specificUptake * biomass * C/(halfSaturation + C)`, multiplied by the
demand factor after the demand-change time. The conservative equation multiplies
this by liquid fraction to obtain uptake per mixture volume.

| Parameter | Default / units | Meaning and effect |
|---|---|---|
| `biomass` | 1 kg/m3 liquid | Prescribed uniform biomass concentration X. Increasing it proportionally increases potential uptake. Nonnegative; zero disables microbial uptake. It is not a transported biomass field. |
| `specificUptake` | 0.002 mol/(kg s) | Maximum uptake per unit biomass qmax. Nonnegative; zero disables uptake. Actual uptake is reduced by the Monod concentration factor. |
| `halfSaturation` | 0.01 mol/m3 liquid | Monod constant KO: at C = KO, uptake is half its maximum at the current biomass and demand factor. Must be positive. Increasing KO reduces uptake at a fixed positive C. |
| `criticalOxygen` | 0.10 mol/m3 liquid | Evaluation threshold: liquid in cells with C below this value is counted as deficient. Nonnegative. It does not change the uptake law and is not automatically the controller setpoint. |
| `demandChangeTime` | 30 s | Absolute simulation time at which the demand multiplier becomes active. Must be nonnegative and align with deltaT. The demand change matters only when oxygen reactions are active. |
| `demandMultiplier` | 1.5, dimensionless | Factor applied to qmax*X after the demand change. 1.5 means 50% greater maximum demand; 1 means no change; 0 removes uptake after the change. Nonnegative. |

For example, the default maximum uptake is 0.002 mol/(m3 liquid s), rising to
0.003 after the change. Actual uptake can be lower because C/(KO+C) is below 1.
The default critical threshold is 3.2 mg/L; KO is 0.32 mg/L.

### Activation and sampling times

| Parameter | Default / units | Meaning and use |
|---|---|---|
| `oxygenStartTime` | 10 s | Oxygen evolution begins after the warm-up interval. Before this, concentration is frozen while flow and phase fractions evolve. Supply/uptake are inactive; the imposed warm-up inventory change is logged. |
| `controlStartTime` | 15 s | Earliest time for student-controller updates. Applies only to student mode. Constant and prescribed modes do not wait for this time. |
| `sampleInterval` | 0.1 s | Interval for probe sampling, command updates and measurement/actuator CSV rows. Must be positive and align with deltaT. It is separate from full-field writeInterval in controlDict. |

All these times must be nonnegative integer multiples of the fixed flow time
step. The initial sample at t = 0 has zero elapsed time, so it cannot create a
finite rate-limited actuator jump. Commands computed at a sample time affect
the next flow step. Oxygen activation is based on the start of the completed
time interval, so do not interpret a field saved exactly at the warm-up boundary
as a full interval of active oxygen transport.

Balance and deficiency diagnostics are written each flow step, not only at
sampleInterval. Longer warm-up times may be needed to obtain developed flow.
Do not begin interpreting sensor-driven oxygen control before oxygen evolves.

### Controller selection and actuator connection

| Parameter | Default | Meaning and use |
|---|---|---|
| `actuatorsEnabled` | true | Enables applying speed and inlet-flow commands to the hydrodynamic model. False skips those updates; it does not disable oxygen, sampling or command calculation/logging, and does not automatically stop existing stirring or inlet boundary conditions. Primarily for verification cases. |
| `gasInlet` | `inlet` | Mesh patch whose gas velocity condition is updated to impose commanded volumetric gas flow. The patch must exist when actuators are enabled. |
| `controller` | `prescribed` | Selects constant, prescribed or student mode, described below. |
| `studentLibrary` | `$FOAM_USER_LIBBIN/libbioStudentController.so` | Shared library loaded in student mode. Environment variables are expanded. It must provide the createBioController factory. Compile the selected controller with Allwmake before starting. |

- **constant:** holds the initial commands (or restored commands on restart).
- **prescribed:** interpolates schedule rows at sample times. This is open-loop
  operation; measurements do not determine the commands.
- **student:** calls the student plugin after controlStartTime. Before that,
  initial/restored commands are held. The prescribed schedule is not also run.

There are no PI gains or oxygen target entries in this dictionary by default.
Those belong to the selected student implementation. Changing criticalOxygen
does not change an independently defined PI target.

### Initial commands, bounds and rates

| Parameter | Default / units | Meaning and effect |
|---|---|---|
| `initialOmega` | 52.35987755982988 rad/s | Fresh-run initial angular speed, equal to 500 rpm. On restart the saved command is used. Rotation axes come from the existing MRF/shaft settings. |
| `initialGasFlow` | 0 m3/s | Fresh-run initial air flow at inlet conditions; on restart the saved value is used. In student mode this is held before control activation, so zero means no commanded aeration during that period. |
| `minOmega` | 0 rad/s | Lower permitted angular-speed command. |
| `maxOmega` | 62.83185307179586 rad/s | Upper permitted speed, equal to 600 rpm. Must not be below minOmega. Initial/restored speed must lie within the bounds. |
| `omegaRate` | 10 rad/s2 | Maximum magnitude of angular-speed change per second, applied using elapsed sample time. This limits both acceleration and deceleration of the command. |
| `minGasFlow` | 0 m3/s | Lower permitted gas-flow command; must be nonnegative. |
| `maxGasFlow` | 0.025 m3/s | Upper permitted gas-flow command; must not be below minGasFlow. Initial/restored flow must lie within the bounds. |
| `gasFlowRate` | 0.2 m3/s2 | Maximum magnitude of change of volumetric gas flow per second. This is a slew-rate limit, not the gas flow itself. |

Use nonnegative finite rate limits; zero holds the corresponding command.
For a 0.1 s elapsed sample interval, default maximum changes are 1 rad/s and
0.02 m3/s respectively. Bounds and slew limits are applied to requested commands;
inspect both requested and applied columns in actuators.csv.
Angular-speed conversion is omega = rpm*2*pi/60.
Gas flow refers to actual inlet volume, not standard litres per minute.

### Prescribed schedule

`schedule` is a list of rows with **(time_s omega_rad_s gasFlow_m3_s)**.
It is read in prescribed mode. Row times must increase strictly, values must
be finite, and the list must contain at least one row.

| Time (s) | Speed (rad/s) | Gas flow (m3/s) |
|---|---|---|
| 0 | 52.35987755982988 | 0 |
| 5 | 52.35987755982988 | 0 |
| 5.1 | 52.35987755982988 | 0.0186666666666667 |
| 60 | 52.35987755982988 | 0.0186666666666667 |

Values interpolate linearly between rows; first/last values are held outside
the row range. Requests are evaluated at sample times, so a ramp shorter than
sampleInterval may be poorly represented. Applied commands still obey the
bounds and rates. To study a smooth ramp, choose adequate sampling resolution.

### Measurement definitions

| Parameter | Default | Meaning and use |
|---|---|---|
| `probeMinLiquid` | 0.5 | Minimum liquid fraction for a valid oxygen reading. Must be greater than 0 and at most 1. A cell exactly at the threshold is valid if oxygen is finite; below it, oxygen is reported as NaN with valid = 0. |
| `measurements` | Three named points | Dictionary of user-defined probe entries. At least one point is required; add or remove entries to change sensor layout. |
| `lowerBulk` / `position` | (0.20 0.05 0.20) m | Default lower probe name and its (x,y,z) coordinates. |
| `middleBulk` / `position` | (0.20 0.05 0.45) m | Default middle probe name and coordinates. |
| `upperBulk` / `position` | (0.20 0.05 0.70) m | Default upper probe name and coordinates. |

Measurements are written inside the run directory to
`postProcessing/bioControl/0/measurements.csv` for a run starting at zero.
After restart, the new segment is in a folder named after the restart time
(for example `postProcessing/bioControl/20/measurements.csv`).
Columns are `time_s`, then `<name>_mol_m3`, `<name>_alphaLiquid` and
`<name>_valid` for each probe. Only the MPI master writes this combined file.
Rows are flushed at sampling times, so the file can be inspected during a run.

Probe names identify CSV columns and controller inputs. Positions must lie in
mesh cells, not outside the domain or inside excluded solid geometry. The
containing cell's value is sampled without interpolation; a deterministic MPI
owner prevents duplicate samples. Sensor noise, lag and filtering are not
included automatically.

### Settings located in other files and safe editing workflow

Initial dissolved oxygen and its boundary conditions are in `0/oxygen.liquid`
in the prepared run. Phase fractions/initial level come from the phase fields
and setFields settings. Bubble diameter is in `constant/phaseProperties`;
densities and viscosity are in the phase physicalProperties files. Mesh settings,
deltaT, endTime, writeInterval and the abort function are not bioProperties
parameters.

Edit bioProperties before starting or restarting: it is loaded at solver
construction, not live-reloaded while a simulation runs. No recompilation is
needed for dictionary edits. Restart compatibility checks require the same
controller mode, probe definitions, sampleInterval and deltaT. Saved actuator
commands override fresh-run initial values. Use a new run for a changed sensor
layout or incompatible controller state, and preserve physical parameters when
testing restart equivalence.

## Understanding postProcessing files and units

All paths below are relative to the prepared run directory. Numeric folder
names such as `0` or `20` identify the start of an output segment (usually
the initial run or a restart), not a probe number. Times in the files are
physical simulation seconds, not elapsed computer time.

### inletGasFlow and outletGasFlow: total air flow

The upstream `system/functions` configures both monitors using
`patchFlowRate` with `field=alphaPhi.gas`. It sums gas volumetric flux
over the named boundary patch. Look inside
`postProcessing/inletGasFlow/<segment>/` and
`postProcessing/outletGasFlow/<segment>/` for the text data file; read its
header for the time and summed-field column names.

| Monitor | Boundary | Quantity | Units | Normal sign |
|---|---|---|---|---|
| `inletGasFlow` | `inlet` | Sum of gas flux over inlet faces | m3/s | Negative when gas enters the tank |
| `outletGasFlow` | `outlet` | Sum of gas flux over outlet faces | m3/s | Positive when gas leaves the tank |

Boundary flux uses the outward normal. Thus an inlet reading of -0.0186667 m3/s
means approximately 1.12 m3/min of air entering. Multiply m3/s by 60 for m3/min,
or by 60000 for L/min. These are volumes at modeled inlet/local conditions,
not standard-volume units.

These monitors measure **all gas**, not oxygen alone, and they are rates,
not accumulated volumes. They use phase-weighted flux, so do not multiply the
reported value by gas fraction again. The inlet command in actuators.csv uses
positive values for supply; compare it with the negative of inletGasFlow.
Commands apply to the next step, and the files can have different sampling times.

During startup, inlet and outlet magnitudes need not match: gas can accumulate
or be displaced inside the tank. With constant gas density and no bulk gas
mass source, the gas-volume change approximately satisfies
`dVgas/dt = -(Qin_signed + Qout_signed)` when these are the only open boundaries.
At statistically steady holdup their time averages should balance.

The upstream monitors request output every 10 flow steps: with the default
deltaT = 0.001 s, this corresponds to 0.01 s. Check the copied
`system/functions` if your OF13 revision or local settings differ.
Reference: [upstream monitor settings](https://github.com/OpenFOAM/OpenFOAM-13/blob/562b5bd8679404cd1dd5859e58322b0ca13bd652/tutorials/multiphaseEuler/aeratedStirredTankMRF/system/functions).

### bioControl: oxygen, controller and evaluation records

This directory is written by our solver. MPI master writes one combined set of
CSV files in `postProcessing/bioControl/<segment>/`; no merging of per-processor
CSV files is needed. A restart creates a new segment and restores cumulative
budget/controller state from the checkpoint. Retain previous segments when
plotting a complete history, and handle any repeated boundary timestamps.

#### measurements.csv

Written at sampleInterval (default 0.1 s), including an initial sample at t = 0.

| Column | Units | Meaning |
|---|---|---|
| `time_s` | s | Measurement time. |
| `<name>_mol_m3` | mol O2/m3 liquid | Local dissolved oxygen at the named probe. Multiply by 32 for mg/L. NaN means the reading is invalid. |
| `<name>_alphaLiquid` | Dimensionless, 0–1 | Liquid fraction in the sampled cell. |
| `<name>_valid` | Flag, 0 or 1 | 1 means finite oxygen and sufficient liquid fraction; 0 means the controller should not use the oxygen reading as a valid measurement. |

The three last columns repeat for each configured probe. These are local
containing-cell values, not volume averages over the tank.

#### actuators.csv

Written at command sampling times (default every 0.1 s).

| Column | Units | Meaning |
|---|---|---|
| `time_s` | s | Time the request is evaluated. |
| `requestedOmega_rad_s` | rad/s | Stirrer speed requested by the chosen mode/controller. |
| `appliedOmega_rad_s` | rad/s | Speed after bounds and rate limiting, queued for the next flow step. |
| `requestedGasFlow_m3_s` | m3/s | Requested inlet gas supply, positive into the tank. |
| `appliedGasFlow_m3_s` | m3/s | Supply after bounds and rate limiting, queued for the next flow step. |

Multiply rad/s by 60/(2*pi) for rpm. Applied commands are not independent
measurements of boundary flow; use the patch-flow monitors to check that.
When actuatorsEnabled is false, command values are still logged but are not
installed in the flow model.

#### oxygenBalance.csv

Written every flow step. All oxygen inventory and cumulative columns are
**amounts in mol O2**, not concentrations or rates.

| Column | Units | Meaning |
|---|---|---|
| `time_s` | s | End time of the completed step. |
| `liquidInventory_mol` | mol | Physical dissolved oxygen: sum of alpha_liquid*C*cellVolume. |
| `regularisationInventory_mol` | mol | Additional numerical inventory from the minimum capacity in nearly dry cells. |
| `cumulativeSupply_mol` | mol | Time-integrated net gas-to-liquid transfer. Positive for net dissolution; may decrease during stripping. |
| `cumulativeUptake_mol` | mol | Time-integrated microbial consumption, counted positive when oxygen is removed. |
| `cumulativeBoundaryOut_mol` | mol | Net outward dissolved-oxygen transport across external boundaries, including the discretized advective/diffusive flux. Positive removes liquid oxygen; negative adds it. |
| `cumulativeWarmupChange_mol` | mol | Signed imposed inventory change while concentration is frozen and phase fractions evolve before oxygen activation. |
| `residual_mol` | mol | Discrepancy in the numerical oxygen balance, ideally small relative to inventory and exchanged amounts. |

The balance is:
`residual = liquidInventory + regularisationInventory - initialStoredInventory
- cumulativeSupply + cumulativeUptake + cumulativeBoundaryOut
- cumulativeWarmupChange`.

initialStoredInventory is the initial physical plus numerical inventory stored
in the checkpoint. To obtain an average uptake or transfer **rate**, subtract
two cumulative values and divide by their time separation; the result is mol/s.
This remains a liquid oxygen balance: it does not track depletion or exhaust
oxygen in the gas phase.

#### evaluation.csv

Written every flow step.

| Column | Units | Meaning |
|---|---|---|
| `time_s` | s | End time of the completed step. |
| `liquidVolume_m3` | m3 | Total liquid volume, sum of alpha_liquid*cellVolume. |
| `deficientLiquidFraction` | Dimensionless, 0–1 | Fraction of liquid volume in cells whose oxygen is below criticalOxygen. Multiply by 100 for percent. |
| `cumulativeDeficiencyTime_s` | s | Integral of deficientLiquidFraction over time after oxygen activation. |

For example, a deficient fraction of 0.2 sustained for 10 s contributes 2 s
to cumulativeDeficiencyTime. This is a volume-fraction-weighted exposure
measure, not the duration of starvation of an individual microorganism and
not simply elapsed time with any deficient region.

Use measurements.csv for the information available to the controller and
evaluation.csv to assess the full-field result. This prevents good readings
at a few sensors from being mistaken for adequate oxygen everywhere.
