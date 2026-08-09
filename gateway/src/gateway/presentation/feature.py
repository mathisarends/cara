from collections.abc import Callable, Sequence
from dataclasses import dataclass

from dishka import Provider
from fastapi import APIRouter, FastAPI


@dataclass(frozen=True, slots=True)
class Feature:
    name: str
    routers: Sequence[APIRouter] = ()
    providers: Sequence[type[Provider]] = ()
    register_exception_handlers: Callable[[FastAPI], None] | None = None

    def install(self, app: FastAPI) -> None:
        for router in self.routers:
            app.include_router(router)
        if self.register_exception_handlers is not None:
            self.register_exception_handlers(app)
