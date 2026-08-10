#pragma once

#include "ecs.hpp"

#include <cstdint>
#include <type_traits>


template <typename Component>
bool draw_many(
        const EngineContentCallContext& context,
        const Component* instances,
        std::uint32_t count,
        std::int32_t draw_order = INT32_MIN) {
    static_assert(component_traits<Component>::size != 0,
        "render instance components must contain data");
    static_assert(std::is_trivially_copyable_v<Component>,
        "render instances must be trivially copyable");
    return context.engine && context.engine->submit_render_instances
        && component_traits<Component>::id
        && context.engine->submit_render_instances(
            context.engine_context,
            component_traits<Component>::id,
            instances,
            sizeof(Component),
            count,
            draw_order) != 0;
}

template <typename Component>
bool draw(
        const EngineContentCallContext& context,
        const Component& instance,
        std::int32_t draw_order = INT32_MIN) {
    return draw_many(context, &instance, 1u, draw_order);
}
