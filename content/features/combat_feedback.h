#include "presentation.hpp"
#include "render.hpp"
#include "audio.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>

struct hit_feedback_entry {
    uint32 serial = 0;
    uint64 tick_id = 0;
    float trigger_alpha = 0.0f;
    entity_id target = 0;
    vec2 position = {};
    bool target_destroyed = false;
    uint64 seed = 0;
};


$r e_present_shot {
    entity_id projectile;
    vec2 position;
    float rotation;
    uint64 seed;
};

$r e_present_hit {
    entity_id projectile;
    entity_id target;
    vec2 position;
    bool target_destroyed;
    uint64 seed;
};

$cr c_hit_feedback_history {
    uint32 count = 0;
    uint32 next_serial = 1;
    hit_feedback_entry entries[8] = {};
};

$r c_hit_feedback_cursor {
    uint32 consumed_serial = 0;
};

inline void append_hit_feedback(
        c_hit_feedback_history& history,
        uint64_t tick_id,
        float trigger_alpha,
        uint64_t target,
        vec2 position,
        bool target_destroyed,
        uint64_t seed) {
    hit_feedback_entry entry{
        history.next_serial++, tick_id,
        clamp(trigger_alpha, 0.0f, 1.0f), target,
        position, target_destroyed, seed};
    if (history.count < 8u) {
        history.entries[history.count++] = entry;
        return;
    }
    for (uint32_t index = 1u; index < 8u; ++index)
        history.entries[index - 1u] = history.entries[index];
    history.entries[7] = entry;
}

inline double hit_feedback_key(
        const hit_feedback_entry& entry) {
    return static_cast<double>(entry.tick_id) - 1.0
        + static_cast<double>(clamp(entry.trigger_alpha, 0.0f, 1.0f));
}

struct projectile_emitter_state {
    vec2 trail_position{};
    vec2 trail_velocity{};
    float trail_carry{};
    bool trail_initialized{};
};

inline particle_emitter_pool<projectile_emitter_state>
    g_projectile_emitters{};

inline auto* find_projectile_emitter(uint64_t stable_id, bool create) {
    return g_projectile_emitters.find(stable_id, g_particle_frame, create);
}

$compute projectile_spark_particle {
    state {
        vec2 velocity;
        float angular_velocity;
        float lifetime;
        float initial_lifetime;
        vec2 start_size;
        vec2 end_size;
        vec4 start_color;
        vec4 end_color;
    };
    instance c_colored_quad;
    logic {
        instance.position += state.velocity * dt;
        instance.rotation += state.angular_velocity * dt;
        state.lifetime -= dt;
        let progress = clamp(
            1.0 - state.lifetime / max(state.initial_lifetime, 0.0001),
            0.0, 1.0);
        instance.size = mix(state.start_size, state.end_size, progress);
        instance.color = mix(state.start_color, state.end_color, progress);
        if (state.lifetime <= 0.0) {
            alive = false;
        }
    };
};

$compute projectile_trail_particle {
    state {
        vec2 velocity;
        float angular_velocity;
        float lifetime;
        float initial_lifetime;
        vec2 start_size;
        vec2 end_size;
        vec4 start_color;
        vec4 end_color;
    };
    instance c_colored_quad;
    logic {
        instance.position += state.velocity * dt;
        instance.rotation += state.angular_velocity * dt;
        state.lifetime -= dt;
        let progress = clamp(
            1.0 - state.lifetime / max(state.initial_lifetime, 0.0001),
            0.0, 1.0);
        instance.size = mix(state.start_size, state.end_size, progress);
        instance.color = mix(state.start_color, state.end_color, progress);
        if (state.lifetime <= 0.0) {
            alive = false;
        }
    };
};


inline uint64_t particle_endpoint_seed(
        uint64_t stable_id,
        double sample_tick,
        motion_endpoint_kind endpoint_kind,
        uint64_t salt) {
    const uint64_t endpoint_key = static_cast<uint64_t>(
        max(sample_tick, 0.0) * 65536.0 + 0.5);
    return particle_hash(
        stable_id
        ^ particle_hash(endpoint_key)
        ^ (static_cast<uint64_t>(endpoint_kind) << 48u)
        ^ salt);
}

inline vec2 normalized_or(
        const vec2& value, const vec2& fallback) {
    const float length_squared =
        value.x * value.x + value.y * value.y;
    if (length_squared <= 0.00000001f)
        return fallback;
    const float inverse_length = 1.0f / std::sqrt(length_squared);
    return {
        value.x * inverse_length,
        value.y * inverse_length
    };
}

inline void spawn_projectile_burst(
        uint64_t stable_id,
        const c_presented_motion& presented,
        const vec2& motion_velocity,
        uint32_t count,
        float base_size,
        float lifetime,
        float legacy_speed,
        bool impact) {
    const vec2 source_direction = motion_velocity;
    const vec2 outward = normalized_or(source_direction, {1.0f, 0.0f});
    const bool directional = !impact
        && source_direction.x * source_direction.x
            + source_direction.y * source_direction.y > 0.00000001f;
    uint64_t random = particle_endpoint_seed(
        stable_id, presented.sample_tick,
        presented.endpoint_kind,
        impact ? 0x494d50414354ull : 0x535041574eull);
    for (uint32_t index = 0u; index < count; ++index) {
        const float angle = directional
            ? std::atan2(outward.y, outward.x)
                + particle_random_signed(random) * 1.1f
            : particle_random_01(random) * TPI;
        const vec2 direction{std::cos(angle), std::sin(angle)};
        const float speed = legacy_speed * 30.0f
            * (0.45f + particle_random_01(random) * 0.75f);
        const float size =
            base_size * (0.75f + particle_random_01(random) * 0.55f);
        const float duration =
            lifetime * (0.75f + particle_random_01(random) * 0.45f);
        const vec2 start_size{size, size};
        const vec4 start_color{0.75f, 1.0f, 1.0f, 0.95f};
        const float end_scale =
            0.12f + particle_random_01(random) * 0.18f;
        const vec2 end_size{size * end_scale, size * end_scale};
        const vec4 end_color{0.10f, 0.45f, 1.0f, 0.0f};
        particles::spawn<projectile_spark_particle>(
            {
                {direction.x * speed, direction.y * speed},
                particle_random_signed(random) * 5.0f,
                duration, duration, start_size, end_size,
                start_color, end_color
            },
            {
                {
                    presented.body.position.x + direction.x
                        * (0.01f + particle_random_01(random) * 0.015f),
                    presented.body.position.y + direction.y
                        * (0.01f + particle_random_01(random) * 0.015f)
                },
                start_size, angle, start_color, 0.18f
            });
    }
}

$c e_hit[2000](
    c_hit_feedback_history& history,
    target: optional read c_health health
) {
    append_hit_feedback(
        history, tick, event.toi, event.target, event.point,
        health && health->current <= 0,
        particle_hash(e.stable_id() ^ event.target ^ tick));
};

$r e_present_shot(c_inst) {
    play_spatial_audio(
        audio_fx, event.position.x, event.position.y,
        0.45f);
    c_presented_motion presented{};
    presented.body.position = event.position;
    presented.body.velocity = angle_to_vec(event.rotation);
    presented.sample_tick = 0.0;
    presented.endpoint_kind = motion_endpoint_kind::spawn;
    spawn_projectile_burst(
        event.projectile, presented, presented.body.velocity,
        10u, 0.11f, 0.16f, 0.09f, false);
};

$r e_present_hit(c_inst) {
    play_spatial_audio(
        audio_fx,
        event.position.x, event.position.y, 0.75f);
};

$r e_present_hit[10](c_inst) {
    c_presented_motion presented{};
    presented.body.position = event.position;
    presented.sample_tick = 0.0;
    presented.endpoint_kind = motion_endpoint_kind::hide;
    spawn_projectile_burst(
        event.projectile, presented, {},
        9u, 0.12f, 0.20f, 0.11f, true);
};

inline void emit_projectile_trail(
        projectile_emitter_state& emitter,
        const vec2& position,
        const vec2& velocity,
        uint64_t stable_id) {
    constexpr float spacing = 0.12f;
    if (!emitter.trail_initialized) {
        emitter.trail_position = position;
        emitter.trail_velocity = velocity;
        emitter.trail_initialized = true;
        return;
    }
    const vec2 delta{
        position.x - emitter.trail_position.x,
        position.y - emitter.trail_position.y
    };
    const float distance = std::sqrt(
        delta.x * delta.x + delta.y * delta.y);
    if (distance <= 0.000001f)
        return;
    const vec2 direction{delta.x / distance, delta.y / distance};
    float next_distance = spacing - emitter.trail_carry;
    uint32_t ordinal = 0u;
    while (next_distance <= distance + 0.000001f) {
        const vec2 point{
            emitter.trail_position.x + direction.x * next_distance,
            emitter.trail_position.y + direction.y * next_distance
        };
        uint64_t random = particle_hash(
            stable_id ^ particle_hash(g_particle_frame)
            ^ static_cast<uint64_t>(ordinal++));
        const float lifetime =
            0.10f + particle_random_01(random) * 0.05f;
        const float size =
            0.075f + particle_random_01(random) * 0.035f;
        const vec2 start_size{size, size};
        const vec4 start_color{0.35f, 0.95f, 1.0f, 0.75f};
        const vec2 end_size{size * 0.2f, size * 0.2f};
        const vec4 end_color{0.10f, 0.35f, 1.0f, 0.0f};
        const vec2 backwards =
            normalized_or({-velocity.x, -velocity.y},
                {-direction.x, -direction.y});
        particles::spawn<projectile_trail_particle>(
            {
                {backwards.x * 0.6f, backwards.y * 0.6f},
                particle_random_signed(random) * 3.0f,
                lifetime, lifetime, start_size, end_size,
                start_color, end_color
            },
            {point, start_size, 0.0f, start_color, 0.15f});
        next_distance += spacing;
    }
    emitter.trail_carry = std::fmod(
        emitter.trail_carry + distance, spacing);
    emitter.trail_position = position;
    if (velocity.x * velocity.x + velocity.y * velocity.y
            > 0.00000001f) {
        emitter.trail_velocity = velocity;
    }
}


$r e_update[-700](
    c_inst,
    const c_presented_motion& presented,
    const c_hit_feedback_history& hit_feedback,
    c_hit_feedback_cursor& hit_feedback_cursor
) {
        const uint64_t stable_id = e.stable_id();
        auto* emitter = find_projectile_emitter(stable_id, true);
        if (!emitter)
            continue;
        auto& state = emitter->state;
        if (!presented.valid)
            continue;
        for (uint32_t index = 0u;
                index < min(hit_feedback.count, 8u); ++index) {
            const auto& entry = hit_feedback.entries[index];
            if (!entry.serial
                    || entry.serial <= hit_feedback_cursor.consumed_serial
                    || hit_feedback_key(entry)
                        > presented.sample_tick + 0.000001) {
                continue;
            }
            e_present_hit hit{
                stable_id, entry.target, entry.position,
                entry.target_destroyed, entry.seed};
            dispatch(e, hit);
            hit_feedback_cursor.consumed_serial = entry.serial;
        }
        if (presented.endpoint_kind == motion_endpoint_kind::spawn) {
            e_present_shot shot{
                stable_id, presented.body.position,
                presented.body.rotation,
                particle_hash(stable_id ^ g_particle_frame)};
            dispatch(e, shot);
        }
        if (presented.visible) {
            emit_projectile_trail(
                state, presented.body.position,
                presented.body.velocity, stable_id);
        } else {
            state.trail_initialized = false;
            state.trail_carry = 0.0f;
        }
};

$r g_update[2000] {
    g_projectile_emitters.prune(g_particle_frame);
    g_particle_last_presentation_tick =
        g_particle_current_presentation_tick;
};
