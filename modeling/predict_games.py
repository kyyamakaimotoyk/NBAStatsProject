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

# Project-root bootstrap so cross-folder imports (core.*, data_engineering.*, modeling.*)
# work regardless of CWD. sys/os are stdlib and don't conflict with the PyTorch-first ordering.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

# PyTorch - MUST be imported FIRST before numpy/pandas on Windows to avoid DLL conflicts
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

# For prediction tracking
try:
    from modeling.prediction_tracker import (
        log_prediction, backfill_actuals, get_model_version,
        print_accuracy_report, ensure_table_exists
    )
    PREDICTION_TRACKING_AVAILABLE = True
except ImportError:
    PREDICTION_TRACKING_AVAILABLE = False
    print("Warning: prediction_tracker not available. Predictions will not be logged to database.")

# For model versioning and registry
try:
    from core.model_registry import (
        ensure_registry_table, register_model, get_current_model,
        compare_models, should_retrain, save_model_with_version,
        print_model_registry
    )
    MODEL_REGISTRY_AVAILABLE = True
except ImportError:
    MODEL_REGISTRY_AVAILABLE = False
    print("Warning: model_registry not available. Model versioning disabled.")

# For player-level projections
try:
    from data_engineering.player_projections import get_matchup_player_features, get_player_projection_features
    PLAYER_PROJECTIONS_AVAILABLE = True
except ImportError:
    PLAYER_PROJECTIONS_AVAILABLE = False
    print("Warning: player_projections not available. Player-level features disabled.")

# For player impact / injury adjustments
try:
    from data_engineering.player_impact import (
        get_player_historical_impact, get_team_player_impacts,
        get_player_id_by_name, calculate_injury_adjusted_margin,
        get_top_players_by_impact, ensure_player_impact_table
    )
    PLAYER_IMPACT_AVAILABLE = True
except ImportError:
    PLAYER_IMPACT_AVAILABLE = False
    print("Warning: player_impact not available. Injury adjustments disabled.")

# For automatic injury data fetching
try:
    from data_engineering.injury_data import (
        get_current_injuries, get_injuries_for_matchup, get_players_out,
        TEAM_ID_TO_ABBREV, ABBREV_TO_TEAM_ID, print_injury_report
    )
    INJURY_DATA_AVAILABLE = True
except ImportError:
    INJURY_DATA_AVAILABLE = False
    print("Warning: injury_data not available. Auto injury fetching disabled.")

# SHAP for feature importance
try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    print("Warning: SHAP not installed. Feature importance explanations disabled.")
    print("  To enable: pip install shap")

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


# ============================================================================
# DATABASE CONNECTION
# ============================================================================

def create_engine():
    """Create database connection engine. Reads MySQL config from environment via db.get_engine()."""
    from core.db import get_engine
    return get_engine()


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
# PYTORCH MODELS WITH PLAYER EMBEDDINGS
# ============================================================================

class NBAClassifierWithEmbeddings(nn.Module):
    """
    Neural network for win/loss classification with player embeddings.

    Architecture:
    - Player IDs (16 per game: 8 home + 8 away) → Embedding layer → Dense vectors
    - Embeddings concatenated with team features and availability flags
    - Combined input passes through MLP

    The embedding layer learns player-specific representations that capture:
    - Playing style interactions
    - Matchup-specific effects
    - Synergies/conflicts between players
    """
    def __init__(self, team_feature_dim, n_players, embedding_dim=16,
                 n_slots=8, dropout_rate=0.3):
        super().__init__()

        self.n_slots = n_slots
        self.embedding_dim = embedding_dim

        # Player embedding: maps player_id -> dense vector
        # Add 1 to n_players for padding index (player_id=0 means empty slot)
        self.player_embedding = nn.Embedding(n_players + 1, embedding_dim, padding_idx=0)

        # Input dimension calculation:
        # - team_feature_dim: all non-player features (rolling stats, fatigue, etc.)
        # - 16 player embeddings (8 home + 8 away) × embedding_dim
        # - 16 availability flags (already in team features, but we use them to mask)
        # - 16 impact scores (already in team features)
        player_input_dim = 2 * n_slots * embedding_dim  # Embedded player vectors

        combined_dim = team_feature_dim + player_input_dim

        self.network = nn.Sequential(
            nn.Linear(combined_dim, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(64, 1)
        )

    def forward(self, team_features, player_ids, availability_mask=None):
        """
        Forward pass with player embeddings.

        Args:
            team_features: Tensor of shape (batch, team_feature_dim) - non-player features
            player_ids: Tensor of shape (batch, 16) - player IDs (8 home + 8 away)
            availability_mask: Optional tensor (batch, 16) - 1 if available, 0 if OUT
                              If provided, OUT players' embeddings are zeroed

        Returns:
            Tensor of shape (batch, 1) - classification logits
        """
        # Get player embeddings: (batch, 16, embedding_dim)
        player_embeds = self.player_embedding(player_ids)

        # Apply availability mask if provided (zero out embeddings for OUT players)
        if availability_mask is not None:
            # Expand mask to match embedding dimensions
            mask = availability_mask.unsqueeze(-1)  # (batch, 16, 1)
            player_embeds = player_embeds * mask

        # Flatten embeddings: (batch, 16 * embedding_dim)
        player_embeds_flat = player_embeds.view(player_embeds.size(0), -1)

        # Concatenate with team features
        combined = torch.cat([team_features, player_embeds_flat], dim=1)

        return self.network(combined)


class NBARegressorWithEmbeddings(nn.Module):
    """
    Neural network for point margin regression with player embeddings.

    Same architecture as classifier but for regression task.
    """
    def __init__(self, team_feature_dim, n_players, embedding_dim=16,
                 n_slots=8, dropout_rate=0.3):
        super().__init__()

        self.n_slots = n_slots
        self.embedding_dim = embedding_dim

        # Player embedding
        self.player_embedding = nn.Embedding(n_players + 1, embedding_dim, padding_idx=0)

        # Combined dimension
        player_input_dim = 2 * n_slots * embedding_dim
        combined_dim = team_feature_dim + player_input_dim

        self.network = nn.Sequential(
            nn.Linear(combined_dim, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(64, 1)
        )

    def forward(self, team_features, player_ids, availability_mask=None):
        """
        Forward pass with player embeddings.

        Args:
            team_features: Tensor of shape (batch, team_feature_dim)
            player_ids: Tensor of shape (batch, 16) - player IDs
            availability_mask: Optional tensor (batch, 16) - availability flags

        Returns:
            Tensor of shape (batch, 1) - margin prediction
        """
        # Get player embeddings
        player_embeds = self.player_embedding(player_ids)

        # Apply availability mask
        if availability_mask is not None:
            mask = availability_mask.unsqueeze(-1)
            player_embeds = player_embeds * mask

        # Flatten and concatenate
        player_embeds_flat = player_embeds.view(player_embeds.size(0), -1)
        combined = torch.cat([team_features, player_embeds_flat], dim=1)

        return self.network(combined)


def create_player_id_mapping(engine):
    """
    Create a mapping from NBA player IDs to sequential indices for embedding.

    The embedding layer needs sequential indices (0, 1, 2, ...) but NBA player IDs
    are large integers (e.g., 1629029). This creates a bidirectional mapping.

    Returns:
        tuple: (player_to_idx, idx_to_player, n_players)
            - player_to_idx: dict mapping NBA player_id -> embedding index
            - idx_to_player: dict mapping embedding index -> NBA player_id
            - n_players: total number of unique players
    """
    from sqlalchemy import text

    query = """
        SELECT DISTINCT personId as player_id
        FROM boxscoretraditionalv3_player
        WHERE personId IS NOT NULL
        ORDER BY personId
    """

    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)

    # Index 0 is reserved for padding (empty slot / unknown player)
    player_to_idx = {0: 0}  # Unknown/empty maps to 0
    idx_to_player = {0: 0}

    for i, player_id in enumerate(df['player_id'].values, start=1):
        player_to_idx[int(player_id)] = i
        idx_to_player[i] = int(player_id)

    n_players = len(df)

    print(f"Created player ID mapping: {n_players} unique players")

    return player_to_idx, idx_to_player, n_players


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

        # Ensure team IDs are integers for proper mapping
        result['HOME_TEAM_ID'] = pd.to_numeric(result['HOME_TEAM_ID'], errors='coerce').astype('Int64')
        result['AWAY_TEAM_ID'] = pd.to_numeric(result['AWAY_TEAM_ID'], errors='coerce').astype('Int64')
        result['HOME_TEAM'] = result['HOME_TEAM_ID'].map(team_map)
        result['AWAY_TEAM'] = result['AWAY_TEAM_ID'].map(team_map)

        # Filter out games with missing team data (e.g., TBD or postponed games)
        before_count = len(result)
        result = result.dropna(subset=['HOME_TEAM_ID', 'AWAY_TEAM_ID', 'HOME_TEAM', 'AWAY_TEAM'])
        if len(result) < before_count:
            print(f"  Filtered out {before_count - len(result)} games with missing team data")

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


def build_matchup_features(home_features: dict, away_features: dict,
                           engine=None, home_team_id: int = None,
                           away_team_id: int = None, game_date: str = None,
                           home_injuries: list = None, away_injuries: list = None) -> dict:
    """
    Build matchup-level features from home and away team features.

    If engine and team IDs are provided, also adds player-level projection features.

    Args:
        home_features: Dict of home team rolling stats
        away_features: Dict of away team rolling stats
        engine: SQLAlchemy database engine (optional)
        home_team_id: Home team NBA ID (optional)
        away_team_id: Away team NBA ID (optional)
        game_date: Game date string YYYY-MM-DD (optional)
        home_injuries: List of injured home team player names to exclude from projections
        away_injuries: List of injured away team player names to exclude from projections
    """
    if home_injuries is None:
        home_injuries = []
    if away_injuries is None:
        away_injuries = []

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

    # Add player-level projection features if available
    # Exclude injured players from roster projections
    if PLAYER_PROJECTIONS_AVAILABLE and engine is not None and home_team_id and away_team_id and game_date:
        try:
            player_features = get_matchup_player_features(
                engine, home_team_id, away_team_id, game_date,
                home_excluded=home_injuries,
                away_excluded=away_injuries
            )
            matchup.update(player_features)
        except Exception as e:
            print(f"  Warning: Player projections failed: {e}")

    # Add player slot features (integrated roster model)
    if PLAYER_IMPACT_AVAILABLE and engine is not None and home_team_id and away_team_id and game_date:
        try:
            slot_features = get_player_slot_features_for_prediction(
                engine, home_team_id, away_team_id, game_date,
                home_injuries, away_injuries
            )
            matchup.update(slot_features)
        except Exception as e:
            print(f"  Warning: Player slot features failed: {e}")

    return matchup


def get_player_slot_features_for_prediction(engine, home_team_id, away_team_id, game_date,
                                              home_injuries=None, away_injuries=None, n_slots=8):
    """
    Get player slot features for a prediction (not a historical game).

    For predictions, we check injuries against the player names to determine availability.
    Returns features in the same format as calculate_player_slot_features() but for a single game.

    Args:
        engine: SQLAlchemy engine
        home_team_id: Home team ID
        away_team_id: Away team ID
        game_date: Game date string
        home_injuries: List of injured home player names (strings)
        away_injuries: List of injured away player names (strings)
        n_slots: Number of player slots per team

    Returns:
        dict with slot features for this matchup
    """
    from data_engineering.player_impact import get_top_players_by_impact

    if home_injuries is None:
        home_injuries = []
    if away_injuries is None:
        away_injuries = []

    # Normalize injury names for matching
    home_injuries_lower = [name.lower().strip() for name in home_injuries]
    away_injuries_lower = [name.lower().strip() for name in away_injuries]

    features = {}
    slot_to_player = {'HOME': {}, 'AWAY': {}}  # For SHAP interpretation

    for side, team_id, injuries_lower in [
        ('HOME', home_team_id, home_injuries_lower),
        ('AWAY', away_team_id, away_injuries_lower)
    ]:
        # Get top players by impact
        top_players = get_top_players_by_impact(engine, team_id, game_date, top_n=n_slots)

        total_available_impact = 0.0
        total_missing_impact = 0.0
        players_out = 0

        for player in top_players:
            slot = player['slot']
            player_name = player['player_name']
            player_id = player['player_id']
            impact = player['impact']

            # Check if this player is injured
            player_name_lower = player_name.lower().strip()
            is_available = player_name_lower not in injuries_lower

            features[f'{side}_SLOT_{slot}_IMPACT'] = impact
            features[f'{side}_SLOT_{slot}_AVAILABLE'] = 1.0 if is_available else 0.0
            features[f'{side}_SLOT_{slot}_PLAYER_ID'] = player_id

            # Store for SHAP interpretation
            slot_to_player[side][slot] = {
                'player_id': player_id,
                'player_name': player_name,
                'impact': impact,
                'available': is_available
            }

            # Aggregate stats
            if is_available:
                total_available_impact += impact
            else:
                total_missing_impact += impact
                players_out += 1

        features[f'{side}_TOTAL_AVAILABLE_IMPACT'] = total_available_impact
        features[f'{side}_TOTAL_MISSING_IMPACT'] = total_missing_impact
        features[f'{side}_PLAYERS_OUT'] = players_out

    # Differential features
    features['DIFF_AVAILABLE_IMPACT'] = features['HOME_TOTAL_AVAILABLE_IMPACT'] - features['AWAY_TOTAL_AVAILABLE_IMPACT']
    features['DIFF_MISSING_IMPACT'] = features['HOME_TOTAL_MISSING_IMPACT'] - features['AWAY_TOTAL_MISSING_IMPACT']

    # Store slot-to-player mapping for SHAP interpretation (will be used in post-processing)
    features['_slot_to_player'] = slot_to_player

    return features


# ============================================================================
# MODEL TRAINING / LOADING - RANDOM FOREST
# ============================================================================

def load_or_train_rf_models(engine, force_retrain=False):
    """Load pre-trained Random Forest models or train new ones.

    Uses model registry to track versions and compare performance.
    Automatically retrains if feature count has changed.

    Args:
        engine: SQLAlchemy database engine
        force_retrain: If True, always retrain even if models exist
    """
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_absolute_error, r2_score

    clf_path = 'models/rf_classifier.joblib'
    reg_path = 'models/rf_regressor.joblib'
    scaler_path = 'models/scaler.joblib'
    features_path = 'models/feature_names.joblib'

    # Check if retraining is needed
    need_retrain = force_retrain

    if not need_retrain and all(os.path.exists(p) for p in [clf_path, reg_path, scaler_path, features_path]):
        saved_features = joblib.load(features_path)

        # Check feature count against current data
        ml_df, current_features, _, _, _, _ = _prepare_training_data(engine)

        if len(current_features) != len(saved_features):
            print(f"\nFeature count changed: {len(saved_features)} -> {len(current_features)}")
            need_retrain = True
        else:
            print("Loading pre-trained Random Forest models...")
            clf = joblib.load(clf_path)
            reg = joblib.load(reg_path)
            scaler = joblib.load(scaler_path)
            return clf, reg, scaler, saved_features

    # Prepare data with train/test split for evaluation
    print("\nTraining Random Forest models...")
    ml_df, feature_cols, X_scaled, y_clf, y_reg, scaler_tuple = _prepare_training_data(engine)

    # Use temporal split - last 20% for test
    n_samples = len(X_scaled)
    split_idx = int(n_samples * 0.8)
    X_train, X_test = X_scaled[:split_idx], X_scaled[split_idx:]
    y_clf_train, y_clf_test = y_clf.values[:split_idx], y_clf.values[split_idx:]
    y_reg_train, y_reg_test = y_reg.values[:split_idx], y_reg.values[split_idx:]

    train_start, train_end, test_start, test_end = _split_window_dates(ml_df, split_idx)

    imputer, scaler = scaler_tuple

    # Hyperparameters captured as a dict so the registry has a faithful record of what produced this model
    rf_clf_hp = {'n_estimators': 100, 'max_depth': 10, 'random_state': 42, 'class': 'RandomForestClassifier'}
    rf_reg_hp = {'n_estimators': 100, 'max_depth': 10, 'random_state': 42, 'class': 'RandomForestRegressor'}

    # Train classifier
    print("  Training RF classifier...")
    clf = RandomForestClassifier(n_estimators=rf_clf_hp['n_estimators'], max_depth=rf_clf_hp['max_depth'],
                                 random_state=rf_clf_hp['random_state'], n_jobs=-1)
    clf.fit(X_train, y_clf_train)

    # Evaluate classifier (test set + train set for overfit gap)
    clf_pred = clf.predict(X_test)
    clf_prob = clf.predict_proba(X_test)[:, 1]
    clf_accuracy = accuracy_score(y_clf_test, clf_pred)
    clf_auc = roc_auc_score(y_clf_test, clf_prob)
    clf_train_pred = clf.predict(X_train)
    clf_train_prob = clf.predict_proba(X_train)[:, 1]
    clf_train_acc = accuracy_score(y_clf_train, clf_train_pred)
    clf_train_auc = roc_auc_score(y_clf_train, clf_train_prob)

    # Train regressor
    print("  Training RF regressor...")
    reg = RandomForestRegressor(n_estimators=rf_reg_hp['n_estimators'], max_depth=rf_reg_hp['max_depth'],
                                random_state=rf_reg_hp['random_state'], n_jobs=-1)
    reg.fit(X_train, y_reg_train)

    # Evaluate regressor (test set + train set for overfit gap)
    reg_pred = reg.predict(X_test)
    reg_mae = mean_absolute_error(y_reg_test, reg_pred)
    reg_r2 = r2_score(y_reg_test, reg_pred)
    reg_train_pred = reg.predict(X_train)
    reg_train_mae = mean_absolute_error(y_reg_train, reg_train_pred)
    reg_train_r2 = r2_score(y_reg_train, reg_train_pred)

    # Compare with previous models and register new ones
    if MODEL_REGISTRY_AVAILABLE:
        # Compare classifier
        is_better_clf, clf_report = compare_models(
            engine, 'rf_classifier',
            {'accuracy': clf_accuracy, 'auc': clf_auc},
            len(feature_cols)
        )
        print(clf_report)

        # Compare regressor
        is_better_reg, reg_report = compare_models(
            engine, 'rf_regressor',
            {'mae': reg_mae, 'r2': reg_r2},
            len(feature_cols)
        )
        print(reg_report)

        # Register new models
        register_model(
            engine, 'rf_classifier', len(feature_cols),
            len(X_train), len(X_test), clf_path, feature_cols,
            accuracy=clf_accuracy, auc=clf_auc,
            train_start_date=train_start, train_end_date=train_end,
            test_start_date=test_start, test_end_date=test_end,
            hyperparameters=rf_clf_hp,
            train_metrics={'accuracy': clf_train_acc, 'auc': clf_train_auc},
            run_kind='train',
        )
        register_model(
            engine, 'rf_regressor', len(feature_cols),
            len(X_train), len(X_test), reg_path, feature_cols,
            mae=reg_mae, r2=reg_r2,
            train_start_date=train_start, train_end_date=train_end,
            test_start_date=test_start, test_end_date=test_end,
            hyperparameters=rf_reg_hp,
            train_metrics={'mae': reg_train_mae, 'r2': reg_train_r2},
            run_kind='train',
        )
    else:
        print(f"\n  Classifier - Accuracy: {clf_accuracy:.4f}, AUC: {clf_auc:.4f}")
        print(f"  Regressor  - MAE: {reg_mae:.2f} points, R2: {reg_r2:.4f}")

    # Retrain on full data for production model
    print("\n  Retraining on full dataset for production...")
    clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    clf.fit(X_scaled, y_clf)
    reg = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    reg.fit(X_scaled, y_reg)

    # Save models
    os.makedirs('models', exist_ok=True)
    joblib.dump(clf, clf_path)
    joblib.dump(reg, reg_path)
    joblib.dump((imputer, scaler), scaler_path)
    joblib.dump(feature_cols, features_path)

    print(f"  Random Forest models saved ({len(feature_cols)} features)")
    return clf, reg, (imputer, scaler), feature_cols


# ============================================================================
# MODEL TRAINING / LOADING - PYTORCH
# ============================================================================

def load_or_train_pytorch_models(engine, force_retrain=False):
    """
    Load pre-trained PyTorch models or train new ones.

    Uses model registry to track versions and compare performance.
    Automatically retrains if feature count has changed.

    Args:
        engine: SQLAlchemy database engine
        force_retrain: If True, always retrain even if models exist

    Returns:
        tuple: (classifier, regressor, feature_scaler, feature_names, target_scaler)
               - classifier: NBAClassifier for win/loss prediction
               - regressor: NBARegressor for point margin prediction
               - feature_scaler: (imputer, scaler) tuple for feature preprocessing
               - feature_names: List of feature column names
               - target_scaler: StandardScaler for inverse-transforming margin predictions
    """
    from sklearn.metrics import accuracy_score, roc_auc_score, mean_absolute_error, r2_score

    if not PYTORCH_AVAILABLE:
        raise ImportError("PyTorch not available")

    clf_path = 'models/nn_classifier.pt'
    reg_path = 'models/nn_regressor.pt'
    scaler_path = 'models/scaler.joblib'
    features_path = 'models/feature_names.joblib'
    config_path = 'models/nn_config.joblib'

    # Check if retraining is needed
    need_retrain = force_retrain

    if not need_retrain and all(os.path.exists(p) for p in [clf_path, reg_path, scaler_path, features_path, config_path]):
        saved_features = joblib.load(features_path)

        # Check feature count against current data
        ml_df, current_features, _, _, _, _ = _prepare_training_data(engine)

        if len(current_features) != len(saved_features):
            print(f"\nFeature count changed: {len(saved_features)} -> {len(current_features)}")
            need_retrain = True
        else:
            print("Loading pre-trained PyTorch models...")
            scaler = joblib.load(scaler_path)
            config = joblib.load(config_path)

            clf = NBAClassifier(config['input_dim'])
            clf.load_state_dict(torch.load(clf_path, weights_only=True))
            clf.eval()

            reg = NBARegressor(config['input_dim'])
            reg.load_state_dict(torch.load(reg_path, weights_only=True))
            reg.eval()

            target_scaler = config.get('target_scaler', None)
            return clf, reg, scaler, saved_features, target_scaler

    print("\nTraining PyTorch models...")
    ml_df, feature_cols, X_scaled, y_clf, y_reg, scaler_tuple = _prepare_training_data(engine)

    # Use temporal split - last 20% for test
    n_samples = len(X_scaled)
    split_idx = int(n_samples * 0.8)
    X_train, X_test = X_scaled[:split_idx], X_scaled[split_idx:]
    y_clf_train, y_clf_test = y_clf.values[:split_idx], y_clf.values[split_idx:]
    y_reg_train, y_reg_test = y_reg.values[:split_idx], y_reg.values[split_idx:]

    train_start, train_end, test_start, test_end = _split_window_dates(ml_df, split_idx)

    input_dim = X_train.shape[1]

    # Hyperparameters faithfully captured for the registry — mirror NBAClassifier/NBARegressor architecture
    nn_clf_hp = {'class': 'NBAClassifier', 'hidden_dims': [128, 64, 32], 'dropout': 0.3,
                 'epochs': 100, 'lr': 0.001, 'optimizer': 'Adam', 'loss': 'BCEWithLogits',
                 'input_dim': int(input_dim)}
    nn_reg_hp = {'class': 'NBARegressor', 'hidden_dims': [128, 64, 32], 'dropout': 0.3,
                 'epochs': 100, 'lr': 0.001, 'optimizer': 'Adam', 'loss': 'MSE',
                 'target_scaling': 'StandardScaler', 'input_dim': int(input_dim)}

    # Train classifier
    print("  Training NN classifier...")
    clf = NBAClassifier(input_dim)
    _train_pytorch_model(clf, X_train, y_clf_train, is_classifier=True)

    # Evaluate classifier (test + train for overfit gap)
    clf.eval()
    with torch.no_grad():
        X_test_tensor = torch.FloatTensor(X_test)
        clf_logits = clf(X_test_tensor).numpy().flatten()
        clf_prob = 1 / (1 + np.exp(-clf_logits))  # sigmoid
        clf_pred = (clf_prob > 0.5).astype(int)

        X_train_tensor = torch.FloatTensor(X_train)
        clf_train_logits = clf(X_train_tensor).numpy().flatten()
        clf_train_prob = 1 / (1 + np.exp(-clf_train_logits))
        clf_train_pred = (clf_train_prob > 0.5).astype(int)
    clf_accuracy = accuracy_score(y_clf_test, clf_pred)
    clf_auc = roc_auc_score(y_clf_test, clf_prob)
    clf_train_acc = accuracy_score(y_clf_train, clf_train_pred)
    clf_train_auc = roc_auc_score(y_clf_train, clf_train_prob)

    # Train regressor WITH target scaling
    print("  Training NN regressor (with target scaling)...")
    reg = NBARegressor(input_dim)
    target_scaler = StandardScaler()
    _train_pytorch_model(reg, X_train, y_reg_train, is_classifier=False, target_scaler=target_scaler)

    # Evaluate regressor (test + train for overfit gap)
    reg.eval()
    with torch.no_grad():
        X_test_tensor = torch.FloatTensor(X_test)
        reg_pred_scaled = reg(X_test_tensor).numpy().flatten()
        reg_pred = target_scaler.inverse_transform(reg_pred_scaled.reshape(-1, 1)).flatten()

        X_train_tensor = torch.FloatTensor(X_train)
        reg_train_pred_scaled = reg(X_train_tensor).numpy().flatten()
        reg_train_pred = target_scaler.inverse_transform(reg_train_pred_scaled.reshape(-1, 1)).flatten()
    reg_mae = mean_absolute_error(y_reg_test, reg_pred)
    reg_r2 = r2_score(y_reg_test, reg_pred)
    reg_train_mae = mean_absolute_error(y_reg_train, reg_train_pred)
    reg_train_r2 = r2_score(y_reg_train, reg_train_pred)

    # Compare with previous models and register new ones
    if MODEL_REGISTRY_AVAILABLE:
        # Compare classifier
        is_better_clf, clf_report = compare_models(
            engine, 'nn_classifier',
            {'accuracy': clf_accuracy, 'auc': clf_auc},
            len(feature_cols)
        )
        print(clf_report)

        # Compare regressor
        is_better_reg, reg_report = compare_models(
            engine, 'nn_regressor',
            {'mae': reg_mae, 'r2': reg_r2},
            len(feature_cols)
        )
        print(reg_report)

        # Register new models
        register_model(
            engine, 'nn_classifier', len(feature_cols),
            len(X_train), len(X_test), clf_path, feature_cols,
            accuracy=clf_accuracy, auc=clf_auc,
            train_start_date=train_start, train_end_date=train_end,
            test_start_date=test_start, test_end_date=test_end,
            hyperparameters=nn_clf_hp,
            train_metrics={'accuracy': clf_train_acc, 'auc': clf_train_auc},
            run_kind='train',
        )
        register_model(
            engine, 'nn_regressor', len(feature_cols),
            len(X_train), len(X_test), reg_path, feature_cols,
            mae=reg_mae, r2=reg_r2,
            train_start_date=train_start, train_end_date=train_end,
            test_start_date=test_start, test_end_date=test_end,
            hyperparameters=nn_reg_hp,
            train_metrics={'mae': reg_train_mae, 'r2': reg_train_r2},
            run_kind='train',
        )
    else:
        print(f"\n  Classifier - Accuracy: {clf_accuracy:.4f}, AUC: {clf_auc:.4f}")
        print(f"  Regressor  - MAE: {reg_mae:.2f} points, R2: {reg_r2:.4f}")

    # Retrain on full data for production model
    print("\n  Retraining on full dataset for production...")
    input_dim = X_scaled.shape[1]
    clf = NBAClassifier(input_dim)
    _train_pytorch_model(clf, X_scaled, y_clf.values, is_classifier=True)
    clf.eval()

    reg = NBARegressor(input_dim)
    target_scaler = StandardScaler()
    _train_pytorch_model(reg, X_scaled, y_reg.values, is_classifier=False, target_scaler=target_scaler)
    reg.eval()

    # Save models
    os.makedirs('models', exist_ok=True)
    torch.save(clf.state_dict(), clf_path)
    torch.save(reg.state_dict(), reg_path)

    # Always save updated scalers and features
    joblib.dump(scaler_tuple, scaler_path)
    joblib.dump(feature_cols, features_path)

    # Save config including target_scaler for margin inverse-transform
    joblib.dump({
        'input_dim': input_dim,
        'target_scaler': target_scaler
    }, config_path)

    print(f"  PyTorch models saved ({len(feature_cols)} features)")
    return clf, reg, scaler_tuple, feature_cols, target_scaler


def _split_window_dates(ml_df, split_idx):
    """Pull the temporal window (train_start, train_end, test_start, test_end) out of ml_df.

    Returns four date objects (or Nones if GAME_DATE is missing). The training split is
    temporal (the first 80% of rows by GAME_DATE order), so train_end + test_start are the
    boundary that defines what "held out" actually means for this version.
    """
    if 'GAME_DATE' not in ml_df.columns:
        return None, None, None, None
    try:
        dates = pd.to_datetime(ml_df['GAME_DATE']).dt.date.tolist()
        return dates[0], dates[split_idx - 1], dates[split_idx], dates[-1]
    except Exception:
        return None, None, None, None


def _prepare_training_data(engine):
    """Prepare training data (shared by RF and PyTorch)."""
    if os.path.exists('nba_ml_features.csv'):
        ml_df = pd.read_csv('nba_ml_features.csv')
    else:
        from data_engineering.feature_engineering import build_feature_dataset, prepare_ml_dataset
        feature_df = build_feature_dataset(engine, start_date='2020-01-01')
        ml_df, _ = prepare_ml_dataset(feature_df)
        ml_df.to_csv('nba_ml_features.csv', index=False)

    # Feature patterns must match those in feature_engineering.py
    # Includes fatigue features, player projection features, and player slot features
    feature_patterns = [
        # Rolling statistics
        '_L5', '_L10',
        # Basic derived features
        'STREAK', 'REST_DAYS', 'WIN_PCT',
        # Fatigue features
        'IS_BACK_TO_BACK', 'IS_3_IN_4_NIGHTS', 'GAMES_LAST',
        'AVG_REST_LAST', 'ROAD_TRIP_LENGTH',
        # Player projection features
        'PROJ_PTS_FROM_PLAYERS', 'PROJ_REB_FROM_PLAYERS', 'PROJ_AST_FROM_PLAYERS',
        'WEIGHTED_AVG_USAGE', 'WEIGHTED_AVG_TS_PCT', 'WEIGHTED_AVG_PIE',
        'ROSTER_DEPTH_SCORE', 'STAR_PLAYER_IMPACT', 'TOP_3_SCORER_SHARE',
        # Player slot features (integrated roster model)
        '_SLOT_', '_IMPACT', '_AVAILABLE',
        'TOTAL_AVAILABLE_IMPACT', 'TOTAL_MISSING_IMPACT', 'PLAYERS_OUT'
    ]
    feature_cols = [col for col in ml_df.columns if any(p in col for p in feature_patterns)]
    # Exclude PLAYER_ID columns (those are for embedding models, not RF)
    feature_cols = [col for col in feature_cols if 'PLAYER_ID' not in col]

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


def _train_pytorch_model(model, X, y, is_classifier=True, epochs=100, lr=0.001, target_scaler=None):
    """
    Train a PyTorch model with early stopping and optional target scaling.

    TARGET SCALING FOR REGRESSION (Critical Fix - 2024-12-08)
    =========================================================
    Problem: Neural network regression was producing collapsed predictions (~0)
    because of a scale mismatch between features and targets:

        Features (X):  Scaled via StandardScaler → mean=0, std=1, range≈[-3, +3]
        Targets (y):   Raw point margins → mean=2.92, std=14.34, range=[-68, +73]

    This ~14x scale difference causes:
    1. Very large initial MSE loss (~200+) creating unstable gradients
    2. Model learns to predict near-zero to minimize loss quickly
    3. Gradient updates are dominated by outliers (blowout games)
    4. Final predictions collapse to narrow range (~±1 instead of ±15)

    Solution: Scale regression targets to mean=0, std=1 during training,
    then inverse-transform predictions back to original scale.

        Scaled targets:  mean=0, std=1, range≈[-5, +5]
        Model output:    Predicts in normalized space
        Final output:    inverse_transform() → original point margin scale

    This ensures:
    - MSE loss starts at reasonable values (~1.0)
    - Gradients are balanced across all training samples
    - Model learns full distribution of margins, not just mean

    Args:
        model: PyTorch nn.Module to train
        X: Feature matrix (already scaled via StandardScaler)
        y: Target vector (raw values for classification, raw margins for regression)
        is_classifier: True for win/loss classification, False for margin regression
        epochs: Maximum training epochs (default: 100)
        lr: Learning rate for Adam optimizer (default: 0.001)
        target_scaler: StandardScaler instance for regression targets.
                       Will be fit on training data in-place.
                       Pass None for classification (targets are already 0/1).

    Returns:
        target_scaler: The fitted scaler (for regression) to use during prediction.
                       Returns None for classification.
    """
    X_tensor = torch.FloatTensor(X)

    # Scale regression targets for stable training
    # Classification targets (0/1) don't need scaling
    if not is_classifier and target_scaler is not None:
        y_scaled = target_scaler.fit_transform(y.reshape(-1, 1)).flatten()
        y_tensor = torch.FloatTensor(y_scaled).unsqueeze(1)
    else:
        y_tensor = torch.FloatTensor(y).unsqueeze(1)

    # Temporal split for validation (80/20)
    # Important: Don't shuffle - maintain temporal order to avoid data leakage
    split_idx = int(0.8 * len(X))
    X_train, X_val = X_tensor[:split_idx], X_tensor[split_idx:]
    y_train, y_val = y_tensor[:split_idx], y_tensor[split_idx:]

    # Loss functions
    if is_classifier:
        criterion = nn.BCEWithLogitsLoss()  # Binary cross-entropy (includes sigmoid)
    else:
        criterion = nn.MSELoss()  # Mean squared error for regression

    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    # Early stopping setup
    best_val_loss = float('inf')
    best_model_state = None
    patience = 15  # Stop if no improvement for 15 epochs
    patience_counter = 0

    model.train()
    for epoch in range(epochs):
        # Forward pass
        optimizer.zero_grad()
        outputs = model(X_train)
        loss = criterion(outputs, y_train)

        # Backward pass
        loss.backward()
        optimizer.step()

        # Validation (model in eval mode for correct BatchNorm behavior)
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val)
            val_loss = criterion(val_outputs, y_val).item()
        model.train()

        # Early stopping check
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"    Early stopping at epoch {epoch+1} (best val_loss: {best_val_loss:.4f})")
                break

    # Restore best model weights
    if best_model_state is not None:
        model.load_state_dict(best_model_state)

    model.eval()

    # Return the fitted target scaler for use during prediction
    return target_scaler if not is_classifier else None


# ============================================================================
# PYTORCH WITH EMBEDDINGS - TRAINING & LOADING
# ============================================================================

def load_or_train_pytorch_embedding_models(engine):
    """
    Load pre-trained PyTorch models with player embeddings or train new ones.

    The embedding models use a different architecture that takes:
    - Team features (rolling stats, fatigue, etc.)
    - Player IDs (16 per game: 8 home + 8 away)
    - Availability mask (1 if playing, 0 if OUT)

    Returns:
        tuple: (classifier, regressor, scaler_tuple, team_feature_names,
                player_to_idx, target_scaler, n_slots, embedding_dim)
    """
    if not PYTORCH_AVAILABLE:
        raise ImportError("PyTorch not available")

    clf_path = 'models/nn_embed_classifier.pt'
    reg_path = 'models/nn_embed_regressor.pt'
    scaler_path = 'models/scaler.joblib'
    features_path = 'models/feature_names.joblib'
    config_path = 'models/nn_embed_config.joblib'

    if all(os.path.exists(p) for p in [clf_path, reg_path, scaler_path, features_path, config_path]):
        print("Loading pre-trained PyTorch embedding models...")
        scaler = joblib.load(scaler_path)
        feature_names = joblib.load(features_path)
        config = joblib.load(config_path)

        clf = NBAClassifierWithEmbeddings(
            team_feature_dim=config['team_feature_dim'],
            n_players=config['n_players'],
            embedding_dim=config['embedding_dim'],
            n_slots=config['n_slots']
        )
        clf.load_state_dict(torch.load(clf_path, weights_only=True))
        clf.eval()

        reg = NBARegressorWithEmbeddings(
            team_feature_dim=config['team_feature_dim'],
            n_players=config['n_players'],
            embedding_dim=config['embedding_dim'],
            n_slots=config['n_slots']
        )
        reg.load_state_dict(torch.load(reg_path, weights_only=True))
        reg.eval()

        return (clf, reg, scaler, config['team_feature_names'],
                config['player_to_idx'], config.get('target_scaler'),
                config['n_slots'], config['embedding_dim'])

    print("Training PyTorch models with player embeddings...")

    # Prepare training data with player IDs
    (ml_df, team_feature_names, X_team_scaled, player_ids, availability_mask,
     y_clf, y_reg, scaler_tuple, player_to_idx, n_players) = _prepare_embedding_training_data(engine)

    n_slots = 8
    embedding_dim = 16
    team_feature_dim = X_team_scaled.shape[1]

    # Train classifier
    print("  Training NN classifier with embeddings...")
    clf = NBAClassifierWithEmbeddings(
        team_feature_dim=team_feature_dim,
        n_players=n_players,
        embedding_dim=embedding_dim,
        n_slots=n_slots
    )
    _train_pytorch_embedding_model(clf, X_team_scaled, player_ids, availability_mask,
                                    y_clf.values, is_classifier=True)

    # Train regressor with target scaling
    print("  Training NN regressor with embeddings (with target scaling)...")
    reg = NBARegressorWithEmbeddings(
        team_feature_dim=team_feature_dim,
        n_players=n_players,
        embedding_dim=embedding_dim,
        n_slots=n_slots
    )
    target_scaler = StandardScaler()
    _train_pytorch_embedding_model(reg, X_team_scaled, player_ids, availability_mask,
                                    y_reg.values, is_classifier=False, target_scaler=target_scaler)

    # Save models
    os.makedirs('models', exist_ok=True)
    torch.save(clf.state_dict(), clf_path)
    torch.save(reg.state_dict(), reg_path)

    # Save scalers if not already saved
    if not os.path.exists(scaler_path):
        joblib.dump(scaler_tuple, scaler_path)
    if not os.path.exists(features_path):
        joblib.dump(team_feature_names, features_path)

    # Save config
    joblib.dump({
        'team_feature_dim': team_feature_dim,
        'team_feature_names': team_feature_names,
        'n_players': n_players,
        'embedding_dim': embedding_dim,
        'n_slots': n_slots,
        'player_to_idx': player_to_idx,
        'target_scaler': target_scaler
    }, config_path)

    print("  PyTorch embedding models saved to ./models/")
    return (clf, reg, scaler_tuple, team_feature_names, player_to_idx,
            target_scaler, n_slots, embedding_dim)


def _prepare_embedding_training_data(engine):
    """
    Prepare training data for embedding models.

    Returns team features (without player ID columns) + separate player ID array.
    """
    if os.path.exists('nba_ml_features.csv'):
        ml_df = pd.read_csv('nba_ml_features.csv')
    else:
        from data_engineering.feature_engineering import build_feature_dataset, prepare_ml_dataset
        feature_df = build_feature_dataset(engine, start_date='2020-01-01')
        ml_df, _ = prepare_ml_dataset(feature_df)
        ml_df.to_csv('nba_ml_features.csv', index=False)

    # Create player ID mapping
    player_to_idx, idx_to_player, n_players = create_player_id_mapping(engine)

    # Identify player ID columns (HOME_SLOT_1_PLAYER_ID, etc.)
    player_id_cols = [col for col in ml_df.columns if 'PLAYER_ID' in col]
    availability_cols = [col for col in ml_df.columns if '_SLOT_' in col and '_AVAILABLE' in col]

    # Sort columns to ensure consistent order: HOME_SLOT_1..8, then AWAY_SLOT_1..8
    player_id_cols = sorted([c for c in player_id_cols if 'HOME' in c]) + \
                     sorted([c for c in player_id_cols if 'AWAY' in c])
    availability_cols = sorted([c for c in availability_cols if 'HOME' in c]) + \
                        sorted([c for c in availability_cols if 'AWAY' in c])

    # Team features (everything except PLAYER_ID columns)
    team_feature_patterns = ['_L5', '_L10', 'STREAK', 'REST_DAYS', 'WIN_PCT',
                              'IS_BACK_TO_BACK', 'IS_3_IN_4_NIGHTS', 'GAMES_LAST',
                              'AVG_REST_LAST', 'ROAD_TRIP_LENGTH',
                              'PROJ_PTS_FROM_PLAYERS', 'PROJ_REB_FROM_PLAYERS', 'PROJ_AST_FROM_PLAYERS',
                              'WEIGHTED_AVG_USAGE', 'WEIGHTED_AVG_TS_PCT', 'WEIGHTED_AVG_PIE',
                              'ROSTER_DEPTH_SCORE', 'STAR_PLAYER_IMPACT', 'TOP_3_SCORER_SHARE',
                              '_SLOT_', '_AVAILABLE', '_IMPACT',
                              'TOTAL_AVAILABLE_IMPACT', 'TOTAL_MISSING_IMPACT', 'PLAYERS_OUT']

    team_feature_cols = [col for col in ml_df.columns
                          if any(p in col for p in team_feature_patterns)
                          and 'PLAYER_ID' not in col]

    # Extract features
    X_team = ml_df[team_feature_cols].copy()
    y_clf = ml_df['TARGET_WIN']
    y_reg = ml_df['TARGET_MARGIN']

    # Handle missing columns
    valid_cols = X_team.columns[X_team.notna().any()].tolist()
    X_team = X_team[valid_cols]

    # Scale team features
    imputer = SimpleImputer(strategy='median')
    scaler = StandardScaler()
    X_team_imputed = imputer.fit_transform(X_team)
    X_team_scaled = scaler.fit_transform(X_team_imputed)

    # Extract player IDs and convert to embedding indices
    if player_id_cols and all(col in ml_df.columns for col in player_id_cols):
        player_ids_raw = ml_df[player_id_cols].fillna(0).astype(int).values
        # Map NBA player IDs to embedding indices
        player_ids = np.vectorize(lambda x: player_to_idx.get(int(x), 0))(player_ids_raw)
    else:
        # No player ID columns - create zeros (all unknown players)
        print("  Warning: No player ID columns found, using zeros")
        player_ids = np.zeros((len(ml_df), 16), dtype=int)

    # Extract availability mask
    if availability_cols and all(col in ml_df.columns for col in availability_cols):
        availability_mask = ml_df[availability_cols].fillna(1.0).values
    else:
        # Default to all available
        availability_mask = np.ones((len(ml_df), 16), dtype=float)

    print(f"  Team features: {len(valid_cols)}, Player ID columns: {len(player_id_cols)}")
    print(f"  Samples: {len(ml_df)}, Unique players in mapping: {n_players}")

    return (ml_df, valid_cols, X_team_scaled, player_ids, availability_mask,
            y_clf, y_reg, (imputer, scaler), player_to_idx, n_players)


def _train_pytorch_embedding_model(model, X_team, player_ids, availability_mask, y,
                                     is_classifier=True, epochs=100, lr=0.001, target_scaler=None):
    """
    Train a PyTorch embedding model with early stopping.

    Similar to _train_pytorch_model but handles the separate inputs for embeddings.
    """
    # Convert to tensors
    X_team_tensor = torch.FloatTensor(X_team)
    player_ids_tensor = torch.LongTensor(player_ids)
    availability_tensor = torch.FloatTensor(availability_mask)

    # Handle target scaling for regression
    if not is_classifier and target_scaler is not None:
        y_scaled = target_scaler.fit_transform(y.reshape(-1, 1)).flatten()
        y_tensor = torch.FloatTensor(y_scaled).unsqueeze(1)
    else:
        y_tensor = torch.FloatTensor(y).unsqueeze(1) if not is_classifier else torch.FloatTensor(y).unsqueeze(1)

    # Train/validation split (80/20)
    n_samples = len(y)
    indices = np.random.permutation(n_samples)
    train_idx = indices[:int(0.8 * n_samples)]
    val_idx = indices[int(0.8 * n_samples):]

    X_team_train = X_team_tensor[train_idx]
    X_team_val = X_team_tensor[val_idx]
    player_ids_train = player_ids_tensor[train_idx]
    player_ids_val = player_ids_tensor[val_idx]
    avail_train = availability_tensor[train_idx]
    avail_val = availability_tensor[val_idx]
    y_train = y_tensor[train_idx]
    y_val = y_tensor[val_idx]

    # Loss and optimizer
    if is_classifier:
        criterion = nn.BCEWithLogitsLoss()
    else:
        criterion = nn.MSELoss()

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-5)

    # Training loop with early stopping
    best_val_loss = float('inf')
    best_model_state = None
    patience = 15
    patience_counter = 0

    model.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        outputs = model(X_team_train, player_ids_train, avail_train)
        loss = criterion(outputs, y_train)

        loss.backward()
        optimizer.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_outputs = model(X_team_val, player_ids_val, avail_val)
            val_loss = criterion(val_outputs, y_val).item()
        model.train()

        # Early stopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_model_state = model.state_dict().copy()
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print(f"    Early stopping at epoch {epoch+1} (best val_loss: {best_val_loss:.4f})")
                break

    if best_model_state is not None:
        model.load_state_dict(best_model_state)

    model.eval()
    return target_scaler if not is_classifier else None


def predict_with_pytorch_embeddings(clf, reg, scaler_tuple, team_feature_names, player_to_idx,
                                     matchup_features: dict, n_samples=100, skip_shap=False,
                                     target_scaler=None, n_slots=8):
    """
    Make predictions using PyTorch models with player embeddings.

    Args:
        clf: NBAClassifierWithEmbeddings model
        reg: NBARegressorWithEmbeddings model
        scaler_tuple: (imputer, scaler) for team features
        team_feature_names: List of team feature column names
        player_to_idx: Dict mapping NBA player_id -> embedding index
        matchup_features: Dict of feature values (including _slot_to_player)
        n_samples: Number of MC Dropout samples
        skip_shap: Skip SHAP calculation
        target_scaler: StandardScaler for inverse-transforming margins
        n_slots: Number of player slots per team (default: 8)

    Returns:
        dict with predictions and uncertainty estimates
    """
    imputer, scaler = scaler_tuple

    # Separate team features from player features
    team_features = {k: v for k, v in matchup_features.items()
                     if not k.startswith('_') and 'PLAYER_ID' not in k}

    # Prepare team features
    X_team = pd.DataFrame([team_features])
    for col in team_feature_names:
        if col not in X_team.columns:
            X_team[col] = np.nan
    X_team = X_team[team_feature_names]

    X_team_imputed = imputer.transform(X_team)
    X_team_scaled = scaler.transform(X_team_imputed)
    X_team_tensor = torch.FloatTensor(X_team_scaled)

    # Extract player IDs and convert to embedding indices
    player_ids = []
    availability = []

    for side in ['HOME', 'AWAY']:
        for slot in range(1, n_slots + 1):
            player_id_key = f'{side}_SLOT_{slot}_PLAYER_ID'
            avail_key = f'{side}_SLOT_{slot}_AVAILABLE'

            nba_player_id = matchup_features.get(player_id_key, 0)
            embed_idx = player_to_idx.get(int(nba_player_id), 0)
            player_ids.append(embed_idx)

            avail = matchup_features.get(avail_key, 1.0)
            availability.append(avail)

    player_ids_tensor = torch.LongTensor([player_ids])
    availability_tensor = torch.FloatTensor([availability])

    # MC Dropout inference for classifier
    clf.train()  # Enable dropout
    enable_dropout(clf)  # Keep BatchNorm in eval mode

    win_probs = []
    for _ in range(n_samples):
        with torch.no_grad():
            logits = clf(X_team_tensor, player_ids_tensor, availability_tensor)
            prob = torch.sigmoid(logits).item()
            win_probs.append(prob)

    win_prob_classifier = np.mean(win_probs)

    # MC Dropout inference for regressor
    reg.train()
    enable_dropout(reg)

    margin_samples = []
    for _ in range(n_samples):
        with torch.no_grad():
            pred = reg(X_team_tensor, player_ids_tensor, availability_tensor)
            margin_samples.append(pred.item())

    margin_samples = np.array(margin_samples)

    # Inverse-transform if target was scaled during training
    if target_scaler is not None:
        margin_samples = target_scaler.inverse_transform(margin_samples.reshape(-1, 1)).flatten()

    margin_mean = np.mean(margin_samples)
    margin_std = np.std(margin_samples)

    # Derive win probability from margin samples
    win_prob = np.mean(margin_samples > 0)

    # SHAP is more complex with embeddings - skip for now
    # (Would need custom explainer for embedding inputs)
    shap_values = None
    shap_feature_importance = {}

    # Get slot_to_player mapping
    slot_to_player = matchup_features.get('_slot_to_player', None)

    return {
        'win_prob': win_prob,
        'win_prob_classifier': win_prob_classifier,
        'win_prob_classifier_std': np.std(win_probs),
        'margin_mean': margin_mean,
        'margin_std': margin_std,
        'margin_samples': margin_samples,
        'model': 'Neural Network with Embeddings (MC Dropout)',
        'shap_values': shap_values,
        'shap_feature_importance': shap_feature_importance,
        'X_scaled': X_team_scaled,
        'feature_names': team_feature_names,
        'slot_to_player': slot_to_player
    }


# ============================================================================
# PREDICTION FUNCTIONS
# ============================================================================

def predict_with_rf(clf, reg, scaler_tuple, feature_names, matchup_features: dict, skip_shap: bool = False):
    """Make predictions with Random Forest (uncertainty from tree ensemble)."""
    imputer, scaler = scaler_tuple

    X = pd.DataFrame([matchup_features])
    for col in feature_names:
        if col not in X.columns:
            X[col] = np.nan
    X = X[feature_names]

    X_imputed = imputer.transform(X)
    X_scaled = scaler.transform(X_imputed)

    # Classifier probability (reference)
    win_prob_classifier = clf.predict_proba(X_scaled)[0][1]

    # Margin samples from tree ensemble (100 trees)
    tree_predictions = np.array([tree.predict(X_scaled)[0] for tree in reg.estimators_])
    margin_mean = np.mean(tree_predictions)
    margin_std = np.std(tree_predictions)

    # PRIMARY: Derive win probability from margin samples
    # P(win) = proportion of margin samples where home team wins (margin > 0)
    win_prob = np.mean(tree_predictions > 0)

    # Calculate SHAP values for feature importance (unless skipped)
    shap_values = None
    shap_feature_importance = {}

    if SHAP_AVAILABLE and not skip_shap:
        try:
            # Use TreeExplainer for Random Forest (fast and exact)
            explainer = shap.TreeExplainer(reg)
            shap_vals = explainer.shap_values(X_scaled)

            # Get SHAP values for this prediction
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[0]  # Handle multi-output case

            shap_values = shap_vals[0] if len(shap_vals.shape) > 1 else shap_vals

            # Create feature importance dict (feature_name -> SHAP value)
            for i, feat in enumerate(feature_names):
                shap_feature_importance[feat] = float(shap_values[i])

        except Exception as e:
            print(f"Warning: SHAP calculation failed: {e}")

    # Extract slot_to_player mapping if present (for SHAP interpretation)
    slot_to_player = matchup_features.get('_slot_to_player', None)

    return {
        'win_prob': win_prob,                        # PRIMARY: derived from margin samples
        'win_prob_classifier': win_prob_classifier,  # REFERENCE: from classifier
        'margin_mean': margin_mean,
        'margin_std': margin_std,
        'margin_samples': tree_predictions,
        'model': 'Random Forest',
        'shap_values': shap_values,
        'shap_feature_importance': shap_feature_importance,
        'X_scaled': X_scaled,
        'feature_names': feature_names,
        'slot_to_player': slot_to_player  # For SHAP player name resolution
    }


def enable_dropout(model):
    """Enable dropout layers while keeping BatchNorm in eval mode."""
    for module in model.modules():
        if isinstance(module, torch.nn.Dropout):
            module.train()


def predict_with_pytorch(clf, reg, scaler_tuple, feature_names, matchup_features: dict,
                          n_samples=100, skip_shap: bool = False, target_scaler=None):
    """
    Make predictions with PyTorch using Monte Carlo Dropout.

    Monte Carlo Dropout: Run inference multiple times with dropout ENABLED
    to get a distribution of predictions, which estimates uncertainty.

    Note: We keep BatchNorm in eval mode (it doesn't work with batch_size=1 in train mode)
    but enable Dropout layers for uncertainty estimation.

    Args:
        clf: NBAClassifier model
        reg: NBARegressor model
        scaler_tuple: (imputer, scaler) for feature preprocessing
        feature_names: List of feature column names
        matchup_features: Dict of feature values for this matchup
        n_samples: Number of MC Dropout samples (default: 100)
        skip_shap: Skip SHAP calculation for speed
        target_scaler: StandardScaler used during training to normalize margins.
                       If provided, predictions will be inverse-transformed to
                       original scale (actual point margins).
                       If None, predictions are in normalized space.

    Returns:
        dict with predictions and uncertainty estimates
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

            # Regression (output is in normalized space if target_scaler was used)
            margin = reg(X_tensor).item()
            margin_samples.append(margin)

    # Fully back to eval mode
    clf.eval()
    reg.eval()

    # Convert to numpy array for calculations
    margin_samples = np.array(margin_samples)

    # Inverse-transform margin samples to original scale (actual point margins)
    # Without this, predictions would be in normalized space (mean=0, std=1)
    if target_scaler is not None:
        margin_samples = target_scaler.inverse_transform(
            margin_samples.reshape(-1, 1)
        ).flatten()

    # Classifier probability (reference) - average of MC Dropout samples
    win_prob_classifier = np.mean(win_probs)

    # Margin statistics (now in actual points, not normalized)
    margin_mean = np.mean(margin_samples)
    margin_std = np.std(margin_samples)

    # PRIMARY: Derive win probability from margin samples
    # P(win) = proportion of margin samples where home team wins (margin > 0)
    win_prob = np.mean(margin_samples > 0)

    # Calculate SHAP values for feature importance (unless skipped)
    shap_values = None
    shap_feature_importance = {}

    if SHAP_AVAILABLE and not skip_shap:
        try:
            # For PyTorch, use GradientExplainer (works with any differentiable model)
            # We need a background dataset - use the current sample as a simple baseline
            reg.eval()  # Make sure dropout is off for SHAP
            background = X_tensor
            explainer = shap.GradientExplainer(reg, background)
            shap_vals = explainer.shap_values(X_tensor)

            # Get SHAP values for this prediction
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[0]

            shap_values = shap_vals[0] if len(shap_vals.shape) > 1 else shap_vals

            # Create feature importance dict
            for i, feat in enumerate(feature_names):
                shap_feature_importance[feat] = float(shap_values[i])

        except Exception as e:
            print(f"Warning: SHAP calculation for NN failed: {e}")
            # Fallback: use gradient-based importance
            try:
                reg.eval()
                X_tensor_grad = X_tensor.clone().requires_grad_(True)
                output = reg(X_tensor_grad)
                output.backward()

                # Use gradient * input as feature importance
                importance = (X_tensor_grad.grad * X_tensor_grad).detach().numpy()[0]
                for i, feat in enumerate(feature_names):
                    shap_feature_importance[feat] = float(importance[i])

            except Exception as e2:
                print(f"Warning: Gradient-based importance also failed: {e2}")

    # Extract slot_to_player mapping if present (for SHAP interpretation)
    slot_to_player = matchup_features.get('_slot_to_player', None)

    return {
        'win_prob': win_prob,                        # PRIMARY: derived from margin samples
        'win_prob_classifier': win_prob_classifier,  # REFERENCE: from classifier
        'win_prob_classifier_std': np.std(win_probs),
        'margin_mean': margin_mean,
        'margin_std': margin_std,
        'margin_samples': margin_samples,  # Already numpy array
        'model': 'Neural Network (MC Dropout)',
        'shap_values': shap_values,
        'shap_feature_importance': shap_feature_importance,
        'X_scaled': X_scaled,
        'feature_names': feature_names,
        'slot_to_player': slot_to_player  # For SHAP player name resolution
    }


# Alias for backward compatibility
def load_or_train_models(engine):
    """Default to Random Forest models."""
    return load_or_train_rf_models(engine)


def predict_with_uncertainty(clf, reg, scaler_tuple, feature_names, matchup_features: dict):
    """Default to Random Forest prediction."""
    return predict_with_rf(clf, reg, scaler_tuple, feature_names, matchup_features)


# ============================================================================
# SHAP FEATURE IMPORTANCE HELPERS
# ============================================================================

def get_top_shap_features(shap_importance: dict, top_n: int = 10, slot_to_player: dict = None) -> list:
    """
    Get top N features by absolute SHAP value.

    Args:
        shap_importance: Dict of feature_name -> SHAP value
        top_n: Number of top features to return
        slot_to_player: Optional mapping of slot -> player info for player slot features
                        Format: {'HOME': {1: {'player_name': 'LeBron James', ...}, ...}, 'AWAY': {...}}

    Returns list of tuples: [(feature_name, shap_value, impact_description), ...]
    """
    if not shap_importance:
        return []

    # Sort by absolute value, descending
    sorted_features = sorted(shap_importance.items(), key=lambda x: abs(x[1]), reverse=True)

    results = []
    for feat, val in sorted_features[:top_n]:
        # Parse feature name to create human-readable description
        impact = format_feature_impact(feat, val, slot_to_player)
        results.append((feat, val, impact))

    return results


def format_feature_impact(feature_name: str, shap_value: float, slot_to_player: dict = None) -> str:
    """
    Convert feature name and SHAP value into human-readable impact description.

    Example:
        DIFF_netRating_L10: +2.3 -> "Home team has +2.3 better net rating (L10)"
        AWAY_IS_BACK_TO_BACK: -1.2 -> "Away team on back-to-back (-1.2 pts)"
        HOME_SLOT_1_AVAILABLE: -6.9 -> "LeBron James OUT (-6.9 pts)"

    Args:
        feature_name: The feature name from the model
        shap_value: The SHAP value for this feature
        slot_to_player: Optional mapping for slot features:
                        {'HOME': {1: {'player_name': 'LeBron James', 'available': False}, ...}, ...}
    """
    import re

    direction = "Home" if shap_value > 0 else "Away"
    abs_val = abs(shap_value)

    # Handle player slot features specially
    # Match patterns like HOME_SLOT_1_AVAILABLE, AWAY_SLOT_3_IMPACT
    slot_match = re.match(r'(HOME|AWAY)_SLOT_(\d+)_(AVAILABLE|IMPACT)', feature_name)
    if slot_match and slot_to_player:
        side = slot_match.group(1)  # HOME or AWAY
        slot_num = int(slot_match.group(2))
        feature_type = slot_match.group(3)  # AVAILABLE or IMPACT

        # Look up player name
        player_info = slot_to_player.get(side, {}).get(slot_num, {})
        player_name = player_info.get('player_name', f'Slot {slot_num} player')
        is_available = player_info.get('available', True)

        team_label = side.lower().capitalize()

        if feature_type == 'AVAILABLE':
            if is_available:
                # Player is playing - positive SHAP means they help their team
                if (side == 'HOME' and shap_value > 0) or (side == 'AWAY' and shap_value < 0):
                    desc = f"{player_name} playing (helps {team_label})"
                else:
                    desc = f"{player_name} playing"
            else:
                # Player is OUT - this is the key use case
                desc = f"{player_name} OUT"
        else:  # IMPACT
            desc = f"{player_name} impact factor"

        return f"{desc} ({shap_value:+.2f} pts)"

    # Handle aggregate slot features
    if 'TOTAL_AVAILABLE_IMPACT' in feature_name:
        side = 'Home' if feature_name.startswith('HOME') else ('Away' if feature_name.startswith('AWAY') else 'Diff')
        if side == 'Diff':
            desc = "Roster strength advantage" if shap_value > 0 else "Roster strength disadvantage"
        else:
            desc = f"{side} available roster strength"
        return f"{desc} ({shap_value:+.2f} pts)"

    if 'TOTAL_MISSING_IMPACT' in feature_name:
        side = 'Home' if feature_name.startswith('HOME') else ('Away' if feature_name.startswith('AWAY') else 'Diff')
        desc = f"{side} injuries impact"
        return f"{desc} ({shap_value:+.2f} pts)"

    if 'PLAYERS_OUT' in feature_name:
        side = 'Home' if feature_name.startswith('HOME') else 'Away'
        desc = f"{side} players missing"
        return f"{desc} ({shap_value:+.2f} pts)"

    # Parse standard feature names
    if feature_name.startswith('DIFF_'):
        stat_name = feature_name.replace('DIFF_', '').replace('_L5', '').replace('_L10', '')
        window = 'L5' if '_L5' in feature_name else ('L10' if '_L10' in feature_name else '')

        if shap_value > 0:
            desc = f"Home team advantage in {stat_name}"
        else:
            desc = f"Away team advantage in {stat_name}"

        if window:
            desc += f" ({window})"

    elif feature_name.startswith('HOME_'):
        stat_name = feature_name.replace('HOME_', '').replace('_L5', '').replace('_L10', '')
        window = 'L5' if '_L5' in feature_name else ('L10' if '_L10' in feature_name else '')

        if 'IS_BACK_TO_BACK' in feature_name:
            desc = "Home team on back-to-back" if shap_value > 0 else "Home team NOT on back-to-back helps"
        elif 'REST_DAYS' in feature_name:
            desc = f"Home team rest days impact"
        else:
            desc = f"Home {stat_name}"
            if window:
                desc += f" ({window})"

    elif feature_name.startswith('AWAY_'):
        stat_name = feature_name.replace('AWAY_', '').replace('_L5', '').replace('_L10', '')
        window = 'L5' if '_L5' in feature_name else ('L10' if '_L10' in feature_name else '')

        if 'IS_BACK_TO_BACK' in feature_name:
            desc = "Away team on back-to-back" if shap_value < 0 else "Away team NOT on back-to-back helps"
        elif 'REST_DAYS' in feature_name:
            desc = f"Away team rest days impact"
        else:
            desc = f"Away {stat_name}"
            if window:
                desc += f" ({window})"
    else:
        desc = feature_name

    return f"{desc} ({shap_value:+.2f} pts)"


def print_shap_explanation(home_team: str, away_team: str, prediction: dict, top_n: int = 10):
    """
    Print SHAP-based explanation for a prediction.

    If the prediction contains slot_to_player mapping, player slot features
    will be displayed with actual player names (e.g., "LeBron James OUT: -6.9 pts").
    """
    if 'shap_feature_importance' not in prediction or not prediction['shap_feature_importance']:
        return

    print(f"\n  Top {top_n} factors driving this prediction:")

    # Get slot_to_player mapping if available (for player name resolution)
    slot_to_player = prediction.get('slot_to_player', None)

    top_features = get_top_shap_features(
        prediction['shap_feature_importance'],
        top_n,
        slot_to_player=slot_to_player
    )

    for i, (feat, shap_val, impact_desc) in enumerate(top_features, 1):
        # Color code: positive = helps home team, negative = helps away team
        marker = "+" if shap_val > 0 else "-"
        print(f"    {i:2d}. {marker} {impact_desc}")


# ============================================================================
# VISUALIZATION
# ============================================================================

def plot_prediction_histograms(predictions: list, game_date: str, save_path: str = None):
    """
    Create histogram visualizations for game predictions.

    DEPRECATED: Use plot_model_comparison() for side-by-side RF/NN visualization.
    This function is kept for backward compatibility with single-model predictions.
    """
    # Redirect to new comparison plot if we have both models
    plot_model_comparison(predictions, [], game_date, save_path)


def plot_model_comparison(rf_predictions: list, nn_predictions: list, game_date: str, save_path: str = None):
    """
    Create side-by-side visualization comparing Random Forest and Neural Network predictions.

    Layout per game (1 row):
    - Col 1: Win Probability bars (RF left, NN right) with agreement badge
    - Col 2: RF Margin Distribution histogram
    - Col 3: NN Margin Distribution histogram
    - Col 4: Full Injury Report (team, player, status, impact)
    - Col 5: Top SHAP Feature Importance (key factors)

    Visual conventions:
    - Blue (#3498db) = Home team (always top bar)
    - Red (#e74c3c) = Away team (always bottom bar)
    - Green dashed line = Predicted margin
    - Red dashed line = Even (0)
    - Team codes annotated on histogram near the even line
    """
    # Handle case where only one model's predictions are provided
    if not rf_predictions and not nn_predictions:
        print("No predictions to visualize")
        return

    # Use whichever predictions are available to get game list
    base_predictions = rf_predictions if rf_predictions else nn_predictions
    n_games = len(base_predictions)

    if n_games == 0:
        print("No games to visualize")
        return

    # Create figure: 5 columns (Probabilities, RF Histogram, NN Histogram, Injury Report, SHAP)
    fig, axes = plt.subplots(n_games, 5, figsize=(26, 4 * n_games))
    if n_games == 1:
        axes = axes.reshape(1, -1)

    fig.suptitle(f'NBA Game Predictions for {game_date}\nRandom Forest vs Neural Network',
                 fontsize=14, fontweight='bold')

    # Color scheme
    HOME_COLOR = '#3498db'  # Blue for home
    AWAY_COLOR = '#e74c3c'  # Red for away

    for i in range(n_games):
        # Get predictions for this game (may be None if model not available)
        rf_pred = rf_predictions[i] if rf_predictions and i < len(rf_predictions) else None
        nn_pred = nn_predictions[i] if nn_predictions and i < len(nn_predictions) else None

        # Get team names from whichever prediction is available
        pred = rf_pred or nn_pred
        home = pred['home_team']
        away = pred['away_team']

        # Determine if models agree on winner
        rf_pick = None
        nn_pick = None
        if rf_pred:
            rf_pick = home if rf_pred['win_prob'] > 0.5 else away
        if nn_pred:
            nn_pick = home if nn_pred['win_prob'] > 0.5 else away

        models_agree = (rf_pick == nn_pick) if (rf_pick and nn_pick) else None

        # =====================================================================
        # Column 1: Win Probability Comparison (side-by-side bars)
        # =====================================================================
        ax1 = axes[i, 0]

        # Bar positions: Home on top (y=1), Away on bottom (y=0)
        y_positions = [0, 1]  # [away, home]
        bar_height = 0.35

        # RF bars (left side of each row)
        if rf_pred:
            rf_home_prob = rf_pred['win_prob']
            rf_away_prob = 1 - rf_home_prob
            ax1.barh([y - bar_height/2 for y in y_positions],
                    [rf_away_prob, rf_home_prob],
                    height=bar_height,
                    color=[AWAY_COLOR, HOME_COLOR],
                    alpha=0.8, label='RF',
                    edgecolor='black', linewidth=0.5)
            # Add probability labels
            ax1.text(rf_away_prob + 0.02, 0 - bar_height/2, f'{rf_away_prob:.0%}',
                    va='center', fontsize=9, fontweight='bold')
            ax1.text(rf_home_prob + 0.02, 1 - bar_height/2, f'{rf_home_prob:.0%}',
                    va='center', fontsize=9, fontweight='bold')

        # NN bars (right side of each row)
        if nn_pred:
            nn_home_prob = nn_pred['win_prob']
            nn_away_prob = 1 - nn_home_prob
            ax1.barh([y + bar_height/2 for y in y_positions],
                    [nn_away_prob, nn_home_prob],
                    height=bar_height,
                    color=[AWAY_COLOR, HOME_COLOR],
                    alpha=0.5, label='NN',
                    edgecolor='black', linewidth=0.5, hatch='///')
            # Add probability labels
            ax1.text(nn_away_prob + 0.02, 0 + bar_height/2, f'{nn_away_prob:.0%}',
                    va='center', fontsize=9, style='italic')
            ax1.text(nn_home_prob + 0.02, 1 + bar_height/2, f'{nn_home_prob:.0%}',
                    va='center', fontsize=9, style='italic')

        ax1.set_xlim(0, 1.15)
        ax1.set_ylim(-0.5, 1.5)
        ax1.set_yticks(y_positions)
        ax1.set_yticklabels([f'{away} (AWAY)', f'{home} (HOME)'], fontsize=10)
        ax1.set_xlabel('Win Probability')
        ax1.axvline(x=0.5, color='gray', linestyle='--', alpha=0.7, linewidth=1.5)

        # Title with agreement badge
        if models_agree is not None:
            agree_text = 'AGREE' if models_agree else 'DISAGREE'
            agree_color = '#27ae60' if models_agree else '#e74c3c'
            title = f'{away} @ {home}'
            ax1.set_title(title, fontsize=11, fontweight='bold')
            # Add agreement badge
            ax1.text(0.98, 0.98, agree_text, transform=ax1.transAxes,
                    fontsize=10, fontweight='bold', color='white',
                    ha='right', va='top',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor=agree_color, alpha=0.9))
        else:
            ax1.set_title(f'{away} @ {home}', fontsize=11, fontweight='bold')

        # Legend for RF vs NN
        if rf_pred and nn_pred:
            ax1.legend(loc='lower right', fontsize=8)

        # =====================================================================
        # Column 2: RF Margin Distribution
        # =====================================================================
        ax2 = axes[i, 1]
        if rf_pred:
            margin_samples = rf_pred['margin_samples']
            margin_mean = np.mean(margin_samples)
            margin_std = np.std(margin_samples)

            ax2.hist(margin_samples, bins=25, color=HOME_COLOR, alpha=0.7, edgecolor='black')

            # Even line (x=0) with team annotations
            ax2.axvline(x=0, color='black', linestyle='--', linewidth=2)

            # Predicted margin line
            ax2.axvline(x=margin_mean, color='#27ae60', linestyle='-', linewidth=2.5,
                       label=f'Pred: {margin_mean:+.1f}')

            # Get y-axis limits for annotation positioning
            y_max = ax2.get_ylim()[1]

            # Team code annotations on either side of even line
            ax2.text(-2, y_max * 0.92, f'← {away}\n    wins', fontsize=10,
                    ha='right', va='top', fontweight='bold', color=AWAY_COLOR)
            ax2.text(2, y_max * 0.92, f'{home} →\nwins    ', fontsize=10,
                    ha='left', va='top', fontweight='bold', color=HOME_COLOR)

            ax2.set_xlabel('Point Margin')
            ax2.set_ylabel('Frequency')

            title_text = f'Random Forest\nMargin: {margin_mean:+.1f} ± {margin_std:.1f}'
            ax2.set_title(title_text, fontsize=10, fontweight='bold')
            ax2.legend(loc='upper right', fontsize=8)
        else:
            ax2.text(0.5, 0.5, 'RF Not Available', transform=ax2.transAxes,
                    ha='center', va='center', fontsize=12, color='gray')
            ax2.set_title('Random Forest', fontsize=10)

        # =====================================================================
        # Column 3: NN Margin Distribution
        # =====================================================================
        ax3 = axes[i, 2]
        if nn_pred:
            margin_samples = nn_pred['margin_samples']
            margin_mean = np.mean(margin_samples)
            margin_std = np.std(margin_samples)

            ax3.hist(margin_samples, bins=25, color=HOME_COLOR, alpha=0.7, edgecolor='black')

            # Even line (x=0) with team annotations
            ax3.axvline(x=0, color='black', linestyle='--', linewidth=2)

            # Predicted margin line
            ax3.axvline(x=margin_mean, color='#27ae60', linestyle='-', linewidth=2.5,
                       label=f'Pred: {margin_mean:+.1f}')

            # Get y-axis limits for annotation positioning
            y_max = ax3.get_ylim()[1]

            # Team code annotations on either side of even line
            ax3.text(-2, y_max * 0.92, f'← {away}\n    wins', fontsize=10,
                    ha='right', va='top', fontweight='bold', color=AWAY_COLOR)
            ax3.text(2, y_max * 0.92, f'{home} →\nwins    ', fontsize=10,
                    ha='left', va='top', fontweight='bold', color=HOME_COLOR)

            ax3.set_xlabel('Point Margin')
            ax3.set_ylabel('Frequency')

            title_text = f'Neural Network\nMargin: {margin_mean:+.1f} ± {margin_std:.1f}'
            ax3.set_title(title_text, fontsize=10, fontweight='bold')
            ax3.legend(loc='upper right', fontsize=8)
        else:
            ax3.text(0.5, 0.5, 'NN Not Available', transform=ax3.transAxes,
                    ha='center', va='center', fontsize=12, color='gray')
            ax3.set_title('Neural Network', fontsize=10)

        # =====================================================================
        # Column 4: Full Injury Report
        # =====================================================================
        ax4 = axes[i, 3]
        ax4.axis('off')
        ax4.set_title('Injury Report', fontsize=10, fontweight='bold')

        injury_details = pred.get('injury_details', [])
        if injury_details:
            # Group injuries by team
            home_injuries = [d for d in injury_details if d['team'] == 'home']
            away_injuries = [d for d in injury_details if d['team'] == 'away']

            # Build table text with [TEAM] Player (status): impact format
            # NO TRUNCATION - show ALL injuries
            table_lines = []
            for d in home_injuries:
                status = d.get('status', 'out').lower()
                table_lines.append(f"[{home}] {d['name']} ({status}): {d['impact']:+.1f}")

            for d in away_injuries:
                status = d.get('status', 'out').lower()
                table_lines.append(f"[{away}] {d['name']} ({status}): {d['impact']:+.1f}")

            if table_lines:
                injury_text = '\n'.join(table_lines)
                ax4.text(0.05, 0.95, injury_text, transform=ax4.transAxes,
                        fontsize=9, fontfamily='monospace',
                        va='top', ha='left',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='#fff3cd', alpha=0.9))
        else:
            ax4.text(0.5, 0.5, 'No Injuries Reported', transform=ax4.transAxes,
                    ha='center', va='center', fontsize=11, color='gray')

        # =====================================================================
        # Column 5: SHAP Feature Importance (Top factors) - Bar Chart
        # =====================================================================
        ax5 = axes[i, 4]
        ax5.set_title('Key Factors (SHAP)', fontsize=10, fontweight='bold')

        # Use RF prediction's SHAP data if available
        shap_importance = rf_pred.get('shap_feature_importance', {}) if rf_pred else {}
        if shap_importance:
            # Sort by absolute value and get top 8 features
            sorted_features = sorted(shap_importance.items(), key=lambda x: abs(x[1]), reverse=True)[:8]

            # Reverse for plotting (top feature at top)
            features = [f[0] for f in sorted_features][::-1]
            values = [f[1] for f in sorted_features][::-1]

            # Shorten feature names for display
            short_names = []
            for feat in features:
                if len(feat) > 30:
                    short_names.append(feat[:30] + '...')
                else:
                    short_names.append(feat)

            # Create horizontal bar chart
            colors = [HOME_COLOR if v > 0 else AWAY_COLOR for v in values]
            y_pos = range(len(short_names))

            ax5.barh(y_pos, values, color=colors, alpha=0.8, height=0.7)
            ax5.set_yticks(y_pos)
            ax5.set_yticklabels(short_names, fontsize=7)
            ax5.axvline(x=0, color='black', linewidth=0.5, linestyle='-')
            ax5.set_xlabel('Impact (pts)', fontsize=8)

            # Add legend
            ax5.text(0.02, 0.02, f'← {away}', transform=ax5.transAxes, fontsize=7, color=AWAY_COLOR, ha='left')
            ax5.text(0.98, 0.02, f'{home} →', transform=ax5.transAxes, fontsize=7, color=HOME_COLOR, ha='right')

            # Clean up
            ax5.spines['top'].set_visible(False)
            ax5.spines['right'].set_visible(False)
        else:
            ax5.axis('off')
            ax5.text(0.5, 0.5, 'SHAP Not Available', transform=ax5.transAxes,
                    ha='center', va='center', fontsize=11, color='gray')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Plot saved to {save_path}")

    plt.show()


def print_predictions_table(predictions: list, game_date: str, model_name: str = ""):
    """Print predictions in a formatted table with SHAP explanations."""
    print("\n" + "=" * 95)
    print(f"NBA GAME PREDICTIONS FOR {game_date}" + (f" ({model_name})" if model_name else ""))
    print("=" * 95)

    if not predictions:
        print("No games found for this date.")
        return

    print(f"\n{'Matchup':<25} {'Pick':<10} {'P(Win)':>10} {'Clf Ref':>10} {'Margin':>10} {'Uncert':>10}")
    print("-" * 95)

    for pred in predictions:
        home = pred['home_team']
        away = pred['away_team']
        matchup = f"{away} @ {home}"

        win_prob = pred['win_prob']  # Primary: derived from margin samples
        win_prob_clf = pred.get('win_prob_classifier', win_prob)  # Reference: from classifier
        margin = pred['margin_mean']
        margin_std = pred['margin_std']

        pick = home if win_prob > 0.5 else away

        margin_str = f"{margin:+.1f} pts"
        uncertainty_str = f"+/-{margin_std:.1f}"

        print(f"{matchup:<25} {pick:<10} {win_prob:>9.1%} {win_prob_clf:>9.1%} {margin_str:>10} {uncertainty_str:>10}")

        # Show injury info for context (impacts are learned in model via slot features)
        if 'injury_details' in pred and pred['injury_details']:
            print(f"  >> Players OUT (incorporated via slot features):")
            for d in pred['injury_details']:
                team_label = home if d['team'] == 'home' else away
                print(f"     {d['name']} ({team_label}): historical impact {d['impact']:+.1f} pts [{d['confidence']}]")

        # Print SHAP explanation if available
        if SHAP_AVAILABLE:
            print_shap_explanation(home, away, pred, top_n=10)
            print()  # Blank line between games

    print("-" * 95)
    print("P(Win) = derived from margin samples | Clf Ref = classifier reference")


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
    print("Win% = P(margin > 0) derived from Monte Carlo margin samples")


def parse_injuries_for_game(engine, injury_list, home_team_id, away_team_id, game_date):
    """
    Parse injury names and match them to teams.

    Args:
        engine: SQLAlchemy engine
        injury_list: List of player names (strings) OR list of dicts with 'name', 'status',
                     and optionally 'team_side' ('home' or 'away') keys
        home_team_id: Home team ID
        away_team_id: Away team ID
        game_date: Game date string

    Returns:
        dict with 'home_injuries' and 'away_injuries' as lists of player_ids,
        and 'injury_details' with full info including status.
    """
    if not PLAYER_IMPACT_AVAILABLE or not injury_list:
        return {'home_injuries': [], 'away_injuries': [], 'injury_details': []}

    home_injuries = []
    away_injuries = []
    injury_details = []

    for item in injury_list:
        # Handle both string names and dict format
        if isinstance(item, dict):
            name = item.get('name', '')
            status = item.get('status', 'out')
            # Use pre-determined team_side if available (from auto-fetched injuries)
            known_team_side = item.get('team_side')  # 'home', 'away', or None
        else:
            name = item
            status = 'out'
            known_team_side = None

        if not name:
            continue

        # If we know which team this player is on, use that directly
        if known_team_side == 'home':
            team_id = home_team_id
            player_id = get_player_id_by_name(engine, name, team_id)
            if player_id:
                home_injuries.append(player_id)
                impact = get_player_historical_impact(engine, player_id, team_id, game_date)
                injury_details.append({
                    'name': name,
                    'team': 'home',
                    'player_id': player_id,
                    'impact': impact['impact'],
                    'confidence': impact['confidence'],
                    'method': impact['method'],
                    'status': status
                })
            else:
                print(f"  Warning: Could not find player '{name}' on home team")
            continue

        if known_team_side == 'away':
            team_id = away_team_id
            player_id = get_player_id_by_name(engine, name, team_id)
            if player_id:
                away_injuries.append(player_id)
                impact = get_player_historical_impact(engine, player_id, team_id, game_date)
                injury_details.append({
                    'name': name,
                    'team': 'away',
                    'player_id': player_id,
                    'impact': impact['impact'],
                    'confidence': impact['confidence'],
                    'method': impact['method'],
                    'status': status
                })
            else:
                print(f"  Warning: Could not find player '{name}' on away team")
            continue

        # Fallback: Try to find player on home team first (for manual --injuries flag)
        player_id = get_player_id_by_name(engine, name, home_team_id)
        if player_id:
            home_injuries.append(player_id)
            impact = get_player_historical_impact(engine, player_id, home_team_id, game_date)
            injury_details.append({
                'name': name,
                'team': 'home',
                'player_id': player_id,
                'impact': impact['impact'],
                'confidence': impact['confidence'],
                'method': impact['method'],
                'status': status
            })
            continue

        # Try away team
        player_id = get_player_id_by_name(engine, name, away_team_id)
        if player_id:
            away_injuries.append(player_id)
            impact = get_player_historical_impact(engine, player_id, away_team_id, game_date)
            injury_details.append({
                'name': name,
                'team': 'away',
                'player_id': player_id,
                'impact': impact['impact'],
                'confidence': impact['confidence'],
                'method': impact['method'],
                'status': status
            })
            continue

        # Try without team filter
        player_id = get_player_id_by_name(engine, name)
        if player_id:
            # Couldn't determine team, skip
            print(f"  Warning: Found {name} but couldn't determine their team")
        else:
            print(f"  Warning: Could not find player '{name}'")

    return {
        'home_injuries': home_injuries,
        'away_injuries': away_injuries,
        'injury_details': injury_details
    }


def apply_injury_adjustments(result, home_impact, away_impact):
    """
    Adjust prediction result based on injury impacts.

    This shifts ALL margin samples by the injury adjustment, then recomputes
    both margin and win probability from the adjusted samples. This ensures
    consistency between margin and probability after injury adjustment.

    Args:
        result: Prediction result dict with 'margin_mean', 'win_prob', 'margin_samples'
        home_impact: Total impact of home team injuries (positive = team worse without)
        away_impact: Total impact of away team injuries (positive = team worse without)

    Returns:
        Adjusted result dict with consistent margin and probability
    """
    # Net impact on margin (from home perspective)
    # If home player is out, margin goes down by their impact
    # If away player is out, margin goes up by their impact
    net_adjustment = away_impact - home_impact

    # Store original values
    result['original_margin'] = result['margin_mean']
    result['original_win_prob'] = result['win_prob']
    original_samples = result['margin_samples'].copy()

    # Shift ALL margin samples by the injury adjustment
    adjusted_samples = original_samples + net_adjustment

    # Recompute statistics from adjusted samples
    result['margin_samples'] = adjusted_samples
    result['margin_mean'] = np.mean(adjusted_samples)
    result['margin_std'] = np.std(adjusted_samples)

    # Recompute win probability from adjusted samples
    # This ensures consistency: P(win) = P(margin > 0)
    result['win_prob'] = np.mean(adjusted_samples > 0)

    # Store adjustment details
    result['injury_adjustment'] = net_adjustment
    result['home_injury_impact'] = home_impact
    result['away_injury_impact'] = away_impact

    return result


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Predict NBA game outcomes')
    parser.add_argument('--date', type=str, help='Game date (YYYY-MM-DD)')
    parser.add_argument('--tomorrow', action='store_true', help='Predict tomorrow\'s games')
    parser.add_argument('--start-date', type=str, default=None,
                       help='If set, predict every day from --start-date through --end-date (default today). '
                            'Uses point-in-time team rolling stats and player_impact snapshots (compute_date <= game_date), '
                            'so historical predictions reflect what was known at game time.')
    parser.add_argument('--end-date', type=str, default=None,
                       help='End date for --start-date backfill (YYYY-MM-DD, inclusive). Defaults to today.')
    parser.add_argument('--model', type=str, choices=['rf', 'nn', 'nn-embed', 'both'], default='both',
                       help='Model to use: rf (Random Forest), nn (Neural Network), nn-embed (NN with player embeddings), both')
    parser.add_argument('--no-plot', action='store_true', help='Skip histogram plots')
    parser.add_argument('--no-log', action='store_true', help='Skip logging predictions to database')
    parser.add_argument('--backfill', action='store_true', help='Backfill actual results for past predictions')
    parser.add_argument('--accuracy-report', action='store_true', help='Show accuracy report and exit')
    parser.add_argument('--lookback', type=int, default=30, help='Days to look back for backfill (default: 30)')
    parser.add_argument('--injuries', type=str, nargs='*', default=[],
                       help='Players who are OUT (e.g., --injuries "LeBron James" "Anthony Davis")')
    parser.add_argument('--auto-injuries', action='store_true', default=True,
                       help='Automatically fetch current injuries from NBA/ESPN (default: on)')
    parser.add_argument('--no-auto-injuries', action='store_false', dest='auto_injuries',
                       help='Disable automatic injury fetching')
    parser.add_argument('--show-injuries', action='store_true', default=True,
                       help='Show current injury report before predictions (default: on)')
    parser.add_argument('--no-show-injuries', action='store_false', dest='show_injuries',
                       help='Hide injury report')
    parser.add_argument('--show-impacts', action='store_true',
                       help='Show player impact reports for each team')
    parser.add_argument('--no-shap', action='store_true',
                       help='Skip SHAP feature importance calculations (faster)')
    args = parser.parse_args()

    engine = create_engine()

    # Handle special commands that don't require predictions
    if args.backfill:
        if not PREDICTION_TRACKING_AVAILABLE:
            print("ERROR: Prediction tracking not available")
            return
        print(f"Backfilling actual results (last {args.lookback} days)...")
        backfill_actuals(engine, lookback_days=args.lookback)
        engine.dispose()
        return

    if args.accuracy_report:
        if not PREDICTION_TRACKING_AVAILABLE:
            print("ERROR: Prediction tracking not available")
            return
        print_accuracy_report(engine)
        engine.dispose()
        return

    # Determine the list of game dates to predict.
    # Date-range mode (--start-date) is point-in-time backfill: every layer downstream of
    # this loop already filters by `as_of_date` (team rolling stats, player_impact compute_date,
    # historical-impact lookbacks), so iterating per-day produces predictions using only data
    # that existed before each game. Auto-injuries are live data and would leak future info,
    # so they are force-disabled in backfill mode (with a printed notice).
    backfill_mode = bool(args.start_date)
    if backfill_mode:
        start_d = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        end_d = (datetime.strptime(args.end_date, '%Y-%m-%d').date()
                 if args.end_date else datetime.now().date())
        if end_d < start_d:
            print(f"ERROR: --end-date {end_d} is before --start-date {start_d}")
            engine.dispose()
            return
        game_dates = [(start_d + timedelta(days=i)).strftime('%Y-%m-%d')
                      for i in range((end_d - start_d).days + 1)]
        if args.auto_injuries:
            print(f"\n[backfill] --auto-injuries forcibly disabled: live injury reports are "
                  f"not point-in-time. Pass historical --injuries explicitly if needed.")
            args.auto_injuries = False
        if not args.no_plot:
            print(f"[backfill] --no-plot forcibly enabled to avoid generating one PNG per day.")
            args.no_plot = True
    elif args.date:
        game_dates = [args.date]
    elif args.tomorrow:
        game_dates = [(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')]
    else:
        game_dates = [datetime.now().strftime('%Y-%m-%d')]

    print(f"\nNBA Game Predictor")
    print("=" * 40)
    if backfill_mode:
        print(f"Backfill window: {game_dates[0]} → {game_dates[-1]} ({len(game_dates)} days)")
    else:
        print(f"Prediction date: {game_dates[0]}")
    print(f"Model: {args.model}")

    # Ensure prediction tracking table exists
    if PREDICTION_TRACKING_AVAILABLE and not args.no_log:
        ensure_table_exists(engine)
        print("Prediction tracking: ENABLED")

    # Load models
    rf_models = None
    nn_models = None
    nn_embed_models = None

    if args.model in ['rf', 'both']:
        rf_models = load_or_train_rf_models(engine)

    if args.model in ['nn', 'both']:
        if not PYTORCH_AVAILABLE:
            print("ERROR: PyTorch not available. Install with: pip install torch")
            return
        nn_models = load_or_train_pytorch_models(engine)

    if args.model == 'nn-embed':
        if not PYTORCH_AVAILABLE:
            print("ERROR: PyTorch not available. Install with: pip install torch")
            return
        nn_embed_models = load_or_train_pytorch_embedding_models(engine)

    # Fetch auto-injuries if requested
    auto_injury_data = {}
    if args.auto_injuries and INJURY_DATA_AVAILABLE:
        print("\nFetching current injury data...")
        all_injuries = get_current_injuries()
        print(f"Found {len(all_injuries)} total injuries across the league")

        # Build lookup by team abbreviation
        for inj in all_injuries:
            team_abbrev = inj.get('team_abbrev')
            if team_abbrev:
                if team_abbrev not in auto_injury_data:
                    auto_injury_data[team_abbrev] = []
                auto_injury_data[team_abbrev].append(inj)

    # Show injury report if requested
    if args.show_injuries and INJURY_DATA_AVAILABLE:
        print_injury_report()

    # Determine feature count and model version once (same across all dates in backfill mode)
    if rf_models:
        _, _, _, rf_features = rf_models
        feature_count = len(rf_features)
        model_version = get_model_version(feature_count) if PREDICTION_TRACKING_AVAILABLE else None
    elif nn_models:
        _, _, _, nn_features, _ = nn_models
        feature_count = len(nn_features)
        model_version = get_model_version(feature_count) if PREDICTION_TRACKING_AVAILABLE else None
    elif nn_embed_models:
        _, _, _, team_features, _, _, _, _ = nn_embed_models
        feature_count = len(team_features)
        model_version = get_model_version(feature_count) if PREDICTION_TRACKING_AVAILABLE else None
    else:
        feature_count = 0
        model_version = None

    # Aggregated across all dates (only meaningful when backfilling)
    total_logged = 0
    total_skipped_no_games = 0
    aggregate_rf_predictions: list = []
    aggregate_nn_predictions: list = []

    for date_idx, game_date in enumerate(game_dates):
        if backfill_mode:
            print(f"\n{'='*60}\n[{date_idx + 1}/{len(game_dates)}] {game_date}\n{'='*60}")

        # Get scheduled games for this date
        games = get_scheduled_games(game_date)

        if len(games) == 0:
            print(f"  No games found for {game_date}")
            total_skipped_no_games += 1
            if backfill_mode:
                continue
            engine.dispose()
            return

        print(f"  Found {len(games)} games scheduled")

        rf_predictions = []
        nn_predictions = []

        for _, game in games.iterrows():
            home_id = game['HOME_TEAM_ID']
            away_id = game['AWAY_TEAM_ID']
            home_team = game['HOME_TEAM']
            away_team = game['AWAY_TEAM']
            game_id = game['GAME_ID']

            if not backfill_mode:
                print(f"\nProcessing: {away_team} @ {home_team}")

            home_features = get_team_rolling_stats(engine, home_id, game_date)
            away_features = get_team_rolling_stats(engine, away_id, game_date)

            if home_features is None or away_features is None:
                print(f"  Warning: Missing data for {away_team} @ {home_team}, skipping")
                continue

            # Collect all injuries for this game (manual + auto-fetched).
            # In backfill mode, args.auto_injuries was force-disabled above (live injury data
            # would leak future info into a historical prediction), so this block is a no-op there.
            game_injuries = [{'name': name, 'status': 'out'} for name in args.injuries]

            if args.auto_injuries and auto_injury_data:
                existing_names = [inj['name'].lower() for inj in game_injuries]
                for team_abbrev in [home_team, away_team]:
                    if team_abbrev in auto_injury_data:
                        for inj in auto_injury_data[team_abbrev]:
                            if inj.get('status') in ['OUT', 'DOUBTFUL']:
                                player_name = inj.get('player_name', '')
                                status = inj.get('status', 'OUT').lower()
                                team_side = 'home' if team_abbrev == home_team else 'away'
                                if player_name and player_name.lower() not in existing_names:
                                    game_injuries.append({
                                        'name': player_name,
                                        'status': status,
                                        'team_abbrev': team_abbrev,
                                        'team_side': team_side
                                    })
                                    existing_names.append(player_name.lower())

            injury_info = parse_injuries_for_game(engine, game_injuries, home_id, away_id, game_date)
            home_injury_impact = sum(d['impact'] for d in injury_info['injury_details'] if d['team'] == 'home')
            away_injury_impact = sum(d['impact'] for d in injury_info['injury_details'] if d['team'] == 'away')

            home_injured_names = [d['name'] for d in injury_info['injury_details'] if d['team'] == 'home']
            away_injured_names = [d['name'] for d in injury_info['injury_details'] if d['team'] == 'away']
            all_injury_names = [inj['name'] if isinstance(inj, dict) else inj for inj in game_injuries]

            matchup = build_matchup_features(
                home_features, away_features,
                engine=engine,
                home_team_id=home_id,
                away_team_id=away_id,
                game_date=game_date,
                home_injuries=home_injured_names,
                away_injuries=away_injured_names
            )

            if injury_info['injury_details'] and not backfill_mode:
                auto_label = " (auto-fetched)" if args.auto_injuries else ""
                print(f"  Injury Adjustments{auto_label}:")
                for d in injury_info['injury_details']:
                    team_label = home_team if d['team'] == 'home' else away_team
                    print(f"    {d['name']} ({team_label}) OUT: {d['impact']:+.1f} pts impact [{d['confidence']}]")

            if args.show_impacts and PLAYER_IMPACT_AVAILABLE and not backfill_mode:
                print(f"\n  --- {home_team} Player Impacts ---")
                home_impacts = get_team_player_impacts(engine, home_id, game_date, min_games=5)
                for p in home_impacts[:5]:
                    print(f"    {p['player_name']}: {p['impact']:+.1f} pts [{p['confidence']}]")

                print(f"\n  --- {away_team} Player Impacts ---")
                away_impacts = get_team_player_impacts(engine, away_id, game_date, min_games=5)
                for p in away_impacts[:5]:
                    print(f"    {p['player_name']}: {p['impact']:+.1f} pts [{p['confidence']}]")

            if rf_models:
                clf, reg, scaler, features = rf_models
                result = predict_with_rf(clf, reg, scaler, features, matchup, skip_shap=args.no_shap)
                result['home_team'] = home_team
                result['away_team'] = away_team
                result['game_id'] = game_id

                if injury_info['injury_details']:
                    result['injury_details'] = injury_info['injury_details']

                rf_predictions.append(result)

                if PREDICTION_TRACKING_AVAILABLE and not args.no_log:
                    try:
                        predicted_winner = home_team if result['win_prob'] > 0.5 else away_team
                        log_prediction(
                            engine=engine,
                            game_id=game_id,
                            game_date=game_date,
                            home_team=home_team,
                            away_team=away_team,
                            model_type='rf',
                            model_version=model_version,
                            predicted_winner=predicted_winner,
                            predicted_margin=result['margin_mean'],
                            home_win_probability=result['win_prob'],
                            margin_uncertainty=result['margin_std'],
                            feature_count=feature_count
                        )
                    except Exception as e:
                        print(f"  Warning: Failed to log RF prediction: {e}")

            if nn_models:
                clf, reg, scaler, features, target_scaler = nn_models
                result = predict_with_pytorch(clf, reg, scaler, features, matchup,
                                              skip_shap=args.no_shap, target_scaler=target_scaler)
                result['home_team'] = home_team
                result['away_team'] = away_team
                result['game_id'] = game_id

                if injury_info['injury_details']:
                    result['injury_details'] = injury_info['injury_details']

                nn_predictions.append(result)

                if PREDICTION_TRACKING_AVAILABLE and not args.no_log:
                    try:
                        predicted_winner = home_team if result['win_prob'] > 0.5 else away_team
                        log_prediction(
                            engine=engine,
                            game_id=game_id,
                            game_date=game_date,
                            home_team=home_team,
                            away_team=away_team,
                            model_type='nn',
                            model_version=model_version,
                            predicted_winner=predicted_winner,
                            predicted_margin=result['margin_mean'],
                            home_win_probability=result['win_prob'],
                            margin_uncertainty=result['margin_std'],
                            feature_count=feature_count
                        )
                    except Exception as e:
                        print(f"  Warning: Failed to log NN prediction: {e}")

            if nn_embed_models:
                clf, reg, scaler, team_features, player_to_idx, target_scaler, n_slots, embed_dim = nn_embed_models
                result = predict_with_pytorch_embeddings(
                    clf, reg, scaler, team_features, player_to_idx, matchup,
                    skip_shap=args.no_shap, target_scaler=target_scaler, n_slots=n_slots
                )
                result['home_team'] = home_team
                result['away_team'] = away_team
                result['game_id'] = game_id

                if injury_info['injury_details']:
                    result['injury_details'] = injury_info['injury_details']

                nn_predictions.append(result)

                if PREDICTION_TRACKING_AVAILABLE and not args.no_log:
                    try:
                        predicted_winner = home_team if result['win_prob'] > 0.5 else away_team
                        log_prediction(
                            engine=engine,
                            game_id=game_id,
                            game_date=game_date,
                            home_team=home_team,
                            away_team=away_team,
                            model_type='nn-embed',
                            model_version=model_version,
                            predicted_winner=predicted_winner,
                            predicted_margin=result['margin_mean'],
                            home_win_probability=result['win_prob'],
                            margin_uncertainty=result['margin_std'],
                            feature_count=len(team_features)
                        )
                    except Exception as e:
                        print(f"  Warning: Failed to log NN-embed prediction: {e}")

        # ---- End per-game loop for this date ----

        # Per-date display: skip verbose tables in backfill (one summary line instead).
        if backfill_mode:
            n = len(rf_predictions) + len(nn_predictions)
            print(f"  Logged {n} predictions for {game_date} "
                  f"(rf={len(rf_predictions)}, nn={len(nn_predictions)})")
        else:
            if args.model == 'both' and rf_predictions and nn_predictions:
                print_comparison_table(rf_predictions, nn_predictions, game_date)
                print_predictions_table(rf_predictions, game_date, "Random Forest")
                print_predictions_table(nn_predictions, game_date, "Neural Network")
            elif args.model == 'nn-embed' and nn_predictions:
                print_predictions_table(nn_predictions, game_date, "Neural Network with Embeddings")
            elif rf_predictions:
                print_predictions_table(rf_predictions, game_date, "Random Forest")
            elif nn_predictions:
                print_predictions_table(nn_predictions, game_date, "Neural Network")

        # Plot — skipped in backfill mode (would produce one PNG per day; --no-plot forced above).
        if not args.no_plot and (rf_predictions or nn_predictions):
            plots_dir = os.path.join('outputs', 'predictions_history')
            os.makedirs(plots_dir, exist_ok=True)
            plot_path = os.path.join(plots_dir, f'predictions_{game_date.replace("-", "")}.png')
            plot_model_comparison(rf_predictions, nn_predictions, game_date, save_path=plot_path)

        total_logged += len(rf_predictions) + len(nn_predictions)
        aggregate_rf_predictions.extend(rf_predictions)
        aggregate_nn_predictions.extend(nn_predictions)

    # ---- End per-date loop ----

    # Final aggregate summary
    if PREDICTION_TRACKING_AVAILABLE and not args.no_log:
        if total_logged > 0:
            if backfill_mode:
                print(f"\n{'='*60}")
                print(f"BACKFILL COMPLETE: {game_dates[0]} → {game_dates[-1]}")
                print(f"{'='*60}")
                print(f"Total predictions logged: {total_logged}")
                print(f"Dates with no games:      {total_skipped_no_games}")
            else:
                print(f"\n{total_logged} predictions logged to database (model_predictions table)")
            print(f"Model version: {model_version}")
            print(f"Feature count: {feature_count}")
            print("\nTo fill in actual results, run:")
            print("  python prediction_tracker.py --backfill --lookback 200")
            print("To see accuracy on the Model Performance tab, refresh the dashboard.")

    engine.dispose()
    print("\nDone!")


if __name__ == '__main__':
    main()
