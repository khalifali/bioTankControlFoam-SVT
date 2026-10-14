# Direct NCC LES repair — 14 October 2026

Host: khalifa-MS-7E34 (141.40.107.27). OpenFOAM 13, 20 MPI ranks.
Base branch: feat/aerated-les-ncc, ae9e98e031086b904269f55a0fdcd6fd14917842.

Repairs: remove inherited MRF zone and use movingWallVelocity on stirrer; decompose post-NCC fields rather than copying serial fields; supply correctMeshPhi=no as in the Foundation multiphase mixer tutorial; use zeroGradient for solved turbulence energy on NCC placeholder patches; project-local cubeRootVol boundary refresh and SmagorinskyZhang energy boundary adapter prevent invalid artificial boundary values entering dissipation. Original interior closures retained. Shared OpenFOAM installation unchanged.

Result: solver and reconstruction exit 0; two steps to 0.0002 s with deltaT=0.0001 s; solver wall time 7 seconds. Maximum reported advancing Courant 0.00205307525081. Absolute oxygen bookkeeping residual 1.39e-17 mol. NCC coverage minimum 0.999999758976 at final time.

Limits: startup test only, prescribed speed still near zero; oxygen supply/uptake inactive. No active oxygen transport validation, full-speed blade-passing, developed LES or mesh convergence claim. Mesh still has 15,165 concave cells. Fixes saved in isolated remote checkout, not pushed to GitHub.

Extended restart completed from 0.0002 to 0.01 s on 20 ranks: solver wall time 304 s, successful final reconstruction and moving-mesh VTK export. Aeration is scheduled by the inherited inlet Function1 at 5–5.1 s; oxygen equations activate at 10 s. This extended run remains before both activations. ParaView entry points are mesh.foam and VTK/case.vtk.series in the retained case directory.
