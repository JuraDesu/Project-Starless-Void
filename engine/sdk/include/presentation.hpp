#pragma once

#include "content_api.h"


struct PresentationTiming {
    bool valid{};
    std::uint64_t latest_simulation_tick{};
    std::uint64_t segment_tick{};
    double presentation_tick{};
    float alpha{};
    float tick_seconds{};
};

inline PresentationTiming presentation_timing(
        const EngineContentCallContext& context) {
    EnginePresentationTiming timing{};
    timing.header = {sizeof(EnginePresentationTiming)};
    const bool queried = context.engine && context.engine->presentation_timing
        && context.engine->presentation_timing(context.engine_context, &timing);
    return {
        queried && timing.valid != 0u,
        timing.latest_simulation_tick,
        timing.segment_tick,
        timing.presentation_tick,
        timing.alpha,
        timing.tick_seconds
    };
}
