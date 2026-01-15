"""Check complexity values in database."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.core import db
from src.core.models import Game


async def check():
    async with db.AsyncSessionLocal() as session:
        result = await session.execute(select(Game).limit(30))
        games = result.scalars().all()

        rated = [g for g in games if g.complexity and g.complexity > 0]
        unrated = [g for g in games if not g.complexity or g.complexity <= 0]

        print("\n=== DATABASE COMPLEXITY CHECK ===")
        print(f"Total games checked: {len(games)}")
        print(f"Rated (complexity > 0): {len(rated)}")
        print(f"Unrated (complexity = 0): {len(unrated)}")

        print("\n=== RATED GAMES ===")
        for g in rated[:10]:
            print(f"  {g.name}: {g.complexity:.2f}")

        print("\n=== UNRATED GAMES ===")
        for g in unrated[:10]:
            print(f"  {g.name}: {g.complexity}")

if __name__ == "__main__":
    asyncio.run(check())
