#include "ecs.hpp"

#include <algorithm>
#include <cmath>

struct motion_breakpoint {
    uint64 tick_id = 0;
    float trigger_alpha = 0.0f;
    uint32 kind = 0;
    vec2 breakpoint_pos = {};
    float breakpoint_rot = 0.0f;
    vec2 pre_velocity = {};
    vec2 post_velocity = {};
    float post_rotation = 0.0f;
};

enum class motion_endpoint_kind : uint32 {
    none = 0,
    spawn = 1,
    hide = 2,
};

$cr c_motion_breakpoint_history {
    uint32 count = 0;
    motion_breakpoint breakpoints[8] = {};
};

$c c_pending_destruction {
    uint64 tick_id = 0;
    float cutoff_alpha = 1.0f;
    bool immediate = false;
};

$c c_motion_breakpoint_anchor {
    vec2 position = {};
    float rotation = 0.0f;
};

$r c_motion_lifecycle_state {
    bool initialized = false;
    bool has_consumed_endpoint = false;
    uint64 consumed_tick_id = 0;
    float consumed_trigger_alpha = 0.0f;
    uint32 consumed_kind = 0;
};


inline constexpr uint32_t motion_breakpoint_none = 0u;
inline constexpr uint32_t motion_breakpoint_spawn = 1u;
inline constexpr uint32_t motion_breakpoint_hide = 2u;
inline constexpr uint32_t motion_breakpoint_bounce = 3u;
inline constexpr uint32_t motion_breakpoint_segment_end = 4u;
inline constexpr uint32_t motion_breakpoint_history_capacity = 8u;

inline motion_breakpoint make_motion_breakpoint(
        uint32_t kind,
        uint64_t tick_id,
        float trigger_alpha,
        vec2 position,
        float rotation,
        vec2 pre_velocity,
        vec2 post_velocity,
        float post_rotation) {
    return {
        tick_id,
        clamp(trigger_alpha, 0.0f, 1.0f),
        kind,
        position,
        rotation,
        pre_velocity,
        post_velocity,
        post_rotation
    };
}

inline double motion_breakpoint_key(const motion_breakpoint& breakpoint) {
    return static_cast<double>(breakpoint.tick_id)
        - 1.0
        + static_cast<double>(
            clamp(breakpoint.trigger_alpha, 0.0f, 1.0f));
}

inline uint32_t motion_breakpoint_count(
        const c_motion_breakpoint_history& history) {
    return min(
        history.count, motion_breakpoint_history_capacity);
}

inline bool motion_breakpoint_same_key(
        const motion_breakpoint& left,
        const motion_breakpoint& right) {
    return left.tick_id == right.tick_id
        && left.kind == right.kind
        && std::abs(left.trigger_alpha - right.trigger_alpha)
            <= 0.0001f;
}

inline void motion_breakpoint_history_sort(
        c_motion_breakpoint_history& history) {
    const uint32_t count = motion_breakpoint_count(history);
    for (uint32_t index = 1u; index < count; ++index) {
        const motion_breakpoint value = history.breakpoints[index];
        const double value_key = motion_breakpoint_key(value);
        uint32_t target = index;
        while (target > 0u) {
            const motion_breakpoint previous =
                history.breakpoints[target - 1u];
            const double previous_key =
                motion_breakpoint_key(previous);
            if (previous_key < value_key
                    || (std::abs(previous_key - value_key) <= 0.000001
                        && (previous.kind < value.kind
                            || (previous.kind == value.kind
                                && (previous.tick_id < value.tick_id
                                    || (previous.tick_id == value.tick_id
                                        && previous.trigger_alpha
                                            <= value.trigger_alpha)))))) {
                break;
            }
            history.breakpoints[target] = previous;
            --target;
        }
        history.breakpoints[target] = value;
    }
}

inline void motion_breakpoint_history_push(
        c_motion_breakpoint_history& history,
        const motion_breakpoint& breakpoint) {
    if (breakpoint.kind == motion_breakpoint_none) return;
    uint32_t count = motion_breakpoint_count(history);
    for (uint32_t index = 0u; index < count; ++index) {
        if (motion_breakpoint_same_key(
                history.breakpoints[index], breakpoint)) {
            history.breakpoints[index] = breakpoint;
            motion_breakpoint_history_sort(history);
            return;
        }
    }
    if (count < motion_breakpoint_history_capacity) {
        history.breakpoints[count] = breakpoint;
        history.count = count + 1u;
    } else {
        for (uint32_t index = 1u; index < count; ++index)
            history.breakpoints[index - 1u] =
                history.breakpoints[index];
        history.breakpoints[count - 1u] = breakpoint;
        history.count = count;
    }
    motion_breakpoint_history_sort(history);
}

inline void append_entity_motion_breakpoint(
        entity target,
        const motion_breakpoint& breakpoint) {
    if (!target || breakpoint.kind == motion_breakpoint_none) return;
    auto* history =
        target.try_get_mut<c_motion_breakpoint_history>();
    if (history) {
        motion_breakpoint_history_push(*history, breakpoint);
        return;
    }
    c_motion_breakpoint_history created{};
    motion_breakpoint_history_push(created, breakpoint);
    target.set<c_motion_breakpoint_history>(created);
}

inline void append_spawn_motion_breakpoint(
        entity target,
        uint64_t tick_id,
        const c_rigid_body& body) {
    append_entity_motion_breakpoint(
        target,
        make_motion_breakpoint(
            motion_breakpoint_spawn,
            tick_id,
            0.0f,
            body.position,
            body.rotation,
            body.velocity,
            body.velocity,
            body.rotation));
}

inline void begin_motion_despawn(
        entity target,
        uint64_t tick_id,
        float trigger_alpha,
        const vec2& segment_end,
        const vec2& impact_position,
        float rotation,
        const vec2& velocity) {
    if (!target || target.has<c_pending_destruction>()) return;
    append_entity_motion_breakpoint(
        target,
        make_motion_breakpoint(
            motion_breakpoint_segment_end,
            tick_id,
            0.0f,
            segment_end,
            rotation,
            velocity,
            velocity,
            rotation));
    append_entity_motion_breakpoint(
        target,
        make_motion_breakpoint(
            motion_breakpoint_hide,
            tick_id,
            trigger_alpha,
            impact_position,
            rotation,
            velocity,
            {},
            rotation));
    if (auto* body = target.try_get_mut<c_rigid_body>()) {
        body->position = impact_position;
        body->rotation = rotation;
        body->velocity = {};
        body->angular_velocity = 0.0f;
    }
    target.set<c_motion_breakpoint_anchor>({
        impact_position, rotation
    });
    target.set<c_pending_destruction>({
        tick_id,
        clamp(trigger_alpha, 0.0f, 1.0f),
        false
    });
}


$c e_update[1000](const c_pending_destruction& pending) {
    if (tick >= pending.tick_id
            + motion_breakpoint_history_capacity) {
        e.destroy();
    }
};

// Canonical presented-motion capture and resolution.
$r e_set(
    const c_rigid_body& body,
    c_rigidbody_sample_history& history
) {
    const auto timing = presentation_timing();
    if (timing.latest_simulation_tick)
        rigidbody_history_push(
            history, timing.latest_simulation_tick, body);
};

$r e_set(
    const c_motion_breakpoint_history& breakpoints,
    c_rigidbody_sample_history& history
) {
    seed_rigidbody_history_from_spawn_breakpoints(
        history, &breakpoints);
};

$r e_update[-900](
    const c_rigid_body& body,
    c_rigidbody_sample_history& history,
    c_render_motion_presentation& presentation,
    c_motion_lifecycle_state& lifecycle,
    c_presented_motion& presented,
    optional read c_motion_breakpoint_history breakpoints
) {
    const auto timing = presentation_timing();
    if (timing.valid) {
        rigidbody_history_push(
            history, timing.latest_simulation_tick, body);
        seed_rigidbody_history_from_spawn_breakpoints(
            history, breakpoints);
        presentation = prepare_motion_presentation(
            history, timing.segment_tick, body, breakpoints);
        const auto raw = resolve_motion_presentation(
            presentation, breakpoints, timing.presentation_tick);
        presented = resolve_canonical_presented_motion(
            presentation, breakpoints, timing.presentation_tick,
            raw, lifecycle);
    } else {
        presented.valid = false;
        presented.visible = false;
        presented.endpoint_kind = motion_endpoint_kind::none;
    }
};
