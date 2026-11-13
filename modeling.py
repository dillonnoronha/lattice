"""Reproducible evaluation with preprocessing fitted independently in every split."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, precision_score, recall_score, f1_score)
from sklearn.model_selection import GroupKFold, GroupShuffleSplit, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MODEL_VERSION = "2.0"


def composition_groups(df: pd.DataFrame) -> pd.Series:
    """Group equivalent site compositions, including scaled stoichiometry."""
    def key(row):
        sites = []
        totals = []
        for fields in [[("A", "AN"), ("AP", "APN")],
                       [("B", "BN"), ("BP", "BPN"), ("BDP", "BDPN")], [("O", "ON")]]:
            values = {}
            for symbol, ratio in fields:
                raw_symbol = row.get(symbol, "")
                s = "" if pd.isna(raw_symbol) else str(raw_symbol).strip()
                n = pd.to_numeric(row.get(ratio, 0), errors="coerce")
                if s and pd.notna(n) and n > 0:
                    values[s] = values.get(s, 0) + float(n)
            sites.append(values)
            totals.extend(values.values())
        scale = sum(totals) or 1
        return "|".join(",".join(f"{s}:{v/scale:.8f}" for s, v in sorted(site.items())) for site in sites)
    return df.apply(key, axis=1)


def feature_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = df.reindex(columns=columns).apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)
    for symbol, ratio in [("AP", "APN"), ("BP", "BPN"), ("BDP", "BDPN")]:
        if symbol in df and ratio in frame:
            absent = df[symbol].fillna("").astype(str).str.strip().eq("")
            frame.loc[absent & frame[ratio].isna(), ratio] = 0.0
    return frame


def new_estimator(seed: int, logistic: bool = False) -> Pipeline:
    steps = [("impute", SimpleImputer(strategy="median", keep_empty_features=True))]
    if logistic:
        steps += [("scale", StandardScaler()), ("model", LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=seed))]
    else:
        steps += [("model", RandomForestClassifier(n_estimators=150, max_depth=7,
                   min_samples_leaf=2, class_weight="balanced_subsample", random_state=seed, n_jobs=1))]
    return Pipeline(steps)


def evaluate(df: pd.DataFrame, target: str = "bubble", use_phase: bool = False,
             use_mass: bool = False, random_state: int = 42,
             evaluation: str = "composition", holdout_semester: str = "") -> dict:
    from pipeline import feature_columns
    label = "Bub" if target == "bubble" else "P"
    mapping = {"yes": 1, "no": 0} if target == "bubble" else {"pure": 1, "impure": 0}
    if label not in df:
        return {"ok": False, "message": "No outcome labels available."}
    eligible = df[label].isin(mapping)
    if target == "bubble" and "P" in df:
        eligible &= df["P"].ne("not made")
    if use_phase and target == "bubble" and "P" in df:
        eligible &= df["P"].isin(["pure", "impure"])
    # Outcome labels do not make an invalid composition suitable for training.
    for column in ["AN", "BN", "ON"]:
        if column in df:
            values = pd.to_numeric(df[column], errors="coerce")
            eligible &= np.isfinite(values) & (values > 0)
    for element, amount in [("AP", "APN"), ("BP", "BPN"), ("BDP", "BDPN")]:
        if element in df and amount in df:
            present = df[element].fillna("").astype(str).str.strip().ne("")
            ratios = pd.to_numeric(df[amount], errors="coerce")
            eligible &= (~present & (ratios.isna() | ratios.eq(0))) | (present & np.isfinite(ratios) & ratios.gt(0))
    d = df[eligible].copy().reset_index(drop=True)
    if len(d) < 10:
        return {"ok": False, "message": "Model needs at least 10 labeled compound rows with confirmed outcomes."}
    y = d[label].map(mapping).astype(int)
    if y.nunique() < 2:
        return {"ok": False, "message": "Model needs both bubble=yes and bubble=no examples." if target == "bubble"
                else "Model needs both pure and impure examples."}
    if y.value_counts().min() < 2:
        return {"ok": False, "message": "At least two examples of each outcome are needed for evaluation."}
    columns = [c for c in feature_columns(use_phase and target == "bubble", use_mass)[0] if c in d]
    if not columns:
        return {"ok": False, "message": "No composition descriptors are available."}
    X = feature_frame(d, columns)
    groups = composition_groups(d)
    indices = np.arange(len(d))
    if evaluation == "semester":
        semesters = d.get("Semester", pd.Series("", index=d.index)).fillna("").astype(str)
        test = indices[semesters.eq(holdout_semester)]
        train = indices[~semesters.eq(holdout_semester)]
        split_label = f"Held-out semester: {holdout_semester}"
    elif evaluation == "composition":
        if groups.nunique() < 3:
            return {"ok": False, "message": "Unseen-composition evaluation needs at least three distinct compositions. Add data or explicitly choose row evaluation."}
        train, test = next(GroupShuffleSplit(n_splits=1, test_size=.25, random_state=random_state).split(X, y, groups))
        split_label = "Unseen compositions"
    else:
        train, test = train_test_split(indices, test_size=.25 if len(d) >= 20 else .35,
                                      random_state=random_state, stratify=y)
        split_label = "Stratified rows (related compositions may overlap)"
    if not len(test) or not len(train) or y.iloc[train].nunique() < 2:
        return {"ok": False, "message": "This split cannot train both outcomes. Choose another evaluation or collect more independent examples."}
    rf = new_estimator(random_state).fit(X.iloc[train], y.iloc[train])
    lr = new_estimator(random_state, True).fit(X.iloc[train], y.iloc[train])
    pred = rf.predict(X.iloc[test])
    prob = rf.predict_proba(X.iloc[test])[:, 1]
    truth = y.iloc[test]
    majority = int(y.iloc[train].mode()[0])
    cm = confusion_matrix(truth, pred, labels=[0, 1]).ravel()
    accuracy = float(accuracy_score(truth, pred))
    baseline = float(accuracy_score(truth, [majority] * len(test)))

    # Semester holdout remains untouched; CV uses only its training semesters.
    cv_X = X.iloc[train] if evaluation == "semester" else X
    cv_y = y.iloc[train] if evaluation == "semester" else y
    cv_groups = groups.iloc[train] if evaluation == "semester" else groups
    splits = []
    if evaluation in {"composition", "semester"}:
        n = min(5, cv_groups.nunique())
        if n >= 3:
            splits = list(GroupKFold(n_splits=n).split(cv_X, cv_y, cv_groups))
    else:
        n = min(5, int(cv_y.value_counts().min()))
        if n >= 3:
            splits = list(StratifiedKFold(n_splits=n, shuffle=True, random_state=random_state).split(cv_X, cv_y))
    scores = []
    for a, b in splits:
        if cv_y.iloc[a].nunique() == 2 and cv_y.iloc[b].nunique() == 2:
            fitted = clone(rf).fit(cv_X.iloc[a], cv_y.iloc[a])
            scores.append(float(accuracy_score(cv_y.iloc[b], fitted.predict(cv_X.iloc[b]))))

    # Diagnostics describe the held-out model; prediction uses a separate refit.
    importance = pd.DataFrame({"Feature": columns, "Importance": rf.named_steps["model"].feature_importances_})
    importance = importance.sort_values("Importance", ascending=False).head(12)
    final_model = clone(rf).fit(X, y)
    warnings = ["Exploratory model scores are not calibrated probabilities or evidence of causation."]
    if len(test) < 20:
        warnings.append(f"Only {len(test)} held-out observations; estimates are unstable.")
    if truth.nunique() < 2:
        warnings.append("The holdout contains only one outcome; balanced performance cannot be assessed.")
    if evaluation == "rows" and set(groups.iloc[train]) & set(groups.iloc[test]):
        warnings.append("Related compositions occur in both training and testing.")
    if splits and len(scores) != len(splits):
        warnings.append(f"{len(splits)-len(scores)} CV fold(s) lacked both outcomes and were omitted.")
    metrics = dict(ok=True, model=final_model, feature_columns=columns, model_version=MODEL_VERSION,
        rf_accuracy=accuracy, accuracy=accuracy, lr_accuracy=float(accuracy_score(truth, lr.predict(X.iloc[test]))),
        rf_precision=float(precision_score(truth, pred, zero_division=0)),
        precision=float(precision_score(truth, pred, zero_division=0)),
        rf_recall=float(recall_score(truth, pred, zero_division=0)),
        rf_f1=float(f1_score(truth, pred, zero_division=0)),
        balanced_accuracy=float(balanced_accuracy_score(truth, pred)) if truth.nunique() == 2 else None,
        brier_score=float(brier_score_loss(truth, prob)), baseline_accuracy=baseline,
        yes_count=int(y.sum()), no_count=int((y == 0).sum()), pure_count=int(y.sum()),
        impure_count=int((y == 0).sum()), training_rows=len(train), testing_rows=len(test),
        labeled_rows=len(d), excluded_rows=len(df)-len(d), yes_rate=float(y.mean()), importance=importance,
        confusion=dict(zip(["tn", "fp", "fn", "tp"], map(int, cm))),
        cv_mean=float(np.mean(scores)) if scores else None,
        cv_std=float(np.std(scores)) if scores else None, cv_folds=len(scores),
        evaluation=split_label, overfit_warning=" ".join(warnings),
        train_indices=train.tolist(), test_indices=test.tolist(),
        training_compositions=sorted(set(groups.iloc[train])), test_compositions=sorted(set(groups.iloc[test])),
        evaluated_imputer=rf.named_steps["impute"].statistics_.tolist(),
        known_elements=sorted({str(v) for c in ["A", "AP", "B", "BP", "BDP"] if c in d
                               for v in d[c].dropna() if str(v).strip()}),
        feature_min=X.min().to_dict(), feature_max=X.max().to_dict())
    return metrics


def predict_candidate(result: dict, row: pd.DataFrame) -> dict:
    """Predict using the saved fitted transformation and describe support limits."""
    X = feature_frame(row, result["feature_columns"])
    elements = {str(row.iloc[0].get(c, "")) for c in ["A", "AP", "B", "BP", "BDP"]} - {"", "nan", "None"}
    unfamiliar = sorted(elements - set(result["known_elements"]))
    missing = X.columns[X.iloc[0].isna()].tolist()
    outside = [c for c in X if pd.notna(X.iloc[0][c]) and
               (X.iloc[0][c] < result["feature_min"][c] or X.iloc[0][c] > result["feature_max"][c])]
    return {"score": float(result["model"].predict_proba(X)[0, 1]), "unfamiliar_elements": unfamiliar,
            "missing_descriptors": missing, "outside_range": outside,
            "support": "Limited" if unfamiliar or outside or missing else "Within observed descriptor ranges"}
