import asyncio
import logging
import os
import sys

# Add project root to sys.path
sys.path.append(os.getcwd())

from sqlalchemy import text

from src.core.db import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate():
    async with engine.begin() as conn:
        try:
            logger.info("Attempting to add settings_weighted column to sessions table...")
            # SQLite syntax to add column
            await conn.execute(text("ALTER TABLE sessions ADD COLUMN settings_weighted BOOLEAN DEFAULT 0"))
            logger.info("Successfully added settings_weighted column.")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                logger.info("Column settings_weighted already exists.")
            else:
                logger.error(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
