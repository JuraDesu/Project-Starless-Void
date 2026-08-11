$cr c_item_splash : c_item {
    float radius = 1.75f;
    float damage_multiplier = 0.75f;

    r e_item_visual {
        ctx.name = "splash";
        ctx.icon = item_icon<t_item_splash>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "deals splash damage in radius " << self.radius;
    };
    c e_item_inst_apply {
        ctx.target.set<c_inst_splash_damage>({
            self.radius, self.damage_multiplier
        });
    };
};

$c e_hit(
    const c_inst_splash_damage& splash,
    const c_inst_damage& damage
) {
    const float radius = max(splash.radius, 0.0f);
    const int32_t amount = max(
        static_cast<int32_t>(std::round(
            static_cast<float>(damage.amount) * splash.damage_multiplier)), 1);
    if (radius <= 0.0f || damage.amount <= 0
            || splash.damage_multiplier <= 0.0f) continue;
    for_each_spatial_candidate_in_radius(
            world, event.point, radius,
            [&](entity target) {
        if (target.stable_id() == event.target
                || !target.has<c_enemy>() || !target.has<c_health>()
                || !target.has<c_rigid_body>()
                || !target.has<c_aabb>() || !target.has<c_collider>())
            return true;
        const auto& collider = target.get<c_collider>();
        if ((collider.type_bits & collision_enemy) == 0u) return true;
        const auto& body = target.get<c_rigid_body>();
        const auto& bounds = target.get<c_aabb>();
        const vec2 delta = body.position + bounds.offset - event.point;
        const vec2 closest = max(abs(delta) - bounds.half_size, vec2{});
        if (dot(closest, closest) <= radius * radius) {
            auto& health = target.get_mut<c_health>();
            health.current = max(health.current - amount, 0);
        }
        return true;
    });
};

$c c_inst_splash_damage {
    float radius = 1.75f;
    float damage_multiplier = 0.75f;
};
