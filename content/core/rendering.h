#include "camera.hpp"
#include "input.hpp"
#include "presentation.hpp"
#include "render.hpp"
#include "texture.hpp"

#include <algorithm>
#include <cmath>


inline bool g_debug_overlay_enabled = false;

$r c_textured_sprite {
    vec2 position;
    vec2 size;
    float rotation;
    vec4 uv_rect;
    uint32 atlas_layer;
    float depth;
    entity_id stable_id = 0;

    shader {
        mesh quad;
        texture game;
        blend alpha;
        logic {
            bridge {
                uv: vec2f,
            };

            vertex {
                let c = cos(rotation);
                let s = sin(rotation);
                let scaled = local_position * size;
                let rotated = vec2f(
                    scaled.x * c - scaled.y * s,
                    scaled.x * s + scaled.y * c
                );
                out.position = projection * vec4f(
                    position + rotated, depth, 1.0);
                out.uv = uv_rect.xy + local_uv * uv_rect.zw;
            }

            fragment {
                let sampled = sample_texture(in.uv);
                if (sampled.a < 0.01) { discard; }
                out.color = sampled;
            }
        };
    };
};


template <typename Texture>
inline c_textured_sprite make_sprite(
        vec2 position = {}, float pixels_per_world_unit = 18.0f,
        float rotation = 0.0f, float depth = 0.0f,
        entity_id stable_id = 0) {
    const auto& image = texture<Texture>();
    return {
        position, texture_world_size(image, pixels_per_world_unit),
        rotation, texture_uv(image), image.layer, depth, stable_id
    };
}


$r c_colored_quad {
    vec2 position;
    vec2 size;
    float rotation;
    vec4 color;
    float depth;

    shader {
        mesh quad;
        blend alpha;
        logic {
            bridge {
                color: vec4f,
            };

            vertex {
                let c = cos(rotation);
                let s = sin(rotation);
                let scaled = local_position * size;
                let rotated = vec2f(
                    scaled.x * c - scaled.y * s,
                    scaled.x * s + scaled.y * c
                );
                out.position = projection * vec4f(
                    position + rotated, depth, 1.0);
                out.color = color;
            }

            fragment {
                out.color = in.color;
            }
        };
    };
};

$r c_debug_line {
    vec2 start;
    vec2 end;
    vec4 color;
    float depth;

    shader {
        topology lines;
        mesh line;
        blend alpha;
        logic {
            bridge {
                color: vec4f,
            };

            vertex {
                let world_position = mix(
                    start, end, local_position.x);
                out.position = projection * vec4f(
                    world_position, depth, 1.0);
                out.color = color;
            }

            fragment {
                out.color = in.color;
            }
        };
    };
};

$r c_debug_wireframe {
    vec2 position;
    vec2 size;
    float rotation;
    vec4 color;
    float depth;

    shader {
        topology lines;
        mesh quad_outline;
        blend alpha;
        logic {
            bridge {
                color: vec4f,
            };

            vertex {
                let c = cos(rotation);
                let s = sin(rotation);
                let scaled = local_position * size;
                let rotated = vec2f(
                    scaled.x * c - scaled.y * s,
                    scaled.x * s + scaled.y * c
                );
                out.position = projection * vec4f(
                    position + rotated, depth, 1.0);
                out.color = color;
            }

            fragment {
                out.color = in.color;
            }
        };
    };
};

$r c_rigidbody_sample_history {
    uint32 count = 0;
    uint64 ticks[5] = {};
    c_rigid_body values[5] = {};
};

$r c_render_motion_presentation {
    uint64 segment_tick = 0;
    bool initialized = false;
    c_rigid_body current = {};
    vec2 position_offset = {};
    float rotation_offset = 0.0f;
    vec2 velocity_offset = {};
    float angular_velocity_offset = 0.0f;
    bool has_previous = false;
    c_rigid_body previous = {};
    bool has_next = false;
    c_rigid_body next = {};
};

$r c_presented_motion {
    c_rigid_body body = {};
    double sample_tick = 0.0;
    motion_endpoint_kind endpoint_kind = none;
    bool valid = false;
    bool visible = false;
};

inline bool camera_follow(entity value) {
    return camera_follow_presented<c_presented_motion>(
        value, component_traits<c_presented_motion>::id,
        static_cast<uint32_t>(offsetof(c_presented_motion, body)
            + offsetof(c_rigid_body, position)),
        static_cast<uint32_t>(offsetof(c_presented_motion, valid)),
        static_cast<uint32_t>(offsetof(c_presented_motion, visible)));
}


inline constexpr uint32_t rigidbody_history_capacity = 5u;

inline uint32_t rigidbody_history_count(
        const c_rigidbody_sample_history& history) {
    return min(history.count, rigidbody_history_capacity);
}

inline void rigidbody_history_sort(c_rigidbody_sample_history& history) {
    const uint32_t count = rigidbody_history_count(history);
    for (uint32_t index = 1u; index < count; ++index) {
        const uint64_t tick = history.ticks[index];
        const c_rigid_body value = history.values[index];
        uint32_t target = index;
        while (target > 0u && tick < history.ticks[target - 1u]) {
            history.ticks[target] = history.ticks[target - 1u];
            history.values[target] = history.values[target - 1u];
            --target;
        }
        history.ticks[target] = tick;
        history.values[target] = value;
    }
}

inline void rigidbody_history_push(
        c_rigidbody_sample_history& history,
        uint64_t tick,
        const c_rigid_body& value) {
    uint32_t count = rigidbody_history_count(history);
    for (uint32_t index = 0u; index < count; ++index) {
        if (history.ticks[index] == tick) {
            history.values[index] = value;
            rigidbody_history_sort(history);
            return;
        }
    }
    if (count < rigidbody_history_capacity) {
        history.ticks[count] = tick;
        history.values[count] = value;
        history.count = count + 1u;
    } else {
        for (uint32_t index = 1u; index < count; ++index) {
            history.ticks[index - 1u] = history.ticks[index];
            history.values[index - 1u] = history.values[index];
        }
        history.ticks[count - 1u] = tick;
        history.values[count - 1u] = value;
        history.count = count;
    }
    rigidbody_history_sort(history);
}

inline bool rigidbody_history_find_exact(
        const c_rigidbody_sample_history& history,
        uint64_t tick,
        c_rigid_body& result) {
    const uint32_t count = rigidbody_history_count(history);
    for (uint32_t index = 0u; index < count; ++index) {
        if (history.ticks[index] == tick) {
            result = history.values[index];
            return true;
        }
    }
    return false;
}

inline bool rigidbody_history_find_hold(
        const c_rigidbody_sample_history& history,
        uint64_t tick,
        c_rigid_body& result) {
    const uint32_t count = rigidbody_history_count(history);
    if (!count) return false;
    bool found = false;
    uint64_t best_tick = 0u;
    for (uint32_t index = 0u; index < count; ++index) {
        if (history.ticks[index] <= tick
                && (!found || history.ticks[index] > best_tick)) {
            found = true;
            best_tick = history.ticks[index];
            result = history.values[index];
        }
    }
    if (!found) result = history.values[0];
    return true;
}

inline float unwrap_angle_near(float angle, float reference) {
    return reference + angle_difference(reference, angle);
}

inline float normalize_angle_signed(float angle) {
    return unwrap_angle_near(angle, 0.0f);
}

inline c_rigid_body lerp_rigidbody(
        const c_rigid_body& start,
        const c_rigid_body& end,
        float alpha) {
    alpha = clamp(alpha, 0.0f, 1.0f);
    const float target_rotation =
        unwrap_angle_near(end.rotation, start.rotation);
    return {
        {
            start.position.x
                + (end.position.x - start.position.x) * alpha,
            start.position.y
                + (end.position.y - start.position.y) * alpha
        },
        normalize_angle_signed(start.rotation
            + (target_rotation - start.rotation) * alpha),
        {
            start.velocity.x
                + (end.velocity.x - start.velocity.x) * alpha,
            start.velocity.y
                + (end.velocity.y - start.velocity.y) * alpha
        },
        start.angular_velocity
            + (end.angular_velocity - start.angular_velocity) * alpha
    };
}

inline float catmull_rom_knot(
        const vec2& start,
        const vec2& end,
        float previous) {
    const float dx = end.x - start.x;
    const float dy = end.y - start.y;
    return previous + max(
        std::sqrt(dx * dx + dy * dy), 0.000001f);
}

inline vec2 catmull_rom_lerp(
        const vec2& start,
        const vec2& end,
        float start_t,
        float end_t,
        float t) {
    const float denominator = end_t - start_t;
    if (std::abs(denominator) <= 0.000001f) return end;
    const float alpha = (t - start_t) / denominator;
    return {
        start.x + (end.x - start.x) * alpha,
        start.y + (end.y - start.y) * alpha
    };
}

inline vec2 catmull_rom(
        const vec2& a,
        const vec2& b,
        const vec2& c,
        const vec2& d,
        float alpha) {
    alpha = clamp(alpha, 0.0f, 1.0f);
    const float ta = 0.0f;
    const float tb = catmull_rom_knot(a, b, ta);
    const float tc = catmull_rom_knot(b, c, tb);
    const float td = catmull_rom_knot(c, d, tc);
    const float t = tb + (tc - tb) * alpha;
    const vec2 ab = catmull_rom_lerp(a, b, ta, tb, t);
    const vec2 bc = catmull_rom_lerp(b, c, tb, tc, t);
    const vec2 cd = catmull_rom_lerp(c, d, tc, td, t);
    const vec2 abc = catmull_rom_lerp(ab, bc, ta, tc, t);
    const vec2 bcd = catmull_rom_lerp(bc, cd, tb, td, t);
    return catmull_rom_lerp(abc, bcd, tb, tc, t);
}

struct motion_presentation_anchor {
    double key{};
    c_rigid_body body{};
    uint32_t kind{};
};

inline c_rigid_body presentation_end(
        const c_render_motion_presentation& presentation) {
    c_rigid_body result = presentation.current;
    result.position.x += presentation.position_offset.x;
    result.position.y += presentation.position_offset.y;
    result.rotation += presentation.rotation_offset;
    result.velocity.x += presentation.velocity_offset.x;
    result.velocity.y += presentation.velocity_offset.y;
    result.angular_velocity += presentation.angular_velocity_offset;
    return result;
}

inline c_rigid_body resolve_motion_presentation(
        const c_render_motion_presentation& presentation,
        double presentation_tick) {
    const float alpha = clamp(static_cast<float>(
        presentation_tick
        - static_cast<double>(presentation.segment_tick)), 0.0f, 1.0f);
    const c_rigid_body end = presentation_end(presentation);
    c_rigid_body result =
        lerp_rigidbody(presentation.current, end, alpha);
    c_rigid_body previous_fallback = presentation.current;
    c_rigid_body next_fallback = end;
    const c_rigid_body* previous =
        presentation.has_previous ? &presentation.previous : nullptr;
    const c_rigid_body* next =
        presentation.has_next ? &presentation.next : nullptr;
    if (!previous) {
        previous_fallback.position = {
            presentation.current.position.x * 2.0f - end.position.x,
            presentation.current.position.y * 2.0f - end.position.y
        };
        previous = &previous_fallback;
    }
    if (!next) {
        next_fallback.position = {
            end.position.x * 2.0f - presentation.current.position.x,
            end.position.y * 2.0f - presentation.current.position.y
        };
        next = &next_fallback;
    }
    result.position = catmull_rom(
        previous->position,
        presentation.current.position,
        end.position,
        next->position,
        alpha);
    return result;
}

inline c_rigid_body rigidbody_from_motion_breakpoint(
        const motion_breakpoint& breakpoint,
        bool after_breakpoint) {
    return {
        breakpoint.breakpoint_pos,
        after_breakpoint
            ? breakpoint.post_rotation
            : breakpoint.breakpoint_rot,
        after_breakpoint
            ? breakpoint.post_velocity
            : breakpoint.pre_velocity,
        0.0f
    };
}

inline void seed_rigidbody_history_from_spawn_breakpoints(
        c_rigidbody_sample_history& history,
        const c_motion_breakpoint_history* breakpoints) {
    if (!breakpoints) return;
    const uint32_t count = motion_breakpoint_count(*breakpoints);
    for (uint32_t index = 0u; index < count; ++index) {
        const motion_breakpoint& breakpoint =
            breakpoints->breakpoints[index];
        if (breakpoint.kind != motion_breakpoint_spawn)
            continue;
        const uint64_t sample_tick =
            breakpoint.tick_id > 0u ? breakpoint.tick_id - 1u : 0u;
        c_rigid_body existing{};
        if (rigidbody_history_find_exact(
                history, sample_tick, existing)) {
            continue;
        }
        rigidbody_history_push(
            history,
            sample_tick,
            rigidbody_from_motion_breakpoint(breakpoint, true));
    }
}

inline bool apply_segment_end_breakpoint(
        const c_motion_breakpoint_history* breakpoints,
        uint64_t segment_tick,
        c_rigid_body& end) {
    if (!breakpoints) return false;
    bool applied = false;
    const uint32_t count = motion_breakpoint_count(*breakpoints);
    for (uint32_t index = 0u; index < count; ++index) {
        const motion_breakpoint& breakpoint =
            breakpoints->breakpoints[index];
        if (breakpoint.kind != motion_breakpoint_segment_end
                || breakpoint.tick_id != segment_tick + 1u) {
            continue;
        }
        end = rigidbody_from_motion_breakpoint(breakpoint, true);
        applied = true;
    }
    return applied;
}

inline c_render_motion_presentation prepare_motion_presentation(
        const c_rigidbody_sample_history& history,
        uint64_t segment_tick,
        const c_rigid_body& fallback,
        const c_motion_breakpoint_history* breakpoints = nullptr) {
    c_render_motion_presentation result{};
    result.initialized = true;
    result.segment_tick = segment_tick;
    const uint64_t end_tick = segment_tick + 1u;
    c_rigid_body start = fallback;
    c_rigid_body end = fallback;
    if (!rigidbody_history_find_exact(history, end_tick, end))
        rigidbody_history_find_hold(history, end_tick, end);
    if (!rigidbody_history_find_exact(
            history, result.segment_tick, start))
        rigidbody_history_find_hold(history, result.segment_tick, start);
    apply_segment_end_breakpoint(
        breakpoints, result.segment_tick, end);
    result.current = start;
    end.rotation = unwrap_angle_near(end.rotation, start.rotation);
    result.position_offset = {
        end.position.x - start.position.x,
        end.position.y - start.position.y
    };
    result.rotation_offset = end.rotation - start.rotation;
    result.velocity_offset = {
        end.velocity.x - start.velocity.x,
        end.velocity.y - start.velocity.y
    };
    result.angular_velocity_offset =
        end.angular_velocity - start.angular_velocity;
    if (result.segment_tick > 0u) {
        result.has_previous = rigidbody_history_find_exact(
            history, result.segment_tick - 1u, result.previous);
    }
    result.has_next = rigidbody_history_find_exact(
        history, end_tick + 1u, result.next);
    return result;
}

struct motion_presentation_result {
    c_rigid_body body{};
    bool visible{true};
};

struct debug_motion_anchor_segment {
    static constexpr uint32_t capacity =
        motion_breakpoint_history_capacity + 2u;
    uint32_t count{};
    vec2 points[capacity]{};
};

inline bool debug_motion_anchors_for_segment(
        const c_render_motion_presentation& presentation,
        const c_motion_breakpoint_history* breakpoints,
        double presentation_tick,
        debug_motion_anchor_segment& result) {
    result = {};
    if (!presentation.initialized)
        return false;
    const double tick_start =
        static_cast<double>(presentation.segment_tick);
    const double tick_end = tick_start + 1.0;
    motion_presentation_anchor anchors[
        debug_motion_anchor_segment::capacity]{};
    uint32_t anchor_count = 0u;
    anchors[anchor_count++] = {
        tick_start, presentation.current, motion_breakpoint_none
    };
    if (breakpoints) {
        const uint32_t count =
            motion_breakpoint_count(*breakpoints);
        for (uint32_t index = 0u;
                index < count
                    && anchor_count + 1u
                        < debug_motion_anchor_segment::capacity;
                ++index) {
            const motion_breakpoint& breakpoint =
                breakpoints->breakpoints[index];
            if (breakpoint.kind == motion_breakpoint_none
                    || breakpoint.kind
                        == motion_breakpoint_segment_end) {
                continue;
            }
            const double key = motion_breakpoint_key(breakpoint);
            if (key < tick_start - 0.000001
                    || key > tick_end + 0.000001) {
                continue;
            }
            anchors[anchor_count++] = {
                key,
                rigidbody_from_motion_breakpoint(
                    breakpoint, presentation_tick >= key),
                breakpoint.kind
            };
        }
    }
    anchors[anchor_count++] = {
        tick_end, presentation_end(presentation),
        motion_breakpoint_none
    };
    for (uint32_t index = 1u; index < anchor_count; ++index) {
        const motion_presentation_anchor value = anchors[index];
        uint32_t target = index;
        while (target > 0u
                && (anchors[target - 1u].key > value.key
                    || (std::abs(
                            anchors[target - 1u].key - value.key)
                            <= 0.000001
                        && anchors[target - 1u].kind > value.kind))) {
            anchors[target] = anchors[target - 1u];
            --target;
        }
        anchors[target] = value;
    }
    const motion_presentation_anchor* start_anchor = nullptr;
    const motion_presentation_anchor* end_anchor = nullptr;
    for (uint32_t index = 0u; index < anchor_count; ++index) {
        const motion_presentation_anchor& anchor = anchors[index];
        if (anchor.key <= tick_start + 0.000001)
            start_anchor = &anchor;
        if (anchor.key <= tick_end + 0.000001)
            end_anchor = &anchor;
    }
    if (!start_anchor)
        start_anchor = &anchors[0];
    if (!end_anchor)
        end_anchor = &anchors[anchor_count - 1u];
    result.points[result.count++] =
        start_anchor->body.position;
    for (uint32_t index = 0u;
            index < anchor_count
                && result.count
                    < debug_motion_anchor_segment::capacity;
            ++index) {
        const motion_presentation_anchor& anchor = anchors[index];
        if (anchor.key <= tick_start + 0.000001
                || anchor.key > tick_end + 0.000001) {
            continue;
        }
        result.points[result.count++] = anchor.body.position;
    }
    const float dx =
        end_anchor->body.position.x - result.points[0].x;
    const float dy =
        end_anchor->body.position.y - result.points[0].y;
    if (result.count == 1u
            && dx * dx + dy * dy > 0.00000001f
            && result.count
                < debug_motion_anchor_segment::capacity) {
        result.points[result.count++] =
            end_anchor->body.position;
    }
    return result.count > 0u;
}

inline c_rigid_body interpolate_motion_anchors(
        const motion_presentation_anchor& lower,
        const motion_presentation_anchor& upper,
        const c_rigid_body* previous,
        const c_rigid_body* next,
        double presentation_tick) {
    const double segment_duration = upper.key - lower.key;
    if (std::abs(segment_duration) <= 0.000001)
        return lower.body;
    const float alpha = clamp(static_cast<float>(
        (presentation_tick - lower.key) / segment_duration),
        0.0f, 1.0f);
    c_rigid_body result =
        lerp_rigidbody(lower.body, upper.body, alpha);
    c_rigid_body previous_fallback = lower.body;
    c_rigid_body next_fallback = upper.body;
    if (!previous) {
        previous_fallback.position = {
            lower.body.position.x * 2.0f - upper.body.position.x,
            lower.body.position.y * 2.0f - upper.body.position.y
        };
        previous = &previous_fallback;
    }
    if (!next) {
        next_fallback.position = {
            upper.body.position.x * 2.0f - lower.body.position.x,
            upper.body.position.y * 2.0f - lower.body.position.y
        };
        next = &next_fallback;
    }
    result.position = catmull_rom(
        previous->position,
        lower.body.position,
        upper.body.position,
        next->position,
        alpha);
    return result;
}

inline motion_presentation_result resolve_motion_presentation(
        const c_render_motion_presentation& presentation,
        const c_motion_breakpoint_history* breakpoints,
        double presentation_tick) {
    motion_presentation_result result{
        resolve_motion_presentation(presentation, presentation_tick),
        true
    };
    if (!breakpoints) return result;

    constexpr uint32_t maximum_anchors =
        motion_breakpoint_history_capacity + 2u;
    motion_presentation_anchor anchors[maximum_anchors]{};
    uint32_t anchor_count = 0u;
    const double segment_start =
        static_cast<double>(presentation.segment_tick);
    const double segment_end = segment_start + 1.0;
    anchors[anchor_count++] = {
        segment_start, presentation.current, motion_breakpoint_none
    };
    const c_rigid_body end = presentation_end(presentation);
    const uint32_t breakpoint_count =
        motion_breakpoint_count(*breakpoints);
    for (uint32_t index = 0u;
            index < breakpoint_count
                && anchor_count + 1u < maximum_anchors;
            ++index) {
        const motion_breakpoint& breakpoint =
            breakpoints->breakpoints[index];
        if (breakpoint.kind == motion_breakpoint_none
                || breakpoint.kind == motion_breakpoint_segment_end) {
            continue;
        }
        const double key = motion_breakpoint_key(breakpoint);
        if (key < segment_start - 0.000001
                || key > segment_end + 0.000001) {
            continue;
        }
        anchors[anchor_count++] = {
            key,
            rigidbody_from_motion_breakpoint(
                breakpoint, presentation_tick >= key),
            breakpoint.kind
        };
    }
    anchors[anchor_count++] = {
        segment_end, end, motion_breakpoint_none
    };
    for (uint32_t index = 1u; index < anchor_count; ++index) {
        const motion_presentation_anchor value = anchors[index];
        uint32_t target = index;
        while (target > 0u
                && (anchors[target - 1u].key > value.key
                    || (std::abs(anchors[target - 1u].key - value.key)
                            <= 0.000001
                        && anchors[target - 1u].kind > value.kind))) {
            anchors[target] = anchors[target - 1u];
            --target;
        }
        anchors[target] = value;
    }

    bool have_spawn = false;
    double earliest_spawn_key = 0.0;
    c_rigid_body earliest_spawn{};
    bool have_lifecycle = false;
    bool lifecycle_visible = true;
    c_rigid_body lifecycle_body{};
    for (uint32_t index = 0u; index < breakpoint_count; ++index) {
        const motion_breakpoint& breakpoint =
            breakpoints->breakpoints[index];
        const double key = motion_breakpoint_key(breakpoint);
        const c_rigid_body breakpoint_body =
            rigidbody_from_motion_breakpoint(
                breakpoint, presentation_tick >= key);
        if (breakpoint.kind == motion_breakpoint_spawn
                && (!have_spawn || key < earliest_spawn_key)) {
            have_spawn = true;
            earliest_spawn_key = key;
            earliest_spawn = breakpoint_body;
        }
        if ((breakpoint.kind == motion_breakpoint_spawn
                    || breakpoint.kind == motion_breakpoint_hide)
                && key <= presentation_tick + 0.000001) {
            have_lifecycle = true;
            lifecycle_visible =
                breakpoint.kind == motion_breakpoint_spawn;
            lifecycle_body = breakpoint_body;
        }
    }
    if (have_spawn
            && presentation_tick < earliest_spawn_key - 0.000001) {
        return {earliest_spawn, false};
    }
    if (have_lifecycle && !lifecycle_visible)
        return {lifecycle_body, false};

    uint32_t lower_index = 0u;
    uint32_t upper_index = anchor_count - 1u;
    for (uint32_t index = 0u; index < anchor_count; ++index) {
        if (anchors[index].key <= presentation_tick + 0.000001)
            lower_index = index;
        if (anchors[index].key >= presentation_tick - 0.000001) {
            upper_index = index;
            break;
        }
    }
    const c_rigid_body* previous = nullptr;
    const c_rigid_body* next = nullptr;
    for (uint32_t index = lower_index; index > 0u; --index) {
        if (anchors[index - 1u].key
                < anchors[lower_index].key - 0.000001) {
            previous = &anchors[index - 1u].body;
            break;
        }
    }
    if (!previous
            && std::abs(anchors[lower_index].key - segment_start)
                <= 0.000001
            && presentation.has_previous) {
        previous = &presentation.previous;
    }
    for (uint32_t index = upper_index + 1u;
            index < anchor_count; ++index) {
        if (anchors[index].key
                > anchors[upper_index].key + 0.000001) {
            next = &anchors[index].body;
            break;
        }
    }
    if (!next
            && std::abs(anchors[upper_index].key - segment_end)
                <= 0.000001
            && presentation.has_next) {
        next = &presentation.next;
    }
    result.body = interpolate_motion_anchors(
        anchors[lower_index],
        anchors[upper_index],
        previous,
        next,
        presentation_tick);
    result.visible = !have_lifecycle || lifecycle_visible;
    return result;
}

inline int compare_lifecycle_endpoint(
        const motion_breakpoint& breakpoint,
        const c_motion_lifecycle_state& lifecycle) {
    const double key = motion_breakpoint_key(breakpoint);
    const double consumed_key =
        static_cast<double>(lifecycle.consumed_tick_id)
        - 1.0
        + static_cast<double>(clamp(
            lifecycle.consumed_trigger_alpha, 0.0f, 1.0f));
    if (key < consumed_key - 0.000001)
        return -1;
    if (key > consumed_key + 0.000001)
        return 1;
    if (breakpoint.kind < lifecycle.consumed_kind)
        return -1;
    if (breakpoint.kind > lifecycle.consumed_kind)
        return 1;
    if (breakpoint.tick_id < lifecycle.consumed_tick_id)
        return -1;
    if (breakpoint.tick_id > lifecycle.consumed_tick_id)
        return 1;
    if (breakpoint.trigger_alpha
            < lifecycle.consumed_trigger_alpha - 0.000001f)
        return -1;
    if (breakpoint.trigger_alpha
            > lifecycle.consumed_trigger_alpha + 0.000001f)
        return 1;
    return 0;
}

inline bool find_next_lifecycle_endpoint(
        const c_motion_breakpoint_history* breakpoints,
        const c_motion_lifecycle_state& lifecycle,
        double presentation_tick,
        motion_breakpoint& result) {
    if (!breakpoints)
        return false;
    bool found = false;
    const uint32_t count =
        motion_breakpoint_count(*breakpoints);
    for (uint32_t index = 0u; index < count; ++index) {
        const motion_breakpoint& breakpoint =
            breakpoints->breakpoints[index];
        if (breakpoint.kind != motion_breakpoint_spawn
                && breakpoint.kind != motion_breakpoint_hide) {
            continue;
        }
        if (motion_breakpoint_key(breakpoint)
                > presentation_tick + 0.000001) {
            continue;
        }
        if (lifecycle.has_consumed_endpoint
                && compare_lifecycle_endpoint(
                    breakpoint, lifecycle) <= 0) {
            continue;
        }
        if (!found) {
            result = breakpoint;
            found = true;
            continue;
        }
        c_motion_lifecycle_state candidate_cursor{};
        candidate_cursor.has_consumed_endpoint = true;
        candidate_cursor.consumed_tick_id = result.tick_id;
        candidate_cursor.consumed_trigger_alpha =
            result.trigger_alpha;
        candidate_cursor.consumed_kind = result.kind;
        if (compare_lifecycle_endpoint(
                breakpoint, candidate_cursor) < 0) {
            result = breakpoint;
        }
    }
    return found;
}

inline c_presented_motion resolve_canonical_presented_motion(
        const c_render_motion_presentation& presentation,
        const c_motion_breakpoint_history* breakpoints,
        double presentation_tick,
        const motion_presentation_result& raw,
        c_motion_lifecycle_state& lifecycle) {
    c_presented_motion result{
        raw.body, presentation_tick,
        static_cast<motion_endpoint_kind>(0), true, raw.visible
    };
    motion_breakpoint endpoint{};
    if (find_next_lifecycle_endpoint(
            breakpoints, lifecycle,
            presentation_tick, endpoint)) {
        result.body =
            rigidbody_from_motion_breakpoint(endpoint, true);
        result.sample_tick = motion_breakpoint_key(endpoint);
        result.endpoint_kind =
            static_cast<motion_endpoint_kind>(endpoint.kind);
        result.visible = true;
        lifecycle.initialized = true;
        lifecycle.has_consumed_endpoint = true;
        lifecycle.consumed_tick_id = endpoint.tick_id;
        lifecycle.consumed_trigger_alpha =
            endpoint.trigger_alpha;
        lifecycle.consumed_kind = endpoint.kind;
        return result;
    }
    if (!lifecycle.initialized && raw.visible) {
        result.body = presentation.current;
        result.sample_tick =
            static_cast<double>(presentation.segment_tick);
        result.visible = true;
        lifecycle.initialized = true;
    }
    return result;
}


$r e_update[-800](
    const c_presented_motion& presented,
    c_textured_sprite& sprite
) {
    if (!presented.valid)
        continue;
    if (!presented.visible) {
        e.remove<c_textured_sprite>();
        continue;
    }
    sprite.position = presented.body.position;
    sprite.rotation = presented.body.rotation;
    sprite.stable_id = context.engine->entity_stable_id(
        context.engine_context, context.world, e.id());
};

$r e_update[-800](
    const c_presented_motion& presented,
    c_colored_quad& quad
) {
    if (!presented.valid)
        continue;
    quad.position = presented.body.position;
    quad.rotation = presented.body.rotation;
    if (!presented.visible)
        e.remove<c_colored_quad>();
};

$r e_update[-800](
    const c_rigid_body& body,
    exclude c_render_motion_presentation,
    c_textured_sprite& sprite
) {
    sprite.position = body.position;
    sprite.rotation = body.rotation;
    sprite.stable_id = context.engine->entity_stable_id(
        context.engine_context, context.world, e.id());
};

$r g_update[1000] {
    const auto toggle =
        input_button(context, "debug_overlay");
    if (toggle.pressed)
        g_debug_overlay_enabled =
            !g_debug_overlay_enabled;
};

$r e_update[1000](
    const c_rigid_body& body,
    const c_aabb& bounds
) {
    if (!g_debug_overlay_enabled)
        continue;
    (void)body;
    vec2 visual_position{};
    float visual_rotation = 0.0f;
    const auto* presented =
        e.try_get<c_presented_motion>();
    if (presented && presented->valid) {
        if (!presented->visible)
            continue;
        visual_position = presented->body.position;
        visual_rotation = presented->body.rotation;
    } else if (const auto* sprite =
            e.try_get<c_textured_sprite>()) {
        visual_position = sprite->position;
        visual_rotation = sprite->rotation;
    } else if (const auto* quad = e.try_get<c_colored_quad>()) {
        visual_position = quad->position;
        visual_rotation = quad->rotation;
    } else {
        continue;
    }

    const float c = std::cos(visual_rotation);
    const float s = std::sin(visual_rotation);
    const vec2 rotated_offset{
        bounds.offset.x * c - bounds.offset.y * s,
        bounds.offset.x * s + bounds.offset.y * c
    };
    const vec2 box_size{
        bounds.half_size.x * 2.0f,
        bounds.half_size.y * 2.0f
    };
    const auto draw_outline = [&](const vec2& position,
            const vec4& color, float rotation = 0.0f) {
        draw<c_debug_wireframe>(context, {
            position, box_size, rotation, color, 0.0f
        });
    };
    const auto timing = presentation_timing(context);
    if (timing.valid) {
        if (const auto* presentation =
                e.try_get<c_render_motion_presentation>()) {
            debug_motion_anchor_segment anchors{};
            if (debug_motion_anchors_for_segment(
                    *presentation,
                    e.try_get<c_motion_breakpoint_history>(),
                    presented && presented->valid
                        ? presented->sample_tick
                        : timing.presentation_tick,
                    anchors)) {
                constexpr vec4 path_color{
                    0.25f, 0.9f, 1.0f, 1.0f
                };
                constexpr vec4 start_color{
                    0.1f, 1.0f, 0.45f, 1.0f
                };
                constexpr vec4 end_color{
                    1.0f, 0.25f, 0.35f, 1.0f
                };
                for (uint32_t index = 1u;
                        index < anchors.count; ++index) {
                    const vec2 start = anchors.points[index - 1u];
                    const vec2 end = anchors.points[index];
                    const float dx = end.x - start.x;
                    const float dy = end.y - start.y;
                    if (dx * dx + dy * dy > 0.00000001f) {
                        draw<c_debug_line>(context, {
                            start, end, path_color, 0.0f
                        });
                    }
                }
                for (uint32_t index = 0u;
                        index < anchors.count; ++index) {
                    draw_outline(
                        anchors.points[index],
                        index == 0u ? start_color : end_color);
                }
            }
        }
    }
    draw_outline(
        {
            visual_position.x + rotated_offset.x,
            visual_position.y + rotated_offset.y
        },
        {1.0f, 0.8f, 0.2f, 1.0f},
        visual_rotation);
};
