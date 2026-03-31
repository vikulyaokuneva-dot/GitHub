"""CLI entry point for WB Analytics v5"""

import asyncio
import sys

from . import entry


if __name__ == "__main__":
    asyncio.run(entry.main())
