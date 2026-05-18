"""
Test script for prediction tracking system
"""

# Project-root bootstrap so cross-folder imports work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

from modeling.prediction_tracker import (
    create_engine, table_exists, log_prediction,
    get_predictions_for_date, print_accuracy_report
)
from sqlalchemy import inspect, text

print("=" * 80)
print("PREDICTION TRACKING SYSTEM TEST")
print("=" * 80)

# 1. Test database connection
print("\n1. Testing database connection...")
try:
    engine = create_engine()
    print("   SUCCESS: Database connection established")
except Exception as e:
    print(f"   FAILED: {e}")
    exit(1)

# 2. Check if table exists
print("\n2. Checking if model_predictions table exists...")
if table_exists(engine):
    print("   SUCCESS: Table 'model_predictions' exists")

    # Show schema
    inspector = inspect(engine)
    cols = inspector.get_columns('model_predictions')
    print("\n   Table schema:")
    for col in cols:
        nullable = "NULL" if col['nullable'] else "NOT NULL"
        print(f"      {col['name']}: {col['type']} {nullable}")
else:
    print("   Table does not exist. Run: python prediction_tracker.py --create-table")
    engine.dispose()
    exit(1)

# 3. Check row count
print("\n3. Checking current predictions in database...")
with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM model_predictions")).scalar()
    print(f"   Found {result} predictions in database")

# 4. Show sample data if any
if result > 0:
    print("\n4. Sample predictions:")
    with engine.connect() as conn:
        query = """
        SELECT
            game_date, home_team, away_team, model_type,
            predicted_winner, predicted_margin, home_win_probability,
            actual_winner, is_correct
        FROM model_predictions
        ORDER BY prediction_timestamp DESC
        LIMIT 5
        """
        import pandas as pd
        sample = pd.read_sql(text(query), conn)
        print(sample.to_string(index=False))

# 5. Test logging a sample prediction (dry run - not actually saving)
print("\n5. Testing prediction logging function...")
try:
    from datetime import datetime
    test_game_id = f"TEST_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # This would log a prediction (commented out to not pollute DB)
    # pred_id = log_prediction(
    #     engine=engine,
    #     game_id=test_game_id,
    #     game_date="2024-12-06",
    #     home_team="TEST_HOME",
    #     away_team="TEST_AWAY",
    #     model_type="rf",
    #     model_version="v1.0_480features_test",
    #     predicted_winner="TEST_HOME",
    #     predicted_margin=5.2,
    #     home_win_probability=0.68,
    #     margin_uncertainty=3.1,
    #     feature_count=480
    # )
    print("   SUCCESS: Logging function is available")
except Exception as e:
    print(f"   WARNING: {e}")

# 6. Show accuracy report if we have predictions with results
print("\n6. Accuracy Report:")
try:
    print_accuracy_report(engine)
except Exception as e:
    print(f"   No predictions with actual results yet: {e}")

# Cleanup
engine.dispose()

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
print("\nNext steps:")
print("1. Run predictions: python predict_games.py --model both")
print("2. Wait for games to complete")
print("3. Backfill results: python predict_games.py --backfill")
print("4. View accuracy: python predict_games.py --accuracy-report")
print("5. Generate charts: python prediction_visualizations.py --chart dashboard")
