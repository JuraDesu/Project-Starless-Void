#include "event.hpp"
#include "render.hpp"
#include "view.hpp"
#include "core/ui_stream.hpp"

#include "content_fonts.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>


$r c_ui_glyph {
    vec2 position;
    vec2 size;
    vec4 uv_rect;
    vec4 color;
    uint32 font_index;
    float depth;

    shader {
        mesh quad;
        texture karowi = font_karowi;
        texture quantix = font_quantix;
        texture sipper = font_sipper;
        blend alpha;
        order 1000;
        logic {
            bridge {
                uv: vec2f,
                color: vec4f,
                font_index: u32,
            };
            vertex {
                out.position = projection * vec4f(
                    position + local_position * size, depth, 1.0);
                out.uv = uv_rect.xy + local_uv * uv_rect.zw;
                out.color = color;
                out.font_index = font_index;
            }
            fragment {
                let karowi_sample = sample_karowi(in.uv);
                let quantix_sample = sample_quantix(in.uv);
                let sipper_sample = sample_sipper(in.uv);
                var sample = select(
                    karowi_sample, quantix_sample,
                    in.font_index == 1u);
                sample = select(
                    sample, sipper_sample,
                    in.font_index == 2u);
                let distance = max(min(sample.r, sample.g),
                    min(max(sample.r, sample.g), sample.b)) - 0.5;
                let alpha = clamp(
                    distance / max(fwidth(distance), 0.0001) + 0.5,
                    0.0, 1.0);
                if (alpha < 0.01) { discard; }
                out.color = vec4f(in.color.rgb, in.color.a * alpha);
            }
        };
    };
};


struct ui_measurement {
    float width{};
    float height{};
};

inline vec4 role_color(const ui_style& style) {
    vec4 result{
        style.color[0], style.color[1],
        style.color[2], style.color[3]};
    switch (style.role) {
        case ui_role::damage: result = {1.0f, 0.35f, 0.25f, result.w}; break;
        case ui_role::heal: result = {0.35f, 1.0f, 0.45f, result.w}; break;
        case ui_role::muted: result = {0.62f, 0.66f, 0.72f, result.w}; break;
        case ui_role::heading: result = {1.0f, 0.88f, 0.45f, result.w}; break;
        default: break;
    }
    return result;
}

inline const GeneratedFontInfo& ui_font(uint32 id) {
    return GENERATED_FONTS[
        min<uint32>(id, GENERATED_FONT_COUNT - 1u)];
}

inline ui_measurement measure_ui_stream(
        const ui_stream& stream, float base_pixels = 18.0f) {
    float line_width = 0.0f;
    float maximum_width = 0.0f;
    float height = base_pixels;
    float line_height = base_pixels;
    for (const ui_token& token : stream.tokens()) {
        if (token.type == ui_token::kind::newline) {
            maximum_width = max(maximum_width, line_width);
            line_width = 0.0f;
            height += line_height;
            line_height = base_pixels;
        } else if (token.type == ui_token::kind::horizontal_space) {
            line_width += token.amount;
        } else if (token.type == ui_token::kind::vertical_space) {
            height += token.amount;
        } else if (token.type == ui_token::kind::icon) {
            line_width += token.icon.width_pixels;
            line_height = max(line_height, token.icon.height_pixels);
        } else {
            const GeneratedFontInfo& font = ui_font(token.style.font);
            const float pixels = base_pixels * token.style.scale;
            float width = 0.0f;
            for (unsigned char character : token.text) {
                if (character < GENERATED_FONT_FIRST_CODEPOINT
                        || character > GENERATED_FONT_LAST_CODEPOINT)
                    continue;
                width += font.glyphs[
                    character - GENERATED_FONT_FIRST_CODEPOINT].advance
                    * pixels;
            }
            line_width += max(width, token.reserved_width);
            line_height = max(
                line_height, font.line_height * pixels);
        }
    }
    maximum_width = max(maximum_width, line_width);
    return {maximum_width, height};
}

inline void draw_glyph(
        const GeneratedFontInfo& font,
        const GeneratedFontGlyph& glyph,
        float x, float baseline_y, float pixels,
        const ViewState& view, vec4 color) {
    const float world_per_pixel = view.world_per_pixel();
    const float left = x + glyph.plane_bounds.x * pixels;
    const float top = baseline_y - glyph.plane_bounds.y * pixels
        - glyph.plane_bounds.w * pixels;
    c_ui_glyph instance{
        {
            view.camera_x
                + (left + glyph.plane_bounds.z * pixels * 0.5f)
                    * world_per_pixel,
            view.camera_y
                - (top + glyph.plane_bounds.w * pixels * 0.5f)
                    * world_per_pixel
        },
        {
            glyph.plane_bounds.z * pixels * world_per_pixel,
            glyph.plane_bounds.w * pixels * world_per_pixel
        },
        {
            glyph.atlas_bounds.x / font.atlas_width,
            glyph.atlas_bounds.y / font.atlas_height,
            glyph.atlas_bounds.z / font.atlas_width,
            glyph.atlas_bounds.w / font.atlas_height
        },
        color, font.id, 0.0f
    };
    draw(instance, 1000);
}

inline void render_ui_stream(
        const ui_stream& stream,
        const ViewState& view,
        float origin_x_pixels,
        float origin_y_pixels,
        float base_pixels = 18.0f) {
    float x = origin_x_pixels - view.canvas_width * 0.5f;
    float y = origin_y_pixels - view.canvas_height * 0.5f;
    const float line_start = x;
    float line_height = base_pixels;
    for (const ui_token& token : stream.tokens()) {
        if (token.type == ui_token::kind::newline) {
            x = line_start;
            y += line_height;
            line_height = base_pixels;
            continue;
        }
        if (token.type == ui_token::kind::horizontal_space) {
            x += token.amount;
            continue;
        }
        if (token.type == ui_token::kind::vertical_space) {
            y += token.amount;
            continue;
        }
        if (token.type == ui_token::kind::icon) {
            if (token.icon.component && !token.icon.bytes.empty())
                draw_instances(
                    token.icon.component,
                    token.icon.bytes.data(), token.icon.stride, 1u, 950);
            x += token.icon.width_pixels;
            continue;
        }
        const GeneratedFontInfo& font = ui_font(token.style.font);
        const float pixels = base_pixels * token.style.scale;
        const vec4 color = role_color(token.style);
        const float start = x;
        for (unsigned char character : token.text) {
            if (character < GENERATED_FONT_FIRST_CODEPOINT
                    || character > GENERATED_FONT_LAST_CODEPOINT)
                continue;
            const GeneratedFontGlyph& glyph = font.glyphs[
                character - GENERATED_FONT_FIRST_CODEPOINT];
            if (glyph.present) {
                    draw_glyph(
                        font, glyph, x, y + pixels,
                    pixels, view, color);
            }
            x += glyph.advance * pixels;
        }
        x = max(x, start + token.reserved_width);
        line_height = max(line_height, font.line_height * pixels);
    }
}

inline vec2 pixel_to_world(
        const ViewState& view, float x, float y) {
    const float wpp = view.world_per_pixel();
    return {
        view.camera_x + (x - view.canvas_width * 0.5f) * wpp,
        view.camera_y + (view.canvas_height * 0.5f - y) * wpp
    };
}

inline void draw_item_tooltip(
        entity item,
        const ViewState& view) {
    e_item_visual visual{};
    ui_stream description;
    e_item_hover hover{&description};
    if (!dispatch(item, visual)
            || !visual.valid || !visual.name
            || !dispatch(item, hover))
        return;

    ui_stream content;
    content.font(fonts::sipper).role(ui_role::heading)
        << visual.name << ui_newline{};
    content.font(fonts::quantix).role(ui_role::normal);
    for (const ui_token& token : description.tokens()) {
        // Preserve the full styled stream without exposing renderer details.
        if (token.type == ui_token::kind::text)
            content << styled(token.text, token.style.role, token.reserved_width);
        else if (token.type == ui_token::kind::newline)
            content << ui_newline{};
        else if (token.type == ui_token::kind::horizontal_space)
            content << ui_spacer{token.amount};
        else if (token.type == ui_token::kind::vertical_space)
            content << ui_vertical_spacer{token.amount};
        else if (token.type == ui_token::kind::icon)
            content << token.icon;
    }
    content << ui_newline{};
    content.font(fonts::karowi).role(ui_role::muted)
        << "move over to collect";

    constexpr float padding = 10.0f;
    constexpr float icon_pixels = 32.0f;
    ui_measurement measured = measure_ui_stream(content);
    const float panel_width =
        padding * 3.0f + icon_pixels + measured.width;
    const float panel_height =
        max(measured.height, icon_pixels) + padding * 2.0f;
    float panel_x = view.cursor_x + 16.0f;
    float panel_y = view.cursor_y + 16.0f;
    panel_x = clamp(
        panel_x, 0.0f, max(0.0f, view.canvas_width - panel_width));
    panel_y = clamp(
        panel_y, 0.0f, max(0.0f, view.canvas_height - panel_height));
    const vec2 panel_center = pixel_to_world(
        view, panel_x + panel_width * 0.5f,
        panel_y + panel_height * 0.5f);
    draw<c_colored_quad>({
        panel_center,
        {panel_width * view.world_per_pixel(),
         panel_height * view.world_per_pixel()},
        0.0f, {0.035f, 0.045f, 0.075f, 0.94f}, 0.0f
    }, 900);
    const vec2 icon_center = pixel_to_world(
        view, panel_x + padding + icon_pixels * 0.5f,
        panel_y + padding + icon_pixels * 0.5f);
    c_textured_sprite icon = visual.icon;
    icon.position = icon_center;
    icon.size = {
        icon_pixels * view.world_per_pixel(),
        icon_pixels * view.world_per_pixel()};
    icon.rotation = 0.0f;
    icon.depth = 0.0f;
    draw(icon, 950);
    render_ui_stream(
        content, view,
        panel_x + padding * 2.0f + icon_pixels,
        panel_y + padding);
}


$r g_update[1000] {
    const auto view = view_state();
    const auto cursor = input_cursor();
    if (view && view.focused
            && view.cursor_valid && cursor.valid) {
        entity hovered{};
        float nearest = 1.0e30f;
        const vec2 cursor_world{cursor.world_x, cursor.world_y};
        for_each_spatial_candidate_in_bounds(
                world, cursor_world, cursor_world,
                [&](entity candidate) {
        if (!candidate.has<c_ground_item>() || !candidate.has<c_item>()
                || !candidate.has<c_rigid_body>() || !candidate.has<c_aabb>())
            return true;
        const auto& body = candidate.get<c_rigid_body>();
        const auto& bounds = candidate.get<c_aabb>();
        const float center_x = body.position.x + bounds.offset.x;
        const float center_y = body.position.y + bounds.offset.y;
        if (cursor.world_x < center_x - bounds.half_size.x
                || cursor.world_x > center_x + bounds.half_size.x
                || cursor.world_y < center_y - bounds.half_size.y
                || cursor.world_y > center_y + bounds.half_size.y)
            return true;
        const float dx = cursor.world_x - center_x;
        const float dy = cursor.world_y - center_y;
        const float distance = dx * dx + dy * dy;
        if (distance < nearest
                || (distance == nearest
                    && (!hovered
                        || candidate.stable_id() < hovered.stable_id()))) {
            nearest = distance;
            hovered = candidate;
        }
        return true;
        });
        if (hovered)
            draw_item_tooltip(hovered, view);
    }
};
