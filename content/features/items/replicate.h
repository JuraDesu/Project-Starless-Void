$cr c_item_replicate : c_item {
    r e_item_visual {
        ctx.name = "replicate";
        ctx.icon = item_icon<t_invalid>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "creates a child projectile on impact";
    };
    c e_item_inst_apply {
        ctx.target.add<c_inst_replicate>();
    };
};

$c e_hit(
    const c_inst_replicate& replicate,
    const c_inst_source& source
) {
    (void)replicate;
    uint64_t seed = e.stable_id()
        ^ (event.target * 0x9e3779b97f4a7c15ull);
    seed ^= seed >> 30u;
    seed *= 0xbf58476d1ce4e5b9ull;
    seed ^= seed >> 27u;
    const float angle = static_cast<float>(seed & 0xffffu)
        * (TPI / 65536.0f);
    const vec2 direction = angle_to_vec(angle);
    const vec2 origin = event.point + direction;
    const c_rigid_body child_body{
        origin, angle, direction * 5.0f, 0.0f};
    world.spawn<p_inst>([&](entity child) {
        child.set<c_rigid_body>(child_body);
        child.set<c_inst_source>({5.0f, 2.0f, source.owner});
        child.set<c_projectile>({2.0f});
        child.set<c_projectile_previous>({origin});
        child.set<c_inst_homing>({8.0f, event.target});
        child.set<c_knockback_on_hit>({0.65f});
        append_spawn_motion_breakpoint(child, context.tick, child_body);
    });
};

$c c_inst_replicate {};
