// Preserve OpenFOAM cubeRootVol internally and populate boundary filter widths
// from owner cells after NCC mesh motion, before LES dissipation is evaluated.
#include "cubeRootVolDelta.H"
#include "addToRunTimeSelectionTable.H"
namespace Foam { namespace LESModels {
class nccCubeRootVolDelta : public cubeRootVolDelta
{
    void updateBoundary()
    {
        forAll(delta_.boundaryField(), patchi)
        {
            delta_.boundaryFieldRef()[patchi] ==
                delta_.boundaryField()[patchi].patchInternalField();
        }
    }
public:
    TypeName("nccCubeRootVol");
    nccCubeRootVolDelta(const word& name, const momentumTransportModel& model,
                       const dictionary& dict)
    : cubeRootVolDelta(name, model, dict) { updateBoundary(); }
    virtual void read(const dictionary& dict)
    { cubeRootVolDelta::read(dict); updateBoundary(); }
    virtual void correct()
    { cubeRootVolDelta::correct(); updateBoundary(); }
};
defineTypeNameAndDebug(nccCubeRootVolDelta, 0);
addToRunTimeSelectionTable(LESdelta, nccCubeRootVolDelta, dictionary);
}}
