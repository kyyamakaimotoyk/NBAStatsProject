"""
Add BoxScoreSummaryV3 columns to importedgamesmemory table
"""

# Project-root bootstrap so cross-folder imports work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from data_engineering.main_refactored import NBADataImporter
import sqlalchemy as sql

# Connect to database
importer = NBADataImporter()
importer.connect_to_database()

# List of V3 columns to add
v3_columns = [
    'nba_data.boxscoresummaryv3_game_summary',
    'nba_data.boxscoresummaryv3_game_info',
    'nba_data.boxscoresummaryv3_arena_info',
    'nba_data.boxscoresummaryv3_officials',
    'nba_data.boxscoresummaryv3_line_score',
    'nba_data.boxscoresummaryv3_inactive_players',
    'nba_data.boxscoresummaryv3_last_five_meetings',
    'nba_data.boxscoresummaryv3_other_stats',
]

print("Adding V3 columns to importedgamesmemory table...")
print("=" * 70)

for col_name in v3_columns:
    try:
        # MySQL requires backticks for column names with dots
        alter_sql = f"ALTER TABLE importedgamesmemory ADD COLUMN `{col_name}` TINYINT DEFAULT 0"
        importer.connection.execute(sql.text(alter_sql))
        importer.connection.commit()
        print(f"[OK] Added: {col_name}")
    except Exception as e:
        if "Duplicate column name" in str(e):
            print(f"[SKIP] {col_name} (already exists)")
        else:
            print(f"[ERROR] {col_name}: {e}")
            raise

print("=" * 70)
print(f"\nSuccess! All {len(v3_columns)} V3 columns added to importedgamesmemory")
print("Default value: 0 (not attempted)")
