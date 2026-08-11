#pragma once

#include "breakpoints.hpp"
#include "callback.hpp"
#include "content_api.h"
#include "content_types.h"

#include <cmath>
#include <cstdint>
#include <limits>
#include <type_traits>

using audio_sample = uint64_t;
inline constexpr uint32_t AUDIO_SAMPLE_RATE = 48000u;

inline constexpr audio_sample from_seconds(double seconds) {
    if (!(seconds > 0.0)) return 0u;
    const double scaled = seconds * static_cast<double>(AUDIO_SAMPLE_RATE);
    const double maximum = static_cast<double>(
        std::numeric_limits<audio_sample>::max());
    if (!(scaled < maximum)) return std::numeric_limits<audio_sample>::max();
    return static_cast<audio_sample>(scaled + 0.5);
}

inline constexpr double to_seconds(audio_sample samples) {
    return static_cast<double>(samples)
        / static_cast<double>(AUDIO_SAMPLE_RATE);
}

enum class audio_playback : uint32_t {
    stopped = AUDIO_PLAYBACK_STOPPED,
    playing = AUDIO_PLAYBACK_PLAYING,
    paused = AUDIO_PLAYBACK_PAUSED,
};

struct c_audio_source {
    EngineAudioId clip{};
    uint32_t playback{AUDIO_PLAYBACK_STOPPED};
    uint32_t looping{};
    uint32_t spatial{};
    float gain{1.0f};
    float distance_scale{-1.0f};
    float pan_range{8.0f};
    float position_x{};
    float position_y{};
    audio_sample requested_sample{};
    audio_sample observed_sample{};
    uint64_t voice{};
    uint32_t observed_playing{};
    uint32_t command_count{};
    uint32_t command_sequence{};
    EngineAudioSourceCommand commands[AUDIO_SOURCE_MAX_COMMANDS]{};

    c_audio_source() = default;
    explicit c_audio_source(EngineAudioId value,
            audio_playback state = audio_playback::stopped,
            bool repeat = false,
            float initial_gain = 1.0f)
        : clip(value), playback(static_cast<uint32_t>(state)),
          looping(repeat ? 1u : 0u),
          gain(std::isfinite(initial_gain) && initial_gain >= 0.0f
              ? initial_gain : 1.0f) {}

    bool valid_context() const {
        const auto* context = active_callback_context();
        return context && context->world == WORLD_RENDER;
    }

    bool append_command(uint32_t kind, audio_sample sample = 0u) {
        if (!valid_context() || command_count >= AUDIO_SOURCE_MAX_COMMANDS)
            return false;
        auto& command = commands[command_count++];
        command = {};
        command.kind = kind;
        command.sequence = command_sequence++;
        command.sample = sample;
        if (const auto* breakpoint = active_breakpoint()) {
            command.tick = breakpoint->tick;
            command.alpha = breakpoint->alpha;
            command.sequence = breakpoint->sequence;
        } else {
            command.tick = std::numeric_limits<uint64_t>::max();
        }
        return true;
    }

    bool play() {
        if (!valid_context()) return false;
        if (!append_command(AUDIO_COMMAND_PLAY, requested_sample)) return false;
        playback = AUDIO_PLAYBACK_PLAYING;
        return true;
    }

    bool pause() {
        if (!valid_context()) return false;
        if (!append_command(AUDIO_COMMAND_PAUSE, observed_sample)) return false;
        playback = AUDIO_PLAYBACK_PAUSED;
        return true;
    }

    bool stop() {
        if (!valid_context()) return false;
        if (!append_command(AUDIO_COMMAND_STOP, 0u)) return false;
        requested_sample = 0u;
        playback = AUDIO_PLAYBACK_STOPPED;
        return true;
    }

    bool seek_samples(audio_sample sample) {
        if (!valid_context()) return false;
        if (!append_command(AUDIO_COMMAND_SEEK, sample)) return false;
        requested_sample = sample;
        return true;
    }

    bool set_looping(bool value) {
        if (!valid_context()) return false;
        looping = value ? 1u : 0u;
        return true;
    }

    bool set_gain(float value) {
        if (!valid_context() || !std::isfinite(value) || value < 0.0f)
            return false;
        gain = value;
        return true;
    }

    bool set_spatial(bool value) {
        if (!valid_context()) return false;
        spatial = value ? 1u : 0u;
        return true;
    }

    bool set_position(vec2 value) {
        if (!valid_context() || !std::isfinite(value.x)
                || !std::isfinite(value.y)) return false;
        position_x = value.x;
        position_y = value.y;
        return true;
    }

    bool set_distance_scale(float value) {
        if (!valid_context() || !std::isfinite(value) || value < 0.0f)
            return false;
        distance_scale = value;
        return true;
    }

    bool set_pan_range(float value) {
        if (!valid_context() || !std::isfinite(value) || value < 0.0f)
            return false;
        pan_range = value;
        return true;
    }

    audio_sample sample_position() const { return observed_sample; }
    double position_seconds() const { return to_seconds(observed_sample); }
    bool is_playing() const { return observed_playing != 0u; }
};

static_assert(sizeof(c_audio_source) == sizeof(EngineAudioSource));
static_assert(std::is_standard_layout_v<c_audio_source>);
static_assert(std::is_trivially_copyable_v<c_audio_source>);
