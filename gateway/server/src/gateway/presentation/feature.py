from collections.abc import Sequence
from dataclasses import dataclass

import pyrpckit as rpc
from dishka import Provider
from fastapi import APIRouter, FastAPI


@dataclass(frozen=True, slots=True)
class Feature:
    name: str
    routers: Sequence[APIRouter] = ()
    providers: Sequence[type[Provider]] = ()
    module: rpc.RpcModule | None = None

    def install(self, app: FastAPI) -> None:
        for router in self.routers:
            app.include_router(router)
