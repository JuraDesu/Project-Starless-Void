#include "event.hpp"
#include "input.hpp"

#include <cmath>



inline uint64_t g_shoot_sequence = 0;

$ g_init {
    input.button("move_up", {Key::W, Key::Up});
    input.button("move_down", {Key::S, Key::Down});
    input.button("move_left", {Key::A, Key::Left});
    input.button("move_right", {Key::D, Key::Right});
    input.button("shoot", {Key::C, Key::Space});
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
        collision_enemy, collision_friendly, true, true
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

inline bool spawn_inventory_projectile(
        const World& world,
        uint64_t owner,
        const vec2& origin,
        float angle,
        float speed,
        int32 lifetime_ticks,
        const c_player_inventory& inventory) {
    const vec2 velocity = angle_to_vec(angle);
    const c_rigid_body projectile_body{
        origin,
        angle,
        velocity * speed,
        0.0f
    };
    entity spawned;
    return world.spawn<p_inst>(spawned, [&](entity& spawned) {
        spawned.set<c_rigid_body>(projectile_body);
        spawned.set<c_inst_source>({speed, owner});
        spawned.set<c_temporary>({lifetime_ticks});
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
    const auto shoot = input_button("shoot");
    if (up.valid && down.valid && left.valid && right.valid) {
        vec2 movement{
            (right.down ? 1.0f : 0.0f) - (left.down ? 1.0f : 0.0f),
            (up.down ? 1.0f : 0.0f) - (down.down ? 1.0f : 0.0f)};
        if (length(movement) > 1.0f) movement = normalize(movement);
        const bool shooting =
            (shoot.valid && (shoot.down || shoot.pressed))
            || (cursor.primary.valid
                && (cursor.primary.down || cursor.primary.pressed));
        if (shooting) {
            ++g_shoot_sequence;
            if (!g_shoot_sequence) ++g_shoot_sequence;
        }
        constexpr float speed = 0.16666667f;
        body.velocity = movement * speed;
        if (cursor.valid)
            body.rotation = HPI;/*vec_to_angle(
                vec2{cursor.world_x, cursor.world_y} - body.position)*/;
        if (weapon.cooldown_ticks > 0) --weapon.cooldown_ticks;
        if (g_shoot_sequence != 0
                && g_shoot_sequence != weapon.last_shoot_sequence) {
            weapon.last_shoot_sequence = g_shoot_sequence;
            vec2 direction = /*cursor.valid
                ? vec2{cursor.world_x, cursor.world_y} - body.position
                : */angle_to_vec(body.rotation);
            if (weapon.cooldown_ticks <= 0
                    && dot(direction, direction) > 0.000001f) {
                direction = normalize(direction);
                constexpr float projectile_radius = 0.14f;
                constexpr float projectile_speed = 2.5f;
                const vec2 origin = body.position + bounds.offset
                    + direction * (bounds.half_size.x + projectile_radius);
                float aim_angle = vec_to_angle(direction);

                constexpr float accuracy = 0.05f;
                
                aim_angle += sfrand() * accuracy;

                bool spawned_any = false;
                constexpr int shot_count = 1;
                for (uint32_t shot = 0; shot < shot_count; ++shot) {
                    const bool projectile = spawn_inventory_projectile(
                        world, e.stable_id(), origin,
                        aim_angle, projectile_speed, 120, inventory);
                    spawned_any = spawned_any || projectile;
                }
                if (spawned_any) weapon.cooldown_ticks = 2;
            }
        }
    }
};
