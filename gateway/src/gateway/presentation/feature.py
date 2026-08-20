from collections.abc import Sequence
from dataclasses import dataclass

from dishka import Provider
from fastapi import APIRouter, FastAPI


@dataclass(frozen=True, slots=True)
class Feature:
    name: str
    routers: Sequence[APIRouter] = ()
    providers: Sequence[type[Provider]] = ()

    def install(self, app: FastAPI) -> None:
        for router in self.routers:
            app.include_router(router)
