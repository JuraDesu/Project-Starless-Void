#pragma once

#include "content_types.h"
#include "content_api.h"
#include "ecs.hpp"
#include "event.hpp"
#include "audio.hpp"

#include <cstddef>
#include <cstdint>
#include <cmath>
#include <functional>
#include <string>
#include <type_traits>
#include <utility>


class AssetRegistry {
public:
    explicit AssetRegistry(EngineContentSharedBlock* shared) : shared_(shared) {}

    void audio_distance_scale(float value) {
        if (!ok_ || !std::isfinite(value) || value < 0.0f) {
            ok_ = false;
            return;
        }
        content_audio_distance_scale = value;
    }

    void texture(
            const char* name,
            const char* path,
            std::uint32_t filter = FILTER_NEAREST,
            std::uint32_t address = ADDRESS_CLAMP) {
        if (!ok_ || !shared_ || !shared_->engine
                || !shared_->engine->append_texture) {
            ok_ = false;
            return;
        }
        EngineTextureDesc desc{};
        desc.header = {sizeof(desc)};
        desc.name = name;
        desc.path = path;
        desc.filter = filter;
        desc.address = address;
        ok_ = shared_->engine->append_texture(
            shared_->engine_context, &desc) != 0;
    }

    void atlas(
            const char* name,
            const char* source_aseprite,
            std::uint32_t filter = FILTER_NEAREST,
            std::uint32_t address = ADDRESS_CLAMP) {
        (void)source_aseprite;
        std::string runtime_path =
            std::string("assets/generated/atlases/") + name + ".png";
        texture(name, runtime_path.c_str(), filter, address);
    }

    void font(
            const char* name,
            const char* source_ttf,
            std::uint32_t size = 32u,
            std::uint32_t pxrange = 4u) {
        (void)source_ttf;
        (void)size;
        (void)pxrange;
        std::string texture_name = std::string("font_") + name;
        std::string runtime_path =
            std::string("assets/generated/fonts/") + name + "__none.png";
        texture(texture_name.c_str(), runtime_path.c_str(),
            FILTER_LINEAR, ADDRESS_CLAMP);
    }

    void audio(
            const char* name,
            const char* path,
            EngineAudioId& result) {
        if (!ok_ || !shared_ || !shared_->engine
                || !shared_->engine->append_audio) {
            ok_ = false;
            return;
        }
        EngineAudioDesc desc{};
        desc.header = {sizeof(desc)};
        desc.name = name;
        desc.path = path;
        ok_ = shared_->engine->append_audio(
            shared_->engine_context, &desc, &result) != 0;
    }

    template <std::size_t VertexCount, std::size_t IndexCount>
    void mesh(
            const char* name,
            const vec2 (&vertices)[VertexCount],
            const std::uint16_t (&indices)[IndexCount]) {
        static_assert(VertexCount > 0 && VertexCount <= 65535u);
        static_assert(IndexCount > 0);
        static_assert(sizeof(vec2) == sizeof(EngineMeshVertex));
        static_assert(alignof(vec2) == alignof(EngineMeshVertex));
        if (!ok_ || !shared_ || !shared_->engine
                || !shared_->engine->append_mesh) {
            ok_ = false;
            return;
        }
        EngineMeshDesc desc{};
        desc.header = {sizeof(desc)};
        desc.name = name;
        desc.vertices =
            reinterpret_cast<const EngineMeshVertex*>(vertices);
        desc.vertex_count = static_cast<std::uint32_t>(VertexCount);
        desc.indices = indices;
        desc.index_count = static_cast<std::uint32_t>(IndexCount);
        ok_ = shared_->engine->append_mesh(
            shared_->engine_context, &desc) != 0;
    }

    int32_t finish() const { return ok_ ? 1 : 0; }

private:
    EngineContentSharedBlock* shared_{};
    bool ok_{true};
};
