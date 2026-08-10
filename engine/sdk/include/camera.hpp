#pragma once

#include "content_api.h"
#include "ecs.hpp"


inline thread_local const EngineContentCallContext* g_camera_call_context = nullptr;

class camera_callback_scope {
public:
    explicit camera_callback_scope(const EngineContentCallContext& context)
        : previous_(g_camera_call_context) {
        g_camera_call_context = &context;
    }
    ~camera_callback_scope() { g_camera_call_context = previous_; }

private:
    const EngineContentCallContext* previous_{};
};

template <typename PresentedMotion>
inline bool camera_follow_presented(
        const entity& value, EngineComponentId component,
        uint32_t position_offset, uint32_t valid_offset,
        uint32_t visible_offset) {
    (void)sizeof(PresentedMotion);
    const auto* context = value.call_context();
    EngineCameraFollowDesc desc{
        {sizeof(EngineCameraFollowDesc)}, value.id(), component,
        position_offset, valid_offset, visible_offset};
    return context && g_camera_call_context == context
        && context->engine && context->engine->camera_follow_entity
        && context->engine->camera_follow_entity(
            context->engine_context, context->world, &desc) != 0;
}

inline bool camera_zoom(float zoom) {
    return g_camera_call_context && g_camera_call_context->engine
        && g_camera_call_context->engine->camera_zoom
        && g_camera_call_context->engine->camera_zoom(
            g_camera_call_context->engine_context, zoom) != 0;
}
