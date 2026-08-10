#pragma once

#include "ecs.hpp"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <string>
#include <type_traits>
#include <vector>



enum class ui_role : std::uint8_t {
    normal,
    damage,
    heal,
    muted,
    heading,
};

enum class ui_alignment : std::uint8_t {
    left,
    center,
    right,
};

struct ui_panel_style {
    float padding{10.0f};
    float color[4]{0.035f, 0.045f, 0.075f, 0.94f};
};

struct ui_style {
    std::uint32_t font{};
    float scale{1.0f};
    float color[4]{1.0f, 1.0f, 1.0f, 1.0f};
    ui_role role{ui_role::normal};
};

struct ui_icon_record {
    EngineComponentId component{};
    std::uint32_t stride{};
    std::vector<std::uint8_t> bytes;
    float width_pixels{18.0f};
    float height_pixels{18.0f};
};

struct ui_token {
    enum class kind : std::uint8_t {
        text, icon, horizontal_space, vertical_space, newline
    } type{kind::text};
    ui_style style{};
    std::string text;
    ui_icon_record icon;
    float amount{};
    float reserved_width{};
};

template <typename Component>
ui_icon_record ui_icon(
        const Component& value,
        float width_pixels = 18.0f,
        float height_pixels = 18.0f) {
    static_assert(std::is_trivially_copyable_v<Component>);
    ui_icon_record result{
        component_traits<Component>::id,
        static_cast<std::uint32_t>(sizeof(Component)),
        {}, width_pixels, height_pixels};
    result.bytes.resize(sizeof(Component));
    std::memcpy(result.bytes.data(), &value, sizeof(Component));
    return result;
}

struct ui_styled_value {
    std::string text;
    ui_role role{};
    float reserved_width{};
};

inline ui_styled_value damage(int value, float reserve = 0.0f) {
    return {std::to_string(value), ui_role::damage, reserve};
}
inline ui_styled_value heal(int value, float reserve = 0.0f) {
    return {std::to_string(value), ui_role::heal, reserve};
}
inline ui_styled_value muted(std::string value) {
    return {std::move(value), ui_role::muted, 0.0f};
}
inline ui_styled_value styled(
        std::string value, ui_role role, float reserve = 0.0f) {
    return {std::move(value), role, reserve};
}
struct ui_spacer { float pixels; };
struct ui_vertical_spacer { float pixels; };
struct ui_newline {};

class ui_stream {
public:
    ui_stream& operator<<(const char* text) {
        return append_text(text ? text : "");
    }
    ui_stream& operator<<(const std::string& text) {
        return append_text(text);
    }
    ui_stream& operator<<(int value) {
        return append_text(std::to_string(value));
    }
    ui_stream& operator<<(unsigned value) {
        return append_text(std::to_string(value));
    }
    ui_stream& operator<<(float value) {
        std::string text = std::to_string(value);
        while (text.size() > 1 && text.back() == '0') text.pop_back();
        if (!text.empty() && text.back() == '.') text.pop_back();
        return append_text(text);
    }
    ui_stream& operator<<(const ui_styled_value& value) {
        ui_style next = style_;
        next.role = value.role;
        tokens_.push_back({
            ui_token::kind::text, next, value.text, {}, 0.0f,
            value.reserved_width});
        return *this;
    }
    ui_stream& operator<<(const ui_icon_record& icon) {
        ui_token token{};
        token.type = ui_token::kind::icon;
        token.style = style_;
        token.icon = icon;
        tokens_.push_back(std::move(token));
        return *this;
    }
    ui_stream& operator<<(ui_spacer value) {
        ui_token token{};
        token.type = ui_token::kind::horizontal_space;
        token.amount = value.pixels;
        tokens_.push_back(std::move(token));
        return *this;
    }
    ui_stream& operator<<(ui_vertical_spacer value) {
        ui_token token{};
        token.type = ui_token::kind::vertical_space;
        token.amount = value.pixels;
        tokens_.push_back(std::move(token));
        return *this;
    }
    ui_stream& operator<<(ui_newline) {
        ui_token token{};
        token.type = ui_token::kind::newline;
        tokens_.push_back(std::move(token));
        return *this;
    }

    ui_stream& font(std::uint32_t value) {
        style_.font = value;
        return *this;
    }
    ui_stream& scale(float value) {
        style_.scale = max(value, 0.05f);
        return *this;
    }
    ui_stream& color(float r, float g, float b, float a = 1.0f) {
        style_.color[0] = r; style_.color[1] = g;
        style_.color[2] = b; style_.color[3] = a;
        return *this;
    }
    ui_stream& role(ui_role value) {
        style_.role = value;
        return *this;
    }
    ui_stream& align(ui_alignment value) {
        alignment_ = value;
        return *this;
    }
    ui_stream& panel(ui_panel_style value) {
        panel_ = value;
        return *this;
    }
    ui_alignment alignment() const { return alignment_; }
    const ui_panel_style& panel_style() const { return panel_; }
    const std::vector<ui_token>& tokens() const { return tokens_; }
    bool empty() const { return tokens_.empty(); }
    void clear() { tokens_.clear(); }

private:
    ui_stream& append_text(const std::string& value) {
        if (!value.empty())
            tokens_.push_back({
                ui_token::kind::text, style_, value, {}, 0.0f, 0.0f});
        return *this;
    }

    ui_style style_{};
    ui_alignment alignment_{ui_alignment::left};
    ui_panel_style panel_{};
    std::vector<ui_token> tokens_;
};
