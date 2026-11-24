import sys
from pathlib import Path

# Use the repo's backend root: pytest can be launched from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
