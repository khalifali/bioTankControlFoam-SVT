#include "phaseSystem.H"
#include "makePhaseCompressibleMomentumTransportModel.H"
#include "SmagorinskyZhang.H"
namespace Foam { namespace LESModels {
template<class BasicMomentumTransportModel>
class nccSmagorinskyZhang : public SmagorinskyZhang<BasicMomentumTransportModel>
{
public:
    TypeName("nccSmagorinskyZhang");
    typedef typename BasicMomentumTransportModel::alphaField alphaField;
    typedef typename BasicMomentumTransportModel::rhoField rhoField;
    nccSmagorinskyZhang(const alphaField& alpha,const rhoField& rho,
        const volVectorField& U,const surfaceScalarField& alphaRhoPhi,
        const surfaceScalarField& phi,const viscosity& viscosity,
        const word& type=typeName)
    : SmagorinskyZhang<BasicMomentumTransportModel>
      (alpha,rho,U,alphaRhoPhi,phi,viscosity,type) {}
    virtual tmp<volScalarField> k() const
    {
        tmp<volScalarField> result=SmagorinskyZhang<BasicMomentumTransportModel>::k();
        auto& field=result.ref();
        forAll(field.boundaryField(),patchi)
        {
            if(field.mesh().boundary()[patchi].name().find("nonCouple")==0
               || field.mesh().boundary()[patchi].type()=="nonConformalError")
                field.boundaryFieldRef()[patchi] == field.boundaryField()[patchi].patchInternalField();
        }
        return result;
    }
};
}}
makeLESModel(nccSmagorinskyZhang);
