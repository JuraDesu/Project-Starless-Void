#pragma once

#include "content_api.h"

// Content-wide default for spatial audio.  A value of zero makes playback
// non-spatial: the configured base gain is used equally in both channels.
inline float content_audio_distance_scale = 12.0f;
inline constexpr float AUDIO_USE_DEFAULT_DISTANCE_SCALE = -1.0f;

inline bool play_spatial_audio(
        const EngineContentCallContext& context,
        EngineAudioId audio,
        float x,
        float y,
        float gain = 1.0f,
        float distance_scale = AUDIO_USE_DEFAULT_DISTANCE_SCALE,
        float pan_range = 8.0f) {
    if (distance_scale == AUDIO_USE_DEFAULT_DISTANCE_SCALE)
        distance_scale = content_audio_distance_scale;
    return context.engine && context.engine->play_spatial_audio
        && context.engine->play_spatial_audio(
            context.engine_context, audio, x, y, gain,
            distance_scale, pan_range) != 0;
}
