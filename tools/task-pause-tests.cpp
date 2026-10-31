#include "Common/TaskPauseGate.h"
#include <chrono>
#include <future>
#include <iostream>
#include <stdexcept>
#include <thread>

void require_pause(bool value)
{
    if (!value) {
        throw std::runtime_error("pause regression failed");
    }
}

int main()
{
    using namespace std::chrono_literals;
    asst::TaskPauseGate gate;
    gate.begin_io();
    gate.pause();
    gate.checkpoint();
    require_pause(gate.state() == 1);
    gate.end_io();
    gate.resume();
    require_pause(gate.state() == 0);
    gate.pause();
    const auto epoch = gate.epoch();
    gate.pause();
    require_pause(gate.epoch() == epoch && gate.state() == 1);
    auto worker = std::async(std::launch::async, [&] {
        gate.checkpoint();
        return 42;
    });
    for (int i = 0; i < 100 && gate.state() != 2; ++i) {
        std::this_thread::sleep_for(1ms);
    }
    const bool parked = gate.state() == 2;
    const bool blocked = worker.wait_for(30ms) == std::future_status::timeout;
    gate.resume();
    require_pause(parked && blocked);
    require_pause(worker.get() == 42 && gate.state() == 0 && gate.epoch() > epoch);
    for (int i = 0; i < 100; ++i) {
        gate.pause();
        auto pending = std::async(std::launch::async, [&] { gate.checkpoint(); });
        gate.resume();
        require_pause(pending.wait_for(1s) == std::future_status::ready);
        pending.get();
    }
    std::cout << "PASS: pause acknowledgement, retained stack, resume, epoch invalidation, cancellation wakeup races\n";
}
