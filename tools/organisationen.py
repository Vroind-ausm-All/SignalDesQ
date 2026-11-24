"""Kurzform für ``python -m sales_tool.betreiber`` (Verwaltung einer Mehrmandanten-Installation, siehe dort)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sales_tool.betreiber import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
