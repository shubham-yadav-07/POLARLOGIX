"""Drop and recreate all tables, then reseed. Useful after changing models or datasets.

Usage:  python scripts/reset_db.py
"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.db import Base, engine
from app.seed import init_db

if __name__ == "__main__":
    print("Dropping all tables...")
    Base.metadata.drop_all(engine)
    print("Recreating and seeding...")
    init_db()
    print("Done.")
