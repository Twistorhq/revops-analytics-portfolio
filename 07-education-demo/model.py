# Prepared by Twistor Holdings LLC
# TW-494: logistic-regression training, calibration, backtest, baseline.
#
# Pipeline:
#   1. features from the observation window (Sep-Oct), target from Nov
#   2. stratified train/test split on students
#   3. StandardScaler + LogisticRegression
#   4. isotonic calibration (CalibratedClassifierCV) on a held-out fold
#   5. backtest metrics: AUC, precision/recall @ 0.5, Brier score,
#      reliability curve (10 bins)
#   6. naive baseline: flag if first30_rate < 0.90
#
# Rollback rule: if the fitted model is unavailable, predict_fallback()
# applies the naive rule. The dashboard must call the model when present
# and fall back without error otherwise.

from itertools import pairwise

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from predict import BASELINE_RATE_CUTOFF


def fit(X_train, y_train, seed=20261013):
    """Scale + logistic regression. Returns (scaler, classifier)."""
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X_train)
    clf = LogisticRegression(C=1.0, max_iter=1000, random_state=seed)
    clf.fit(Xs, y_train)
    return scaler, clf


def calibrate(scaler, clf, X_cal, y_cal):
    """Isotonic calibration on held-out data. Returns calibrated classifier."""
    cal = CalibratedClassifierCV(clf, method="isotonic", cv=5)
    cal.fit(scaler.transform(X_cal), y_cal)
    return cal


def reliability_curve(y_true, y_prob, n_bins=10):
    """Mean predicted vs observed rate per bin. Well-calibrated: diagonal."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for lo, hi in pairwise(bins):
        mask = (y_prob > lo) & (y_prob <= hi) if lo > 0 else (y_prob <= hi)
        if mask.sum() == 0:
            continue
        out.append(
            {
                "bin_low": round(float(lo), 2),
                "bin_high": round(float(hi), 2),
                "n": int(mask.sum()),
                "mean_predicted": round(float(y_prob[mask].mean()), 4),
                "observed_rate": round(float(y_true[mask].mean()), 4),
            }
        )
    return out


def evaluate(y_true, y_prob, threshold=0.5):
    y_hat = (y_prob >= threshold).astype(int)
    tp = int(((y_hat == 1) & (y_true == 1)).sum())
    fp = int(((y_hat == 1) & (y_true == 0)).sum())
    fn = int(((y_hat == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "precision_at_50": round(precision, 4),
        "recall_at_50": round(recall, 4),
        "brier": round(float(brier_score_loss(y_true, y_prob)), 4),
        "n_positive": int(y_true.sum()),
        "n_total": len(y_true),
        "base_rate": round(float(y_true.mean()), 4),
    }


def baseline_predict(rows):
    """Naive rule: flag if first-30-day attendance rate < 90%."""
    return np.array(
        [1 if r["first30_rate"] < BASELINE_RATE_CUTOFF else 0 for r in rows],
        dtype=int,
    )


def baseline_evaluate(y_true, y_hat):
    tp = int(((y_hat == 1) & (y_true == 1)).sum())
    fp = int(((y_hat == 1) & (y_true == 0)).sum())
    fn = int(((y_hat == 0) & (y_true == 1)).sum())
    return {
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else 0.0,
        "recall": round(tp / (tp + fn), 4) if (tp + fn) else 0.0,
    }


def predict_fallback(row):
    """Rollback: the naive rule, used when the fitted model is unavailable."""
    return 1 if row["first30_rate"] < BASELINE_RATE_CUTOFF else 0


def odds_ratios(clf, features):
    """exp(beta): multiplicative odds change per unit of each feature."""
    return {f: round(float(np.exp(b)), 3) for f, b in zip(features, clf.coef_[0])}


def run_backtest(rows, features, seed=20261013):
    """Full backtest: train -> calibrate -> evaluate model vs baseline.

    Returns (model_eval, baseline_eval, reliability, odds, artifacts)
    where artifacts = (scaler, calibrated_classifier) for the dashboard.
    """
    X = np.array([[r[f] for f in features] for r in rows], dtype=float)
    y = np.array([r["chronic_next"] for r in rows], dtype=int)
    idx = np.arange(len(rows))
    train_idx, test_idx = train_test_split(
        idx, test_size=0.25, random_state=seed, stratify=y
    )
    fit_idx, cal_idx = train_test_split(
        train_idx, test_size=0.3, random_state=seed, stratify=y[train_idx]
    )

    scaler, clf = fit(X[fit_idx], y[fit_idx], seed=seed)
    cal = calibrate(scaler, clf, X[cal_idx], y[cal_idx])

    proba = cal.predict_proba(scaler.transform(X[test_idx]))[:, 1]
    model_eval = evaluate(y[test_idx], proba)
    base_hat = baseline_predict([rows[i] for i in test_idx])
    base_eval = baseline_evaluate(y[test_idx], base_hat)

    # Fair fight: model precision at the baseline's recall level.
    from sklearn.metrics import precision_recall_curve

    prec, rec, thresh = precision_recall_curve(y[test_idx], proba)
    target_rec = base_eval["recall"]
    # find the threshold whose recall is closest to (but >=) the baseline's
    best = None
    for p, r, t in zip(prec, rec, np.append(thresh, 1.0)):
        if r >= target_rec and (best is None or r < best[1]):
            best = (p, r, t)
    matched = (
        {
            "precision": round(float(best[0]), 4),
            "recall": round(float(best[1]), 4),
            "threshold": round(float(best[2]), 4),
        }
        if best
        else None
    )
    model_eval["at_baseline_recall"] = matched

    return (
        model_eval,
        base_eval,
        reliability_curve(y[test_idx], proba),
        odds_ratios(clf, features),
        (scaler, cal),
    )
