"""Refresh complexity values for all games from BGG."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.core import db
from src.core.bgg import BGGClient
from src.core.models import Game


async def refresh_complexity():
    """Fetch and update complexity for all games with complexity = 0."""
    bgg = BGGClient()

    async with db.AsyncSessionLocal() as session:
        # Get all games with no complexity
        result = await session.execute(
            select(Game).where(Game.complexity <= 0, Game.id > 0)  # Only real BGG games (positive IDs)
        )
        games = result.scalars().all()

        print(f"Found {len(games)} games with missing complexity")

        updated = 0
        for i, game in enumerate(games):
            print(f"[{i+1}/{len(games)}] Fetching {game.name} (ID: {game.id})...")

            try:
                details = await bgg.get_game_details(game.id)
                if details and details.complexity and details.complexity > 0:
                    game.complexity = details.complexity
                    updated += 1
                    print(f"  → Updated to {details.complexity:.2f}")
                else:
                    print("  → No complexity data available")

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"  → Error: {e}")
                continue

        await session.commit()
        print("\n=== DONE ===")
        print(f"Updated {updated}/{len(games)} games with complexity values")

if __name__ == "__main__":
    asyncio.run(refresh_complexity())
