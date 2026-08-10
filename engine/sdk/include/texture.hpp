#pragma once

#include "content_api.h"
#include "content_types.h"


template <typename Texture>
struct texture_traits;

template <typename Texture>
const EngineTextureSlice& texture() {
    return texture_traits<Texture>::value;
}

inline vec2 texture_world_size(
        const EngineTextureSlice& value,
        float pixels_per_world_unit) {
    if (pixels_per_world_unit <= 0.0f) return {};
    return {
        static_cast<float>(value.pixel_width) / pixels_per_world_unit,
        static_cast<float>(value.pixel_height) / pixels_per_world_unit
    };
}

inline vec4 texture_uv(const EngineTextureSlice& value) {
    return {value.uv_x, value.uv_y, value.uv_width, value.uv_height};
}
