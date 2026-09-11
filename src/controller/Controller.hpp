// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <vector>
#include <string>
#include <stdexcept>
#include <cmath>
#include <algorithm>

namespace bio {
struct Command { double omega; double gasFlow; }; // rad/s; m3/s at inlet conditions
struct Measurement {
    std::string name;
    double concentration; // mol/m3 liquid; NaN when not valid
    double liquidFraction;
    bool valid;
};
struct Observation {
    double time, elapsed; // seconds
    std::vector<Measurement> probes;
    Command applied;
};
class Controller {
public:
    virtual ~Controller() = default;
    virtual Command update(const Observation&) = 0;
    virtual std::vector<double> save() const { return {}; }
    virtual void restore(const std::vector<double>& state) {
        if (!state.empty()) throw std::runtime_error("Unexpected controller state");
    }
};
inline double limited(double request, double old, double low, double high, double rate, double dt) {
    if (!std::isfinite(request+old+low+high+rate+dt) || low>high || rate<0 || dt<0)
        throw std::runtime_error("Invalid actuator command or limits");
    return std::clamp(std::clamp(request,old-rate*dt,old+rate*dt),low,high);
}
inline bool active(double time, double dt, double start) { return time-dt >= start-1e-9*dt; }

// Positive root of backward-Euler dissolution + Monod uptake.
// dc/dt = a*(sat-c) - q*c/(half+c). Rates include phase/capacity weighting.
inline double reaction(double c,double dt,double a,double sat,double q,double half) {
    if(!std::isfinite(c+dt+a+sat+q+half) || c<0 || dt<=0 || a<0 || sat<0 || q<0 || half<=0)
        throw std::runtime_error("Invalid reaction parameters");
    const double A=1+dt*a, b=A*half-c-dt*a*sat+dt*q, rhs=(c+dt*a*sat)*half;
    const double root=std::sqrt(b*b+4*A*rhs);
    return b>=0 ? (rhs==0 ? 0 : 2*rhs/(b+root)) : (-b+root)/(2*A);
}
// Dispersed-bubble closure; explicitly fades out before gas becomes continuous.
inline double dispersedWeight(double ag,double begin,double end) {
    if(ag<=begin)return 1;
    if(ag>=end)return 0;
    const double s=(ag-begin)/(end-begin);
    return 1-s*s*(3-2*s);
}
}
