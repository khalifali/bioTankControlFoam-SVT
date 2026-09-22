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
steady conditions. The original RANS exercise uses fixed Euler timesteps; select timestep by
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

The model separates **equilibrium**, **transfer speed** and **available bubble
area**. The source entering the oxygen balance is

$$
S_{\mathrm{transfer}}=k_L a(C^*-C).
$$

It has units mol O2/(m3 mixture s). It is positive for undersaturated liquid,
zero at saturation, and negative for supersaturated liquid (oxygen stripping).
`kL*a` is calculated locally from the flow; it is not a constant entered in
`bioProperties`.

### 1. Equilibrium: Henry's law

$$
C^*=H_{cp}\,y_{O_2}\,(p+\mathrm{pressureOffset}).
$$

The product of oxygen mole fraction and absolute pressure is oxygen partial
pressure. Henry's law relates that partial pressure to the equilibrium dissolved
concentration in a dilute solution at fixed temperature. `henrySolubility` is
$H_{cp}$ in mol/(m3 Pa), the concentration/pressure convention, not its reciprocal.
`gasOxygenFraction` supplies $y_{O_2}$. The official case uses absolute `p`, so
`pressureOffset` is zero: do not add atmospheric pressure again.

With the defaults and 101325 Pa, $C^* = 1.175\times10^{-5}\times0.21\times101325
\approx0.250$ mol/m3 liquid, or about 8 mg/L. This is equilibrium with the assumed
air composition, not the concentration the tank necessarily reaches while cells
consume oxygen. Temperature and medium affect solubility; the constant must be
chosen for the intended experiment.

### 2. Transfer speed: a Sherwood closure

$$
Re_b=\frac{|\mathbf U_g-\mathbf U_L|d_b}{\nu_L},\qquad
Sc=\frac{\nu_L}{D},\qquad
Sh=2+0.6\sqrt{Re_b}\,Sc^{1/3},\qquad
k_L=\frac{Sh\,D}{d_b}.
$$

| Symbol | Meaning | Source in the model |
|---|---|---|
| $d_b$ | Bubble diameter [m] | Gas phase diameter model; baseline 1 mm |
| $\nu_L$ | Liquid kinematic viscosity [m2/s] | Liquid dynamic viscosity divided by density |
| $D$ | Molecular oxygen diffusivity [m2/s] | `molecularDiffusivity` |
| $Re_b$ | Slip Reynolds number [-] | Relative gas/liquid velocity |
| $Sc$ | Schmidt number [-] | Momentum diffusivity divided by molecular mass diffusivity |
| $Sh$ | Sherwood number [-] | Dimensionless mass-transfer coefficient |
| $k_L$ | Liquid-side transfer coefficient [m/s] | Calculated from $ShD/d_b$ |

The value 2 is the diffusion-only spherical limit in this closure. The additional
term represents enhanced transfer with relative motion. This is a
Ranz–Marshall-style approximation, implemented in the solver, rather than a
universal bubble correlation: interface mobility, contamination, deformation and
turbulence can change transfer. Its historical origin is Ranz and Marshall,
*Evaporation from drops*, Chemical Engineering Progress 48 (1952), 141–146 and
173–180; the bubble mass-transfer analogy requires validation.

Do not substitute `turbulentSchmidt` for $Sc$ here. That setting controls bulk
oxygen mixing through $D_{\mathrm{eff}}=D+\nu_t/Sc_t$; this interfacial closure
uses molecular $D$ and molecular liquid viscosity.

### 3. Bubble area and the headspace taper

For spherical bubbles, surface area divided by bubble volume is
$\pi d_b^2/(\pi d_b^3/6)=6/d_b$. Multiplying by gas volume fraction gives area
per mixture volume. The implemented expression is

$$
a=\frac{6\alpha_g}{d_b}w(\alpha_g),\qquad
w=1-3x^2+2x^3,\qquad
x=\mathrm{clamp}\!\left(
\frac{\alpha_g-\mathrm{fadeBegin}}{\mathrm{fadeEnd}-\mathrm{fadeBegin}},0,1\right).
$$

Thus $a$ has units m2/m3 mixture. Below `fadeBegin`, $w=1$; above `fadeEnd`,
$w=0$. The taper avoids treating the gas-filled headspace as dispersed bubbles.
It also omits transfer at segregated/free surfaces and gas cavities; no separate
free-surface closure is supplied. Test sensitivity to the thresholds.

For example, $\alpha_g=0.1$ and $d_b=0.001$ m give $a=600$ m2/m3 mixture.
If the local calculated $k_L$ were $10^{-4}$ m/s, then $k_La=0.06$ s−1.
At $C^*=0.25$ and $C=0.15$ mol/m3 liquid, supply would be
$0.06(0.25-0.15)=0.006$ mol/(m3 mixture s). The chosen $k_L$ in this example is
illustrative; the actual solver calculates it from the local flow.

Because area is already per mixture volume, do not multiply this source by
$\alpha_L$ again. A coefficient reported per liquid volume would instead be
$k_La/\alpha_L$ in cells with nonzero liquid fraction. Keep this convention in
mind when comparing experimental vessel-average `kLa` values.

Fixed `gasOxygenFraction = 0.21` neglects bubble oxygen depletion. Supply is
accounted as transfer from an assumed gas reservoir; there is no transported
gas oxygen inventory or claimed combined gas-plus-liquid oxygen balance.

## Biology: oxygen-limited uptake

The model uses a Monod-type saturating uptake law:

$$
r_L=m(t)q_{\max}X\frac{C}{K_O+C},\qquad
S_{\mathrm{biology}}=-\alpha_Lr_L.
$$

Here $r_L$ is positive consumption per liquid volume, while
$S_{\mathrm{biology}}$ is the negative source per mixture volume used in the
transport equation. `biomass` supplies $X$ [kg biomass/m3 liquid],
`specificUptake` supplies $q_{\max}$ [mol O2/(kg biomass s)], and
`halfSaturation` supplies $K_O$ [mol/m3 liquid]. $m(t)$ is 1 before
`demandChangeTime` and `demandMultiplier` for intervals starting at or after that
time. Reactions remain off until `oxygenStartTime`.

This empirical law represents limited uptake when oxygen is scarce. At zero
oxygen it gives zero uptake; at $C=K_O$ uptake is half the current maximum;
at high $C$ it approaches $m q_{\max}X$. At low $C$, the factor is approximately
$C/K_O$. It does not subtract a fixed amount regardless of oxygen availability.
Biomass is uniform and prescribed: there is no growth equation, substrate
limitation, cell death or transported biomass. The demand step is an imposed
disturbance, not simulated growth.

For the default $q_{\max}X=0.002$ and $C=0.15$, uptake before the demand step is
$0.002\times0.15/(0.01+0.15)=0.001875$ mol/(m3 liquid s). In a cell with
$\alpha_L=0.9$, the mixture-volume sink is $-0.0016875$ mol/(m3 mixture s).
At 30 s the demand factor becomes 1.5, increasing uptake by 50% **at the same
concentration**. The concentration then evolves with transport and transfer.

In a well-mixed region with constant liquid fraction and no external transport,
a stationary balance requires $k_La(C^*-C)=\alpha_Lr_L$. Positive uptake therefore
requires concentration below saturation when bubble transfer provides the supply.
Increasing gas flow or stirring changes flow, area and transfer; it does not
set $C$ directly. Spatially nonuniform tanks can still contain oxygen-poor regions.

`criticalOxygen` is a separate evaluation threshold. It neither changes the
Monod curve nor sets the student's control target. Reduced consumption caused
by starvation is not evidence of successful control. See the
[worked uptake examples](aerated-tank-walkthrough.md#microbial-uptake-what-the-sink-term-does)
and [mode selection](controller.md#choose-the-operating-mode).

## Numerical treatment and inventory

The default `oxygenIntegration splitEuler` uses conservative implicit Euler
transport followed by a local implicit positive Monod/transfer solve. This first-order split must be checked by reducing deltaT.
Upwind scalar advection and uncorrected diffusion provide a robust baseline;
mesh nonorthogonality and numerical diffusion still require convergence studies.

The separate [LES exercise](les-exercise.md#coupled-midpoint-oxygen-update) sets
`oxygenIntegration midpoint` and couples transport, transfer and uptake in one
second-order scalar step. Its balance uses the same midpoint rates and fluxes.
The RANS default is unchanged. The upstream bounded phase-fraction solver remains
Euler-based, so this option does not make the full two-fluid system second order.
A restart must preserve the chosen oxygen integration method.

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
