#pragma once

#include "content_api.h"
#include "callback.hpp"

#include <cmath>

struct ViewState {
    float canvas_width{};
    float canvas_height{};
    float cursor_x{};
    float cursor_y{};
    float camera_x{};
    float camera_y{};
    float camera_zoom{1.0f};
    bool focused{};
    bool cursor_valid{};

    explicit operator bool() const {
        return canvas_width > 0.0f && canvas_height > 0.0f
            && camera_zoom > 0.0f;
    }

    float world_per_pixel() const {
        return *this ? 2.0f / (canvas_height * camera_zoom) : 0.0f;
    }

    vec2 screen_to_world(vec2 screen_position) const {
        const float scale = world_per_pixel();
        if (!*this || !std::isfinite(screen_position.x)
                || !std::isfinite(screen_position.y)) return {};
        return {
            camera_x + (screen_position.x - canvas_width * 0.5f) * scale,
            camera_y + (canvas_height * 0.5f - screen_position.y) * scale};
    }

    vec2 world_to_screen(vec2 world_position) const {
        const float scale = world_per_pixel();
        if (!*this || !std::isfinite(world_position.x)
                || !std::isfinite(world_position.y)) return {};
        return {
            (world_position.x - camera_x) / scale + canvas_width * 0.5f,
            (camera_y - world_position.y) / scale + canvas_height * 0.5f};
    }

    vec2 screen_size_to_world(vec2 pixel_size) const {
        const float scale = world_per_pixel();
        if (!*this || !std::isfinite(pixel_size.x)
                || !std::isfinite(pixel_size.y)) return {};
        return {std::abs(pixel_size.x) * scale,
            std::abs(pixel_size.y) * scale};
    }

    vec2 world_size_to_screen(vec2 world_size) const {
        const float scale = world_per_pixel();
        if (!*this || !std::isfinite(world_size.x)
                || !std::isfinite(world_size.y)) return {};
        return {std::abs(world_size.x) / scale,
            std::abs(world_size.y) / scale};
    }
};

inline ViewState view_state() {
    const auto* context = active_callback_context();
    EngineViewState raw{{sizeof(EngineViewState)}};
    if (!context || !context->engine || !context->engine->view_state
            || !context->engine->view_state(context->engine_context, &raw))
        return {};
    return {
        raw.canvas_width, raw.canvas_height,
        raw.cursor_x, raw.cursor_y,
        raw.camera_x, raw.camera_y, raw.camera_zoom,
        raw.focused != 0, raw.cursor_valid != 0
    };
}

inline vec2 screen_to_world(vec2 screen_position) {
    return view_state().screen_to_world(screen_position);
}

inline vec2 world_to_screen(vec2 world_position) {
    return view_state().world_to_screen(world_position);
}

inline vec2 screen_size_to_world(vec2 pixel_size) {
    return view_state().screen_size_to_world(pixel_size);
}

inline vec2 world_size_to_screen(vec2 world_size) {
    return view_state().world_size_to_screen(world_size);
}
