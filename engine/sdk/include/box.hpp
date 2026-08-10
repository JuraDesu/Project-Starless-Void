#pragma once

#include "content_types.h"

struct box;

struct ibox {
    union {
        struct {
            int32 x;
            int32 y;
            int32 w;
            int32 h;
        };
        struct {
            ivec2 pos;
            ivec2 bounds;
        };
    };

    ibox(int32 x, int32 y, int32 w, int32 h)
        : x(x), y(y), w(w), h(h) {}
    ibox(ivec2 pos, ivec2 bounds) : pos(pos), bounds(bounds) {}
    ibox(const box& other);

    ivec2 center() const {
        return {x + w / 2, y + h / 2};
    }

    bool intersects(const ibox& other) const {
        return !(x + w <= other.x || other.x + other.w <= x
            || y + h <= other.y || other.y + other.h <= y);
    }

    bool intersects(const ivec2& point) const {
        return point.x >= x && point.x < x + w
            && point.y >= y && point.y < y + h;
    }
};

struct box {
    union {
        struct {
            float x;
            float y;
            float w;
            float h;
        };
        struct {
            vec2 pos;
            vec2 bounds;
        };
    };

    box(float x, float y, float w, float h) : x(x), y(y), w(w), h(h) {}
    box(vec2 pos, vec2 bounds) : pos(pos), bounds(bounds) {}
    box(const ibox& other)
        : x(static_cast<float>(other.x)), y(static_cast<float>(other.y)),
          w(static_cast<float>(other.w)), h(static_cast<float>(other.h)) {}

    vec2 center() const {
        return {x + w * 0.5f, y + h * 0.5f};
    }

    bool intersects(const box& other) const {
        return !(x + w <= other.x || other.x + other.w <= x
            || y + h <= other.y || other.y + other.h <= y);
    }

    bool intersects(const vec2& point) const {
        return point.x >= x && point.x < x + w
            && point.y >= y && point.y < y + h;
    }
};

inline ibox::ibox(const box& other)
    : x(static_cast<int32>(other.x)), y(static_cast<int32>(other.y)),
      w(static_cast<int32>(other.w)), h(static_cast<int32>(other.h)) {}
