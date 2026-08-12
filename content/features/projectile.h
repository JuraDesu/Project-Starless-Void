#include "event.hpp"

#include <algorithm>
#include <cmath>



struct ProjectileContact {
    uint64_t stable_id;
    float toi;
    vec2 point;
    vec2 normal;
};

$c e_hit {
    entity_id target;
    vec2 point;
    vec2 normal;
    float toi;
    uint32 hits_processed;
    uint32 hit_limit;
    bool consume_hit = true;
    bool destroy_projectile = false;
    bool stop_sweep = false;
};

$cr c_inst {
};

$c c_inst_damage {
    int32 amount = 1;
};

$c c_inst_hit_budget {
    int32 remaining = 1;
};

$c c_inst_source {
    float speed = 2.5f;
    entity_id owner = 0;
};

$c c_temporary {
    int32 ticks = 120;
};

$c e_update[170](c_temporary& temporary) {
    if (--temporary.ticks <= 0)
        e.destroy();
};

$c c_projectile_recent_hit {
    uint64 expires_tick = 0;
};

$c e_update[150](
    const c_projectile_recent_hit(*)& recent
) {
    if (tick > recent.expires_tick)
        e.remove_pair<c_projectile_recent_hit>(recent_target);
};

$c c_knockback_on_hit {
    float strength = 0.25f;
};

$c c_projectile_previous {
    vec2 position;
};

$cr p_inst {
    c_inst {};
    c_inst_damage {};
    c_inst_hit_budget {};
    c_inst_source {};
    c_temporary {120};
    c_hit_feedback_history {};
    c_knockback_on_hit {};
    c_rigid_body {};
    c c_kinematic_motion {};
    c c_projectile_previous {};
    c c_aabb {{}, {0.14f, 0.14f}};
    c c_collider {collision_enemy | collision_tile, collision_friendly, false, true};
    r c_color {
        {}, {0.28f, 0.28f}, 0.0f,
        {0.35f, 0.95f, 1.0f, 1.0f}, 0.1f
    };
    r c_rigidbody_sample_history {};
    r c_render_motion_presentation {};
    r c_motion_lifecycle_state {};
    r c_presented_motion {};
    r c_hit_feedback_cursor {};
};

$c e_hit(
    c_inst,
    const c_inst_damage& damage,
    const c_knockback_on_hit& knockback,
    target: c_health& health,
    target: c_rigid_body& target_body
) {
    health.current = max(health.current - damage.amount, 0);
    target_body.velocity.x += -event.normal.x * knockback.strength;
    target_body.velocity.y += -event.normal.y * knockback.strength;
};

$c e_update[200](
    const c_inst_source& source,
    c_inst_hit_budget& budget,
    const c_rigid_body& body,
    const c_aabb& projectile_bounds,
    const c_collider& projectile_collider,
    exclude c_pending_destruction
) {
    auto& previous = e.get_mut<c_projectile_previous>();
    ProjectileContact contacts[64]{};
    uint32_t contact_count = 0;
    const vec2 sweep_min = min(previous.position, body.position)
        - projectile_bounds.half_size;
    const vec2 sweep_max = max(previous.position, body.position)
        + projectile_bounds.half_size;
    for_each_spatial_candidate_in_bounds(
            world, sweep_min, sweep_max,
            [&](entity target) {
        if (!target.has<c_health>() || !target.has<c_rigid_body>()
                || !target.has<c_aabb>() || !target.has<c_collider>())
            return true;
        const uint64_t stable = target.stable_id();
        if (!stable || stable == source.owner) {
            return true;
        }
        if (const auto* recent_hit =
                e.try_get_pair<c_projectile_recent_hit>(target)) {
            if (tick <= recent_hit->expires_tick)
                return true;
            e.remove_pair<c_projectile_recent_hit>(target);
        }
        const auto& health = target.get<c_health>();
        const auto& target_body = target.get<c_rigid_body>();
        const auto& target_bounds = target.get<c_aabb>();
        const auto& target_collider = target.get<c_collider>();
        if (health.current <= 0
                || !colliders_match(projectile_collider, target_collider)) {
            return true;
        }
        const vec2 center{
            target_body.position.x + target_bounds.offset.x,
            target_body.position.y + target_bounds.offset.y
        };
        const vec2 expanded{
            target_bounds.half_size.x + projectile_bounds.half_size.x,
            target_bounds.half_size.y + projectile_bounds.half_size.y
        };
        float toi = 1.0f;
        vec2 normal{};
        if (sweep_expanded_aabb(
                previous.position, body.position, center, expanded,
                toi, normal)) {
            const ProjectileContact candidate{
                stable, toi,
                {
                    previous.position.x
                        + (body.position.x - previous.position.x) * toi,
                    previous.position.y
                        + (body.position.y - previous.position.y) * toi
                },
                normal
            };
            if (contact_count < 64u) {
                contacts[contact_count++] = candidate;
            } else {
                uint32_t worst = 0;
                for (uint32_t index = 1; index < contact_count; ++index) {
                    if (contacts[index].toi > contacts[worst].toi
                            || (contacts[index].toi == contacts[worst].toi
                                && contacts[index].stable_id
                                    > contacts[worst].stable_id)) {
                        worst = index;
                    }
                }
                if (candidate.toi < contacts[worst].toi
                        || (candidate.toi == contacts[worst].toi
                            && candidate.stable_id
                                < contacts[worst].stable_id)) {
                    contacts[worst] = candidate;
                }
            }
        }
        return true;
    });
    std::sort(contacts, contacts + contact_count,
        [](const auto& left, const auto& right) {
            return left.toi != right.toi
                ? left.toi < right.toi
                : left.stable_id < right.stable_id;
        });
    uint32_t processed = 0;
    bool destroy = false;
    bool have_destroy_contact = false;
    ProjectileContact destroy_contact{};
    for (uint32_t contact_index = 0;
            contact_index < contact_count; ++contact_index) {
        const auto& contact = contacts[contact_index];
        e_hit hit{
            contact.stable_id, contact.point, contact.normal, contact.toi,
            processed, static_cast<uint32_t>(
                max(budget.remaining, 0)),
            true, false, false
        };
        if (!dispatch(e, hit)) {
            break;
        }
        entity target = world.from_stable_id(contact.stable_id);
        if (target)
            e.set_pair<c_projectile_recent_hit>(target, {tick + 3u});
        ++processed;
        if (hit.consume_hit) --budget.remaining;
        destroy = hit.destroy_projectile || budget.remaining <= 0;
        if (destroy) {
            have_destroy_contact = true;
            destroy_contact = contact;
        }
        if (destroy || hit.stop_sweep) break;
    }
    const vec2 segment_end = body.position;
    previous.position = segment_end;
    if (destroy) {
        const float rotation =
            std::abs(body.velocity.x) + std::abs(body.velocity.y)
                    > 0.0001f
                ? std::atan2(body.velocity.y, body.velocity.x)
                : body.rotation;
        begin_motion_despawn(
            e,
            tick,
            have_destroy_contact ? destroy_contact.toi : 1.0f,
            segment_end,
            have_destroy_contact
                ? destroy_contact.point : segment_end,
            rotation,
            body.velocity);
    }
};
