from __future__ import annotations

import argparse
import os


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    reload_enabled = bool(args.reload)
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=reload_enabled,
        workers=args.workers,
        log_level=args.log_level,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="senteniel",
        description="Senteniel control-plane runtime CLI.",
    )
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the FastAPI/GraphQL gateway.")
    serve.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    serve.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    serve.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "info"))
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload (development only).",
    )
    serve.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of uvicorn workers. Leave unset for single-process mode.",
    )
    serve.set_defaults(func=_serve)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
