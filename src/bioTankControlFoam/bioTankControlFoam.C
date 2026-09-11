// SPDX-License-Identifier: GPL-3.0-or-later
// Extends the Foundation 13 multiphaseEuler module without modifying upstream.
#include "bioTankControlFoam.H"
#include "addToRunTimeSelectionTable.H"
#include "fvmDdt.H"
#include "fvmDiv.H"
#include "fvmLaplacian.H"
#include "PstreamReduceOps.H"
#include "meshSearch.H"
#include "OSspecific.H"
#include "IStringStream.H"
#include <dlfcn.h>
#include <iomanip>
#include <limits>

namespace Foam { namespace solvers {
defineTypeNameAndDebug(bioTankControlFoam,0);
addToRunTimeSelectionTable(solver,bioTankControlFoam,fvMesh);

scalar bioTankControlFoam::coeff(const word& key,const dimensionSet& dims) const {
    scalar v=dimensionedScalar(key,dims,cfg_).value();
    if(!std::isfinite(v))FatalErrorInFunction<<key<<" must be finite"<<exit(FatalError);
    return v;
}
scalar bioTankControlFoam::inventory(bool regularised) const {
    scalar sum=0;
    forAll(oxygen_,i)sum+=(regularised?capacity_[i]:liquid_[i])*oxygen_[i]*mesh.V()[i];
    reduce(sum,sumOp<scalar>());return sum;
}

bioTankControlFoam::bioTankControlFoam(fvMesh& mesh)
: multiphaseEuler(mesh),
  cfg_(IOobject("bioProperties",runTime.constant(),mesh,IOobject::MUST_READ,IOobject::NO_WRITE)),
  state_(IOobject("bioControlState",runTime.name(),"uniform",mesh,
      runTime.value()>0?IOobject::MUST_READ:IOobject::READ_IF_PRESENT,IOobject::AUTO_WRITE)),
  liquid_(phases_[cfg_.lookup<word>("liquidPhase")]),
  gas_(phases_[cfg_.lookup<word>("gasPhase")]),
  oxygen_(IOobject("oxygen.liquid",runTime.name(),mesh,IOobject::MUST_READ,IOobject::AUTO_WRITE),mesh),
  capacity_(IOobject("oxygenCapacity",runTime.name(),mesh,IOobject::NO_READ,IOobject::NO_WRITE),
      max(liquid_,dimensionedScalar(dimless,coeff("residualCapacity",dimless)))),
  kla_(IOobject("kLa",runTime.name(),mesh,IOobject::NO_READ,IOobject::AUTO_WRITE),mesh,dimensionedScalar(dimless/dimTime,0)),
  saturation_(IOobject("oxygenEquilibrium",runTime.name(),mesh,IOobject::NO_READ,IOobject::AUTO_WRITE),mesh,dimensionedScalar(dimMoles/dimVolume,0)),
  mode_(cfg_.lookup<word>("controller")),
  interval_(coeff("sampleInterval",dimTime)),
  lastSample_(state_.lookupOrDefault<scalar>("lastSample",runTime.value())),
  totalSupply_(state_.lookupOrDefault<scalar>("supply",0)),
  totalUptake_(state_.lookupOrDefault<scalar>("uptake",0)),
  totalBoundary_(state_.lookupOrDefault<scalar>("boundaryOut",0)),
  totalWarmup_(state_.lookupOrDefault<scalar>("warmupChange",0)),
  initial_(state_.lookupOrDefault<scalar>("initialInventory",inventory(true))),
  deficiencyTime_(state_.lookupOrDefault<scalar>("deficiencyTime",0)),
  applied_{state_.lookupOrDefault<scalar>("omega",coeff("initialOmega",dimless/dimTime)),
      state_.lookupOrDefault<scalar>("gasFlow",coeff("initialGasFlow",dimVolume/dimTime))}
{
    if(mesh.dynamic() || !transient() || LTS)
        FatalErrorInFunction<<"Use a fixed mesh and transient Euler time stepping"<<exit(FatalError);
    if(!liquid_.isochoric() || !gas_.isochoric() || phases_.size()!=2)
        FatalErrorInFunction<<"Baseline requires two constant-density phases"<<exit(FatalError);
    if(oxygen_.dimensions()!=dimMoles/dimVolume)
        FatalErrorInFunction<<"oxygen.liquid must be mol/m3 of liquid"<<exit(FatalError);
    const scalar dt=runTime.deltaTValue();
    if(runTime.controlDict().lookupOrDefault<bool>("adjustTimeStep",false))
        FatalErrorInFunction<<"Use fixed deltaT for reproducible control timing"<<exit(FatalError);
    for(const word& key:{word("sampleInterval"),word("oxygenStartTime"),word("controlStartTime"),word("demandChangeTime")}) {
        const scalar v=coeff(key,dimTime);
        if(v<0 || mag(v/dt-round(v/dt))>1e-6)
            FatalErrorInFunction<<key<<" must be nonnegative and aligned with deltaT"<<exit(FatalError);
    }
    if(interval_<=0 || coeff("residualCapacity",dimless)<=0 || coeff("residualCapacity",dimless)>1e-3
       || coeff("molecularDiffusivity",dimArea/dimTime)<=0 || coeff("turbulentSchmidt",dimless)<=0
       || coeff("halfSaturation",dimMoles/dimVolume)<=0 || coeff("biomass",dimMass/dimVolume)<0
       || coeff("specificUptake",dimMoles/dimMass/dimTime)<0 || coeff("demandMultiplier",dimless)<0
       || coeff("henrySolubility",dimMoles/dimVolume/dimPressure)<0
       || coeff("gasOxygenFraction",dimless)<0 || coeff("gasOxygenFraction",dimless)>1
       || coeff("fadeBegin",dimless)<0 || coeff("fadeEnd",dimless)>1
       || coeff("fadeBegin",dimless)>=coeff("fadeEnd",dimless)
       || coeff("probeMinLiquid",dimless)<=0 || coeff("probeMinLiquid",dimless)>1
       || coeff("criticalOxygen",dimMoles/dimVolume)<0)
        FatalErrorInFunction<<"Invalid bioProperties coefficients"<<exit(FatalError);
    if(mode_!="constant" && mode_!="prescribed" && mode_!="student")
        FatalErrorInFunction<<"controller must be constant, prescribed or student"<<exit(FatalError);
    if(mode_=="prescribed") {
        const List<vector> rows(cfg_.lookup("schedule"));
        if(rows.empty())FatalErrorInFunction<<"Empty schedule"<<exit(FatalError);
        forAll(rows,i)if(!std::isfinite(mag(rows[i])) || (i && rows[i].x()<=rows[i-1].x()))
            FatalErrorInFunction<<"Schedule must have finite values and increasing times"<<exit(FatalError);
    }
    // Allocate old capacity before the first phase evolution (Euler storage).
    capacity_.oldTime(); oxygen_.oldTime();
    mesh.schemes().setFluxRequired(oxygen_.name());
    if(gMin(oxygen_.primitiveField())<0)FatalErrorInFunction<<"Negative initial oxygen"<<exit(FatalError);
    const dictionary& probes=cfg_.subDict("measurements");
    names_=probes.toc();positions_.setSize(names_.size());cells_.setSize(names_.size());
    if(names_.empty())FatalErrorInFunction<<"Specify at least one measurement"<<exit(FatalError);
    const meshSearch& search=meshSearch::New(mesh);
    forAll(names_,i) {
        positions_[i]=probes.subDict(names_[i]).lookup<vector>("position");
        label c=search.findCell(positions_[i]),owner=c>=0?Pstream::myProcNo():labelMax;
        reduce(owner,minOp<label>());
        if(owner==labelMax)FatalErrorInFunction<<"Probe outside mesh: "<<names_[i]<<exit(FatalError);
        cells_[i]=owner==Pstream::myProcNo()?c:-1;
    }
    if(runTime.value()>0 && (state_.lookup<word>("controller")!=mode_
        || state_.lookup<wordList>("probeNames")!=names_
        || state_.lookup<vectorField>("probePositions")!=positions_
        || state_.lookup<scalar>("sampleInterval")!=interval_
        || state_.lookup<scalar>("deltaT")!=dt))
        FatalErrorInFunction<<"Restart must preserve controller, probes, sample interval and deltaT"<<exit(FatalError);
    if(runTime.value()>0 && cfg_.lookupOrDefault<bool>("actuatorsEnabled",true)) {
        // Written phase phi fields are already relative to the frame USED in
        // the last completed step, which can differ from the next queued command.
        // Restore that frame without transforming the just-read fluxes. preSolve
        // then performs the ordinary old-frame -> new-frame command update.
        installedOmega_=state_.lookup<scalar>("installedOmega");
        dictionary zones(static_cast<const IOdictionary&>(MRF));
        forAllConstIter(dictionary,zones,it)if(it().isDict())zones.subDict(it().keyword()).set("omega",installedOmega_);
        const_cast<IOMRFZoneList&>(MRF).MRFZoneList::reset(zones);
    }
    for(const word& key:{word("Omega"),word("GasFlow")}) {
        const dimensionSet dims=key=="Omega"?dimless/dimTime:dimVolume/dimTime;
        const scalar lo=coeff(word("min"+key),dims), hi=coeff(word("max"+key),dims);
        const scalar v=key=="Omega"?applied_.omega:applied_.gasFlow;
        if(lo>hi || v<lo || v>hi || (key=="GasFlow" && lo<0))
            FatalErrorInFunction<<"Invalid initial/restarted actuator bounds"<<exit(FatalError);
    }
    if(Pstream::master()) {
        fileName folder=runTime.globalPath()/"postProcessing"/"bioControl"/runTime.name();mkDir(folder);
        // A restart writes a new time segment, preserving previous segments.
        probesLog_.open((folder/"measurements.csv").c_str());
        commandLog_.open((folder/"actuators.csv").c_str());
        balanceLog_.open((folder/"oxygenBalance.csv").c_str());
        evaluationLog_.open((folder/"evaluation.csv").c_str());
        if(!probesLog_||!commandLog_||!balanceLog_||!evaluationLog_)
            FatalErrorInFunction<<"Cannot open CSV logs"<<exit(FatalError);
        probesLog_<<std::setprecision(17)<<"time_s";
        for(const word& n:names_)probesLog_<<','<<n<<"_mol_m3,"<<n<<"_alphaLiquid,"<<n<<"_valid";
        probesLog_<<'\n';
        commandLog_<<std::setprecision(17)<<"time_s,requestedOmega_rad_s,appliedOmega_rad_s,requestedGasFlow_m3_s,appliedGasFlow_m3_s\n";
        balanceLog_<<std::setprecision(17)<<"time_s,liquidInventory_mol,regularisationInventory_mol,cumulativeSupply_mol,cumulativeUptake_mol,cumulativeBoundaryOut_mol,cumulativeWarmupChange_mol,residual_mol\n";
        evaluationLog_<<std::setprecision(17)<<"time_s,liquidVolume_m3,deficientLiquidFraction,cumulativeDeficiencyTime_s\n";
        if(mode_=="student") {
            fileName library=cfg_.lookup<fileName>("studentLibrary");library.expand();
            plugin_=dlopen(library.c_str(),RTLD_NOW|RTLD_LOCAL);
            if(!plugin_)FatalErrorInFunction<<dlerror()<<exit(FatalError);
            auto create=reinterpret_cast<bio::Controller*(*)()>(dlsym(plugin_,"createBioController"));
            if(!create)FatalErrorInFunction<<"Missing createBioController"<<exit(FatalError);
            controller_.reset(create());
            if(!controller_)FatalErrorInFunction<<"Null controller"<<exit(FatalError);
            if(runTime.value()>0) {
                const List<scalar> saved(state_.lookup("studentState"));
                try{controller_->restore(std::vector<double>(saved.begin(),saved.end()));}
                catch(const std::exception& e){FatalErrorInFunction<<e.what()<<exit(FatalError);}
            }
        }
    }
    // Initial reading does not integrate a fictitious pre-simulation interval.
    if(runTime.value()==0)sample();
    persist();
}
bioTankControlFoam::~bioTankControlFoam(){controller_.reset();if(plugin_)dlclose(plugin_);}

void bioTankControlFoam::sample() {
    const scalar t=runTime.value(), elapsed=t-lastSample_;
    bio::Observation obs{t,elapsed,{},applied_};
    forAll(names_,i) {
        scalar c=cells_[i]>=0?oxygen_[cells_[i]]:0;
        scalar al=cells_[i]>=0?liquid_[cells_[i]]:0;
        reduce(c,sumOp<scalar>());reduce(al,sumOp<scalar>());
        const bool valid=al>=coeff("probeMinLiquid",dimless) && std::isfinite(c);
        obs.probes.push_back({names_[i].c_str(),valid?c:std::numeric_limits<double>::quiet_NaN(),al,valid});
    }
    bio::Command request=applied_;
    if(Pstream::master()) {
        if(mode_=="student" && t>=coeff("controlStartTime",dimTime)) {
            try{request=controller_->update(obs);}
            catch(const std::exception& e){FatalErrorInFunction<<e.what()<<exit(FatalError);}
        }
        if(mode_=="prescribed") {
            const List<vector> rows(cfg_.lookup("schedule"));vector r=rows.first();
            forAll(rows,i) {
                if(t>=rows[i].x())r=rows[i];
                if(i+1<rows.size() && t>=rows[i].x() && t<rows[i+1].x()) {
                    scalar f=(t-rows[i].x())/(rows[i+1].x()-rows[i].x());r=(1-f)*rows[i]+f*rows[i+1];break;
                }
            }
            request={r.y(),r.z()};
        }
    }
    Pstream::scatter(request.omega);Pstream::scatter(request.gasFlow);
    try {
        applied_.omega=bio::limited(request.omega,applied_.omega,coeff("minOmega",dimless/dimTime),coeff("maxOmega",dimless/dimTime),coeff("omegaRate",dimless/sqr(dimTime)),elapsed);
        applied_.gasFlow=bio::limited(request.gasFlow,applied_.gasFlow,coeff("minGasFlow",dimVolume/dimTime),coeff("maxGasFlow",dimVolume/dimTime),coeff("gasFlowRate",dimVolume/sqr(dimTime)),elapsed);
    }catch(const std::exception& e){FatalErrorInFunction<<e.what()<<exit(FatalError);}
    if(Pstream::master()) {
        probesLog_<<t;for(const auto& p:obs.probes)probesLog_<<','<<p.concentration<<','<<p.liquidFraction<<','<<p.valid;
        probesLog_<<std::endl;
        commandLog_<<t<<','<<request.omega<<','<<applied_.omega<<','<<request.gasFlow<<','<<applied_.gasFlow<<std::endl;
    }
    lastSample_=t;
}

void bioTankControlFoam::actuate() {
    if(!cfg_.lookupOrDefault<bool>("actuatorsEnabled",true))return; // Closed-box verification.
    const bool changed=applied_.omega!=installedOmega_ || applied_.gasFlow!=installedFlow_;
    if(applied_.omega!=installedOmega_) {
        // MRFZone::read() in OF13 does NOT rebuild omega_. Reset the zones.
        // Convert current relative fluxes using the old frame, then the new one.
        forAll(movingPhases_,i)MRF.makeAbsolute(movingPhases_[i].phiRef());
        MRF.makeAbsolute(phi_);
        dictionary zones(static_cast<const IOdictionary&>(MRF));
        forAllConstIter(dictionary,zones,it)if(it().isDict())zones.subDict(it().keyword()).set("omega",applied_.omega);
        const_cast<IOMRFZoneList&>(MRF).MRFZoneList::reset(zones);
        forAll(movingPhases_,i)MRF.makeRelative(movingPhases_[i].phiRef());
        MRF.makeRelative(phi_);
        // MRFPatchField looks up zones by name; it does not retain zone pointers.
        // Shaft BCs outside the MRF zone require their own angular-speed update.
        forAll(movingPhases_,i) {
            volVectorField& U=movingPhases_[i].URef();
            forAll(U.boundaryField(),patchi)if(U.boundaryField()[patchi].type()=="rotatingWallVelocity") {
                OStringStream os;U.boundaryField()[patchi].write(os);
                IStringStream is(os.str());dictionary d(is);d.set("omega",applied_.omega);
                U.boundaryFieldRef().set(patchi,fvPatchField<vector>::New(U.mesh().boundary()[patchi],U.internalField(),d).ptr());
            }
            U.correctBoundaryConditions();
        }
        installedOmega_=applied_.omega;
    }
    if(applied_.gasFlow!=installedFlow_) {
        const word name=cfg_.lookup<word>("gasInlet");
        const label patchi=mesh.boundaryMesh().findIndex(name);
        if(patchi<0)FatalErrorInFunction<<"Missing gas inlet "<<name<<exit(FatalError);
        volVectorField& U=gas_.URef();
        IStringStream is("{ type flowRateInletVelocity; alpha alpha.gas; volumetricFlowRate 0; value uniform (0 0 0); }");
        dictionary d(is);d.set("alpha",IOobject::groupName("alpha",gas_.name()));d.set("volumetricFlowRate",applied_.gasFlow);
        U.boundaryFieldRef().set(patchi,fvPatchField<vector>::New(mesh.boundary()[patchi],U.internalField(),d).ptr());
        U.correctBoundaryConditions();installedFlow_=applied_.gasFlow;
    }
    fluid_.correctBoundaryFlux();
    if(changed) {
        const label patchi=mesh.boundaryMesh().findIndex(cfg_.lookup<word>("gasInlet"));
        scalar Q=-sum(gas_.boundaryField()[patchi]*(gas_.URef().boundaryField()[patchi]&mesh.Sf().boundaryField()[patchi]));
        reduce(Q,sumOp<scalar>());
        Info<<"bioActuators: omega="<<applied_.omega<<" actualInletGasFlow="<<Q<<" requestedAppliedFlow="<<applied_.gasFlow<<endl;
    }
}
void bioTankControlFoam::preSolve(){actuate();multiphaseEuler::preSolve();}

void bioTankControlFoam::oxygenStep() {
    const scalar dt=runTime.deltaTValue(), before=inventory(true);
    capacity_=max(liquid_,dimensionedScalar(dimless,coeff("residualCapacity",dimless)));
    if(!bio::active(runTime.value(),dt,coeff("oxygenStartTime",dimTime))) {
        // Freeze concentration, not liquid inventory: gas holdup still evolves.
        totalWarmup_+=inventory(true)-before;
        return;
    }
    const scalar D=coeff("molecularDiffusivity",dimArea/dimTime);
    volScalarField diffusivity("oxygenDiffusivity",liquid_*dimensionedScalar(dimArea/dimTime,D));
    const word nutName=IOobject::groupName("nut",liquid_.name());
    if(mesh.foundObject<volScalarField>(nutName))
        diffusivity+=liquid_*mesh.lookupObject<volScalarField>(nutName)/coeff("turbulentSchmidt",dimless);
    // Use the phase solver's bounded/subcycle-averaged liquid flux.
    fvScalarMatrix transport(fvm::ddt(capacity_,oxygen_)+fvm::div(liquid_.alphaPhiRef(),oxygen_)
        -fvm::laplacian(diffusivity,oxygen_));
    transport.solve();
    const surfaceScalarField flux(transport.flux());
    scalar outward=0;
    forAll(mesh.boundary(),patchi)if(!mesh.boundary()[patchi].coupled())outward+=sum(flux.boundaryField()[patchi]);
    reduce(outward,sumOp<scalar>());totalBoundary_+=dt*outward;
    // Never silently clip away a conservation failure.
    label invalid=0;forAll(oxygen_,i)if(!std::isfinite(oxygen_[i]) || oxygen_[i]<0)invalid=1;
    reduce(invalid,maxOp<label>());
    if(invalid)FatalErrorInFunction<<"Nonfinite/negative oxygen: reduce timestep and check transport schemes"<<exit(FatalError);
    const tmp<volScalarField> td=gas_.d();
    const tmp<volScalarField> tmu=liquid_.fluidThermo().mu();
    const scalar H=coeff("henrySolubility",dimMoles/dimVolume/dimPressure), y=coeff("gasOxygenFraction",dimless);
    const scalar offset=coeff("pressureOffset",dimPressure);
    scalar q=coeff("specificUptake",dimMoles/dimMass/dimTime)*coeff("biomass",dimMass/dimVolume);
    if(bio::active(runTime.value(),dt,coeff("demandChangeTime",dimTime)))q*=coeff("demandMultiplier",dimless);
    const scalar half=coeff("halfSaturation",dimMoles/dimVolume);
    const scalar fadeBegin=coeff("fadeBegin",dimless),fadeEnd=coeff("fadeEnd",dimless);
    scalar supply=0,uptake=0;
    invalid=0;
    forAll(oxygen_,i) {
        const scalar d=td()[i],nu=tmu()[i]/liquid_.rho()[i],pressure=p_[i]+offset;
        if(d<=0 || nu<=0 || pressure<=0 || !std::isfinite(d+nu+pressure)){invalid=1;continue;}
        // Ranz-Marshall-style Sherwood approximation for spherical bubbles.
        const scalar Re=mag(gas_.URef()[i]-liquid_.URef()[i])*d/nu;
        const scalar Sh=2+0.6*sqrt(Re)*cbrt(nu/D);
        const scalar area=6*gas_[i]/d*bio::dispersedWeight(gas_[i],fadeBegin,fadeEnd);
        kla_[i]=D*Sh/d*area; // 1/s per mixture volume, not per liquid volume
        saturation_[i]=H*y*pressure;
        scalar next=0;
        try{next=bio::reaction(oxygen_[i],dt,kla_[i]/capacity_[i],saturation_[i],liquid_[i]*q/capacity_[i],half);}
        catch(const std::exception&){invalid=1;continue;}
        oxygen_[i]=next;
        supply+=dt*kla_[i]*(saturation_[i]-next)*mesh.V()[i];
        uptake+=dt*liquid_[i]*q*next/(half+next)*mesh.V()[i];
    }
    reduce(invalid,maxOp<label>());
    if(invalid)FatalErrorInFunction<<"Invalid transfer/reaction state (check absolute pressure and phase properties)"<<exit(FatalError);
    reduce(supply,sumOp<scalar>());reduce(uptake,sumOp<scalar>());
    totalSupply_+=supply;totalUptake_+=uptake;oxygen_.correctBoundaryConditions();
}

void bioTankControlFoam::persist() {
    state_.set("controller",mode_);state_.set("probeNames",names_);state_.set("probePositions",positions_);
    state_.set("sampleInterval",interval_);state_.set("deltaT",runTime.deltaTValue());state_.set("lastSample",lastSample_);
    state_.set("omega",applied_.omega);state_.set("gasFlow",applied_.gasFlow);
    state_.set("installedOmega",installedOmega_);
    state_.set("initialInventory",initial_);state_.set("supply",totalSupply_);state_.set("uptake",totalUptake_);
    state_.set("boundaryOut",totalBoundary_);state_.set("warmupChange",totalWarmup_);state_.set("deficiencyTime",deficiencyTime_);
    List<scalar> saved;
    if(Pstream::master() && controller_) {
        try{const auto data=controller_->save();saved.setSize(data.size());forAll(saved,i)saved[i]=data[i];}
        catch(const std::exception& e){FatalErrorInFunction<<e.what()<<exit(FatalError);}
    }
    Pstream::scatter(saved);state_.set("studentState",saved);
}
void bioTankControlFoam::postSolve() {
    oxygenStep();
    const scalar physical=inventory(false),stored=inventory(true);
    scalar volume=0,deficient=0;
    const scalar critical=coeff("criticalOxygen",dimMoles/dimVolume);
    forAll(oxygen_,i) {
        const scalar v=liquid_[i]*mesh.V()[i];volume+=v;
        if(oxygen_[i]<critical)deficient+=v;
    }
    reduce(volume,sumOp<scalar>());reduce(deficient,sumOp<scalar>());
    const scalar fraction=volume>VSMALL?deficient/volume:0;
    if(bio::active(runTime.value(),runTime.deltaTValue(),coeff("oxygenStartTime",dimTime)))
        deficiencyTime_+=fraction*runTime.deltaTValue();
    if(Pstream::master()) {
        balanceLog_<<runTime.value()<<','<<physical<<','<<stored-physical<<','<<totalSupply_<<','<<totalUptake_
            <<','<<totalBoundary_<<','<<totalWarmup_<<','<<stored-initial_-totalSupply_+totalUptake_+totalBoundary_-totalWarmup_<<std::endl;
        evaluationLog_<<runTime.value()<<','<<volume<<','<<fraction<<','<<deficiencyTime_<<std::endl;
    }
    if(runTime.value()-lastSample_>=interval_*(1-1e-9))sample();
    persist();multiphaseEuler::postSolve();
}
} }
