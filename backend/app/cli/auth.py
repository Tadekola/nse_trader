"""
CLI for API key management.

Usage:
  python -m app.cli.auth create-key --name "my-laptop"
  python -m app.cli.auth list-keys
  python -m app.cli.auth revoke-key --key-id 3
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.middleware.auth import generate_key, hash_key
from app.db.models import ApiKey
from app.db.engine import get_session_factory


async def create_key(name: str) -> None:
    """Create a new API key and print the plain-text value (shown once)."""
    plain = generate_key()
    hashed = hash_key(plain)

    factory = get_session_factory()
    async with factory() as session:
        db_key = ApiKey(key_hash=hashed, name=name, is_active=True)
        session.add(db_key)
        await session.commit()
        await session.refresh(db_key)

    print("=" * 60)
    print(f"  API Key created (id={db_key.id}, name={name!r})")
    print(f"  Key: {plain}")
    print("  *** Save this key now — it cannot be retrieved later ***")
    print("=" * 60)


async def list_keys() -> None:
    """List all API keys (hash prefix only)."""
    from sqlalchemy import select

    factory = get_session_factory()
    async with factory() as session:
        rows = (await session.execute(select(ApiKey))).scalars().all()

    if not rows:
        print("No API keys found.")
        return

    print(f"{'ID':<5} {'Name':<25} {'Active':<8} {'Hash prefix':<18} {'Last used'}")
    print("-" * 80)
    for k in rows:
        last = k.last_used_at.isoformat() if k.last_used_at else "never"
        print(f"{k.id:<5} {k.name:<25} {str(k.is_active):<8} {k.key_hash[:12]}... {last}")


async def revoke_key(key_id: int) -> None:
    """Deactivate an API key."""
    from sqlalchemy import update

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            update(ApiKey).where(ApiKey.id == key_id).values(is_active=False)
        )
        await session.commit()

    if result.rowcount:
        print(f"API key {key_id} revoked.")
    else:
        print(f"No key found with id={key_id}.")


def main():
    parser = argparse.ArgumentParser(description="API key management")
    sub = parser.add_subparsers(dest="command")

    create = sub.add_parser("create-key", help="Create a new API key")
    create.add_argument("--name", required=True, help="Human label for the key")

    sub.add_parser("list-keys", help="List all API keys")

    revoke = sub.add_parser("revoke-key", help="Revoke an API key")
    revoke.add_argument("--key-id", type=int, required=True, help="Key ID to revoke")

    args = parser.parse_args()

    if args.command == "create-key":
        asyncio.run(create_key(args.name))
    elif args.command == "list-keys":
        asyncio.run(list_keys())
    elif args.command == "revoke-key":
        asyncio.run(revoke_key(args.key_id))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
