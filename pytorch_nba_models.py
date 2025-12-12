"""
PyTorch NBA Game Prediction
===========================

This script teaches PyTorch fundamentals while building neural networks
for NBA game prediction.

PHASE 3: PyTorch Basics
-----------------------
- Tensors: The fundamental data structure
- Autograd: Automatic differentiation
- nn.Module: Building neural networks
- Optimizers: Gradient descent variants
- Loss functions: What we're minimizing

PHASE 4: NBA Models
-------------------
- Custom Dataset class
- DataLoaders for batching
- Training loops
- Classification network (Win/Loss)
- Regression network (Point Margin)
- Evaluation and comparison to sklearn baselines
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, TensorDataset

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, roc_auc_score, mean_absolute_error, r2_score

import os
import warnings
warnings.filterwarnings('ignore')

# ============================================================================
# PHASE 3: PYTORCH FUNDAMENTALS
# ============================================================================

def pytorch_basics_tutorial():
    """
    Interactive tutorial covering PyTorch fundamentals.
    Run this to understand the building blocks before we use them.
    """
    print("="*70)
    print("PHASE 3: PYTORCH FUNDAMENTALS")
    print("="*70)

    # -------------------------------------------------------------------------
    # 1. TENSORS - The fundamental data structure
    # -------------------------------------------------------------------------
    print("\n" + "-"*70)
    print("1. TENSORS")
    print("-"*70)

    print("""
    Tensors are like NumPy arrays, but with two superpowers:
    1. They can run on GPU for massive speedups
    2. They track operations for automatic differentiation (autograd)
    """)

    # Creating tensors
    # From Python list
    t1 = torch.tensor([1, 2, 3, 4])
    print(f"From list: {t1}")

    # From NumPy array (common in data science)
    np_array = np.array([[1, 2], [3, 4]])
    t2 = torch.from_numpy(np_array)
    print(f"From NumPy:\n{t2}")

    # Special tensors
    zeros = torch.zeros(2, 3)  # 2x3 matrix of zeros
    ones = torch.ones(2, 3)    # 2x3 matrix of ones
    rand = torch.randn(2, 3)   # 2x3 matrix of random normal values
    print(f"Random tensor:\n{rand}")

    # Tensor properties
    print(f"\nTensor properties:")
    print(f"  Shape: {rand.shape}")
    print(f"  Data type: {rand.dtype}")
    print(f"  Device: {rand.device}")  # CPU or CUDA (GPU)

    # Check if GPU is available
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"  Using device: {device}")

    # -------------------------------------------------------------------------
    # 2. AUTOGRAD - Automatic differentiation
    # -------------------------------------------------------------------------
    print("\n" + "-"*70)
    print("2. AUTOGRAD (Automatic Differentiation)")
    print("-"*70)

    print("""
    Autograd tracks all operations on tensors and computes gradients automatically.
    This is the magic that makes training neural networks possible.

    Key concept: requires_grad=True tells PyTorch to track operations
    """)

    # Create a tensor that tracks gradients
    x = torch.tensor([2.0, 3.0], requires_grad=True)
    print(f"x = {x}")

    # Perform operations
    y = x ** 2  # y = x^2
    print(f"y = x^2 = {y}")

    z = y.sum()  # z = sum(y) = x1^2 + x2^2
    print(f"z = sum(y) = {z}")

    # Compute gradients (backpropagation!)
    z.backward()

    # The gradient dz/dx = 2x
    print(f"Gradient dz/dx = 2x = {x.grad}")  # Should be [4, 6]

    print("""
    Why this matters:
    - In neural networks, z is our loss function
    - x represents our model weights
    - x.grad tells us how to adjust weights to reduce loss
    - This is BACKPROPAGATION - computed automatically!
    """)

    # -------------------------------------------------------------------------
    # 3. nn.Module - Building Neural Networks
    # -------------------------------------------------------------------------
    print("\n" + "-"*70)
    print("3. nn.Module (Neural Network Building Blocks)")
    print("-"*70)

    print("""
    nn.Module is the base class for all neural networks in PyTorch.
    You define:
    - __init__: Create the layers
    - forward: Define how data flows through the layers
    """)

    # Simple neural network example
    class SimpleNet(nn.Module):
        def __init__(self, input_size, hidden_size, output_size):
            super(SimpleNet, self).__init__()
            # Define layers
            self.layer1 = nn.Linear(input_size, hidden_size)  # Fully connected
            self.relu = nn.ReLU()                              # Activation function
            self.layer2 = nn.Linear(hidden_size, output_size)

        def forward(self, x):
            # Define forward pass
            x = self.layer1(x)  # Linear transformation
            x = self.relu(x)    # Non-linearity
            x = self.layer2(x)  # Output layer
            return x

    # Create model
    model = SimpleNet(input_size=10, hidden_size=5, output_size=1)
    print(f"Model architecture:\n{model}")

    # Count parameters
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {total_params}")

    # Forward pass example
    sample_input = torch.randn(1, 10)  # Batch of 1, 10 features
    output = model(sample_input)
    print(f"Input shape: {sample_input.shape}")
    print(f"Output shape: {output.shape}")

    # -------------------------------------------------------------------------
    # 4. LOSS FUNCTIONS
    # -------------------------------------------------------------------------
    print("\n" + "-"*70)
    print("4. LOSS FUNCTIONS")
    print("-"*70)

    print("""
    Loss functions measure how wrong our predictions are.
    The goal of training is to MINIMIZE the loss.

    Common loss functions:
    - MSELoss: Mean Squared Error (regression)
    - CrossEntropyLoss: Classification (multi-class)
    - BCEWithLogitsLoss: Binary classification
    """)

    # Binary classification example
    predictions = torch.tensor([0.8, 0.3, 0.9])  # Model outputs (logits)
    targets = torch.tensor([1.0, 0.0, 1.0])      # True labels

    bce_loss = nn.BCEWithLogitsLoss()
    loss = bce_loss(predictions, targets)
    print(f"Binary Cross-Entropy Loss: {loss.item():.4f}")

    # Regression example
    pred_margin = torch.tensor([5.0, -3.0, 10.0])
    true_margin = torch.tensor([7.0, -5.0, 8.0])

    mse_loss = nn.MSELoss()
    loss = mse_loss(pred_margin, true_margin)
    print(f"Mean Squared Error Loss: {loss.item():.4f}")

    # -------------------------------------------------------------------------
    # 5. OPTIMIZERS
    # -------------------------------------------------------------------------
    print("\n" + "-"*70)
    print("5. OPTIMIZERS")
    print("-"*70)

    print("""
    Optimizers update model weights based on gradients.

    Common optimizers:
    - SGD: Stochastic Gradient Descent (classic)
    - Adam: Adaptive learning rate (usually works well)
    - AdamW: Adam with weight decay (regularization)

    Key parameter: learning_rate (lr)
    - Too high: Training unstable, loss explodes
    - Too low: Training too slow, might get stuck
    """)

    # Create optimizer
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    print(f"Optimizer: {optimizer}")

    # -------------------------------------------------------------------------
    # 6. TRAINING LOOP (putting it all together)
    # -------------------------------------------------------------------------
    print("\n" + "-"*70)
    print("6. THE TRAINING LOOP")
    print("-"*70)

    print("""
    The training loop is the heart of deep learning:

    for epoch in range(num_epochs):
        for batch in data_loader:
            # 1. Forward pass
            predictions = model(batch)
            loss = loss_fn(predictions, targets)

            # 2. Backward pass
            optimizer.zero_grad()  # Clear old gradients
            loss.backward()        # Compute new gradients

            # 3. Update weights
            optimizer.step()       # Apply gradients
    """)

    print("\nNow let's apply these concepts to NBA prediction!")


# ============================================================================
# PHASE 4: NBA NEURAL NETWORK MODELS
# ============================================================================

# -------------------------------------------------------------------------
# Custom Dataset Class
# -------------------------------------------------------------------------

class NBADataset(Dataset):
    """
    Custom PyTorch Dataset for NBA game data.

    WHY USE A DATASET CLASS?
    - Standardized interface for data loading
    - Works with DataLoader for batching, shuffling
    - Memory efficient (can load data on-demand)
    """
    def __init__(self, features: np.ndarray, targets: np.ndarray):
        """
        Args:
            features: NumPy array of shape (n_samples, n_features)
            targets: NumPy array of shape (n_samples,)
        """
        # Convert to PyTorch tensors
        self.features = torch.FloatTensor(features)
        self.targets = torch.FloatTensor(targets)

    def __len__(self):
        """Return the number of samples."""
        return len(self.targets)

    def __getitem__(self, idx):
        """Return a single sample (features, target)."""
        return self.features[idx], self.targets[idx]


# -------------------------------------------------------------------------
# Neural Network Architectures
# -------------------------------------------------------------------------

class NBAClassifier(nn.Module):
    """
    Neural network for predicting Win/Loss (binary classification).

    Architecture:
    - Input layer (n_features)
    - Hidden layer 1 (128 neurons) + ReLU + Dropout
    - Hidden layer 2 (64 neurons) + ReLU + Dropout
    - Hidden layer 3 (32 neurons) + ReLU + Dropout
    - Output layer (1 neuron) + Sigmoid

    DESIGN CHOICES:
    - ReLU activation: Simple, effective, avoids vanishing gradients
    - Dropout: Regularization to prevent overfitting
    - Batch normalization: Stabilizes training
    - Gradual size reduction: Common pattern in MLPs
    """
    def __init__(self, input_size, dropout_rate=0.3):
        super(NBAClassifier, self).__init__()

        self.network = nn.Sequential(
            # Layer 1
            nn.Linear(input_size, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),

            # Layer 2
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),

            # Layer 3
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(dropout_rate),

            # Output layer
            nn.Linear(32, 1)
            # Note: No sigmoid here - we use BCEWithLogitsLoss which includes it
        )

    def forward(self, x):
        return self.network(x).squeeze()


class NBARegressor(nn.Module):
    """
    Neural network for predicting Point Margin (regression).

    Similar architecture to classifier, but:
    - No activation on output (we want unbounded predictions)
    - Could be negative (away team wins) or positive (home team wins)
    """
    def __init__(self, input_size, dropout_rate=0.3):
        super(NBARegressor, self).__init__()

        self.network = nn.Sequential(
            # Layer 1
            nn.Linear(input_size, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),

            # Layer 2
            nn.Linear(128, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.Dropout(dropout_rate),

            # Layer 3
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Dropout(dropout_rate),

            # Output layer (no activation - raw value)
            nn.Linear(32, 1)
        )

    def forward(self, x):
        return self.network(x).squeeze()


# -------------------------------------------------------------------------
# Training Functions
# -------------------------------------------------------------------------

def train_epoch(model, dataloader, loss_fn, optimizer, device):
    """Train for one epoch."""
    model.train()  # Set to training mode (enables dropout, batchnorm updates)
    total_loss = 0
    n_batches = 0

    for features, targets in dataloader:
        # Move data to device (CPU or GPU)
        features = features.to(device)
        targets = targets.to(device)

        # Forward pass
        predictions = model(features)
        loss = loss_fn(predictions, targets)

        # Backward pass
        optimizer.zero_grad()  # Clear old gradients
        loss.backward()        # Compute gradients
        optimizer.step()       # Update weights

        total_loss += loss.item()
        n_batches += 1

    return total_loss / n_batches


def evaluate(model, dataloader, loss_fn, device, task='classification'):
    """Evaluate model on a dataset."""
    model.eval()  # Set to evaluation mode (disables dropout)
    total_loss = 0
    all_predictions = []
    all_targets = []

    with torch.no_grad():  # No gradient computation needed
        for features, targets in dataloader:
            features = features.to(device)
            targets = targets.to(device)

            predictions = model(features)
            loss = loss_fn(predictions, targets)

            total_loss += loss.item()

            # Store predictions
            if task == 'classification':
                # Apply sigmoid to get probabilities
                probs = torch.sigmoid(predictions)
                all_predictions.extend(probs.cpu().numpy())
            else:
                all_predictions.extend(predictions.cpu().numpy())

            all_targets.extend(targets.cpu().numpy())

    avg_loss = total_loss / len(dataloader)
    predictions = np.array(all_predictions)
    targets = np.array(all_targets)

    # Compute metrics
    if task == 'classification':
        binary_preds = (predictions > 0.5).astype(int)
        accuracy = accuracy_score(targets, binary_preds)
        auc = roc_auc_score(targets, predictions)
        return avg_loss, accuracy, auc
    else:
        mae = mean_absolute_error(targets, predictions)
        r2 = r2_score(targets, predictions)
        return avg_loss, mae, r2


def train_model(model, train_loader, val_loader, loss_fn, optimizer,
                device, num_epochs, task='classification', patience=10):
    """
    Full training loop with early stopping.

    EARLY STOPPING:
    If validation loss doesn't improve for 'patience' epochs, stop training.
    This prevents overfitting.
    """
    best_val_loss = float('inf')
    epochs_without_improvement = 0
    best_model_state = None

    history = {'train_loss': [], 'val_loss': [], 'val_metric': []}

    for epoch in range(num_epochs):
        # Train
        train_loss = train_epoch(model, train_loader, loss_fn, optimizer, device)

        # Evaluate
        if task == 'classification':
            val_loss, accuracy, auc = evaluate(model, val_loader, loss_fn, device, task)
            metric = auc
            metric_name = 'AUC'
        else:
            val_loss, mae, r2 = evaluate(model, val_loader, loss_fn, device, task)
            metric = mae
            metric_name = 'MAE'

        history['train_loss'].append(train_loss)
        history['val_loss'].append(val_loss)
        history['val_metric'].append(metric)

        # Print progress
        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"Epoch {epoch+1:3d}/{num_epochs}: "
                  f"Train Loss: {train_loss:.4f}, "
                  f"Val Loss: {val_loss:.4f}, "
                  f"Val {metric_name}: {metric:.4f}")

        # Early stopping check
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            epochs_without_improvement = 0
            best_model_state = model.state_dict().copy()
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                print(f"\nEarly stopping at epoch {epoch+1}")
                break

    # Restore best model
    if best_model_state is not None:
        model.load_state_dict(best_model_state)

    return history


# -------------------------------------------------------------------------
# Data Preparation
# -------------------------------------------------------------------------

def load_and_prepare_data():
    """Load and prepare data for PyTorch."""
    print("\n" + "="*70)
    print("LOADING AND PREPARING DATA")
    print("="*70)

    # Load data
    df = pd.read_csv('nba_ml_features.csv')
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])

    print(f"Loaded {len(df)} games")

    # Get feature columns - comprehensive list matching feature_engineering.py
    # Includes:
    # - Rolling statistics (_L5, _L10)
    # - Fatigue features (IS_BACK_TO_BACK, GAMES_LAST, etc.)
    # - Player projection features (PROJ_*, WEIGHTED_AVG_*, etc.)
    # - Player slot features (SLOT_*_IMPACT, SLOT_*_AVAILABLE, etc.)
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
    feature_cols = [col for col in df.columns
                   if any(pattern in col for pattern in feature_patterns)]
    # Exclude identifiers and PLAYER_ID columns (those are for embedding models)
    feature_cols = [col for col in feature_cols
                   if 'TARGET' not in col and 'TEAM_ID' not in col
                   and 'GAME_ID' not in col and 'PLAYER_ID' not in col]

    print(f"Using {len(feature_cols)} features")

    # Temporal split
    df_sorted = df.sort_values('GAME_DATE').reset_index(drop=True)
    split_idx = int(len(df_sorted) * 0.8)

    train_df = df_sorted.iloc[:split_idx]
    test_df = df_sorted.iloc[split_idx:]

    print(f"Train: {len(train_df)} games, Test: {len(test_df)} games")

    # Extract features and targets
    X_train = train_df[feature_cols].values
    X_test = test_df[feature_cols].values

    y_train_clf = train_df['TARGET_WIN'].values
    y_test_clf = test_df['TARGET_WIN'].values

    y_train_reg = train_df['TARGET_MARGIN'].values
    y_test_reg = test_df['TARGET_MARGIN'].values

    # Handle missing values
    imputer = SimpleImputer(strategy='median')
    X_train = imputer.fit_transform(X_train)
    X_test = imputer.transform(X_test)

    # Remove any columns that are all NaN (after imputation shouldn't happen, but safety check)
    valid_cols = ~np.isnan(X_train).all(axis=0)
    X_train = X_train[:, valid_cols]
    X_test = X_test[:, valid_cols]

    # Scale features
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)

    print(f"Final feature shape: {X_train.shape[1]}")

    return (X_train, X_test,
            y_train_clf, y_test_clf,
            y_train_reg, y_test_reg)


# -------------------------------------------------------------------------
# Main Execution
# -------------------------------------------------------------------------

def main():
    # Run the fundamentals tutorial first
    pytorch_basics_tutorial()

    # Load data
    (X_train, X_test,
     y_train_clf, y_test_clf,
     y_train_reg, y_test_reg) = load_and_prepare_data()

    # Device configuration
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"\nUsing device: {device}")

    # Hyperparameters
    BATCH_SIZE = 64
    LEARNING_RATE = 0.001
    NUM_EPOCHS = 100
    PATIENCE = 15

    # =========================================================================
    # CLASSIFICATION MODEL
    # =========================================================================
    print("\n" + "="*70)
    print("TRAINING CLASSIFICATION MODEL (Win/Loss)")
    print("="*70)

    # Create datasets and dataloaders
    train_dataset_clf = NBADataset(X_train, y_train_clf)
    test_dataset_clf = NBADataset(X_test, y_test_clf)

    train_loader_clf = DataLoader(train_dataset_clf, batch_size=BATCH_SIZE, shuffle=True)
    test_loader_clf = DataLoader(test_dataset_clf, batch_size=BATCH_SIZE, shuffle=False)

    # Create model
    input_size = X_train.shape[1]
    clf_model = NBAClassifier(input_size).to(device)

    print(f"\nModel architecture:")
    print(clf_model)
    print(f"\nTotal parameters: {sum(p.numel() for p in clf_model.parameters()):,}")

    # Loss and optimizer
    clf_loss_fn = nn.BCEWithLogitsLoss()
    clf_optimizer = optim.Adam(clf_model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)

    # Train
    print("\nTraining...")
    clf_history = train_model(
        clf_model, train_loader_clf, test_loader_clf,
        clf_loss_fn, clf_optimizer, device,
        NUM_EPOCHS, task='classification', patience=PATIENCE
    )

    # Final evaluation
    _, test_accuracy, test_auc = evaluate(
        clf_model, test_loader_clf, clf_loss_fn, device, task='classification'
    )

    print(f"\nFinal Classification Results:")
    print(f"  Test Accuracy: {test_accuracy:.3f}")
    print(f"  Test AUC: {test_auc:.3f}")

    # =========================================================================
    # REGRESSION MODEL
    # =========================================================================
    print("\n" + "="*70)
    print("TRAINING REGRESSION MODEL (Point Margin)")
    print("="*70)

    # Create datasets and dataloaders
    train_dataset_reg = NBADataset(X_train, y_train_reg)
    test_dataset_reg = NBADataset(X_test, y_test_reg)

    train_loader_reg = DataLoader(train_dataset_reg, batch_size=BATCH_SIZE, shuffle=True)
    test_loader_reg = DataLoader(test_dataset_reg, batch_size=BATCH_SIZE, shuffle=False)

    # Create model
    reg_model = NBARegressor(input_size).to(device)

    print(f"\nModel architecture:")
    print(reg_model)

    # Loss and optimizer
    reg_loss_fn = nn.MSELoss()
    reg_optimizer = optim.Adam(reg_model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)

    # Train
    print("\nTraining...")
    reg_history = train_model(
        reg_model, train_loader_reg, test_loader_reg,
        reg_loss_fn, reg_optimizer, device,
        NUM_EPOCHS, task='regression', patience=PATIENCE
    )

    # Final evaluation
    _, test_mae, test_r2 = evaluate(
        reg_model, test_loader_reg, reg_loss_fn, device, task='regression'
    )

    print(f"\nFinal Regression Results:")
    print(f"  Test MAE: {test_mae:.2f} points")
    print(f"  Test R2: {test_r2:.3f}")

    # =========================================================================
    # COMPARISON WITH SKLEARN BASELINES
    # =========================================================================
    print("\n" + "="*70)
    print("COMPARISON: PyTorch vs Scikit-learn")
    print("="*70)

    print("""
    Scikit-learn Baselines (from baseline_models.py):
    -------------------------------------------------
    Classification (Random Forest):
      - Accuracy: 0.700
      - AUC: 0.792

    Regression (Random Forest):
      - MAE: 9.33 points
      - R2: 0.204
    """)

    print(f"""
    PyTorch Neural Network Results:
    -------------------------------
    Classification:
      - Accuracy: {test_accuracy:.3f}
      - AUC: {test_auc:.3f}

    Regression:
      - MAE: {test_mae:.2f} points
      - R2: {test_r2:.3f}
    """)

    # Verdict
    clf_better = test_auc > 0.792
    reg_better = test_mae < 9.33

    print("Verdict:")
    if clf_better:
        print(f"  Classification: Neural Network WINS (AUC {test_auc:.3f} vs 0.792)")
    else:
        print(f"  Classification: Random Forest wins (AUC 0.792 vs {test_auc:.3f})")

    if reg_better:
        print(f"  Regression: Neural Network WINS (MAE {test_mae:.2f} vs 9.33)")
    else:
        print(f"  Regression: Random Forest wins (MAE 9.33 vs {test_mae:.2f})")

    print("""
    Key Takeaways:
    --------------
    1. For tabular data, tree-based models often match or beat neural networks
    2. Neural networks require more tuning (architecture, learning rate, etc.)
    3. But you now understand how deep learning works from the ground up!
    4. These skills transfer to domains where neural networks excel (images, text)
    """)

    return clf_model, reg_model, clf_history, reg_history


if __name__ == '__main__':
    clf_model, reg_model, clf_history, reg_history = main()
