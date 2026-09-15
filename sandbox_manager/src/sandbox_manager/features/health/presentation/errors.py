from fastapi_canon import Error, ErrorRegistry

from sandbox_manager.features.health.application import DependencyUnavailableError

DEPENDENCY_UNAVAILABLE = Error(
    DependencyUnavailableError,
    status=503,
    code="dependency_unavailable",
    title="Dependency unavailable",
    detail=str,
)

HEALTH_ERRORS = ErrorRegistry(
    name="health",
    errors=[DEPENDENCY_UNAVAILABLE],
)
