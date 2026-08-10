#pragma once

#include "content_api.h"


template <typename Command>
inline bool submit_local_command(
        const EngineContentCallContext& context,
        const char* name,
        const Command& command) {
    static_assert(sizeof(Command) <= MAX_LOCAL_COMMAND_SIZE);
    return context.engine && context.engine->local_command_submit
        && context.engine->local_command_submit(
            context.engine_context, name, &command,
            static_cast<uint32_t>(sizeof(Command))) != 0;
}

template <typename Command>
inline bool read_local_command(
        const EngineContentCallContext& context,
        const char* name,
        Command& command,
        uint64_t* sequence = nullptr) {
    static_assert(sizeof(Command) <= MAX_LOCAL_COMMAND_SIZE);
    return context.engine && context.engine->local_command_read
        && context.engine->local_command_read(
            context.engine_context, name, &command,
            static_cast<uint32_t>(sizeof(Command)), sequence) != 0;
}
