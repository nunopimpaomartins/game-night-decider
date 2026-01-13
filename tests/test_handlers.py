"""
Comprehensive test suite for Game Night Decider bot.

Coverage targets:
- All handler functions
- Edge cases and error paths
- User flows and interactions
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, CallbackQuery
from telegram.ext import ContextTypes
from sqlalchemy import select

from src.bot.handlers import (
    start, set_bgg, start_night, join_lobby_callback, leave_lobby_callback, create_poll,
    mark_played, exclude_game, add_game, test_mode as handler_test_mode,
    add_guest, guest_game, help_command
)
from src.core.models import User, Session, SessionPlayer, Game, Collection
from src.core import db


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_update():
    """Create a mock Telegram Update object."""
    update = MagicMock(spec=Update)
    update.effective_chat.id = 12345
    update.effective_user.id = 111
    update.effective_user.first_name = "TestUser"
    update.message = MagicMock(spec=Message)
    update.message.reply_text = AsyncMock()
    update.callback_query = MagicMock(spec=CallbackQuery)
    update.callback_query.message.chat.id = 12345
    update.callback_query.from_user.id = 111
    update.callback_query.from_user.first_name = "TestUser"
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    """Create a mock Telegram Context object."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot.send_message = AsyncMock()
    context.bot.send_poll = AsyncMock()
    context.args = []
    return context


# ============================================================================
# /start command tests
# ============================================================================

@pytest.mark.asyncio
async def test_start_command(mock_update, mock_context):
    """Test /start shows welcome message."""
    # Patch os.path.exists to ensure we verify the text fallback path
    # 'os' is imported inside the function, so we must patch 'os.path.exists' directly
    with patch("os.path.exists", return_value=False):
        await start(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once()
    # Handle reply_photo vs reply_text?
    # The handler checks os.path.exists. By default it likely returns False in tests unless mocked.
    # So we expect reply_text or reply_photo.
    # Let's check call args of whatever was called.
    
    # Actually, in the test environment, the file probably doesn't exist, so reply_text is called.
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "Welcome to Game Night Decider!" in call_args
    assert "Quick Start" in call_args
    assert "/setbgg" in call_args
    assert "/addgame" in call_args
    assert "/help" in call_args


@pytest.mark.asyncio
async def test_help_command(mock_update, mock_context):
    """Test /help shows command list."""
    await help_command(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_once()
    call_args = mock_update.message.reply_text.call_args[0][0]
    
    assert "Command List" in call_args
    assert "/setbgg" in call_args
    assert "/poll" in call_args
    assert "/addguest" in call_args


# ============================================================================
# /setbgg command tests
# ============================================================================

@pytest.mark.asyncio
async def test_setbgg_no_args(mock_update, mock_context):
    """Test /setbgg without username shows usage."""
    mock_context.args = []
    await set_bgg(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with("Usage: /setbgg <username>")


@pytest.mark.asyncio
async def test_setbgg_creates_user(mock_update, mock_context):
    """Test /setbgg creates user and updates name."""
    mock_context.args = ["testbgguser"]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.fetch_collection = AsyncMock(return_value=[])
        
        await set_bgg(mock_update, mock_context)
        
        async with db.AsyncSessionLocal() as session:
            user = await session.get(User, 111)
            assert user is not None
            assert user.bgg_username == "testbgguser"
            assert user.telegram_name == "TestUser"


@pytest.mark.asyncio
async def test_setbgg_bgg_fetch_fails(mock_update, mock_context):
    """Test /setbgg handles BGG API failure gracefully."""
    mock_context.args = ["invaliduser"]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.fetch_collection = AsyncMock(side_effect=Exception("API Error"))
        
        await set_bgg(mock_update, mock_context)
        
        # Should send two messages: initial feedback + error
        assert mock_update.message.reply_text.call_count == 2
        error_call = mock_update.message.reply_text.call_args_list[1][0][0]
        assert "temporarily unavailable" in error_call or "try again later" in error_call


@pytest.mark.asyncio
async def test_setbgg_resync_adds_new_games(mock_update, mock_context):
    """Test /setbgg re-sync adds newly added BGG games to collection."""
    mock_context.args = ["testuser"]
    
    # Setup: User already has some games
    async with db.AsyncSessionLocal() as session:
        user = User(telegram_id=111, telegram_name="TestUser", bgg_username="testuser")
        session.add(user)
        
        # Existing games
        g1 = Game(id=1, name="OldGame1", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        g2 = Game(id=2, name="OldGame2", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        session.add_all([g1, g2])
        await session.flush()
        
        # User already has these in collection
        c1 = Collection(user_id=111, game_id=1)
        c2 = Collection(user_id=111, game_id=2)
        session.add_all([c1, c2])
        await session.commit()
    
    # Mock BGG response with original + new games
    g3 = Game(id=3, name="NewGame", min_players=2, max_players=4, playing_time=60, complexity=2.5)
    mock_games = [
        Game(id=1, name="OldGame1", min_players=2, max_players=4, playing_time=60, complexity=2.0),
        Game(id=2, name="OldGame2", min_players=2, max_players=4, playing_time=60, complexity=2.0),
        g3
    ]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.fetch_collection = AsyncMock(return_value=mock_games)
        
        await set_bgg(mock_update, mock_context)
    
    # Verify new game was added to collection
    async with db.AsyncSessionLocal() as session:
        stmt = select(Collection).where(Collection.user_id == 111)
        collections = (await session.execute(stmt)).scalars().all()
        collection_ids = {c.game_id for c in collections}
        assert collection_ids == {1, 2, 3}
    
    # Verify feedback message mentions new game
    calls = [call[0][0] for call in mock_update.message.reply_text.call_args_list]
    success_msg = calls[-1]  # Last message should be success
    assert "3 games total" in success_msg
    assert "1 new" in success_msg


@pytest.mark.asyncio
async def test_setbgg_resync_removes_deleted_games(mock_update, mock_context):
    """Test /setbgg re-sync removes games no longer in BGG collection."""
    mock_context.args = ["testuser"]
    
    # Setup: User has 3 games
    async with db.AsyncSessionLocal() as session:
        user = User(telegram_id=111, telegram_name="TestUser", bgg_username="testuser")
        session.add(user)
        
        g1 = Game(id=1, name="Game1", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        g2 = Game(id=2, name="Game2", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        g3 = Game(id=3, name="Game3", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        session.add_all([g1, g2, g3])
        await session.flush()
        
        c1 = Collection(user_id=111, game_id=1)
        c2 = Collection(user_id=111, game_id=2)
        c3 = Collection(user_id=111, game_id=3)
        session.add_all([c1, c2, c3])
        await session.commit()
    
    # Mock BGG response with only games 1 and 2 (game 3 removed)
    mock_games = [
        Game(id=1, name="Game1", min_players=2, max_players=4, playing_time=60, complexity=2.0),
        Game(id=2, name="Game2", min_players=2, max_players=4, playing_time=60, complexity=2.0)
    ]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.fetch_collection = AsyncMock(return_value=mock_games)
        
        await set_bgg(mock_update, mock_context)
    
    # Verify game 3 was removed from collection
    async with db.AsyncSessionLocal() as session:
        stmt = select(Collection).where(Collection.user_id == 111)
        collections = (await session.execute(stmt)).scalars().all()
        collection_ids = {c.game_id for c in collections}
        assert collection_ids == {1, 2}
    
    # Verify feedback message mentions removed game
    calls = [call[0][0] for call in mock_update.message.reply_text.call_args_list]
    success_msg = calls[-1]
    assert "2 games total" in success_msg
    assert "1 removed" in success_msg


@pytest.mark.asyncio
async def test_setbgg_resync_no_changes(mock_update, mock_context):
    """Test /setbgg re-sync with no changes shows appropriate message."""
    mock_context.args = ["testuser"]
    
    # Setup: User has games
    async with db.AsyncSessionLocal() as session:
        user = User(telegram_id=111, telegram_name="TestUser", bgg_username="testuser")
        session.add(user)
        
        g1 = Game(id=1, name="Game1", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        g2 = Game(id=2, name="Game2", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        session.add_all([g1, g2])
        await session.flush()
        
        c1 = Collection(user_id=111, game_id=1)
        c2 = Collection(user_id=111, game_id=2)
        session.add_all([c1, c2])
        await session.commit()
    
    # Mock BGG response with same games
    mock_games = [
        Game(id=1, name="Game1", min_players=2, max_players=4, playing_time=60, complexity=2.0),
        Game(id=2, name="Game2", min_players=2, max_players=4, playing_time=60, complexity=2.0)
    ]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.fetch_collection = AsyncMock(return_value=mock_games)
        
        await set_bgg(mock_update, mock_context)
    
    # Verify feedback message shows no changes
    calls = [call[0][0] for call in mock_update.message.reply_text.call_args_list]
    success_msg = calls[-1]
    assert "2 games total" in success_msg
    assert "no changes" in success_msg


@pytest.mark.asyncio
async def test_setbgg_initial_sync_feedback(mock_update, mock_context):
    """Test /setbgg initial sync shows correct feedback."""
    mock_context.args = ["newuser"]
    
    # Mock BGG response
    mock_games = [
        Game(id=1, name="Game1", min_players=2, max_players=4, playing_time=60, complexity=2.0),
        Game(id=2, name="Game2", min_players=2, max_players=4, playing_time=60, complexity=2.0),
        Game(id=3, name="Game3", min_players=2, max_players=4, playing_time=60, complexity=2.0)
    ]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.fetch_collection = AsyncMock(return_value=mock_games)
        
        await set_bgg(mock_update, mock_context)
    
    # Verify feedback messages
    calls = [call[0][0] for call in mock_update.message.reply_text.call_args_list]
    assert len(calls) == 2
    assert "Fetching collection..." in calls[0]
    success_msg = calls[1]
    assert "3 games total" in success_msg
    assert "3 new" in success_msg


# ============================================================================
# /addgame command tests
# ============================================================================

@pytest.mark.asyncio
async def test_addgame_no_args(mock_update, mock_context):
    """Test /addgame without arguments shows usage."""
    mock_context.args = []
    await add_game(mock_update, mock_context)
    
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "Usage:" in call_args
    assert "Search BGG" in call_args


@pytest.mark.asyncio
async def test_addgame_searches_bgg_when_name_only(mock_update, mock_context):
    """Test /addgame with only name searches BGG."""
    mock_context.args = ["Catan"]
    
    mock_game = Game(
        id=13, name="Catan", min_players=3, max_players=4,
        playing_time=60, complexity=2.32, thumbnail="http://example.com/catan.jpg"
    )
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.search_games = AsyncMock(return_value=[{"id": 13, "name": "Catan", "year_published": "1995"}])
        mock_client.get_game_details = AsyncMock(return_value=mock_game)
        
        await add_game(mock_update, mock_context)
        
        mock_client.search_games.assert_called_once_with("Catan", limit=10)
        mock_client.get_game_details.assert_called_once_with(13)
    
    # Verify game was added
    async with db.AsyncSessionLocal() as session:
        game = await session.get(Game, 13)
        assert game is not None
        assert game.name == "Catan"
        assert game.min_players == 3
        assert game.max_players == 4


@pytest.mark.asyncio
async def test_addgame_multiword_name_searches_bgg(mock_update, mock_context):
    """Test /addgame with multi-word name searches BGG."""
    mock_context.args = ["Ticket", "to", "Ride"]
    
    mock_game = Game(
        id=9209, name="Ticket to Ride", min_players=2, max_players=5,
        playing_time=60, complexity=1.85
    )
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.search_games = AsyncMock(return_value=[{"id": 9209, "name": "Ticket to Ride"}])
        mock_client.get_game_details = AsyncMock(return_value=mock_game)
        
        await add_game(mock_update, mock_context)
        
        # Should join args into search query
        mock_client.search_games.assert_called_once_with("Ticket to Ride", limit=10)


@pytest.mark.asyncio
async def test_addgame_bgg_not_found(mock_update, mock_context):
    """Test /addgame when BGG search returns no results."""
    mock_context.args = ["NonexistentGame123"]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.search_games = AsyncMock(return_value=[])
        
        await add_game(mock_update, mock_context)
    
    # Should suggest manual entry
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "Could not find" in call_args
    assert "manual entry" in call_args.lower()


@pytest.mark.asyncio
async def test_addgame_bgg_error_fallback(mock_update, mock_context):
    """Test /addgame handles BGG API error gracefully."""
    mock_context.args = ["Catan"]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        mock_client.search_games = AsyncMock(side_effect=Exception("API Error"))
        
        await add_game(mock_update, mock_context)
    
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "Error searching BGG" in call_args


@pytest.mark.asyncio
async def test_addgame_manual_with_all_params(mock_update, mock_context):
    """Test /addgame with all parameters uses manual mode (bypasses BGG)."""
    mock_context.args = ["CustomGame", "3", "4", "2.3"]
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        await add_game(mock_update, mock_context)
        
        # Should NOT call BGG (manual mode)
        MockBGG.assert_not_called()
    
    async with db.AsyncSessionLocal() as session:
        stmt = select(Game).where(Game.name == "CustomGame")
        game = (await session.execute(stmt)).scalar_one_or_none()
        assert game is not None
        assert game.min_players == 3
        assert game.max_players == 4
        assert game.complexity == 2.3
        assert game.id < 0  # Negative ID for manual games


@pytest.mark.asyncio
async def test_addgame_creates_user(mock_update, mock_context):
    """Test /addgame creates user if doesn't exist."""
    mock_update.effective_user.id = 999  # New user
    mock_context.args = ["TestGame", "2", "6", "2.5"]  # Manual mode
    
    await add_game(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        user = await session.get(User, 999)
        assert user is not None
        assert user.telegram_name == "TestUser"


# ============================================================================
# /gamenight command tests
# ============================================================================

@pytest.mark.asyncio
async def test_startnight_creates_session(mock_update, mock_context):
    """Test /gamenight creates a new session."""
    await start_night(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        sess = await session.get(Session, 12345)
        assert sess is not None
        assert sess.is_active is True


@pytest.mark.asyncio
async def test_startnight_shows_confirmation_when_players_exist(mock_update, mock_context):
    """Test /gamenight shows confirmation when session already has players."""
    # Setup: Create session with a player
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        user = User(telegram_id=111, telegram_name="Test")
        session.add(user)
        await session.flush()
        player = SessionPlayer(session_id=12345, user_id=111)
        session.add(player)
        await session.commit()
    
    # Start new night - should show confirmation instead of clearing
    await start_night(mock_update, mock_context)
    
    # Verify confirmation message shown with Resume/Restart options
    call_args = mock_update.message.reply_text.call_args
    message_text = call_args.kwargs.get('text') or call_args.args[0]
    assert "Already Running" in message_text
    assert "Test" in message_text  # Should show current player


@pytest.mark.asyncio
async def test_startnight_clears_when_no_players(mock_update, mock_context):
    """Test /gamenight starts fresh when session exists but has no players."""
    # Setup: Create session without players
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        await session.commit()
    
    # Start new night - should start fresh since no players
    await start_night(mock_update, mock_context)
    
    # Verify standard lobby message shown
    call_args = mock_update.message.reply_text.call_args
    message_text = call_args.kwargs.get('text') or call_args.args[0]
    assert "Who is in?" in message_text


# ============================================================================
# join_lobby_callback tests
# ============================================================================

@pytest.mark.asyncio
async def test_join_lobby_creates_user(mock_update, mock_context):
    """Test joining lobby creates user if doesn't exist."""
    # Setup session first
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        await session.commit()
    
    await join_lobby_callback(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        user = await session.get(User, 111)
        assert user is not None
        stmt = select(SessionPlayer).where(
            SessionPlayer.session_id == 12345,
            SessionPlayer.user_id == 111
        )
        player = (await session.execute(stmt)).scalar_one_or_none()
        assert player is not None


@pytest.mark.asyncio
async def test_join_lobby_updates_telegram_name(mock_update, mock_context):
    """Test joining lobby updates user's telegram name."""
    # Setup: create user with old name
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        user = User(telegram_id=111, telegram_name="OldName")
        session.add(user)
        await session.commit()
    
    mock_update.callback_query.from_user.first_name = "NewName"
    await join_lobby_callback(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        user = await session.get(User, 111)
        assert user.telegram_name == "NewName"


@pytest.mark.asyncio
async def test_join_lobby_prevents_double_join(mock_update, mock_context):
    """Test user can't join lobby twice."""
    # Setup
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        user = User(telegram_id=111, telegram_name="Test")
        session.add(user)
        await session.commit()
    
    # Join twice
    await join_lobby_callback(mock_update, mock_context)
    await join_lobby_callback(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        stmt = select(SessionPlayer).where(
            SessionPlayer.session_id == 12345,
            SessionPlayer.user_id == 111
        )
        players = (await session.execute(stmt)).scalars().all()
        assert len(players) == 1  # Only one entry


@pytest.mark.asyncio
async def test_join_lobby_sends_notification(mock_update, mock_context):
    """Test joining lobby sends notification to chat."""
    chat_id = 12345
    user_id = 999
    
    # Setup session
    async with db.AsyncSessionLocal() as session:
        session.add(Session(chat_id=chat_id, is_active=True))
        await session.commit()
    
    mock_update.callback_query.message.chat.id = chat_id
    mock_update.callback_query.from_user.id = user_id
    mock_update.callback_query.from_user.first_name = "NewUser"
    
    await join_lobby_callback(mock_update, mock_context)
    
    # Verify notification sent
    mock_context.bot.send_message.assert_called_once()
    # Check args (kwargs or positional)
    # Handler uses keyword arg 'text' or positional?
    # await context.bot.send_message(chat_id=chat_id, text=...)
    call_args = mock_context.bot.send_message.call_args
    
    # Handle both positional and keyword possibilities for robustness
    if 'text' in call_args.kwargs:
        text = call_args.kwargs['text']
    elif len(call_args.args) >= 2:
        text = call_args.args[1]
    else:
        text = ""
        
    assert "joined the game night" in text
    assert "NewUser" in text


# ============================================================================
# leave_lobby_callback tests
# ============================================================================

@pytest.mark.asyncio
async def test_leave_lobby_removes_player(mock_update, mock_context):
    """Test leaving lobby removes player from session."""
    # Setup: Create session with a player
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        user = User(telegram_id=111, telegram_name="TestUser")
        session.add(user)
        await session.flush()
        player = SessionPlayer(session_id=12345, user_id=111)
        session.add(player)
        await session.commit()
    
    await leave_lobby_callback(mock_update, mock_context)
    
    # Verify player removed
    async with db.AsyncSessionLocal() as session:
        stmt = select(SessionPlayer).where(
            SessionPlayer.session_id == 12345,
            SessionPlayer.user_id == 111
        )
        player = (await session.execute(stmt)).scalar_one_or_none()
        assert player is None


@pytest.mark.asyncio
async def test_leave_lobby_not_in_session(mock_update, mock_context):
    """Test leaving when not in session shows error."""
    # Setup: Create session but no player
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        await session.commit()
    
    await leave_lobby_callback(mock_update, mock_context)
    
    # Verify error message sent
    mock_context.bot.send_message.assert_called_once()
    call_kwargs = mock_context.bot.send_message.call_args.kwargs
    assert "not in this game night" in call_kwargs['text']


@pytest.mark.asyncio
async def test_leave_lobby_guest_cleanup(mock_update, mock_context):
    """Test leaving as guest cleans up collection and user."""
    # Setup: Create guest user with games
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        
        # Create guest user
        guest = User(telegram_id=111, telegram_name="GuestUser", is_guest=True, added_by_user_id=999)
        session.add(guest)
        await session.flush()
        
        # Add game to guest's collection
        game = Game(id=-1, name="GuestGame", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        session.add(game)
        await session.flush()
        
        col = Collection(user_id=111, game_id=-1)
        session.add(col)
        
        # Add guest to session
        player = SessionPlayer(session_id=12345, user_id=111)
        session.add(player)
        await session.commit()
    
    await leave_lobby_callback(mock_update, mock_context)
    
    # Verify guest and collection removed
    async with db.AsyncSessionLocal() as session:
        user = await session.get(User, 111)
        assert user is None
        
        stmt = select(Collection).where(Collection.user_id == 111)
        collections = (await session.execute(stmt)).scalars().all()
        assert len(collections) == 0


@pytest.mark.asyncio
async def test_leave_lobby_updates_message(mock_update, mock_context):
    """Test leaving updates lobby message."""
    # Setup: Create session with two players
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        
        u1 = User(telegram_id=111, telegram_name="User1")
        u2 = User(telegram_id=222, telegram_name="User2")
        session.add_all([u1, u2])
        await session.flush()
        
        sp1 = SessionPlayer(session_id=12345, user_id=111)
        sp2 = SessionPlayer(session_id=12345, user_id=222)
        session.add_all([sp1, sp2])
        await session.commit()
    
    await leave_lobby_callback(mock_update, mock_context)
    
    # Verify message was updated
    mock_update.callback_query.edit_message_text.assert_called_once()
    call_args = mock_update.callback_query.edit_message_text.call_args[0][0]
    
    # Should show remaining player
    assert "User2" in call_args
    # Original user should not be listed
    assert "User1" not in call_args or "Joined (1)" in call_args


@pytest.mark.asyncio
async def test_leave_lobby_last_player_updates_message(mock_update, mock_context):
    """Test leaving as last player shows empty lobby message."""
    # Setup: Create session with one player
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        
        user = User(telegram_id=111, telegram_name="TestUser")
        session.add(user)
        await session.flush()
        
        player = SessionPlayer(session_id=12345, user_id=111)
        session.add(player)
        await session.commit()
    
    await leave_lobby_callback(mock_update, mock_context)
    
    # Verify message shows empty lobby
    mock_update.callback_query.edit_message_text.assert_called_once()
    call_args = mock_update.callback_query.edit_message_text.call_args[0][0]
    assert "Who is in?" in call_args


@pytest.mark.asyncio
async def test_leave_lobby_sends_notification(mock_update, mock_context):
    """Test leaving sends notification to chat."""
    # Setup: Create session with player
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        
        user = User(telegram_id=111, telegram_name="TestUser")
        session.add(user)
        await session.flush()
        
        player = SessionPlayer(session_id=12345, user_id=111)
        session.add(player)
        await session.commit()
    
    await leave_lobby_callback(mock_update, mock_context)
    
    # Verify leave notification sent
    calls = mock_context.bot.send_message.call_args_list
    leave_call = calls[0]  # First call should be the leave notification
    
    if 'text' in leave_call.kwargs:
        text = leave_call.kwargs['text']
    elif len(leave_call.args) >= 2:
        text = leave_call.args[1]
    else:
        text = ""
    
    assert "has left the game night" in text
    assert "TestUser" in text



# ============================================================================
# /poll command tests
# ============================================================================

@pytest.mark.asyncio
async def test_poll_no_players(mock_update, mock_context):
    """Test /poll with no players shows error."""
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        await session.commit()
    
    await create_poll(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with(
        "No players in lobby! Use /gamenight first."
    )


@pytest.mark.asyncio
async def test_poll_only_one_player(mock_update, mock_context):
    """Test /poll with only one player shows error."""
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        user = User(telegram_id=111, telegram_name="Test")
        session.add(user)
        await session.flush()
        player = SessionPlayer(session_id=12345, user_id=111)
        session.add(player)
        await session.commit()
    
    await create_poll(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with(
        "Need at least 2 players to start a poll!"
    )


@pytest.mark.asyncio
async def test_poll_no_games_in_collections(mock_update, mock_context):
    """Test /poll with players who have no games in their collections."""
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        # Two users with no games
        u1 = User(telegram_id=111, telegram_name="User1")
        u2 = User(telegram_id=222, telegram_name="User2")
        session.add_all([u1, u2])
        await session.flush()
        
        # No games added to collections
        
        sp1 = SessionPlayer(session_id=12345, user_id=111)
        sp2 = SessionPlayer(session_id=12345, user_id=222)
        session.add_all([sp1, sp2])
        await session.commit()
    
    await create_poll(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with(
        "No games in any player's collection! "
        "Use /setbgg or /addgame to add games first."
    )


@pytest.mark.asyncio
async def test_poll_no_matching_games(mock_update, mock_context):
    """Test /poll with games that don't support the player count."""
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        # Two users
        u1 = User(telegram_id=111, telegram_name="User1")
        u2 = User(telegram_id=222, telegram_name="User2")
        session.add_all([u1, u2])
        await session.flush()
        
        # Games that require 3-4 players (won't match 2 players)
        g1 = Game(id=1, name="Game1", min_players=3, max_players=4, playing_time=60, complexity=2.0)
        g2 = Game(id=2, name="Game2", min_players=3, max_players=4, playing_time=60, complexity=2.0)
        session.add_all([g1, g2])
        await session.flush()
        
        # Both users have these games but they don't support 2 players
        c1 = Collection(user_id=111, game_id=1)
        c2 = Collection(user_id=222, game_id=2)
        session.add_all([c1, c2])
        
        sp1 = SessionPlayer(session_id=12345, user_id=111)
        sp2 = SessionPlayer(session_id=12345, user_id=222)
        session.add_all([sp1, sp2])
        await session.commit()
    
    await create_poll(mock_update, mock_context)
    
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "No games found matching 2 players" in call_args


@pytest.mark.asyncio
async def test_poll_with_valid_games(mock_update, mock_context):
    """Test /poll creates poll with valid intersecting games."""
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        
        u1 = User(telegram_id=111, telegram_name="User1")
        u2 = User(telegram_id=222, telegram_name="User2")
        session.add_all([u1, u2])
        await session.flush()
        
        game = Game(id=1, name="SharedGame", min_players=2, max_players=4, playing_time=60, complexity=2.5)
        session.add(game)
        await session.flush()
        
        # Both users own the same game
        c1 = Collection(user_id=111, game_id=1)
        c2 = Collection(user_id=222, game_id=1)
        session.add_all([c1, c2])
        
        sp1 = SessionPlayer(session_id=12345, user_id=111)
        sp2 = SessionPlayer(session_id=12345, user_id=222)
        session.add_all([sp1, sp2])
        await session.commit()
    
    await create_poll(mock_update, mock_context)
    
    mock_context.bot.send_poll.assert_called_once()
    call_kwargs = mock_context.bot.send_poll.call_args[1]
    assert "SharedGame" in call_kwargs['options'][0]


@pytest.mark.asyncio
async def test_poll_excludes_excluded_games(mock_update, mock_context):
    """Test /poll respects is_excluded flag."""
    async with db.AsyncSessionLocal() as session:
        sess = Session(chat_id=12345, is_active=True)
        session.add(sess)
        
        u1 = User(telegram_id=111, telegram_name="User1")
        u2 = User(telegram_id=222, telegram_name="User2")
        session.add_all([u1, u2])
        await session.flush()
        
        game = Game(id=1, name="ExcludedGame", min_players=2, max_players=4, playing_time=60, complexity=2.5)
        session.add(game)
        await session.flush()
        
        # Both users have excluded the game
        c1 = Collection(user_id=111, game_id=1, is_excluded=True)
        c2 = Collection(user_id=222, game_id=1, is_excluded=True)
        session.add_all([c1, c2])
        
        sp1 = SessionPlayer(session_id=12345, user_id=111)
        sp2 = SessionPlayer(session_id=12345, user_id=222)
        session.add_all([sp1, sp2])
        await session.commit()
    
    await create_poll(mock_update, mock_context)
    
    # Should not find any games (all excluded)
    mock_context.bot.send_poll.assert_not_called()


# ============================================================================
# /markplayed command tests
# ============================================================================

@pytest.mark.asyncio
async def test_markplayed_no_args(mock_update, mock_context):
    """Test /markplayed without args shows usage."""
    mock_context.args = []
    await mark_played(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with("Usage: /markplayed <game name>")


@pytest.mark.asyncio
async def test_markplayed_game_not_found(mock_update, mock_context):
    """Test /markplayed with nonexistent game."""
    mock_context.args = ["NonexistentGame"]
    await mark_played(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with("Game not found.")


@pytest.mark.asyncio
async def test_markplayed_multiple_matches(mock_update, mock_context):
    """Test /markplayed with ambiguous name."""
    async with db.AsyncSessionLocal() as session:
        g1 = Game(id=1, name="Catan", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        g2 = Game(id=2, name="Catan: Cities", min_players=2, max_players=4, playing_time=60, complexity=2.5)
        session.add_all([g1, g2])
        await session.commit()
    
    mock_context.args = ["Catan"]
    await mark_played(mock_update, mock_context)
    
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "Found multiple games" in call_args


# ============================================================================
# /exclude command tests
# ============================================================================

@pytest.mark.asyncio
async def test_exclude_no_args(mock_update, mock_context):
    """Test /exclude without args shows usage."""
    mock_context.args = []
    await exclude_game(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with("Usage: /exclude <game name>")


@pytest.mark.asyncio
async def test_exclude_toggles_state(mock_update, mock_context):
    """Test /exclude toggles exclusion state."""
    async with db.AsyncSessionLocal() as session:
        user = User(telegram_id=111, telegram_name="Test")
        session.add(user)
        game = Game(id=1, name="TestGame", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        session.add(game)
        await session.flush()
        col = Collection(user_id=111, game_id=1, is_excluded=False)
        session.add(col)
        await session.commit()
    
    mock_context.args = ["TestGame"]
    
    # First call: exclude
    await exclude_game(mock_update, mock_context)
    async with db.AsyncSessionLocal() as session:
        stmt = select(Collection).where(Collection.user_id == 111, Collection.game_id == 1)
        col = (await session.execute(stmt)).scalar_one()
        assert col.is_excluded is True
    
    # Second call: include
    await exclude_game(mock_update, mock_context)
    async with db.AsyncSessionLocal() as session:
        stmt = select(Collection).where(Collection.user_id == 111, Collection.game_id == 1)
        col = (await session.execute(stmt)).scalar_one()
        assert col.is_excluded is False


@pytest.mark.asyncio
async def test_exclude_not_owned(mock_update, mock_context):
    """Test /exclude on game not in collection."""
    async with db.AsyncSessionLocal() as session:
        user = User(telegram_id=111, telegram_name="Test")
        session.add(user)
        game = Game(id=1, name="OtherGame", min_players=2, max_players=4, playing_time=60, complexity=2.0)
        session.add(game)
        await session.commit()
    
    mock_context.args = ["OtherGame"]
    await exclude_game(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with("You don't own this game.")


# ============================================================================
# /testmode command tests
# ============================================================================

@pytest.mark.asyncio
async def test_testmode_creates_users_and_games(mock_update, mock_context):
    """Test /testmode creates fake users with test games (default 2 users)."""
    mock_context.args = []  # No args = default 2 users
    await handler_test_mode(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        # Check fake users created
        u1 = await session.get(User, 999001)
        u2 = await session.get(User, 999002)
        assert u1 is not None
        assert u2 is not None
        assert u1.telegram_name == "TestUser1"
        
        # Check test games created
        g = await session.get(Game, -1001)
        assert g is not None
        assert g.name == "Test Catan"
        
        # Check collections created
        stmt = select(Collection).where(Collection.user_id == 999001)
        cols = (await session.execute(stmt)).scalars().all()
        assert len(cols) == 4  # 4 test games


@pytest.mark.asyncio
async def test_testmode_adds_to_lobby(mock_update, mock_context):
    """Test /testmode adds fake users to current lobby (default 2 users)."""
    # Use unique chat_id for this test
    mock_update.effective_chat.id = 99999
    mock_context.args = []  # Default 2 users
    
    await handler_test_mode(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        stmt = select(SessionPlayer).where(SessionPlayer.session_id == 99999)
        players = (await session.execute(stmt)).scalars().all()
        assert len(players) == 3  # 2 fake users + calling user


@pytest.mark.asyncio
async def test_testmode_custom_player_count(mock_update, mock_context):
    """Test /testmode with custom player count."""
    mock_update.effective_chat.id = 88888
    mock_context.args = ["5"]  # 5 fake users
    
    await handler_test_mode(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        # Check 5 fake users created
        for i in range(1, 6):
            user = await session.get(User, 999000 + i)
            assert user is not None, f"TestUser{i} not created"
            assert user.telegram_name == f"TestUser{i}"
        
        # Check session has 6 players (5 fake + calling user)
        stmt = select(SessionPlayer).where(SessionPlayer.session_id == 88888)
        players = (await session.execute(stmt)).scalars().all()
        assert len(players) == 6


@pytest.mark.asyncio
async def test_testmode_clamps_player_count(mock_update, mock_context):
    """Test /testmode clamps player count to 1-10 range."""
    mock_update.effective_chat.id = 77777
    mock_context.args = ["20"]  # Should be clamped to 10
    
    await handler_test_mode(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        stmt = select(SessionPlayer).where(SessionPlayer.session_id == 77777)
        players = (await session.execute(stmt)).scalars().all()
        assert len(players) == 11  # 10 fake users + calling user


@pytest.mark.asyncio
async def test_testmode_run_twice_existing_users(mock_update, mock_context):
    """Test /testmode running a second time handles existing users correctly."""
    mock_update.effective_chat.id = 66666
    
    # Run once
    mock_context.args = []
    await handler_test_mode(mock_update, mock_context)
    
    # Run twice
    await handler_test_mode(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        # Verify users still exist and have collections
        u1 = await session.get(User, 999001)
        assert u1 is not None
        
        # Check collection (should have 4 items)
        stmt = select(Collection).where(Collection.user_id == 999001)
        cols = (await session.execute(stmt)).scalars().all()
        assert len(cols) == 4
        
        # Check session players
        stmt = select(SessionPlayer).where(SessionPlayer.session_id == 66666)
        players = (await session.execute(stmt)).scalars().all()
        assert len(players) == 3


# ============================================================================
# Guest Feature Tests
# ============================================================================

@pytest.mark.asyncio
async def test_addguest_no_args(mock_update, mock_context):
    """Test /addguest without name shows usage."""
    mock_context.args = []
    await add_guest(mock_update, mock_context)
    
    # Check that reply contains "Usage"
    mock_update.message.reply_text.assert_called_once()
    assert "Usage" in mock_update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_addguest_no_session(mock_update, mock_context):
    """Test /addguest without active session shows error."""
    # Ensure no session exists
    # (By default db is empty in test)
    
    # We need args
    mock_context.args = ["GuestName"]
    
    await add_guest(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with(
        "No active game night! Use /gamenight first."
    )


@pytest.mark.asyncio
async def test_addguest_success(mock_update, mock_context):
    """Test /addguest successfully adds a guest."""
    # Setup session
    async with db.AsyncSessionLocal() as session:
        session.add(Session(chat_id=12345, is_active=True))
        await session.commit()
    
    mock_context.args = ["John Doe"]
    mock_update.effective_user.id = 111  # Added by User 111
    
    await add_guest(mock_update, mock_context)
    
    # Verify response
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "Guest **John Doe** added!" in call_args
    
    # Verify DB
    async with db.AsyncSessionLocal() as session:
        # Check User created
        stmt = select(User).where(User.telegram_name == "John Doe", User.is_guest == True)
        guest = (await session.execute(stmt)).scalar_one_or_none()
        assert guest is not None
        assert guest.added_by_user_id == 111
        assert guest.telegram_id < 0  # Should be negative
        
        # Check added to session
        sp_stmt = select(SessionPlayer).where(
            SessionPlayer.session_id == 12345,
            SessionPlayer.user_id == guest.telegram_id
        )
        sp = (await session.execute(sp_stmt)).scalar_one_or_none()
        assert sp is not None


@pytest.mark.asyncio
async def test_guestgame_success(mock_update, mock_context):
    """Test /guestgame adds game to guest collection (single word name)."""
    # Setup session and guest
    async with db.AsyncSessionLocal() as session:
        session.add(Session(chat_id=12345, is_active=True))
        guest = User(telegram_id=-123, telegram_name="GuestJohn", is_guest=True)
        session.add(guest)
        session.add(SessionPlayer(session_id=12345, user_id=-123))
        await session.commit()
    
    # Args: GuestName GameName Min Max Complexity
    mock_context.args = ["GuestJohn", "Catan", "3", "4", "2.5"]
    
    await guest_game(mock_update, mock_context)
    
    mock_update.message.reply_text.assert_called_with(
        "Added 'Catan' to GuestJohn's collection!"
    )
    
    # Verify collection
    async with db.AsyncSessionLocal() as session:
        # Find game
        g_stmt = select(Game).where(Game.name == "Catan")
        game = (await session.execute(g_stmt)).scalar_one()
        
        # Check collection
        stmt = select(Collection).where(
            Collection.user_id == -123,
            Collection.game_id == game.id
        )
        col = (await session.execute(stmt)).scalar_one_or_none()
        assert col is not None


@pytest.mark.asyncio
async def test_addgame_uses_cache(mock_update, mock_context):
    """Test /addgame uses local cache if available."""
    mock_context.args = ["CachedGame"]
    
    # Pre-populate DB with the game
    async with db.AsyncSessionLocal() as session:
        game = Game(id=12345, name="CachedGame", min_players=1, max_players=4, playing_time=30, complexity=2.0)
        session.add(game)
        await session.commit()
    
    with patch("src.bot.handlers.BGGClient") as MockBGG:
        mock_client = MockBGG.return_value
        # Search returns the ID we have locally
        mock_client.search_games = AsyncMock(return_value=[{"id": 12345, "name": "CachedGame"}])
        # get_game_details should NOT be called
        mock_client.get_game_details = AsyncMock()
        
        await add_game(mock_update, mock_context)
        
        mock_client.search_games.assert_called_once()
        mock_client.get_game_details.assert_not_called()
    
    # Verify user collection updated
    async with db.AsyncSessionLocal() as session:
        stmt = select(Collection).where(
            Collection.user_id == 111,
            Collection.game_id == 12345
        )
        col = (await session.execute(stmt)).scalar_one_or_none()
        assert col is not None


@pytest.mark.asyncio
async def test_guestgame_uses_existing_game(mock_update, mock_context):
    """Test /guestgame links to existing game instead of creating manual entry."""
    # Setup session and guest
    async with db.AsyncSessionLocal() as session:
        session.add(Session(chat_id=12345, is_active=True))
        guest = User(telegram_id=-555, telegram_name="GuestUser", is_guest=True)
        session.add(guest)
        session.add(SessionPlayer(session_id=12345, user_id=-555))
        
        # Pre-populate exact match game (Real BGG ID)
        real_game = Game(id=999, name="RealGame", min_players=2, max_players=4, playing_time=60, complexity=3.0)
        session.add(real_game)
        await session.commit()
    
    mock_context.args = ["GuestUser", "RealGame"]
    
    await guest_game(mock_update, mock_context)
    
    async with db.AsyncSessionLocal() as session:
        # Check collection links to ID 999
        stmt = select(Collection).where(
            Collection.user_id == -555,
            Collection.game_id == 999
        )
        col = (await session.execute(stmt)).scalar_one_or_none()
        assert col is not None
        
        # Ensure no manual game was created (count games with name "RealGame")
        g_stmt = select(Game).where(Game.name == "RealGame")
        games = (await session.execute(g_stmt)).scalars().all()
        assert len(games) == 1
        assert games[0].id == 999


@pytest.mark.asyncio
async def test_guestgame_multiword_names(mock_update, mock_context):
    """Test /guestgame with multi-word guest name and game name."""
    # Setup session and guest
    async with db.AsyncSessionLocal() as session:
        session.add(Session(chat_id=12345, is_active=True))
        # Multi-word name
        guest = User(telegram_id=-456, telegram_name="John Doe", is_guest=True)
        session.add(guest)
        session.add(SessionPlayer(session_id=12345, user_id=-456))
        await session.commit()
    
    # Args: John Doe Ticket to Ride 2 5
    # Logic should parse numeric args from end: 2, 5 -> min, max.
    # Remainder: "John Doe Ticket to Ride"
    # Matches guest "John Doe".
    # Remaining: "Ticket to Ride"
    
    mock_context.args = ["John", "Doe", "Ticket", "to", "Ride", "2", "5"]
    
    await guest_game(mock_update, mock_context)
    
    call_args = mock_update.message.reply_text.call_args[0][0]
    assert "Added 'Ticket to Ride' to John Doe's collection!" in call_args
    
    # Verify
    async with db.AsyncSessionLocal() as session:
        g_stmt = select(Game).where(Game.name == "Ticket to Ride")
        game = (await session.execute(g_stmt)).scalar_one_or_none()
        assert game is not None
        assert game.min_players == 2
        assert game.max_players == 5
        
        # Verify collection
        c_stmt = select(Collection).where(
            Collection.user_id == -456,
            Collection.game_id == game.id
        )
        assert (await session.execute(c_stmt)).scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_startnight_with_guests_shows_confirmation(mock_update, mock_context):
    """Test /gamenight shows confirmation when session has guests."""
    # Setup: Old session with a guest
    async with db.AsyncSessionLocal() as session:
        session.add(Session(chat_id=12345, is_active=True))
        guest = User(telegram_id=-555, telegram_name="OldGuest", is_guest=True)
        session.add(guest)
        session.add(SessionPlayer(session_id=12345, user_id=-555))
        await session.commit()
    
    # Start new night - should show confirmation since guest exists
    await start_night(mock_update, mock_context)
    
    # Verify confirmation dialog shown (guest still exists)
    call_args = mock_update.message.reply_text.call_args
    message_text = call_args.kwargs.get('text') or call_args.args[0]
    assert "Already Running" in message_text
    assert "OldGuest" in message_text

