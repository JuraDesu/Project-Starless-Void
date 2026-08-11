#pragma once

#include "content_api.h"
#include "callback.hpp"
#include "ecs.hpp"

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
    return context && active_callback_matches(*context)
        && context->engine && context->engine->camera_follow_entity
        && context->engine->camera_follow_entity(
            context->engine_context, context->world, &desc) != 0;
}

inline bool camera_zoom(float zoom) {
    const auto* context = active_callback_context();
    return context && context->engine
        && context->engine->camera_zoom
        && context->engine->camera_zoom(
            context->engine_context, zoom) != 0;
}
