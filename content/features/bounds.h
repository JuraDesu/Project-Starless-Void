box bounds = {{0.0f, 0.0f}, {30.0f, 40.0f}};
vec2 bounds_center = bounds.center();
$c e_update(c_aabb& aabb, c_rigid_body& rb, c_collider& col){
    (void)aabb;
    (void)col;
    if (!bounds.intersects(rb.position)) {
        rb.position = clamp(
            rb.position,
            bounds.pos,
            bounds.pos + bounds.bounds);
    }
};

$cr c_bounds {
};


$cr p_bounds_camera {
    c_rigid_body {};
    r c_rigidbody_sample_history {};
    r c_render_motion_presentation {};
    r c_motion_lifecycle_state {};
    r c_presented_motion {};
    c_bounds {};
};

$c g_start {
    world.spawn<p_bounds_camera>([](entity e) {
        e.set<c_rigid_body>({
            bounds_center,
            0.0f,
            {0.0f, 0.0f},
            0.0f
        });
    });
};

$r e_add(const c_presented_motion& motion, c_bounds bounds) {
    (void)motion;
    print << "motion pos: " << motion.body.position.x << " " << motion.body.position.y << "\n";
    camera_follow(e);
    camera_zoom(0.04f);
};

/*$r g_update[-1100] {
    const WheelState wheel = input_wheel(context);
    if (wheel.valid && wheel.y != 0.0f) {
        const float next = g_camera_zoom * std::pow(1.15f, wheel.y);
        if (camera_zoom(next)) g_camera_zoom = next;
    }
};*/

$r g_update[1000] {
    draw<c_debug_wireframe>(context, {
        bounds_center,
        bounds.bounds,
        0.0f,
        {0.35f, 0.85f, 1.0f, 1.0f},
        0.0f
    });
};

$c g_start {
    g_shoot_sequence = 0u;
    g_random_state = 0x12345678u;
    g_spatial_chunks.clear();
    g_spatial_generation = 0u;
    reset_particle_state();
    g_projectile_emitters.reset();
    g_fire_emitters.reset();
    g_aura_emitters.reset();
    world.spawn<p_player>();
    world.spawn<p_dummy>();
    world.spawn<p_dummy>([](entity e) {
        return e.set<c_rigid_body>(
            {{2.1f, 0.75f}, 0.0f, {}, 0.0f});
    });
    world.spawn<p_dummy>([](entity e) {
        return e.set<c_rigid_body>(
            {{2.1f, -0.75f}, 0.0f, {}, 0.0f});
    });
    const auto item_types = component_children<c_item>();

    float space = item_types.size();
    for (int i = 0; i < item_types.size(); i++) {
        float fi = float(i) / float(item_types.size());
        
        const EngineComponentId item_type = item_types[i];
        world.spawn<p_ground_item>([=](entity item) {
            if (!item.add(item_type)) return false;
            auto& body = item.get_mut<c_rigid_body>();
            body.position = {
                bounds.pos.x + bounds_center.x - space * 0.5 + fi * space,
                bounds.pos.y + bounds.bounds.y * 0.1};
            return true;
        });
    }
};
