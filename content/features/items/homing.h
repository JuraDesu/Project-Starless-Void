$cr c_item_homing : c_item {
    float radius = 8.0f;

    r e_item_visual {
        ctx.name = "homing";
        ctx.icon = item_icon<t_item_homing>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "homes toward enemies within " << self.radius;
    };
    c e_item_inst_apply {
        ctx.target.set<c_inst_homing>({self.radius, 0});
    };
};

$c e_update[-500](
    c_inst_homing& homing,
    c_rigid_body& body,
    exclude c_pending_destruction
) {
    entity target = homing.target
        ? world.from_stable_id(homing.target) : entity{};
    const auto valid_target = [&](entity candidate) {
        const auto* health = candidate.try_get<c_health>();
        const auto* collider = candidate.try_get<c_collider>();
        return candidate && candidate.has<c_enemy>()
            && health && health->current > 0 && collider
            && collider_has_type(*collider, collision_enemy)
            && candidate.has<c_rigid_body>() && candidate.has<c_aabb>();
    };
    if (!valid_target(target)) {
        homing.target = 0;
        float closest_distance = homing.radius * homing.radius;
        for_each_spatial_candidate_in_radius(
                world, body.position, homing.radius,
                [&](entity candidate) {
            if (!valid_target(candidate)) return true;
            const auto& target_body = candidate.get<c_rigid_body>();
            const auto& bounds = candidate.get<c_aabb>();
            const vec2 offset = target_body.position + bounds.offset
                - body.position;
            const float candidate_distance = dot(offset, offset);
            if (candidate_distance < closest_distance) {
                closest_distance = candidate_distance;
                target = candidate;
            }
            return true;
        });
        if (target) homing.target = target.stable_id();
    }
    if (valid_target(target)) {
        auto& target_body = target.get<c_rigid_body>();

        float current_angle = vec_to_angle(body.velocity);
        float current_speed = length(body.velocity);

        float target_angle = vec_to_angle(target_body.position - body.position);
        float target_speed = length(target_body.position - body.position);

        float difference = angle_difference(current_angle, target_angle);

        float maximum_rotation_speed = 1.25f
            / (1.0f + current_speed * 2.0f);

        float next_angle = current_angle + clamp(difference, -maximum_rotation_speed, maximum_rotation_speed);//todo remove "std::"

        float speed_increment = (abs(difference) / PI - 0.5f) * -0.75f;

        float next_speed = current_speed + speed_increment;

        body.velocity = angle_to_vec(next_angle) * next_speed;
        body.rotation = next_angle;
    }
};

$c c_inst_homing {
    float radius = 8.0f;
    entity_id target = 0;
};
