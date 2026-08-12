$cr p_enemy_projectile {
    // Enemy shots use the same generic hit pipeline as player shots.  Their
    // collider polarity decides that they can hit friendly targets.
    c_inst {};
    c_inst_damage {1};
    c_inst_hit_budget {1};
    c_inst_source {};
    c_temporary {5000};
    c_hit_feedback_history {};
    c_knockback_on_hit {};
    c_rigid_body {};
    c c_projectile_previous {};
    c c_aabb {{0.0f, 0.0f}, {0.245f, 0.245f}};
    c c_collider {collision_friendly, collision_enemy, false, true};
    r c_texture {
        make_texture<t_invalid>({}, 20.0f)
    };
    r c_presented_motion {};
    r c_rigidbody_sample_history {};
    r c_render_motion_presentation {};
    r c_motion_lifecycle_state {};
    r c_hit_feedback_cursor {};
    c c_kinematic_motion {};
};
