if(NOT EMSCRIPTEN)
    message(FATAL_ERROR "The exported content SDK currently supports Emscripten browser builds only")
endif()

set(ENGINE_CONTENT_EMSCRIPTEN_VERSION "22.0.0")
if(NOT CMAKE_CXX_COMPILER_VERSION VERSION_EQUAL ENGINE_CONTENT_EMSCRIPTEN_VERSION)
    message(FATAL_ERROR
        "Emscripten ${ENGINE_CONTENT_EMSCRIPTEN_VERSION} is required by this engine distribution; "
        "the configured compiler is ${CMAKE_CXX_COMPILER_VERSION}")
endif()

include("${CMAKE_CURRENT_LIST_DIR}/cmake/EngineContent.cmake")
