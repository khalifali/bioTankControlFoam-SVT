// SPDX-License-Identifier: GPL-3.0-or-later
#include "Controller.hpp"
// OPTIONAL: select examples/OxygenPI.C in Make/files, then rebuild.
// These gains are educational guesses, not tuned or biologically validated.
class OxygenPI final : public bio::Controller {
    double integral_=0;
    const double target_=0.18; // mol/m3 liquid
    const double kp_=0.02;     // (m3 gas/s)/(mol/m3 liquid)
    const double ki_=0.002;    // kp/s
    const double bias_=0.006, low_=0, high_=0.025; // inlet m3/s; match case bounds
public:
    bio::Command update(const bio::Observation& m) override {
        double c=0;unsigned n=0;
        for(const auto& p:m.probes)if(p.valid){c+=p.concentration;++n;}
        if(!n) return m.applied; // Hold both commands and integral if all probes are dry.
        const double error=target_-c/n;
        const double trial=integral_+ki_*error*m.elapsed;
        const double request=bias_+kp_*error+trial;
        // Amplitude anti-windup only. Extend for restrictive solver slew limits.
        if(!((request>high_ && error>0)||(request<low_ && error<0)))integral_=trial;
        return {m.applied.omega,std::clamp(bias_+kp_*error+integral_,low_,high_)};
    }
    std::vector<double> save() const override{return {integral_};}
    void restore(const std::vector<double>& s) override {
        if(s.size()!=1 || !std::isfinite(s[0]))throw std::runtime_error("Incompatible PI checkpoint");
        integral_=s[0];
    }
};
extern "C" bio::Controller* createBioController(){return new OxygenPI;}
