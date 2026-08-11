$c c_enemy_projectile {
    int lifetime;
};

$cr p_enemy_projectile {
    c_rigid_body {};
    c c_aabb {{0.0f, 0.0f}, {0.245f, 0.245f}};
    c c_collider {collision_friendly, collision_enemy, false, true};
    r c_textured_sprite {
        make_sprite<t_invalid>({}, 20.0f)
    };
    c c_enemy_projectile {500};
    r c_presented_motion {};
    r c_rigidbody_sample_history {};
    r c_render_motion_presentation {};
    r c_motion_lifecycle_state {};
    c c_kinematic_motion {};
};

$c e_update(
    c_enemy_projectile& proj,
    const c_rigid_body& body
) {
    if (--proj.lifetime < 0) {
        begin_motion_despawn(
            e, tick, 1.0f, body.position, body.position,
            body.rotation, body.velocity);
    }
};
