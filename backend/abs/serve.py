"""
ABS backend IPC entry point.

Launched by the VS Code extension as a child process::

    abs-backend abs-serve --deals-root <path>     (frozen executable)
    python -m backend.abs.serve --deals-root <path>   (development)

It runs the stateless :class:`IPCServer` over stdin/stdout. All diagnostics go
to stderr so stdout stays a clean JSON-lines channel.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="abs-serve", description="ABS Waterfall backend IPC server")
    parser.add_argument("--deals-root", required=True, help="Root folder containing deal folders")
    args = parser.parse_args(argv)

    from backend.abs.services.ipc_server import run_stdio

    try:
        asyncio.run(run_stdio(args.deals_root))
    except KeyboardInterrupt:  # pragma: no cover
        return 0
    except Exception as exc:  # noqa: BLE001 — top-level guard
        print(f"[abs-serve] fatal: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
