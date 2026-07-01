"""Health and readiness routes."""

from dataclasses import asdict

from fastapi import APIRouter

from app.managers.health_check_manager import HealthCheckManager

router = APIRouter(prefix="/api", tags=["health"])


def create_health_router(health_manager: HealthCheckManager) -> APIRouter:
    """
    Wire health routes to a manager instance.

    Casual: mounts /api/health so Docker can verify the container is up.

    Factory keeps FastAPI route functions free of global state and makes the
    router easy to test with a injected manager.
    """

    @router.get("/health")
    def read_health() -> dict:
        """Liveness probe used by Docker Compose and uptime monitors."""
        return asdict(health_manager.get_status())

    return router
