$cr c_item_crit : c_item {
    float travel_budget = 3.5f;
    float velocity_multiplier = 0.92f;

    r e_item_visual {
        ctx.name = "crit decay";
        ctx.icon = item_icon<t_item_crit>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "slows projectiles over " << self.travel_budget;
    };
    c e_item_inst_apply {
        ctx.target.set<c_inst_crit_decay>({
            self.travel_budget, self.velocity_multiplier
        });
    };
};

$c e_update[-500](
    c_inst_crit_decay& decay,
    c_rigid_body& body,
    exclude c_pending_destruction
) {
    decay.travel_remaining -= length(body.velocity);
    body.velocity *= clamp(decay.velocity_multiplier, 0.0f, 1.0f);
    if (decay.travel_remaining <= 0.0f
            || dot(body.velocity, body.velocity) <= 0.0004f) {
        const float rotation = length(body.velocity) > 0.0001f
            ? vec_to_angle(body.velocity) : body.rotation;
        begin_motion_despawn(
            e, tick, 1.0f, body.position, body.position,
            rotation, body.velocity);
    }
};

$c c_inst_crit_decay {
    float travel_remaining = 3.5f;
    float velocity_multiplier = 0.92f;
};
