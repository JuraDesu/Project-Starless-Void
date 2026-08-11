#pragma once

#include "ecs.hpp"

#include <cstdint>
#include <type_traits>


inline bool draw_instances(
        EngineComponentId component,
        const void* instances,
        std::uint32_t stride,
        std::uint32_t count,
        std::int32_t draw_order = INT32_MIN) {
    const auto* context = active_callback_context();
    return context && context->engine
        && context->engine->submit_render_instances
        && component && instances && stride
        && context->engine->submit_render_instances(
            context->engine_context, component, instances, stride, count,
            draw_order) != 0;
}

template <typename Component>
bool draw_many(
        const Component* instances,
        std::uint32_t count,
        std::int32_t draw_order = INT32_MIN) {
    static_assert(component_traits<Component>::size != 0,
        "render instance components must contain data");
    static_assert(std::is_trivially_copyable_v<Component>,
        "render instances must be trivially copyable");
    return draw_instances(component_traits<Component>::id, instances,
        sizeof(Component), count, draw_order);
}

template <typename Component>
bool draw(
        const Component& instance,
        std::int32_t draw_order = INT32_MIN) {
    return draw_many(&instance, 1u, draw_order);
}
