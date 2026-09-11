// Test-only controller: demonstrate checkpointed state, not a student strategy.
#include "Controller.hpp"
class StateController final : public bio::Controller {
    double calls_=0;
public:
    bio::Command update(const bio::Observation& m) override { ++calls_;return m.applied; }
    std::vector<double> save() const override{return {calls_};}
    void restore(const std::vector<double>& state) override {
        if(state.size()!=1)throw std::runtime_error("Missing counter checkpoint");
        calls_=state[0];
    }
};
extern "C" bio::Controller* createBioController(){return new StateController;}
