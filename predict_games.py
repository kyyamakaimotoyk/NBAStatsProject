"""
NBA Game Prediction Script
==========================

Predicts winners and winning margins for today's/tomorrow's NBA games.
Supports both Random Forest (scikit-learn) and Neural Network (PyTorch) models.

Features:
- Fetches scheduled games from NBA API
- Loads recent team stats from database
- Predicts win probability and point margin
- Shows uncertainty distributions via histograms
- Compares sklearn vs PyTorch predictions

Usage:
    python predict_games.py                    # Today's games with Random Forest
    python predict_games.py --model nn         # Today's games with Neural Network
    python predict_games.py --model both       # Compare both models
    python predict_games.py --tomorrow         # Tomorrow's games
    python predict_games.py --date 2024-12-25  # Specific date
"""

import argparse
import sqlalchemy as sql
from sqlalchemy import text
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import joblib
import os
import warnings
warnings.filterwarnings('ignore')

# For visualization
import matplotlib.pyplot as plt

# NBA API for scheduled games
try:
    from nba_api.stats.endpoints import ScoreboardV2
    from nba_api.stats.static import teams as nba_teams
    NBA_API_AVAILABLE = True
except ImportError:
    NBA_API_AVAILABLE = False
    print("Warning: nba_api not installed. Install with: pip install nba_api")

# Scikit-learn
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

# PyTorch
try:
    import torch
    import torch.nn as nn
    PYTORCH_AVAILABLE = True
except (ImportError, OSError) as e:
    PYTORCH_AVAILABLE = False
    print(f"Warning: PyTorch not available ({type(e).__name__}). Neural network models disabled.")
    print("  To enable: pip install torch (may need Visual C++ redistributable on Windows)")
    # Create dummy classes so code doesn't break
    class nn:
        class Module:
            pass
        class Sequential:
            pass
        class Linear:
            pass
        class BatchNorm1d:
            pass
        class ReLU:
            pass
        class Dropout:
            pass
        class BCEWithLogitsLoss:
            pass
        class MSELoss:
            pass


# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def create_engine():
    """Create database connection engine."""
    host = 'localhost'
    user = 'kaiyamamoto'
    password = 'KN!yoWMhiH8cBvD'
    port = '3306'
    database = 'nba_data'
    connection_string = f'mysql://{user}:{password}@{host}:{port}/{database}'
    return sql.create_engine(connection_string)


# ============================================================================
# PYTORCH MODEL DEFINITIONS
# ============================================================================

class NBAClassifier(nn.Module):
    """
    Neural network for win/loss classification.
    Uses dropout for Monte Carlo uncertainty estimation.
    """
    def __init__(self, input_dim, dropout_rate=0.3):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        return self.network(x)


class NBARegressor(nn.Module):
    """
    Neural network for point margin regression.
    Uses dropout for Monte Carlo uncertainty estimation.
    """
    def __init__(self, input_dim, dropout_rate=0.3):
        super().__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(32, 1)
        )

    def forward(self, x):
        return self.network(x)


# ============================================================================
# GET SCHEDULED GAMES
# ============================================================================

def get_nba_team_mapping():
    """Get mapping of team abbreviations to IDs."""
    if not NBA_API_AVAILABLE:
        return {}
    team_list = nba_teams.get_teams()
    return {t['abbreviation']: t['id'] for t in team_list}


def get_scheduled_games(game_date: str) -> pd.DataFrame:
    """
    Get scheduled games for a given date from NBA API.
    """
    if not NBA_API_AVAILABLE:
        print("NBA API not available. Please install nba_api package.")
        return pd.DataFrame()

    dt = datetime.strptime(game_date, '%Y-%m-%d')
    api_date = dt.strftime('%m/%d/%Y')

    try:
        print(f"Fetching games for {game_date}...")
        scoreboard = ScoreboardV2(game_date=api_date)
        games_df = scoreboard.get_data_frames()[0]

        if len(games_df) == 0:
            print(f"No games scheduled for {game_date}")
            return pd.DataFrame()

        scheduled = []
        for _, game in games_df.iterrows():
            scheduled.append({
                'GAME_ID': game['GAME_ID'],
                'HOME_TEAM_ID': game['HOME_TEAM_ID'],
                'AWAY_TEAM_ID': game['VISITOR_TEAM_ID'],
                'GAME_STATUS': game.get('GAME_STATUS_TEXT', 'Scheduled'),
                'ARENA': game.get('ARENA_NAME', 'Unknown')
            })

        result = pd.DataFrame(scheduled)
        team_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
        result['HOME_TEAM'] = result['HOME_TEAM_ID'].map(team_map)
        result['AWAY_TEAM'] = result['AWAY_TEAM_ID'].map(team_map)

        return result

    except Exception as e:
        print(f"Error fetching games: {e}")
        return pd.DataFrame()


# ============================================================================
# GET TEAM FEATURES
# ============================================================================

def get_team_rolling_stats(engine, team_id: int, as_of_date: str = None) -> dict:
    """Get the most recent rolling statistics for a team."""
    if as_of_date is None:
        as_of_date = datetime.now().strftime('%Y-%m-%d')

    query = f"""
        SELECT
            gl.TEAM_ID, gl.TEAM_ABBREVIATION, gl.GAME_DATE, gl.GAME_ID,
            gl.PTS, gl.FGM, gl.FGA, gl.FG_PCT, gl.FG3M, gl.FG3A, gl.FG3_PCT,
            gl.FTM, gl.FTA, gl.FT_PCT, gl.OREB, gl.DREB, gl.REB,
            gl.AST, gl.STL, gl.BLK, gl.TOV, gl.PF, gl.PLUS_MINUS, gl.WL,
            adv.offensiveRating, adv.defensiveRating, adv.netRating,
            adv.pace, adv.possessions,
            adv.effectiveFieldGoalPercentage as EFG_PCT,
            adv.trueShootingPercentage as TS_PCT,
            adv.assistPercentage, adv.assistToTurnover,
            adv.offensiveReboundPercentage as ADV_OREB_PCT,
            adv.defensiveReboundPercentage as ADV_DREB_PCT,
            adv.turnoverRatio, adv.PIE,
            ff.freeThrowAttemptRate as FT_RATE,
            ff.teamTurnoverPercentage as TOV_PCT,
            ff.offensiveReboundPercentage as OREB_PCT,
            ff.oppEffectiveFieldGoalPercentage as OPP_EFG_PCT,
            ff.oppFreeThrowAttemptRate as OPP_FT_RATE,
            ff.oppTeamTurnoverPercentage as OPP_TOV_PCT,
            ff.oppOffensiveReboundPercentage as OPP_OREB_PCT,
            hst.contestedShots, hst.contestedShots2pt, hst.contestedShots3pt,
            hst.deflections, hst.chargesDrawn, hst.screenAssists,
            hst.looseBallsRecoveredTotal as looseBallsRecovered, hst.boxOuts,
            trk.speed, trk.distance, trk.reboundChancesTotal,
            trk.touches, trk.passes, trk.secondaryAssists,
            trk.contestedFieldGoalsMade, trk.contestedFieldGoalsAttempted,
            trk.uncontestedFieldGoalsMade, trk.uncontestedFieldGoalsAttempted,
            trk.defendedAtRimFieldGoalsMade, trk.defendedAtRimFieldGoalsAttempted,
            msc.pointsOffTurnovers, msc.pointsSecondChance,
            msc.pointsFastBreak, msc.pointsPaint,
            msc.oppPointsOffTurnovers, msc.oppPointsSecondChance,
            msc.oppPointsFastBreak, msc.oppPointsPaint, msc.foulsDrawn,
            scr.percentageFieldGoalsAttempted2pt as pctFGA_2pt,
            scr.percentageFieldGoalsAttempted3pt as pctFGA_3pt,
            scr.percentagePoints2pt as pctPTS_2pt,
            scr.percentagePoints3pt as pctPTS_3pt,
            scr.percentagePointsPaint as pctPTS_paint,
            scr.percentagePointsFastBreak as pctPTS_fastBreak,
            scr.percentageAssistedFGM as pctAssisted,
            scr.percentageUnassistedFGM as pctUnassisted
        FROM game_list gl
        LEFT JOIN boxscoreadvancedv3_team adv ON gl.GAME_ID = adv.gameId AND gl.TEAM_ID = adv.teamId
        LEFT JOIN boxscorefourfactorsv3_team ff ON gl.GAME_ID = ff.gameId AND gl.TEAM_ID = ff.teamId
        LEFT JOIN boxscorehustlev2_team hst ON gl.GAME_ID = hst.gameId AND gl.TEAM_ID = hst.teamId
        LEFT JOIN boxscoreplayertrackv3_team trk ON gl.GAME_ID = trk.gameId AND gl.TEAM_ID = trk.teamId
        LEFT JOIN boxscoremiscv3_team msc ON gl.GAME_ID = msc.gameId AND gl.TEAM_ID = msc.teamId
        LEFT JOIN boxscorescoringv3_team scr ON gl.GAME_ID = scr.gameId AND gl.TEAM_ID = scr.teamId
        WHERE gl.TEAM_ID = {team_id}
            AND gl.GAME_DATE < '{as_of_date}'
            AND gl.WL IS NOT NULL
        ORDER BY gl.GAME_DATE DESC
        LIMIT 15
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    if len(df) == 0:
        return None

    rolling_stats = [
        'PTS', 'FGM', 'FGA', 'FG_PCT', 'FG3M', 'FG3A', 'FG3_PCT',
        'FTM', 'FTA', 'FT_PCT', 'OREB', 'DREB', 'REB', 'AST', 'STL',
        'BLK', 'TOV', 'PF', 'PLUS_MINUS',
        'offensiveRating', 'defensiveRating', 'netRating', 'pace',
        'possessions', 'EFG_PCT', 'TS_PCT', 'assistPercentage',
        'assistToTurnover', 'ADV_OREB_PCT', 'ADV_DREB_PCT', 'turnoverRatio', 'PIE',
        'FT_RATE', 'TOV_PCT', 'OREB_PCT', 'OPP_EFG_PCT', 'OPP_FT_RATE',
        'OPP_TOV_PCT', 'OPP_OREB_PCT',
        'contestedShots', 'contestedShots2pt', 'contestedShots3pt',
        'deflections', 'chargesDrawn', 'screenAssists', 'looseBallsRecovered', 'boxOuts',
        'speed', 'distance', 'reboundChancesTotal', 'touches', 'passes',
        'secondaryAssists', 'contestedFieldGoalsMade', 'contestedFieldGoalsAttempted',
        'uncontestedFieldGoalsMade', 'uncontestedFieldGoalsAttempted',
        'defendedAtRimFieldGoalsMade', 'defendedAtRimFieldGoalsAttempted',
        'pointsOffTurnovers', 'pointsSecondChance', 'pointsFastBreak',
        'pointsPaint', 'oppPointsOffTurnovers', 'oppPointsSecondChance',
        'oppPointsFastBreak', 'oppPointsPaint', 'foulsDrawn',
        'pctFGA_2pt', 'pctFGA_3pt', 'pctPTS_2pt', 'pctPTS_3pt',
        'pctPTS_paint', 'pctPTS_fastBreak', 'pctAssisted', 'pctUnassisted'
    ]

    features = {'TEAM_ID': team_id, 'TEAM_ABBREVIATION': df['TEAM_ABBREVIATION'].iloc[0]}

    for stat in rolling_stats:
        if stat in df.columns:
            features[f'{stat}_L5'] = df[stat].head(5).mean()
            features[f'{stat}_L10'] = df[stat].head(10).mean()

    # Win streak
    streak = 0
    for wl in df['WL'].head(10):
        if wl == 'W':
            streak = streak + 1 if streak >= 0 else 1
        else:
            streak = streak - 1 if streak <= 0 else -1
            break
    features['WIN_STREAK'] = streak

    # Rest days
    if len(df) >= 2:
        last_game = pd.to_datetime(df['GAME_DATE'].iloc[0])
        today = pd.to_datetime(as_of_date)
        features['REST_DAYS'] = (today - last_game).days
    else:
        features['REST_DAYS'] = 3

    # =========================================================================
    # FATIGUE FEATURES
    # =========================================================================
    rest_days = features['REST_DAYS']

    # IS_BACK_TO_BACK: Playing with 0 or 1 day rest
    features['IS_BACK_TO_BACK'] = 1 if rest_days <= 1 else 0

    # Games in last 7 and 14 days
    game_dates = pd.to_datetime(df['GAME_DATE']).values
    today = pd.to_datetime(as_of_date)

    games_last_7 = sum(game_dates > (today - pd.Timedelta(days=7)))
    games_last_14 = sum(game_dates > (today - pd.Timedelta(days=14)))

    features['GAMES_LAST_7_DAYS'] = games_last_7
    features['GAMES_LAST_14_DAYS'] = games_last_14

    # IS_3_IN_4_NIGHTS: 2+ games in last 3 days means this is 3rd in 4 nights
    games_last_3 = sum(game_dates > (today - pd.Timedelta(days=3)))
    features['IS_3_IN_4_NIGHTS'] = 1 if games_last_3 >= 2 else 0

    # AVG_REST_LAST_5: Average rest between last 5 games
    if len(df) >= 5:
        game_dates_sorted = pd.to_datetime(df['GAME_DATE'].head(6))
        rest_between = game_dates_sorted.diff().dt.days.dropna().abs()
        features['AVG_REST_LAST_5'] = rest_between.head(5).mean()
    else:
        features['AVG_REST_LAST_5'] = 2.5

    # ROAD_TRIP_LENGTH: Would need matchup info, set to 0 for now
    # (This gets calculated at matchup level based on IS_HOME)
    features['ROAD_TRIP_LENGTH'] = 0

    features['HOME_WIN_PCT_L10'] = 0.5
    features['AWAY_WIN_PCT_L10'] = 0.5

    return features


def build_matchup_features(home_features: dict, away_features: dict) -> dict:
    """Build matchup-level features from home and away team features."""
    matchup = {}

    for key, value in home_features.items():
        if key not in ['TEAM_ID', 'TEAM_ABBREVIATION']:
            matchup[f'HOME_{key}'] = value

    for key, value in away_features.items():
        if key not in ['TEAM_ID', 'TEAM_ABBREVIATION']:
            matchup[f'AWAY_{key}'] = value

    for key in home_features.keys():
        if key not in ['TEAM_ID', 'TEAM_ABBREVIATION']:
            home_val = home_features.get(key, 0) or 0
            away_val = away_features.get(key, 0) or 0
            matchup[f'DIFF_{key}'] = home_val - away_val

    return matchup


# ============================================================================
# MODEL TRAINING / LOADING - RANDOM FOREST
# ============================================================================

def load_or_train_rf_models(engine):
    """Load pre-trained Random Forest models or train new ones."""
    clf_path = 'models/rf_classifier.joblib'
    reg_path = 'models/rf_regressor.joblib'
    scaler_path = 'models/scaler.joblib'
    features_path = 'models/feature_names.joblib'

    if all(os.path.exists(p) for p in [clf_path, reg_path, scaler_path, features_path]):
        print("Loading pre-trained Random Forest models...")
        clf = joblib.load(clf_path)
        reg = joblib.load(reg_path)
        scaler = joblib.load(scaler_path)
        feature_names = joblib.load(features_path)
        return clf, reg, scaler, feature_names

    print("Training Random Forest models...")
    ml_df, feature_cols, X_scaled, y_clf, y_reg, scaler_tuple = _prepare_training_data(engine)

    imputer, scaler = scaler_tuple

    print("  Training RF classifier...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    clf.fit(X_scaled, y_clf)

    print("  Training RF regressor...")
    reg = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    reg.fit(X_scaled, y_reg)

    os.makedirs('models', exist_ok=True)
    joblib.dump(clf, clf_path)
    joblib.dump(reg, reg_path)
    joblib.dump((imputer, scaler), scaler_path)
    joblib.dump(feature_cols, features_path)

    print("  Random Forest models saved to ./models/")
    return clf, reg, (imputer, scaler), feature_cols


# ============================================================================
# MODEL TRAINING / LOADING - PYTORCH
# ============================================================================

def load_or_train_pytorch_models(engine):
    """Load pre-trained PyTorch models or train new ones."""
    if not PYTORCH_AVAILABLE:
        raise ImportError("PyTorch not available")

    clf_path = 'models/nn_classifier.pt'
    reg_path = 'models/nn_regressor.pt'
    scaler_path = 'models/scaler.joblib'
    features_path = 'models/feature_names.joblib'
    config_path = 'models/nn_config.joblib'

    if all(os.path.exists(p) for p in [clf_path, reg_path, scaler_path, features_path, config_path]):
        print("Loading pre-trained PyTorch models...")
        scaler = joblib.load(scaler_path)
        feature_names = joblib.load(features_path)
        config = joblib.load(config_path)

        clf = NBAClassifier(config['input_dim'])
        clf.load_state_dict(torch.load(clf_path, weights_only=True))
        clf.eval()

        reg = NBARegressor(config['input_dim'])
        reg.load_state_dict(torch.load(reg_path, weights_only=True))
        reg.eval()

        return clf, reg, scaler, feature_names

    print("Training PyTorch models...")
    ml_df, feature_cols, X_scaled, y_clf, y_reg, scaler_tuple = _prepare_training_data(engine)

    input_dim = X_scaled.shape[1]

    # Train classifier
    print("  Training NN classifier...")
    clf = NBAClassifier(input_dim)
    _train_pytorch_model(clf, X_scaled, y_clf.values, is_classifier=True)

    # Train regressor
    print("  Training NN regressor...")
    reg = NBARegressor(input_dim)
    _train_pytorch_model(reg, X_scaled, y_reg.values, is_classifier=False)

    os.makedirs('models', exist_ok=True)
    torch.save(clf.state_dict(), clf_path)
    torch.save(reg.state_dict(), reg_path)

    # Save scaler if not already saved
    if not os.path.exists(scaler_path):
        joblib.dump(scaler_tuple, scaler_path)
    if not os.path.exists(features_path):
        joblib.dump(feature_cols, features_path)

    joblib.dump({'input_dim': input_dim}, config_path)

    print("  PyTorch models saved to ./models/")
    return clf, reg, scaler_tuple, feature_cols


def _prepare_training_data(engine):
    """Prepare training data (shared by RF and PyTorch)."""
    if os.path.exists('nba_ml_features.csv'):
        ml_df = pd.read_csv('nba_ml_features.csv')
    else:
        from feature_engineering import build_feature_dataset, prepare_ml_dataset
        feature_df = build_feature_dataset(engine, start_date='2020-01-01')
        ml_df, _ = prepare_ml_dataset(feature_df)
        ml_df.to_csv('nba_ml_features.csv', index=False)

    # Feature patterns must match those in feature_engineering.py
    feature_patterns = ['_L5', '_L10', 'STREAK', 'REST_DAYS', 'WIN_PCT',
                        'IS_BACK_TO_BACK', 'IS_3_IN_4_NIGHTS', 'GAMES_LAST',
                        'AVG_REST_LAST', 'ROAD_TRIP_LENGTH']
    feature_cols = [col for col in ml_df.columns if any(p in col for p in feature_patterns)]

    X = ml_df[feature_cols].copy()
    y_clf = ml_df['TARGET_WIN']
    y_reg = ml_df['TARGET_MARGIN']

    valid_cols = X.columns[X.notna().any()].tolist()
    X = X[valid_cols]

    imputer = SimpleImputer(strategy='median')
    scaler = StandardScaler()

    X_imputed = imputer.fit_transform(X)
    X_scaled = scaler.fit_transform(X_imputed)

    return ml_df, valid_cols, X_scaled, y_clf, y_reg, (imputer, scaler)


def _train_pytorch_model(model, X, y, is_classifier=True, epochs=100, lr=0.001):
    """Train a PyTorch model with early stopping."""
    X_tensor = torch.FloatTensor(X)
    y_tensor = torch.FloatTensor(y).unsqueeze(1)

    # Split for validation
    split_idx = int(0.8 * len(X))
    X_train, X_val = X_tensor[:split_idx], X_tensor[split_idx:]
    y_train, y_val = y_tensor[:split_idx], y_tensor[split_idx:]

    if is_classifier:
        criterion = nn.BCEWithLogitsLoss()
    else:
        criterion = nn.MSELoss()

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    best_val_loss = float('inf')
    patience = 10
    patience_counter = 0

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)
        loss.backward()
        optimizer.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val)
            val_loss = criterion(val_outputs, y_val).item()
        model.train()

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                break

    model.eval()


# ============================================================================
# PREDICTION FUNCTIONS
# ============================================================================

def predict_with_rf(clf, reg, scaler_tuple, feature_names, matchup_features: dict):
    """Make predictions with Random Forest (uncertainty from tree ensemble)."""
    imputer, scaler = scaler_tuple

    X = pd.DataFrame([matchup_features])
    for col in feature_names:
        if col not in X.columns:
            X[col] = np.nan
    X = X[feature_names]

    X_imputed = imputer.transform(X)
    X_scaled = scaler.transform(X_imputed)

    win_prob = clf.predict_proba(X_scaled)[0][1]
    tree_predictions = np.array([tree.predict(X_scaled)[0] for tree in reg.estimators_])
    margin_mean = np.mean(tree_predictions)
    margin_std = np.std(tree_predictions)

    return {
        'win_prob': win_prob,
        'margin_mean': margin_mean,
        'margin_std': margin_std,
        'margin_samples': tree_predictions,
        'model': 'Random Forest'
    }


def enable_dropout(model):
    """Enable dropout layers while keeping BatchNorm in eval mode."""
    for module in model.modules():
        if isinstance(module, torch.nn.Dropout):
            module.train()


def predict_with_pytorch(clf, reg, scaler_tuple, feature_names, matchup_features: dict, n_samples=100):
    """
    Make predictions with PyTorch using Monte Carlo Dropout.

    Monte Carlo Dropout: Run inference multiple times with dropout ENABLED
    to get a distribution of predictions, which estimates uncertainty.

    Note: We keep BatchNorm in eval mode (it doesn't work with batch_size=1 in train mode)
    but enable Dropout layers for uncertainty estimation.
    """
    imputer, scaler = scaler_tuple

    X = pd.DataFrame([matchup_features])
    for col in feature_names:
        if col not in X.columns:
            X[col] = np.nan
    X = X[feature_names]

    X_imputed = imputer.transform(X)
    X_scaled = scaler.transform(X_imputed)
    X_tensor = torch.FloatTensor(X_scaled)

    # Keep models in eval mode (for BatchNorm) but enable dropout
    clf.eval()
    reg.eval()
    enable_dropout(clf)
    enable_dropout(reg)

    win_probs = []
    margin_samples = []

    with torch.no_grad():
        for _ in range(n_samples):
            # Classification
            logit = clf(X_tensor)
            prob = torch.sigmoid(logit).item()
            win_probs.append(prob)

            # Regression
            margin = reg(X_tensor).item()
            margin_samples.append(margin)

    # Fully back to eval mode
    clf.eval()
    reg.eval()

    win_prob = np.mean(win_probs)
    margin_mean = np.mean(margin_samples)
    margin_std = np.std(margin_samples)

    return {
        'win_prob': win_prob,
        'win_prob_std': np.std(win_probs),
        'margin_mean': margin_mean,
        'margin_std': margin_std,
        'margin_samples': np.array(margin_samples),
        'model': 'Neural Network (MC Dropout)'
    }


# Alias for backward compatibility
def load_or_train_models(engine):
    """Default to Random Forest models."""
    return load_or_train_rf_models(engine)


def predict_with_uncertainty(clf, reg, scaler_tuple, feature_names, matchup_features: dict):
    """Default to Random Forest prediction."""
    return predict_with_rf(clf, reg, scaler_tuple, feature_names, matchup_features)


# ============================================================================
# VISUALIZATION
# ============================================================================

def plot_prediction_histograms(predictions: list, game_date: str, save_path: str = None):
    """Create histogram visualizations for game predictions."""
    n_games = len(predictions)
    if n_games == 0:
        print("No games to visualize")
        return

    fig, axes = plt.subplots(n_games, 2, figsize=(12, 4 * n_games))
    if n_games == 1:
        axes = axes.reshape(1, -1)

    fig.suptitle(f'NBA Game Predictions for {game_date}', fontsize=14, fontweight='bold')

    for i, pred in enumerate(predictions):
        home = pred['home_team']
        away = pred['away_team']
        win_prob = pred['win_prob']
        margin_samples = pred['margin_samples']

        ax1 = axes[i, 0]
        colors = ['#2ecc71' if win_prob > 0.5 else '#e74c3c',
                  '#e74c3c' if win_prob > 0.5 else '#2ecc71']
        bars = ax1.barh([away, home], [1 - win_prob, win_prob], color=colors)
        ax1.set_xlim(0, 1)
        ax1.set_xlabel('Win Probability')
        ax1.set_title(f'{away} @ {home}')
        ax1.axvline(x=0.5, color='gray', linestyle='--', alpha=0.5)

        for bar, prob in zip(bars, [1 - win_prob, win_prob]):
            ax1.text(prob + 0.02, bar.get_y() + bar.get_height()/2,
                    f'{prob:.1%}', va='center', fontsize=10)

        ax2 = axes[i, 1]
        ax2.hist(margin_samples, bins=20, color='#3498db', alpha=0.7, edgecolor='black')
        ax2.axvline(x=0, color='red', linestyle='--', linewidth=2, label='Even')
        ax2.axvline(x=np.mean(margin_samples), color='green', linestyle='-',
                   linewidth=2, label=f'Predicted: {np.mean(margin_samples):+.1f}')
        ax2.set_xlabel(f'Point Margin (+ = {home} wins)')
        ax2.set_ylabel('Frequency')
        ax2.set_title(f'Margin Distribution (Std: {np.std(margin_samples):.1f})')
        ax2.legend(loc='upper right')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {save_path}")

    plt.show()


def print_predictions_table(predictions: list, game_date: str, model_name: str = ""):
    """Print predictions in a formatted table."""
    print("\n" + "=" * 85)
    print(f"NBA GAME PREDICTIONS FOR {game_date}" + (f" ({model_name})" if model_name else ""))
    print("=" * 85)

    if not predictions:
        print("No games found for this date.")
        return

    print(f"\n{'Matchup':<25} {'Pick':<12} {'Win Prob':>10} {'Margin':>12} {'Uncertainty':>12}")
    print("-" * 85)

    for pred in predictions:
        home = pred['home_team']
        away = pred['away_team']
        matchup = f"{away} @ {home}"

        win_prob = pred['win_prob']
        margin = pred['margin_mean']
        margin_std = pred['margin_std']

        pick = home if win_prob > 0.5 else away

        margin_str = f"{margin:+.1f} pts"
        uncertainty_str = f"+/-{margin_std:.1f}"

        print(f"{matchup:<25} {pick:<12} {win_prob:>9.1%} {margin_str:>12} {uncertainty_str:>12}")

    print("-" * 85)


def print_comparison_table(rf_predictions: list, nn_predictions: list, game_date: str):
    """Print side-by-side comparison of RF and NN predictions."""
    print("\n" + "=" * 100)
    print(f"MODEL COMPARISON FOR {game_date}")
    print("=" * 100)

    print(f"\n{'Matchup':<20} | {'--- Random Forest ---':^30} | {'--- Neural Network ---':^30}")
    print(f"{'':20} | {'Pick':<8} {'Win%':>8} {'Margin':>10} | {'Pick':<8} {'Win%':>8} {'Margin':>10}")
    print("-" * 100)

    for rf, nn in zip(rf_predictions, nn_predictions):
        matchup = f"{rf['away_team']} @ {rf['home_team']}"

        rf_pick = rf['home_team'] if rf['win_prob'] > 0.5 else rf['away_team']
        nn_pick = nn['home_team'] if nn['win_prob'] > 0.5 else nn['away_team']

        # Highlight disagreements
        disagree = rf_pick != nn_pick
        marker = " *" if disagree else ""

        print(f"{matchup:<20} | {rf_pick:<8} {rf['win_prob']:>7.1%} {rf['margin_mean']:>+9.1f} | "
              f"{nn_pick:<8} {nn['win_prob']:>7.1%} {nn['margin_mean']:>+9.1f}{marker}")

    print("-" * 100)
    print("* = Models disagree on winner")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Predict NBA game outcomes')
    parser.add_argument('--date', type=str, help='Game date (YYYY-MM-DD)')
    parser.add_argument('--tomorrow', action='store_true', help='Predict tomorrow\'s games')
    parser.add_argument('--model', type=str, choices=['rf', 'nn', 'both'], default='rf',
                       help='Model to use: rf (Random Forest), nn (Neural Network), both')
    parser.add_argument('--no-plot', action='store_true', help='Skip histogram plots')
    args = parser.parse_args()

    if args.date:
        game_date = args.date
    elif args.tomorrow:
        game_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        game_date = datetime.now().strftime('%Y-%m-%d')

    print(f"\nNBA Game Predictor")
    print("=" * 40)
    print(f"Prediction date: {game_date}")
    print(f"Model: {args.model}")

    engine = create_engine()

    # Load models
    rf_models = None
    nn_models = None

    if args.model in ['rf', 'both']:
        rf_models = load_or_train_rf_models(engine)

    if args.model in ['nn', 'both']:
        if not PYTORCH_AVAILABLE:
            print("ERROR: PyTorch not available. Install with: pip install torch")
            return
        nn_models = load_or_train_pytorch_models(engine)

    # Get scheduled games
    games = get_scheduled_games(game_date)

    if len(games) == 0:
        print(f"\nNo games found for {game_date}")
        engine.dispose()
        return

    print(f"\nFound {len(games)} games scheduled")

    rf_predictions = []
    nn_predictions = []

    for _, game in games.iterrows():
        home_id = game['HOME_TEAM_ID']
        away_id = game['AWAY_TEAM_ID']
        home_team = game['HOME_TEAM']
        away_team = game['AWAY_TEAM']

        print(f"\nProcessing: {away_team} @ {home_team}")

        home_features = get_team_rolling_stats(engine, home_id, game_date)
        away_features = get_team_rolling_stats(engine, away_id, game_date)

        if home_features is None or away_features is None:
            print(f"  Warning: Missing data, skipping")
            continue

        matchup = build_matchup_features(home_features, away_features)

        if rf_models:
            clf, reg, scaler, features = rf_models
            result = predict_with_rf(clf, reg, scaler, features, matchup)
            result['home_team'] = home_team
            result['away_team'] = away_team
            rf_predictions.append(result)

        if nn_models:
            clf, reg, scaler, features = nn_models
            result = predict_with_pytorch(clf, reg, scaler, features, matchup)
            result['home_team'] = home_team
            result['away_team'] = away_team
            nn_predictions.append(result)

    # Display results
    if args.model == 'both' and rf_predictions and nn_predictions:
        print_comparison_table(rf_predictions, nn_predictions, game_date)
        print_predictions_table(rf_predictions, game_date, "Random Forest")
        print_predictions_table(nn_predictions, game_date, "Neural Network")
    elif rf_predictions:
        print_predictions_table(rf_predictions, game_date, "Random Forest")
    elif nn_predictions:
        print_predictions_table(nn_predictions, game_date, "Neural Network")

    # Plot
    if not args.no_plot:
        if rf_predictions:
            plot_path = f'predictions_rf_{game_date.replace("-", "")}.png'
            plot_prediction_histograms(rf_predictions, game_date + " (RF)", save_path=plot_path)
        if nn_predictions:
            plot_path = f'predictions_nn_{game_date.replace("-", "")}.png'
            plot_prediction_histograms(nn_predictions, game_date + " (NN)", save_path=plot_path)

    engine.dispose()
    print("\nDone!")


if __name__ == '__main__':
    main()
