#pragma once

#include <initializer_list>

#include "content_api.h"
#include "callback.hpp"


enum class Key : uint32_t {
    A = KEY_A, B = KEY_B, C = KEY_C,
    D = KEY_D, E = KEY_E, F = KEY_F,
    G = KEY_G, H = KEY_H, I = KEY_I,
    J = KEY_J, K = KEY_K, L = KEY_L,
    M = KEY_M, N = KEY_N, O = KEY_O,
    P = KEY_P, Q = KEY_Q, R = KEY_R,
    S = KEY_S, T = KEY_T, U = KEY_U,
    V = KEY_V, W = KEY_W, X = KEY_X,
    Y = KEY_Y, Z = KEY_Z,
    Digit1 = KEY_1, Digit2 = KEY_2,
    Digit3 = KEY_3, Digit4 = KEY_4,
    Digit5 = KEY_5, Digit6 = KEY_6,
    Digit7 = KEY_7, Digit8 = KEY_8,
    Digit9 = KEY_9, Digit0 = KEY_0,
    Enter = KEY_ENTER, Escape = KEY_ESCAPE,
    Backspace = KEY_BACKSPACE, Tab = KEY_TAB,
    Space = KEY_SPACE, Minus = KEY_MINUS,
    Equal = KEY_EQUAL, LeftBracket = KEY_LEFT_BRACKET,
    RightBracket = KEY_RIGHT_BRACKET,
    Backslash = KEY_BACKSLASH, Semicolon = KEY_SEMICOLON,
    Apostrophe = KEY_APOSTROPHE, Grave = KEY_GRAVE,
    Comma = KEY_COMMA, Period = KEY_PERIOD,
    Slash = KEY_SLASH, CapsLock = KEY_CAPS_LOCK,
    F1 = KEY_F1, F2 = KEY_F2, F3 = KEY_F3,
    F4 = KEY_F4, F5 = KEY_F5, F6 = KEY_F6,
    F7 = KEY_F7, F8 = KEY_F8, F9 = KEY_F9,
    F10 = KEY_F10, F11 = KEY_F11, F12 = KEY_F12,
    Insert = KEY_INSERT, Home = KEY_HOME,
    PageUp = KEY_PAGE_UP, Delete = KEY_DELETE,
    End = KEY_END, PageDown = KEY_PAGE_DOWN,
    Right = KEY_RIGHT, Left = KEY_LEFT,
    Down = KEY_DOWN, Up = KEY_UP,
    NumpadDivide = KEY_NUMPAD_DIVIDE,
    NumpadMultiply = KEY_NUMPAD_MULTIPLY,
    NumpadSubtract = KEY_NUMPAD_SUBTRACT,
    NumpadAdd = KEY_NUMPAD_ADD, NumpadEnter = KEY_NUMPAD_ENTER,
    Numpad1 = KEY_NUMPAD_1, Numpad2 = KEY_NUMPAD_2,
    Numpad3 = KEY_NUMPAD_3, Numpad4 = KEY_NUMPAD_4,
    Numpad5 = KEY_NUMPAD_5, Numpad6 = KEY_NUMPAD_6,
    Numpad7 = KEY_NUMPAD_7, Numpad8 = KEY_NUMPAD_8,
    Numpad9 = KEY_NUMPAD_9, Numpad0 = KEY_NUMPAD_0,
    NumpadDecimal = KEY_NUMPAD_DECIMAL,
    NonUsBackslash = KEY_NON_US_BACKSLASH,
    LeftControl = KEY_LEFT_CONTROL, LeftShift = KEY_LEFT_SHIFT,
    LeftAlt = KEY_LEFT_ALT, LeftMeta = KEY_LEFT_META,
    RightControl = KEY_RIGHT_CONTROL,
    RightShift = KEY_RIGHT_SHIFT, RightAlt = KEY_RIGHT_ALT,
    RightMeta = KEY_RIGHT_META,
};

struct ButtonState {
    bool valid{};
    bool down{};
    bool pressed{};
    bool released{};
};

struct CursorState {
    bool valid{};
    float world_x{};
    float world_y{};
    ButtonState primary{};
};

struct WheelState {
    bool valid{};
    float y{};
};

class InputRegistry {
public:
    explicit InputRegistry(EngineContentSharedBlock* shared) : shared_(shared) {}

    bool button(const char* name, std::initializer_list<Key> keys) {
        if (!ok_ || !shared_ || !shared_->engine
                || !shared_->engine->append_input_action
                || keys.size() > MAX_INPUT_KEYS) {
            ok_ = false;
            return false;
        }
        EngineInputActionDesc desc{};
        desc.header = {sizeof(desc)};
        desc.name = name;
        desc.key_count = static_cast<uint32_t>(keys.size());
        uint32_t index = 0;
        for (Key key : keys) desc.keys[index++] = static_cast<uint32_t>(key);
        ok_ = shared_->engine->append_input_action(
            shared_->engine_context, &desc) != 0;
        return ok_;
    }

    int32_t finish() const { return ok_ ? 1 : 0; }

private:
    EngineContentSharedBlock* shared_{};
    bool ok_{true};
};

inline ButtonState input_button(const char* name) {
    const auto* context = active_callback_context();
    EngineInputButtonState state{};
    const bool valid = context && context->engine && context->engine->input_button
        && context->engine->input_button(context->engine_context, name, &state);
    return {valid, state.down != 0, state.pressed != 0, state.released != 0};
}

inline CursorState input_cursor() {
    const auto* context = active_callback_context();
    EngineCursorState state{};
    state.header = {sizeof(EngineCursorState)};
    const bool queried = context && context->engine && context->engine->input_cursor
        && context->engine->input_cursor(context->engine_context, &state);
    return {
        queried && state.valid != 0,
        state.world_x,
        state.world_y,
        {
            queried,
            state.primary.down != 0,
            state.primary.pressed != 0,
            state.primary.released != 0
        }
    };
}

inline WheelState input_wheel() {
    const auto* context = active_callback_context();
    EngineWheelState state{};
    state.header = {sizeof(EngineWheelState)};
    const bool queried = context && context->engine && context->engine->input_wheel
        && context->engine->input_wheel(context->engine_context, &state);
    return {queried && state.valid != 0, state.y};
}
