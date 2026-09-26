# LES rotating-mesh/NCC experiment

This experimental case extends `aeratedTankLES` from MRF to physical rotation
using Foundation OpenFOAM 13's NCC pattern from `simpleRushtonNCC`.

The first validation stage deliberately uses the existing prescribed 0-to-500 rpm
startup. OF13 `rotatingMotion` accepts a time-varying `omega Function1`, so the
rotor angle is the time integral of the same speed schedule. This isolates
MRF versus physical blade passage without introducing a second controller path.

Euler-Euler, liquid `SmagorinskyZhang`, gas `continuousGasKEqn`, oxygen and
biology are otherwise inherited from `aeratedTankLES`.

## Important current gate

The custom solver currently rejects dynamic meshes and its actuator implementation
is MRF-specific. Do not claim this case runnable until the dynamic-mesh solver
audit is completed and the native NCC smoke test passes. Closed-loop/student
variable-speed NCC additionally requires a runtime motion-control bridge; the
prescribed Function1 case does not.

The mesh construction follows OF13 `simpleRushtonNCC`: create two interface
baffles around `rotatingZone`, split them, then call
`createNonConformalCouples`. The exact patch extraction for the aerated
snappyHexMesh geometry must be verified in the native smoke test before the
case is promoted.
