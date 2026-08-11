#include "ecs.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <map>
#include <unordered_set>
#include <vector>



inline constexpr uint32_t collision_friendly = 1u << 0u;
inline constexpr uint32_t collision_enemy = 1u << 1u;
inline constexpr uint32_t collision_tile = 1u << 2u;
inline constexpr int32_t chunk_size = 16;
inline constexpr uint32_t spatial_level_offsets[5] = {
    0u, 256u, 320u, 336u, 340u
};

struct SpatialChunk {
    std::array<std::vector<entity_id>, 341> cells;
    uint32_t member_count{};
};

inline std::map<int64_t, SpatialChunk> g_spatial_chunks;
inline uint32 g_spatial_generation{};

inline int32_t floor_div(int32_t value, int32_t divisor) {
    const int32_t quotient = value / divisor;
    const int32_t remainder = value % divisor;
    return quotient - (remainder < 0 ? 1 : 0);
}

inline int32_t positive_mod(int32_t value, int32_t divisor) {
    const int32_t result = value % divisor;
    return result < 0 ? result + divisor : result;
}

inline int64_t chunk_key(int32_t x, int32_t y) {
    return static_cast<int64_t>(
        (static_cast<uint64_t>(static_cast<uint32_t>(x)) << 32u)
        | static_cast<uint32_t>(y));
}

inline uint32_t spatial_level_for(const c_aabb& bounds) {
    const float diameter = 2.0f * max(
        bounds.half_size.x, bounds.half_size.y);
    if (diameter <= 1.0f) return 0u;
    if (diameter <= 2.0f) return 1u;
    if (diameter <= 4.0f) return 2u;
    if (diameter <= 8.0f) return 3u;
    return 4u;
}

inline void reset_spatial_if_needed() {
    const uint32 generation = uint32(component_traits<c_spatial_partition>::id >> 32u);
    if (g_spatial_generation == generation) return;
    g_spatial_chunks.clear();
    g_spatial_generation = generation;
}

inline bool aabb_overlap(
        const vec2& a_position, const c_aabb& a,
        const vec2& b_position, const c_aabb& b) {
    const vec2 delta =
        (a_position + a.offset) - (b_position + b.offset);
    const vec2 extent = a.half_size + b.half_size;
    return delta.x >= -extent.x && delta.x <= extent.x
        && delta.y >= -extent.y && delta.y <= extent.y;
}

inline bool sweep_expanded_aabb(
        const vec2& start, const vec2& end,
        const vec2& center, const vec2& half_size,
        float& toi, vec2& normal) {
    float enter = 0.0f;
    float leave = 1.0f;
    normal = {};
    const vec2 delta = end - start;
    const auto axis = [&](float origin, float movement,
                          float minimum, float maximum,
                          vec2 negative_normal,
                          vec2 positive_normal) {
        if (std::abs(movement) < 0.000001f)
            return origin >= minimum && origin <= maximum;
        float first = (minimum - origin) / movement;
        float second = (maximum - origin) / movement;
        vec2 first_normal = negative_normal;
        if (first > second) {
            std::swap(first, second);
            first_normal = positive_normal;
        }
        if (first > enter) {
            enter = first;
            normal = first_normal;
        }
        leave = min(leave, second);
        return enter <= leave;
    };
    if (!axis(start.x, delta.x, center.x - half_size.x,
              center.x + half_size.x, {-1.0f, 0.0f}, {1.0f, 0.0f})
            || !axis(start.y, delta.y, center.y - half_size.y,
              center.y + half_size.y, {0.0f, -1.0f}, {0.0f, 1.0f})
            || enter < 0.0f || enter > 1.0f) return false;
    toi = enter;
    return true;
}


$cr c_rigid_body {
    vec2 position;
    float rotation;
    vec2 velocity;
    float angular_velocity;
};

$c c_kinematic_motion {};

$c c_health {
    int32 current = 5;
    int32 max = 5;
};

$cr c_aabb {
    vec2 offset;
    vec2 half_size;
};

$c c_collider {
    uint32 mask;
    uint32 type_bits;
    bool detectable;
    bool collide_tilemap;
};

$c c_spatial_partition {
    ivec2 chunk;
    uint32 level;
    uint32 cell;
    entity_id stable_id;
    bool inserted = false;
};


inline void erase_spatial(c_spatial_partition& member) {
    if (!member.inserted) return;
    const auto found = g_spatial_chunks.find(
        chunk_key(member.chunk.x, member.chunk.y));
    if (found != g_spatial_chunks.end() && member.cell < 341u) {
        auto& ids = found->second.cells[member.cell];
        const size_t previous_size = ids.size();
        ids.erase(std::remove(ids.begin(), ids.end(), member.stable_id), ids.end());
        if (ids.size() != previous_size && found->second.member_count)
            --found->second.member_count;
        if (!found->second.member_count) g_spatial_chunks.erase(found);
    }
    member.inserted = false;
}

inline void refresh_spatial(
        entity_id stable_id,
        const c_rigid_body& body, const c_aabb& bounds,
        c_spatial_partition& member) {
    reset_spatial_if_needed();
    if (!stable_id) {
        erase_spatial(member);
        return;
    }
    const vec2 center = body.position + bounds.offset;
    const uint32_t level = spatial_level_for(bounds);
    const int32_t cell_size = 1 << level;
    const int32_t cells_per_chunk = chunk_size / cell_size;
    const int32_t global_x = static_cast<int32_t>(std::floor(center.x / cell_size));
    const int32_t global_y = static_cast<int32_t>(std::floor(center.y / cell_size));
    const ivec2 chunk{
        floor_div(global_x, cells_per_chunk),
        floor_div(global_y, cells_per_chunk)};
    const uint32_t local_x = static_cast<uint32_t>(
        positive_mod(global_x, cells_per_chunk));
    const uint32_t local_y = static_cast<uint32_t>(
        positive_mod(global_y, cells_per_chunk));
    const uint32_t cell = spatial_level_offsets[level]
        + local_y * static_cast<uint32_t>(cells_per_chunk) + local_x;
    if (member.inserted && member.stable_id == stable_id
            && member.chunk.x == chunk.x && member.chunk.y == chunk.y
            && member.level == level && member.cell == cell) return;
    erase_spatial(member);
    auto& target = g_spatial_chunks[chunk_key(chunk.x, chunk.y)];
    auto& ids = target.cells[cell];
    const size_t previous_size = ids.size();
    ids.push_back(stable_id);
    std::sort(ids.begin(), ids.end());
    ids.erase(std::unique(ids.begin(), ids.end()), ids.end());
    if (ids.size() != previous_size) ++target.member_count;
    member = {chunk, level, cell, stable_id, true};
}

template <typename Callback>
inline bool for_each_spatial_candidate_in_bounds(
        const World& world, vec2 minimum, vec2 maximum,
        Callback&& callback) {
    reset_spatial_if_needed();
    std::vector<entity_id> candidates;
    for (uint32_t level = 0; level < 5u; ++level) {
        const int32_t cell_size = 1 << level;
        const int32_t cells_per_chunk = chunk_size / cell_size;
        const int32_t min_x =
            static_cast<int32_t>(std::floor(minimum.x / cell_size)) - 1;
        const int32_t min_y =
            static_cast<int32_t>(std::floor(minimum.y / cell_size)) - 1;
        const int32_t max_x =
            static_cast<int32_t>(std::floor(maximum.x / cell_size)) + 1;
        const int32_t max_y =
            static_cast<int32_t>(std::floor(maximum.y / cell_size)) + 1;
        for (int32_t y = min_y; y <= max_y; ++y) {
            for (int32_t x = min_x; x <= max_x; ++x) {
                const int32_t chunk_x = floor_div(x, cells_per_chunk);
                const int32_t chunk_y = floor_div(y, cells_per_chunk);
                const auto chunk = g_spatial_chunks.find(chunk_key(chunk_x, chunk_y));
                if (chunk == g_spatial_chunks.end()) continue;
                const uint32_t local_x = static_cast<uint32_t>(positive_mod(x, cells_per_chunk));
                const uint32_t local_y = static_cast<uint32_t>(positive_mod(y, cells_per_chunk));
                const uint32_t cell = spatial_level_offsets[level]
                    + local_y * static_cast<uint32_t>(cells_per_chunk) + local_x;
                candidates.insert(candidates.end(),
                    chunk->second.cells[cell].begin(),
                    chunk->second.cells[cell].end());
            }
        }
    }
    std::sort(candidates.begin(), candidates.end());
    candidates.erase(std::unique(candidates.begin(), candidates.end()), candidates.end());
    for (entity_id stable_id : candidates) {
        entity candidate = world.from_stable_id(stable_id);
        if (candidate && !callback(candidate)) return false;
    }
    return true;
}

template <typename Callback>
inline bool for_each_spatial_candidate_in_radius(
        const World& world, vec2 center, float radius,
        Callback&& callback) {
    const vec2 extent{radius, radius};
    return for_each_spatial_candidate_in_bounds(
        world, center - extent, center + extent,
        [&](entity candidate) {
            const auto* body = candidate.try_get<c_rigid_body>();
            const auto* bounds = candidate.try_get<c_aabb>();
            if (!body || !bounds) return true;
            const vec2 candidate_center = body->position + bounds->offset;
            const float reach = radius + length(bounds->half_size);
            return distance(center, candidate_center) <= reach
                ? callback(candidate) : true;
        });
}


$c e_add(const c_collider& collider) {
    (void)collider;
    if (!e.has<c_spatial_partition>()) e.add<c_spatial_partition>();
};

$c e_remove(c_spatial_partition& member) {
    erase_spatial(member);
};

$c e_remove(
    const c_collider& collider,
    c_spatial_partition& member
) {
    (void)collider;
    erase_spatial(member);
};

$c e_update[0](
    c_rigid_body& body,
    const c_kinematic_motion& kinematic,
    exclude c_pending_destruction
) {
    (void)kinematic;
    body.position += body.velocity;
    body.rotation += body.angular_velocity;
};

$c e_update[100](
    const c_rigid_body& body,
    const c_aabb& bounds,
    const c_collider& collider,
    c_spatial_partition& spatial
) {
    (void)collider;
    refresh_spatial(e.stable_id(), body, bounds, spatial);
};
