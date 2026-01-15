
import asyncio
import os
import sys

sys.path.append(os.getcwd())

from sqlalchemy import text

from src.core.db import engine


async def verify_schema():
    async with engine.connect() as conn:
        result = await conn.execute(text("PRAGMA table_info(sessions)"))
        columns = result.fetchall()
        # columns is list of (cid, name, type, notnull, dflt_value, pk)
        found = False
        for col in columns:
            if col[1] == 'settings_weighted':
                print(f"✅ Found column: {col[1]} ({col[2]})")
                found = True
                break

        if not found:
            print("❌ Column 'settings_weighted' NOT found!")
            exit(1)

if __name__ == "__main__":
    asyncio.run(verify_schema())
