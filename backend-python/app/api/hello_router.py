"""Hello-world route used by the frontend connectivity check."""

from dataclasses import asdict

from fastapi import APIRouter

from app.managers.hello_manager import HelloManager

router = APIRouter(prefix="/api", tags=["hello"])


def create_hello_router(hello_manager: HelloManager) -> APIRouter:
    """
    Wire hello routes to a manager instance.

    Casual: mounts /api/hello so the React app can prove the API is reachable.

    Factory keeps FastAPI route functions free of global state and makes the
    router easy to test with an injected manager.
    """

    @router.get("/hello")
    def read_hello() -> dict[str, str]:
        """Return a simple greeting with HTTP 200 when the API is up."""
        return asdict(hello_manager.get_hello())

    return router
