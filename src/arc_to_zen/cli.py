from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .arc import extract
from .engine import delete_password_transfer, migrate, prepare_passwords, restore
from .models import BridgeError, Options
from .paths import defaults


def main(argv: list[str] | None = None) -> int:
    default_arc, _, runtime = defaults()
    parser = argparse.ArgumentParser(description="arc_to_zen — local, verified migration")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Read-only, count-only source scan; never prints URLs or login values")
    scan.add_argument("--arc", type=Path, default=default_arc)
    transfer = sub.add_parser("migrate", help="Back up, stage, verify, and commit")
    transfer.add_argument("--arc", type=Path, default=default_arc)
    transfer.add_argument("--zen", type=Path, required=True)
    transfer.add_argument("--output", type=Path, default=runtime)
    transfer.add_argument(
        "--replace",
        action="store_true",
        help="Replace selected profile after full backup; default creates a new profile",
    )
    transfer.add_argument("--yes", action="store_true", help="Acknowledge the selected profile operation")
    transfer.add_argument(
        "--cookies", action="store_true", help="Request Keychain approval and import compatible cookies"
    )
    for name in ("history", "bookmarks", "forms", "favicons"):
        transfer.add_argument("--no-" + name, action="store_true")
    recovery = sub.add_parser(
        "restore", help="Restore a verified pre-change Zen backup; retain the replaced profile"
    )
    recovery.add_argument("run", type=Path)
    recovery.add_argument("--yes", action="store_true")
    passwords = sub.add_parser(
        "prepare-passwords", help="Explicitly decrypt into a private temporary CSV for Zen's native importer"
    )
    passwords.add_argument("run", type=Path)
    passwords.add_argument("--yes", action="store_true", help="Acknowledge creation of a plaintext CSV")
    cleanup = sub.add_parser(
        "delete-password-csv", help="Remove the known temporary password CSV after native import"
    )
    cleanup.add_argument("run", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            print(json.dumps(extract(args.arc).summary(), indent=2))
        elif args.command == "migrate":
            if not args.yes:
                parser.error(
                    "Review a scan first, then pass --yes. The default creates a separate Zen profile."
                )
            options = Options(
                not args.no_history,
                not args.no_bookmarks,
                not args.no_forms,
                not args.no_favicons,
                args.cookies,
                args.replace,
            )
            result = migrate(
                args.arc, args.zen, args.output, options, lambda message: print(message, file=sys.stderr)
            )
            print(
                json.dumps(
                    {"profile": str(result.profile), "run": str(result.run), "report": result.report},
                    indent=2,
                )
            )
        elif args.command == "restore":
            if not args.yes:
                parser.error(
                    "Pass --yes to restore the backed-up profile. The current profile will be retained separately."
                )
            print(restore(args.run))
        elif args.command == "prepare-passwords":
            if not args.yes:
                parser.error(
                    "Pass --yes to create a private plaintext CSV. Delete it after importing in Zen."
                )
            path, summary = prepare_passwords(args.run)
            print(
                json.dumps(
                    {
                        "file": str(path),
                        "summary": summary,
                        "next": "Open Zen → Settings → Import Data → Passwords from CSV. Then run delete-password-csv.",
                    },
                    indent=2,
                )
            )
        else:
            delete_password_transfer(args.run)
            print("Known temporary CSV removed, if present.")
    except BridgeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except Exception:
        print(
            "The operation stopped on an unsupported file or database. No browser content was printed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
