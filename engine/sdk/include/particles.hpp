#pragma once

#include "content_api.h"

#include <cstdint>
#include <type_traits>


template <typename Compute>
struct compute_traits;

namespace particles {

template <typename Compute>
bool spawn_many(
        const EngineContentCallContext& context,
        const typename compute_traits<Compute>::state* states,
        const typename compute_traits<Compute>::instance* instances,
        std::uint32_t count) {
    using traits = compute_traits<Compute>;
    using state = typename traits::state;
    using instance = typename traits::instance;
    static_assert(std::is_trivially_copyable_v<state>);
    static_assert(std::is_trivially_copyable_v<instance>);
    static_assert(sizeof(state) == traits::state_size);
    static_assert(alignof(state) == traits::state_alignment);
    static_assert(sizeof(instance) == traits::instance_size);
    if (!count)
        return true;
    return context.engine && context.engine->submit_compute_spawns
        && context.engine->submit_compute_spawns(
            context.engine_context, traits::id,
            states, sizeof(state), instances, sizeof(instance), count) != 0;
}

template <typename Compute>
bool spawn(
        const EngineContentCallContext& context,
        const typename compute_traits<Compute>::state& state,
        const typename compute_traits<Compute>::instance& instance) {
    return spawn_many<Compute>(context, &state, &instance, 1u);
}

} // namespace particles
