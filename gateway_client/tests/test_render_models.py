import pytest

_EVENT_SCHEMAS = {
    "DeltaPayload": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "CompletedPayload": {
        "type": "object",
        "properties": {"finish_reason": {"type": "string"}},
        "required": ["finish_reason"],
    },
    "DeltaEvent": {
        "type": "object",
        "properties": {
            "type": {"const": "chat.delta", "type": "string"},
            "event_id": {"type": "string", "format": "uuid"},
            "metadata": {"type": "object", "additionalProperties": True},
            "data": {"$ref": "#/components/schemas/DeltaPayload"},
        },
        "required": ["type", "event_id", "data"],
    },
    "CompletedEvent": {
        "type": "object",
        "properties": {
            "type": {"const": "chat.completed", "type": "string"},
            "event_id": {"type": "string", "format": "uuid"},
            "metadata": {"type": "object", "additionalProperties": True},
            "data": {"$ref": "#/components/schemas/CompletedPayload"},
        },
        "required": ["type", "event_id", "data"],
    },
    "EventMessage": {
        "oneOf": [
            {"$ref": "#/components/schemas/DeltaEvent"},
            {"$ref": "#/components/schemas/CompletedEvent"},
        ],
        "discriminator": {
            "propertyName": "type",
            "mapping": {
                "chat.delta": "#/components/schemas/DeltaEvent",
                "chat.completed": "#/components/schemas/CompletedEvent",
            },
        },
    },
}


def test_maps_scalar_types_and_string_formats(generator, build_spec) -> None:
    spec = build_spec(
        {
            "Item": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "format": "uuid"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "name": {"type": "string"},
                    "count": {"type": "integer"},
                    "ratio": {"type": "number"},
                    "active": {"type": "boolean"},
                },
                "required": ["id", "created_at", "name", "count", "ratio", "active"],
            }
        }
    )

    source = generator.render_models(spec)

    assert "class Item(BaseModel):" in source
    assert "    id: UUID" in source
    assert "    created_at: datetime" in source
    assert "    name: str" in source
    assert "    count: int" in source
    assert "    ratio: float" in source
    assert "    active: bool" in source


def test_optional_fields_get_container_or_none_defaults(generator, build_spec) -> None:
    spec = build_spec(
        {
            "Item": {
                "type": "object",
                "properties": {
                    "metadata": {"type": "object", "additionalProperties": True},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "note": {"type": "string"},
                    "anything": {},
                },
            }
        }
    )

    source = generator.render_models(spec)

    assert "    metadata: dict[str, Any] = Field(default_factory=dict)" in source
    assert "    tags: list[str] = Field(default_factory=list)" in source
    assert "    note: str | None = None" in source
    assert "    anything: Any = None" in source


def test_translates_constraints_into_field_arguments(generator, build_spec) -> None:
    spec = build_spec(
        {
            "Item": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "minLength": 1},
                    "size": {"type": "integer", "minimum": 0, "maximum": 10},
                },
                "required": ["text", "size"],
            }
        }
    )

    source = generator.render_models(spec)

    assert "    text: str = Field(min_length=1)" in source
    assert "    size: int = Field(ge=0, le=10)" in source


def test_renders_const_with_default_as_literal(generator, build_spec) -> None:
    spec = build_spec(
        {
            "Health": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "const": "ok", "default": "ok"}
                },
            }
        }
    )

    source = generator.render_models(spec)

    # Quote style is ruff format's job, which runs after rendering.
    assert "    status: Literal['ok'] = 'ok'" in source


def test_strips_leading_underscore_from_schema_names(generator, build_spec) -> None:
    spec = build_spec({"_Internal": {"type": "object", "properties": {}}})

    source = generator.render_models(spec)

    assert "class Internal(BaseModel):" in source


def test_orders_models_after_the_schemas_they_reference(generator, build_spec) -> None:
    spec = build_spec(
        {
            "Envelope": {
                "type": "object",
                "properties": {"item": {"$ref": "#/components/schemas/Item"}},
                "required": ["item"],
            },
            "Item": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }
    )

    source = generator.render_models(spec)

    assert source.index("class Item(") < source.index("class Envelope(")


def test_factors_shared_union_fields_into_a_base_class(generator, build_spec) -> None:
    source = generator.render_models(build_spec(_EVENT_SCHEMAS))

    assert "class EventType(StrEnum):" in source
    assert '    CHAT_DELTA = "chat.delta"' in source
    assert "class EventBase(BaseModel):" in source
    assert "    event_id: UUID" in source
    assert "    metadata: dict[str, Any] = Field(default_factory=dict)" in source
    assert "class DeltaEvent(EventBase):" in source
    assert "    type: Literal[EventType.CHAT_DELTA]" in source
    assert "    data: DeltaPayload" in source
    assert 'Field(discriminator="type")' in source
    assert "event_adapter: TypeAdapter[EventMessage] = TypeAdapter(EventMessage)" in (
        source
    )


def test_union_members_do_not_repeat_the_shared_fields(generator, build_spec) -> None:
    source = generator.render_models(build_spec(_EVENT_SCHEMAS))

    member = source[source.index("class DeltaEvent(") :]
    member = member[: member.index("class CompletedEvent(")]

    assert "event_id" not in member
    assert "metadata" not in member


def test_generated_models_parse_a_discriminated_event(
    generator, build_spec, load_module
) -> None:
    namespace = load_module(generator.render_models(build_spec(_EVENT_SCHEMAS)))

    event = namespace["event_adapter"].validate_python(
        {
            "type": "chat.delta",
            "event_id": "00000000-0000-0000-0000-000000000001",
            "data": {"text": "hi"},
        }
    )

    assert isinstance(event, namespace["DeltaEvent"])
    assert event.data.text == "hi"
    assert event.metadata == {}


def test_generated_models_ignore_unknown_server_fields(
    generator, build_spec, load_module
) -> None:
    spec = build_spec(
        {
            "Item": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        }
    )
    namespace = load_module(generator.render_models(spec))

    item = namespace["Item"].model_validate({"name": "a", "added_later": 1})

    assert item.name == "a"


def test_rejects_inline_object_schemas(generator, build_spec) -> None:
    spec = build_spec(
        {
            "Item": {
                "type": "object",
                "properties": {
                    "nested": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    }
                },
                "required": ["nested"],
            }
        }
    )

    with pytest.raises(generator.UnsupportedSchemaError, match="Inline object"):
        generator.render_models(spec)


def test_rejects_unions_without_a_discriminator(generator, build_spec) -> None:
    spec = build_spec(
        {
            "Item": {"type": "object", "properties": {}},
            "Union": {"oneOf": [{"$ref": "#/components/schemas/Item"}]},
        }
    )

    with pytest.raises(generator.UnsupportedSchemaError, match="discriminator"):
        generator.render_models(spec)
