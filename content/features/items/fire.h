struct fire_emitter_state { float carry{}; };
inline particle_emitter_pool<fire_emitter_state> g_fire_emitters{};

$cr c_item_fire : c_item {
    r e_item_visual {
        ctx.name = "fire";
        ctx.icon = item_icon<t_item_fire>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "burns targets for "
                        << damage(4) << " damage over time";
    };
    c e_item_inst_apply {
        ctx.target.add<c_inst_debuff_burning>();
    };
};

$c e_update[-500](c_effect_burning& burning, c_health& health) {
    --burning.ticks_remaining;
    burning.pending_damage += 0.1f;
    const int32_t whole = static_cast<int32_t>(
        std::floor(burning.pending_damage));
    if (whole > 0) {
        burning.pending_damage -= static_cast<float>(whole);
        health.current = max(health.current - whole, 0);
    }
    if (burning.ticks_remaining <= 0) e.remove<c_effect_burning>();
};

$c e_hit(
    c_inst_debuff_burning,
    c_inst_damage,
    target: c_burnable
) {
    auto* effect = target_entity.try_get_mut<c_effect_burning>();
    if (effect) effect->ticks_remaining = 40;
    else target_entity.set<c_effect_burning>({40, 0.0f});
};

#include "render.hpp"


$compute burning_particle {
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
    instance c_color;
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


inline void emit_burning_particles(
        fire_emitter_state& emitter,
        const vec2& position,
        float dt_seconds,
        uint64_t stable_id) {
    emitter.carry += scale_particle_spawn_budget(30.0f * dt_seconds);
    const uint32_t count = static_cast<uint32_t>(
        std::floor(max(emitter.carry, 0.0f)));
    emitter.carry -= static_cast<float>(count);
    for (uint32_t index = 0u; index < count; ++index) {
        uint64_t random = particle_hash(stable_id ^ particle_hash(g_particle_frame)
            ^ (static_cast<uint64_t>(index) << 32u) ^ 0x46495245ull);
        const float angle = particle_random_01(random) * TPI;
        const float speed =
            (0.05f + particle_random_01(random) * 0.10f) * 30.0f;
        const float duration = 0.15f + particle_random_01(random) * 0.15f;
        const vec2 start_size{0.30f, 0.30f};
        const vec2 end_size{0.01f, 0.01f};
        const vec4 start_color{1.0f, 1.0f, 0.0f, 1.0f};
        const vec4 end_color{1.0f, 0.0f, 0.0f, 0.0f};
        particles::spawn<burning_particle>({
            {std::cos(angle) * speed, std::sin(angle) * speed},
            particle_random_signed(random) * 4.0f,
            duration, duration, start_size, end_size, start_color, end_color
        }, {position, start_size, angle, start_color, 0.2f});
    }
}


$c c_inst_debuff_burning {};
$c c_burnable {};
$cr c_effect_burning {
    int32 ticks_remaining = 40;
    float pending_damage = 0.0f;
};

$r e_update[-700](
    c_effect_burning,
    const c_rigid_body& body
) {
    const uint64_t stable_id = e.stable_id();
    auto* entry = g_fire_emitters.find(stable_id, g_particle_frame, true);
    auto* emitter = entry ? &entry->state : nullptr;
    if (!emitter) continue;
    vec2 position = body.position;
    if (const auto* presented = e.try_get<c_presented_motion>()) {
        if (!presented->valid || !presented->visible) continue;
        position = presented->body.position;
    } else if (const auto* sprite = e.try_get<c_texture>()) {
        position = sprite->position;
    }
    emit_burning_particles(
        *emitter, position, g_particle_dt_seconds, stable_id);
    g_fire_emitters.prune(g_particle_frame);
};
