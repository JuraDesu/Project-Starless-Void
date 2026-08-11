#ifndef CONTENT_TYPES_H
#define CONTENT_TYPES_H

#include <stdint.h>

typedef struct EngineVec2 { float x, y; } EngineVec2;
typedef struct EngineVec3 { float x, y, z; } EngineVec3;
typedef struct EngineVec4 { float x, y, z, w; } EngineVec4;
typedef struct EngineIVec2 { int32_t x, y; } EngineIVec2;
typedef struct EngineIVec3 { int32_t x, y, z; } EngineIVec3;
typedef struct EngineIVec4 { int32_t x, y, z, w; } EngineIVec4;
typedef struct EngineUVec2 { uint32_t x, y; } EngineUVec2;
typedef struct EngineUVec3 { uint32_t x, y, z; } EngineUVec3;
typedef struct EngineUVec4 { uint32_t x, y, z, w; } EngineUVec4;

#if defined(__cplusplus)
#include <cmath>
#include <cstdlib>
#include <type_traits>
#include <glm/glm.hpp>
#include <glm/gtc/constants.hpp>

using uint8 = uint8_t;
using int8 = int8_t;
using uint16 = uint16_t;
using int16 = int16_t;
using int32 = int32_t;
using uint32 = uint32_t;
using uint64 = uint64_t;
using int64 = int64_t;
using entity_id = uint64_t;
using namespace glm;
using vec2 = glm::vec2;
using vec3 = glm::vec3;
using vec4 = glm::vec4;
using ivec2 = glm::ivec2;
using ivec3 = glm::ivec3;
using ivec4 = glm::ivec4;
using uvec2 = glm::uvec2;
using uvec3 = glm::uvec3;
using uvec4 = glm::uvec4;

static_assert(sizeof(vec2) == sizeof(EngineVec2));
static_assert(sizeof(vec3) == sizeof(EngineVec3));
static_assert(sizeof(vec4) == sizeof(EngineVec4));
static_assert(sizeof(int) == 4,
    "content requires the 32-bit WebAssembly int ABI");
static_assert(std::is_standard_layout_v<vec2> && std::is_trivially_copyable_v<vec2>);
static_assert(std::is_standard_layout_v<vec3> && std::is_trivially_copyable_v<vec3>);
static_assert(std::is_standard_layout_v<vec4> && std::is_trivially_copyable_v<vec4>);

inline constexpr float PI = glm::pi<float>();
inline constexpr float TPI = glm::two_pi<float>();
inline constexpr float HPI = glm::half_pi<float>();
inline float angle_difference(float a, float b) {
    float d = std::fmod(b - a + PI, TPI);
    if (d < 0.0f) d += TPI;
    return d - PI;
}
inline vec2 angle_to_vec(float angle) { return {std::cos(angle), std::sin(angle)}; }
inline float vec_to_angle(vec2 value) { return std::atan2(value.y, value.x); }

inline float frand() {
    return static_cast<float>(std::rand()) /
        static_cast<float>(RAND_MAX);
}

inline float sfrand() {
    return frand() * 2.0f - 1.0f;
}
#endif

#endif
