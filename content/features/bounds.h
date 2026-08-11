inline constexpr vec2 visible_bounds_size{30.0f, 40.0f};
inline constexpr vec2 visible_bounds_center{0.0f, 100.0f};

// `box` stores a minimum corner and a size, rather than two corners.
inline const box visible_bounds{
    visible_bounds_center - visible_bounds_size * 0.5f,
    visible_bounds_size};

// Projectiles leave the play area before disappearing, while the player is
// constrained to a smaller inset area.
inline constexpr float despawn_bounds_offset = 7.0f;
inline const box despawn_bounds{
    visible_bounds.pos - vec2{
        despawn_bounds_offset, despawn_bounds_offset},
    visible_bounds.bounds + vec2{
        despawn_bounds_offset * 2.0f, despawn_bounds_offset * 2.0f}};

inline constexpr float movement_bounds_offset = -0.7f;
inline const box movement_bounds{
    visible_bounds.pos - vec2{
        movement_bounds_offset, movement_bounds_offset},
    visible_bounds.bounds + vec2{
        movement_bounds_offset * 2.0f, movement_bounds_offset * 2.0f}};

$c e_update[180](
    c_temporary,
    const c_rigid_body& body,
    exclude c_pending_destruction
) {
    if (despawn_bounds.intersects(body.position))
        continue;
    e.destroy();
};

$c e_update(
    c_aabb,
    c_rigid_body& body,
    c_player,
    c_collider
) {
    if (!movement_bounds.intersects(body.position)) {
        body.position = clamp(
            body.position,
            movement_bounds.pos,
            movement_bounds.pos + movement_bounds.bounds);
    }
};

$cr c_bounds_camera {};

$cr p_bounds_camera {
    c_rigid_body {};
    r c_rigidbody_sample_history {};
    r c_render_motion_presentation {};
    r c_motion_lifecycle_state {};
    r c_presented_motion {};
    c_bounds_camera {};
};

inline void spawn_bounds_outline(
        const World& world, const box& bounds, const vec4& color) {
    entity outline = world.create();
    outline.set<c_debug_wireframe>(c_debug_wireframe{
        bounds.center(), bounds.bounds, 0.0f, color, 0.0f});
}

$c g_start {
    world.spawn<p_bounds_camera>([](entity& e) {
        e.set<c_rigid_body>({
            visible_bounds_center,
            0.0f,
            {0.0f, 0.0f},
            0.0f
        });
    });
};

$r g_start {
    spawn_bounds_outline(
        world, visible_bounds, {0.35f, 0.85f, 1.0f, 1.0f});
    spawn_bounds_outline(
        world, despawn_bounds, {1.0f, 0.3f, 0.25f, 1.0f});
    spawn_bounds_outline(
        world, movement_bounds, {0.3f, 1.0f, 0.45f, 1.0f});
};

$r e_add(c_presented_motion, c_bounds_camera) {
    camera_follow(e);
    camera_zoom(0.04f);
};

$c g_start {
    g_shoot_sequence = 0u;
    std::srand(0x12345678u);
    g_spatial_chunks.clear();
    g_spatial_generation = 0u;
    reset_particle_state();
    g_projectile_emitters.reset();
    g_fire_emitters.reset();
    g_aura_emitters.reset();
    world.spawn<p_player>([](entity& e) {
        e.set<c_rigid_body>({
            {visible_bounds_center.x,
                visible_bounds.pos.y + visible_bounds.bounds.y * 0.2f},
            0.0f, {}, 0.0f});
    });
    world.spawn<p_enemy>([](entity& e) {
        e.add<c_enemy_boss>();
        e.set<c_rigid_body>({
            {visible_bounds_center.x,
                visible_bounds.pos.y + visible_bounds.bounds.y * 0.9f},
            0.0f, {}, 0.0f});
    });
    world.spawn<p_enemy>([](entity& e) {
        e.add<c_dummy>() && e.set<c_rigid_body>({
            {visible_bounds.pos.x + visible_bounds.bounds.x * 0.2f,
                visible_bounds.pos.y + visible_bounds.bounds.y * 0.3f},
            0.0f, {}, 0.0f});
    });
    const auto item_types = component_children<c_item>();
    const float spacing = static_cast<float>(item_types.size());
    for (uint32_t index = 0; index < item_types.size(); ++index) {
        const float fraction = static_cast<float>(index)
            / static_cast<float>(item_types.size());
        const EngineComponentId item_type = item_types[index];
        world.spawn<p_ground_item>([=](entity& item) {
            if (!item.add(item_type)) return false;
            auto& body = item.get_mut<c_rigid_body>();
            body.position = {
                visible_bounds_center.x - spacing * 0.5f
                    + fraction * spacing,
                visible_bounds.pos.y + visible_bounds.bounds.y * 0.1f};
            return true;
        });
    }
};
