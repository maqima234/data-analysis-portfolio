"""
个人信用违约预测与评分卡模型构建
流程：数据清洗 → WOE/IV → 逻辑回归 → 评分卡 → 评估（训练集+测试集）
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import warnings
warnings.filterwarnings('ignore')
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve
from sklearn.model_selection import train_test_split

target = 'SeriousDlqin2yrs'

# ============================================================
# 数据加载与清洗
# ============================================================
print('数据清洗...')

df = pd.read_csv(r'C:\Users\86186\Desktop\credit_risk_project\data\cs-training.csv', index_col=0)

df = df[df['age'] > 0]
df = df[df['RevolvingUtilizationOfUnsecuredLines'] < 13]
df = df[df['DebtRatio'] < 50]
df.dropna(subset=[target], inplace=True)
df['MonthlyIncome'] = df['MonthlyIncome'].fillna(df['MonthlyIncome'].median())
df['NumberOfDependents'] = df['NumberOfDependents'].fillna(df['NumberOfDependents'].median())

print(f'清洗后样本量: {len(df):,}')
print(f'违约率: {df[target].mean()*100:.2f}%')

# ============================================================
# IV 筛选
# ============================================================
print('\nIV 筛选...')

feature_cols = [c for c in df.columns if c != target]
iv_results = {}

for col in feature_cols:
    try:
        df_temp = df[[col, target]].dropna()
        df_temp['bin'] = pd.qcut(df_temp[col], q=5, duplicates='drop')
        grouped = df_temp.groupby('bin')[target].agg(['count', 'sum'])
        grouped['good'] = grouped['count'] - grouped['sum']
        grouped['bad'] = grouped['sum']
        grouped['good_pct'] = grouped['good'] / grouped['good'].sum()
        grouped['bad_pct'] = grouped['bad'] / grouped['bad'].sum()
        grouped['woe'] = np.log(grouped['bad_pct'] / grouped['good_pct'])
        grouped['iv'] = (grouped['bad_pct'] - grouped['good_pct']) * grouped['woe']
        iv_results[col] = grouped['iv'].sum()
    except:
        pass

print('变量IV值:')
for col, iv in sorted(iv_results.items(), key=lambda x: x[1], reverse=True):
    selected = iv > 0.02
    print(f'  [{"IN" if selected else "OUT"}] {col:45s} IV = {iv:.4f}')

selected_vars = [v for v, iv in iv_results.items() if iv > 0.02]
print(f'入模变量: {len(selected_vars)} 个')

# ============================================================
# WOE编码 + 切分训练/测试集 + 建模
# ============================================================
print('\nWOE编码与建模...')

df_woe = df[[target]].copy()
for col in selected_vars:
    df_temp = df[[col, target]].dropna()
    df_temp['bin'] = pd.qcut(df_temp[col], q=5, duplicates='drop')
    grouped = df_temp.groupby('bin')[target].agg(['count', 'sum'])
    grouped['good'] = grouped['count'] - grouped['sum']
    grouped['bad'] = grouped['sum']
    grouped['good_pct'] = grouped['good'] / grouped['good'].sum()
    grouped['bad_pct'] = grouped['bad'] / grouped['bad'].sum()
    grouped['woe'] = np.log(grouped['bad_pct'] / grouped['good_pct'])
    df_woe[col + '_woe'] = df[col].map(dict(grouped['woe'])).fillna(0.0).astype(float)

woe_cols = [c for c in df_woe.columns if c.endswith('_woe')]
print(f'WOE特征列: {len(woe_cols)}')

# 切分
X = df_woe[woe_cols]
y = df_woe[target]
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42, stratify=y
)
print(f'训练集: {len(X_train):,}  |  测试集: {len(X_test):,}')

# 建模
lr = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
lr.fit(X_train, y_train)

print('模型系数:')
for col, coef in zip(woe_cols, lr.coef_[0]):
    print(f'  {col.replace("_woe",""):40s} coef = {coef:.4f}')
print(f'  截距 = {lr.intercept_[0]:.4f}')

# ============================================================
# 评分卡转换
# ============================================================
print('\n评分卡转换...')

base_score = 600
pdo = 50
factor = pdo / np.log(2)

score_vars = ['RevolvingUtilizationOfUnsecuredLines', 'age', 'DebtRatio',
              'MonthlyIncome', 'NumberOfOpenCreditLinesAndLoans', 'NumberOfDependents']
score_vars = [v for v in score_vars if v in selected_vars]

print(f'基准分={base_score}, PDO={pdo}, Factor={factor:.2f}')
for col in score_vars:
    woe_col = col + '_woe'
    if woe_col not in woe_cols:
        continue
    coef = lr.coef_[0][woe_cols.index(woe_col)]
    df_temp = df[[col, target]].dropna()
    df_temp['bin'] = pd.qcut(df_temp[col], q=5, duplicates='drop')
    grouped = df_temp.groupby('bin')[target].agg(['count', 'sum'])
    grouped['good'] = grouped['count'] - grouped['sum']
    grouped['bad'] = grouped['sum']
    grouped['woe'] = np.log(grouped['bad'] / grouped['good'] * grouped['good'].sum() / grouped['bad'].sum())
    print(f'\n  {col}:')
    for idx, row in grouped.iterrows():
        points = round(-coef * row['woe'] * factor, 0)
        print(f'    {str(idx):30s} WOE={row["woe"]:+.3f}  Score={points:+.0f}')

# ============================================================
# 模型评估
# ============================================================
print('\n模型评估...')

y_train_prob = lr.predict_proba(X_train)[:, 1]
y_test_prob = lr.predict_proba(X_test)[:, 1]

auc_train = roc_auc_score(y_train, y_train_prob)
fpr_train, tpr_train, _ = roc_curve(y_train, y_train_prob)
ks_train = max(tpr_train - fpr_train)

auc_test = roc_auc_score(y_test, y_test_prob)
fpr_test, tpr_test, thresholds_test = roc_curve(y_test, y_test_prob)
ks_test = max(tpr_test - fpr_test)

print(f'训练集 AUC: {auc_train:.4f}  |  KS: {ks_train:.4f}')
print(f'测试集 AUC: {auc_test:.4f}  |  KS: {ks_test:.4f}')

# ROC
plt.figure(figsize=(8, 6))
plt.plot(fpr_train, tpr_train, color='steelblue', lw=2, alpha=0.7, label=f'Train (AUC={auc_train:.4f})')
plt.plot(fpr_test, tpr_test, color='darkorange', lw=2, label=f'Test (AUC={auc_test:.4f})')
plt.plot([0, 1], [0, 1], color='gray', linestyle='--')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Curve')
plt.legend(loc='lower right')
plt.tight_layout()
plt.savefig('output_roc.png', dpi=150)
plt.close()

# KS
plt.figure(figsize=(8, 6))
plt.plot(thresholds_test, tpr_test, color='darkorange', label='TPR')
plt.plot(thresholds_test, fpr_test, color='steelblue', label='FPR')
plt.plot(thresholds_test, tpr_test - fpr_test, color='forestgreen', linewidth=2, label=f'KS={ks_test:.4f}')
plt.xlabel('Threshold')
plt.ylabel('Rate')
plt.title('KS Curve (Test Set)')
plt.legend()
plt.tight_layout()
plt.savefig('output_ks.png', dpi=150)
plt.close()

print('\n=== 最终评估总结 ===')
print(f'训练集 AUC: {auc_train:.4f}  |  KS: {ks_train:.4f}')
print(f'测试集 AUC: {auc_test:.4f}  |  KS: {ks_test:.4f}')
gap = auc_train - auc_test
print(f'过拟合程度: {"轻微" if gap < 0.05 else "明显"} (AUC差={gap:.4f})')
print(f'\n=== 风控项目完成 ===')
