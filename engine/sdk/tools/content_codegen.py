"""Compile the mixed C++ content DSL to the sole runtime API."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import struct
import tempfile
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

MAX_TERMS = 8
MAX_EVENT_ROLES = 8
MAX_ATTRIBUTES = 8
RESIDENCY = {"s": 1, "c": 2, "r": 4, "sc": 3, "cr": 6, "scr": 7}
WORLD_ENUM = {"s": "WORLD_SERVER", "c": "WORLD_CLIENT", "r": "WORLD_RENDER"}
ACCESS_ENUM = {
    "read": "ACCESS_READ",
    "write": "ACCESS_WRITE",
    "mut": "ACCESS_READ_WRITE",
}
# A bare component term is a required presence filter.  It deliberately does
# not materialize a column in the generated callback.
PRESENCE_ACCESS = "ACCESS_FILTER"
ACCESS_CPP = {**ACCESS_ENUM, PRESENCE_ACCESS: PRESENCE_ACCESS}
EVENT_ENUM = {
    "e_add": "OBSERVER_ADD",
    "e_set": "OBSERVER_SET",
    "e_remove": "OBSERVER_REMOVE",
}
MATCH_ENUM = {
    "required": "MATCH_REQUIRED",
    "optional": "MATCH_OPTIONAL",
    "exclude": "MATCH_EXCLUDE",
}

# Ordinary helper declarations lifted into the generated header.  This is
# refreshed for every generated module so fields keep their real C++ spelling.
HELPER_TYPE_NAMES: set[str] = set()
HELPER_ALIASES: dict[str, str] = {}
HELPER_CONSTANTS: dict[str, int] = {}


def authority_mask(residency: int) -> int:
    for side in (1, 2, 4):
        if residency & side:
            return side
    return 0


def world_mask(world: str) -> int:
    return RESIDENCY[world]
TYPE_INFO = {
    "uint8": ("uint8", 1, 1, None),
    "int8": ("int8", 1, 1, None),
    "char": ("char", 1, 1, None),
    "bool": ("uint8", 1, 1, None),
    "uint16": ("uint16", 2, 2, None),
    "int16": ("int16", 2, 2, None),
    # The supported content ABI is WebAssembly, where C++ int is 32-bit.
    "int": ("int", 4, 4, "VERTEX_SINT32"),
    "int32": ("int32", 4, 4, "VERTEX_SINT32"),
    "uint32": ("uint32", 4, 4, "VERTEX_UINT32"),
    "uint64": ("uint64", 8, 8, None),
    "entity_id": ("entity_id", 8, 8, None),
    "int64": ("int64", 8, 8, None),
    "float": ("float", 4, 4, "VERTEX_FLOAT32"),
    "double": ("double", 8, 8, None),
    "vec2": ("vec2", 8, 4, "VERTEX_FLOAT32X2"),
    "vec3": ("vec3", 12, 4, "VERTEX_FLOAT32X3"),
    "vec4": ("vec4", 16, 4, "VERTEX_FLOAT32X4"),
    "ivec2": ("ivec2", 8, 4, None),
    "ivec3": ("ivec3", 12, 4, None),
    "ivec4": ("ivec4", 16, 4, None),
    "uvec2": ("uvec2", 8, 4, None),
    "uvec3": ("uvec3", 12, 4, None),
    "uvec4": ("uvec4", 16, 4, None),
    "breakpoint_time": ("breakpoint_time", 16, 8, None),
}
BUILTIN_COMPONENTS = {
    "c_audio_source": {
        "name": "c_audio_source",
        "canonical": "builtin:c_audio_source",
        "size": 1104,
        "alignment": 8,
        "residency": RESIDENCY["r"],
        "authority": RESIDENCY["r"],
        "replicated": False,
        "kind": "component",
        "shader": False,
        "base": None,
        "contract": [],
        "contract_fingerprint": 1,
        "fields": [],
        "fingerprint": 0x8b3f4d1c29a5e701,
    },
}
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
REF_RE = re.compile(r"[a-z][a-z0-9_-]*:[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*")
CONTENT_ID_RE = re.compile(r"[a-z][a-z0-9_-]*\Z")
WGSL_TYPE = {
    "int": "i32",
    "int32": "i32",
    "uint32": "u32",
    "float": "f32",
    "vec2": "vec2f",
    "vec3": "vec3f",
    "vec4": "vec4f",
    "ivec2": "vec2i",
    "ivec3": "vec3i",
    "ivec4": "vec4i",
    "uvec2": "vec2u",
    "uvec3": "vec3u",
    "uvec4": "vec4u",
}


class CodegenError(ValueError):
    pass


@dataclass
class Field:
    type_name: str
    name: str
    array: str | None = None
    count: int = 1
    default: str | None = None
    offset: int = 0
    size: int = 0


@dataclass
class Constant:
    type_name: str
    name: str
    expression: str
    value: int
    source: str


@dataclass
class PodType:
    name: str
    fields: list[Field]
    source: str
    size: int = 0
    alignment: int = 1
    emit: bool = True


@dataclass
class EnumType:
    name: str
    underlying: str
    values: list[tuple[str, str]]
    source: str
    emit: bool = True


@dataclass
class Shader:
    blend: str = "opaque"
    order: int = 0
    textures: list[tuple[str, str]] = field(default_factory=list)
    topology: str = "triangles"
    mesh: str = ""
    wgsl: str = ""
    bridge: list[tuple[str, str]] = field(default_factory=list)
    vertex_body: str = ""
    fragment_body: str = ""

@dataclass
class Texture:
    name: str
    source_path: str
    filter: str
    address: str
    source: str
    slices_path: str = ""
    width: int = 0
    height: int = 0
    slices: list[dict] = field(default_factory=list)
    registered_by_assets: bool = False
    resolved_source: str = ""
    resolved_slices: str = ""


@dataclass
class Component:
    name: str
    residency: int
    fields: list[Field]
    source: str
    shader: Shader | None = None
    size: int = 0
    alignment: int = 1
    fingerprint: int = 0
    contract_fingerprint: int = 0
    base: str = ""
    requirements: list["ContractRequirement"] = field(default_factory=list)
    nested_observers: list["NestedObserver"] = field(default_factory=list)


@dataclass
class ContractRequirement:
    side: str
    observer: str
    required: bool


@dataclass
class NestedObserver:
    side: str
    observer: str
    body: str
    source: str
    order: int = 0


@dataclass
class Compute:
    name: str
    fields: list[Field]
    instance: str
    logic: str
    source: str
    size: int = 0
    alignment: int = 1
    fingerprint: int = 0
    instance_fingerprint: int = 0
    wgsl: str = ""


@dataclass
class Term:
    access: str
    component: str
    variable: str
    match: str = "required"
    pair_wildcard: bool = False
    role: str = ""

    @property
    def presence_only(self) -> bool:
        return not self.variable


@dataclass
class System:
    name: str
    side: str
    terms: list[Term]
    body: str
    source: str
    callback: int = 0
    order: int = 0
    global_hook: bool = False


@dataclass
class Observer:
    name: str
    side: str
    event: str
    terms: list[Term]
    body: str
    source: str
    callback: int = 0
    custom: bool = False
    context_type: str = ""
    order: int = 0


@dataclass
class InitHandler:
    body: str
    source: str
    order: int = 0
    callback: int = 0


@dataclass
class StartHandler:
    side: str
    body: str
    source: str
    order: int = 0
    callback: int = 0


@dataclass
class Event:
    name: str
    residency: int
    fields: list[Field]
    source: str
    size: int = 0
    alignment: int = 1
    members: list[str] = field(default_factory=list)


@dataclass
class EntityValue:
    component: str
    initializer: str
    residency: int = 7
    pair: bool = False


@dataclass
class Entity:
    name: str
    residency: int
    values: list[EntityValue]
    source: str
    callback: int = 0
    uses: list[str] = field(default_factory=list)
    flattened: list[EntityValue] = field(default_factory=list)
    fingerprint: int = 0


@dataclass
class CppSource:
    path: Path
    text: str


@dataclass
class Module:
    content_id: str
    root: Path
    textures: list[Texture] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    computes: list[Compute] = field(default_factory=list)
    constants: list[Constant] = field(default_factory=list)
    pod_types: list[PodType] = field(default_factory=list)
    enum_types: list[EnumType] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    systems: list[System] = field(default_factory=list)
    observers: list[Observer] = field(default_factory=list)
    init_handlers: list[InitHandler] = field(default_factory=list)
    start_handlers: list[StartHandler] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    cpp_sources: list[CppSource] = field(default_factory=list)
    helper_declarations: list[tuple[str, str, str]] = field(default_factory=list)
    has_init_handler: bool = False
    cpp_component_aliases: dict[str, str] = field(default_factory=dict)
    cpp_entity_aliases: dict[str, str] = field(default_factory=dict)
    cpp_texture_aliases: dict[str, str] = field(default_factory=dict)
    cpp_texture_fallbacks: dict[str, str] = field(default_factory=dict)
    simulation: str = "server_client"
    ticks_per_second: int = 30
    project_name: str = "Content"


def validate_setup(
        simulation: str, ticks: int, project_name: str,
        source: str) -> tuple[str, int, str]:
    if simulation not in {"client", "server_client"}:
        raise CodegenError(
            f"{source}: simulation must be 'client' or 'server_client'")
    if isinstance(ticks, bool) or not isinstance(ticks, int) or not 1 <= ticks <= 1000:
        raise CodegenError(
            f"{source}: ticks per second must be an integer from 1 to 1000")
    if not project_name or not project_name.strip():
        raise CodegenError(f"{source}: project name must not be empty")
    if "\x00" in project_name:
        raise CodegenError(f"{source}: project name must not contain NUL")
    return simulation, ticks, project_name


def validate_setup_residency(module: Module) -> None:
    if module.simulation != "client":
        return
    server_mask = 1
    for item in [*module.components, *module.events, *module.entities]:
        if getattr(item, "residency", 0) & server_mask:
            raise CodegenError(
                f"{item.source}: {item.name} uses server residency in client simulation")
    for item in [*module.systems, *module.observers, *module.start_handlers]:
        if getattr(item, "side", 0) == 1:
            raise CodegenError(
                f"{item.source}: server handler is invalid in client simulation")
    for component in module.components:
        for requirement in component.requirements:
            if RESIDENCY[requirement.side] & server_mask:
                raise CodegenError(
                    f"{component.source}: server contract requirement is invalid "
                    "in client simulation")
        for nested in component.nested_observers:
            if RESIDENCY[nested.side] & server_mask:
                raise CodegenError(
                    f"{nested.source}: server component handler is invalid "
                    "in client simulation")


class Parser:
    def __init__(self, text: str, path: Path):
        self.text = text
        self.path = path
        self.i = 0

    def error(self, message: str) -> CodegenError:
        line = self.text.count("\n", 0, self.i) + 1
        last = self.text.rfind("\n", 0, self.i)
        column = self.i - last
        return CodegenError(f"{self.path}:{line}:{column}: {message}")

    def skip(self) -> None:
        while self.i < len(self.text):
            if self.text[self.i].isspace():
                self.i += 1
            elif self.text.startswith("//", self.i):
                end = self.text.find("\n", self.i + 2)
                self.i = len(self.text) if end < 0 else end + 1
            elif self.text.startswith("/*", self.i):
                end = self.text.find("*/", self.i + 2)
                if end < 0:
                    raise self.error("unterminated comment")
                self.i = end + 2
            else:
                break

    def literal(self, value: str) -> None:
        self.skip()
        if not self.text.startswith(value, self.i):
            raise self.error(f"expected {value!r}")
        self.i += len(value)

    def identifier(self, *, reference: bool = False) -> str:
        self.skip()
        match = (REF_RE if reference else IDENT_RE).match(self.text, self.i)
        if not match:
            raise self.error("expected identifier")
        self.i = match.end()
        return match.group(0)

    def handler_order(self) -> int:
        """Parse the optional signed decimal order on an event handler."""
        self.skip()
        if self.i >= len(self.text) or self.text[self.i] != "[":
            return 0
        self.i += 1
        self.skip()
        start = self.i
        if self.i < len(self.text) and self.text[self.i] in "+-":
            self.i += 1
        digits = self.i
        while self.i < len(self.text) and self.text[self.i].isdigit():
            self.i += 1
        if self.i == digits:
            raise self.error(
                "event handler order must be a signed decimal integer")
        value_text = self.text[start:self.i]
        self.skip()
        if self.i >= len(self.text) or self.text[self.i] != "]":
            raise self.error("unterminated event handler order")
        self.i += 1
        try:
            value = int(value_text, 10)
        except ValueError as exc:
            raise self.error("invalid event handler order") from exc
        if value < -(1 << 31) or value > (1 << 31) - 1:
            raise self.error(
                "event handler order is outside signed 32-bit range")
        return value

    def string(self) -> str:
        self.skip()
        if self.i >= len(self.text) or self.text[self.i] != '"':
            raise self.error("expected string")
        start = self.i
        self.i += 1
        while self.i < len(self.text):
            if self.text[self.i] == "\\":
                self.i += 2
                continue
            if self.text[self.i] == '"':
                self.i += 1
                try:
                    value = json.loads(self.text[start:self.i])
                except json.JSONDecodeError as exc:
                    raise self.error("invalid string") from exc
                if not isinstance(value, str):
                    raise self.error("expected string")
                return value
            self.i += 1
        raise self.error("unterminated string")

    def block(self) -> str:
        self.skip()
        if self.i >= len(self.text) or self.text[self.i] != "{":
            raise self.error("expected '{'")
        start = self.i + 1
        depth = 1
        self.i += 1
        quote = ""
        while self.i < len(self.text):
            if quote:
                if self.text[self.i] == "\\":
                    self.i += 2
                    continue
                if self.text[self.i] == quote:
                    quote = ""
                self.i += 1
                continue
            if self.text.startswith("//", self.i):
                end = self.text.find("\n", self.i + 2)
                self.i = len(self.text) if end < 0 else end + 1
                continue
            if self.text.startswith("/*", self.i):
                end = self.text.find("*/", self.i + 2)
                if end < 0:
                    raise self.error("unterminated comment in block")
                self.i = end + 2
                continue
            char = self.text[self.i]
            if char in "\"'":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    result = self.text[start:self.i]
                    self.i += 1
                    return result
            self.i += 1
        raise self.error("unterminated block")

    def semicolon(self) -> None:
        self.literal(";")

    def until_semicolon(self) -> str:
        self.skip()
        start = self.i
        paren = bracket = brace = 0
        quote = ""
        while self.i < len(self.text):
            char = self.text[self.i]
            if quote:
                if char == "\\":
                    self.i += 2
                    continue
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "(":
                paren += 1
            elif char == ")":
                paren -= 1
            elif char == "[":
                bracket += 1
            elif char == "]":
                bracket -= 1
            elif char == "{":
                brace += 1
            elif char == "}":
                brace -= 1
            elif char == ";" and paren == bracket == brace == 0:
                value = self.text[start:self.i].strip()
                self.i += 1
                return value
            self.i += 1
        raise self.error("expected ';'")

    def field_after_type(self, type_name: str) -> Field:
        name = self.identifier()
        self.skip()
        array = None
        if self.i < len(self.text) and self.text[self.i] == "[":
            self.i += 1
            start = self.i
            while self.i < len(self.text) and self.text[self.i] != "]":
                self.i += 1
            if self.i >= len(self.text):
                raise self.error("unterminated array extent")
            array = self.text[start:self.i].strip()
            self.i += 1
            if not array:
                raise self.error("dynamic arrays are not supported")
        self.skip()
        default = None
        if self.i < len(self.text) and self.text[self.i] == "=":
            self.i += 1
            default = self.until_semicolon()
        else:
            self.semicolon()
        return Field(type_name, name, array, 1, default)

    def fields(self) -> list[Field]:
        self.literal("{")
        result: list[Field] = []
        while True:
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "}":
                self.i += 1
                self.semicolon()
                return result
            type_name = self.identifier(reference=True)
            item = self.field_after_type(type_name)
            if any(existing.name == item.name for existing in result):
                raise self.error(f"duplicate field {item.name}")
            result.append(item)

    def event_fields(self) -> tuple[list[Field], list[str]]:
        """Parse the data members of an event payload.

        Event payloads may contain callback-only pointer/handle fields which
        are intentionally outside the ordinary ECS field type table.
        """
        self.literal("{")
        result: list[Field] = []
        members: list[str] = []
        while True:
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "}":
                self.i += 1
                self.semicolon()
                return result, members
            start = self.i
            first = self.identifier(reference=True)
            if first in {"static", "using", "typedef", "struct", "enum", "class"}:
                self.i = start
                members.append(self._consume_cpp_member())
                continue
            type_name = first
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "(":
                self.i = start
                members.append(self._consume_cpp_member())
                continue
            if first == "const":
                type_name = "const " + self.identifier(reference=True)
                self.skip()
            if self.i < len(self.text) and self.text[self.i] == "*":
                self.i += 1
                type_name += "*"
            name = self.identifier()
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "(":
                self.i = start
                members.append(self._consume_cpp_member())
                continue
            array = None
            if self.i < len(self.text) and self.text[self.i] == "[":
                self.i += 1
                extent_start = self.i
                while self.i < len(self.text) and self.text[self.i] != "]":
                    self.i += 1
                if self.i >= len(self.text):
                    raise self.error("unterminated event array extent")
                array = self.text[extent_start:self.i].strip()
                self.i += 1
                if not array:
                    raise self.error("event arrays require a fixed extent")
            self.skip()
            default = None
            if self.i < len(self.text) and self.text[self.i] == "=":
                self.i += 1
                default = self.until_semicolon()
            elif self.i < len(self.text) and self.text[self.i] == "{":
                default = self.block().strip()
                if not default:
                    default = "{}"
                self.semicolon()
            else:
                self.semicolon()
            if any(item.name == name for item in result):
                raise self.error(f"duplicate event field {name}")
            if "&" in type_name or "&&" in type_name:
                raise self.error("event payload references are not supported")
            result.append(Field(type_name, name, array, 1, default))

    def _consume_cpp_member(self) -> str:
        start = self.i
        paren = bracket = 0
        quote = ""
        brace_start = -1
        while self.i < len(self.text):
            char = self.text[self.i]
            if quote:
                if char == "\\":
                    self.i += 2
                    continue
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "(":
                paren += 1
            elif char == ")":
                paren -= 1
            elif char == "[":
                bracket += 1
            elif char == "]":
                bracket -= 1
            elif char == "{" and paren == bracket == 0:
                brace_start = self.i
                self.block()
                self.skip()
                if self.i < len(self.text) and self.text[self.i] == ";":
                    self.i += 1
                return self.text[start:self.i].strip()
            elif char == ";" and paren == bracket == 0:
                self.i += 1
                return self.text[start:self.i].strip()
            self.i += 1
        raise self.error("unterminated event member")

    def component_terms(self, *, allow_roles: bool = False) -> list[Term]:
        """Parse the common component-term grammar used by all handlers."""
        terms: list[Term] = []
        self.literal("(")
        self.skip()
        while self.i < len(self.text) and self.text[self.i] != ")":
            first = self.identifier(reference=True)
            role = ""
            if allow_roles:
                self.skip()
                if self.i < len(self.text) and self.text[self.i] == ":":
                    if first in {"const", "optional", "exclude", *ACCESS_ENUM}:
                        raise self.error("event roles must prefix the complete term")
                    role = first
                    self.i += 1
                    first = self.identifier(reference=True)
            else:
                self.skip()
                if self.i < len(self.text) and self.text[self.i] == ":":
                    raise self.error("event roles are only valid for custom events")
            match = "required"
            if first == "optional":
                match = "optional"
                access = self.identifier()
                component = self.identifier(reference=True)
                pair_wildcard = self._pair_wildcard()
                self.skip()
                if self.i >= len(self.text) or self.text[self.i] in ",)":
                    raise self.error("optional terms require a variable name")
                variable = self.identifier()
            elif first == "exclude":
                access = "read"
                match = "exclude"
                component = self.identifier(reference=True)
                pair_wildcard = self._pair_wildcard()
                variable = ""
            elif first == "const":
                access = "read"
                component = self.identifier(reference=True)
                pair_wildcard = self._pair_wildcard()
                self.literal("&")
                variable = self.identifier()
            elif first in ACCESS_ENUM:
                access = first
                component = self.identifier(reference=True)
                pair_wildcard = self._pair_wildcard()
                variable = self.identifier()
            else:
                component = first
                pair_wildcard = self._pair_wildcard()
                self.skip()
                # A bare component (including a bare pair wildcard) is a
                # required presence-only term.  It matches without exposing
                # storage or a target variable to the callback.
                if self.i >= len(self.text) or self.text[self.i] in ",)":
                    access = PRESENCE_ACCESS
                    variable = ""
                    if role and pair_wildcard:
                        raise self.error("event roles cannot qualify pair wildcard terms")
                    terms.append(Term(access, component, variable, match,
                                      pair_wildcard, role))
                    self.skip()
                    if self.i < len(self.text) and self.text[self.i] == ",":
                        self.i += 1
                    elif self.i >= len(self.text) or self.text[self.i] != ")":
                        raise self.error("expected ',' or ')' in term list")
                    continue
                if self.i < len(self.text) and self.text[self.i] == "&":
                    self.i += 1
                    access = "mut"
                else:
                    access = "read"
                variable = self.identifier()
            if access not in ACCESS_ENUM and access != PRESENCE_ACCESS:
                raise self.error("term access must be read, write, or mut")
            if role and pair_wildcard:
                raise self.error("event roles cannot qualify pair wildcard terms")
            terms.append(Term(access, component, variable, match,
                              pair_wildcard, role))
            self.skip()
            if self.text[self.i] == ",":
                self.i += 1
            elif self.text[self.i] != ")":
                raise self.error("expected ',' or ')' in term list")
        self.literal(")")
        if len(terms) > MAX_TERMS:
            raise self.error(f"at most {MAX_TERMS} terms are supported")
        if len({(term.role, term.component) for term in terms}) != len(terms):
            raise self.error("duplicate component term")
        return terms

    def _pair_wildcard(self) -> bool:
        self.skip()
        if self.text[self.i:self.i + 3] == "(*)":
            self.i += 3
            return True
        return False

    def shader(self) -> Shader:
        self.literal("{")
        shader = Shader()
        seen: set[str] = set()
        while True:
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "}":
                self.i += 1
                self.semicolon()
                break
            key = self.identifier()
            if key in seen and key != "texture":
                raise self.error(f"duplicate shader section {key}")
            seen.add(key)
            if key == "blend":
                shader.blend = self.identifier()
                if shader.blend not in ("opaque", "alpha"):
                    raise self.error("blend must be opaque or alpha")
                self.semicolon()
            elif key == "texture":
                binding = self.identifier(reference=True)
                self.skip()
                if self.i < len(self.text) and self.text[self.i] == "=":
                    self.i += 1
                    texture = self.identifier(reference=True)
                else:
                    texture = binding
                    binding = "texture"
                if len(shader.textures) >= 8:
                    raise self.error("at most eight shader textures are supported")
                if any(name == binding for name, _ in shader.textures):
                    raise self.error(f"duplicate shader texture binding {binding}")
                shader.textures.append((binding, texture))
                self.semicolon()
            elif key == "topology":
                shader.topology = self.identifier()
                if shader.topology not in ("triangles", "lines"):
                    raise self.error("topology must be triangles or lines")
                self.semicolon()
            elif key == "mesh":
                shader.mesh = self.identifier(reference=True)
                self.semicolon()
            elif key == "order":
                expression = self.until_semicolon()
                try:
                    shader.order = int(expression, 10)
                except ValueError as exc:
                    raise self.error("shader order must be an integer literal") from exc
                if shader.order < -32768 or shader.order > 32767:
                    raise self.error("shader order is out of range")
            elif key == "logic":
                shader.bridge, shader.vertex_body, shader.fragment_body = parse_shader_logic(
                    self.block(), self.path)
                self.semicolon()
            else:
                if key == "attributes":
                    raise self.error("shader attributes are derived automatically from component fields")
                raise self.error(f"unknown shader section {key}")
        if not shader.vertex_body or not shader.fragment_body:
            raise self.error("shader requires logic")
        if shader.topology == "lines" and not shader.mesh:
            raise self.error("line shaders require a mesh")
        return shader

    def texture(self, name: str, source: str, atlas: bool) -> Texture:
        self.literal("{")
        source_path = ""
        slices_path = ""
        filter_mode = "nearest"
        address = "clamp"
        seen: set[str] = set()
        while True:
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "}":
                self.i += 1
                self.semicolon()
                break
            key = self.identifier()
            if key in seen:
                raise self.error(f"duplicate texture section {key}")
            seen.add(key)
            if key == "source":
                source_path = self.string()
            elif key == "slices" and atlas:
                slices_path = self.string()
            elif key == "filter":
                filter_mode = self.identifier()
            elif key == "address":
                address = self.identifier()
            else:
                raise self.error(f"unknown texture section {key}")
            self.semicolon()
        if not source_path:
            raise self.error("texture requires source")
        if atlas and not slices_path:
            raise self.error("atlas requires slices")
        if filter_mode not in {"nearest", "linear"}:
            raise self.error("filter must be nearest or linear")
        if address not in {"clamp", "repeat"}:
            raise self.error("address must be clamp or repeat")
        return Texture(
            name, source_path, filter_mode, address, source,
            slices_path=slices_path)

    def component(
            self, residency: str, name: str, source: str,
            base: str = "") -> Component:
        self.literal("{")
        fields: list[Field] = []
        shader = None
        requirements: list[ContractRequirement] = []
        nested_observers: list[NestedObserver] = []
        side_names = {"s": "s", "c": "c", "r": "r"}
        while True:
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "}":
                self.i += 1
                self.semicolon()
                return Component(
                    name, RESIDENCY[residency], fields, source, shader,
                    base=base, requirements=requirements,
                    nested_observers=nested_observers)
            first = self.identifier(reference=True)
            if first in {"require", "optional"}:
                side_name = self.identifier()
                if side_name not in side_names:
                    raise self.error(
                        "contract observer world must be s, c, or r")
                observer = self.identifier(reference=True)
                if not observer.split(":")[-1].startswith("e_"):
                    raise self.error("contract event names must start with e_")
                # Keep the complete e_ name for generated C++ types and IDs.
                self.semicolon()
                requirements.append(ContractRequirement(
                    side_names[side_name], observer, first == "require"))
                continue
            if first in side_names:
                observer = self.identifier(reference=True)
                if not observer.split(":")[-1].startswith("e_"):
                    raise self.error("nested event names must start with e_")
                # Keep the complete e_ name for generated C++ types and IDs.
                order = self.handler_order()
                body = self.block().strip()
                self.semicolon()
                nested_observers.append(NestedObserver(
                    side_names[first], observer, body, source, order))
                continue
            if first.startswith("g_"):
                raise self.error("global hooks must be declared at top level")
            if first == "shader":
                if shader:
                    raise self.error("component may define only one shader")
                shader = self.shader()
                continue
            item = self.field_after_type(first)
            if any(existing.name == item.name for existing in fields):
                raise self.error(f"duplicate field {item.name}")
            fields.append(item)

    def compute(self, name: str, source: str) -> Compute:
        self.literal("{")
        fields: list[Field] | None = None
        instance = ""
        logic = ""
        while True:
            self.skip()
            if self.i < len(self.text) and self.text[self.i] == "}":
                self.i += 1
                self.semicolon()
                break
            section = self.identifier()
            if section == "state":
                if fields is not None:
                    raise self.error("compute may define only one state block")
                fields = self.fields()
            elif section == "instance":
                if instance:
                    raise self.error("compute may define only one instance")
                instance = self.identifier(reference=True)
                self.semicolon()
            elif section == "logic":
                if logic:
                    raise self.error("compute may define only one logic block")
                logic = self.block().strip()
                self.semicolon()
            else:
                raise self.error(f"unknown compute section {section}")
        if fields is None or not fields:
            raise self.error("compute requires a non-empty state block")
        if not instance:
            raise self.error("compute requires an instance component")
        if not logic:
            raise self.error("compute requires logic")
        return Compute(name, fields, instance, logic, source)

    def entity_body(self) -> tuple[list[str], list[EntityValue]]:
        body = Parser(self.block(), self.path)
        uses: list[str] = []
        values: list[EntityValue] = []
        side_names = {"s": 1, "c": 2, "r": 4}
        while True:
            body.skip()
            if body.i >= len(body.text):
                break
            first = body.identifier(reference=True)
            if first == "use":
                uses.append(body.identifier(reference=True))
                body.semicolon()
                continue
            residency = 7
            is_pair = first == "pair"
            if is_pair:
                first = body.identifier(reference=True)
            if first in side_names:
                residency = side_names[first]
                component = body.identifier(reference=True)
            else:
                component = first
            initializer = body.block().strip()
            body.semicolon()
            values.append(EntityValue(component, initializer, residency, is_pair))
        return uses, values

    def declaration(self) -> object:
        declaration_line = self.text.count("\n", 0, self.i) + 1
        self.literal("$")
        source = str(self.path)
        # Worldless one-time initialization is a global lifecycle hook.
        # It deliberately has no residency prefix because it runs before
        # worlds exist, while the registries are still being staged.
        self.skip()
        if self.text.startswith("g_init", self.i) and not re.match(
                r"[A-Za-z0-9_]", self.text[self.i + len("g_init"):self.i + len("g_init") + 1]):
            self.i += len("g_init")
            order = self.handler_order()
            body = self.block().strip()
            self.semicolon()
            return InitHandler(body, source, order)
        if self.text.startswith("e_init", self.i) and not re.match(
                r"[A-Za-z0-9_]", self.text[self.i + len("e_init"):self.i + len("e_init") + 1]):
            raise self.error("e_init was renamed to g_init")
        residency = self.identifier()
        if residency in {"texture", "atlas"}:
            name = self.identifier()
            return self.texture(name, source, residency == "atlas")
        if residency == "compute":
            return self.compute(self.identifier(), source)
        if residency == "const":
            type_name = self.identifier(reference=True)
            name = self.identifier()
            self.literal("=")
            expression = self.until_semicolon()
            return Constant(type_name, name, expression, 0, source)
        if residency == "struct":
            name = self.identifier()
            return PodType(name, self.fields(), source)
        if residency == "enum":
            underlying = self.identifier()
            name = self.identifier()
            self.literal("{")
            values: list[tuple[str, str]] = []
            while True:
                self.skip()
                if self.i < len(self.text) and self.text[self.i] == "}":
                    self.i += 1
                    self.semicolon()
                    break
                value_name = self.identifier()
                self.literal("=")
                start = self.i
                while self.i < len(self.text) and self.text[self.i] not in ",}":
                    self.i += 1
                expression = self.text[start:self.i].strip()
                values.append((value_name, expression))
                self.skip()
                if self.i < len(self.text) and self.text[self.i] == ",":
                    self.i += 1
            return EnumType(name, underlying, values, source)
        if residency not in RESIDENCY:
            raise self.error(f"invalid residency {residency}")
        kind_or_name = self.identifier()
        if kind_or_name in {"system", "observer"} or kind_or_name.startswith("o_"):
            raise self.error("system/observer syntax was removed; use e_ event declarations")
        if kind_or_name.startswith("g_"):
            if kind_or_name == "g_init":
                raise self.error("g_init is worldless; omit the residency prefix")
            if kind_or_name not in {"g_start", "g_update"}:
                raise self.error("unknown global hook; expected g_start or g_update")
            order = self.handler_order()
            body = self.block().strip()
            self.semicolon()
            if kind_or_name == "g_start":
                return StartHandler(residency, body, source, order)
            return System(
                f"__{self.path.stem}_global_update_{declaration_line}",
                residency, [], body, source, order=order, global_hook=True)
        if kind_or_name.startswith("e_"):
            if residency not in WORLD_ENUM:
                raise self.error("events require exactly one of s, c, or r")
            event = kind_or_name
            self.skip()
            if event == "e_init":
                raise self.error("e_init was renamed to g_init; omit the residency prefix")
            if event == "e_start":
                raise self.error("e_start was renamed to g_start")
            if self.i < len(self.text) and self.text[self.i] == "{":
                if event in {"e_update", "e_add", "e_set", "e_remove"}:
                    raise self.error(f"{event} is a built-in event and cannot define a payload")
                fields, members = self.event_fields()
                return Event(event, RESIDENCY[residency], fields, source, members=members)
            order = self.handler_order()
            terms = self.component_terms(
                allow_roles=event not in EVENT_ENUM and event != "e_update")
            if not terms:
                if event == "e_update":
                    raise self.error("empty e_update was replaced by g_update")
                raise self.error("event handlers require at least one component term")
            body = self.block().strip()
            self.semicolon()
            if event == "e_update":
                return System(
                    f"__{self.path.stem}_update_{declaration_line}",
                    residency, terms, body, source, order=order)
            return Observer(
                f"__{self.path.stem}_event_{declaration_line}",
                residency, event, terms, body, source,
                custom=event not in EVENT_ENUM, order=order)
        if kind_or_name == "entity":
            raise self.error("entity syntax was removed; use p_ prefabs")
        if kind_or_name.startswith("p_"):
            uses, values = self.entity_body()
            self.semicolon()
            return Entity(
                kind_or_name, RESIDENCY[residency], values, source, uses=uses)
        if kind_or_name == "startup":
            raise self.error(
                "startup declarations are not supported; use g_start")
        if kind_or_name == "event":
            raise self.error("event syntax was removed; use e_ declarations")
        self.skip()
        base = ""
        if self.i < len(self.text) and self.text[self.i] == ":":
            self.i += 1
            base = self.identifier(reference=True)
        return self.component(residency, kind_or_name, source, base)

    def declarations(self) -> list[object]:
        result: list[object] = []
        while True:
            self.skip()
            if self.i >= len(self.text):
                return result
            result.append(self.declaration())


def parse_shader_logic(text: str, path: Path) -> tuple[list[tuple[str, str]], str, str]:
    parser = Parser(text, path)
    bridge: list[tuple[str, str]] | None = None
    vertex = ""
    fragment = ""
    while True:
        parser.skip()
        if parser.i >= len(parser.text):
            break
        section = parser.identifier()
        if section == "bridge":
            if bridge is not None:
                raise parser.error("duplicate WGSL bridge block")
            bridge = []
            parser.literal("{")
            while True:
                parser.skip()
                if parser.i < len(parser.text) and parser.text[parser.i] == "}":
                    parser.i += 1
                    break
                name = parser.identifier()
                parser.literal(":")
                type_name = parser.identifier()
                if type_name not in {"f32", "vec2f", "vec3f", "vec4f", "i32", "u32"}:
                    raise parser.error(f"unsupported bridge type {type_name}")
                if name == "position" or any(existing == name for existing, _ in bridge):
                    raise parser.error(f"reserved or duplicate bridge field {name}")
                bridge.append((name, type_name))
                parser.literal(",")
            parser.semicolon()
        elif section == "vertex":
            if vertex:
                raise parser.error("duplicate WGSL vertex block")
            vertex = parser.block().strip()
        elif section == "fragment":
            if fragment:
                raise parser.error("duplicate WGSL fragment block")
            fragment = parser.block().strip()
        else:
            raise parser.error(f"unknown WGSL section {section}")
        parser.skip()
        if parser.i < len(parser.text) and parser.text[parser.i] == ";":
            parser.i += 1
    if bridge is None:
        raise parser.error("WGSL requires a bridge block")
    if len(bridge) > MAX_ATTRIBUTES:
        raise parser.error(f"at most {MAX_ATTRIBUTES} bridge fields are supported")
    if not vertex or not fragment:
        raise parser.error("WGSL requires vertex and fragment blocks")
    return bridge, vertex, fragment


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


def evaluate_integer(expression: str, constants: dict[str, int], source: str) -> int:
    parse_expression = expression
    parse_constants = dict(constants)
    for index, name in enumerate(
            sorted((name for name in constants if ":" in name), key=len, reverse=True)):
        replacement = f"__qualified_constant_{index}"
        parse_expression = re.sub(
            rf"(?<![A-Za-z0-9_:-]){re.escape(name)}(?![A-Za-z0-9_:-])",
            replacement, parse_expression)
        parse_constants[replacement] = constants[name]
    try:
        node = ast.parse(parse_expression, mode="eval")
    except SyntaxError as error:
        raise CodegenError(f"{source}: invalid integer expression {expression!r}") from error

    def visit(value: ast.AST) -> int:
        if isinstance(value, ast.Expression):
            return visit(value.body)
        if isinstance(value, ast.Constant) and isinstance(value.value, int):
            return value.value
        if isinstance(value, ast.Name) and value.id in parse_constants:
            return parse_constants[value.id]
        if isinstance(value, ast.UnaryOp) and isinstance(value.op, (ast.UAdd, ast.USub)):
            result = visit(value.operand)
            return result if isinstance(value.op, ast.UAdd) else -result
        if isinstance(value, ast.BinOp) and isinstance(
                value.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Div, ast.Mod)):
            left, right = visit(value.left), visit(value.right)
            if isinstance(value.op, ast.Add): return left + right
            if isinstance(value.op, ast.Sub): return left - right
            if isinstance(value.op, ast.Mult): return left * right
            if right == 0:
                raise CodegenError(f"{source}: division by zero in integer expression")
            if isinstance(value.op, (ast.Div, ast.FloorDiv)): return left // right
            return left % right
        raise CodegenError(f"{source}: unsupported integer expression {expression!r}")

    result = visit(node)
    if result < -(1 << 63) or result >= (1 << 64):
        raise CodegenError(f"{source}: integer expression is out of range")
    return result


def calculate_layout(
        value: Component | PodType | Event | Compute,
        type_records: dict[str, dict], constants: dict[str, int]) -> None:
    if isinstance(value, Event):
        # Event payloads may contain callback-only pointers and handles. Their
        # authoritative ABI layout is taken from the generated C++ type.
        for item in value.fields:
            item.count = 1
        value.alignment = 0
        value.size = 0
        return
    offset = 0
    alignment = 1
    for item in value.fields:
        resolved_type = item.type_name
        seen_aliases: set[str] = set()
        while resolved_type in HELPER_ALIASES:
            if resolved_type in seen_aliases:
                raise CodegenError(f"{value.source}: cyclic helper alias {resolved_type}")
            seen_aliases.add(resolved_type)
            resolved_type = HELPER_ALIASES[resolved_type]
        if resolved_type in TYPE_INFO:
            size, field_alignment = TYPE_INFO[resolved_type][1:3]
        else:
            record = type_records.get(resolved_type)
            if not record:
                raise CodegenError(f"{value.source}: unknown field type {item.type_name}")
            if record.get("kind") == "tag":
                raise CodegenError(f"{value.source}: tag {item.type_name} cannot be embedded")
            size, field_alignment = record["size"], record["alignment"]
        item.count = evaluate_integer(item.array, constants, value.source) if item.array else 1
        if item.count <= 0 or item.count > (1 << 20):
            raise CodegenError(f"{value.source}: invalid array extent for {item.name}")
        item.size = size * item.count
        offset = align_up(offset, field_alignment)
        item.offset = offset
        offset += item.size
        alignment = max(alignment, field_alignment)
        if offset > (1 << 20):
            raise CodegenError(f"{value.source}: POD layout exceeds 1 MiB")
    value.alignment = alignment
    value.size = align_up(offset, alignment)


def field_record(item: Field, content_id: str | None = None) -> dict:
    type_name = item.type_name
    opaque = type_name.endswith("*") or type_name in {"entity", "ui_stream"}
    if (content_id and type_name not in TYPE_INFO
            and type_name not in HELPER_TYPE_NAMES
            and ":" not in type_name and not opaque):
        type_name = f"{content_id}:{type_name}"
    return {
        "name": item.name,
        "type": type_name,
        "count": item.count,
        "offset": item.offset,
        "size": item.size,
        "default": item.default,
    }

def schema_fingerprint(value: dict) -> int:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result = int.from_bytes(hashlib.sha256(encoded).digest()[:8], "little")
    return result or 1


def component_record(content_id: str, component: Component) -> dict:
    return {
        "name": component.name,
        "canonical": f"{content_id}:{component.name}",
        "size": component.size,
        "alignment": component.alignment,
        "residency": component.residency,
        "authority": authority_mask(component.residency),
        "replicated": component.residency not in (1, 2, 4),
        "stable_entity_references": any(
            item.type_name == "entity_id" for item in component.fields),
        "kind": "tag" if not component.fields else "component",
        "shader": component.shader is not None,
        "shader_topology": (
            component.shader.topology if component.shader else None),
        "shader_mesh": (
            component.shader.mesh if component.shader else None),
        "base": (
            component.base if ":" in component.base
            else f"{content_id}:{component.base}"
        ) if component.base else None,
        "contract": [
            {
                "world": item.side,
                "observer": item.observer,
                "required": item.required,
            }
            for item in component.requirements
        ],
        "contract_fingerprint": component.contract_fingerprint,
        "fields": [field_record(item, content_id) for item in component.fields],
        "fingerprint": component.fingerprint,
    }


def event_record(content_id: str, event: Event) -> dict:
    fields = [field_record(item, content_id) for item in event.fields]
    roles = [
        {"name": item.name}
        for item in event.fields
        if item.type_name == "entity_id" and item.count == 1
    ]
    return {
        "kind": "event",
        "name": event.name,
        "canonical": f"{content_id}:{event.name}",
        "size": event.size,
        "alignment": event.alignment,
        "residency": event.residency,
        "stable_entity_references": any(
            item.type_name == "entity_id" for item in event.fields),
        "fields": fields,
        "roles": roles,
        "members": list(event.members),
        "fingerprint": schema_fingerprint({
            "canonical": f"{content_id}:{event.name}",
            "size": event.size,
            "alignment": event.alignment,
            "residency": event.residency,
            "fields": fields,
        }),
    }


def compute_record(content_id: str, compute: Compute) -> dict:
    instance = compute.instance if ":" in compute.instance \
        else f"{content_id}:{compute.instance}"
    return {
        "name": compute.name,
        "canonical": f"{content_id}:{compute.name}",
        "state_size": compute.size,
        "state_alignment": compute.alignment,
        "state_fields": [field_record(item, content_id) for item in compute.fields],
        "state_fingerprint": compute.fingerprint,
        "instance": instance,
        "instance_fingerprint": compute.instance_fingerprint,
    }


def api_document(module: Module) -> dict:
    return {
        "content": module.content_id,
        "textures": [
            {
                "name": item.name,
                "canonical": f"{module.content_id}:{item.name}",
                "source": item.source_path,
                "slices_source": item.slices_path or None,
                "filter": item.filter,
                "address": item.address,
                "width": item.width,
                "height": item.height,
                "kind": "atlas" if item.slices_path else "texture",
                "slices": [
                    {**slice_item,
                     "marker_name": f"{item.name}_{slice_item['name']}"}
                    for slice_item in item.slices],
            }
            for item in module.textures
        ],
        "constants": [
            {"name": item.name, "type": item.type_name, "value": item.value}
            for item in module.constants
        ],
        "types": [
            {
                "kind": "struct", "name": item.name,
                "canonical": f"{module.content_id}:{item.name}",
                "size": item.size, "alignment": item.alignment,
                "fields": [field_record(field, module.content_id) for field in item.fields],
            }
            for item in module.pod_types
        ] + [
            {
                "kind": "enum", "name": item.name,
                "canonical": f"{module.content_id}:{item.name}",
                "underlying": item.underlying,
                "values": [{"name": name, "value": expression}
                           for name, expression in item.values],
                "size": TYPE_INFO[item.underlying][1],
                "alignment": TYPE_INFO[item.underlying][2],
            }
            for item in module.enum_types
        ],
        "components": [component_record(module.content_id, item) for item in module.components],
        "computes": [compute_record(module.content_id, item) for item in module.computes],
        "events": [event_record(module.content_id, item) for item in module.events],
        "entities": [
            {
                "name": item.name, "canonical": f"{module.content_id}:{item.name}",
                "residency": item.residency,
                "fingerprint": item.fingerprint,
                "values": [
                    {
                        "component": value.component,
                        "initializer": value.initializer,
                        "residency": value.residency,
                    }
                    for value in item.flattened
                ],
            }
            for item in module.entities
        ],
    }


def cpp_name(canonical: str, current_content: str) -> str:
    if ":" in canonical:
        content_id, name = canonical.split(":", 1)
    else:
        content_id, name = current_content, canonical
    if name in BUILTIN_COMPONENTS:
        return name
    return f"content_{name}"


def runtime_name(canonical: str) -> str:
    """Return the sole content registry name from an internal schema key."""
    return canonical.split(":", 1)[-1]


def find_dsl_start(text: str, start: int, path: Path) -> int:
    """Find the next top-level DSL declaration without interpreting C++."""
    i = start
    braces = parentheses = brackets = 0
    line_start = start == 0 or text[start - 1] == "\n"
    while i < len(text):
        if text.startswith("//", i):
            end = text.find("\n", i + 2)
            if end < 0:
                return -1
            i = end + 1
            line_start = True
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                line = text.count("\n", 0, i) + 1
                raise CodegenError(f"{path}:{line}:1: unterminated C++ comment")
            line_start = "\n" in text[i:end + 2]
            i = end + 2
            continue
        raw = re.match(r'(?:u8|u|U|L)?R"([^ ()\\\t\r\n]{0,16})\(', text[i:])
        if raw:
            delimiter = raw.group(1)
            end = text.find(")" + delimiter + '"', i + raw.end())
            if end < 0:
                line = text.count("\n", 0, i) + 1
                raise CodegenError(f"{path}:{line}:1: unterminated C++ raw string")
            token_end = end + len(delimiter) + 2
            line_start = "\n" in text[i:token_end]
            i = token_end
            continue
        char = text[i]
        if char in "\"'":
            quote = char
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            else:
                line = text.count("\n", 0, i) + 1
                raise CodegenError(f"{path}:{line}:1: unterminated C++ literal")
            line_start = False
            continue
        if line_start and char in " \t\r":
            i += 1
            continue
        if line_start and char == "#":
            while i < len(text):
                end = text.find("\n", i)
                if end < 0:
                    return -1
                continuation = end > i and text[end - 1] == "\\"
                i = end + 1
                if not continuation:
                    break
            line_start = True
            continue
        if char == "\n":
            line_start = True
            i += 1
            continue
        line_start = False
        if char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
        elif char == "(":
            parentheses += 1
        elif char == ")":
            parentheses -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "$":
            if braces == parentheses == brackets == 0:
                return i
            line = text.count("\n", 0, i) + 1
            column = i - text.rfind("\n", 0, i)
            raise CodegenError(
                f"{path}:{line}:{column}: DSL declarations must be at C++ top level")
        if braces < 0 or parentheses < 0 or brackets < 0:
            line = text.count("\n", 0, i) + 1
            raise CodegenError(f"{path}:{line}:1: unmatched C++ delimiter")
        i += 1
    if braces or parentheses or brackets:
        line = text.count("\n", 0, len(text)) + 1
        raise CodegenError(f"{path}:{line}:1: unterminated C++ declaration")
    return -1


def parse_mixed_source(path: Path) -> tuple[list[object], str]:
    text = path.read_text(encoding="utf-8")
    # The active language is intentionally small.  Constants, helper structs,
    # enums, textures, and input/mesh registration are ordinary C++ now.
    removed = re.search(
        r"\$\s*(?:texture|const|event|entity|observer|struct|enum|atlas)\b",
        text)
    if removed:
        line = text.count("\n", 0, removed.start()) + 1
        raise CodegenError(
            f"{path}:{line}: removed DSL declaration; use ordinary C++ asset registration")
    named_system = re.search(r"\$\s*(?:s|c|r|sc|cr|scr)\s+system\s+[A-Za-z_]", text)
    if named_system:
        line = text.count("\n", 0, named_system.start()) + 1
        raise CodegenError(f"{path}:{line}: systems are anonymous; omit the system name")
    parser = Parser(text, path)
    declarations: list[object] = []
    masked = list(text)
    position = 0
    while True:
        start = find_dsl_start(text, position, path)
        if start < 0:
            break
        parser.i = start
        declarations.append(parser.declaration())
        end = parser.i
        for index in range(start, end):
            if masked[index] not in "\r\n":
                masked[index] = " "
        position = end
    return declarations, "".join(masked)


def scan_helper_declarations(text: str, path: Path) -> tuple[list[tuple[str, str, str]], str]:
    """Lift top-level helper structs/enums from a mixed content file.

    DSL bodies and ordinary function bodies are already masked or remain at
    nonzero brace depth, so only global declarations are considered.  The raw
    declaration is retained for the generated header while the implementation
    copy is blanked to avoid duplicate definitions.
    """
    helpers: list[tuple[str, str, str]] = []
    code = list(text)
    # Remove comments and string/character literals from the scanner while
    # retaining newlines and source positions.
    i = 0
    while i < len(code):
        if text.startswith("//", i):
            end = text.find("\n", i + 2)
            end = len(text) if end < 0 else end
            for j in range(i, end):
                if code[j] != "\n": code[j] = " "
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise CodegenError(f"{path}: unterminated comment")
            for j in range(i, end + 2):
                if code[j] != "\n": code[j] = " "
            i = end + 2
        elif text[i] in {'\"', "'"}:
            quote = text[i]
            i += 1
            while i < len(code):
                if text[i] == "\\":
                    code[i] = " "
                    if i + 1 < len(code): code[i + 1] = " "
                    i += 2
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    if code[i] != "\n": code[i] = " "
                    i += 1
        else:
            i += 1
    scan = "".join(code)
    depth = 0
    i = 0
    while i < len(scan):
        if depth == 0 and re.match(r"template\b", scan[i:]):
            brace = scan.find("{", i)
            if brace >= 0:
                parser = Parser(text, path)
                parser.i = brace
                parser.block()
                i = parser.i
                while i < len(scan) and scan[i].isspace():
                    i += 1
                if i < len(scan) and scan[i] == ";":
                    i += 1
                continue
        if scan[i] == "{":
            depth += 1
            i += 1
            continue
        if scan[i] == "}":
            depth = max(0, depth - 1)
            i += 1
            continue
        if depth != 0:
            i += 1
            continue
        alias_match = re.match(
            r"using\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);", scan[i:])
        if alias_match:
            name = alias_match.group(1)
            helpers.append((name, "alias", text[i:i + alias_match.end()].strip()))
            i += alias_match.end()
            continue
        constant_match = re.match(
            r"inline\s+constexpr\s+([A-Za-z_][A-Za-z0-9_]*)\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;\n]+);", scan[i:])
        if constant_match:
            name = constant_match.group(2)
            helpers.append((name, "constant", text[i:i + constant_match.end()].strip()))
            i += constant_match.end()
            continue
        match = re.match(
            r"(?:struct|enum(?:\s+class)?)\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^\{]+)?\{", scan[i:])
        if not match:
            i += 1
            continue
        start = i
        name = match.group(1)
        brace = i + match.end() - 1
        parser = Parser(text, path)
        parser.i = brace
        body = parser.block()
        end = parser.i
        while end < len(text) and text[end].isspace():
            end += 1
        if end >= len(text) or text[end] != ";":
            raise CodegenError(f"{path}: helper declaration {name} must end with ';'")
        end += 1
        raw = text[start:end].strip()
        kind = "enum" if scan[start:].lstrip().startswith("enum") else "struct"
        helpers.append((name, kind, raw))
        i = end
    return helpers, text


def parse_helper_metadata(
        declarations: list[tuple[str, str, str]], path: Path
        ) -> tuple[list[PodType], list[EnumType]]:
    pods: list[PodType] = []
    enums: list[EnumType] = []
    for name, kind, raw in declarations:
        if kind == "alias":
            continue
        if kind == "struct":
            parser = Parser(raw, path)
            brace = raw.find("{")
            parser.i = brace
            body = parser.block()
            fields, _members = Parser("{" + body + "};", path).event_fields()
            if any(field.type_name.startswith(("c_", "e_", "p_"))
                   for field in fields):
                raise CodegenError(
                    f"{path}: helper type {name} cannot depend on generated ECS types")
            pods.append(PodType(name, fields, str(path), emit=False))
        else:
            match = re.match(
                r"enum(?:\s+class)?\s+" + re.escape(name) +
                r"(?:\s*:\s*([A-Za-z_][A-Za-z0-9_]*))?\s*\{", raw)
            underlying = match.group(1) if match and match.group(1) else "int32"
            body = raw[raw.find("{") + 1:raw.rfind("}")]
            values: list[tuple[str, str]] = []
            for item in body.split(","):
                item = item.strip()
                if not item: continue
                if "=" in item:
                    value_name, expression = item.split("=", 1)
                    values.append((value_name.strip(), expression.strip()))
                else:
                    values.append((item, str(len(values))))
            enums.append(EnumType(name, underlying, values, str(path), emit=False))
    return pods, enums


def load_module(
        content_root: Path,
        asset_manifest: Path | None = None,
        simulation: str = "server_client",
        ticks_per_second: int = 30,
        project_name: str = "Content") -> Module:
    # The internal identifier keeps generated C++ names deterministic. It is
    # not package metadata and is never negotiated at runtime.
    module = Module("content", content_root)
    module.simulation, module.ticks_per_second, module.project_name = validate_setup(
        simulation, ticks_per_second, project_name, "content build configuration")
    global HELPER_TYPE_NAMES, HELPER_ALIASES, HELPER_CONSTANTS
    HELPER_TYPE_NAMES = set()
    HELPER_ALIASES = {}
    HELPER_CONSTANTS = {}
    source_root = content_root / "content"
    for path in sorted(source_root.rglob("*.h"), key=lambda item: item.relative_to(source_root).as_posix()):
        declarations, cpp_source = parse_mixed_source(path)
        helpers, cpp_source = scan_helper_declarations(cpp_source, path)
        if helpers:
            module.helper_declarations.extend(helpers)
        if cpp_source.strip():
            module.cpp_sources.append(CppSource(path, cpp_source))
            if re.search(r'\bcontent_register_audio\s*\(', cpp_source):
                raise CodegenError(
                    f"{path}: content_register_audio was removed; register audio in g_init")
            if re.search(r'\bcontent_register_assets\s*\(', cpp_source):
                raise CodegenError(
                    f"{path}: content_register_assets was removed; move registrations into g_init")
            if re.search(r'\bcontent_register_inputs\s*\(', cpp_source):
                raise CodegenError(
                    f"{path}: content_register_inputs was removed; move bindings into g_init")
            if re.search(r'\bcontent_startup\s*\(', cpp_source):
                raise CodegenError(
                    f"{path}: content_startup was removed; use g_start")
        for declaration in declarations:
            if isinstance(declaration, Component):
                module.components.append(declaration)
            elif isinstance(declaration, Compute):
                module.computes.append(declaration)
            elif isinstance(declaration, Texture):
                module.textures.append(declaration)
            elif isinstance(declaration, Constant):
                module.constants.append(declaration)
            elif isinstance(declaration, PodType):
                module.pod_types.append(declaration)
            elif isinstance(declaration, EnumType):
                module.enum_types.append(declaration)
            elif isinstance(declaration, Event):
                module.events.append(declaration)
            elif isinstance(declaration, InitHandler):
                # Asset and mesh registration is performed by the generated
                # one-time init callback rather than a hand-written export.
                module.init_handlers.append(declaration)
                module.has_init_handler = True
            elif isinstance(declaration, StartHandler):
                module.start_handlers.append(declaration)
            elif isinstance(declaration, System):
                module.systems.append(declaration)
            elif isinstance(declaration, Observer):
                module.observers.append(declaration)
            elif isinstance(declaration, Entity):
                module.entities.append(declaration)
            else:
                raise CodegenError(f"{path}: unsupported declaration")

    # Only lift helpers that are part of a generated layout.  Unrelated
    # ordinary structs (including containers used by implementation code) stay
    # in the implementation fragment and are never subjected to POD checks.
    helper_map: dict[str, tuple[str, str, str]] = {}
    for helper in module.helper_declarations:
        if helper[0] in helper_map:
            raise CodegenError(f"{helper[2]}: duplicate helper type {helper[0]}")
        helper_map[helper[0]] = helper
    needed: set[str] = set()
    pending = [
        field.type_name for value in
        [*module.components, *module.events]
        for field in value.fields
        if field.type_name not in TYPE_INFO
    ]
    pending.extend(
        token for value in [*module.components, *module.events]
        for field in value.fields
        for token in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", field.array or ""))
    while pending:
        name = pending.pop()
        if name in needed:
            continue
        if name not in helper_map:
            continue
        needed.add(name)
        raw = helper_map[name][2]
        for dependency in helper_map:
            if dependency != name and re.search(rf"\b{re.escape(dependency)}\b", raw):
                pending.append(dependency)
    selected_helpers = [helper_map[name] for name in sorted(needed)]
    module.helper_declarations = selected_helpers
    for name, kind, raw in selected_helpers:
        if kind == "alias":
            match = re.match(
                r"using\s+" + re.escape(name) + r"\s*=\s*([^;]+);", raw)
            if match:
                HELPER_ALIASES[name] = match.group(1).strip()
        elif kind == "constant":
            match = re.match(
                r"inline\s+constexpr\s+([A-Za-z_][A-Za-z0-9_]*)\s+"
                + re.escape(name) + r"\s*=\s*([^;\n]+);", raw)
            if match:
                HELPER_CONSTANTS[name] = evaluate_integer(
                    match.group(2), HELPER_CONSTANTS, str(source_root))
    helper_pods, helper_enums = parse_helper_metadata(selected_helpers, source_root)
    module.pod_types.extend(helper_pods)
    module.enum_types.extend(helper_enums)
    HELPER_TYPE_NAMES.update(needed)
    if selected_helpers:
        for source in module.cpp_sources:
            for _name, _kind, raw in selected_helpers:
                source.text = source.text.replace(raw, "\n" * raw.count("\n"))

    if asset_manifest is not None:
        try:
            manifest = json.loads(asset_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CodegenError(f"invalid content asset manifest {asset_manifest}: {exc}") from exc
        generated_root = Path(manifest.get("generated_root", ""))
        for atlas in manifest.get("atlases", []):
            runtime_png = atlas["runtime_png"]
            runtime_json = atlas["runtime_json"]
            texture = Texture(
                atlas["name"], runtime_png, atlas["filter"], atlas["address"],
                str(asset_manifest), slices_path=runtime_json,
                registered_by_assets=True,
                resolved_source=str(generated_root / "atlases" / Path(runtime_png).name),
                resolved_slices=str(generated_root / "atlases" / Path(runtime_json).name))
            module.textures.append(texture)
        for font in manifest.get("fonts", []):
            runtime_png = font["runtime_png"]
            module.textures.append(Texture(
                font["texture"], runtime_png, "linear", "clamp", str(asset_manifest),
                registered_by_assets=True,
                resolved_source=str(generated_root / "fonts" / Path(runtime_png).name)))
    validate_module(module, {})
    validate_setup_residency(module)
    return module


def validate_asset_path(value: str, source: str) -> Path:
    path = PurePosixPath(value)
    if (not value or "\\" in value or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.as_posix() != value
            or not path.parts or path.parts[0] != "assets"):
        raise CodegenError(f"{source}: unsafe asset path {value!r}")
    return Path(*path.parts)


def png_dimensions(path: Path, source: str) -> tuple[int, int]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CodegenError(f"{source}: missing texture asset {path}") from exc
    if (len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n"
            or data[12:16] != b"IHDR"):
        raise CodegenError(f"{source}: texture source is not a valid PNG")
    width, height = struct.unpack(">II", data[16:24])
    if not 1 <= width <= 8192 or not 1 <= height <= 8192:
        raise CodegenError(f"{source}: PNG dimensions exceed 8192")
    if width * height * 4 > 64 * 1024 * 1024:
        raise CodegenError(f"{source}: decoded PNG exceeds 64 MiB")
    return width, height


def load_atlas_slices(texture: Texture, metadata_path: Path) -> list[dict]:
    try:
        document = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CodegenError(f"{texture.source}: malformed atlas metadata") from exc
    meta = document.get("meta")
    frames = document.get("frames")
    if not isinstance(meta, dict) or not isinstance(frames, (dict, list)):
        raise CodegenError(f"{texture.source}: malformed Aseprite atlas metadata")
    size = meta.get("size")
    if (not isinstance(size, dict)
            or size.get("w") != texture.width
            or size.get("h") != texture.height):
        raise CodegenError(f"{texture.source}: atlas image dimension mismatch")
    if PurePosixPath(str(meta.get("image", ""))).name \
            != PurePosixPath(texture.source_path).name:
        raise CodegenError(f"{texture.source}: atlas image name mismatch")
    frame_values = list(frames.values()) if isinstance(frames, dict) else frames
    if len(frame_values) != 1 or not isinstance(frame_values[0], dict):
        raise CodegenError(f"{texture.source}: atlas must contain one sheet frame")
    frame = frame_values[0]
    if frame.get("rotated") is not False or frame.get("trimmed") is not False:
        raise CodegenError(f"{texture.source}: rotated or trimmed atlases are unsupported")
    slices = meta.get("slices")
    if not isinstance(slices, list):
        raise CodegenError(f"{texture.source}: atlas has no slices")
    result: list[dict] = []
    seen: set[str] = set()
    for item in slices:
        if not isinstance(item, dict):
            raise CodegenError(f"{texture.source}: invalid atlas slice")
        name, keys = item.get("name"), item.get("keys")
        if (not isinstance(name, str) or not IDENT_RE.fullmatch(name)
                or name in seen or not isinstance(keys, list) or len(keys) != 1
                or not isinstance(keys[0], dict)
                or keys[0].get("frame") not in (None, 0)
                or not isinstance(keys[0].get("bounds"), dict)):
            raise CodegenError(f"{texture.source}: invalid or duplicate atlas slice")
        bounds = keys[0]["bounds"]
        values = [bounds.get(key) for key in ("x", "y", "w", "h")]
        if (any(not isinstance(value, int) for value in values)
                or values[0] < 0 or values[1] < 0
                or values[2] <= 0 or values[3] <= 0
                or values[0] + values[2] > texture.width
                or values[1] + values[3] > texture.height):
            raise CodegenError(f"{texture.source}: atlas slice {name} is out of bounds")
        seen.add(name)
        result.append({
            "name": name,
            "x": values[0], "y": values[1], "width": values[2], "height": values[3],
            "uv": [
                values[0] / texture.width, values[1] / texture.height,
                values[2] / texture.width, values[3] / texture.height,
            ],
        })
    return result


def cpp_handle_tokens(source: CppSource) -> list[tuple[str | None, str, int]]:
    """Collect c_/e_/t_ identifiers while excluding comments and literals."""
    text = source.text
    masked = list(text)
    index = 0
    while index < len(text):
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            end = len(text) if end < 0 else end
            for position in range(index, end):
                masked[position] = " "
            index = end
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise CodegenError(f"{source.path}: unterminated C++ comment")
            end += 2
            for position in range(index, end):
                if masked[position] not in "\r\n":
                    masked[position] = " "
            index = end
        elif text[index] in {'"', "'"}:
            quote = text[index]
            start = index
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                elif text[index] == quote:
                    index += 1
                    break
                else:
                    index += 1
            else:
                raise CodegenError(f"{source.path}: unterminated C++ literal")
            for position in range(start, min(index, len(masked))):
                if masked[position] not in "\r\n":
                    masked[position] = " "
        else:
            index += 1
    pattern = re.compile(
        r"\b(?:(?P<owner>[a-z][a-z0-9_-]*)\s*::\s*)?"
        r"(?P<name>[cet]_[A-Za-z0-9_]*)\b")
    return [
        (match.group("owner"), match.group("name"), match.start())
        for match in pattern.finditer("".join(masked))
    ]


def validate_cpp_handles(module: Module, dependencies: dict[str, dict]) -> None:
    local_components = {item.name for item in module.components}
    local_components.update(BUILTIN_COMPONENTS)
    local_entities = {item.name for item in module.entities}
    dependency_components = {
        dep_id: {item["name"] for item in document.get("components", [])}
        for dep_id, document in dependencies.items()}
    dependency_entities = {
        dep_id: {item["name"] for item in document.get("entities", [])}
        for dep_id, document in dependencies.items()}
    local_events = {item.name for item in module.events}
    dependency_events = {
        dep_id: {item["name"] for item in document.get("events", [])}
        for dep_id, document in dependencies.items()}
    local_textures = {
        f"t_{texture.name}_{item['name']}"
        for texture in module.textures for item in texture.slices}
    local_slice_matches: dict[str, int] = {}
    for texture in module.textures:
        for item in texture.slices:
            local_slice_matches[item["name"]] = local_slice_matches.get(item["name"], 0) + 1
    local_textures.update(
        f"t_{name}" for name, count in local_slice_matches.items() if count == 1)
    dependency_textures = {
        dep_id: {
            f"t_{item['name']}"
            for texture in document.get("textures", [])
            for item in texture.get("slices", [])
        }
        for dep_id, document in dependencies.items()}

    callback_sources = [
        CppSource(Path(item.source), item.body)
        for item in module.systems + module.observers]
    for source in module.cpp_sources + callback_sources:
        for owner, name, offset in cpp_handle_tokens(source):
            line = source.text.count("\n", 0, offset) + 1
            column = offset - source.text.rfind("\n", 0, offset)
            location = f"{source.path}:{line}:{column}"
            if name.startswith("t_"):
                if owner:
                    if owner == module.content_id:
                        available = local_textures
                    elif owner not in dependencies:
                        raise CodegenError(
                            f"{location}: reference to undeclared dependency "
                            f"{owner}::{name}")
                    else:
                        available = dependency_textures[owner]
                    if name in available:
                        continue
                    fallback = next(
                        (value for value in available if value.endswith("_invalid")),
                        None)
                    if fallback is None:
                        raise CodegenError(
                            f"{location}: unknown texture slice {owner}::{name}; "
                            f"{owner} has no invalid fallback")
                    alias = f"{owner}::{name}"
                    module.cpp_texture_aliases[alias] = f"{owner}:{fallback[2:]}"
                    module.cpp_texture_fallbacks[alias] = f"{owner}:{fallback[2:]}"
                    continue
                if name in local_textures:
                    continue
                short_name = name[2:]
                if local_slice_matches.get(short_name, 0) > 1:
                    raise CodegenError(
                        f"{location}: ambiguous texture slice {name}; use an atlas-prefixed marker")
                matches = [
                    dep_id for dep_id in []
                    if name in dependency_textures[dep_id]]
                if len(matches) == 1:
                    module.cpp_texture_aliases[name] = f"{matches[0]}:{name[2:]}"
                    continue
                if len(matches) > 1:
                    raise CodegenError(
                        f"{location}: ambiguous texture slice {name}; qualify it as "
                        + " or ".join(f"{item}::{name}" for item in matches))
                # The short t_invalid alias is also present in local_textures.
                # Resolve fallbacks through the atlas-qualified marker so the
                # generated canonical name always identifies a real slice.
                fallback = next(
                    (f"t_{texture.name}_{item['name']}"
                     for texture in module.textures
                     for item in texture.slices
                     if item["name"] == "invalid"),
                    None)
                if fallback is None:
                    raise CodegenError(
                        f"{location}: unknown texture slice {name}; "
                        f"{module.content_id} has no invalid fallback")
                module.cpp_texture_aliases[name] = f"{module.content_id}:{fallback[2:]}"
                module.cpp_texture_fallbacks[name] = f"{module.content_id}:{fallback[2:]}"
                continue
            event_lookup = name
            if name.startswith("e_") or ((name.startswith("c_")) and (
                    (owner == module.content_id and event_lookup in local_events)
                    or (owner in dependency_events
                        and event_lookup in dependency_events[owner])
                    or (not owner and (event_lookup in local_events
                        or sum(event_lookup in values for values in dependency_events.values()) == 1)))):
                continue
            kind = "component" if name.startswith("c_") else "entity recipe"
            local = local_components if kind == "component" else local_entities
            imported = dependency_components if kind == "component" \
                else dependency_entities
            aliases = module.cpp_component_aliases if kind == "component" \
                else module.cpp_entity_aliases
            if owner:
                if owner == module.content_id:
                    if name not in local:
                        raise CodegenError(
                            f"{location}: unknown {kind} {owner}::{name}")
                elif owner not in dependencies:
                    raise CodegenError(
                        f"{location}: reference to undeclared dependency "
                        f"{owner}::{name}")
                elif name not in imported[owner]:
                    raise CodegenError(
                        f"{location}: unknown {kind} {owner}::{name}")
                continue
            if name in local:
                continue
            matches = [
                dep_id for dep_id in []
                if name in imported[dep_id]]
            if not matches:
                raise CodegenError(f"{location}: unknown {kind} {name}")
            if len(matches) != 1:
                raise CodegenError(
                    f"{location}: ambiguous {kind} {name}; qualify it as "
                    + " or ".join(f"{item}::{name}" for item in matches))
            aliases[name] = f"{matches[0]}:{name}"


def validate_module(module: Module, dependencies: dict[str, dict]) -> None:
    for component in module.components:
        if component.name in BUILTIN_COMPONENTS:
            raise CodegenError(
                f"{component.source}: {component.name} is an engine-defined component")
    for event in module.events:
        role_count = sum(
            1 for field in event.fields
            if field.type_name == "entity_id" and field.count == 1)
        if role_count > MAX_EVENT_ROLES:
            raise CodegenError(
                f"{event.source}: custom events support at most "
                f"{MAX_EVENT_ROLES} named entity roles")
    for component in module.components:
        seen_nested: set[tuple[str, str]] = set()
        for nested in component.nested_observers:
            key = (nested.side, nested.observer)
            if key in seen_nested:
                raise CodegenError(
                    f"{nested.source}: duplicate nested observer "
                    f"{nested.observer} for {component.name}")
            seen_nested.add(key)
            event_reference = nested.observer
            if event_reference == "e_update":
                module.systems.append(System(
                    name=f"__{component.name}_update",
                    side=nested.side,
                    terms=[Term("mut", component.name, "self")],
                    body=nested.body,
                    source=nested.source,
                    order=nested.order))
            else:
                module.observers.append(Observer(
                    name=f"__{component.name}_{nested.observer.replace(':', '_')}",
                    side=nested.side,
                    event=event_reference,
                    terms=[Term("read", component.name, "self")],
                    body=nested.body,
                    source=nested.source,
                    custom=True,
                    context_type=nested.observer.replace(":", "::"),
                    order=nested.order,
                ))

    seen: set[str] = set()
    for collection, label in (
        (module.constants, "constant"), (module.pod_types, "struct"),
        (module.enum_types, "enum"), (module.events, "event"),
        (module.components, "component"), (module.systems, "system"),
        (module.observers, "observer"), (module.entities, "entity"),
        (module.textures, "texture"),
        (module.computes, "compute"),
    ):
        local: set[str] = set()
        for item in collection:
            if item.name in local:
                raise CodegenError(f"{item.source}: duplicate {label} {item.name}")
            local.add(item.name)
    public_names: dict[str, str] = {}
    for collection, label in (
        (module.constants, "constant"), (module.pod_types, "struct"),
        (module.enum_types, "enum"), (module.events, "event"),
        (module.components, "component"), (module.entities, "entity"),
        (module.textures, "texture"), (module.computes, "compute"),
    ):
        for item in collection:
            if item.name in public_names:
                raise CodegenError(
                    f"{item.source}: {label} {item.name} conflicts with "
                    f"{public_names[item.name]}")
            public_names[item.name] = label

    all_textures: dict[str, dict | Texture] = {}
    local_slice_names: dict[str, str] = {}
    for dep_id, document in dependencies.items():
        for record in document.get("textures", []):
            all_textures[record["canonical"]] = record
    for texture in module.textures:
        source_relative = validate_asset_path(texture.source_path, texture.source)
        source_path = Path(texture.resolved_source) if texture.resolved_source \
            else module.root / source_relative
        texture.width, texture.height = png_dimensions(source_path, texture.source)
        if texture.slices_path:
            slices_relative = validate_asset_path(texture.slices_path, texture.source)
            texture.slices = load_atlas_slices(
                texture, Path(texture.resolved_slices) if texture.resolved_slices
                else module.root / slices_relative)
            if not any(item["name"] == "invalid" for item in texture.slices):
                raise CodegenError(
                    f"{texture.source}: atlas {texture.name} requires an invalid slice")
            for item in texture.slices:
                previous = local_slice_names.get(item["name"])
                if previous:
                    raise CodegenError(
                        f"{texture.source}: atlas slice {item['name']} conflicts "
                        f"with atlas {previous}")
                local_slice_names[item["name"]] = texture.name
        all_textures[texture.name] = texture
        all_textures[f"{module.content_id}:{texture.name}"] = texture

    def resolve_texture(reference: str, source: str) -> dict | Texture:
        if ":" in reference:
            dep_id = reference.split(":", 1)[0]
            if dep_id != module.content_id and dep_id not in dependencies:
                raise CodegenError(
                    f"{source}: reference to undeclared dependency {reference}")
        texture = all_textures.get(reference)
        if not texture and ":" not in reference and module.has_init_handler:
            # C++ asset registries are intentionally private implementation.
            # The loader validates that the named texture exists after Assets.
            return {}
        if not texture:
            raise CodegenError(f"{source}: unresolved texture {reference}")
        return texture

    def validate_mesh_reference(reference: str, source: str) -> None:
        if not reference:
            return
        if ":" in reference:
            owner = reference.split(":", 1)[0]
            if owner != module.content_id and owner not in dependencies:
                raise CodegenError(
                    f"{source}: reference to undeclared dependency {reference}")
            if owner == module.content_id and not module.has_init_handler:
                raise CodegenError(
                    f"{source}: unresolved mesh {reference}; "
                    "meshes are registered from C++ during Assets")
            return
        if not module.has_init_handler:
            raise CodegenError(
                f"{source}: unresolved mesh {reference}; "
                "meshes are registered from C++ during Assets")

    def texture_slices(texture: dict | Texture) -> list[dict]:
        return texture.slices if isinstance(texture, Texture) \
            else texture.get("slices", [])

    slice_expression = re.compile(
        rf"\bslice\s*\(\s*({REF_RE.pattern})\s*,\s*"
        rf"({IDENT_RE.pattern})\s*\)")

    def float_literal(value: float) -> str:
        rendered = format(value, ".9g")
        if "." not in rendered and "e" not in rendered:
            rendered += ".0"
        return rendered + "f"

    def expand_slices(initializer: str, source: str) -> str:
        def replace(match: re.Match[str]) -> str:
            reference, slice_name = match.group(1), match.group(2)
            texture = resolve_texture(reference, source)
            item = next(
                (candidate for candidate in texture_slices(texture)
                 if candidate.get("name") == slice_name), None)
            if not item:
                raise CodegenError(
                    f"{source}: unresolved atlas slice {reference}:{slice_name}")
            return "vec4{" + ", ".join(
                float_literal(float(value)) for value in item["uv"]) + "}"
        expanded = slice_expression.sub(replace, initializer)
        if re.search(r"\bslice\s*\(", expanded):
            raise CodegenError(f"{source}: malformed slice initializer")
        return expanded

    for declaration in module.entities:
        for value in declaration.values:
            value.initializer = expand_slices(value.initializer, declaration.source)

    constants: dict[str, int] = {
        f"{dep_id}:{item['name']}": item["value"]
        for dep_id, document in dependencies.items()
        for item in document.get("constants", [])
    }
    constants.update(HELPER_CONSTANTS)
    for item in module.constants:
        if item.type_name not in TYPE_INFO or item.type_name in {
                "float", "double", "vec2", "vec3", "vec4",
                "ivec2", "ivec3", "ivec4", "uvec2", "uvec3", "uvec4"}:
            raise CodegenError(f"{item.source}: constant {item.name} requires an integer type")
        item.value = evaluate_integer(item.expression, constants, item.source)
        constants[item.name] = item.value

    type_records: dict[str, dict] = {}
    for dep_id, document in dependencies.items():
        for record in document.get("types", []) + document.get("components", []):
            type_records[record["canonical"]] = record
    for item in module.enum_types:
        if item.underlying not in TYPE_INFO or TYPE_INFO[item.underlying][1] > 8 \
                or item.underlying in {"float", "double", "vec2", "vec3", "vec4",
                                       "ivec2", "ivec3", "ivec4",
                                       "uvec2", "uvec3", "uvec4", "bool"}:
            raise CodegenError(f"{item.source}: enum {item.name} has invalid underlying type")
        enum_constants = dict(constants)
        evaluated_values: list[tuple[str, str]] = []
        for value_name, expression in item.values:
            value = evaluate_integer(expression, enum_constants, item.source)
            enum_constants[value_name] = value
            evaluated_values.append((value_name, str(value)))
        item.values = evaluated_values
        type_records[item.name] = {
            "kind": "enum", "name": item.name,
            "canonical": f"{module.content_id}:{item.name}",
            "size": TYPE_INFO[item.underlying][1],
            "alignment": TYPE_INFO[item.underlying][2],
            "underlying": item.underlying,
        }

    local_layouts: dict[str, Component | PodType | Event] = {
        item.name: item for item in module.pod_types + module.components + module.events}
    visiting: set[str] = set()

    def layout_local(name: str) -> None:
        if name in type_records:
            return
        value = local_layouts.get(name)
        if not value:
            return
        if name in visiting:
            raise CodegenError(f"{value.source}: cyclic POD layout involving {name}")
        visiting.add(name)
        for field_value in value.fields:
            if field_value.type_name not in TYPE_INFO:
                local_name = field_value.type_name
                if ":" in local_name:
                    if local_name.split(":", 1)[0] not in dependencies:
                        raise CodegenError(
                            f"{value.source}: reference to undeclared dependency {local_name}")
                else:
                    layout_local(local_name)
        calculate_layout(value, type_records, constants)
        kind = "tag" if isinstance(value, Component) and not value.fields else \
            "component" if isinstance(value, Component) else \
            "event" if isinstance(value, Event) else "struct"
        type_records[name] = {
            "kind": kind, "name": name, "canonical": f"{module.content_id}:{name}",
            "size": value.size, "alignment": value.alignment,
            "fields": [field_record(field) for field in value.fields],
        }
        visiting.remove(name)

    for name in local_layouts:
        layout_local(name)

    integer_types = {
        "char", "int8", "uint8", "int16", "uint16", "int", "int32", "uint32",
        "int64", "uint64", "entity_id"}
    float_types = {"float", "double"}
    vector_types = {
        "vec2", "vec3", "vec4", "ivec2", "ivec3", "ivec4",
        "uvec2", "uvec3", "uvec4"}
    vector_constructors = {
        "vec2": {"vec2"}, "vec3": {"vec3"}, "vec4": {"vec4"},
        "ivec2": {"ivec2"},
        "ivec3": {"ivec3"}, "ivec4": {"ivec4"},
        "uvec2": {"uvec2"}, "uvec3": {"uvec3"}, "uvec4": {"uvec4"},
    }
    numeric_literal = re.compile(
        r"[+-]?(?:(?:0[xX][0-9A-Fa-f]+)|(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:[eE][+-]?\d+)?)[uUlLfF]*")
    local_enums = {
        item.name: {name for name, _ in item.values}
        for item in module.enum_types}
    imported_enums = {
        item["canonical"]: {value["name"] for value in item.get("values", [])}
        for document in dependencies.values()
        for item in document.get("types", [])
        if item.get("kind") == "enum"}
    constant_names = {item.name for item in module.constants} | {
        f"{dep_id}:{item['name']}"
        for dep_id, document in dependencies.items()
        for item in document.get("constants", [])}

    for value in local_layouts.values():
        for field_value in value.fields:
            default = field_value.default
            if default is None:
                continue
            if isinstance(value, Event) and default == "{}":
                continue
            valid = default == "{}"
            if field_value.array is not None:
                valid = default == "{}"
            elif field_value.type_name == "bool":
                valid = default in {"{}", "true", "false", "0", "1"}
            elif field_value.type_name in integer_types | float_types:
                valid = default == "{}" or bool(numeric_literal.fullmatch(default)) \
                    or default in constant_names
            elif field_value.type_name in vector_types:
                constructor = re.fullmatch(
                    r"([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)", default,
                    re.DOTALL)
                valid = default == "{}" or bool(
                    constructor and constructor.group(1)
                    in vector_constructors[field_value.type_name])
            elif field_value.type_name in local_enums:
                valid = default in local_enums[field_value.type_name]
            elif field_value.type_name in imported_enums:
                valid = default in imported_enums[field_value.type_name]
            if not valid:
                raise CodegenError(
                    f"{value.source}: invalid default for field "
                    f"{field_value.name}")

    imported_components = {
        record["canonical"]: record
        for document in dependencies.values()
        for record in document.get("components", [])
    }
    local_component_objects = {item.name: item for item in module.components}
    component_contract_visiting: set[str] = set()

    def canonical_contract_reference(reference: str) -> str:
        return reference if ":" in reference else f"{module.content_id}:{reference}"

    def finalize_component_contract(component: Component) -> None:
        if component.fingerprint:
            return
        if component.name in component_contract_visiting:
            raise CodegenError(
                f"{component.source}: cyclic component contract inheritance")
        component_contract_visiting.add(component.name)
        base_record = None
        if component.base:
            base_canonical = canonical_contract_reference(component.base)
            owner, base_name = base_canonical.split(":", 1)
            if owner == module.content_id:
                base_component = local_component_objects.get(base_name)
                if not base_component:
                    raise CodegenError(
                        f"{component.source}: unresolved contract base "
                        f"{component.base}")
                finalize_component_contract(base_component)
                base_record = component_record(module.content_id, base_component)
            else:
                if owner not in dependencies:
                    raise CodegenError(
                        f"{component.source}: reference to undeclared dependency "
                        f"{component.base}")
                base_record = imported_components.get(base_canonical)
            if not base_record:
                raise CodegenError(
                    f"{component.source}: unresolved contract base {component.base}")
            if base_record["kind"] != "tag":
                raise CodegenError(
                    f"{component.source}: contract base {component.base} must be a tag")
            if base_record["residency"] != component.residency:
                raise CodegenError(
                    f"{component.source}: contract base {component.base} must have "
                    "the same residency")

            requirements = base_record.get("contract", [])
            implementations = {
                (item.side, item.observer.split(":")[-1]): item
                for item in component.nested_observers
            }
            for requirement in requirements:
                leaf = (
                    requirement["world"],
                    requirement["observer"].split(":")[-1])
                if leaf not in implementations:
                    if requirement["required"]:
                        raise CodegenError(
                            f"{component.source}: {component.name} is missing "
                            f"required {requirement['world']} "
                            f"{requirement['observer']}")
            allowed = {
                (item["world"], item["observer"].split(":")[-1])
                for item in requirements
            }
            for implementation in component.nested_observers:
                if (implementation.side,
                        implementation.observer.split(":")[-1]) not in allowed:
                    raise CodegenError(
                        f"{component.source}: undeclared or wrong-world contract "
                        f"observer {implementation.observer}")
        elif component.nested_observers:
            raise CodegenError(
                f"{component.source}: nested observers require a contract base")

        requirement_keys: set[tuple[str, str]] = set()
        for requirement in component.requirements:
            key = (requirement.side, requirement.observer)
            if key in requirement_keys:
                raise CodegenError(
                    f"{component.source}: duplicate observer contract "
                    f"{requirement.observer}")
            requirement_keys.add(key)
            if not component.residency & RESIDENCY[requirement.side]:
                raise CodegenError(
                    f"{component.source}: observer contract "
                    f"{requirement.observer} uses an absent world")
        if component.requirements and component.fields:
            raise CodegenError(
                f"{component.source}: components declaring observer contracts "
                "must be tags")

        contract_shape = {
            "base": base_record["canonical"] if base_record else None,
            "base_contract": (
                base_record.get("contract_fingerprint") if base_record else None),
            "requirements": [
                {
                    "world": item.side,
                    "observer": item.observer,
                    "required": item.required,
                }
                for item in component.requirements
            ],
        }
        component.contract_fingerprint = schema_fingerprint(contract_shape)
        component.fingerprint = schema_fingerprint({
            "canonical": f"{module.content_id}:{component.name}",
            "size": component.size,
            "alignment": component.alignment,
            "residency": component.residency,
            "kind": "tag" if not component.fields else "component",
            "fields": [
                field_record(item, module.content_id)
                for item in component.fields],
            "contract": contract_shape,
        })
        component_contract_visiting.remove(component.name)

    for component in module.components:
        finalize_component_contract(component)

    local_components: dict[str, dict] = {
        item.name: component_record(module.content_id, item) for item in module.components}
    for component in module.components:
        if component.shader:
            if not component.residency & RESIDENCY["r"]:
                raise CodegenError(f"{component.source}: shader component {component.name} is not render-resident")
            if not component.shader.mesh:
                raise CodegenError(
                    f"{component.source}: shader component {component.name} requires an explicit mesh")
            shader_fields = [
                item for item in component.fields
                if item.count == 1 and item.type_name in TYPE_INFO
                and TYPE_INFO[item.type_name][3] is not None]
            if len(shader_fields) > MAX_ATTRIBUTES:
                raise CodegenError(
                    f"{component.source}: shader component {component.name} exceeds "
                    f"the {MAX_ATTRIBUTES}-field attribute limit")
            if any(item.name == "local_position" for item in component.fields):
                raise CodegenError(
                    f"{component.source}: shader component field local_position is reserved")
            for item in component.fields:
                if (item.count != 1 or item.type_name not in TYPE_INFO
                        or TYPE_INFO[item.type_name][3] is None) \
                        and item.type_name != "entity_id":
                    raise CodegenError(
                        f"{component.source}: shader field {item.name} type "
                        f"{item.type_name} cannot be uploaded as a vertex attribute")
            if component.shader.textures:
                for _, texture_reference in component.shader.textures:
                    resolve_texture(texture_reference, component.source)
            elif re.search(
                    r"\bsample_[A-Za-z_][A-Za-z0-9_]*\s*\(",
                    component.shader.vertex_body + component.shader.fragment_body):
                raise CodegenError(
                    f"{component.source}: texture sampling requires a shader texture")
            validate_mesh_reference(
                component.shader.mesh, component.source)
            component.shader.wgsl = build_shader_wgsl(component)
            if len(component.shader.wgsl.encode("utf-8")) > 65536:
                raise CodegenError(f"{component.source}: generated WGSL source exceeds 64 KiB")

    all_components = {
        **{record["canonical"]: record
           for record in BUILTIN_COMPONENTS.values()},
        **local_components,
    }
    all_components.update({
        f"{module.content_id}:{name}": record for name, record in local_components.items()})
    for dep_id, document in dependencies.items():
        for record in document.get("components", []):
            canonical = record.get("canonical")
            if canonical != f"{dep_id}:{record.get('name', '')}":
                raise CodegenError(f"dependency {dep_id}: invalid canonical component")
            all_components[canonical] = record

    def resolve(reference: str, source: str) -> dict:
        key = ("builtin:" + reference
               if reference in BUILTIN_COMPONENTS and ":" not in reference
               else reference)
        if ":" in reference:
            dep_id = reference.split(":", 1)[0]
            if dep_id != module.content_id and dep_id not in dependencies:
                raise CodegenError(f"{source}: reference to undeclared dependency {reference}")
        record = all_components.get(key)
        if not record:
            raise CodegenError(f"{source}: unresolved component {reference}")
        return record

    supported_compute_types = {
        "int", "int32", "uint32", "float", "vec2", "vec3", "vec4"}
    for compute in module.computes:
        for item in compute.fields:
            if (item.type_name not in supported_compute_types
                    or item.array is not None or item.default is not None):
                raise CodegenError(
                    f"{compute.source}: compute state field {item.name} has "
                    f"unsupported type, array, or default")
        calculate_layout(compute, {}, {})
        instance = resolve(compute.instance, compute.source)
        if instance.get("kind") == "tag" or not instance.get("shader", False):
            raise CodegenError(
                f"{compute.source}: compute instance {compute.instance} "
                "must be a shader component")
        canonical_instance = compute.instance if ":" in compute.instance \
            else f"{module.content_id}:{compute.instance}"
        if ":" in compute.instance:
            owner = compute.instance.split(":", 1)[0]
            if owner != module.content_id and owner not in dependencies:
                raise CodegenError(
                    f"{compute.source}: reference to undeclared dependency "
                    f"{compute.instance}")
        compute.instance = canonical_instance
        compute.instance_fingerprint = int(instance["fingerprint"])
        compute.fingerprint = schema_fingerprint({
            "canonical": f"{module.content_id}:{compute.name}",
            "size": compute.size,
            "alignment": compute.alignment,
            "fields": [field_record(item, module.content_id) for item in compute.fields],
            "instance": compute.instance,
            "instance_fingerprint": compute.instance_fingerprint,
        })
        instance_fields = {item["name"]: item for item in instance["fields"]}
        state_fields = {item.name for item in compute.fields}
        for match in re.finditer(
                r"\bstate\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)",
                compute.logic):
            if match.group(1) not in state_fields:
                raise CodegenError(
                    f"{compute.source}: compute logic references unknown "
                    f"state field {match.group(1)}")
        for match in re.finditer(
                r"\binstance\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)",
                compute.logic):
            field_name = match.group(1)
            field_value = instance_fields.get(field_name)
            if not field_value:
                raise CodegenError(
                    f"{compute.source}: compute logic references unknown "
                    f"instance field {field_name}")
            if (field_value.get("count") != 1
                    or field_value.get("type") not in WGSL_TYPE):
                raise CodegenError(
                    f"{compute.source}: compute logic references unsupported "
                    f"instance field {field_name}")
        local_instance = next(
            (item for item in module.components
             if f"{module.content_id}:{item.name}" == compute.instance), None)
        compute.wgsl = build_compute_wgsl(
            compute, local_instance if local_instance else instance)
        if len(compute.wgsl.encode("utf-8")) > 65536:
            raise CodegenError(
                f"{compute.source}: generated compute WGSL exceeds 64 KiB")

    all_entities: dict[str, dict] = {}
    for dep_id, document in dependencies.items():
        for record in document.get("entities", []):
            all_entities[record["canonical"]] = record
    entity_by_name = {item.name: item for item in module.entities}
    flattening: set[str] = set()

    def canonical_component(reference: str) -> str:
        if ":" not in reference and reference in BUILTIN_COMPONENTS:
            return "builtin:" + reference
        return reference if ":" in reference else f"{module.content_id}:{reference}"

    def flatten_entity(entity: Entity) -> list[EntityValue]:
        if entity.flattened:
            return entity.flattened
        if entity.name in flattening:
            raise CodegenError(f"{entity.source}: cyclic entity template composition")
        flattening.add(entity.name)
        values: list[EntityValue] = []
        inherited: dict[str, int] = {}
        for use in entity.uses:
            if ":" in use:
                dep_id = use.split(":", 1)[0]
                if dep_id not in dependencies:
                    raise CodegenError(
                        f"{entity.source}: reference to undeclared dependency {use}")
                record = all_entities.get(use)
                if not record:
                    raise CodegenError(f"{entity.source}: unresolved entity template {use}")
                source_values = [
                    EntityValue(value["component"], value["initializer"], value["residency"])
                    for value in record.get("values", [])]
            else:
                base = entity_by_name.get(use)
                if not base:
                    raise CodegenError(f"{entity.source}: unresolved entity template {use}")
                source_values = flatten_entity(base)
            for value in source_values:
                canonical = canonical_component(value.component)
                record = resolve(canonical, entity.source)
                effective = value.residency & entity.residency & record["residency"]
                if (record["residency"] not in (1, 2, 4)
                        and value.residency != 7
                        and value.residency != record["residency"]
                        and value.residency
                            != authority_mask(record["residency"])):
                    raise CodegenError(
                        f"{entity.source}: shared component {canonical} cannot "
                        f"have a destination-specific initializer")
                if (not effective
                        or value.residency != 7
                        and record["residency"] & value.residency != value.residency):
                    raise CodegenError(
                        f"{entity.source}: component {canonical} has incompatible residency")
                if inherited.get(canonical, 0) & effective:
                    raise CodegenError(
                        f"{entity.source}: duplicate inherited component {canonical}")
                inherited[canonical] = inherited.get(canonical, 0) | effective
                values.append(EntityValue(canonical, value.initializer, effective))
        explicit: dict[str, int] = {}
        for value in entity.values:
            canonical = canonical_component(value.component)
            record = resolve(canonical, entity.source)
            effective = value.residency & entity.residency & record["residency"]
            if (record["residency"] not in (1, 2, 4)
                    and value.residency != 7
                    and value.residency != record["residency"]
                    and value.residency != authority_mask(record["residency"])):
                raise CodegenError(
                    f"{entity.source}: shared component {canonical} cannot "
                    f"have a destination-specific initializer")
            if (not effective
                    or value.residency != 7
                    and record["residency"] & value.residency != value.residency):
                raise CodegenError(
                    f"{entity.source}: component {canonical} has incompatible residency")
            if explicit.get(canonical, 0) & effective:
                raise CodegenError(
                    f"{entity.source}: duplicate component {canonical}")
            explicit[canonical] = explicit.get(canonical, 0) | effective
            retained: list[EntityValue] = []
            for existing in values:
                if existing.component != canonical:
                    retained.append(existing)
                    continue
                remaining = existing.residency & ~effective
                if remaining:
                    retained.append(EntityValue(
                        existing.component, existing.initializer, remaining))
            values = retained
            values.append(EntityValue(canonical, value.initializer, effective))
        # Contract bases are real runtime tags. Materialize them in recipes so
        # generic base queries match immediately in every resident world.
        expanded_values = list(values)
        known_masks: dict[str, int] = {}
        for value in expanded_values:
            known_masks[value.component] = (
                known_masks.get(value.component, 0) | value.residency)
        cursor = 0
        while cursor < len(expanded_values):
            value = expanded_values[cursor]
            cursor += 1
            record = resolve(value.component, entity.source)
            base = record.get("base")
            if not base:
                continue
            base_record = resolve(base, entity.source)
            effective = value.residency & base_record["residency"]
            missing = effective & ~known_masks.get(base, 0)
            if missing:
                expanded_values.append(EntityValue(base, "", missing))
                known_masks[base] = known_masks.get(base, 0) | missing
        values = expanded_values
        if not values:
            raise CodegenError(f"{entity.source}: entity {entity.name} must contain components")
        entity.flattened = values
        flattening.remove(entity.name)
        return values

    for index, entity in enumerate(module.entities, 1):
        entity.callback = index
        flatten_entity(entity)
        entity.fingerprint = schema_fingerprint({
            "canonical": f"{module.content_id}:{entity.name}",
            "residency": entity.residency,
            "values": [
                {
                    "component": value.component,
                    "initializer": value.initializer,
                    "residency": value.residency,
                }
                for value in entity.flattened],
        })
        all_entities[entity.name] = {
            "name": entity.name, "canonical": f"{module.content_id}:{entity.name}",
            "residency": entity.residency,
            "fingerprint": entity.fingerprint,
            "values": [
                {"component": value.component, "initializer": value.initializer,
                 "residency": value.residency}
                for value in entity.flattened],
        }

    for index, start in enumerate(module.start_handlers, 1):
        start.callback = index
        if start.side not in WORLD_ENUM:
            raise CodegenError(f"{start.source}: g_start requires s, c, or r")

    # Init handlers are worldless and cannot carry ECS terms.  Their bodies
    # are emitted into the single content_init callback in declaration order.
    module.init_handlers.sort(key=lambda item: item.order)
    module.start_handlers.sort(key=lambda item: item.order)

    for index, system in enumerate(module.systems, 1):
        system.callback = index
        side = RESIDENCY[system.side]
        for term in system.terms:
            record = resolve(term.component, system.source)
            if not record["residency"] & side:
                raise CodegenError(f"{system.source}: component {term.component} is absent from system world")
            if record["size"] == 0 and term.access not in {"read", PRESENCE_ACCESS}:
                raise CodegenError(
                    f"{system.source}: tag terms must use read access")
            if (record["residency"] not in (1, 2, 4)
                    and term.access not in {"read", PRESENCE_ACCESS}
                    and world_mask(system.side)
                    != authority_mask(record["residency"])):
                raise CodegenError(
                    f"{system.source}: shared component {term.component} is "
                    f"read-only outside its authority world")
    for index, observer in enumerate(module.observers, 1):
        observer.callback = index
        side = RESIDENCY[observer.side]
        for term in observer.terms:
            record = resolve(term.component, observer.source)
            if not record["residency"] & side:
                raise CodegenError(f"{observer.source}: component {term.component} is absent from observer world")
            if record["size"] == 0 and term.access not in {"read", PRESENCE_ACCESS}:
                raise CodegenError(
                    f"{observer.source}: tag terms must use read access")
            if (record["residency"] not in (1, 2, 4)
                    and term.access not in {"read", PRESENCE_ACCESS}
                    and world_mask(observer.side)
                    != authority_mask(record["residency"])):
                raise CodegenError(
                    f"{observer.source}: shared component {term.component} is "
                    f"read-only outside its authority world")
        if observer.custom:
            event_reference = observer.event
            if ":" in event_reference:
                dep_id = event_reference.split(":", 1)[0]
                if dep_id not in dependencies:
                    raise CodegenError(
                        f"{observer.source}: reference to undeclared dependency {event_reference}")
            events = {
                item.name: item for item in module.events}
            dependency_events = {
                record["canonical"]: record
                for document in dependencies.values()
                for record in document.get("events", [])}
            event_record = events.get(event_reference) or dependency_events.get(event_reference)
            if not event_record:
                raise CodegenError(
                    f"{observer.source}: unresolved custom event {event_reference}")
            else:
                residency = event_record.residency if isinstance(event_record, Event) \
                    else event_record["residency"]
                if not residency & side:
                    raise CodegenError(
                        f"{observer.source}: custom event is absent from observer world")
                role_fields = {
                    item.name: item for item in event_record.fields
                } if isinstance(event_record, Event) else {
                    item["name"]: item
                    for item in event_record.get("fields", [])
                }
                roles = {term.role for term in observer.terms if term.role}
                if len(roles) > MAX_EVENT_ROLES:
                    raise CodegenError(
                        f"{observer.source}: custom events support at most "
                        f"{MAX_EVENT_ROLES} named entity roles")
                for term in observer.terms:
                    if not term.role:
                        continue
                    field = role_fields.get(term.role)
                    field_type = (field.type_name if isinstance(field, Field)
                                  else field.get("type")) if field else None
                    field_count = (field.count if isinstance(field, Field)
                                   else field.get("count", 1)) if field else 0
                    if field_type != "entity_id" or field_count != 1:
                        raise CodegenError(
                            f"{observer.source}: event role {term.role!r} "
                            "must name a scalar entity_id field")

    validate_cpp_handles(module, dependencies)


def imported_records(dependencies: dict[str, dict]) -> list[dict]:
    result: list[dict] = []
    for document in dependencies.values():
        result.extend(
            record for record in document.get("types", [])
            if record.get("kind") == "struct")
        result.extend(document.get("components", []))
        result.extend(document.get("events", []))
    return result


def cpp_type(type_name: str, current_content: str) -> str:
    if type_name in TYPE_INFO:
        return TYPE_INFO[type_name][0]
    if type_name in HELPER_TYPE_NAMES:
        return type_name
    return cpp_name(type_name, current_content)


def event_cpp_type(type_name: str, current_content: str) -> str:
    if type_name in TYPE_INFO:
        return TYPE_INFO[type_name][0]
    if type_name in {"entity", "ui_stream", "const char*"}:
        return type_name
    if type_name.endswith("*"):
        base = type_name[:-1].strip()
        if base in {"char", "void", "ui_stream"}:
            return type_name
        return cpp_name(base, current_content) + "*"
    return cpp_name(type_name, current_content)


def render_struct(
        record: dict, current_content: str, enum_types: set[str],
        constants: dict[str, str]) -> list[str]:
    lines = [f"struct {cpp_name(record['canonical'], current_content)} {{"]
    for item in record["fields"]:
        array = f"[{item.get('count', 1)}]" if item.get("count", 1) != 1 else ""
        default_value = item.get("default")
        if (default_value is not None and item["type"] in enum_types
                and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", default_value)):
            default_value = f"{cpp_type(item['type'], current_content)}::{default_value}"
        elif default_value in constants:
            default_value = constants[default_value]
        default = f" = {default_value}" if default_value is not None else ""
        field_type = (event_cpp_type(item["type"], current_content)
                      if record.get("kind") == "event"
                      else cpp_type(item["type"], current_content))
        lines.append(
            f"    {field_type} {item['name']}{array}{default};")
    for member in record.get("members", []):
        lines.append("    " + member)
    lines.append("};")
    name = cpp_name(record["canonical"], current_content)
    if record["fields"] and record.get("kind") != "event":
        lines.append(f"static_assert(sizeof({name}) == {record['size']}u);")
        lines.append(f"static_assert(alignof({name}) == {record['alignment']}u);")
        for item in record["fields"]:
            lines.append(f"static_assert(offsetof({name}, {item['name']}) == {item['offset']}u);")
    if record.get("kind") == "event":
        lines.extend([
            f"static_assert(std::is_standard_layout_v<{name}>);",
            f"static_assert(std::is_trivially_copyable_v<{name}>);",
            f"static_assert(std::is_trivially_destructible_v<{name}>);",
        ])
    return lines


def ordered_helper_declarations(module: Module) -> list[str]:
    declarations = {name: (kind, raw) for name, kind, raw in module.helper_declarations}
    names = set(declarations)
    dependencies: dict[str, set[str]] = {
        name: {other for other in names if other != name and
               re.search(rf"\b{re.escape(other)}\b", raw)}
        for name, (_kind, raw) in declarations.items()}
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise CodegenError(f"cyclic helper layout involving {name}")
        visiting.add(name)
        for dependency in sorted(dependencies[name]):
            visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(declarations[name][1])

    for name in sorted(names):
        visit(name)
    return ordered


def render_header(module: Module, dependencies: dict[str, dict]) -> str:
    records = imported_records(dependencies) + [
        {
            "kind": "struct", "name": item.name,
            "canonical": f"{module.content_id}:{item.name}",
            "size": item.size, "alignment": item.alignment,
            "fields": [field_record(field, module.content_id) for field in item.fields],
        }
        for item in module.pod_types if item.emit
    ] + [
        component_record(module.content_id, item) for item in module.components
    ] + [event_record(module.content_id, item) for item in module.events]
    lines = [
        "#pragma once", '#include "content_types.h"',
        '#include "ecs.hpp"', '#include "event.hpp"', '#include "particles.hpp"',
        '#include "breakpoints.hpp"',
        '#include "callback.hpp"',
        '#include "audio_source.hpp"',
        '#include "box.hpp"',
        '#include "camera.hpp"',
        '#include "print.hpp"',
        '#include "texture.hpp"',
        "class ui_stream;",
        "#include <cstddef>",
        "#include <type_traits>", "",
    ]
    if module.helper_declarations:
        lines.extend(ordered_helper_declarations(module))
        lines.append("")
    enum_types = {
        item["canonical"]
        for document in dependencies.values()
        for item in document.get("types", [])
        if item.get("kind") == "enum"
    }
    enum_types.update(
        {item.name for item in module.enum_types}
        | {f"{module.content_id}:{item.name}" for item in module.enum_types})
    constant_cpp = {item.name: item.name for item in module.constants}
    constant_cpp.update({
        f"{document['content']}:{item['name']}":
            cpp_name(f"{document['content']}:{item['name']}", module.content_id)
        for document in dependencies.values()
        for item in document.get("constants", [])})
    for document in dependencies.values():
        for item in document.get("constants", []):
            lines.append(
                f"inline constexpr {cpp_type(item['type'], module.content_id)} "
                f"{cpp_name(document['content'] + ':' + item['name'], module.content_id)} = "
                f"{item['value']};")
        for item in document.get("types", []):
            if item.get("kind") != "enum":
                continue
            name = cpp_name(item["canonical"], module.content_id)
            lines.append(f"enum class {name} : {cpp_type(item['underlying'], module.content_id)} {{")
            for value in item.get("values", []):
                lines.append(f"    {value['name']} = {value['value']},")
            lines.append("};")
    for item in module.constants:
        lines.append(
            f"inline constexpr {cpp_type(item.type_name, module.content_id)} "
            f"{item.name} = {item.value};")
    for item in module.enum_types:
        if not item.emit:
            continue
        name = cpp_name(item.name, module.content_id)
        lines.append(f"enum class {name} : {cpp_type(item.underlying, module.content_id)} {{")
        for value_name, expression in item.values:
            lines.append(f"    {value_name} = {expression},")
        lines.append("};")
    if module.constants or module.enum_types or dependencies:
        lines.append("")
    for record in records:
        lines.extend(render_struct(
            record, module.content_id, enum_types, constant_cpp))
        lines.append("")
    local_type_names = [
        item.name for item in module.enum_types if item.emit
    ] + [
        item.name
        for item in module.pod_types + module.components + module.events
        if not isinstance(item, PodType) or item.emit
    ]
    if local_type_names:
        lines.append("// Friendly names for ordinary C++ embedded in content files.")
        for name in local_type_names:
            lines.append(
                f"using {name} = {cpp_name(name, module.content_id)};")
        lines.append("")
    component_records = [
        record for record in records
        if record.get("kind") in {"component", "tag"}
    ] + list(BUILTIN_COMPONENTS.values())
    event_records = [
        record for record in records if record.get("kind") == "event"]
    named_type_records = [
        item
        for document in dependencies.values()
        for item in document.get("types", [])
        if item.get("kind") in {"struct", "enum"}
    ] + [
        {
            "kind": "struct",
            "name": item.name,
            "canonical": f"{module.content_id}:{item.name}",
        }
        for item in module.pod_types if item.emit
    ] + [
        {
            "kind": "enum",
            "name": item.name,
            "canonical": f"{module.content_id}:{item.name}",
        }
        for item in module.enum_types if item.emit
    ]
    entity_records = [
        record
        for document in dependencies.values()
        for record in document.get("entities", [])
    ] + [
        {
            "name": item.name,
            "canonical": f"{module.content_id}:{item.name}",
            "residency": item.residency,
            "fingerprint": item.fingerprint,
        }
        for item in module.entities]
    texture_slice_records = []
    for document in [*dependencies.values(), api_document(module)]:
        owner = document["content"]
        for atlas in document.get("textures", []):
            for item in atlas.get("slices", []):
                texture_slice_records.append({
                    **item,
                    "marker_name": item.get("marker_name", item["name"]),
                    "canonical": f"{owner}:{item.get('marker_name', item['name'])}",
                    "atlas": atlas["canonical"],
                })
    for owner in sorted({
            item["canonical"].split(":", 1)[0]
            for item in texture_slice_records}):
        lines.append(f"namespace {owner} {{")
        for item in texture_slice_records:
            if item["canonical"].split(":", 1)[0] == owner:
                lines.append(f"struct t_{item['marker_name']} {{}};")
        lines.append(f"}} // namespace {owner}")
    for item in texture_slice_records:
        owner, name = item["canonical"].split(":", 1)
        lines.extend([
            "template <>",
            f"struct texture_traits<{owner}::t_{name}> {{",
            "    static inline EngineTextureSlice value{};",
            f"    static constexpr const char* canonical_name = "
            f"{c_string(runtime_name(item['canonical']))};",
            f"    static constexpr const char* atlas_name = "
            f"{c_string(runtime_name(item['atlas']))};",
            "};",
        ])
    local_texture_names = [
        item["marker_name"] for item in texture_slice_records
        if item["canonical"].startswith(module.content_id + ":")]
    for name in local_texture_names:
        lines.append(f"using t_{name} = {module.content_id}::t_{name};")
    local_slices: dict[str, list[dict]] = {}
    for item in texture_slice_records:
        if item["canonical"].startswith(module.content_id + ":"):
            local_slices.setdefault(item["name"], []).append(item)
    for slice_name, matches in sorted(local_slices.items()):
        if len(matches) == 1:
            marker = matches[0]["marker_name"]
            lines.append(
                f"using t_{slice_name} = {module.content_id}::t_{marker};")
    texture_marker_by_canonical = {
        item["canonical"]: item["marker_name"]
        for item in texture_slice_records
    }
    for alias, canonical in sorted(module.cpp_texture_aliases.items()):
        owner, target = canonical.split(":", 1)
        marker = texture_marker_by_canonical.get(canonical)
        if marker is None:
            raise CodegenError(
                f"generated texture alias {alias} has no slice target {canonical}")
        if "::" in alias:
            alias_owner, alias_name = alias.split("::", 1)
            lines.extend([
                f"namespace {alias_owner} {{",
                f"using {alias_name} = {owner}::t_{marker};",
                f"}} // namespace {alias_owner}",
            ])
        else:
            lines.append(f"using {alias} = {owner}::t_{marker};")
    owners = sorted({
        record["canonical"].split(":", 1)[0]
        for record in
        component_records + event_records + named_type_records + entity_records})
    for owner in owners:
        lines.append(f"namespace {owner} {{")
        for record in named_type_records:
            if record["canonical"].startswith(owner + ":"):
                lines.append(
                    f"using {record['name']} = ::"
                    f"{cpp_name(record['canonical'], module.content_id)};")
        for record in component_records:
            if record["canonical"].startswith(owner + ":"):
                lines.append(
                    f"using {record['name']} = ::"
                    f"{cpp_name(record['canonical'], module.content_id)};")
        for record in event_records:
            if record["canonical"].startswith(owner + ":"):
                lines.append(
                    f"using {record['name']} = ::"
                    f"{cpp_name(record['canonical'], module.content_id)};")
        for record in entity_records:
            if record["canonical"].startswith(owner + ":"):
                marker = cpp_name(record["canonical"], module.content_id)
                lines.append(f"struct {record['name']} {{}};")
                lines.append(f"using {marker}_marker = {record['name']};")
        lines.append(f"}} // namespace {owner}")
    lines.append("")
    if module.cpp_component_aliases or module.cpp_entity_aliases:
        lines.append("// Unambiguous direct-dependency handles used by embedded C++.")
        for name, canonical in sorted(module.cpp_component_aliases.items()):
            lines.append(
                f"using {name} = ::{cpp_name(canonical, module.content_id)};")
        for name, canonical in sorted(module.cpp_entity_aliases.items()):
            owner, imported_name = canonical.split(":", 1)
            lines.append(f"using {name} = {owner}::{imported_name};")
        lines.append("")
    compute_records = [
        record
        for document in dependencies.values()
        for record in document.get("computes", [])
    ] + [compute_record(module.content_id, item) for item in module.computes]
    for owner in sorted({
            record["canonical"].split(":", 1)[0]
            for record in compute_records}):
        lines.append(f"namespace {owner} {{")
        for record in compute_records:
            if not record["canonical"].startswith(owner + ":"):
                continue
            lines.append(f"struct {record['name']} {{")
            lines.append("    struct state {")
            for item in record["state_fields"]:
                lines.append(
                    f"        {cpp_type(item['type'], module.content_id)} "
                    f"{item['name']};")
            lines.append("    };")
            lines.append("};")
            lines.append(
                f"static_assert(sizeof({record['name']}::state) == "
                f"{record['state_size']}u);")
            lines.append(
                f"static_assert(alignof({record['name']}::state) == "
                f"{record['state_alignment']}u);")
            for item in record["state_fields"]:
                lines.append(
                    f"static_assert(offsetof({record['name']}::state, "
                    f"{item['name']}) == {item['offset']}u);")
        lines.append(f"}} // namespace {owner}")
    if compute_records:
        lines.append("")
    for record in compute_records:
        owner, name = record["canonical"].split(":", 1)
        instance_type = cpp_name(record["instance"], module.content_id)
        lines.extend([
            "template <>",
            f"struct compute_traits<{owner}::{name}> {{",
            "    static inline EngineComputeId id{};",
            f"    using state = {owner}::{name}::state;",
            f"    using instance = {instance_type};",
            f"    static constexpr const char* canonical_name = "
            f"{c_string(runtime_name(record['canonical']))};",
            f"    static constexpr uint64_t state_fingerprint = "
            f"{record['state_fingerprint']}ull;",
            f"    static constexpr uint32_t state_size = "
            f"{record['state_size']}u;",
            f"    static constexpr uint32_t state_alignment = "
            f"{record['state_alignment']}u;",
            f"    static constexpr uint32_t instance_size = "
            f"sizeof(instance);",
            "};",
        ])
    if module.computes:
        lines.append("")
        for item in module.computes:
            lines.append(f"using {item.name} = {module.content_id}::{item.name};")
        lines.append("")
    for record in component_records:
        type_name = cpp_name(record["canonical"], module.content_id)
        lines.extend([
            "template <>",
            f"struct component_traits<{type_name}> {{",
            "    static inline EngineComponentId id{};",
            f"    static constexpr const char* canonical_name = "
            f"{c_string(runtime_name(record['canonical']))};",
            f"    static constexpr uint64_t fingerprint = "
            f"{record['fingerprint']}ull;",
            f"    static constexpr uint32_t size = {record['size']}u;",
            f"    static constexpr uint32_t alignment = "
            f"{record['alignment']}u;",
            f"    static constexpr uint32_t residency = "
            f"{record['residency']}u;",
            "};",
        ])
    for record in event_records:
        type_name = cpp_name(record["canonical"], module.content_id)
        lines.extend([
            "template <>",
            f"struct event_traits<{type_name}> {{",
            "    static inline EngineEventId id{};",
            f"    static constexpr const char* canonical_name = "
            f"{c_string(runtime_name(record['canonical']))};",
            f"    static constexpr uint64_t fingerprint = "
            f"{record['fingerprint']}ull;",
            f"    static constexpr uint32_t size = {record['size']}u;",
            f"    static constexpr uint32_t alignment = {record['alignment']}u;",
            f"    static constexpr uint32_t residency = {record['residency']}u;",
            "};",
        ])
    for record in entity_records:
        owner, name = record["canonical"].split(":", 1)
        marker = f"{owner}::{name}"
        lines.extend([
            "template <>",
            f"struct prefab_traits<{marker}> {{",
            "    static inline EnginePrefabId id{};",
            f"    static constexpr const char* canonical_name = "
            f"{c_string(runtime_name(record['canonical']))};",
            f"    static constexpr uint64_t fingerprint = "
            f"{record['fingerprint']}ull;",
            f"    static constexpr uint32_t residency = "
            f"{record['residency']}u;",
            "};",
        ])
    local_entities = [item.name for item in module.entities]
    if local_entities:
        lines.append("")
        for name in local_entities:
            lines.append(f"using {name} = {module.content_id}::{name};")

    # Generate deterministic direct-child views for generic content logic.
    # IDs are read from the generated traits on every call so the arrays never
    # retain handles from an earlier runtime generation.
    component_children: dict[str, list[str]] = {
        record["canonical"]: [] for record in component_records}
    for record in component_records:
        base = record.get("base")
        if not base:
            continue
        children = component_children.setdefault(base, [])
        if record["canonical"] not in children:
            children.append(record["canonical"])
    for base, children in component_children.items():
        base_type = cpp_name(base, module.content_id)
        lines.extend([
            "",
            "template <>",
            f"struct component_children_traits<{base_type}> {{",
            "    static auto ids() {",
            f"        return std::array<EngineComponentId, {len(children)}>{{{{",
        ])
        for child in children:
            lines.append(
                f"            component_traits<{cpp_name(child, module.content_id)}>::id,")
        lines.extend(["        }};", "    }", "};"])

    return "\n".join(lines)


def c_string(value: str) -> str:
    return json.dumps(value)


def c_float(value: float) -> str:
    rendered = format(value, ".9g")
    if "." not in rendered and "e" not in rendered:
        rendered += ".0"
    return rendered + "f"


def build_shader_wgsl(component: Component) -> str:
    shader = component.shader
    if not shader:
        return ""
    parameters = ["@location(0) local_position: vec2f"]
    shader_fields = [
        item for item in component.fields
        if item.count == 1 and item.type_name in TYPE_INFO
        and TYPE_INFO[item.type_name][3] is not None]
    for location, item in enumerate(shader_fields, 1):
        parameters.append(f"@location({location}) {item.name}: {WGSL_TYPE[item.type_name]}")
    vertex_members = ["    @builtin(position) position: vec4f,"]
    fragment_members: list[str] = []
    for location, (name, type_name) in enumerate(shader.bridge):
        interpolation = " @interpolate(flat)" if type_name in {"i32", "u32"} else ""
        vertex_members.append(
            f"    @location({location}){interpolation} {name}: {type_name},")
        fragment_members.append(
            f"    @location({location}){interpolation} {name}: {type_name},")
    lines = [
        "struct Builtins {",
        "    projection: mat4x4f,",
        "};",
        "",
        "@group(0) @binding(0) var<uniform> engine: Builtins;",
        "",
        "struct EngineVertexOut {",
        *vertex_members,
        "};",
    ]
    for index, (binding_name, _) in enumerate(shader.textures):
        texture_var = f"engine_texture_{binding_name}"
        sampler_var = f"engine_sampler_{binding_name}"
        helper = "sample_texture" if (
            len(shader.textures) == 1 and binding_name == "texture") \
            else f"sample_{binding_name}"
        lines.extend([
            "",
            f"@group(1) @binding({index * 2}) var {texture_var}: texture_2d<f32>;",
            f"@group(1) @binding({index * 2 + 1}) var {sampler_var}: sampler;",
            "",
            f"fn {helper}(uv: vec2f) -> vec4f {{",
            f"    return textureSample({texture_var}, {sampler_var}, uv);",
            "}",
        ])
    if shader.bridge:
        lines.extend(["", "struct EngineFragmentIn {", *fragment_members, "};"])
    lines.extend([
        "",
        "struct EngineFragmentOut {",
        "    @location(0) color: vec4f,",
        "};",
        "",
        "@vertex",
        "fn vs_main(",
        "    " + ",\n    ".join(parameters),
        ") -> EngineVertexOut {",
        "    var out: EngineVertexOut;",
        "    let projection = engine.projection;",
        "    let local_uv = vec2f(local_position.x + 0.5, 0.5 - local_position.y);",
        shader.vertex_body,
        "    return out;",
        "}",
        "",
        "@fragment",
        "fn fs_main(" + ("in: EngineFragmentIn" if shader.bridge else "") + ") -> EngineFragmentOut {",
        "    var out: EngineFragmentOut;",
        shader.fragment_body,
        "    return out;",
        "}",
    ])
    return "\n".join(lines)


def wgsl_packed_load(buffer: str, base: str, field: Field) -> str:
    word = field.offset // 4
    type_name = WGSL_TYPE[field.type_name]
    if type_name == "f32":
        return f"bitcast<f32>({buffer}[{base} + {word}u])"
    if type_name in {"i32", "u32"}:
        cast = "bitcast<i32>" if type_name == "i32" else "u32"
        return f"{cast}({buffer}[{base} + {word}u])"
    count = int(type_name[3])
    scalar = "f32"
    values = ", ".join(
        f"bitcast<{scalar}>({buffer}[{base} + {word + index}u])"
        for index in range(count))
    return f"{type_name}({values})"


def wgsl_packed_store(
        buffer: str, base: str, field: Field, value: str) -> list[str]:
    word = field.offset // 4
    type_name = WGSL_TYPE[field.type_name]
    if type_name in {"f32", "i32"}:
        return [f"    {buffer}[{base} + {word}u] = bitcast<u32>({value});"]
    if type_name == "u32":
        return [f"    {buffer}[{base} + {word}u] = {value};"]
    count = int(type_name[3])
    names = "xyzw"
    return [
        f"    {buffer}[{base} + {word + index}u] = "
        f"bitcast<u32>({value}.{names[index]});"
        for index in range(count)]


def build_compute_wgsl(compute: Compute, instance: Component | dict) -> str:
    state_words = compute.size // 4
    instance_size = instance.size if isinstance(instance, Component) else instance["size"]
    instance_fields = instance.fields if isinstance(instance, Component) else [
        Field(
            item["type"], item["name"], count=item["count"],
            offset=item["offset"], size=item["size"])
        for item in instance["fields"]]
    instance_words = instance_size // 4
    supported_instance_fields = [
        item for item in instance_fields
        if item.count == 1 and item.type_name in WGSL_TYPE]
    command_words = 1 + state_words + instance_words
    lines = [
        "struct ParticleState {",
        *[f"    {item.name}: {WGSL_TYPE[item.type_name]}," for item in compute.fields],
        "};",
        "struct ParticleInstance {",
        *[f"    {item.name}: {WGSL_TYPE[item.type_name]}," for item in supported_instance_fields],
        "};",
        "struct ParticleParams { dt: f32, frame: u32, capacity: u32, spawn_count: u32 };",
        "@group(0) @binding(0) var<storage, read_write> state_words: array<u32>;",
        "@group(0) @binding(1) var<storage, read_write> instance_words: array<u32>;",
        "@group(0) @binding(2) var<storage, read_write> metadata: array<atomic<u32>>;",
        "@group(0) @binding(3) var<storage, read> spawn_words: array<u32>;",
        "@group(0) @binding(4) var<storage, read_write> compact_words: array<u32>;",
        "@group(0) @binding(5) var<storage, read_write> indirect: array<atomic<u32>>;",
        "@group(0) @binding(6) var<uniform> params: ParticleParams;",
        "",
        "fn hash_u32(value: u32) -> u32 {",
        "    var x = value;",
        "    x = ((x >> 16u) ^ x) * 0x45d9f3bu;",
        "    x = ((x >> 16u) ^ x) * 0x45d9f3bu;",
        "    return (x >> 16u) ^ x;",
        "}",
        "fn random_f32(value: u32) -> f32 {",
        "    return f32(hash_u32(value) & 0x00ffffffu) / 16777216.0;",
        "}",
        "",
        "fn load_state(index: u32) -> ParticleState {",
        f"    let base = index * {state_words}u;",
        "    return ParticleState(",
        *[
            f"        {wgsl_packed_load('state_words', 'base', item)},"
            for item in compute.fields],
        "    );",
        "}",
        "fn store_state(index: u32, value: ParticleState) {",
        f"    let base = index * {state_words}u;",
    ]
    for item in compute.fields:
        lines.extend(wgsl_packed_store("state_words", "base", item, f"value.{item.name}"))
    lines.extend([
        "}",
        "fn load_instance(index: u32) -> ParticleInstance {",
        f"    let base = index * {instance_words}u;",
        "    return ParticleInstance(",
        *[
            f"        {wgsl_packed_load('instance_words', 'base', item)},"
            for item in supported_instance_fields],
        "    );",
        "}",
        "fn store_instance(index: u32, value: ParticleInstance) {",
        f"    let base = index * {instance_words}u;",
    ])
    for item in supported_instance_fields:
        lines.extend(wgsl_packed_store(
            "instance_words", "base", item, f"value.{item.name}"))
    lines.extend([
        "}",
        "",
        "@compute @workgroup_size(256)",
        "fn spawn_main(@builtin(global_invocation_id) gid: vec3u) {",
        "    let command = gid.x;",
        "    if (command >= params.spawn_count) { return; }",
        f"    let source = command * {command_words}u;",
        "    let slot = spawn_words[source];",
        "    if (slot >= params.capacity) { return; }",
        f"    let state_base = slot * {state_words}u;",
        f"    for (var word = 0u; word < {state_words}u; word++) {{",
        "        state_words[state_base + word] = spawn_words[source + 1u + word];",
        "    }",
        f"    let instance_base = slot * {instance_words}u;",
        f"    for (var word = 0u; word < {instance_words}u; word++) {{",
        f"        instance_words[instance_base + word] = "
        f"spawn_words[source + 1u + {state_words}u + word];",
        "    }",
        "    atomicStore(&metadata[slot * 2u], 1u);",
        "    atomicStore(&metadata[slot * 2u + 1u], 1u);",
        "}",
        "",
        "@compute @workgroup_size(256)",
        "fn update_main(@builtin(global_invocation_id) gid: vec3u) {",
        "    let index = gid.x;",
        "    if (index >= params.capacity || atomicLoad(&metadata[index * 2u]) == 0u) { return; }",
        "    var state = load_state(index);",
        "    var instance = load_instance(index);",
        "    let dt = params.dt;",
        "    let frame = params.frame;",
        "    var alive = true;",
        "    var spawned = atomicLoad(&metadata[index * 2u + 1u]) != 0u;",
        "    if (spawned) {",
        "        atomicStore(&metadata[index * 2u + 1u], 0u);",
        "    } else {",
        *["        " + line for line in compute.logic.splitlines()],
        "    }",
        "    if (!alive) { atomicStore(&metadata[index * 2u], 0u); return; }",
        "    store_state(index, state);",
        "    store_instance(index, instance);",
        "    let output = atomicAdd(&indirect[1], 1u);",
        f"    let source = index * {instance_words}u;",
        f"    let destination = output * {instance_words}u;",
        f"    for (var word = 0u; word < {instance_words}u; word++) {{",
        "        compact_words[destination + word] = instance_words[source + word];",
        "    }",
        "}",
    ])
    return "\n".join(lines)


def component_id_expression(reference: str, current_content: str) -> str:
    if reference == "c_audio_source" or reference == "builtin:c_audio_source":
        return "component_traits<c_audio_source>::id"
    return (
        "component_traits<"
        f"{cpp_name(reference, current_content)}>::id")


def event_id_expression(reference: str, current_content: str) -> str:
    type_name = reference.replace(":", "::")
    return f"event_traits<{type_name}>::id"


def entity_type_expression(reference: str, current_content: str) -> str:
    canonical = reference if ":" in reference \
        else f"{current_content}:{reference}"
    owner, name = canonical.split(":", 1)
    return f"prefab_traits<{owner}::{name}>::id"


def render_cpp(module: Module, dependencies: dict[str, dict]) -> str:
    component_records = {
        record["canonical"]: record
        for record in BUILTIN_COMPONENTS.values()
    }
    component_records.update({
        record["canonical"]: record
        for document in dependencies.values()
        for record in document.get("components", [])
    })
    component_records.update({
        f"{module.content_id}:{item.name}": component_record(module.content_id, item)
        for item in module.components})
    event_records = {
        record["canonical"]: record
        for document in dependencies.values()
        for record in document.get("events", [])
    }
    event_records.update({
        f"{module.content_id}:{item.name}": event_record(module.content_id, item)
        for item in module.events})
    texture_slice_records = []
    for document in [*dependencies.values(), api_document(module)]:
        owner = document["content"]
        for atlas in document.get("textures", []):
            for item in atlas.get("slices", []):
                texture_slice_records.append({
                    **item,
                    "marker_name": item.get("marker_name", item["name"]),
                    "canonical": f"{owner}:{item.get('marker_name', item['name'])}",
                    "atlas": atlas["canonical"],
                })

    def term_is_tag(reference: str) -> bool:
        canonical = reference if ":" in reference else f"{module.content_id}:{reference}"
        return component_records[canonical]["size"] == 0

    def event_role_index(observer: Observer, term: Term) -> int:
        if not term.role:
            return 0
        canonical = observer.event if ":" in observer.event \
            else f"{module.content_id}:{observer.event}"
        record = event_records[canonical]
        names = [item["name"] for item in record.get("roles", [])]
        return names.index(term.role) + 1

    lines = [
        '#include "content_generated.h"', '#include "content_api.h"',
        '#include "registry.hpp"', '#include "input.hpp"',
        "",
        "using entity_handle = entity;",
        "",
        "namespace {",
        "const EngineApi* g_api = nullptr;",
        "void* g_engine_context = nullptr;",
        "EngineStructHeader struct_header(uint32_t size) { return {size}; }",
        "void content_log(const char* message) {",
        "    if (g_api && g_api->log) g_api->log(g_engine_context, 1u, message);",
        "}",
    ]
    for component in module.components:
        if component.fields:
            lines.append(
                f"const {cpp_name(component.name, module.content_id)} "
                f"default_{component.name}{{}};")
        if component.shader:
            delimiter = "WGSL"
            while f"){delimiter}\"" in component.shader.wgsl:
                delimiter += "_"
            lines.append(
                f"constexpr char shader_{component.name}[] = R\"{delimiter}({component.shader.wgsl}){delimiter}\";")
    for compute in module.computes:
        delimiter = "NL_COMPUTE"
        while f"){delimiter}\"" in compute.wgsl:
            delimiter += "_"
        lines.append(
            f"constexpr char compute_{compute.name}[] = "
            f"R\"{delimiter}({compute.wgsl}){delimiter}\";")
    lines.append("}")
    if module.cpp_sources:
        lines.extend([
            "",
            "// Ordinary C++ preserved from mixed content files.",
        ])
        for source in module.cpp_sources:
            source_name = source.path.relative_to(module.root).as_posix()
            lines.extend([
                f"#line 1 {c_string(source_name)}",
                source.text.rstrip(),
                '#line 1 "content_generated.cpp"',
            ])
    lines.extend([
        'extern "C" int32_t content_get_setup(EngineContentSetup* setup) {',
        "    if (!setup || setup->header.struct_size != sizeof(*setup)) return 0;",
        f"    setup->simulation = {'SIMULATION_CLIENT' if module.simulation == 'client' else 'SIMULATION_SERVER_CLIENT'};",
        f"    setup->ticks_per_second = {module.ticks_per_second}u;",
        f"    setup->project_name = {c_string(module.project_name)};",
        "    return 1;",
        "}",
        "",
        'extern "C" int32_t content_init(EngineContentSharedBlock* shared) {',
        "    if (!shared || shared->header.struct_size != sizeof(*shared)"
        " || !shared->engine || shared->engine->header.struct_size != sizeof(*shared->engine)) return 0;",
        "    g_api = shared->engine; g_engine_context = shared->engine_context;",
        "    bind_content_print(g_api, g_engine_context);",
        "    AssetRegistry assets{shared};",
        "    InputRegistry input{shared};",
    ])
    for handler in module.init_handlers:
        lines.extend([
            "    {",
            "        (void)assets; (void)input;",
            handler.body,
            "    }",
        ])
    lines.extend([
        "    return assets.finish() && input.finish();",
        "}",
        "",
        'extern "C" int32_t content_phase(EngineContentSharedBlock* shared) {',
        "    if (!shared || shared->header.struct_size != sizeof(*shared)"
        " || !shared->engine"
        " || shared->engine->header.struct_size != sizeof(*shared->engine)) return 0;",
        "    g_api = shared->engine; g_engine_context = shared->engine_context;",
        "    bind_content_print(g_api, g_engine_context);",
        "    switch (shared->phase) {",
        "    case PHASE_COMPONENTS:",
    ])
    for component in module.components:
        name = cpp_name(component.name, module.content_id)
        component_size = f"sizeof({name})" if component.fields else "0u"
        component_alignment = f"alignof({name})" if component.fields else "1u"
        lines.extend([
            "    { EngineComponentDesc d{}; d.header = struct_header(sizeof(d));",
            f"      d.name = {c_string(component.name)}; d.size = {component_size}; "
            f"d.alignment = {component_alignment};",
            f"      d.residency = {component.residency}u;",
            f"      d.fingerprint = {component.fingerprint}ull;",
            f"      d.contract_fingerprint = "
            f"{component.contract_fingerprint}ull;",
            (f"      d.default_value = &default_{component.name}; "
             f"d.default_size = sizeof(default_{component.name});"
             if component.fields else
             "      d.default_value = nullptr; d.default_size = 0u;"),
            "      if (!g_api->append_component(g_engine_context, &d)) return 0; }",
        ])
    for event in module.events:
        record = event_records[f"{module.content_id}:{event.name}"]
        lines.extend([
            "    { EngineEventDesc d{}; d.header = struct_header(sizeof(d));",
            f"      d.name = {c_string(event.name)}; d.size = sizeof({cpp_name(event.name, module.content_id)}); "
            f"d.alignment = alignof({cpp_name(event.name, module.content_id)}); d.residency = {event.residency}u;",
            f"      d.fingerprint = {record['fingerprint']}ull; "
            f"d.result = &event_traits<"
            f"{cpp_name(event.name, module.content_id)}>::id;",
            f"      d.role_count = {len(record.get('roles', []))}u;",
        ])
        for role in record.get("roles", []):
            event_type = cpp_name(event.name, module.content_id)
            lines.append(
                f"      d.roles[{record['roles'].index(role)}] = "
                f"{{offsetof({event_type}, {role['name']})}};")
        lines.extend([
            "      if (!g_api->append_event(g_engine_context, &d)) return 0; }",
        ])
    lines.extend([
        "        return 1;",
        "    case PHASE_COMPONENT_BINDINGS:",
    ])
    for record in component_records.values():
        type_name = cpp_name(record["canonical"], module.content_id)
        is_local = record["canonical"].split(":", 1)[0] == module.content_id
        is_tag = record["kind"] == "tag"
        size = "0u" if is_tag else (f"sizeof({type_name})" if is_local else f"{record['size']}u")
        alignment = "1u" if is_tag else (f"alignof({type_name})" if is_local else f"{record['alignment']}u")
        lines.extend([
            f"      if (!g_api->resolve_component(g_engine_context, "
            f"{c_string(runtime_name(record['canonical']))}, {record['fingerprint']}ull, "
            f"{size}, {alignment}, "
            f"{record['residency']}u, "
            f"&component_traits<{type_name}>::id)) return 0;",
        ])
    for component in module.components:
        if not component.base:
            continue
        base_canonical = component.base if ":" in component.base \
            else f"{module.content_id}:{component.base}"
        base_record = component_records[base_canonical]
        lines.append(
            "      if (!g_api->bind_component_base(g_engine_context, "
            f"{component_id_expression(component.name, module.content_id)}, "
            f"{component_id_expression(base_canonical, module.content_id)}, "
            f"{base_record['contract_fingerprint']}ull)) return 0;")
    lines.extend(["        return 1;", "    case PHASE_EVENT_BINDINGS:"])
    for record in event_records.values():
        type_name = cpp_name(record["canonical"], module.content_id)
        lines.append(
            f"      if (!g_api->resolve_event(g_engine_context, "
            f"{c_string(runtime_name(record['canonical']))}, {record['fingerprint']}ull, "
            f"sizeof({type_name}), alignof({type_name}), "
            f"{record['residency']}u, "
            f"&event_traits<{type_name}>::id)) return 0;")
    lines.extend(["        return 1;", "    case PHASE_INIT:"])
    lines.extend(["        return 1;"])
    lines.extend(["    case PHASE_TEXTURE_BINDINGS:"])
    for item in texture_slice_records:
        owner, name = item["canonical"].split(":", 1)
        uv = item["uv"]
        lines.append(
            f"      if (!g_api->bind_texture_slice(g_engine_context, "
            f"{c_string(runtime_name(item['canonical']))}, {c_string(runtime_name(item['atlas']))}, "
            f"{item['width']}u, {item['height']}u, "
            f"{c_float(float(uv[0]))}, {c_float(float(uv[1]))}, "
            f"{c_float(float(uv[2]))}, {c_float(float(uv[3]))}, 0u, "
            f"&texture_traits<{owner}::t_{name}>::value)) return 0;")
    for alias, fallback in sorted(module.cpp_texture_fallbacks.items()):
        lines.append(
            f"      content_log({c_string('texture slice ' + alias + ' is missing; using ' + fallback)});")
    lines.extend(["        return 1;", "    case PHASE_SHADERS:"])
    for component in module.components:
        shader = component.shader
        if not shader:
            continue
        type_name = cpp_name(component.name, module.content_id)
        shader_fields = [
            item for item in component.fields
            if item.count == 1 and item.type_name in TYPE_INFO
            and TYPE_INFO[item.type_name][3] is not None]
        lines.extend([
            "    { EngineShaderDesc d{}; d.header = struct_header(sizeof(d));",
            f"      d.name = {c_string(component.name)}; "
            f"d.component = {component_id_expression(component.name, module.content_id)};",
            f"      d.wgsl_source = shader_{component.name}; d.wgsl_size = sizeof(shader_{component.name}) - 1u;",
            f"      d.instance_stride = sizeof({type_name}); d.blend_mode = " +
            ("BLEND_ALPHA;" if shader.blend == "alpha" else "BLEND_OPAQUE;"),
            f"      d.draw_order = {shader.order};",
            f"      d.attribute_count = {len(shader_fields)}u;",
            f"      d.texture_count = {len(shader.textures)}u;",
            "      d.topology = " + (
                "TOPOLOGY_LINES;" if shader.topology == "lines"
                else "TOPOLOGY_TRIANGLES;"),
            f"      d.mesh = {c_string(shader.mesh) if shader.mesh else 'nullptr'};",
        ])
        for index, (_, texture_reference) in enumerate(shader.textures):
            lines.append(
                f"      d.textures[{index}] = {c_string(texture_reference)};")
        for index, item in enumerate(shader_fields):
            lines.append(
                f"      d.attributes[{index}] = {{{index + 1}u, {TYPE_INFO[item.type_name][3]}, "
                f"(uint32_t)offsetof({type_name}, {item.name})}};")
        lines.append("      if (!g_api->append_shader(g_engine_context, &d)) return 0; }")
    lines.extend(["        return 1;", "    case PHASE_COMPUTES:"])
    for compute in module.computes:
        instance_record = component_records[compute.instance]
        lines.extend([
            "    { EngineComputeDesc d{}; d.header = struct_header(sizeof(d));",
            f"      d.name = {c_string(compute.name)}; "
            f"d.instance_component = "
            f"{component_id_expression(compute.instance, module.content_id)};",
            f"      d.wgsl_source = compute_{compute.name}; "
            f"d.wgsl_size = sizeof(compute_{compute.name}) - 1u;",
            f"      d.state_stride = {compute.size}u; "
            f"d.state_alignment = {compute.alignment}u; "
            f"d.instance_stride = {instance_record['size']}u;",
            f"      d.state_fingerprint = {compute.fingerprint}ull; "
            f"d.instance_fingerprint = {compute.instance_fingerprint}ull;",
            "      if (!g_api->append_compute(g_engine_context, &d)) return 0; }",
        ])
    lines.extend([
        "        return 1;",
        "    case PHASE_COMPUTE_BINDINGS:",
    ])
    compute_binding_records = [
        record
        for document in dependencies.values()
        for record in document.get("computes", [])
    ] + [compute_record(module.content_id, item) for item in module.computes]
    for record in compute_binding_records:
        owner, name = record["canonical"].split(":", 1)
        lines.append(
            f"      if (!g_api->resolve_compute(g_engine_context, "
            f"{c_string(runtime_name(record['canonical']))}, "
            f"{record['state_fingerprint']}ull, {record['state_size']}u, "
            f"{record['state_alignment']}u, "
            f"{component_id_expression(record['instance'], module.content_id)}, "
            f"{record['instance_fingerprint']}ull, "
            f"&compute_traits<{owner}::{name}>::id)) return 0;")
    lines.extend(["        return 1;", "    case PHASE_ENTITIES:"])
    for entity in module.entities:
        lines.extend([
            "    { EnginePrefabDesc d{}; d.header = struct_header(sizeof(d));",
            f"      d.name = {c_string(entity.name)}; "
            f"d.residency = {entity.residency}u; "
            f"d.callback = {entity.callback}u; "
            f"d.fingerprint = {entity.fingerprint}ull;",
            "      if (!g_api->append_prefab(g_engine_context, &d)) return 0; }",
        ])
    lines.extend([
        "        return 1;",
        "    case PHASE_ENTITY_BINDINGS:",
    ])
    entity_binding_records = [
        record
        for document in dependencies.values()
        for record in document.get("entities", [])
    ] + [
        {
            "canonical": f"{module.content_id}:{item.name}",
            "fingerprint": item.fingerprint,
            "residency": item.residency,
        }
        for item in module.entities]
    for record in entity_binding_records:
        owner, name = record["canonical"].split(":", 1)
        lines.append(
            f"      if (!g_api->resolve_prefab(g_engine_context, "
            f"{c_string(runtime_name(record['canonical']))}, {record['fingerprint']}ull, "
            f"{record['residency']}u, "
            f"&prefab_traits<{owner}::{name}>::id)) return 0;")
    lines.extend(["        return 1;", "    case PHASE_OBSERVERS:"])
    for observer in module.observers:
        lines.extend([
            "    { EngineObserverDesc d{}; d.header = struct_header(sizeof(d));",
            f"      d.name = {c_string(observer.name)}; d.world = {WORLD_ENUM[observer.side]};",
            f"      d.callback = {observer.callback}u; d.event = "
            + ("OBSERVER_CUSTOM;" if observer.custom else f"{EVENT_ENUM[observer.event]};"),
            f"      d.order = {observer.order};",
            (f"      d.custom_event = {event_id_expression(observer.event, module.content_id)};"
             if observer.custom else "      d.custom_event = 0;"),
            f"      d.term_count = {len(observer.terms)}u;",
        ])
        for index, term in enumerate(observer.terms):
            lines.append(
                f"      d.terms[{index}] = "
                f"{{{component_id_expression(term.component, module.content_id)}, "
                f"{ACCESS_CPP[term.access]}, {MATCH_ENUM[term.match]}, "
                f"{1 if term.pair_wildcard else 0}, "
                f"{event_role_index(observer, term)}}};")
        lines.append("      if (!g_api->append_observer(g_engine_context, &d)) return 0; }")
    lines.extend(["        return 1;", "    case PHASE_SYSTEMS:"])
    for system in module.systems:
        lines.extend([
            "    { EngineSystemDesc d{}; d.header = struct_header(sizeof(d));",
            f"      d.name = {c_string(system.name)}; d.world = {WORLD_ENUM[system.side]};",
            f"      d.callback = {system.callback}u; d.order = {system.order}; "
            f"d.term_count = {len(system.terms)}u;",
        ])
        for index, term in enumerate(system.terms):
            lines.append(
                f"      d.terms[{index}] = "
                f"{{{component_id_expression(term.component, module.content_id)}, "
                f"{ACCESS_CPP[term.access]}, {MATCH_ENUM[term.match]}, "
                f"{1 if term.pair_wildcard else 0}, "
                f"0}};")
        lines.append("      if (!g_api->append_system(g_engine_context, &d)) return 0; }")
    lines.extend([
        "        return 1;", "    default: return 1;", "    }", "}",
        'extern "C" int32_t content_apply_prefab(uint32_t callback, EnginePrefabApplyContext* ctx) {',
        "    if (!ctx || !g_api) return 0;", "    switch (callback) {",
    ])
    apply_values: list[tuple[int, list[EntityValue]]] = [
        (entity.callback, entity.flattened) for entity in module.entities]
    for callback, values in apply_values:
        lines.append(f"    case {callback}u:")
        for index, value in enumerate(values):
            type_name = cpp_name(value.component, module.content_id)
            record = next(
                (record for record in
                 [*BUILTIN_COMPONENTS.values(),
                  *[component_record(module.content_id, item)
                    for item in module.components]]
                 + [record for document in dependencies.values()
                    for record in document.get("components", [])]
                 if record["canonical"] == value.component), None)
            apply_residency = value.residency
            if record and record["residency"] not in (1, 2, 4):
                apply_residency &= authority_mask(record["residency"])
            if value.pair:
                if record and record["size"] == 0:
                    lines.append(
                        f"      if ((ctx->context.world & {apply_residency}u) && "
                        f"!g_api->component_pair_add(ctx->context.engine_context, "
                        f"ctx->context.world, ctx->entity, "
                        f"{component_id_expression(value.component, module.content_id)}, nullptr, 0u)) return 0;")
                else:
                    lines.extend([
                        f"    {{ const {type_name} value_{index}{{{value.initializer}}};",
                        f"      if ((ctx->context.world & {apply_residency}u) && !g_api->component_pair_add("
                        f"ctx->context.engine_context, ctx->context.world, ctx->entity, "
                        f"{component_id_expression(value.component, module.content_id)}, &value_{index}, sizeof(value_{index}))) return 0; }}",
                    ])
                continue
            if record and record["size"] == 0:
                lines.extend([
                    f"      if ((ctx->context.world & {apply_residency}u) && "
                    f"!g_api->component_add(ctx->context.engine_context, ctx->context.world, "
                    f"ctx->entity, "
                    f"{component_id_expression(value.component, module.content_id)}"
                    f")) return 0;",
                ])
                continue
            lines.extend([
                f"    {{ const {type_name} value_{index}{{{value.initializer}}};",
                f"      if ((ctx->context.world & {apply_residency}u) && "
                f"!g_api->component_set(ctx->context.engine_context, ctx->context.world, ctx->entity, "
                f"{component_id_expression(value.component, module.content_id)}, "
                f"&value_{index}, sizeof(value_{index}))) return 0; }}",
            ])
        lines.append("        return 1;")
    lines.extend(["    default: return 0;", "    }", "}"])
    lines.extend([
        'extern "C" int32_t content_run_system(uint32_t callback, EngineSystemInvocation* invocation) {',
        "    if (!invocation || !g_api) return 0;", "    switch (callback) {",
    ])
    for system in module.systems:
        lines.extend([
            f"    case {system.callback}u: {{",
            f"        if (invocation->context.world != {WORLD_ENUM[system.side]} || invocation->column_count != {len(system.terms)}u) return 0;",
            f"        for (uint32_t i = 0; i < "
            f"{'invocation->count' if system.terms else '1u'}; ++i) {{",
            "            const uint64 tick = invocation->context.tick;",
            "            const float dt = (float)invocation->context.delta_time;",
            "            const EngineContentCallContext& callback_context_internal = invocation->context;",
            "            active_callback_scope callback_scope{callback_context_internal};",
            "            World world{callback_context_internal};",
            "            (void)world; (void)tick; (void)dt;",
        ])
        if not system.global_hook:
            lines.extend([
                "            entity_handle e{callback_context_internal, invocation->count ? invocation->entities[i] : 0u};",
                "            (void)e;",
            ])
        for index, term in enumerate(system.terms):
            if term.match == "exclude":
                continue
            if term.presence_only:
                continue
            type_name = cpp_name(term.component, module.content_id)
            const = "const " if term.access == "read" else ""
            if term_is_tag(term.component):
                lines.append(
                    f"            static const {type_name} tag_{index}{{}};")
                if term.match == "optional":
                    lines.append(
                        f"            const {type_name}* {term.variable} = "
                        f"invocation->columns[{index}].is_set ? "
                        f"&tag_{index} : nullptr;")
                else:
                    lines.append(
                        f"            const {type_name}& {term.variable} = tag_{index};")
            elif term.match == "optional":
                lines.append(
                    f"            {const}{type_name}* {term.variable} = "
                    f"invocation->columns[{index}].data ? "
                    f"&static_cast<{const}{type_name}*>(invocation->columns[{index}].data)[i] : nullptr;")
            else:
                lines.append(
                    f"            {const}{type_name}& {term.variable} = "
                    f"static_cast<{const}{type_name}*>(invocation->columns[{index}].data)[i];")
            if term.pair_wildcard and not term.presence_only:
                lines.append(
                    f"            entity {term.variable}_target{{callback_context_internal, "
                    f"invocation->columns[{index}].pair_target}};")
        lines.extend([f"            {system.body}", "        }", "        return 1;", "    }"])
    lines.extend(["    default: return 0;", "    }", "}"])
    lines.extend([
        'extern "C" int32_t content_run_observer(uint32_t callback, EngineObserverInvocation* invocation) {',
        "    if (!invocation || !g_api) return 0;", "    switch (callback) {",
    ])
    for observer in module.observers:
        lines.extend([
            f"    case {observer.callback}u: {{",
            f"        if (invocation->context.world != {WORLD_ENUM[observer.side]} || "
            f"invocation->event != "
            + ("OBSERVER_CUSTOM" if observer.custom else EVENT_ENUM[observer.event])
            + f" || invocation->column_count != {len(observer.terms)}u) return 0;",
        ])
        if observer.custom:
            known_events = {item.name for item in module.events}
            known_events.update(
                record["canonical"]
                for document in dependencies.values()
                for record in document.get("events", []))
            event_type = (
                cpp_name(observer.event, module.content_id)
                if observer.event in known_events
                else observer.event.replace(":", "::"))
            lines.extend([
                f"        if (!invocation->event_data || invocation->event_size != "
                f"sizeof({event_type})) return 0;",
                f"        {event_type}& event = *static_cast<{event_type}*>(invocation->event_data);",
                "        (void)event;",
            ])
            if observer.context_type:
                lines.extend([
                    f"        {observer.context_type}& ctx = event;",
                    "        (void)ctx;",
                ])
        lines.extend([
            "        for (uint32_t i = 0; i < invocation->count; ++i) {",
            "            const EngineContentCallContext& callback_context_internal = invocation->context;",
            "            active_callback_scope callback_scope{callback_context_internal};",
            "            const uint64 tick = callback_context_internal.tick;",
            "            const float dt = (float)callback_context_internal.delta_time;",
            "            entity_handle e{callback_context_internal, invocation->entities[i]};",
            "            World world{callback_context_internal};",
            "            (void)e; (void)world;",
        ])
        if observer.custom:
            roles = []
            for term in observer.terms:
                if term.role and term.role not in roles:
                    roles.append(term.role)
            for role in roles:
                lines.extend([
                    f"            entity {role}_entity = "
                    f"world.from_stable_id(event.{role});",
                    f"            (void){role}_entity;",
                ])
        for index, term in enumerate(observer.terms):
            if term.match == "exclude":
                continue
            if term.presence_only:
                continue
            type_name = cpp_name(term.component, module.content_id)
            const = "const " if term.access == "read" else ""
            if term_is_tag(term.component):
                lines.append(
                    f"            static const {type_name} tag_{index}{{}};")
                if term.match == "optional":
                    lines.append(
                        f"            const {type_name}* {term.variable} = "
                        f"invocation->columns[{index}].is_set ? "
                        f"&tag_{index} : nullptr;")
                else:
                    lines.append(
                        f"            const {type_name}& {term.variable} = tag_{index};")
            elif term.match == "optional":
                lines.append(
                    f"            {const}{type_name}* {term.variable} = "
                    f"invocation->columns[{index}].data ? "
                    f"&static_cast<{const}{type_name}*>(invocation->columns[{index}].data)[i] : nullptr;")
            else:
                lines.append(
                    f"            {const}{type_name}& {term.variable} = "
                    f"static_cast<{const}{type_name}*>(invocation->columns[{index}].data)[i];")
            if term.pair_wildcard and not term.presence_only:
                lines.append(
                    f"            entity {term.variable}_target{{callback_context_internal, "
                    f"invocation->columns[{index}].pair_target}};")
        lines.extend([f"            {observer.body}", "        }", "        return 1;", "    }"])
    lines.extend(["    default: return 0;", "    }", "}", ""])
    lines.extend([
        'extern "C" int32_t content_run_start(uint32_t side, '
        'EngineContentCallContext* invocation) {',
        "    if (!invocation || !g_api) return 0;",
        "    if (invocation->world != side) return 0;",
        "    const EngineContentCallContext& callback_context_internal = *invocation;",
        "    active_callback_scope callback_scope{callback_context_internal};",
        "    World world{callback_context_internal};",
        "    (void)world;",
    ])
    for handler in module.start_handlers:
        lines.extend([
            f"    if (side == {WORLD_ENUM[handler.side]}) {{",
            handler.body,
            "    }",
        ])
    lines.extend(["    return 1;", "}", ""])
    return "\n".join(lines)


def write_if_changed(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    if path.exists() and path.read_bytes() == encoded:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def generate(
        content_root: Path,
        output: Path,
        *,
        asset_manifest: Path | None = None,
        simulation: str = "server_client",
        ticks_per_second: int = 30,
        project_name: str = "Content") -> None:
    module = load_module(
        content_root, asset_manifest, simulation, ticks_per_second, project_name)
    write_if_changed(output / "content_generated.h", render_header(module, {}))
    write_if_changed(output / "content_generated.cpp", render_cpp(module, {}))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-manifest", type=Path)
    parser.add_argument(
        "--simulation", choices=("client", "server_client"), required=True)
    parser.add_argument("--ticks-per-second", type=int, required=True)
    parser.add_argument("--project-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        generate(
            args.content_root.resolve(), args.output.resolve(),
            asset_manifest=args.asset_manifest.resolve() if args.asset_manifest else None,
            simulation=args.simulation,
            ticks_per_second=args.ticks_per_second,
            project_name=args.project_name)
    except (CodegenError, OSError, json.JSONDecodeError) as error:
        print(f"content codegen error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
