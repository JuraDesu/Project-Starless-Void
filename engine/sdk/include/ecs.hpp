#pragma once

#include "content_api.h"
#include "callback.hpp"

#include <array>
#include <cstdint>
#include <functional>
#include <type_traits>
#include <utility>


template <typename Component>
struct component_traits;

template <typename Base>
struct component_children_traits;

template <typename Base>
auto component_children() {
    return component_children_traits<Base>::ids();
}

using pair_slot = EnginePairSlot;

template <typename EntityType>
struct prefab_traits;

template <typename Component, std::uint32_t Access, std::uint32_t Match>
struct query_term {
    using component = Component;
    static constexpr std::uint32_t access = Access;
    static constexpr std::uint32_t match = Match;
};

template <typename Component>
using read = query_term<Component, ACCESS_READ, MATCH_REQUIRED>;

/* Match component presence without exposing or materializing its storage. */
template <typename Component>
using present = query_term<Component, ACCESS_FILTER, MATCH_REQUIRED>;

template <typename Component>
using write = query_term<Component, ACCESS_WRITE, MATCH_REQUIRED>;

template <typename Component>
using mut = query_term<Component, ACCESS_READ_WRITE, MATCH_REQUIRED>;

template <typename Component>
using optional_read = query_term<Component, ACCESS_READ, MATCH_OPTIONAL>;

template <typename Component>
using optional_mut = query_term<Component, ACCESS_READ_WRITE, MATCH_OPTIONAL>;

template <typename Component>
using exclude = query_term<Component, ACCESS_READ, MATCH_EXCLUDE>;

[[noreturn]] inline void missing_required_component(
        const EngineContentCallContext* context) {
    if (context && context->engine && context->engine->log)
        context->engine->log(
            context->engine_context, 3u, "required runtime component is missing");
#if defined(__GNUC__) || defined(__clang__)
    __builtin_trap();
#else
    for (;;) {}
#endif
}

class World;

inline bool reset_game() {
    const auto* context = active_callback_context();
    return context && context->engine && context->engine->reset_game
        && context->engine->reset_game(context->engine_context) != 0;
}

class entity {
public:
    entity() = default;
    entity(const EngineContentCallContext& context, std::uint64_t value)
        : content_(&context), value_(value) {}

    std::uint64_t id() const { return value_; }
    const EngineContentCallContext* call_context() const { return content_; }
    explicit operator bool() const { return alive(); }

    template <typename Event>
    bool dispatch(Event& event) const;

    bool alive() const {
        return content_ && content_->engine
            && content_->engine->entity_alive(
                content_->engine_context, content_->world, value_) != 0;
    }

    bool destroy() const {
        return content_ && content_->engine
            && content_->engine->entity_delete(
                content_->engine_context, content_->world, value_) != 0;
    }

    std::uint64_t stable_id() const {
        return content_ && content_->engine
            ? content_->engine->entity_stable_id(
                content_->engine_context, content_->world, value_)
            : 0;
    }

    template <typename Component>
    bool has() const {
        return content_ && content_->engine && component_traits<Component>::id
            && content_->engine->component_has(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id) != 0;
    }

    bool has(EngineComponentId component_id) const {
        return content_ && content_->engine && component_id
            && content_->engine->component_has(
                content_->engine_context, content_->world, value_,
                component_id) != 0;
    }

    template <typename Component>
    const Component* try_get() const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && component_traits<Component>::id
            ? static_cast<const Component*>(content_->engine->component_get(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id))
            : nullptr;
    }

    template <typename Component>
    const Component& get() const {
        const Component* result = try_get<Component>();
        if (!result) missing_required_component(content_);
        return *result;
    }

    template <typename Component>
    Component* try_get_mut() const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && component_traits<Component>::id
            ? static_cast<Component*>(content_->engine->component_get_mut(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id))
            : nullptr;
    }

    template <typename Component>
    Component& get_mut() const {
        Component* result = try_get_mut<Component>();
        if (!result) missing_required_component(content_);
        return *result;
    }

    template <typename Component>
    bool add() const {
        return content_ && content_->engine && component_traits<Component>::id
            && content_->engine->component_add(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id) != 0;
    }

    bool add(EngineComponentId component_id) const {
        return content_ && content_->engine && component_id
            && content_->engine->component_add(
                content_->engine_context, content_->world, value_,
                component_id) != 0;
    }

    template <typename Component>
    bool set(const Component& value) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && component_traits<Component>::id
            && content_->engine->component_set(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id,
                component_traits<Component>::size ? &value : nullptr,
                component_traits<Component>::size) != 0;
    }

    template <typename Component>
    bool remove() const {
        return content_ && content_->engine && component_traits<Component>::id
            && content_->engine->component_remove(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id) != 0;
    }

    bool remove(EngineComponentId component_id) const {
        return content_ && content_->engine && component_id
            && content_->engine->component_remove(
                content_->engine_context, content_->world, value_,
                component_id) != 0;
    }

    template <typename Component>
    bool modified() const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && component_traits<Component>::id
            && content_->engine->component_modified(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id) != 0;
    }

    template <typename Component>
    pair_slot add_pair(const Component& value) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && content_->engine->component_pair_add
            ? content_->engine->component_pair_add(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id, &value,
                component_traits<Component>::size)
            : 0;
    }

    template <typename Component>
    bool has_pair(pair_slot slot) const {
        return content_ && content_->engine && content_->engine->component_pair_has
            && content_->engine->component_pair_has(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id, slot) != 0;
    }

    template <typename Component>
    const Component* try_get_pair(pair_slot slot) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && content_->engine->component_pair_get
            ? static_cast<const Component*>(content_->engine->component_pair_get(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id, slot)) : nullptr;
    }

    template <typename Component>
    Component* try_get_pair_mut(pair_slot slot) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && content_->engine->component_pair_get_mut
            ? static_cast<Component*>(content_->engine->component_pair_get_mut(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id, slot)) : nullptr;
    }

    template <typename Component>
    const Component& get_pair(pair_slot slot) const {
        const Component* result = try_get_pair<Component>(slot);
        if (!result) missing_required_component(content_);
        return *result;
    }

    template <typename Component>
    Component& get_pair_mut(pair_slot slot) const {
        Component* result = try_get_pair_mut<Component>(slot);
        if (!result) missing_required_component(content_);
        return *result;
    }

    template <typename Component>
    bool set_pair(pair_slot slot, const Component& value) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return content_ && content_->engine && content_->engine->component_pair_set
            && content_->engine->component_pair_set(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id, slot, &value,
                component_traits<Component>::size) != 0;
    }

    template <typename Component>
    bool remove_pair(pair_slot slot) const {
        return content_ && content_->engine && content_->engine->component_pair_remove
            && content_->engine->component_pair_remove(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id, slot) != 0;
    }

    template <typename Component>
    bool modified_pair(pair_slot slot) const {
        return content_ && content_->engine && content_->engine->component_pair_modified
            && content_->engine->component_pair_modified(
                content_->engine_context, content_->world, value_,
                component_traits<Component>::id, slot) != 0;
    }

    template <typename Component>
    bool add_pair(entity target, const Component& value) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return same_world(target) && content_->engine && content_->engine->component_target_pair_add
            && content_->engine->component_target_pair_add(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id, &value,
                component_traits<Component>::size) != 0;
    }

    template <typename Component>
    bool add_pair(entity target) const {
        static_assert(component_traits<Component>::size == 0,
            "data pairs require an initializer");
        return same_world(target) && content_->engine && content_->engine->component_target_pair_add
            && content_->engine->component_target_pair_add(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id, nullptr, 0u) != 0;
    }

    template <typename Component>
    bool has_pair(entity target) const {
        return same_world(target) && content_->engine && content_->engine->component_target_pair_has
            && content_->engine->component_target_pair_has(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id) != 0;
    }

    template <typename Component>
    const Component* try_get_pair(entity target) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return same_world(target) && content_->engine && content_->engine->component_target_pair_get
            ? static_cast<const Component*>(content_->engine->component_target_pair_get(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id)) : nullptr;
    }

    template <typename Component>
    Component* try_get_pair_mut(entity target) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return same_world(target) && content_->engine && content_->engine->component_target_pair_get_mut
            ? static_cast<Component*>(content_->engine->component_target_pair_get_mut(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id)) : nullptr;
    }

    template <typename Component>
    const Component& get_pair(entity target) const {
        const Component* result = try_get_pair<Component>(target);
        if (!result) missing_required_component(content_);
        return *result;
    }

    template <typename Component>
    Component& get_pair_mut(entity target) const {
        Component* result = try_get_pair_mut<Component>(target);
        if (!result) missing_required_component(content_);
        return *result;
    }

    template <typename Component>
    bool set_pair(entity target, const Component& value) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return same_world(target) && content_->engine && content_->engine->component_target_pair_set
            && content_->engine->component_target_pair_set(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id, &value,
                component_traits<Component>::size) != 0;
    }

    template <typename Component>
    bool remove_pair(entity target) const {
        return same_world(target) && content_->engine && content_->engine->component_target_pair_remove
            && content_->engine->component_target_pair_remove(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id) != 0;
    }

    template <typename Component>
    bool modified_pair(entity target) const {
        static_assert(component_traits<Component>::size != 0,
            "tags do not contain data");
        return same_world(target) && content_->engine && content_->engine->component_target_pair_modified
            && content_->engine->component_target_pair_modified(
                content_->engine_context, content_->world, value_, target.value_,
                component_traits<Component>::id) != 0;
    }

    World world() const;

private:
    bool same_world(const entity& target) const {
        return content_ && target.content_
            && content_->engine_context == target.content_->engine_context
            && content_->world == target.content_->world;
    }

    const EngineContentCallContext* content_{};
    std::uint64_t value_{};
};

class World {
public:
    World() = default;
    explicit World(const EngineContentCallContext& context) : content_(&context) {}

    const EngineContentCallContext& context() const { return *content_; }

    entity create() const {
        if (!content_ || !content_->engine) return {};
        return entity(
            *content_,
            content_->engine->entity_create(content_->engine_context, content_->world));
    }

    template <typename EntityType>
    entity spawn() const {
        if (!content_ || !content_->engine || !prefab_traits<EntityType>::id)
            return {};
        return entity(
            *content_,
            content_->engine->entity_spawn(
                content_->engine_context, content_->world,
                prefab_traits<EntityType>::id));
    }

    template <typename EntityType, typename Initialize>
    entity spawn(Initialize&& initialize) const {
        if (!content_ || !content_->engine
                || !content_->engine->entity_spawn_initialized
                || !prefab_traits<EntityType>::id) {
            return {};
        }
        using InitializeType = std::remove_reference_t<Initialize>;
        struct State {
            InitializeType* initialize;
        } state{&initialize};
        const auto trampoline = [](
                const EngineContentCallContext* context,
                std::uint64_t entity_value,
                void* user_data) -> int32_t {
            if (!context || !user_data) return 0;
            auto& function =
                *static_cast<State*>(user_data)->initialize;
            entity value{*context, entity_value};
            if constexpr (std::is_same_v<
                    std::invoke_result_t<InitializeType&, entity>, bool>) {
                return std::invoke(function, value) ? 1 : 0;
            } else {
                std::invoke(function, value);
                return 1;
            }
        };
        return entity(
            *content_,
            content_->engine->entity_spawn_initialized(
                content_->engine_context, content_->world,
                prefab_traits<EntityType>::id,
                trampoline, &state));
    }

    entity from_stable_id(std::uint64_t stable_id) const {
        if (!content_ || !content_->engine) return {};
        return entity(
            *content_,
            content_->engine->entity_from_stable_id(
                content_->engine_context, content_->world, stable_id));
    }

    template <typename... Terms, typename Callback>
    bool query(Callback&& callback) const {
        static_assert(sizeof...(Terms) > 0,
            "queries require at least one term");
        static_assert(sizeof...(Terms) <= MAX_TERMS,
            "queries support at most eight terms");
        if (!content_ || !content_->engine || !content_->engine->query_each)
            return false;
        const std::array<EngineTermDesc, sizeof...(Terms)> descriptions{{
            EngineTermDesc{
                component_traits<typename Terms::component>::id,
                Terms::access,
                Terms::match,
                0
            }...
        }};
        for (const EngineTermDesc& term : descriptions)
            if (!term.component) return false;

        using CallbackType = std::remove_reference_t<Callback>;
        struct State {
            CallbackType* callback;
        } state{&callback};
        const auto trampoline = [](
                const EngineQueryInvocation* invocation,
                void* user_data) -> int32_t {
            if (!invocation || !user_data
                    || (invocation->count && !invocation->entities))
                return QUERY_ERROR;
            auto& function = *static_cast<State*>(user_data)->callback;
            for (std::uint32_t row = 0; row < invocation->count; ++row) {
                entity value{invocation->context, invocation->entities[row]};
                if constexpr (std::is_same_v<
                        std::invoke_result_t<CallbackType&, entity>, bool>) {
                    if (!std::invoke(function, value))
                        return QUERY_STOP;
                } else {
                    std::invoke(function, value);
                }
            }
            return QUERY_CONTINUE;
        };
        return content_->engine->query_each(
            content_->engine_context, content_->world,
            descriptions.data(), static_cast<std::uint32_t>(descriptions.size()),
            trampoline, &state) != 0;
    }

private:
    const EngineContentCallContext* content_{};
};

inline World entity::world() const {
    return content_ ? World(*content_) : World();
}
