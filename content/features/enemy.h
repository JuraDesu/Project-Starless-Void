$cr c_enemy {
};

$cr p_enemy {
    c_enemy {};
    c_rigid_body {};
    c_health {1000, 1000};
    c c_burnable {};
    c c_aabb {{0.0f, 0.0f}, {0.245f, 0.245f}};
    c c_collider {1u, 2u, true, true};
    r c_textured_sprite {
        make_sprite<t_invalid>({}, 20.0f)
    };
};

