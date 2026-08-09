import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from gateway.lifespan import lifespan

app = FastAPI(title="Cara Gateway", lifespan=lifespan)


class HealthResponse(BaseModel):
    status: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


if __name__ == "__main__":
    uvicorn.run("gateway.main:app", reload=True)
