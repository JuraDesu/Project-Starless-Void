#include "event.hpp"

#include <algorithm>



template <typename Texture>
inline c_textured_sprite item_icon() {
    const auto& image = texture<Texture>();
    return {
        {}, texture_world_size(image, 20.0f), 0.0f,
        texture_uv(image), image.layer, 0.05f, 0
    };
}


$r e_item_visual {
    const char* name{};
    c_textured_sprite icon{};
    bool valid{};
};

$r e_item_hover {
    ui_stream* stream{};
};

$c e_item_inst_apply {
    entity target{};
    int32 damage_bonus{};
    int32 additional_hits{};
};

$c e_item_pickup {
    entity player{};
};


$cr c_item {
    require r e_item_visual;
    require r e_item_hover;
    optional c e_item_inst_apply;
    optional c e_item_pickup;
};

$cr c_ground_item {
};

$c c_player_inventory {
    uint8 count = 0;
    entity_id item_ids[10] = {};
};

$c c_player_weapon {
    int32 cooldown_ticks = 0;
    uint64 last_shoot_sequence = 0;
};

$cr p_ground_item {
    c_ground_item {};
    c_rigid_body {};
    c_aabb {{}, {0.25f, 0.25f}};
    c c_collider {};
};

$c e_update[200](
    const c_player& player,
    const c_rigid_body& player_body,
    const c_aabb& player_bounds,
    c_player_inventory& inventory
) {
    (void)player;
    if (inventory.count < 10u) {
        const vec2 center = player_body.position + player_bounds.offset;
        for_each_spatial_candidate_in_bounds(
                world, center - player_bounds.half_size,
                center + player_bounds.half_size,
                [&](entity item) {
            if (!item.has<c_ground_item>() || !item.has<c_item>()
                    || !item.has<c_rigid_body>() || !item.has<c_aabb>())
                return true;
            const auto& item_body = item.get<c_rigid_body>();
            const auto& item_bounds = item.get<c_aabb>();
            if (!aabb_overlap(
                    player_body.position, player_bounds,
                    item_body.position, item_bounds))
                return true;
            const uint64_t stable = item.stable_id();
            if (!stable) return true;
            e_item_pickup pickup{e};
            dispatch(context, item, pickup);
            inventory.item_ids[inventory.count++] = stable;
            item.remove<c_ground_item>();
            item.remove<c_rigid_body>();
            item.remove<c_aabb>();
            item.remove<c_collider>();
            return inventory.count < 10u;
        });
    }
};

$r e_update[-800](
    const c_item& item,
    const c_ground_item& ground,
    const c_rigid_body& body
) {
    (void)item;
    (void)ground;
    e_item_visual visual{};
    if (dispatch(context, e, visual) && visual.valid) {
        visual.icon.position = body.position;
        visual.icon.stable_id = e.stable_id();
        e.set<c_textured_sprite>(visual.icon);
    }
};

$r e_remove(const c_ground_item& item) {
    (void)item;
    e.remove<c_textured_sprite>();
};
