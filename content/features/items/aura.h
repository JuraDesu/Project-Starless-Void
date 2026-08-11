#include "render.hpp"

struct aura_emitter_state { float carry{}; };
inline particle_emitter_pool<aura_emitter_state> g_aura_emitters{};

$compute aura_particle {
    state {
        vec2 velocity;
        float angular_velocity;
        float lifetime;
        float initial_lifetime;
        vec2 start_size;
        vec2 end_size;
        vec4 start_color;
        vec4 end_color;
    };
    instance c_colored_quad;
    logic {
        instance.position += state.velocity * dt;
        instance.rotation += state.angular_velocity * dt;
        state.lifetime -= dt;
        let progress = clamp(
            1.0 - state.lifetime / max(state.initial_lifetime, 0.0001),
            0.0, 1.0);
        instance.size = mix(state.start_size, state.end_size, progress);
        instance.color = mix(state.start_color, state.end_color, progress);
        if (state.lifetime <= 0.0) { alive = false; }
    };
};


inline void emit_aura_particles(
        aura_emitter_state& emitter,
        const vec2& position,
        float radius,
        float dt_seconds,
        uint64_t stable_id) {
    emitter.carry += scale_particle_spawn_budget(
        180.0f * (dt_seconds / max(g_particle_tick_seconds, 0.000001f)));
    const uint32_t count = static_cast<uint32_t>(
        std::floor(max(emitter.carry, 0.0f)));
    emitter.carry -= static_cast<float>(count);
    for (uint32_t index = 0u; index < count; ++index) {
        uint64_t random = particle_hash(stable_id ^ particle_hash(g_particle_frame)
            ^ (static_cast<uint64_t>(index) << 32u) ^ 0x41555241ull);
        const float angle =
            (static_cast<float>(index) + particle_random_01(random))
            * (TPI / static_cast<float>(max(count, 1u)));
        const float value = particle_random_01(random);
        const float shaped = value * value;
        const vec2 direction{std::cos(angle), std::sin(angle)};
        const float duration = 0.18f + particle_random_01(random) * 0.14f;
        const float size = 0.08f + shaped * 0.08f;
        const vec2 start_size{size, size};
        const vec2 end_size{size * 0.15f, size * 0.15f};
        const vec4 start_color{
            0.5f - shaped * 0.3f, 0.2f + shaped * 0.8f,
            0.4f + shaped * 0.3f, 0.9f};
        const vec4 end_color{
            1.0f - shaped * 0.2f, 0.4f - shaped * 0.3f,
            0.1f + shaped * 0.2f, 0.0f};
        const float speed = particle_random_01(random) * 3.0f;
        particles::spawn<aura_particle>({
            direction * speed, particle_random_signed(random) * 2.0f,
            duration, duration, start_size, end_size, start_color, end_color
        }, {
            position + direction * max(radius, 0.0f),
            start_size, angle, start_color, 0.17f
        });
    }
}


$cr c_item_aura : c_item {
    float radius = 1.25f;
    int32 damage_per_tick = 1;

    r e_item_visual {
        ctx.name = "aura";
        ctx.icon = item_icon<t_item_aura>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "damages nearby enemies for "
                        << damage(self.damage_per_tick);
    };
    c e_item_inst_apply {
        ctx.target.set<c_inst_aura>({
            max(self.radius, 0.05f),
            max(self.damage_per_tick, 1)
        });
    };
};

$c e_update[-500](
    c_inst,
    const c_inst_source& source,
    c_inst_aura& aura,
    const c_rigid_body& body,
    exclude c_pending_destruction
) {
    const float radius = max(aura.radius, 0.0f);
    aura.damage_phase += 0.5f;
    if (aura.damage_phase < 1.0f) continue;
    aura.damage_phase -= 1.0f;
    const int32_t damage = max(aura.damage_per_tick, 0);
    if (radius <= 0.0f || damage <= 0) continue;
    for_each_spatial_candidate_in_radius(
            world, body.position, radius,
            [&](entity target) {
        if (!target || target.stable_id() == source.owner
                || target.stable_id() == e.stable_id()
                || !target.has<c_enemy>() || !target.has<c_health>()
                || !target.has<c_collider>())
            return true;
        const auto& collider = target.get<c_collider>();
        if ((collider.type_bits & collision_enemy) == 0u) return true;
        auto& health = target.get_mut<c_health>();
        health.current = max(health.current - damage, 0);
        return true;
    });
};

$cr c_inst_aura {
    float radius = 1.25f;
    int32 damage_per_tick = 1;
    float damage_phase = 0.0f;
};

$r e_update[-700](
    const c_inst_aura& aura,
    const c_presented_motion& presented
) {
    if (!presented.valid || !presented.visible) continue;
    const uint64_t stable_id = e.stable_id();
    auto* entry = g_aura_emitters.find(stable_id, g_particle_frame, true);
    auto* emitter = entry ? &entry->state : nullptr;
    if (!emitter) continue;
    emit_aura_particles(
        *emitter, presented.body.position,
        aura.radius, g_particle_dt_seconds, stable_id);
    g_aura_emitters.prune(g_particle_frame);
};
