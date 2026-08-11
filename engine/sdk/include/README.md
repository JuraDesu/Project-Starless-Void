# Content runtime API

This directory is the exact C-compatible boundary and header-only C++ SDK
shared by the engine and the single required content module. Public structures
carry `struct_size`, and their layouts must match exactly.

Registration uses one fixed barrier sequence:

`Components -> ComponentBindings -> EventBindings -> Init -> TextureBindings ->
Shaders -> Computes -> ComputeBindings -> Entities -> EntityBindings ->
Observers -> Systems -> Ready`

Names exist only during registration and binding. Components, events, entity
recipes, textures, computes, and audio clips receive generation-checked opaque
handles. Runtime gameplay operations use those handles, while generated C++
traits preserve typed component access.

Callbacks can perform scoped ECS iteration with `World::query`. Terms use
`read<T>`, `present<T>`, `write<T>`, `mut<T>`, `optional_read<T>`,
`optional_mut<T>`, and `exclude<T>`. `present<T>` matches required component
presence without exposing or fetching its storage. Query callbacks receive an `entity`; returning `false` stops a
query successfully. Component handles are resolved at runtime, shared-component
write ownership is enforced, writable terms are marked modified, nested queries
are supported, and structural changes are deferred until the outer iteration
finishes.

Component residency controls the server, client, and render worlds and local
replication. Shader components remain ordinary ECS components; render-world
buffers are additionally uploaded through their registered shader pipeline.
Meshes, textures, audio, input actions, camera attachment, particles, text, and
UI behavior are all registered or implemented by the content module.

The browser host requires exactly one `content.wmod` containing `client.wasm`
and optional `assets/**`. Asset authoring is explicit in `content/assets.h`:
`assets.atlas(name, aseprite, filter, address)` and
`assets.font(name, ttf, size, pxrange)` are scanned at build time, staged into
`assets/generated/atlases` and `assets/generated/fonts`, and only those runtime
files are packaged. Aseprite is an external build prerequisite; set `ASEPRITE`
to its command-line executable when it is not discoverable. Source atlas files
and TTFs never ship. Atlas authoring files are single-frame documents with
named slices and a required `invalid` slice. There are no module
identifiers, manifests, dependencies, imported schemas, public-header packages,
or compatibility APIs.

Every content project passes `SIMULATION` (`client` or `server_client`) and
`TICKS_PER_SECOND` (an integer from 1 to 1000) through `engine_add_content` in
its `CMakeLists.txt`. Codegen embeds those values in the content module.

Engine builds export these headers, the content compiler, packaging tools, and
the reusable CMake integration under `out/engine/sdk`. Standalone games consume
that exported SDK and the sibling prebuilt runtime; they do not include engine
source files.
# Content DSL surface

The supported declarations are intentionally prefix-driven: `$s/$c/$r/$sc/$cr/$scr c_*` components, `p_*` prefabs, `e_*` events and handlers, global `g_*` hooks, and `$compute`. Event and update handlers share one component-term grammar. A bare component such as `c_player` requires presence without creating a callback variable; `c_status(*)` does the same for paired instances. Named terms retain `read`, `write`, `mut`, `optional`, and `exclude` forms. Helper structs/enums/constants, meshes, textures, audio, fonts, and input registrations are ordinary C++. Register all runtime assets from the single `content/assets.h` callback; atlas and font source paths must be literals so the build can stage them before compiling the content module. Atlas slice marker types are generated automatically, with qualified `t_<atlas>_<slice>` names and unique short aliases.

`AssetRegistry::audio_distance_scale(0.0f)` makes audio non-spatial: each sound
uses its configured base gain equally in both channels. Positive values enable
the distance curve, and individual `play_spatial_audio` calls may override the
content-wide default.
