# Physical model and conventions

## Quick introduction for students

This solver extends Foundation OpenFOAM 13's `multiphaseEuler` solver with
dissolved-oxygen transport, microbial consumption and a controller interface.
The tank contains water and air. Air enters through a sparger below the lower
impeller, rises through the liquid and can leave through the upper outlet.

### How the two phases are represented

The flow uses an **Euler–Euler two-fluid model**: both gas and liquid are
represented by fields on the same mesh. Each cell has a gas volume fraction
`alpha.gas` and a liquid volume fraction `alpha.liquid`, which sum to one.
For example, `alpha.gas = 0.1` means that gas occupies 10% of the cell volume.

Each phase has its own velocity, `U.gas` and `U.liquid`. They can differ,
allowing bubbles to rise relative to the water. Interphase forces, including
drag, exchange momentum between the phases. Individual bubble trajectories
and bubble surfaces are not resolved. The baseline represents dispersed
bubbles collectively using a prescribed diameter of 1 mm.

### Turbulence and stirring

**RANS** means Reynolds-averaged Navier–Stokes: turbulent fluctuations are
represented through a turbulence model. The liquid uses `kOmegaSSTSato`,
including a bubble-induced turbulence contribution. A transient RANS run can
show changing mean flow, but does not resolve the turbulent eddies as LES would.

**MRF** means multiple reference frames. The impeller geometry and mesh stay
fixed while rotating reference-frame regions and boundary conditions represent
stirring. Changing the rotation command changes this representation of stirring.
Individual blade-passage events are not reproduced; slowly varying control is
the intended application.

### Where oxygen goes

1. Air supplies oxygen through the bubbles.
2. A gas-to-liquid transfer model adds dissolved oxygen to the liquid according
   to local bubble area, transfer coefficient and departure from saturation.
3. Liquid motion and diffusion redistribute dissolved oxygen.
4. A microbial uptake term removes dissolved oxygen. Microorganisms are
   represented by a prescribed biomass concentration, without explicit particles.

`oxygen.liquid` is dissolved oxygen in **mol per cubic metre of liquid**.
It is not the gas oxygen fraction. The current gas composition is fixed at
an oxygen mole fraction of 0.21: gas-phase oxygen depletion is not transported.
Consequently, the model tracks a liquid oxygen balance supplied by an assumed
gas reservoir, not a conserved combined gas-plus-liquid oxygen inventory.
Dispersed-bubble transfer fades out in gas-rich regions; a separate free-surface
transfer model is not included.

### How this connects to control

Measurement points report local dissolved oxygen. The student controller can
use these readings to change impeller speed and inlet gas flow. These commands
affect mixing, gas distribution and oxygen supply; they do not directly impose
the oxygen concentration everywhere. The default case uses a prescribed
schedule, so feedback requires selecting and implementing a controller.
See [controller and measurements](controller.md) for the interface.

Read the sections below for equations, units and assumptions, then
[verification and validation](validation.md) before interpreting simulation
results. The default first-order numerics are a robust starting point; mesh,
time-step and numerical-diffusion sensitivity still need assessment.

## Tank and hydrodynamics

The pinned Foundation 13 tutorial contains water, air, wall baffles, a lower
Rushton turbine, an upper pitched-blade impeller, a sparger and an upper outlet.
Initial gas space starts at z=0.8 m. The official air density is 1.184 kg/m3,
water density 997 kg/m3 and liquid viscosity 8.904e-4 Pa s. Both phases are
isothermal and constant density. The default nominal rotation is 500 rpm,
equivalent to 52.35987756 rad/s, around the official negative-z axis.

Run `python3 scripts/geometry_report.py` to report exact OBJ bounds and groups
from the pinned installation. Inspect the gas inlet and impeller relationship
in ParaView before changing probe coordinates.
The inspected sparger surface spans z=-0.205 to 0 m and radial extents of about
0.1225 m; the impeller surface starts at z=0.084 m. Thus the sparger is below the
lower impeller. The inlet faces themselves lie at z=0 with x/y bounds approximately +/-0.1175 m.
Overall tank bounds span approximately z=-0.216 to 1.25 m and
radius 0.5 m: this is an industrial-scale tutorial, not the earlier 0.1 m tank.
Retain this scale for the official baseline. Rescaling requires revisiting inlet
flow, speed, mesh, mixing time and control timing rather than only coordinates.

Liquid turbulence retains `kOmegaSSTSato` RANS. MRF keeps the impeller geometry
stationary: it approximates rotation through rotating-zone terms and boundary
conditions, not blade passage. Slowly varying control is the intended use.
Rapid acceleration/deceleration would require separate validation and potentially
a transient rotating-mesh model. No explicit angular-acceleration source is added.

The source tutorial's large permitted Courant number targets fast approach to
steady conditions. This project uses fixed Euler timesteps; select timestep by
transient oxygen and controller sensitivity, not only solver stability.

## Dissolved oxygen

Let alpha be liquid fraction and C be mol O2 per m3 of liquid. The intended equation is

```
d(alpha C)/dt + div(alphaPhi_liquid C)
  = div(alpha (D + nut/Sc_t) grad(C)) + kL a (Cstar-C)
    - alpha qmax X C/(KO+C).
```

The advective flux is the phase solver's actual liquid `alphaPhi` (including
phase subcycling), not a separately reconstructed alpha*U flux. Oxygen is a
passive dilute constituent: its uptake/dissolution does not change bulk phase
densities or volume fractions. Hydrodynamics responds to controller commands,
not directly to dissolved-oxygen concentration.

Units: D [m2/s], Sc_t [-], kL [m/s], a [m2/m3 mixture], X [kg biomass/m3 liquid],
qmax [mol/(kg biomass s)], KO and Cstar [mol/m3 liquid]. The example biomass and
uptake are prescribed and uniform. A timed multiplier tests changing demand.
No biomass growth, substrate depletion or temperature dependence is solved.

## Gas-to-liquid oxygen transfer

The baseline uses the familiar spherical-particle Sherwood approximation
Sh=2+0.6 sqrt(Re) Sc^(1/3), kL=Sh D/db, Re=|Ug-Ul|db/nu, Sc=nu/D.
It is a documented starting closure, not a validated universal bubble correlation:
interface mobility, contamination, bubble shape and turbulence can change transfer.
Reference origin: Ranz and Marshall, *Evaporation from drops*, Chemical Engineering
Progress 48 (1952), 141–146 and 173–180. The mass-transfer analogy is an approximation.

Use a=6 alpha_g/db in dispersed gas. A cubic smooth taper is one below gas fraction
fadeBegin and zero above fadeEnd. This prevents applying a dispersed-bubble area
to the gas-filled headspace. It also omits transfer at segregated/free surfaces
and gas cavities; the blend thresholds need sensitivity testing. A separate
free-surface transfer closure is not supplied.

Cstar=Hcp*yO2*pAbsolute. Hcp [mol/(m3 Pa)] is the concentration/pressure convention,
not its reciprocal. The illustrative constant gives about 0.25 mol/m3 at room
temperature and atmospheric air. It must be calibrated for the actual temperature,
medium and organism. `p` is absolute in the official case; pressureOffset is zero.
Fixed yO2=0.21 neglects oxygen depletion in air bubbles. Negative net transfer is
allowed for supersaturated water. Liquid supply is accounted as transfer from an
assumed gas reservoir; there is no claimed gas-plus-liquid oxygen balance.

## Numerical treatment and inventory

Conservative implicit Euler transport is followed by a local implicit positive
Monod/transfer solve. This first-order split must be checked by reducing deltaT.
Upwind scalar advection and uncorrected diffusion provide a robust baseline;
mesh nonorthogonality and numerical diffusion still require convergence studies.

Pure gas cells make alpha*C storage singular. The implemented transport capacity
is max(alpha,residualCapacity). The difference creates a small artificial oxygen
inventory, reported separately in oxygenBalance.csv. Uptake always uses actual
alpha, and transfer vanishes in gas-rich cells. Vary residualCapacity to show that
this numerical regularisation does not affect liquid predictions. Oxygen is never
silently clipped: a negative or nonfinite transported value aborts with guidance.

Before oxygenStartTime, C is frozen while alpha and flow evolve. Therefore liquid
inventory can change even with frozen C; the log records this imposed warm-up
inventory change explicitly. After activation, the balance includes transport
through external boundaries, net dissolution and biological uptake. Internal and
processor fluxes cancel and are excluded from external boundary accounting.

The regularised balance is:
inventory - initial - supply + uptake + boundaryOut - warmupChange = residual.
Subtracting the reported regularisation inventory gives physical liquid inventory.

## Biological/control evaluation

Reduced uptake during starvation is not successful control. Set a separate
criticalOxygen threshold. The evaluation log contains liquid volume, liquid-volume
fraction below that threshold, and its time integral after oxygen activation.
This integral is an aggregate deficiency exposure, not a trajectory history of
individual microorganisms. Full-field diagnostics are not exposed to the controller.
