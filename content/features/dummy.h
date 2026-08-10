
$cr c_dummy {
};

$c c_heal_full_on_hit {
};

$cr p_dummy {
    c_dummy {};
    c_rigid_body {};
    c_health {1000, 1000};
    c c_heal_full_on_hit {};
    c c_burnable {};
    c c_aabb {{0.0f, 0.0f}, {0.245f, 0.245f}};
    c c_collider {1u, 2u, true, true};
    r c_textured_sprite {
        make_sprite<t_invalid>({}, 20.0f)
    };
};

// Training dummies restore their health after all ordinary hit effects.
$c e_hit[1000](
    const c_inst& inst,
    const c_inst_damage& damage
) {
    (void)inst;
    (void)damage;
    entity target = world.from_stable_id(event.target);
    if (!target || !target.has<c_heal_full_on_hit>()) continue;
    auto* health = target.try_get_mut<c_health>();
    if (health) health->current = health->max;
};
