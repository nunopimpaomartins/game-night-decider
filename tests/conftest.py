import pytest
import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.core import db
from src.core.models import Base

# Configure logging for tests
logging.basicConfig(level=logging.INFO)

@pytest.fixture(scope="function", autouse=True)
async def setup_test_db():
    """
    Override the production DB engine with an in-memory SQLite engine for tests.
    This ensures tests are isolated and don't affect the file-based DB.
    """
    # Create in-memory engine
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Patch the global engine and sessionmaker in src.core.db
    # Since handlers.py imports 'db' and calls 'db.AsyncSessionLocal()', this works!
    original_engine = db.engine
    original_sessionmaker = db.AsyncSessionLocal
    
    db.engine = test_engine
    db.AsyncSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    # Create Tables
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    yield
    
    # Teardown
    await db.engine.dispose()
    
    # Restore (optional, but good practice if tests shared process)
    db.engine = original_engine
    db.AsyncSessionLocal = original_sessionmaker
