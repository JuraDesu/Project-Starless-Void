#ifndef CONTENT_API_H
#define CONTENT_API_H

#include <stdint.h>

#if defined(__cplusplus)
extern "C" {
#endif

#define MAX_TERMS 8u
#define MAX_SHADER_ATTRIBUTES 8u
#define MAX_SHADER_TEXTURES 8u
#define MAX_EVENT_DEPTH 32u
#define MAX_INPUT_KEYS 8u
#define MAX_LOCAL_COMMAND_SIZE 256u
#define PARTICLE_CAPACITY 65536u

typedef enum EngineContentPhase {
    PHASE_COMPONENTS = 0,
    PHASE_COMPONENT_BINDINGS = 1,
    PHASE_EVENT_BINDINGS = 2,
    PHASE_INIT = 3,
    PHASE_TEXTURE_BINDINGS = 4,
    PHASE_SHADERS = 5,
    PHASE_COMPUTES = 6,
    PHASE_COMPUTE_BINDINGS = 7,
    PHASE_ENTITIES = 8,
    PHASE_ENTITY_BINDINGS = 9,
    PHASE_OBSERVERS = 10,
    PHASE_SYSTEMS = 11,
    PHASE_READY = 12
} EngineContentPhase;

/* Physical USB HID usage IDs, matching SDL scancodes. */
typedef enum EngineKey {
    KEY_UNKNOWN = 0,
    KEY_A = 4, KEY_B = 5, KEY_C = 6,
    KEY_D = 7, KEY_E = 8, KEY_F = 9,
    KEY_G = 10, KEY_H = 11, KEY_I = 12,
    KEY_J = 13, KEY_K = 14, KEY_L = 15,
    KEY_M = 16, KEY_N = 17, KEY_O = 18,
    KEY_P = 19, KEY_Q = 20, KEY_R = 21,
    KEY_S = 22, KEY_T = 23, KEY_U = 24,
    KEY_V = 25, KEY_W = 26, KEY_X = 27,
    KEY_Y = 28, KEY_Z = 29,
    KEY_1 = 30, KEY_2 = 31, KEY_3 = 32,
    KEY_4 = 33, KEY_5 = 34, KEY_6 = 35,
    KEY_7 = 36, KEY_8 = 37, KEY_9 = 38,
    KEY_0 = 39,
    KEY_ENTER = 40, KEY_ESCAPE = 41,
    KEY_BACKSPACE = 42, KEY_TAB = 43,
    KEY_SPACE = 44, KEY_MINUS = 45,
    KEY_EQUAL = 46, KEY_LEFT_BRACKET = 47,
    KEY_RIGHT_BRACKET = 48, KEY_BACKSLASH = 49,
    KEY_SEMICOLON = 51, KEY_APOSTROPHE = 52,
    KEY_GRAVE = 53, KEY_COMMA = 54,
    KEY_PERIOD = 55, KEY_SLASH = 56,
    KEY_CAPS_LOCK = 57,
    KEY_F1 = 58, KEY_F2 = 59, KEY_F3 = 60,
    KEY_F4 = 61, KEY_F5 = 62, KEY_F6 = 63,
    KEY_F7 = 64, KEY_F8 = 65, KEY_F9 = 66,
    KEY_F10 = 67, KEY_F11 = 68, KEY_F12 = 69,
    KEY_PRINT_SCREEN = 70, KEY_SCROLL_LOCK = 71,
    KEY_PAUSE = 72, KEY_INSERT = 73,
    KEY_HOME = 74, KEY_PAGE_UP = 75,
    KEY_DELETE = 76, KEY_END = 77,
    KEY_PAGE_DOWN = 78, KEY_RIGHT = 79,
    KEY_LEFT = 80, KEY_DOWN = 81, KEY_UP = 82,
    KEY_NUM_LOCK = 83, KEY_NUMPAD_DIVIDE = 84,
    KEY_NUMPAD_MULTIPLY = 85, KEY_NUMPAD_SUBTRACT = 86,
    KEY_NUMPAD_ADD = 87, KEY_NUMPAD_ENTER = 88,
    KEY_NUMPAD_1 = 89, KEY_NUMPAD_2 = 90,
    KEY_NUMPAD_3 = 91, KEY_NUMPAD_4 = 92,
    KEY_NUMPAD_5 = 93, KEY_NUMPAD_6 = 94,
    KEY_NUMPAD_7 = 95, KEY_NUMPAD_8 = 96,
    KEY_NUMPAD_9 = 97, KEY_NUMPAD_0 = 98,
    KEY_NUMPAD_DECIMAL = 99,
    KEY_NON_US_BACKSLASH = 100,
    KEY_F13 = 104, KEY_F14 = 105,
    KEY_F15 = 106, KEY_F16 = 107,
    KEY_F17 = 108, KEY_F18 = 109,
    KEY_F19 = 110, KEY_F20 = 111,
    KEY_F21 = 112, KEY_F22 = 113,
    KEY_F23 = 114, KEY_F24 = 115,
    KEY_LEFT_CONTROL = 224, KEY_LEFT_SHIFT = 225,
    KEY_LEFT_ALT = 226, KEY_LEFT_META = 227,
    KEY_RIGHT_CONTROL = 228, KEY_RIGHT_SHIFT = 229,
    KEY_RIGHT_ALT = 230, KEY_RIGHT_META = 231
} EngineKey;

typedef enum EngineWorldSide {
    WORLD_SERVER = 1,
    WORLD_CLIENT = 2,
    WORLD_RENDER = 4
} EngineWorldSide;

typedef enum EngineSimulationMode {
    SIMULATION_CLIENT = 1,
    SIMULATION_SERVER_CLIENT = 2
} EngineSimulationMode;

typedef enum EngineTermAccess {
    ACCESS_READ = 1,
    ACCESS_WRITE = 2,
    ACCESS_READ_WRITE = 3
} EngineTermAccess;

typedef enum EngineTermMatch {
    MATCH_REQUIRED = 1,
    MATCH_OPTIONAL = 2,
    MATCH_EXCLUDE = 3
} EngineTermMatch;

typedef enum EngineObserverEvent {
    OBSERVER_ADD = 1,
    OBSERVER_SET = 2,
    OBSERVER_REMOVE = 3,
    OBSERVER_CUSTOM = 4
} EngineObserverEvent;

typedef enum EngineQueryControl {
    QUERY_ERROR = -1,
    QUERY_STOP = 0,
    QUERY_CONTINUE = 1
} EngineQueryControl;

typedef enum EngineVertexFormat {
    VERTEX_FLOAT32 = 1,
    VERTEX_FLOAT32X2 = 2,
    VERTEX_FLOAT32X3 = 3,
    VERTEX_FLOAT32X4 = 4,
    VERTEX_SINT32 = 5,
    VERTEX_UINT32 = 6
} EngineVertexFormat;

typedef enum EngineBlendMode {
    BLEND_OPAQUE = 1,
    BLEND_ALPHA = 2
} EngineBlendMode;

typedef enum EnginePrimitiveTopology {
    TOPOLOGY_TRIANGLES = 0,
    TOPOLOGY_LINES = 1
} EnginePrimitiveTopology;

typedef uint64_t EngineComponentId;
typedef uint64_t EnginePrefabId;
typedef uint64_t EngineComputeId;
typedef uint64_t EngineAudioId;
typedef uint64_t EngineEventId;
typedef uint64_t EngineTextureId;
typedef uint64_t EnginePairSlot;

typedef struct EngineStructHeader {
    uint32_t struct_size;
} EngineStructHeader;

typedef struct EngineContentSetup {
    EngineStructHeader header;
    uint32_t simulation;
    uint32_t ticks_per_second;
    const char* project_name;
} EngineContentSetup;

typedef struct EngineComponentDesc {
    EngineStructHeader header;
    const char* name;
    uint32_t size;
    uint32_t alignment;
    uint32_t residency;
    const void* default_value;
    uint32_t default_size;
    uint64_t fingerprint;
    uint64_t contract_fingerprint;
} EngineComponentDesc;

typedef struct EngineEventDesc {
    EngineStructHeader header;
    const char* name;
    uint32_t size;
    uint32_t alignment;
    uint32_t residency;
    uint64_t fingerprint;
    EngineEventId* result;
} EngineEventDesc;

typedef struct EngineAudioDesc {
    EngineStructHeader header;
    const char* name;
    const char* path;
} EngineAudioDesc;

typedef struct EngineTermDesc {
    EngineComponentId component;
    uint32_t access;
    uint32_t match;
    uint32_t pair_wildcard;
} EngineTermDesc;

typedef struct EnginePrefabDesc {
    EngineStructHeader header;
    const char* name;
    uint32_t residency;
    uint32_t callback;
    uint64_t fingerprint;
} EnginePrefabDesc;

typedef struct EngineSystemDesc {
    EngineStructHeader header;
    const char* name;
    uint32_t world;
    uint32_t callback;
    int32_t order;
    uint32_t term_count;
    EngineTermDesc terms[MAX_TERMS];
} EngineSystemDesc;

typedef struct EngineObserverDesc {
    EngineStructHeader header;
    const char* name;
    uint32_t world;
    uint32_t callback;
    int32_t order;
    uint32_t event;
    EngineEventId custom_event;
    uint32_t term_count;
    EngineTermDesc terms[MAX_TERMS];
} EngineObserverDesc;

typedef struct EngineShaderAttributeDesc {
    uint32_t shader_location;
    uint32_t format;
    uint32_t offset;
} EngineShaderAttributeDesc;

enum {
    FILTER_NEAREST = 0,
    FILTER_LINEAR = 1,
};

enum {
    ADDRESS_CLAMP = 0,
    ADDRESS_REPEAT = 1,
};

typedef struct EngineTextureDesc {
    EngineStructHeader header;
    const char* name;
    const char* path;
    uint32_t filter;
    uint32_t address;
    EngineTextureId* result;
} EngineTextureDesc;

typedef struct EngineTextureSlice {
    EngineStructHeader header;
    EngineTextureId id;
    EngineTextureId atlas;
    uint32_t pixel_width;
    uint32_t pixel_height;
    float uv_x;
    float uv_y;
    float uv_width;
    float uv_height;
    uint32_t layer;
} EngineTextureSlice;

typedef struct EngineMeshVertex {
    float x;
    float y;
} EngineMeshVertex;

typedef struct EngineMeshDesc {
    EngineStructHeader header;
    const char* name;
    const EngineMeshVertex* vertices;
    uint32_t vertex_count;
    const uint16_t* indices;
    uint32_t index_count;
} EngineMeshDesc;

typedef struct EngineInputActionDesc {
    EngineStructHeader header;
    const char* name;
    uint32_t key_count;
    uint32_t keys[MAX_INPUT_KEYS];
} EngineInputActionDesc;

typedef struct EngineInputButtonState {
    uint8_t down;
    uint8_t pressed;
    uint8_t released;
    uint8_t reserved;
} EngineInputButtonState;

typedef struct EngineCursorState {
    EngineStructHeader header;
    float world_x;
    float world_y;
    uint32_t valid;
    EngineInputButtonState primary;
} EngineCursorState;

typedef struct EngineWheelState {
    EngineStructHeader header;
    float y;
    uint32_t valid;
} EngineWheelState;

typedef struct EngineViewState {
    EngineStructHeader header;
    float canvas_width;
    float canvas_height;
    float cursor_x;
    float cursor_y;
    float camera_x;
    float camera_y;
    float camera_zoom;
    uint32_t focused;
    uint32_t cursor_valid;
} EngineViewState;

typedef struct EnginePresentationTiming {
    EngineStructHeader header;
    uint64_t latest_simulation_tick;
    uint64_t segment_tick;
    double presentation_tick;
    float alpha;
    float tick_seconds;
    uint32_t valid;
} EnginePresentationTiming;

typedef struct EngineCameraFollowDesc {
    EngineStructHeader header;
    uint64_t entity;
    EngineComponentId presented_component;
    uint32_t position_offset;
    uint32_t valid_offset;
    uint32_t visible_offset;
} EngineCameraFollowDesc;

typedef struct EngineShaderDesc {
    EngineStructHeader header;
    const char* name;
    EngineComponentId component;
    const char* wgsl_source;
    uint32_t wgsl_size;
    uint32_t instance_stride;
    uint32_t blend_mode;
    int32_t draw_order;
    uint32_t attribute_count;
    EngineShaderAttributeDesc attributes[MAX_SHADER_ATTRIBUTES];
    uint32_t texture_count;
    const char* textures[MAX_SHADER_TEXTURES];
    uint32_t topology;
    const char* mesh;
} EngineShaderDesc;

typedef struct EngineComputeDesc {
    EngineStructHeader header;
    const char* name;
    EngineComponentId instance_component;
    const char* wgsl_source;
    uint32_t wgsl_size;
    uint32_t state_stride;
    uint32_t state_alignment;
    uint32_t instance_stride;
    uint64_t state_fingerprint;
    uint64_t instance_fingerprint;
} EngineComputeDesc;

typedef struct EngineColumnView {
    void* data;
    uint32_t element_size;
    uint32_t stride;
    uint32_t count;
    uint64_t component;
    uint32_t access;
    uint32_t match;
    uint32_t is_set;
    uint64_t pair_target;
} EngineColumnView;

struct EngineApi;

typedef struct EngineContentCallContext {
    const struct EngineApi* engine;
    void* engine_context;
    uint32_t world;
    uint64_t tick;
    double delta_time;
} EngineContentCallContext;

typedef int32_t (*EnginePrefabInitializeFn)(
    const EngineContentCallContext* context, uint64_t entity, void* user_data);

typedef struct EngineSystemInvocation {
    EngineStructHeader header;
    EngineContentCallContext context;
    uint32_t count;
    const uint64_t* entities;
    uint32_t column_count;
    EngineColumnView* columns;
} EngineSystemInvocation;

typedef struct EngineObserverInvocation {
    EngineStructHeader header;
    EngineContentCallContext context;
    uint32_t event;
    void* event_data;
    uint32_t event_size;
    uint32_t count;
    const uint64_t* entities;
    uint32_t column_count;
    EngineColumnView* columns;
} EngineObserverInvocation;

typedef struct EnginePrefabApplyContext {
    EngineStructHeader header;
    EngineContentCallContext context;
    uint64_t entity;
} EnginePrefabApplyContext;

typedef struct EngineQueryInvocation {
    EngineStructHeader header;
    EngineContentCallContext context;
    uint32_t count;
    const uint64_t* entities;
    uint32_t column_count;
    EngineColumnView* columns;
} EngineQueryInvocation;

typedef int32_t (*EngineQueryBatchFn)(
    const EngineQueryInvocation* invocation, void* user_data);

typedef struct EngineApi {
    EngineStructHeader header;
    void (*log)(void* engine_context, uint32_t level, const char* message);
    int32_t (*append_component)(void* engine_context, const EngineComponentDesc* desc);
    int32_t (*append_prefab)(void* engine_context, const EnginePrefabDesc* desc);
    int32_t (*append_event)(void* engine_context, const EngineEventDesc* desc);
    int32_t (*append_system)(void* engine_context, const EngineSystemDesc* desc);
    int32_t (*append_observer)(void* engine_context, const EngineObserverDesc* desc);
    int32_t (*append_shader)(void* engine_context, const EngineShaderDesc* desc);

    int32_t (*resolve_component)(void* engine_context, const char* canonical_name,
        uint64_t fingerprint, uint32_t size, uint32_t alignment,
        uint32_t residency, EngineComponentId* result);
    int32_t (*resolve_prefab)(void* engine_context, const char* canonical_name,
        uint64_t fingerprint, uint32_t residency, EnginePrefabId* result);
    int32_t (*resolve_event)(void* engine_context, const char* canonical_name,
        uint64_t fingerprint, uint32_t size, uint32_t alignment,
        uint32_t residency, EngineEventId* result);
    int32_t (*entity_alive)(void* engine_context, uint32_t world, uint64_t entity);
    uint64_t (*entity_create)(void* engine_context, uint32_t world);
    uint64_t (*entity_spawn)(void* engine_context, uint32_t world, EnginePrefabId entity_type);
    uint64_t (*entity_spawn_initialized)(
        void* engine_context, uint32_t world, EnginePrefabId entity_type,
        EnginePrefabInitializeFn initialize, void* user_data);
    int32_t (*entity_delete)(void* engine_context, uint32_t world, uint64_t entity);
    int32_t (*component_has)(void* engine_context, uint32_t world, uint64_t entity, EngineComponentId component);
    const void* (*component_get)(void* engine_context, uint32_t world, uint64_t entity, EngineComponentId component);
    void* (*component_get_mut)(void* engine_context, uint32_t world, uint64_t entity, EngineComponentId component);
    int32_t (*component_add)(void* engine_context, uint32_t world, uint64_t entity, EngineComponentId component);
    int32_t (*component_set)(void* engine_context, uint32_t world, uint64_t entity, EngineComponentId component, const void* value, uint32_t size);
    int32_t (*component_remove)(void* engine_context, uint32_t world, uint64_t entity, EngineComponentId component);
    int32_t (*component_modified)(void* engine_context, uint32_t world, uint64_t entity, EngineComponentId component);
    EnginePairSlot (*component_pair_add)(void* engine_context, uint32_t world, uint64_t entity,
        EngineComponentId component, const void* value, uint32_t size);
    int32_t (*component_pair_has)(void* engine_context, uint32_t world, uint64_t entity,
        EngineComponentId component, EnginePairSlot slot);
    const void* (*component_pair_get)(void* engine_context, uint32_t world, uint64_t entity,
        EngineComponentId component, EnginePairSlot slot);
    void* (*component_pair_get_mut)(void* engine_context, uint32_t world, uint64_t entity,
        EngineComponentId component, EnginePairSlot slot);
    int32_t (*component_pair_set)(void* engine_context, uint32_t world, uint64_t entity,
        EngineComponentId component, EnginePairSlot slot, const void* value, uint32_t size);
    int32_t (*component_pair_remove)(void* engine_context, uint32_t world, uint64_t entity,
        EngineComponentId component, EnginePairSlot slot);
    int32_t (*component_pair_modified)(void* engine_context, uint32_t world, uint64_t entity,
        EngineComponentId component, EnginePairSlot slot);
    int32_t (*query_each)(void* engine_context, uint32_t world,
        const EngineTermDesc* terms, uint32_t term_count,
        EngineQueryBatchFn callback, void* user_data);
    int32_t (*dispatch_event)(void* engine_context, uint32_t world,
        EngineEventId event, uint64_t subject,
        void* event_data, uint32_t event_size);
    uint64_t (*entity_stable_id)(
        void* engine_context, uint32_t world, uint64_t entity);
    uint64_t (*entity_from_stable_id)(
        void* engine_context, uint32_t world, uint64_t stable_id);
    int32_t (*append_texture)(
        void* engine_context, const EngineTextureDesc* desc);
    int32_t (*bind_texture_slice)(
        void* engine_context, const char* canonical_name,
        const char* atlas_name, uint32_t pixel_width,
        uint32_t pixel_height, float uv_x, float uv_y,
        float uv_width, float uv_height, uint32_t layer,
        EngineTextureSlice* result);
    int32_t (*append_mesh)(
        void* engine_context, const EngineMeshDesc* desc);
    int32_t (*append_input_action)(
        void* engine_context, const EngineInputActionDesc* desc);
    int32_t (*input_button)(
        void* engine_context, const char* name,
        EngineInputButtonState* state);
    int32_t (*input_cursor)(
        void* engine_context, EngineCursorState* state);
    int32_t (*input_wheel)(
        void* engine_context, EngineWheelState* state);
    int32_t (*camera_follow_entity)(
        void* engine_context, uint32_t world,
        const EngineCameraFollowDesc* desc);
    int32_t (*camera_zoom)(void* engine_context, float zoom);
    int32_t (*reset_game)(void* engine_context);
    int32_t (*local_command_submit)(
        void* engine_context, const char* name,
        const void* data, uint32_t size);
    int32_t (*local_command_read)(
        void* engine_context, const char* name,
        void* data, uint32_t size, uint64_t* sequence);
    int32_t (*presentation_timing)(
        void* engine_context, EnginePresentationTiming* timing);
    int32_t (*submit_render_instances)(
        void* engine_context, EngineComponentId component,
        const void* instances, uint32_t stride, uint32_t count,
        int32_t draw_order_override);
    int32_t (*append_compute)(
        void* engine_context, const EngineComputeDesc* desc);
    int32_t (*resolve_compute)(
        void* engine_context, const char* canonical_name,
        uint64_t state_fingerprint, uint32_t state_stride,
        uint32_t state_alignment, EngineComponentId instance_component,
        uint64_t instance_fingerprint, EngineComputeId* result);
    int32_t (*submit_compute_spawns)(
        void* engine_context, EngineComputeId compute,
        const void* states, uint32_t state_stride,
        const void* instances, uint32_t instance_stride,
        uint32_t count);
    int32_t (*append_audio)(
        void* engine_context, const EngineAudioDesc* desc,
        EngineAudioId* result);
    int32_t (*play_spatial_audio)(
        void* engine_context, EngineAudioId audio,
        float x, float y, float gain,
        float distance_scale, float pan_range);
    int32_t (*bind_component_base)(
        void* engine_context, EngineComponentId derived,
        EngineComponentId base, uint64_t contract_fingerprint);
    int32_t (*view_state)(
        void* engine_context, EngineViewState* state);
    int32_t (*component_target_pair_add)(
        void* engine_context, uint32_t world, uint64_t entity,
        uint64_t target, EngineComponentId component,
        const void* value, uint32_t size);
    int32_t (*component_target_pair_has)(
        void* engine_context, uint32_t world, uint64_t entity,
        uint64_t target, EngineComponentId component);
    const void* (*component_target_pair_get)(
        void* engine_context, uint32_t world, uint64_t entity,
        uint64_t target, EngineComponentId component);
    void* (*component_target_pair_get_mut)(
        void* engine_context, uint32_t world, uint64_t entity,
        uint64_t target, EngineComponentId component);
    int32_t (*component_target_pair_set)(
        void* engine_context, uint32_t world, uint64_t entity,
        uint64_t target, EngineComponentId component,
        const void* value, uint32_t size);
    int32_t (*component_target_pair_remove)(
        void* engine_context, uint32_t world, uint64_t entity,
        uint64_t target, EngineComponentId component);
    int32_t (*component_target_pair_modified)(
        void* engine_context, uint32_t world, uint64_t entity,
        uint64_t target, EngineComponentId component);
} EngineApi;

typedef struct EngineContentSharedBlock {
    EngineStructHeader header;
    uint32_t phase;
    uint32_t world_mask;
    void* engine_context;
    const EngineApi* engine;
} EngineContentSharedBlock;

int32_t content_phase(EngineContentSharedBlock* shared);
int32_t content_get_setup(EngineContentSetup* setup);
int32_t content_apply_prefab(uint32_t callback, EnginePrefabApplyContext* context);
int32_t content_run_system(uint32_t callback, EngineSystemInvocation* invocation);
int32_t content_run_observer(uint32_t callback, EngineObserverInvocation* invocation);
/* Required one-time initialization callback, invoked during PHASE_INIT. */
int32_t content_init(EngineContentSharedBlock* shared);

#if defined(__cplusplus)
}
#endif

#endif
