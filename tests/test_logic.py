from src.core.logic import split_games
from src.core.models import Game


def create_game(name: str, complexity: float) -> Game:
    return Game(
        id=hash(name),
        name=name,
        min_players=1,
        max_players=4,
        playing_time=60,
        complexity=complexity,
    )


def test_split_games_small_list():
    """Small lists (<=10) should return a single 'Games' group."""
    games = [
        create_game("Catan", 2.3),
        create_game("Carcassonne", 1.9),
    ]
    result = split_games(games, max_per_poll=10)
    assert len(result) == 1
    assert result[0][0] == "Games"
    assert len(result[0][1]) == 2


def test_split_games_by_category():
    """Games should be grouped by complexity category."""
    # 5 Light games (1.0 - 1.5)
    light = [create_game(f"Light {i}", 1.0 + i * 0.1) for i in range(5)]
    # 6 Heavy games (3.0 - 3.5)
    heavy = [create_game(f"Heavy {i}", 3.0 + i * 0.1) for i in range(6)]

    games = light + heavy
    # Total 11 games -> should split by category, not by fixed chunks

    result = split_games(games, max_per_poll=10)

    assert len(result) == 2

    # First chunk should be light
    label1, chunk1 = result[0]
    assert label1 == "Light / Party Games"
    assert len(chunk1) == 5
    assert all(g.name.startswith("Light") for g in chunk1)

    # Second chunk should be heavy
    label2, chunk2 = result[1]
    assert label2 == "Heavy Strategy Games"
    assert len(chunk2) == 6
    assert all(g.name.startswith("Heavy") for g in chunk2)


def test_split_games_category_overflow():
    """Categories with >10 games should split into numbered parts."""
    # 15 light games (complexity 1.0-1.5)
    games = [create_game(f"Light {i}", 1.0 + i * 0.03) for i in range(15)]

    result = split_games(games, max_per_poll=10)

    assert len(result) == 2
    assert result[0][0] == "Light / Party Games (1/2)"
    assert len(result[0][1]) == 10
    assert result[1][0] == "Light / Party Games (2/2)"
    assert len(result[1][1]) == 5


def test_split_games_unrated():
    """Games with complexity 0.0 should go to 'Unrated Games'."""
    # 5 rated games
    rated = [create_game(f"Rated {i}", 2.5) for i in range(5)]
    # 8 unrated games (complexity 0.0)
    unrated = [create_game(f"Unrated {i}", 0.0) for i in range(8)]

    games = rated + unrated
    result = split_games(games, max_per_poll=10)

    assert len(result) == 2

    # First should be medium weight (rated games)
    label1, chunk1 = result[0]
    assert label1 == "Medium Weight Games"
    assert len(chunk1) == 5

    # Second should be unrated
    label2, chunk2 = result[1]
    assert label2 == "Unrated Games"
    assert len(chunk2) == 8


def test_split_games_all_categories():
    """Test with games across all categories."""
    light = [create_game("Light 1", 1.5)]
    medium = [create_game("Medium 1", 2.5)]
    heavy = [create_game("Heavy 1", 3.5)]
    unrated = [create_game("Unrated 1", 0.0)]

    games = light + medium + heavy + unrated
    result = split_games(games, max_per_poll=10)

    # Should NOT combine into single "Games" even though <=10
    # Wait - it will because total is 4 which is <= 10
    # Small list returns single "Games" group
    assert len(result) == 1
    assert result[0][0] == "Games"
    assert len(result[0][1]) == 4


def test_split_games_empty():
    """Empty list should return empty result."""
    result = split_games([], max_per_poll=10)
    assert result == []

