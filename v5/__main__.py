"""CLI entry point for WB Analytics v5"""

import asyncio
import sys
from pathlib import Path

# Добавляем текущую папку в path
sys.path.insert(0, str(Path(__file__).parent))

from entry import main


if __name__ == "__main__":
    asyncio.run(main())
