$cr p_enemy_projectile {
    c_temporary {5000};
    c_rigid_body {};
    c c_aabb {{0.0f, 0.0f}, {0.245f, 0.245f}};
    c c_collider {collision_friendly, collision_enemy, false, true};
    r c_textured_sprite {
        make_sprite<t_invalid>({}, 20.0f)
    };
    r c_presented_motion {};
    r c_rigidbody_sample_history {};
    r c_render_motion_presentation {};
    r c_motion_lifecycle_state {};
    c c_kinematic_motion {};
};
