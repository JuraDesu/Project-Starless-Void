#include "registry.hpp"

inline EngineAudioId audio_fx{};

$ g_init {
    static constexpr vec2 line_vertices[] = {
        {0.0f, 0.0f}, {1.0f, 0.0f}
    };
    static constexpr uint16_t line_indices[] = {0u, 1u};
    static constexpr vec2 quad_vertices[] = {
        {-0.5f, -0.5f}, {0.5f, -0.5f},
        {0.5f, 0.5f}, {-0.5f, 0.5f}
    };
    static constexpr uint16_t quad_indices[] = {
        0u, 1u, 2u, 0u, 2u, 3u
    };
    static constexpr vec2 quad_outline_vertices[] = {
        {-0.5f, -0.5f}, {0.5f, -0.5f},
        {0.5f, 0.5f}, {-0.5f, 0.5f}
    };
    static constexpr uint16_t quad_outline_indices[] = {
        0u, 1u, 1u, 2u, 2u, 3u, 3u, 0u
    };

    assets.audio_distance_scale(0.0f);
    assets.atlas(
        "game",
        "assets/atlas/atlas.aseprite",
        FILTER_NEAREST,
        ADDRESS_CLAMP);
    assets.mesh("quad", quad_vertices, quad_indices);
    assets.mesh("line", line_vertices, line_indices);
    assets.mesh(
        "quad_outline", quad_outline_vertices, quad_outline_indices);
    assets.font("karowi", "assets/fonts/karowi.ttf", 32u, 4u);
    assets.font("quantix", "assets/fonts/quantix.ttf", 32u, 4u);
    assets.font("sipper", "assets/fonts/sipper.ttf", 32u, 4u);
    assets.audio("laser", "assets/audio/fx1.wav", audio_fx);
};
