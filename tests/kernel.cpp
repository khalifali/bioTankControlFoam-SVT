// SPDX-License-Identifier: GPL-3.0-or-later
#include "Controller.hpp"
#include <cassert>
#include <iostream>
int main() {
    // Dissolution must approach equilibrium without overshoot for any dt.
    for(double dt:{0.001,1.0,1000.0}) {
        const double c=bio::reaction(0.1,dt,0.3,0.25,0,0.01);
        assert(c>=0.1 && c<=0.25);
        assert(std::abs(c-(0.1+dt*0.3*0.25)/(1+dt*0.3))<1e-13);
        const double next=bio::reaction(0.1,dt,0.3,0.25,0.02,0.01);
        assert(next>=0);
        assert(std::abs(next-0.1-dt*(0.3*(0.25-next)-0.02*next/(0.01+next)))<1e-12);
    }
    assert(bio::reaction(0,1,0,0.25,1,0.01)==0);
    assert(bio::dispersedWeight(1,0.3,0.7)==0);
    assert(bio::dispersedWeight(0,0.3,0.7)==1);
    assert(std::abs(bio::dispersedWeight(0.5,0.3,0.7)-0.5)<1e-14);
    assert(bio::limited(10,1,0,5,2,0.1)==1.2);
    assert(!bio::active(1,0.1,1));assert(bio::active(1.1,0.1,1));
    std::cout<<"PASS: reaction balance, positivity, equilibrium, dry-region cutoff, actuator limits, activation\n";
}
