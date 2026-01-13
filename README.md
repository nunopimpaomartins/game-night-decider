# Game Night Decider 🎲

A Telegram bot that helps your group decide what board game to play on game night.

## Features

- **BGG Integration**: Syncs your collection from BoardGameGeek
- **Lobby System**: Create a lobby for players to join
- **Smart Filtering**: Only shows games that support the player count
- **Complexity Splitting**: Polls are split by game weight (Light/Medium/Heavy)
- **New Game Flags**: Mark games as "new" to promote trying them
- **Exclusions**: Temporarily exclude games you don't want to play

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/setbgg <username>` | Link your BoardGameGeek account |
| `/gamenight` | Start a new game night lobby |
| `/poll` | Generate voting polls |
| `/addguest <name>` | Add a guest player |
| `/guestgame <name> <game>` | Add a game for a guest |
| `/markplayed <game>` | Mark a game as played (removes "new" flag) |
| `/exclude <game>` | Toggle game exclusion from polls |

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Local Development

```bash
# Clone the repository
git clone https://github.com/JCaet/game-night-decider.git
cd game-night-decider

# Install dependencies
uv sync --group dev

# Create .env file
cp .env.example .env
# Edit .env and add your TELEGRAM_BOT_TOKEN

# Run the bot
uv run python -m src.bot.main
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `DATABASE_URL` | PostgreSQL connection string (optional, defaults to SQLite) |

## Deployment

The bot is designed to run on Google Cloud Run. See `.github/workflows/deploy.yml` for the CI/CD pipeline.

### Required GitHub Secrets

- `GCP_PROJECT_ID`
- `GCP_CREDENTIALS`
- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL` (Cloud SQL connection string)

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy .
```

## License

MIT
