"""Builds the hello-world payload the frontend smoke-tests against."""

from dataclasses import dataclass


@dataclass(frozen=True)
class HelloResponse:
    """Immutable hello payload returned by /api/hello."""

    message: str


class HelloManager:
    """
    Knows how to say hello.

    Casual: returns the string the React app should display on a 200.

    Keeps the greeting in one place so routes stay thin and we can swap the
    payload shape later (i18n, versioning, etc.) without touching HTTP wiring.
    """

    def get_hello(self) -> HelloResponse:
        """Return the canonical hello-world message."""
        return HelloResponse(message="hello world")
