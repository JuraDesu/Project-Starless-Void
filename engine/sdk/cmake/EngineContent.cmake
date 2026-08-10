include_guard(GLOBAL)

include(CMakeParseArguments)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    set(CMAKE_C_FLAGS_FASTDEV "-O1 -DNDEBUG" CACHE STRING "C flags for FastDev builds")
    set(CMAKE_CXX_FLAGS_FASTDEV "-O1 -DNDEBUG" CACHE STRING "CXX flags for FastDev builds")
    set(CMAKE_EXE_LINKER_FLAGS_FASTDEV "-O1" CACHE STRING "Linker flags for FastDev builds")
endif()

get_filename_component(ENGINE_CONTENT_SDK_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(ENGINE_CONTENT_INCLUDE_DIR "${ENGINE_CONTENT_SDK_ROOT}/include")
set(ENGINE_CONTENT_TOOLS_DIR "${ENGINE_CONTENT_SDK_ROOT}/tools")

if(NOT TARGET EngineContentSDK)
    add_library(EngineContentSDK INTERFACE)
    target_include_directories(EngineContentSDK INTERFACE "${ENGINE_CONTENT_INCLUDE_DIR}")
    add_library(Engine::ContentSDK ALIAS EngineContentSDK)
endif()

set(ASEPRITE "" CACHE FILEPATH "Path to the Aseprite command-line executable")
set(MSDF_ATLAS_GEN "" CACHE FILEPATH "Path to the msdf-atlas-gen executable")

function(engine_resolve_tool OUTPUT_VARIABLE CACHE_NAME EXPLICIT_VALUE ENVIRONMENT_VARIABLE DESCRIPTION)
    set(CANDIDATE "${EXPLICIT_VALUE}")
    if(NOT CANDIDATE AND DEFINED ENV{${ENVIRONMENT_VARIABLE}})
        file(TO_CMAKE_PATH "$ENV{${ENVIRONMENT_VARIABLE}}" CANDIDATE)
    endif()
    if(NOT CANDIDATE)
        if(ENVIRONMENT_VARIABLE STREQUAL "MSDF_ATLAS_GEN")
            find_program(MSDF_CANDIDATE_FROM_PATH NAMES msdf-atlas-gen msdf-atlas-gen.exe)
            set(CANDIDATE "${MSDF_CANDIDATE_FROM_PATH}")
        else()
            find_program(TOOL_CANDIDATE_FROM_PATH NAMES "${ENVIRONMENT_VARIABLE}" "${ENVIRONMENT_VARIABLE}.exe")
            set(CANDIDATE "${TOOL_CANDIDATE_FROM_PATH}")
        endif()
    endif()
    if(CANDIDATE AND EXISTS "${CANDIDATE}" AND NOT IS_DIRECTORY "${CANDIDATE}")
        set(${CACHE_NAME} "${CANDIDATE}" CACHE FILEPATH "${DESCRIPTION}" FORCE)
    else()
        set(CANDIDATE "")
    endif()
    set(${OUTPUT_VARIABLE} "${CANDIDATE}" PARENT_SCOPE)
endfunction()

function(engine_resolve_aseprite OUTPUT_VARIABLE EXPLICIT_VALUE)
    set(CANDIDATE "${EXPLICIT_VALUE}")
    if(NOT CANDIDATE AND DEFINED ENV{ASEPRITE})
        file(TO_CMAKE_PATH "$ENV{ASEPRITE}" CANDIDATE)
    endif()
    if(NOT CANDIDATE)
        find_program(CANDIDATE_FROM_PATH NAMES aseprite aseprite.exe)
        set(CANDIDATE "${CANDIDATE_FROM_PATH}")
    endif()
    if(NOT CANDIDATE AND WIN32)
        foreach(KNOWN_PATH
                "C:/Program Files/Aseprite/Aseprite.exe"
                "C:/Program Files (x86)/Steam/steamapps/common/Aseprite/Aseprite.exe"
                "C:/Program Files/Steam/steamapps/common/Aseprite/Aseprite.exe")
            if(EXISTS "${KNOWN_PATH}")
                set(CANDIDATE "${KNOWN_PATH}")
                break()
            endif()
        endforeach()
    endif()
    if(CANDIDATE AND EXISTS "${CANDIDATE}" AND NOT IS_DIRECTORY "${CANDIDATE}")
        set(ASEPRITE "${CANDIDATE}" CACHE FILEPATH
            "Path to the Aseprite command-line executable" FORCE)
    else()
        set(CANDIDATE "")
    endif()
    set(${OUTPUT_VARIABLE} "${CANDIDATE}" PARENT_SCOPE)
endfunction()

function(engine_resolve_msdf_atlas_gen OUTPUT_VARIABLE EXPLICIT_VALUE)
    engine_resolve_tool(
        RESOLVED_MSDF
        MSDF_ATLAS_GEN
        "${EXPLICIT_VALUE}"
        "MSDF_ATLAS_GEN"
        "msdf-atlas-gen")
    set(${OUTPUT_VARIABLE} "${RESOLVED_MSDF}" PARENT_SCOPE)
endfunction()

function(engine_stage_content_assets TARGET_NAME)
    cmake_parse_arguments(ARG "" "ROOT;OUTPUT_ROOT;MANIFEST;HEADER;MSDF_ATLAS_GEN;ASEPRITE" "" ${ARGN})
    foreach(REQUIRED ROOT OUTPUT_ROOT MANIFEST HEADER)
        if(NOT ARG_${REQUIRED})
            message(FATAL_ERROR "engine_stage_content_assets requires ${REQUIRED}")
        endif()
    endforeach()
    engine_resolve_aseprite(RESOLVED_ASEPRITE "${ARG_ASEPRITE}")
    engine_resolve_msdf_atlas_gen(RESOLVED_MSDF "${ARG_MSDF_ATLAS_GEN}")
    set(ASSET_TOOL_ARGS)
    set(ASSET_TOOL_DEPENDS)
    if(RESOLVED_ASEPRITE)
        list(APPEND ASSET_TOOL_ARGS --aseprite "${RESOLVED_ASEPRITE}")
        list(APPEND ASSET_TOOL_DEPENDS "${RESOLVED_ASEPRITE}")
    endif()
    if(RESOLVED_MSDF)
        list(APPEND ASSET_TOOL_ARGS --msdf-atlas-gen "${RESOLVED_MSDF}")
        list(APPEND ASSET_TOOL_DEPENDS "${RESOLVED_MSDF}")
    endif()
    file(GLOB_RECURSE ASSET_INPUTS CONFIGURE_DEPENDS
        "${ARG_ROOT}/assets/*" "${ARG_ROOT}/content/*.h" "${ARG_ROOT}/content/*.hpp")
    set(STAMP "${ARG_OUTPUT_ROOT}/.assets.stamp")
    add_custom_command(
        OUTPUT "${STAMP}" "${ARG_MANIFEST}" "${ARG_HEADER}"
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${ARG_OUTPUT_ROOT}"
        COMMAND "${Python3_EXECUTABLE}" "${ENGINE_CONTENT_TOOLS_DIR}/content_assets.py"
            --root "${ARG_ROOT}"
            --output-root "${ARG_OUTPUT_ROOT}"
            --manifest "${ARG_MANIFEST}"
            --header "${ARG_HEADER}"
            ${ASSET_TOOL_ARGS}
        COMMAND "${CMAKE_COMMAND}" -E touch "${STAMP}"
        DEPENDS "${ENGINE_CONTENT_TOOLS_DIR}/content_assets.py"
            "${ENGINE_CONTENT_TOOLS_DIR}/content_atlas.py"
            "${ENGINE_CONTENT_TOOLS_DIR}/font_codegen.py"
            ${ASSET_TOOL_DEPENDS}
            ${ASSET_INPUTS}
        VERBATIM)
    add_custom_target(${TARGET_NAME} DEPENDS "${STAMP}" "${ARG_MANIFEST}" "${ARG_HEADER}")
    file(GLOB GENERATED_ASSET_OUTPUTS CONFIGURE_DEPENDS
        "${ARG_OUTPUT_ROOT}/atlases/*.png"
        "${ARG_OUTPUT_ROOT}/atlases/*.json"
        "${ARG_OUTPUT_ROOT}/fonts/*.png"
        "${ARG_OUTPUT_ROOT}/fonts/*.json")
    set_target_properties(${TARGET_NAME} PROPERTIES
        ENGINE_CONTENT_ASSET_ROOT "${ARG_OUTPUT_ROOT}"
        ENGINE_CONTENT_ASSET_MANIFEST "${ARG_MANIFEST}"
        ENGINE_CONTENT_FONT_HEADER "${ARG_HEADER}"
        ENGINE_CONTENT_ASSET_OUTPUTS "${ARG_HEADER};${GENERATED_ASSET_OUTPUTS}")
endfunction()

function(engine_add_content TARGET_NAME)
    cmake_parse_arguments(ARG "" "ROOT;GENERATED_ROOT;STAGE_DIR;ASSET_MANIFEST;ASSET_TARGET;SIMULATION;TICKS_PER_SECOND;PROJECT_NAME" "" ${ARGN})
    foreach(REQUIRED ROOT GENERATED_ROOT STAGE_DIR ASSET_MANIFEST ASSET_TARGET SIMULATION TICKS_PER_SECOND PROJECT_NAME)
        if(NOT ARG_${REQUIRED})
            message(FATAL_ERROR "engine_add_content requires ${REQUIRED}")
        endif()
    endforeach()
    if(NOT ARG_SIMULATION STREQUAL "client" AND NOT ARG_SIMULATION STREQUAL "server_client")
        message(FATAL_ERROR "SIMULATION must be 'client' or 'server_client'")
    endif()
    if(NOT ARG_TICKS_PER_SECOND MATCHES "^[0-9]+$"
            OR ARG_TICKS_PER_SECOND LESS 1 OR ARG_TICKS_PER_SECOND GREATER 1000)
        message(FATAL_ERROR "TICKS_PER_SECOND must be an integer from 1 to 1000")
    endif()
    if(ARG_PROJECT_NAME STREQUAL "")
        message(FATAL_ERROR "PROJECT_NAME must not be empty")
    endif()

    set(GENERATED_CPP "${ARG_GENERATED_ROOT}/content_generated.cpp")
    set(GENERATED_HEADER "${ARG_GENERATED_ROOT}/content_generated.h")
    set(CODEGEN_STAMP "${ARG_GENERATED_ROOT}/.content_codegen.stamp")
    file(GLOB_RECURSE CONTENT_SOURCES CONFIGURE_DEPENDS
        "${ARG_ROOT}/content/*.h" "${ARG_ROOT}/content/*.hpp")
    get_target_property(ASSET_OUTPUTS ${ARG_ASSET_TARGET} ENGINE_CONTENT_ASSET_OUTPUTS)
    if(NOT ASSET_OUTPUTS)
        set(ASSET_OUTPUTS "")
    endif()
    add_custom_command(
        OUTPUT "${CODEGEN_STAMP}"
        BYPRODUCTS "${GENERATED_CPP}" "${GENERATED_HEADER}"
        COMMAND "${Python3_EXECUTABLE}" "${ENGINE_CONTENT_TOOLS_DIR}/content_codegen.py"
            --content-root "${ARG_ROOT}"
            --output "${ARG_GENERATED_ROOT}"
            --asset-manifest "${ARG_ASSET_MANIFEST}"
            --simulation "${ARG_SIMULATION}"
            --ticks-per-second "${ARG_TICKS_PER_SECOND}"
            --project-name "${ARG_PROJECT_NAME}"
        COMMAND "${CMAKE_COMMAND}" -E touch "${CODEGEN_STAMP}"
        DEPENDS "${ENGINE_CONTENT_TOOLS_DIR}/content_codegen.py"
            ${CONTENT_SOURCES} "${ARG_ASSET_MANIFEST}" ${ASSET_OUTPUTS}
        VERBATIM)
    add_custom_target(${TARGET_NAME}_codegen DEPENDS "${CODEGEN_STAMP}")

    add_executable(${TARGET_NAME} "${GENERATED_CPP}")
    add_dependencies(${TARGET_NAME} ${TARGET_NAME}_codegen)
    set_target_properties(${TARGET_NAME} PROPERTIES
        OUTPUT_NAME "client"
        SUFFIX ".wasm"
        RUNTIME_OUTPUT_DIRECTORY "${ARG_STAGE_DIR}"
        POSITION_INDEPENDENT_CODE ON
        ENGINE_CONTENT_ROOT "${ARG_ROOT}"
        ENGINE_CONTENT_STAGE_DIR "${ARG_STAGE_DIR}"
        ENGINE_CONTENT_GENERATED_ROOT "${ARG_GENERATED_ROOT}"
        ENGINE_CONTENT_OUTPUT_STAMP "${ARG_STAGE_DIR}.content.stamp")
    add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
        BYPRODUCTS "${ARG_STAGE_DIR}.content.stamp"
        COMMAND "${CMAKE_COMMAND}" -E touch "${ARG_STAGE_DIR}.content.stamp")
    add_dependencies(${TARGET_NAME} ${ARG_ASSET_TARGET})
    target_link_libraries(${TARGET_NAME} PRIVATE Engine::ContentSDK)
    target_include_directories(${TARGET_NAME} PRIVATE
        "${ARG_GENERATED_ROOT}"
        "${ARG_ROOT}/content")
    target_link_options(${TARGET_NAME} PRIVATE
        "-sSIDE_MODULE=2"
        "-sALLOW_TABLE_GROWTH=1"
        "-Wl,--no-entry"
        "-Wl,--export=content_phase"
        "-Wl,--export=content_apply_prefab"
        "-Wl,--export=content_run_system"
        "-Wl,--export=content_run_observer"
        "-Wl,--export=content_get_setup"
        "-Wl,--export=content_init"
        "-Wl,--export=content_run_start")
endfunction()

function(engine_package_content TARGET_NAME)
    cmake_parse_arguments(ARG "" "CONTENT_TARGET;ROOT;OUTPUT;ASSET_MANIFEST;ASSET_TARGET" "" ${ARGN})
    foreach(REQUIRED CONTENT_TARGET ROOT OUTPUT ASSET_MANIFEST ASSET_TARGET)
        if(NOT ARG_${REQUIRED})
            message(FATAL_ERROR "engine_package_content requires ${REQUIRED}")
        endif()
    endforeach()
    get_target_property(STAGE_DIR ${ARG_CONTENT_TARGET} ENGINE_CONTENT_STAGE_DIR)
    get_target_property(CONTENT_OUTPUT_STAMP ${ARG_CONTENT_TARGET} ENGINE_CONTENT_OUTPUT_STAMP)
    file(GLOB_RECURSE PACKAGE_ASSETS CONFIGURE_DEPENDS "${ARG_ROOT}/assets/*")
    list(FILTER PACKAGE_ASSETS EXCLUDE REGEX "\\.(aseprite|ttf)$")
    get_target_property(ASSET_OUTPUTS ${ARG_ASSET_TARGET} ENGINE_CONTENT_ASSET_OUTPUTS)
    if(NOT ASSET_OUTPUTS)
        set(ASSET_OUTPUTS "")
    endif()

    add_custom_command(
        OUTPUT "${ARG_OUTPUT}.stamp"
        BYPRODUCTS "${ARG_OUTPUT}"
        COMMAND "${Python3_EXECUTABLE}" "${ENGINE_CONTENT_TOOLS_DIR}/content_assets.py"
            --root "${ARG_ROOT}" --manifest "${ARG_ASSET_MANIFEST}"
            --stage-dir "${STAGE_DIR}"
        COMMAND "${Python3_EXECUTABLE}" "${ENGINE_CONTENT_TOOLS_DIR}/content_package.py"
            --source "${STAGE_DIR}" --output "${ARG_OUTPUT}"
        COMMAND "${CMAKE_COMMAND}" -E touch "${ARG_OUTPUT}.stamp"
        DEPENDS ${ARG_ASSET_TARGET} "${ARG_ASSET_MANIFEST}"
            "${CONTENT_OUTPUT_STAMP}"
            ${ASSET_OUTPUTS} ${PACKAGE_ASSETS} "${ENGINE_CONTENT_TOOLS_DIR}/content_assets.py"
            "${ENGINE_CONTENT_TOOLS_DIR}/content_package.py"
        VERBATIM)
    add_custom_target(${TARGET_NAME} DEPENDS "${ARG_OUTPUT}.stamp")
endfunction()

function(engine_assemble_browser_game TARGET_NAME)
    cmake_parse_arguments(ARG "" "RUNTIME;CONTENT_PACKAGE;OUTPUT" "" ${ARGN})
    foreach(REQUIRED RUNTIME CONTENT_PACKAGE OUTPUT)
        if(NOT ARG_${REQUIRED})
            message(FATAL_ERROR "engine_assemble_browser_game requires ${REQUIRED}")
        endif()
    endforeach()
    set(STAMP "${CMAKE_BINARY_DIR}/${TARGET_NAME}.stamp")
    add_custom_command(
        OUTPUT "${STAMP}"
        COMMAND "${CMAKE_COMMAND}" -E remove_directory "${ARG_OUTPUT}"
        COMMAND "${CMAKE_COMMAND}" -E make_directory "${ARG_OUTPUT}"
        COMMAND "${CMAKE_COMMAND}" -E copy_directory "${ARG_RUNTIME}" "${ARG_OUTPUT}"
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${ARG_CONTENT_PACKAGE}" "${ARG_OUTPUT}/content.wmod"
        COMMAND "${CMAKE_COMMAND}" -E touch "${STAMP}"
        DEPENDS "${ARG_CONTENT_PACKAGE}"
            "${ARG_RUNTIME}/index.html"
            "${ARG_RUNTIME}/index.js"
            "${ARG_RUNTIME}/index.wasm"
        VERBATIM)
    add_custom_target(${TARGET_NAME} ALL DEPENDS "${STAMP}")
endfunction()
