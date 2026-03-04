from __future__ import annotations

import argparse
import secrets


def generate_auth_key(prefix: str = "ak_") -> str:
    return f"{prefix}{secrets.token_urlsafe(32)}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate auth key for autonlp API")
    parser.add_argument("--prefix", default="ak_", help="Key prefix")
    parser.add_argument(
        "--print-export",
        action="store_true",
        help="Print shell export command for AUTONLP_API_KEYS",
    )
    args = parser.parse_args()

    key = generate_auth_key(prefix=args.prefix)
    if args.print_export:
        print(f'export AUTONLP_API_KEYS="{key}"')
        return
    print(key)


if __name__ == "__main__":
    main()
