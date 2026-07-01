#!/usr/bin/env python3
"""CLI entrypoint for the daily morning ingestion batch."""

from app.core.dependencies import build_ingestion_manager


def main() -> None:
    """Run the full ingestion pipeline once."""
    result = build_ingestion_manager().run_full_pipeline()
    print(result)


if __name__ == "__main__":
    main()
