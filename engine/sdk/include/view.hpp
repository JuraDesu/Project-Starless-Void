#pragma once

#include "content_api.h"
#include "callback.hpp"


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
