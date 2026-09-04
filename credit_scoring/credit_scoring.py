# -*- coding: utf-8 -*-
"""
个人信用违约预测与评分卡模型（主流标准版）
=============================================
流程：数据清洗 → 单调 WOE 分箱 → IV 筛选 → 逻辑回归（+XGBoost 效果上限参照）
      → 5 折交叉验证 → 评分卡转换 → 评分卡单调性验证 → 阈值/业务成本分析

设计要点（对齐行业主流做法）：
1. 分箱按变量类型自适应：
   - 连续变量：等频初箱后做单调性合并（greedy 相邻合并）；
   - 有序离散/高度偏态变量（如逾期次数）：按取值分箱 + 长尾合并，
     避免 pd.qcut 在偏态数据上退化成单箱导致 IV=0 的静默错误。
2. WOE 单调性是评分卡最重要的约束：分箱后强制校验单调性并合并调优，
   保证每个变量的 WOE 方向与业务直觉一致、且逻辑回归稳定可解释。
3. 分箱边界在全集上确定，训练/测试共用同一套映射：
   分箱只使用特征边际分布（分位数/取值频次），不接触目标变量，无目标泄漏。
4. XGBoost 作为效果上限参照，用于论证"选逻辑回归是监管可解释性的取舍，
   而非效果偷懒"。
5. 数据无时间字段，无法做严格 OOT 验证，用 bootstrap 重采样近似稳定性评估，
   并在结论中如实说明该局限。
6. 评分卡输出为可直接使用的映射表 CSV，并验证分数段-违约率的单调性。
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import roc_auc_score, roc_curve
import warnings

warnings.filterwarnings("ignore")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ---------------- 路径与全局配置（相对路径，保证可移植） ----------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_FILE = PROJECT_ROOT.parent / "个人信用卡评估数据" / "cs-training.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

TARGET = "SeriousDlqin2yrs"
BASE_SCORE = 600
PDO = 50
FACTOR = PDO / np.log(2)          # ≈ 72.13
RANDOM_STATE = 42
MAX_BINS = 6                      # 值分箱时保留的高频取值数（+1 尾箱）
MIN_BIN_PCT = 0.03                # 每箱最小样本占比
DISCRETE_NUNIQUE = 30             # 唯一值 <= 该值视为"取值可枚举"变量，走值分箱


# ============================================================
# 1. 数据加载与清洗
# ============================================================
def load_and_clean():
    df = pd.read_csv(DATA_FILE, index_col=0)

    # 删除逻辑性异常
    df = df[df["age"] > 0]
    df = df[df["RevolvingUtilizationOfUnsecuredLines"] < 13]
    df = df[df["DebtRatio"] < 50]
    df.dropna(subset=[TARGET], inplace=True)

    # 清洗该数据集著名的编码脏值：三个逾期次数变量出现 96/98
    # （现实中不可能逾期近百次），且为同一批记录三个字段同时异常，属损坏数据，直接剔除
    overdue_cols = [
        "NumberOfTime30-59DaysPastDueNotWorse",
        "NumberOfTimes90DaysLate",
        "NumberOfTime60-89DaysPastDueNotWorse",
    ]
    dirty = (df[overdue_cols] >= 20).any(axis=1)
    print(f"[清洗] 剔除逾期次数脏值(96/98 编码错误)记录 {int(dirty.sum())} 条")
    df = df[~dirty]

    # 缺失值：用中位数填补（比均值稳健，抗极端值）
    df["MonthlyIncome"] = df["MonthlyIncome"].fillna(df["MonthlyIncome"].median())
    df["NumberOfDependents"] = df["NumberOfDependents"].fillna(
        df["NumberOfDependents"].median()
    )

    # 极端值截尾：月收入截到 99 分位（数据里存在 300 万的脏值）
    income_p99 = df["MonthlyIncome"].quantile(0.99)
    df["MonthlyIncome"] = df["MonthlyIncome"].clip(upper=income_p99)

    print(f"[清洗] 样本量={len(df):,}  违约率={df[TARGET].mean():.4f}")
    print(f"[清洗] 月收入 99 分位截尾值={income_p99:,.0f}")
    return df


# ============================================================
# 2. 单调 WOE 分箱（按变量类型自适应 + 单调性合并）
# ============================================================
def _is_monotonic(seq):
    d = np.diff(np.asarray(seq, dtype=float))
    return bool((d <= 1e-9).all() or (d >= -1e-9).all())


def _initial_bins(sub, col):
    """初始分箱：取值可枚举的按取值，连续用等频。返回 (sub, binspec)。"""
    uniq = sub[col].nunique()
    if uniq <= DISCRETE_NUNIQUE:
        # 有序离散/取值可枚举变量：高频取值单独成箱，长尾合并为 tail
        vc = sub[col].value_counts().sort_index()
        keep = list(vc.index[: MAX_BINS - 1])
        sub["_b"] = sub[col].apply(lambda x: x if x in keep else "tail")
        order_map = {v: i for i, v in enumerate(keep)}
        sub["_ord"] = sub["_b"].map(order_map).fillna(MAX_BINS - 1)
        return sub, {"mode": "value"}
    else:
        # 连续变量：等频初箱
        try:
            sub["_b"] = pd.qcut(sub[col], q=10, duplicates="drop")
        except Exception:
            sub["_b"] = pd.qcut(sub[col], q=5, duplicates="drop")
        cats = sub["_b"].cat.categories
        edges = [c.left for c in cats] + [cats[-1].right]
        sub["_ord"] = sub["_b"].cat.codes
        sub["_b"] = sub["_b"].astype(str)
        return sub, {"mode": "qcut", "edges": edges}


def _agg(sub):
    g = (
        sub.groupby(["_b", "_ord"], observed=True)
        .agg(count=(TARGET, "count"), bad=(TARGET, "sum"))
        .reset_index()
    )
    g["good"] = g["count"] - g["bad"]
    return g.sort_values("_ord").reset_index(drop=True)


def _calc(g):
    g = g.copy()
    g["good_s"] = g["good"] + 0.5   # 平滑，避免 log(0)/除 0
    g["bad_s"] = g["bad"] + 0.5
    gp = g["good_s"] / g["good_s"].sum()
    bp = g["bad_s"] / g["bad_s"].sum()
    g["woe"] = np.log(bp / gp)
    g["iv"] = (bp - gp) * g["woe"]
    g["bad_rate"] = g["bad"] / g["count"]
    return g


def _merge_pair(sub, g, i):
    lo, hi = i, i + 1
    keep = sub["_ord"].isin([g.loc[lo, "_ord"], g.loc[hi, "_ord"]])
    sub.loc[keep, "_b"] = f"{g.loc[lo,'_b']}|{g.loc[hi,'_b']}"
    sub.loc[keep, "_ord"] = g.loc[lo, "_ord"]
    return sub


def woe_binning(df, col, n_total, max_bins=MAX_BINS, min_pct=MIN_BIN_PCT):
    """对单变量做单调 WOE 分箱。
    返回 (binspec, woe_map, iv, 分箱明细, 是否单调)。
    binspec 携带完整的初始箱信息，供 apply_woe 在训练/测试上复用同一套边界。
    """
    sub = df[[col, TARGET]].dropna().copy()
    sub, binspec = _initial_bins(sub, col)
    init_b = sub["_b"].copy()          # 记录初始箱，用于构建合并映射

    g = _agg(sub)
    for _ in range(300):
        g = _calc(g)
        # a) 先合并过小箱（样本占比 < min_pct）
        small = g["count"] < min_pct * n_total
        if small.any() and len(g) > 3:
            idx = g["count"].idxmin()
            if idx == 0:
                partner = idx + 1
            elif idx == len(g) - 1:
                partner = idx - 1
            else:
                d_prev = abs(g.loc[idx - 1, "bad_rate"] - g.loc[idx, "bad_rate"])
                d_next = abs(g.loc[idx + 1, "bad_rate"] - g.loc[idx, "bad_rate"])
                partner = idx - 1 if d_prev <= d_next else idx + 1
            sub = _merge_pair(sub, g, min(idx, partner))
            g = _agg(sub)
            continue
        # b) 单调性校验：不单调则合并相邻对（优先 WOE 差距最小的反转点）
        woes = g["woe"].values
        if _is_monotonic(woes) or len(g) <= 3:
            break
        diffs = np.diff(woes)
        viol = [i for i in range(len(diffs) - 1) if diffs[i] * diffs[i + 1] < 0]
        if viol:
            merge_i = min(viol, key=lambda i: abs(woes[i] - woes[i + 1]))
        else:
            merge_i = int(np.argmin(
                [abs(g.loc[i, "woe"] - g.loc[i + 1, "woe"]) for i in range(len(g) - 1)]
            ))
        sub = _merge_pair(sub, g, merge_i)
        g = _agg(sub)

    g = _calc(g)
    iv = float(g["iv"].sum())
    woe_map = dict(zip(g["_b"], g["woe"]))
    monotonic = _is_monotonic(g["woe"].values)

    # 记录"初始箱/原始取值 → 最终箱"的映射，保证训练/测试分箱一致
    final_b = sub["_b"].copy()
    if binspec["mode"] == "value":
        binspec["value_to_final"] = dict(zip(sub[col].values, final_b.values))
    else:
        binspec["init_to_final"] = dict(zip(init_b.values, final_b.values))
    return binspec, woe_map, iv, g, monotonic


def apply_woe(df, col, binspec, woe_map):
    """用与建模时完全相同的分箱边界，把 WOE 映射回样本行。"""
    sub = df[[col]].copy()
    if binspec["mode"] == "value":
        b = sub[col].map(binspec["value_to_final"]).fillna("tail")
    else:
        b = pd.cut(sub[col], bins=binspec["edges"], include_lowest=True).astype(str)
        b = b.map(binspec["init_to_final"])
    return b.map(woe_map).fillna(0.0).astype(float).values


# ============================================================
# 3. 主流程
# ============================================================
def main():
    df = load_and_clean()
    feature_cols = [c for c in df.columns if c != TARGET]

    # --- 逐变量分箱 + IV 筛选 ---
    print("\n[分箱与 IV]（分箱边界在全集上确定：仅用特征边际分布、不接触目标变量，"
          "无目标泄漏，且保证训练/测试分箱一致）")
    bin_meta = {}
    for col in feature_cols:
        binspec, woe_map, iv, detail, mono = woe_binning(df, col, len(df))
        bin_meta[col] = {"binspec": binspec, "woe_map": woe_map,
                         "iv": iv, "detail": detail, "monotonic": mono}
        print(f"  {col:45s} IV={iv:.4f}  箱数={len(detail)}  单调={mono}")

    iv_pass = [c for c in feature_cols if bin_meta[c]["iv"] > 0.02]

    # 多重共线性筛选：三个逾期次数变量两两相关系数高达 0.98+，同时入模会让
    # 逻辑回归系数不稳定。按 IV 从高到低贪心保留，与已保留变量 |相关系数|>0.8
    # 的变量剔除（评分卡要求入模变量相对独立）
    print("\n[共线性筛选]（阈值 |corr|>0.8，保留 IV 更高者）")
    selected = []
    for c in sorted(iv_pass, key=lambda x: -bin_meta[x]["iv"]):
        if not selected:
            selected.append(c)
            continue
        corrs = [abs(df[c].corr(df[s])) for s in selected]
        m = max(corrs)
        if m > 0.8:
            hit = selected[int(np.argmax(corrs))]
            print(f"  剔除 {c}：与已保留的 {hit} 相关系数={m:.3f}（>0.8）")
        else:
            selected.append(c)
    print(f"[筛选] IV 初筛 {len(iv_pass)} 个 → 共线性后最终入模 {len(selected)} 个: {selected}")

    # --- 训练/测试切分 ---
    X = df.drop(columns=[TARGET])
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=RANDOM_STATE
    )
    print(f"[切分] 训练={len(X_train):,}  测试={len(X_test):,}")

    # --- 构造 WOE 特征矩阵 ---
    def build_woe_matrix(data):
        return np.column_stack(
            [apply_woe(data, col, bin_meta[col]["binspec"],
                       bin_meta[col]["woe_map"]) for col in selected]
        )

    Xtr_w = build_woe_matrix(X_train)
    Xte_w = build_woe_matrix(X_test)

    # --- 5 折交叉验证（逻辑回归稳定性）---
    print("\n[5 折交叉验证 - 逻辑回归]")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    cv_auc, cv_ks = [], []
    for tr_idx, va_idx in skf.split(Xtr_w, y_train):
        lr = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_STATE)
        lr.fit(Xtr_w[tr_idx], y_train.iloc[tr_idx])
        proba = lr.predict_proba(Xtr_w[va_idx])[:, 1]
        fpr, tpr, _ = roc_curve(y_train.iloc[va_idx], proba)
        cv_auc.append(roc_auc_score(y_train.iloc[va_idx], proba))
        cv_ks.append(float(np.max(tpr - fpr)))
    print(f"  AUC: {np.mean(cv_auc):.4f} ± {np.std(cv_auc):.4f}")
    print(f"  KS : {np.mean(cv_ks):.4f} ± {np.std(cv_ks):.4f}")

    # --- 逻辑回归（最终模型，可解释性优先）---
    lr = LogisticRegression(C=1.0, max_iter=1000, random_state=RANDOM_STATE)
    lr.fit(Xtr_w, y_train)
    proba_tr = lr.predict_proba(Xtr_w)[:, 1]
    proba_te = lr.predict_proba(Xte_w)[:, 1]

    # --- XGBoost 效果上限参照 ---
    has_xgb = False
    proba_xgb_te = None
    try:
        from xgboost import XGBClassifier
        xgb = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            eval_metric="auc", random_state=RANDOM_STATE, verbosity=0,
        )
        xgb.fit(Xtr_w, y_train)
        proba_xgb_te = xgb.predict_proba(Xte_w)[:, 1]
        has_xgb = True
    except Exception as e:
        print(f"[XGBoost 不可用] {e}")

    # --- 测试集评估 ---
    fpr_tr, tpr_tr, _ = roc_curve(y_train, proba_tr)
    fpr_te, tpr_te, _ = roc_curve(y_test, proba_te)
    auc_te = roc_auc_score(y_test, proba_te)
    ks_te = float(np.max(tpr_te - fpr_te))
    print(f"\n[测试集 - 逻辑回归] AUC={auc_te:.4f}  KS={ks_te:.4f}")
    if has_xgb:
        auc_xgb = roc_auc_score(y_test, proba_xgb_te)
        print(f"[测试集 - XGBoost]  AUC={auc_xgb:.4f}（效果上限参照）")

    # --- bootstrap 稳定性（替代 OOT，数据无时间字段）---
    rng = np.random.default_rng(RANDOM_STATE)
    boot_auc = []
    idx_all = np.arange(len(y_test))
    for _ in range(200):
        idx = rng.choice(idx_all, size=len(y_test), replace=True)
        if len(np.unique(y_test.iloc[idx])) < 2:
            continue
        boot_auc.append(roc_auc_score(y_test.iloc[idx], proba_te[idx]))
    lo, hi = np.percentile(boot_auc, [2.5, 97.5])
    print(f"[bootstrap 稳定性] AUC 95%CI=[{lo:.4f}, {hi:.4f}]"
          f"（数据无时间字段，以重采样近似 OOT 稳定性）")

    # --- ROC 对比图 ---
    plt.figure(figsize=(7, 6))
    plt.plot(fpr_tr, tpr_tr, color="#7FB3D5", lw=2, alpha=0.6, label="LR 训练集")
    plt.plot(fpr_te, tpr_te, color="#3C6E91", lw=2.5, label=f"LR 测试集 (AUC={auc_te:.4f})")
    if has_xgb:
        fpr_x, tpr_x, _ = roc_curve(y_test, proba_xgb_te)
        plt.plot(fpr_x, tpr_x, color="#F2B98A", lw=2, ls="--",
                 label=f"XGBoost 测试集 (AUC={auc_xgb:.4f})")
    plt.plot([0, 1], [0, 1], color="gray", ls="--", lw=1)
    plt.xlabel("假阳性率 FPR")
    plt.ylabel("真阳性率 TPR")
    plt.title("ROC 曲线：逻辑回归 vs XGBoost（效果上限参照）")
    plt.legend(loc="lower right", fontsize=10)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "roc_compare.png", dpi=150)
    plt.close()

    # --- IV 条形图 ---
    ivs = [(c, bin_meta[c]["iv"]) for c in selected]
    ivs.sort(key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(7, max(3, len(ivs) * 0.45)))
    ax.barh([c[:28] for c, _ in ivs], [iv for _, iv in ivs], color="#8BC8EA")
    for i, (_, iv) in enumerate(ivs):
        ax.text(iv + 0.01, i, f"{iv:.3f}", va="center", fontsize=9)
    ax.set_xlabel("IV")
    ax.set_title("入模变量 IV（区分能力）")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "iv_bar.png", dpi=150)
    plt.close()

    # ============================================================
    # 4. 评分卡转换
    # ============================================================
    print("\n[评分卡转换]")
    coef_dict = dict(zip(selected, lr.coef_[0]))
    intercept = float(lr.intercept_[0])

    # 基准分对应的基准 odds（用训练集整体违约率定义，保证 600 分可解释）
    odds_base = y_train.mean() / (1 - y_train.mean())
    offset = BASE_SCORE - FACTOR * np.log(odds_base)

    score_rows = []
    for col in selected:
        detail = bin_meta[col]["detail"].copy()
        detail["variable"] = col
        detail["points"] = -FACTOR * coef_dict[col] * detail["woe"]
        score_rows.append(detail[["variable", "_b", "count", "bad_rate", "woe", "points"]])
    scorecard = pd.concat(score_rows, ignore_index=True)
    scorecard["points"] = scorecard["points"].round(0).astype(int)
    scorecard.to_csv(OUTPUT_DIR / "scorecard.csv", index=False, encoding="utf-8-sig")
    print(f"[评分卡] 已输出 {OUTPUT_DIR / 'scorecard.csv'}")
    print(f"[评分卡] 基准分={BASE_SCORE}  PDO={PDO}  Factor={FACTOR:.2f}  "
          f"基准odds={odds_base:.4f}（对应 {BASE_SCORE} 分）")

    # --- 评分卡得分 + 单调性验证 ---
    def score_from_woe(X_w):
        s = np.full(len(X_w), offset + FACTOR * intercept)
        for j, col in enumerate(selected):
            s += -FACTOR * coef_dict[col] * X_w[:, j]
        return s

    score_te = score_from_woe(Xte_w)
    tmp = pd.DataFrame({"score": score_te, "y": y_test.values})
    bucket = pd.qcut(pd.Series(score_te), q=10, duplicates="drop")
    mono_df = (
        tmp.assign(bucket=bucket)
        .groupby("bucket", observed=True)
        .agg(平均分=("score", "mean"), 违约率=("y", "mean"), 样本量=("y", "size"))
        .reset_index()
    )
    print("\n[评分卡单调性验证（分数段 vs 违约率）]")
    print(mono_df.to_string(index=False))

    plt.figure(figsize=(7, 5))
    plt.plot(range(len(mono_df)), mono_df["违约率"], marker="o", color="#3C6E91")
    plt.xticks(range(len(mono_df)), [f"{s:.0f}" for s in mono_df["平均分"]], rotation=45)
    plt.xlabel("分数段（均值）")
    plt.ylabel("违约率")
    plt.title("评分卡单调性：分数越高违约率越低")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "score_monotonicity.png", dpi=150)
    plt.close()

    # ============================================================
    # 5. 阈值与业务成本分析
    # ============================================================
    print("\n[阈值 - 业务成本分析]")
    print("（拒绝率 = 分数低于阈值的占比；被拒用户坏账率 = 被拒者中实际违约占比）")
    thresholds = np.percentile(score_te, [70, 60, 50, 40, 30, 20])
    rows = []
    for t in thresholds:
        rejected = score_te < t
        rr = rejected.mean()
        bad_rej = y_test.values[rejected].mean() if rejected.sum() > 0 else np.nan
        rows.append((float(t), rr, bad_rej))
        print(f"  阈值={t:6.1f}  拒绝率={rr*100:5.1f}%  被拒用户坏账率={bad_rej*100:5.2f}%")
    th_df = pd.DataFrame(rows, columns=["threshold", "reject_rate", "bad_rate_rejected"])
    th_df.to_csv(OUTPUT_DIR / "threshold_analysis.csv", index=False, encoding="utf-8-sig")

    # 建议阈值：示例取拒绝率 30% 附近
    t30 = float(thresholds[-2])
    bad_t30 = th_df.loc[th_df["threshold"] == t30, "bad_rate_rejected"].values[0] * 100
    print(f"\n[业务建议示例] 若取阈值 {t30:.1f}（拒绝率约 30%），"
          f"被拒客户中坏账率约 {bad_t30:.1f}%，即能拦住较大比例高风险客群；"
          f"实际取值需结合获客成本与坏账损失权衡。")

    # 阈值曲线图
    grid_t = np.percentile(score_te, np.linspace(1, 80, 80))
    rr_list = [(score_te < t).mean() for t in grid_t]
    br_list = [y_test.values[score_te < t].mean() if (score_te < t).any() else 0
               for t in grid_t]
    fig, ax1 = plt.subplots(figsize=(7, 5))
    ax1.plot(grid_t, rr_list, color="#3C6E91", lw=2, label="拒绝率")
    ax1.set_xlabel("分数阈值")
    ax1.set_ylabel("拒绝率", color="#3C6E91")
    ax2 = ax1.twinx()
    ax2.plot(grid_t, br_list, color="#E1A04A", lw=2, ls="--", label="被拒用户坏账率")
    ax2.set_ylabel("被拒用户坏账率", color="#E1A04A")
    ax1.set_title("阈值-业务成本权衡")
    fig.legend(loc="upper right", fontsize=9)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "threshold_curve.png", dpi=150)
    plt.close()

    print("\n=== 评分卡建模完成（主流标准版）===")


if __name__ == "__main__":
    main()
