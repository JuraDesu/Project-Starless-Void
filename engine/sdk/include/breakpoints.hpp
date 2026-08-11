#pragma once

#include "content_types.h"

#include <cmath>
#include <cstdint>

struct breakpoint_time {
    uint64_t tick = 0;
    float alpha = 0.0f;
    uint32_t sequence = 0;
};

struct breakpoint_cursor {
    bool initialized = false;
    breakpoint_time consumed{};
};

inline bool operator<(const breakpoint_time& left,
        const breakpoint_time& right) {
    if (left.tick != right.tick) return left.tick < right.tick;
    if (std::abs(left.alpha - right.alpha) > 0.000001f)
        return left.alpha < right.alpha;
    return left.sequence < right.sequence;
}

inline bool operator<=(const breakpoint_time& left,
        const breakpoint_time& right) {
    return !(right < left);
}

inline double breakpoint_value(const breakpoint_time& value) {
    return static_cast<double>(value.tick > 0u ? value.tick - 1u : 0u)
        + static_cast<double>(clamp(value.alpha, 0.0f, 1.0f));
}

inline thread_local const breakpoint_time* g_active_breakpoint = nullptr;

class active_breakpoint_scope {
public:
    explicit active_breakpoint_scope(const breakpoint_time& value)
        : previous_(g_active_breakpoint) {
        g_active_breakpoint = &value;
    }
    ~active_breakpoint_scope() { g_active_breakpoint = previous_; }
    active_breakpoint_scope(const active_breakpoint_scope&) = delete;
    active_breakpoint_scope& operator=(const active_breakpoint_scope&) = delete;
private:
    const breakpoint_time* previous_{};
};

inline const breakpoint_time* active_breakpoint() {
    return g_active_breakpoint;
}

template <typename Record>
inline bool breakpoint_insert(
        Record* records, uint32_t& count, uint32_t capacity,
        uint32_t& next_sequence, const Record& value) {
    if (!records || count >= capacity) return false;
    Record copy = value;
    copy.time.sequence = next_sequence++;
    uint32_t target = count++;
    while (target > 0 && copy.time < records[target - 1].time) {
        records[target] = records[target - 1];
        --target;
    }
    records[target] = copy;
    return true;
}

template <typename Record, typename Callback>
inline uint32_t run_crossed_breakpoints(
        const Record* records, uint32_t count,
        breakpoint_cursor& cursor, const breakpoint_time& through,
        Callback&& callback) {
    if (!records) return 0;
    uint32_t ran = 0;
    for (uint32_t index = 0; index < count; ++index) {
        const Record& record = records[index];
        if (through < record.time
                || (cursor.initialized && record.time <= cursor.consumed))
            continue;
        {
            active_breakpoint_scope scope(record.time);
            callback(record);
        }
        cursor.initialized = true;
        cursor.consumed = record.time;
        ++ran;
    }
    return ran;
}

template <typename Record>
inline void prune_breakpoints_before(
        Record* records, uint32_t& count,
        const breakpoint_cursor& cursor) {
    if (!records || !cursor.initialized) return;
    uint32_t first = 0;
    while (first < count && records[first].time <= cursor.consumed)
        ++first;
    for (uint32_t index = first; index < count; ++index)
        records[index - first] = records[index];
    count -= first;
}
