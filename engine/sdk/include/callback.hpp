#pragma once

#include "content_api.h"

#include <cstdint>

// The C ABI still passes a complete callback context to generated entry
// points.  Content-facing helpers read it from this synchronous, thread-local
// scope instead of requiring every call to forward it manually.
inline thread_local const EngineContentCallContext*
    g_active_callback_context = nullptr;

class active_callback_scope {
public:
    explicit active_callback_scope(const EngineContentCallContext& context)
        : previous_(g_active_callback_context) {
        g_active_callback_context = &context;
    }

    ~active_callback_scope() {
        g_active_callback_context = previous_;
    }

    active_callback_scope(const active_callback_scope&) = delete;
    active_callback_scope& operator=(const active_callback_scope&) = delete;

private:
    const EngineContentCallContext* previous_{};
};

inline const EngineContentCallContext* active_callback_context() {
    return g_active_callback_context;
}

inline bool active_callback_matches(
        const EngineContentCallContext& candidate) {
    const auto* active = active_callback_context();
    return active && active->engine == candidate.engine
        && active->engine_context == candidate.engine_context
        && active->world == candidate.world;
}

inline std::uint64_t active_callback_tick() {
    const auto* context = active_callback_context();
    return context ? context->tick : 0u;
}

inline float active_callback_delta_time() {
    const auto* context = active_callback_context();
    return context ? static_cast<float>(context->delta_time) : 0.0f;
}
