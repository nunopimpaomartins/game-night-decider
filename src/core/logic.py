from src.core.models import Game


def split_games(games: list[Game], max_per_poll: int = 10) -> list[tuple[str, list[Game]]]:
    """
    Split games into logical groups by complexity category.

    Groups games by:
    - Light / Party Games: complexity < 2.0 (but not 0.0)
    - Medium Weight Games: 2.0 <= complexity < 3.0
    - Heavy Strategy Games: complexity >= 3.0
    - Unrated Games: complexity == 0.0 or None

    Each category is then split into chunks of max_per_poll if needed.

    Returns:
        List of (Label, List[Game]) tuples.
    """
    if not games:
        return []

    # Filter invalid entries
    valid_games = [g for g in games if g.name]

    if not valid_games:
        return []

    if len(valid_games) <= max_per_poll:
        return [("Games", valid_games)]

    # Categorize games by complexity
    light: list[Game] = []
    medium: list[Game] = []
    heavy: list[Game] = []
    unrated: list[Game] = []

    for g in valid_games:
        c = g.complexity or 0
        if c <= 0:
            unrated.append(g)
        elif c < 2.0:
            light.append(g)
        elif c < 3.0:
            medium.append(g)
        else:
            heavy.append(g)

    # Sort each category by complexity, then name
    for group in [light, medium, heavy, unrated]:
        group.sort(key=lambda g: (g.complexity or 0, g.name.lower()))

    # Build result, splitting categories into chunks if needed
    result: list[tuple[str, list[Game]]] = []

    def add_category(games_list: list[Game], label: str) -> None:
        if not games_list:
            return
        # Split into chunks of max_per_poll
        chunks = [games_list[i : i + max_per_poll] for i in range(0, len(games_list), max_per_poll)]
        for idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                final_label = f"{label} ({idx + 1}/{len(chunks)})"
            else:
                final_label = label
            result.append((final_label, chunk))

    add_category(light, "Light / Party Games")
    add_category(medium, "Medium Weight Games")
    add_category(heavy, "Heavy Strategy Games")
    add_category(unrated, "Unrated Games")

    return result
