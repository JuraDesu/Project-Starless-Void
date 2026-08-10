cmake_minimum_required(VERSION 3.20)

project(game__example_game_creating_ac85de9a9ffc466cba863199bb6b22d0 LANGUAGES C CXX)



set(CMAKE_CXX_STANDARD 23)

set(CMAKE_CXX_STANDARD_REQUIRED ON)



if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/engine/sdk/engine-content-config.cmake")

    get_filename_component(DEFAULT_ENGINE_DIST "${CMAKE_CURRENT_SOURCE_DIR}/engine" ABSOLUTE)

else()

    get_filename_component(DEFAULT_ENGINE_DIST "${CMAKE_CURRENT_SOURCE_DIR}/../out/engine" ABSOLUTE)

endif()

get_filename_component(DEFAULT_GAME_OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/out" ABSOLUTE)

set(ENGINE_DIST "${DEFAULT_ENGINE_DIST}" CACHE PATH "Prebuilt engine distribution")

set(GAME_OUTPUT_DIR "${DEFAULT_GAME_OUTPUT}" CACHE PATH "Complete browser game output")

set(CONTENT_SIMULATION "client" CACHE STRING "Simulation topology: client or server_client")

set_property(CACHE CONTENT_SIMULATION PROPERTY STRINGS client server_client)

set(CONTENT_TICKS_PER_SECOND "30" CACHE STRING "Fixed simulation ticks per second")

set(CONTENT_PROJECT_NAME "touhou game" CACHE STRING "Project name shown in the host window")
set(MSDF_ATLAS_GEN "" CACHE FILEPATH "Path to msdf-atlas-gen")

set(ASEPRITE "" CACHE FILEPATH "Path to Aseprite")



if(NOT EXISTS "${ENGINE_DIST}/sdk/engine-content-config.cmake")

    message(FATAL_ERROR

        "Engine SDK not found at ${ENGINE_DIST}. Build it with 'build.bat engine' or set ENGINE_DIST.")

endif()

if(NOT EXISTS "${ENGINE_DIST}/runtime/index.html")

    message(FATAL_ERROR "Engine browser runtime not found at ${ENGINE_DIST}/runtime")

endif()



include("${ENGINE_DIST}/sdk/engine-content-config.cmake")



set(GENERATED_ROOT "${CMAKE_BINARY_DIR}/generated/content")

set(GENERATED_ASSET_ROOT "${GENERATED_ROOT}/assets")

set(ASSET_MANIFEST "${GENERATED_ROOT}/content_assets.json")

set(CONTENT_STAGE_DIR "${CMAKE_BINARY_DIR}/content_stage")

set(CONTENT_PACKAGE "${CMAKE_BINARY_DIR}/package/content.wmod")



engine_stage_content_assets(content_assets

    ROOT "${CMAKE_CURRENT_SOURCE_DIR}"

    OUTPUT_ROOT "${GENERATED_ASSET_ROOT}"

    MANIFEST "${ASSET_MANIFEST}"

    HEADER "${GENERATED_ROOT}/content_fonts.h"

    MSDF_ATLAS_GEN "${MSDF_ATLAS_GEN}"

    ASEPRITE "${ASEPRITE}")



engine_add_content(content_module

    ROOT "${CMAKE_CURRENT_SOURCE_DIR}"

    GENERATED_ROOT "${GENERATED_ROOT}"

    STAGE_DIR "${CONTENT_STAGE_DIR}"

    ASSET_MANIFEST "${ASSET_MANIFEST}"

    ASSET_TARGET content_assets
    SIMULATION "${CONTENT_SIMULATION}"
    TICKS_PER_SECOND "${CONTENT_TICKS_PER_SECOND}"
    PROJECT_NAME "${CONTENT_PROJECT_NAME}")


engine_package_content(content_package

    CONTENT_TARGET content_module

    ROOT "${CMAKE_CURRENT_SOURCE_DIR}"

    OUTPUT "${CONTENT_PACKAGE}"

    ASSET_MANIFEST "${ASSET_MANIFEST}"

    ASSET_TARGET content_assets)



add_custom_target(content_codegen DEPENDS content_module_codegen)

file(GLOB_RECURSE CONTENT_CHECK_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/content/*.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/content/*.hpp")
set(CONTENT_CHECK_STAMP "${GENERATED_ROOT}/.content_codegen_check.stamp")
add_custom_command(
    OUTPUT "${CONTENT_CHECK_STAMP}"
    COMMAND "${Python3_EXECUTABLE}" "${ENGINE_CONTENT_TOOLS_DIR}/check_content_codegen_boundary.py"
        "${ENGINE_CONTENT_TOOLS_DIR}/content_codegen.py"
        "${CMAKE_CURRENT_SOURCE_DIR}/content"
    COMMAND "${Python3_EXECUTABLE}" "${ENGINE_CONTENT_TOOLS_DIR}/check_game_boundary.py"
        "${CMAKE_CURRENT_SOURCE_DIR}"
    COMMAND "${CMAKE_COMMAND}" -E touch "${CONTENT_CHECK_STAMP}"
    DEPENDS content_codegen
        ${CONTENT_CHECK_SOURCES}
        "${ENGINE_CONTENT_TOOLS_DIR}/check_content_codegen_boundary.py"
        "${ENGINE_CONTENT_TOOLS_DIR}/check_game_boundary.py"
    VERBATIM)
add_custom_target(content_codegen_check DEPENDS "${CONTENT_CHECK_STAMP}")



engine_assemble_browser_game(game_client

    RUNTIME "${ENGINE_DIST}/runtime"

    CONTENT_PACKAGE "${CONTENT_PACKAGE}"

    OUTPUT "${GAME_OUTPUT_DIR}")

add_dependencies(game_client content_package content_codegen_check)

