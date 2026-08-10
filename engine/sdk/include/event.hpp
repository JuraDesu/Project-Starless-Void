#pragma once

#include "ecs.hpp"


template <typename Event>
struct event_traits;

constexpr std::uint64_t event_fingerprint(const char* value) {
    std::uint64_t result = 1469598103934665603ull;
    while (*value) {
        result ^= static_cast<unsigned char>(*value++);
        result *= 1099511628211ull;
    }
    return result ? result : 1ull;
}

template <typename Event>
bool dispatch(
        const EngineContentCallContext& context,
        entity subject,
        Event& event) {
    const EngineEventId id = event_traits<Event>::id;
    return id && context.engine && context.engine->dispatch_event && subject.alive()
        && context.engine->dispatch_event(
            context.engine_context, context.world, id, subject.id(),
            &event, static_cast<std::uint32_t>(sizeof(Event))) != 0;
}

template <typename Event>
bool entity::dispatch(Event& event) const {
    return content_ && dispatch(*content_, *this, event);
}
