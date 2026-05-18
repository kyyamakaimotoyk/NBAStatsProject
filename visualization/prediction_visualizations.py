"""
NBA Prediction Accuracy Visualizations
========================================

Visualize model prediction accuracy over time and compare models.

Charts:
- Prediction vs Actual scatter plot (margin)
- Accuracy over time (rolling window)
- Model comparison (RF vs NN accuracy)
- Calibration plot (predicted probability vs actual win rate)
"""

# Project-root bootstrap so cross-folder imports work regardless of CWD.
import sys as _sys
import os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime
import seaborn as sns
from typing import Optional

# Use seaborn style for better looking plots
sns.set_style("darkgrid")
plt.rcParams['figure.figsize'] = (12, 8)


# ============================================================================
# PREDICTION VS ACTUAL SCATTER PLOT
# ============================================================================

def plot_predicted_vs_actual_margin(df: pd.DataFrame, model_type: str = 'both',
                                    save_path: Optional[str] = None):
    """
    Scatter plot of predicted margin vs actual margin.

    Args:
        df: DataFrame from get_all_predictions_with_results()
        model_type: 'rf', 'nn', or 'both'
        save_path: Optional path to save figure
    """
    fig, ax = plt.subplots(figsize=(10, 10))

    if model_type == 'both':
        rf_data = df[df['model_type'] == 'rf']
        nn_data = df[df['model_type'] == 'nn']

        if len(rf_data) > 0:
            ax.scatter(rf_data['predicted_margin'], rf_data['actual_margin'],
                      alpha=0.5, s=50, label='Random Forest', color='#3498db')

        if len(nn_data) > 0:
            ax.scatter(nn_data['predicted_margin'], nn_data['actual_margin'],
                      alpha=0.5, s=50, label='Neural Network', color='#e74c3c')
    else:
        model_data = df[df['model_type'] == model_type]
        color = '#3498db' if model_type == 'rf' else '#e74c3c'
        model_name = 'Random Forest' if model_type == 'rf' else 'Neural Network'

        ax.scatter(model_data['predicted_margin'], model_data['actual_margin'],
                  alpha=0.5, s=50, label=model_name, color=color)

    # Perfect prediction line
    lims = [
        min(ax.get_xlim()[0], ax.get_ylim()[0]),
        max(ax.get_xlim()[1], ax.get_ylim()[1])
    ]
    ax.plot(lims, lims, 'k--', alpha=0.5, linewidth=2, label='Perfect Prediction')

    # Zero lines
    ax.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    ax.axvline(x=0, color='gray', linestyle='-', alpha=0.3)

    ax.set_xlabel('Predicted Margin (points)', fontsize=12)
    ax.set_ylabel('Actual Margin (points)', fontsize=12)
    ax.set_title('Predicted vs Actual Point Margin', fontsize=14, fontweight='bold')
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)

    # Add MAE to plot
    if model_type == 'both':
        rf_mae = df[df['model_type'] == 'rf']['margin_error'].mean()
        nn_mae = df[df['model_type'] == 'nn']['margin_error'].mean()
        textstr = f'RF MAE: {rf_mae:.2f}\nNN MAE: {nn_mae:.2f}'
    else:
        mae = df[df['model_type'] == model_type]['margin_error'].mean()
        textstr = f'MAE: {mae:.2f}'

    ax.text(0.05, 0.95, textstr, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")

    plt.show()


# ============================================================================
# ACCURACY OVER TIME
# ============================================================================

def plot_accuracy_over_time(df: pd.DataFrame, model_type: str = 'both',
                            window_size: int = 20, save_path: Optional[str] = None):
    """
    Plot rolling accuracy over time.

    Args:
        df: DataFrame from get_all_predictions_with_results()
        model_type: 'rf', 'nn', or 'both'
        window_size: Window size for rolling average
        save_path: Optional path to save figure
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)

    # Sort by game date
    df = df.sort_values('game_date')

    if model_type == 'both':
        for mtype, color, name in [('rf', '#3498db', 'Random Forest'),
                                   ('nn', '#e74c3c', 'Neural Network')]:
            model_df = df[df['model_type'] == mtype].copy()
            if len(model_df) == 0:
                continue

            model_df['is_correct_num'] = model_df['is_correct'].astype(int)
            model_df['rolling_acc'] = model_df['is_correct_num'].rolling(
                window=window_size, min_periods=1).mean()
            model_df['rolling_mae'] = model_df['margin_error'].rolling(
                window=window_size, min_periods=1).mean()

            ax1.plot(model_df['game_date'], model_df['rolling_acc'],
                    label=name, color=color, linewidth=2)
            ax2.plot(model_df['game_date'], model_df['rolling_mae'],
                    label=name, color=color, linewidth=2)
    else:
        model_df = df[df['model_type'] == model_type].copy()
        color = '#3498db' if model_type == 'rf' else '#e74c3c'
        name = 'Random Forest' if model_type == 'rf' else 'Neural Network'

        model_df['is_correct_num'] = model_df['is_correct'].astype(int)
        model_df['rolling_acc'] = model_df['is_correct_num'].rolling(
            window=window_size, min_periods=1).mean()
        model_df['rolling_mae'] = model_df['margin_error'].rolling(
            window=window_size, min_periods=1).mean()

        ax1.plot(model_df['game_date'], model_df['rolling_acc'],
                label=name, color=color, linewidth=2)
        ax2.plot(model_df['game_date'], model_df['rolling_mae'],
                label=name, color=color, linewidth=2)

    # Accuracy plot
    ax1.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5, label='50% baseline')
    ax1.set_ylabel('Accuracy (Rolling Average)', fontsize=12)
    ax1.set_title(f'Prediction Accuracy Over Time (Window: {window_size} games)',
                 fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim([0, 1])

    # MAE plot
    ax2.set_xlabel('Game Date', fontsize=12)
    ax2.set_ylabel('Mean Absolute Error (points)', fontsize=12)
    ax2.set_title('Prediction Error Over Time', fontsize=14, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3)

    # Format x-axis dates
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax2.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")

    plt.show()


# ============================================================================
# MODEL COMPARISON
# ============================================================================

def plot_model_comparison(df: pd.DataFrame, save_path: Optional[str] = None):
    """
    Compare RF vs NN model performance.

    Args:
        df: DataFrame from get_all_predictions_with_results()
        save_path: Optional path to save figure
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    rf_df = df[df['model_type'] == 'rf']
    nn_df = df[df['model_type'] == 'nn']

    if len(rf_df) == 0 or len(nn_df) == 0:
        print("Warning: Need both RF and NN predictions for comparison")
        return

    # 1. Accuracy comparison
    ax = axes[0, 0]
    models = ['Random Forest', 'Neural Network']
    accuracies = [
        rf_df['is_correct'].mean(),
        nn_df['is_correct'].mean()
    ]
    colors = ['#3498db', '#e74c3c']

    bars = ax.bar(models, accuracies, color=colors, alpha=0.7)
    ax.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    ax.set_ylabel('Accuracy', fontsize=11)
    ax.set_title('Overall Accuracy Comparison', fontsize=12, fontweight='bold')
    ax.set_ylim([0, 1])

    for bar, acc in zip(bars, accuracies):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.02,
               f'{acc:.1%}', ha='center', va='bottom', fontsize=10)

    # 2. MAE comparison
    ax = axes[0, 1]
    maes = [
        rf_df['margin_error'].mean(),
        nn_df['margin_error'].mean()
    ]

    bars = ax.bar(models, maes, color=colors, alpha=0.7)
    ax.set_ylabel('Mean Absolute Error (points)', fontsize=11)
    ax.set_title('Margin Prediction Error', fontsize=12, fontweight='bold')

    for bar, mae in zip(bars, maes):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.2,
               f'{mae:.2f}', ha='center', va='bottom', fontsize=10)

    # 3. Error distribution
    ax = axes[1, 0]
    ax.hist(rf_df['margin_error'], bins=30, alpha=0.6, label='Random Forest',
           color='#3498db', edgecolor='black')
    ax.hist(nn_df['margin_error'], bins=30, alpha=0.6, label='Neural Network',
           color='#e74c3c', edgecolor='black')
    ax.set_xlabel('Margin Error (points)', fontsize=11)
    ax.set_ylabel('Frequency', fontsize=11)
    ax.set_title('Error Distribution', fontsize=12, fontweight='bold')
    ax.legend(loc='upper right', fontsize=9)

    # 4. Confidence vs Accuracy
    ax = axes[1, 1]

    # Bin predictions by confidence
    for mtype, color, name in [('rf', '#3498db', 'Random Forest'),
                               ('nn', '#e74c3c', 'Neural Network')]:
        model_df = df[df['model_type'] == mtype].copy()

        # Create confidence bins
        model_df['confidence_bin'] = pd.cut(model_df['home_win_probability'],
                                           bins=[0, 0.55, 0.65, 0.75, 0.85, 1.0],
                                           labels=['50-55%', '55-65%', '65-75%', '75-85%', '85-100%'])

        # Calculate accuracy per bin
        acc_by_conf = model_df.groupby('confidence_bin')['is_correct'].mean()

        ax.plot(range(len(acc_by_conf)), acc_by_conf.values,
               marker='o', linewidth=2, markersize=8, label=name, color=color)

    ax.set_xticks(range(5))
    ax.set_xticklabels(['50-55%', '55-65%', '65-75%', '75-85%', '85-100%'], rotation=45)
    ax.set_xlabel('Predicted Win Probability Range', fontsize=11)
    ax.set_ylabel('Actual Accuracy', fontsize=11)
    ax.set_title('Calibration: Confidence vs Accuracy', fontsize=12, fontweight='bold')
    ax.legend(loc='lower right', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim([0, 1])

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")

    plt.show()


# ============================================================================
# CALIBRATION PLOT
# ============================================================================

def plot_calibration_curve(df: pd.DataFrame, model_type: str = 'both',
                          n_bins: int = 10, save_path: Optional[str] = None):
    """
    Plot calibration curve (predicted probability vs actual win rate).

    Perfect calibration means predicted probabilities match actual outcomes.

    Args:
        df: DataFrame from get_all_predictions_with_results()
        model_type: 'rf', 'nn', or 'both'
        n_bins: Number of bins for grouping predictions
        save_path: Optional path to save figure
    """
    fig, ax = plt.subplots(figsize=(10, 10))

    if model_type == 'both':
        for mtype, color, name in [('rf', '#3498db', 'Random Forest'),
                                   ('nn', '#e74c3c', 'Neural Network')]:
            model_df = df[df['model_type'] == mtype].copy()
            if len(model_df) == 0:
                continue

            # Convert to home team won (0/1)
            model_df['home_won'] = (model_df['actual_winner'] == model_df['home_team']).astype(int)

            # Create bins
            model_df['prob_bin'] = pd.cut(model_df['home_win_probability'],
                                         bins=n_bins, duplicates='drop')

            # Calculate mean predicted prob and actual win rate per bin
            grouped = model_df.groupby('prob_bin').agg({
                'home_win_probability': 'mean',
                'home_won': 'mean',
                'game_id': 'count'
            }).dropna()

            ax.scatter(grouped['home_win_probability'], grouped['home_won'],
                      s=grouped['game_id']*10, alpha=0.6, color=color, label=name)
            ax.plot(grouped['home_win_probability'], grouped['home_won'],
                   color=color, linewidth=2, alpha=0.8)

    else:
        model_df = df[df['model_type'] == model_type].copy()
        color = '#3498db' if model_type == 'rf' else '#e74c3c'
        name = 'Random Forest' if model_type == 'rf' else 'Neural Network'

        model_df['home_won'] = (model_df['actual_winner'] == model_df['home_team']).astype(int)
        model_df['prob_bin'] = pd.cut(model_df['home_win_probability'],
                                     bins=n_bins, duplicates='drop')

        grouped = model_df.groupby('prob_bin').agg({
            'home_win_probability': 'mean',
            'home_won': 'mean',
            'game_id': 'count'
        }).dropna()

        ax.scatter(grouped['home_win_probability'], grouped['home_won'],
                  s=grouped['game_id']*10, alpha=0.6, color=color, label=name)
        ax.plot(grouped['home_win_probability'], grouped['home_won'],
               color=color, linewidth=2, alpha=0.8)

    # Perfect calibration line
    ax.plot([0, 1], [0, 1], 'k--', linewidth=2, label='Perfect Calibration')

    ax.set_xlabel('Predicted Win Probability', fontsize=12)
    ax.set_ylabel('Actual Win Rate', fontsize=12)
    ax.set_title('Calibration Curve\n(Bubble size = number of predictions)',
                fontsize=14, fontweight='bold')
    ax.legend(loc='upper left', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim([0, 1])
    ax.set_ylim([0, 1])

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")

    plt.show()


# ============================================================================
# COMPREHENSIVE DASHBOARD
# ============================================================================

def create_accuracy_dashboard(df: pd.DataFrame, save_path: Optional[str] = None):
    """
    Create a comprehensive 6-panel accuracy dashboard.

    Args:
        df: DataFrame from get_all_predictions_with_results()
        save_path: Optional path to save figure
    """
    fig = plt.figure(figsize=(18, 12))
    gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

    # 1. Predicted vs Actual Margin (2x2 grid)
    ax1 = fig.add_subplot(gs[0:2, 0:2])
    rf_data = df[df['model_type'] == 'rf']
    nn_data = df[df['model_type'] == 'nn']

    if len(rf_data) > 0:
        ax1.scatter(rf_data['predicted_margin'], rf_data['actual_margin'],
                   alpha=0.4, s=40, label='Random Forest', color='#3498db')
    if len(nn_data) > 0:
        ax1.scatter(nn_data['predicted_margin'], nn_data['actual_margin'],
                   alpha=0.4, s=40, label='Neural Network', color='#e74c3c')

    lims = [min(ax1.get_xlim()[0], ax1.get_ylim()[0]),
            max(ax1.get_xlim()[1], ax1.get_ylim()[1])]
    ax1.plot(lims, lims, 'k--', alpha=0.5, linewidth=2)
    ax1.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    ax1.axvline(x=0, color='gray', linestyle='-', alpha=0.3)
    ax1.set_xlabel('Predicted Margin', fontsize=11)
    ax1.set_ylabel('Actual Margin', fontsize=11)
    ax1.set_title('Predicted vs Actual Margin', fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)

    # 2. Accuracy bar chart
    ax2 = fig.add_subplot(gs[0, 2])
    models = ['RF', 'NN']
    accuracies = [rf_data['is_correct'].mean(), nn_data['is_correct'].mean()]
    colors = ['#3498db', '#e74c3c']
    ax2.bar(models, accuracies, color=colors, alpha=0.7)
    ax2.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    ax2.set_ylabel('Accuracy', fontsize=10)
    ax2.set_title('Accuracy', fontsize=11, fontweight='bold')
    ax2.set_ylim([0, 1])
    for i, (m, acc) in enumerate(zip(models, accuracies)):
        ax2.text(i, acc + 0.02, f'{acc:.1%}', ha='center', fontsize=9)

    # 3. MAE bar chart
    ax3 = fig.add_subplot(gs[1, 2])
    maes = [rf_data['margin_error'].mean(), nn_data['margin_error'].mean()]
    ax3.bar(models, maes, color=colors, alpha=0.7)
    ax3.set_ylabel('MAE (points)', fontsize=10)
    ax3.set_title('Margin Error', fontsize=11, fontweight='bold')
    for i, (m, mae) in enumerate(zip(models, maes)):
        ax3.text(i, mae + 0.2, f'{mae:.2f}', ha='center', fontsize=9)

    # 4. Accuracy over time
    ax4 = fig.add_subplot(gs[2, :2])
    df_sorted = df.sort_values('game_date')
    window_size = 15

    for mtype, color, name in [('rf', '#3498db', 'RF'), ('nn', '#e74c3c', 'NN')]:
        model_df = df_sorted[df_sorted['model_type'] == mtype].copy()
        if len(model_df) > 0:
            model_df['is_correct_num'] = model_df['is_correct'].astype(int)
            model_df['rolling_acc'] = model_df['is_correct_num'].rolling(
                window=window_size, min_periods=1).mean()
            ax4.plot(model_df['game_date'], model_df['rolling_acc'],
                    label=name, color=color, linewidth=2)

    ax4.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
    ax4.set_xlabel('Game Date', fontsize=10)
    ax4.set_ylabel('Rolling Accuracy', fontsize=10)
    ax4.set_title(f'Accuracy Over Time (window={window_size})', fontsize=11, fontweight='bold')
    ax4.legend(loc='best', fontsize=9)
    ax4.grid(True, alpha=0.3)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, ha='right', fontsize=8)

    # 5. Error distribution
    ax5 = fig.add_subplot(gs[2, 2])
    ax5.hist(rf_data['margin_error'], bins=20, alpha=0.6, label='RF',
            color='#3498db', edgecolor='black')
    ax5.hist(nn_data['margin_error'], bins=20, alpha=0.6, label='NN',
            color='#e74c3c', edgecolor='black')
    ax5.set_xlabel('Error (pts)', fontsize=10)
    ax5.set_ylabel('Count', fontsize=10)
    ax5.set_title('Error Distribution', fontsize=11, fontweight='bold')
    ax5.legend(loc='upper right', fontsize=8)

    fig.suptitle('NBA Prediction Accuracy Dashboard', fontsize=16, fontweight='bold', y=0.98)

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")

    plt.show()


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == '__main__':
    import argparse
    from modeling.prediction_tracker import create_engine, get_all_predictions_with_results

    parser = argparse.ArgumentParser(description='NBA Prediction Visualizations')
    parser.add_argument('--chart', type=str,
                       choices=['scatter', 'time', 'compare', 'calibration', 'dashboard'],
                       default='dashboard',
                       help='Chart type to generate')
    parser.add_argument('--model', type=str, choices=['rf', 'nn', 'both'], default='both',
                       help='Model to visualize')
    parser.add_argument('--save', type=str, help='Path to save figure')
    parser.add_argument('--days', type=int, help='Number of days to look back')
    args = parser.parse_args()

    # Load data
    engine = create_engine()

    if args.days:
        from datetime import datetime, timedelta
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
        df = get_all_predictions_with_results(engine, start_date=start_date)
    else:
        df = get_all_predictions_with_results(engine)

    if len(df) == 0:
        print("No predictions with actual results found.")
        print("Run predictions first, then use --backfill to update with actual results.")
        engine.dispose()
        exit(1)

    print(f"Loaded {len(df)} predictions with actual results")

    # Generate requested chart
    if args.chart == 'scatter':
        plot_predicted_vs_actual_margin(df, model_type=args.model, save_path=args.save)
    elif args.chart == 'time':
        plot_accuracy_over_time(df, model_type=args.model, save_path=args.save)
    elif args.chart == 'compare':
        plot_model_comparison(df, save_path=args.save)
    elif args.chart == 'calibration':
        plot_calibration_curve(df, model_type=args.model, save_path=args.save)
    elif args.chart == 'dashboard':
        create_accuracy_dashboard(df, save_path=args.save)

    engine.dispose()
