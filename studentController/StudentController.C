// SPDX-License-Identifier: GPL-3.0-or-later
#include "Controller.hpp"
// Default student extension point: no feedback law is imposed.
// Only named probes, time and previous applied commands are available.
class StudentController final : public bio::Controller {
public:
    bio::Command update(const bio::Observation& measured) override {
        return measured.applied;
    }
};
extern "C" bio::Controller* createBioController() { return new StudentController; }
