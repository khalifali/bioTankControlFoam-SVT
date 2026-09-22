// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include "multiphaseEuler.H"
#include "localIOdictionary.H"
#include "Controller.hpp"
#include <fstream>
#include <memory>

namespace Foam { namespace solvers {
class bioTankControlFoam : public multiphaseEuler {
    IOdictionary cfg_;
    localIOdictionary state_;
    phaseModel& liquid_;
    phaseModel& gas_;
    volScalarField oxygen_, capacity_, kla_, saturation_;
    word mode_, oxygenIntegration_;
    autoPtr<volScalarField> oldDiffusivity_, oldKla_, oldSaturation_, oldLiquid_;
    wordList names_;
    vectorField positions_;
    labelList cells_;
    scalar interval_, lastSample_, totalSupply_, totalUptake_, totalBoundary_, totalWarmup_, initial_;
    scalar deficiencyTime_;
    bio::Command applied_;
    scalar installedOmega_=-GREAT, installedFlow_=-GREAT;
    void* plugin_=nullptr;
    std::unique_ptr<bio::Controller> controller_;
    std::ofstream probesLog_, commandLog_, balanceLog_, evaluationLog_;
    scalar coeff(const word&,const dimensionSet&) const;
    scalar inventory(bool regularised) const;
    void sample();
    void persist();
    void actuate();
    void oxygenStep();
    tmp<volScalarField> oxygenDiffusivity() const;
    void transferCoefficients();
    void oxygenMidpointStep();
public:
    TypeName("bioTankControlFoam");
    explicit bioTankControlFoam(fvMesh&);
    ~bioTankControlFoam() override;
    void preSolve() override;
    void postSolve() override;
};
} }
