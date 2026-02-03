# Kanami - Gacha Timer Bot

![Version](https://img.shields.io/badge/version-2.7.0-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%205-red)

A Discord bot that tracks and notifies users about gacha game events across multiple titles.

## Supported Games

- **Arknights (AK)** - Event tracking with LLM-powered extraction
- **Uma Musume (UMA)** - Timeline scraping with special event support
- **Honkai: Star Rail (HSR)** - Prydwen data integration
- **Zenless Zone Zero (ZZZ)** - Generic event tracking
- **Strinova (STRI)** - Generic event tracking
- **Wuthering Waves (WUWA)** - Generic event tracking
- **Shadowverse (SV)** - Win rate tracking and statistics

## Features

✨ Multi-game event tracking with automated scraping/LLM extraction
🔔 Profile-specific notification system with regional targeting (Asia, America, Europe)
🎮 Interactive control panels with persistent views
🔌 REST API for external integrations
🐦 Twitter/X listener for auto-event extraction
📊 Shadowverse win rate tracking with visual dashboards

## Quick Start

### Prerequisites

- Python 3.10+
- Discord Bot Token
- Raspberry Pi 5 (or compatible Linux environment)

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd Gacha-Timer-Bot

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp config/.env.example .env
# Edit .env with your bot token and configuration

# Run the bot
python src/main.py
```

## Documentation

📚 **[Full Documentation](docs/README.md)** - Comprehensive guide and architecture details
🔧 **[API Reference](docs/API_REFERENCE.md)** - REST API documentation
🎯 **[Game Modules Guide](docs/GAME_MODULES.md)** - How to add new games
💾 **[Database Schema](docs/DATABASE_SCHEMA.md)** - Database structure and relationships

## Project Structure

```
Gacha-Timer-Bot/
├── src/              # Source code (SOLID architecture)
├── config/           # Configuration files
├── assets/           # Static assets (fonts, images)
├── data/             # SQLite databases
├── logs/             # Log files
├── tests/            # Unit and integration tests
├── scripts/          # Utility scripts
├── docs/             # Documentation
└── examples/         # Example client code
```

## Commands

**Event Management:**
- `Kanami add` - Add new event
- `Kanami remove` - Remove event
- `Kanami edit` - Edit existing event

**Utilities:**
- `Kanami convert` - Convert date/time to UNIX timestamp
- `Kanami help` - Show help message

**Admin:**
- `Kanami mmj` - Graceful shutdown (owner only)
- `Kanami restart` - Restart bot (owner only)

## Contributing

This project follows SOLID principles and clean architecture patterns. See [REFACTORING_PLAN.md](docs/REFACTORING_PLAN.md) for architectural details.

## License

[Your License Here]

## Support

For issues and questions, please use the GitHub issue tracker.

---

**Made with ❤️ for gacha game players**
