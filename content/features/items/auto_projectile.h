$cr c_item_auto_projectile : c_item {
    int32 interval_ticks = 30;
    float speed = 2.5f;
    float lifetime = 2.0f;
    float target_radius = 9.0f;

    r e_item_visual {
        ctx.name = "auto projectile";
        ctx.icon = item_icon<t_invalid>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "automatically fires at nearby enemies";
    };
    c e_item_pickup {
        c_player_auto_projectile next{
            max(self.interval_ticks, 1),
            max(self.interval_ticks, 1),
            self.speed, self.lifetime, self.target_radius
        };
        if (const auto* current =
                ctx.player.try_get<c_player_auto_projectile>()) {
            next.interval_ticks = min(
                max(current->interval_ticks, 1),
                next.interval_ticks);
            next.ticks_remaining = min(
                max(current->ticks_remaining, 1),
                next.interval_ticks);
            next.speed = max(current->speed, next.speed);
            next.lifetime = max(current->lifetime, next.lifetime);
            next.target_radius =
                max(current->target_radius, next.target_radius);
        }
        ctx.player.set<c_player_auto_projectile>(next);
    };
};

$c c_player_auto_projectile {
    int32 interval_ticks = 30;
    int32 ticks_remaining = 30;
    float speed = 2.5f;
    float lifetime = 2.0f;
    float target_radius = 9.0f;
};

$c e_update[-500](
    c_player,
    const c_rigid_body& body,
    const c_aabb& bounds,
    const c_player_inventory& inventory,
    c_player_auto_projectile& automatic
) {
    automatic.interval_ticks = max(automatic.interval_ticks, 1);
    if (--automatic.ticks_remaining > 0) continue;
    automatic.ticks_remaining = automatic.interval_ticks;
    entity best{};
    float best_distance_squared =
        automatic.target_radius * automatic.target_radius;
    for_each_spatial_candidate_in_radius(
            world, body.position, automatic.target_radius,
            [&](entity target) {
        if (!target || target.stable_id() == e.stable_id()
                || !target.has<c_health>() || !target.has<c_rigid_body>()
                || !target.has<c_aabb>() || !target.has<c_collider>())
            return true;
        const auto& health = target.get<c_health>();
        const auto& collider = target.get<c_collider>();
        if (health.current <= 0
                || !(collider.type_bits & collision_enemy))
            return true;
        const vec2 position = target.get<c_rigid_body>().position
            + target.get<c_aabb>().offset;
        const float candidate_distance = dot(
            position - body.position, position - body.position);
        if (candidate_distance < best_distance_squared
                || (candidate_distance == best_distance_squared
                    && (!best || target.stable_id() < best.stable_id()))) {
            best = target;
            best_distance_squared = candidate_distance;
        }
        return true;
    });
    float angle = body.rotation;
    if (best) angle = vec_to_angle(
        best.get<c_rigid_body>().position
            + best.get<c_aabb>().offset - body.position);
    const vec2 direction = angle_to_vec(angle);
    const vec2 origin = body.position + bounds.offset
        + direction * (bounds.half_size.x + 0.14f);
    spawn_inventory_projectile(
        world, e.stable_id(), origin, angle,
        max(automatic.speed, 0.1f),
        max(automatic.lifetime, 1.0f / 60.0f), inventory);
};
