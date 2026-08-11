$cr c_enemy {};

$c c_enemy_boss {
    float cooldown = 0.f;
    float shoot_direction_offset = 0.f;
};

$cr p_enemy {
    c_enemy {};
    c_rigid_body {};
    c_health {1000, 1000};
    c c_burnable {};
    c c_aabb {{0.0f, 0.0f}, {0.245f, 0.245f}};
    c c_collider {collision_friendly, collision_enemy, true, true};
    r c_textured_sprite {
        make_sprite<t_invalid>({}, 20.0f)
    };
};

$c e_update[900](
    c_enemy,
    const c_health& health,
    const c_rigid_body& body,
    exclude c_pending_destruction
) {
    if (health.current > 0)
        continue;
    begin_motion_despawn(
        e, tick, 1.0f, body.position, body.position,
        body.rotation, body.velocity);
};

$c e_update(
    c_enemy,
    c_enemy_boss& boss,
    c_rigid_body& rb,
    exclude c_pending_destruction
) {
    if (boss.cooldown <= 0.f) {
        boss.cooldown = 1.0;
        constexpr int count = 40;
        for (int i = 0; i < count; i++){
            float fi = float(i) / float(count);
            float angle = fi * TPI + boss.shoot_direction_offset;
            constexpr float speed = 0.1f;
            world.spawn<p_enemy_projectile>([&](entity& e) {
                const c_rigid_body projectile_body{
                    rb.position,
                    angle,
                    angle_to_vec(angle) * speed,
                    0.0f
                };
                e.set<c_rigid_body>(projectile_body);
                append_spawn_motion_breakpoint(
                    e, tick, projectile_body);
            });
        }
        boss.shoot_direction_offset += 0.06;
    } else {
        boss.cooldown -= 0.1;
    }
};
