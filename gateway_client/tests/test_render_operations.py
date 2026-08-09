import pytest

_SCHEMAS = {
    "ChatRequest": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    "SessionResponse": {
        "type": "object",
        "properties": {"id": {"type": "string", "format": "uuid"}},
        "required": ["id"],
    },
}
_SESSION_ID = {
    "name": "session_id",
    "in": "path",
    "required": True,
    "schema": {"type": "string", "format": "uuid"},
}


def _operation(**overrides):
    return {
        "tags": ["sessions"],
        "operationId": "get_session",
        "responses": {
            "200": {
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/SessionResponse"}
                    }
                }
            }
        },
        **overrides,
    }


def test_groups_operations_into_one_namespace_per_tag(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/health": {
                "get": {
                    "tags": ["system"],
                    "operationId": "get_gateway_health",
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/v1/sessions/{session_id}": {"get": _operation(parameters=[_SESSION_ID])},
        },
    )

    source = generator.render_operations(spec)

    assert "class SystemOperations:" in source
    assert "class SessionsOperations:" in source
    assert "    async def get_gateway_health(self) -> None:" in source
    assert source.index("class SystemOperations:") < source.index(
        "class SessionsOperations:"
    )


def test_renders_path_parameters_into_signature_and_url(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {"/v1/sessions/{session_id}": {"get": _operation(parameters=[_SESSION_ID])}},
    )

    source = generator.render_operations(spec)

    assert "    async def get_session(self, session_id: UUID) -> SessionResponse:" in (
        source
    )
    assert 'request("GET", f"/v1/sessions/{session_id}")' in source
    assert "return SessionResponse.model_validate_json(response.content)" in source


def test_paths_without_parameters_are_plain_strings(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/sessions": {
                "get": _operation(operationId="list_sessions", parameters=[])
            }
        },
    )

    source = generator.render_operations(spec)

    assert 'request("GET", "/v1/sessions")' in source


def test_renders_request_body_as_a_typed_argument(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/sessions/{session_id}/chat": {
                "post": _operation(
                    operationId="start_chat",
                    parameters=[_SESSION_ID],
                    requestBody={
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ChatRequest"}
                            }
                        },
                    },
                    responses={"202": {"description": "accepted"}},
                )
            }
        },
    )

    source = generator.render_operations(spec)

    assert "session_id: UUID, body: ChatRequest) -> None:" in source
    assert 'json=body.model_dump(mode="json")' in source
    assert "response =" not in source


def test_renders_free_form_object_responses_as_dicts(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/schemas/events": {
                "get": _operation(
                    tags=["events"],
                    operationId="get_event_schema",
                    responses={
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "additionalProperties": True,
                                    }
                                }
                            }
                        }
                    },
                )
            }
        },
    )

    source = generator.render_operations(spec)

    assert "    async def get_event_schema(self) -> dict[str, Any]:" in source
    assert "        return response.json()" in source


def test_wires_every_namespace_into_the_api_class(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/health": {
                "get": {
                    "tags": ["system"],
                    "operationId": "get_gateway_health",
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/v1/sessions/{session_id}": {"get": _operation(parameters=[_SESSION_ID])},
        },
    )

    source = generator.render_operations(spec)

    assert "class GatewayApi:" in source
    assert "        self.system = SystemOperations(transport)" in source
    assert "        self.sessions = SessionsOperations(transport)" in source


def test_generated_operations_are_valid_python(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {"/v1/sessions/{session_id}": {"get": _operation(parameters=[_SESSION_ID])}},
    )

    compile(generator.render_operations(spec), "<generated operations>", "exec")


def test_imports_only_the_models_the_operations_use(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {"/v1/sessions/{session_id}": {"get": _operation(parameters=[_SESSION_ID])}},
    )

    source = generator.render_operations(spec)

    assert "from gateway_client.models import SessionResponse" in source
    assert "ChatRequest" not in source


def test_rejects_non_path_parameters(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/sessions": {
                "get": _operation(
                    operationId="list_sessions",
                    parameters=[
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                        }
                    ],
                )
            }
        },
    )

    with pytest.raises(generator.UnsupportedSchemaError, match="path parameters"):
        generator.render_operations(spec)


def test_rejects_operations_without_a_tag(generator, build_spec) -> None:
    spec = build_spec(_SCHEMAS, {"/v1/sessions": {"get": _operation(tags=[])}})

    with pytest.raises(generator.UnsupportedSchemaError, match="without tag"):
        generator.render_operations(spec)


def test_rejects_operations_without_a_success_response(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {"/v1/sessions": {"get": _operation(responses={"404": {"description": "no"}})}},
    )

    with pytest.raises(generator.UnsupportedSchemaError, match="No success response"):
        generator.render_operations(spec)


def test_rejects_inline_request_bodies(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/sessions": {
                "post": _operation(
                    operationId="create_session",
                    requestBody={
                        "content": {"application/json": {"schema": {"type": "object"}}}
                    },
                )
            }
        },
    )

    with pytest.raises(generator.UnsupportedSchemaError, match="Inline request body"):
        generator.render_operations(spec)


def test_rejects_non_json_payloads(generator, build_spec) -> None:
    spec = build_spec(
        _SCHEMAS,
        {
            "/v1/export": {
                "get": _operation(
                    operationId="export",
                    responses={"200": {"content": {"text/csv": {"schema": {}}}}},
                )
            }
        },
    )

    with pytest.raises(generator.UnsupportedSchemaError, match="JSON payloads"):
        generator.render_operations(spec)
