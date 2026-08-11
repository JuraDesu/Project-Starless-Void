#include "event.hpp"
#include "input.hpp"

#include <cmath>



inline uint64_t g_shoot_sequence = 0;
inline thread_local uint32_t g_random_state = 0x12345678u;

inline uint32_t random_u32() {
    uint32_t value = g_random_state;
    value ^= value << 13u;
    value ^= value >> 17u;
    value ^= value << 5u;
    g_random_state = value ? value : 0x12345678u;
    return g_random_state;
}

inline float signed_random() {
    const float value = static_cast<float>(
        random_u32() & 0x00ffffffu) / 16777216.0f;
    return value * 2.0f - 1.0f;
}


$ g_init {
    input.button("move_up", {Key::W, Key::Up});
    input.button("move_down", {Key::S, Key::Down});
    input.button("move_left", {Key::A, Key::Left});
    input.button("move_right", {Key::D, Key::Right});
    input.button("debug_overlay", {Key::G});
};

$cr c_player {
};

$cr p_player {
    c_player {};
    c_rigid_body {};
    c c_kinematic_motion {};
    c_health {};
    c c_aabb {
        {0.0f, 0.0f}, {0.315f, 0.315f}
    };
    c c_collider {
        2u, 1u, true, true
    };
    c c_player_inventory {};
    c c_player_weapon {};
    r c_textured_sprite {
        make_sprite<t_player>({}, 18.0f)
    };
    r c_rigidbody_sample_history {};
    r c_render_motion_presentation {};
    r c_motion_lifecycle_state {};
    r c_presented_motion {};
};

inline entity spawn_inventory_projectile(
        const World& world,
        uint64_t owner,
        const vec2& origin,
        float angle,
        float speed,
        float lifetime,
        const c_player_inventory& inventory) {
    const vec2 direction{std::cos(angle), std::sin(angle)};
    const c_rigid_body projectile_body{
        origin,
        angle,
        {direction.x * speed, direction.y * speed},
        0.0f
    };
    return world.spawn<p_inst>([&](entity spawned) {
        spawned.set<c_rigid_body>(projectile_body);
        spawned.set<c_inst_source>({speed, lifetime, owner});
        spawned.set<c_projectile>({lifetime});
        spawned.set<c_projectile_previous>({origin});
        spawned.set<c_knockback_on_hit>({0.325f});
        e_item_inst_apply apply{spawned, 0, 0};
        const uint32_t item_count =
            min<uint32_t>(inventory.count, 10u);
        for (uint32_t index = 0; index < item_count; ++index) {
            entity item =
                world.from_stable_id(inventory.item_ids[index]);
            if (item) {
                dispatch(item, apply);
            }
        }
        spawned.set<c_inst_damage>({1 + apply.damage_bonus});
        spawned.set<c_inst_hit_budget>({1 + apply.additional_hits});
        append_spawn_motion_breakpoint(
            spawned, active_callback_tick(), spawned.get<c_rigid_body>());
    });
}

$c e_update[-500](
    c_rigid_body& body,
    c_player,
    const c_aabb& bounds,
    const c_player_inventory& inventory,
    c_player_weapon& weapon
) {
    const auto cursor = input_cursor();
    const auto up = input_button("move_up");
    const auto down = input_button("move_down");
    const auto left = input_button("move_left");
    const auto right = input_button("move_right");
    if (up.valid && down.valid && left.valid && right.valid) {
        vec2 movement{
            (right.down ? 1.0f : 0.0f) - (left.down ? 1.0f : 0.0f),
            (up.down ? 1.0f : 0.0f) - (down.down ? 1.0f : 0.0f)};
        if (length(movement) > 1.0f) movement = normalize(movement);
        if (cursor.primary.down || cursor.primary.pressed) {
            ++g_shoot_sequence;
            if (!g_shoot_sequence) ++g_shoot_sequence;
        }
        constexpr float speed = 0.16666667f;
        body.velocity = movement * speed;
        if (cursor.valid)
            body.rotation = vec_to_angle(
                vec2{cursor.world_x, cursor.world_y} - body.position);
        if (weapon.cooldown_ticks > 0) --weapon.cooldown_ticks;
        if (g_shoot_sequence != 0
                && g_shoot_sequence != weapon.last_shoot_sequence) {
            weapon.last_shoot_sequence = g_shoot_sequence;
            vec2 direction = cursor.valid
                ? vec2{cursor.world_x, cursor.world_y} - body.position
                : angle_to_vec(body.rotation);
            if (weapon.cooldown_ticks <= 0
                    && dot(direction, direction) > 0.000001f) {
                direction = normalize(direction);
                constexpr float projectile_radius = 0.14f;
                constexpr float projectile_speed = 2.5f;
                const vec2 origin = body.position + bounds.offset
                    + direction * (bounds.half_size.x + projectile_radius);
                const float aim_angle = vec_to_angle(direction);
                bool spawned_any = false;
                constexpr int shot_count = 1;
                for (uint32_t shot = 0; shot < shot_count; ++shot) {
                    entity projectile = spawn_inventory_projectile(
                        world, e.stable_id(), origin,
                        aim_angle, projectile_speed, 2.0f, inventory);
                    spawned_any = spawned_any || static_cast<bool>(projectile);
                }
                if (spawned_any) weapon.cooldown_ticks = 2;
            }
        }
    }
};
