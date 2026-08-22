from pydantic import BaseModel

from gateway.presentation import rpc


class _Params(BaseModel):
    pass


class _Result(BaseModel):
    pass


def test_method_summary_uses_explicit_value_when_given() -> None:
    class Handlers(rpc.RpcHandler):
        @rpc.method("explicit", summary="Explicit summary.")
        async def handle(self, params: _Params) -> _Result:
            """Docstring summary, should be ignored."""
            raise AssertionError

    metadata = Handlers.handle.__cara_rpc_method__
    assert metadata.summary == "Explicit summary."


def test_method_summary_falls_back_to_docstring_first_line() -> None:
    class Handlers(rpc.RpcHandler):
        @rpc.method("inferred")
        async def handle(self, params: _Params) -> _Result:
            """Inferred summary.

            Further details that are not part of the summary.
            """
            raise AssertionError

    metadata = Handlers.handle.__cara_rpc_method__
    assert metadata.summary == "Inferred summary."


def test_method_summary_is_none_without_explicit_value_or_docstring() -> None:
    class Handlers(rpc.RpcHandler):
        @rpc.method("undocumented")
        async def handle(self, params: _Params) -> _Result:
            raise AssertionError

    metadata = Handlers.handle.__cara_rpc_method__
    assert metadata.summary is None
