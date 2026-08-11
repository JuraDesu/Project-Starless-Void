#pragma once

#include "presentation.hpp"

#include <algorithm>
#include <array>
#include <cstdint>

inline uint64_t g_particle_state_epoch{};

template <typename State, uint32_t Capacity = 512>
struct particle_emitter_pool {
    struct entry {
        uint64_t stable_id{};
        uint64_t seen_frame{};
        State state{};
    };
    std::array<entry, Capacity> values{};
    uint32_t count{};
    uint64_t epoch{};
    void reset() { count = 0; epoch = g_particle_state_epoch; }
    entry* find(uint64_t stable_id, uint64_t frame, bool create = true) {
        if (epoch != g_particle_state_epoch) reset();
        for (uint32_t index = 0; index < count; ++index)
            if (values[index].stable_id == stable_id) {
                values[index].seen_frame = frame;
                return &values[index];
            }
        if (!create || count >= Capacity) return nullptr;
        values[count] = entry{stable_id, frame, {}};
        return &values[count++];
    }
    void prune(uint64_t frame, uint64_t age = 2) {
        for (uint32_t index = 0; index < count;) {
            if (values[index].seen_frame + age >= frame) {
                ++index;
                continue;
            }
            values[index] = values[--count];
        }
    }
};

inline uint64_t g_particle_frame{};
inline double g_particle_last_presentation_tick{};
inline double g_particle_current_presentation_tick{};
inline float g_particle_dt_seconds{};
inline float g_particle_tick_seconds{};
inline bool g_particle_timing_initialized{};

inline void reset_particle_state() {
    ++g_particle_state_epoch;
    g_particle_frame = 0u;
    g_particle_last_presentation_tick = 0.0;
    g_particle_current_presentation_tick = 0.0;
    g_particle_dt_seconds = 0.0f;
    g_particle_tick_seconds = 0.0f;
    g_particle_timing_initialized = false;
}

inline uint64_t particle_hash(uint64_t value) {
    value += 0x9e3779b97f4a7c15ull;
    value = (value ^ (value >> 30u)) * 0xbf58476d1ce4e5b9ull;
    value = (value ^ (value >> 27u)) * 0x94d049bb133111ebull;
    return value ^ (value >> 31u);
}

inline float particle_random_01(uint64_t& state) {
    state = particle_hash(state);
    return static_cast<float>(state >> 40u) * (1.0f / 16777216.0f);
}

inline float particle_random_signed(uint64_t& state) {
    return particle_random_01(state) * 2.0f - 1.0f;
}

inline float scale_particle_spawn_budget(float raw_budget) {
    return raw_budget;
}

$r g_update[-1000] {
    const auto timing = presentation_timing();
    if (!timing.valid) {
        reset_particle_state();
        continue;
    }
    if (!g_particle_timing_initialized) {
        g_particle_last_presentation_tick = timing.presentation_tick;
        g_particle_timing_initialized = true;
    } else if (timing.presentation_tick + 0.000001
            < g_particle_last_presentation_tick) {
        reset_particle_state();
        g_particle_last_presentation_tick = timing.presentation_tick;
        g_particle_timing_initialized = true;
    }
    const double previous_tick = g_particle_last_presentation_tick;
    const double current_tick = timing.presentation_tick;
    g_particle_dt_seconds = clamp(
        static_cast<float>((current_tick - previous_tick)
            * timing.tick_seconds),
        0.0f, 4.0f * timing.tick_seconds);
    g_particle_tick_seconds = timing.tick_seconds;
    ++g_particle_frame;
    g_particle_current_presentation_tick = current_tick;
};
