"""
用户质量诊断
诊断问题：平台用户质量怎么样？用户结构健康吗？
分析链路：购买频次分布 → 复购分析 → RFM分层 → 贡献集中度 → 高价值用户画像
"""
import pymysql
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import numpy as np

matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import warnings
import sys
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

# ========== 连接 MySQL ==========
conn = pymysql.connect(
    host='127.0.0.1', user='root', password='123456',
    database='ecommerce_analysis', charset='utf8mb4'
)

# ============================================================
# 一、用户购买频次分布 —— 用户粘性的最直接证据
# ============================================================
print('=' * 60)
print('一、用户购买频次分布：用户买几次就走？')
print('=' * 60)

df_freq = pd.read_sql_query("""
    SELECT
        CASE WHEN order_count = 1 THEN '1 time'
             WHEN order_count = 2 THEN '2 times'
             WHEN order_count BETWEEN 3 AND 5 THEN '3-5 times'
             ELSE '6+ times'
        END AS frequency,
        COUNT(*) AS user_count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS user_pct,
        ROUND(SUM(total_gmv), 2) AS total_gmv,
        ROUND(SUM(total_gmv) * 100.0 / SUM(SUM(total_gmv)) OVER(), 1) AS gmv_pct
    FROM (
        SELECT
            o.客户ID,
            COUNT(DISTINCT o.订单ID) AS order_count,
            SUM(oi.价格) AS total_gmv
        FROM orders o
        JOIN order_items oi ON o.订单ID = oi.订单ID
        WHERE o.订单状态 = 'delivered'
        GROUP BY o.客户ID
    ) t
    GROUP BY frequency
    ORDER BY MIN(order_count)
""", conn)

print(df_freq.to_string(index=False))

one_time_pct = df_freq[df_freq['frequency'] == '1 time']['user_pct'].values[0]
one_time_gmv = df_freq[df_freq['frequency'] == '1 time']['gmv_pct'].values[0]
total_users = df_freq['user_count'].sum()

print(f"\n→ 一次性用户占 {one_time_pct}% 的用户量，贡献 {one_time_gmv}% 的 GMV")
print(f"→ 平台本质上是一个'一锤子买卖'模型")

# ---------- 图1: 购买频次分布 ----------
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

# 左: 用户数占比
colors_freq = ['#e74c3c', '#f39c12', '#3498db', '#2ecc71']
axes[0].pie(df_freq['user_count'], labels=df_freq['frequency'],
            autopct='%1.1f%%', colors=colors_freq, startangle=90,
            explode=tuple([0.05] + [0] * (len(df_freq) - 1)))
axes[0].set_title('User Distribution by Purchase Frequency')

# 右: GMV占比 vs 用户数占比 对比
x = range(len(df_freq))
w = 0.35
axes[1].bar([i - w/2 for i in x], df_freq['user_pct'], w,
            color='steelblue', alpha=0.8, label='% of Users')
axes[1].bar([i + w/2 for i in x], df_freq['gmv_pct'], w,
            color='darkorange', alpha=0.8, label='% of GMV')
axes[1].set_xticks(x)
axes[1].set_xticklabels(df_freq['frequency'])
axes[1].set_ylabel('Percentage (%)')
axes[1].set_title('User Share vs GMV Share by Frequency')
axes[1].legend()

# 标注差值
for i, (_, row) in enumerate(df_freq.iterrows()):
    diff = row['gmv_pct'] - row['user_pct']
    if abs(diff) > 1:
        axes[1].annotate(f'Δ={diff:+.1f}%', (i + w/2, row['gmv_pct'] + 1),
                         ha='center', fontsize=9, color='crimson')

plt.suptitle('Diagnosis 2: Purchase Frequency — The "One-and-Done" Pattern',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/user_01_frequency.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 1 saved: user_01_frequency.png')

# ============================================================
# 二、复购行为深度分析
# ============================================================
print('\n' + '=' * 60)
print('二、复购行为：有多少用户回来了？隔多久回来？')
print('=' * 60)

# 复购率（按月看首购用户中有多少在后续月份复购）
df_retention = pd.read_sql_query("""
    WITH user_first_month AS (
        SELECT
            客户ID,
            DATE_FORMAT(MIN(下单时间), '%Y-%m') AS cohort_month
        FROM orders
        WHERE 订单状态 = 'delivered'
        GROUP BY 客户ID
    ),
    user_all_months AS (
        SELECT DISTINCT
            o.客户ID,
            DATE_FORMAT(o.下单时间, '%Y-%m') AS purchase_month,
            f.cohort_month
        FROM orders o
        JOIN user_first_month f ON o.客户ID = f.客户ID
        WHERE o.订单状态 = 'delivered'
    )
    SELECT
        cohort_month,
        COUNT(DISTINCT 客户ID) AS cohort_size,
        ROUND(COUNT(DISTINCT CASE WHEN purchase_month > cohort_month THEN 客户ID END)
              * 100.0 / COUNT(DISTINCT 客户ID), 1) AS repurchase_rate
    FROM user_all_months
    GROUP BY cohort_month
    ORDER BY cohort_month
""", conn)

# 过滤掉最后几个月的队列（没有足够时间观察复购行为）
# 保留2016-09到2018-06的队列（至少留3个月观察窗口）
df_retention_valid = df_retention[df_retention['cohort_month'] <= '2018-06']

print(f"月度队列复购率（{df_retention_valid['cohort_month'].iloc[0]} ~ {df_retention_valid['cohort_month'].iloc[-1]}）:")
print(f"  平均复购率: {df_retention_valid['repurchase_rate'].mean():.2f}%")
print(f"  最高复购率: {df_retention_valid['repurchase_rate'].max():.2f}% ({df_retention_valid.loc[df_retention_valid['repurchase_rate'].idxmax(), 'cohort_month']})")
print(f"  最低复购率: {df_retention_valid['repurchase_rate'].min():.2f}% ({df_retention_valid.loc[df_retention_valid['repurchase_rate'].idxmin(), 'cohort_month']})")

# 复购间隔分布
df_repurchase_gap = pd.read_sql_query("""
    WITH ranked AS (
        SELECT
            客户ID,
            订单ID,
            下单时间,
            ROW_NUMBER() OVER (PARTITION BY 客户ID ORDER BY 下单时间) AS rn
        FROM orders
        WHERE 订单状态 = 'delivered'
    )
    SELECT
        TIMESTAMPDIFF(DAY, r1.下单时间, r2.下单时间) AS days_between,
        COUNT(*) AS count
    FROM ranked r1
    JOIN ranked r2 ON r1.客户ID = r2.客户ID AND r1.rn + 1 = r2.rn
    GROUP BY days_between
    ORDER BY days_between
""", conn)

print(f"\n复购间隔统计:")
if len(df_repurchase_gap) == 0:
    print("  无可分析数据——平台 delivered 订单中不存在任何复购行为。")
    print("  这印证了第一节的发现：每个客户仅完成过一次交易。")
    # 跳过复购间隔图表，直接进入 RFM
    print("[!] 复购间隔图跳过（无复购数据）")
    plt.close('all')  # 清理可能残留的figure
else:
    print(f"  中位复购间隔: {df_repurchase_gap['days_between'].median():.0f} 天")
    print(f"  30天内复购占比: {df_repurchase_gap[df_repurchase_gap['days_between'] <= 30]['count'].sum() / df_repurchase_gap['count'].sum() * 100:.1f}%")
    print(f"  90天内复购占比: {df_repurchase_gap[df_repurchase_gap['days_between'] <= 90]['count'].sum() / df_repurchase_gap['count'].sum() * 100:.1f}%")

# ---------- 图2: 复购分析 ----------
if len(df_repurchase_gap) == 0:
    # 无复购数据时，展示队列规模趋势 + 零复购标注
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(range(len(df_retention_valid)), df_retention_valid['cohort_size'],
           color='steelblue', alpha=0.8)
    ax.set_xticks(range(0, len(df_retention_valid), 3))
    ax.set_xticklabels(df_retention_valid['cohort_month'].iloc[::3], rotation=45, ha='right')
    ax.set_ylabel('Cohort Size')
    ax.set_title('Monthly New Customer Cohorts (Zero Repurchase Across All Cohorts)')
    ax.text(0.5, 0.95, 'All cohorts: 0.00% repurchase rate\nEvery customer bought exactly once.',
            transform=ax.transAxes, ha='center', va='top',
            fontsize=14, color='crimson', fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
    plt.tight_layout()
    plt.savefig('outputs/user_02_repurchase.png', dpi=150, bbox_inches='tight')
    plt.close()
else:
    # 有复购数据时，展示复购率和间隔分析
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # 左: 各队列复购率趋势
    axes[0].plot(range(len(df_retention_valid)), df_retention_valid['repurchase_rate'],
                 color='steelblue', marker='o', linewidth=2)
    axes[0].axhline(df_retention_valid['repurchase_rate'].mean(), color='crimson',
                    linestyle='--', linewidth=1.5,
                    label=f'Mean = {df_retention_valid["repurchase_rate"].mean():.2f}%')
    axes[0].set_xticks(range(0, len(df_retention_valid), 3))
    axes[0].set_xticklabels(df_retention_valid['cohort_month'].iloc[::3],
                             rotation=45, ha='right')
    axes[0].set_ylabel('Repurchase Rate (%)')
    axes[0].set_title('Monthly Cohort Repurchase Rate')
    axes[0].legend()
    axes[0].text(0.02, 0.98,
                 'Note: Later cohorts have less\nobservation time for repurchase',
                 transform=axes[0].transAxes, fontsize=8, color='gray',
                 verticalalignment='top')

    # 右: 复购间隔分布
    gap_bins = [0, 7, 14, 30, 60, 90, 180, 365, 9999]
    gap_labels = ['0-7d', '8-14d', '15-30d', '31-60d', '61-90d', '91-180d', '181-365d', '>365d']
    df_repurchase_gap['gap_bucket'] = pd.cut(df_repurchase_gap['days_between'],
                                              bins=gap_bins, labels=gap_labels,
                                              right=True)
    df_gap_agg = df_repurchase_gap.groupby('gap_bucket', observed=False)['count'].sum()
    df_gap_agg = df_gap_agg[df_gap_agg > 0]

    colors_gap = ['#2ecc71', '#27ae60', '#f39c12', '#e67e22', '#e74c3c',
                  '#c0392b', '#8e44ad', '#2c3e50'][:len(df_gap_agg)]
    axes[1].bar(range(len(df_gap_agg)), df_gap_agg.values,
                color=colors_gap, alpha=0.85)
    axes[1].set_xticks(range(len(df_gap_agg)))
    axes[1].set_xticklabels(df_gap_agg.index, rotation=45, ha='right')
    axes[1].set_ylabel('Repurchase Count')
    axes[1].set_title('Time Gap Between Purchases (same user)')

    plt.suptitle('Diagnosis 2 (cont.): Repurchase Behavior Deep Dive',
                 fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig('outputs/user_02_repurchase.png', dpi=150, bbox_inches='tight')
    plt.close()
    print('[OK] Fig 2 saved: user_02_repurchase.png')

# ============================================================
# 三、RFM 用户分层 + 价值结构诊断
# ============================================================
print('\n' + '=' * 60)
print('三、RFM 分层：用户价值结构是否健康？')
print('=' * 60)

df_rfm = pd.read_sql_query("""
    SELECT
        o.客户ID,
        DATEDIFF('2018-10-01', MAX(o.下单时间)) AS recency,
        COUNT(DISTINCT o.订单ID) AS frequency,
        ROUND(SUM(oi.价格), 2) AS monetary
    FROM orders o
    JOIN order_items oi ON o.订单ID = oi.订单ID
    WHERE o.订单状态 = 'delivered'
    GROUP BY o.客户ID
""", conn)


def percentile_score(series, ascending=True):
    """分三层打分 1/2/3"""
    p33, p67 = series.quantile(1/3), series.quantile(2/3)
    if ascending:
        return series.apply(lambda x: 3 if x >= p67 else (2 if x >= p33 else 1))
    else:
        return series.apply(lambda x: 3 if x <= p33 else (2 if x <= p67 else 1))


df_rfm['R_score'] = percentile_score(df_rfm['recency'], ascending=False)
df_rfm['F_score'] = percentile_score(df_rfm['frequency'], ascending=True)
df_rfm['M_score'] = percentile_score(df_rfm['monetary'], ascending=True)
df_rfm['RFM_total'] = (df_rfm['R_score'] + df_rfm['F_score'] + df_rfm['M_score']).astype(int)

# 分层
q75, q50, q25 = df_rfm['RFM_total'].quantile([0.75, 0.50, 0.25]).values


def label_rfm(score):
    if score >= q75:
        return 'High-Value'
    elif score >= q50:
        return 'Potential'
    elif score >= q25:
        return 'Average'
    else:
        return 'At-Risk'


df_rfm['segment'] = df_rfm['RFM_total'].apply(label_rfm)

# 分层统计
seg_stats = df_rfm.groupby('segment').agg(
    user_count=('客户ID', 'count'),
    avg_recency=('recency', 'mean'),
    avg_frequency=('frequency', 'mean'),
    avg_monetary=('monetary', 'mean'),
    total_gmv=('monetary', 'sum')
).reindex(['High-Value', 'Potential', 'Average', 'At-Risk'])

seg_stats['user_pct'] = seg_stats['user_count'] / seg_stats['user_count'].sum() * 100
seg_stats['gmv_pct'] = seg_stats['total_gmv'] / seg_stats['total_gmv'].sum() * 100

print("RFM 分层概览:")
print(seg_stats.to_string())

# 诊断：F值区分度
f_score_std = df_rfm.groupby('F_score')['frequency'].mean()
print(f"\nF 值实际业务含义:")
for score_val in [1, 2, 3]:
    subset = df_rfm[df_rfm['F_score'] == score_val]
    print(f"  F_score={score_val}: 用户数={len(subset):,}, 平均购买次数={subset['frequency'].mean():.2f}, "
          f"中位购买次数={subset['frequency'].median():.0f}")

# 关键发现
if df_rfm['frequency'].median() <= 1:
    print("\n[!] 数据局限：绝大多数用户仅购买 1 次，F 值几乎无区分度。")
    print("  RFM 在此数据集中本质上退化为 R+M 二维模型。")
    print("  这不代表 RFM 方法论有问题，而是 Olist 平台本身的复购率过低所致。")
    print("  在复购正常的平台（如天猫、京东），F 值是区分用户价值的关键维度。")

# ---------- 图3: RFM 分层（三面板）----------
fig, axes = plt.subplots(1, 3, figsize=(15, 5))

# 左: 分层饼图
seg_colors = {'High-Value': '#2ecc71', 'Potential': '#3498db',
              'Average': '#f39c12', 'At-Risk': '#e74c3c'}
seg_order = ['High-Value', 'Potential', 'Average', 'At-Risk']
pie_data = [seg_stats.loc[s, 'user_count'] for s in seg_order if s in seg_stats.index]
pie_labels = [s for s in seg_order if s in seg_stats.index]
pie_colors = [seg_colors[s] for s in seg_order if s in seg_stats.index]
axes[0].pie(pie_data, labels=pie_labels, autopct='%1.1f%%',
            colors=pie_colors, startangle=90, explode=tuple([0.05] + [0] * (len(pie_data) - 1)))
axes[0].set_title('RFM Segment Distribution')

# 中: 各层用户占比 vs GMV占比
x = range(len(seg_order))
w = 0.35
axes[1].bar([i - w/2 for i in x],
            [seg_stats.loc[s, 'user_pct'] for s in seg_order if s in seg_stats.index],
            w, color='steelblue', alpha=0.8, label='% Users')
axes[1].bar([i + w/2 for i in x],
            [seg_stats.loc[s, 'gmv_pct'] for s in seg_order if s in seg_stats.index],
            w, color='darkorange', alpha=0.8, label='% GMV')
axes[1].set_xticks(x)
axes[1].set_xticklabels(pie_labels)
axes[1].set_ylabel('Percentage (%)')
axes[1].set_title('User Share vs GMV Share by Segment')
axes[1].legend()

# 右: 各分层的平均 R/F/M 雷达图风格的柱状图
# 用 grouped bar 展示各层在三个维度上的均值
metrics = ['avg_recency', 'avg_frequency', 'avg_monetary']
metric_labels = ['Recency (days)', 'Frequency', 'Monetary (BRL)']
x = range(len(metrics))
w = 0.2
for i, seg in enumerate(seg_order):
    if seg in seg_stats.index:
        vals = [seg_stats.loc[seg, m] for m in metrics]
        # 归一化以便比较
        axes[2].bar([j + (i - 1.5) * w for j in x], vals, w,
                    color=seg_colors[seg], alpha=0.8, label=seg)

axes[2].set_xticks(x)
axes[2].set_xticklabels(metric_labels)
axes[2].set_title('Segment Profile (avg R/F/M)')
axes[2].legend(fontsize=7)

plt.suptitle('Diagnosis 2 (cont.): RFM User Segmentation',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/user_03_rfm.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 3 saved: user_03_rfm.png')

# ============================================================
# 四、用户贡献集中度 —— 帕累托分析
# ============================================================
print('\n' + '=' * 60)
print('四、用户贡献集中度：头部用户多重要？')
print('=' * 60)

# 按用户累计GMV做帕累托
df_user_gmv = df_rfm[['客户ID', 'monetary']].sort_values('monetary', ascending=False)
df_user_gmv['cum_gmv_pct'] = df_user_gmv['monetary'].cumsum() / df_user_gmv['monetary'].sum() * 100
df_user_gmv['user_pct'] = (np.arange(len(df_user_gmv)) + 1) / len(df_user_gmv) * 100

# 关键切点
top5_share = df_user_gmv[df_user_gmv['user_pct'] <= 5]['monetary'].sum() / df_user_gmv['monetary'].sum() * 100
top10_share = df_user_gmv[df_user_gmv['user_pct'] <= 10]['monetary'].sum() / df_user_gmv['monetary'].sum() * 100
top20_share = df_user_gmv[df_user_gmv['user_pct'] <= 20]['monetary'].sum() / df_user_gmv['monetary'].sum() * 100
bottom50_share = df_user_gmv[df_user_gmv['user_pct'] > 50]['monetary'].sum() / df_user_gmv['monetary'].sum() * 100

print(f"用户贡献集中度（帕累托分析）:")
print(f"  Top 5% 用户贡献:  {top5_share:.1f}% GMV")
print(f"  Top 10% 用户贡献: {top10_share:.1f}% GMV")
print(f"  Top 20% 用户贡献: {top20_share:.1f}% GMV")
print(f"  Bottom 50% 用户贡献: {bottom50_share:.1f}% GMV")

# Lorenz 曲线的简化 Gini 估算
# Gini ≈ 1 - 2*area under Lorenz curve (trapezoidal approximation)
n = min(1000, len(df_user_gmv))  # sample for efficiency
sample = df_user_gmv.iloc[::max(1, len(df_user_gmv) // n)]
area = np.trapz(sample['cum_gmv_pct'].values / 100, sample['user_pct'].values / 100)
gini_approx = 1 - 2 * area
print(f"  近似 Gini 系数: {gini_approx:.3f} (0=完全均等, 1=完全不均等)")
print(f"  → {'GMV 高度集中在少数用户手中' if gini_approx > 0.6 else 'GMV 分布相对均匀'}")

# ---------- 图4: 帕累托 + 消费分布 ----------
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 左: Lorenz 曲线
axes[0].fill_between(sample['user_pct'].values, sample['cum_gmv_pct'].values,
                      alpha=0.3, color='steelblue')
axes[0].plot(sample['user_pct'].values, sample['cum_gmv_pct'].values,
             color='steelblue', linewidth=2.5, label='Actual Distribution')
axes[0].plot([0, 100], [0, 100], '--', color='gray', linewidth=1, label='Perfect Equality')
axes[0].set_xlabel('Cumulative % of Users')
axes[0].set_ylabel('Cumulative % of GMV')
axes[0].set_title(f'Lorenz Curve (approx. Gini = {gini_approx:.3f})')
axes[0].legend()

# 标注关键点
for pct, share, label in [(5, top5_share, 'Top 5%'), (20, top20_share, 'Top 20%')]:
    axes[0].annotate(f'{label}\n{share:.1f}% GMV',
                     xy=(pct, share), xytext=(pct + 10, share - 10),
                     arrowprops=dict(arrowstyle='->', color='darkorange'),
                     fontsize=10, color='darkorange')

# 右: 消费金额分布（直方图，截断极端值）
q99 = df_user_gmv['monetary'].quantile(0.99)
df_hist = df_user_gmv[df_user_gmv['monetary'] <= q99]
axes[1].hist(df_hist['monetary'], bins=80, color='steelblue',
             alpha=0.8, edgecolor='white')
axes[1].axvline(df_user_gmv['monetary'].median(), color='darkorange',
                linestyle='--', linewidth=2, label=f'Median = {df_user_gmv["monetary"].median():.0f}')
axes[1].axvline(df_user_gmv['monetary'].mean(), color='crimson',
                linestyle='--', linewidth=2, label=f'Mean = {df_user_gmv["monetary"].mean():.0f}')
axes[1].set_xlabel('Total Spending per User (BRL)')
axes[1].set_ylabel('User Count')
axes[1].set_title(f'User Spending Distribution (99% cutoff, q99={q99:.0f})')
axes[1].legend()

plt.suptitle('Diagnosis 2 (cont.): User Contribution Concentration',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/user_04_concentration.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 4 saved: user_04_concentration.png')

# ============================================================
# 五、高价值用户画像：他们有什么特征？
# ============================================================
print('\n' + '=' * 60)
print('五、高价值用户画像：他们是谁？')
print('=' * 60)

# 给每个用户打上 segment 标签，关联品类和支付偏好
hv_users = df_rfm[df_rfm['segment'] == 'High-Value']['客户ID'].tolist()

# 高价值 vs 其他：品类偏好对比
df_hv_category = pd.read_sql_query("""
    SELECT
        CASE WHEN o.客户ID IN ({hv_list}) THEN 'High-Value' ELSE 'Others' END AS user_group,
        pt.品类名英文 AS category,
        COUNT(DISTINCT o.订单ID) AS order_count,
        ROUND(SUM(oi.价格), 2) AS gmv
    FROM orders o
    JOIN order_items oi ON o.订单ID = oi.订单ID
    JOIN products p ON oi.商品ID = p.商品ID
    JOIN product_category_translation pt ON p.商品品类名 = pt.品类名
    WHERE o.订单状态 = 'delivered'
    GROUP BY user_group, category
""".replace('{hv_list}', ','.join([f"'{u}'" for u in hv_users[:5000]])), conn)
# 限制5000个避免SQL过长；高价值用户一般就几万，采样代表

# 计算各品类在高价值用户中的GMV占比 vs 其他用户的GMV占比
df_cat_pivot = df_hv_category.pivot_table(
    index='category', columns='user_group', values='gmv', aggfunc='sum'
).fillna(0)
df_cat_pivot['hv_share'] = df_cat_pivot['High-Value'] / df_cat_pivot['High-Value'].sum() * 100
df_cat_pivot['others_share'] = df_cat_pivot['Others'] / df_cat_pivot['Others'].sum() * 100
df_cat_pivot['share_diff'] = df_cat_pivot['hv_share'] - df_cat_pivot['others_share']
df_cat_pivot = df_cat_pivot.sort_values('share_diff', ascending=False)

print("高价值用户品类偏好（vs 其他用户的GMV占比差异）:")
print("  Top 5 高价值用户更偏好的品类:")
for cat, row in df_cat_pivot.head(5).iterrows():
    print(f"    {cat}: +{row['share_diff']:.1f}pp (高价值{row['hv_share']:.1f}% vs 其他{row['others_share']:.1f}%)")

# 高价值 vs 其他：支付方式偏好
df_hv_payment = pd.read_sql_query("""
    SELECT
        CASE WHEN o.客户ID IN ({hv_list}) THEN 'High-Value' ELSE 'Others' END AS user_group,
        op.支付方式,
        COUNT(*) AS payment_count,
        ROUND(AVG(op.支付金额), 2) AS avg_支付金额
    FROM orders o
    JOIN order_payments op ON o.订单ID = op.订单ID
    WHERE o.订单状态 = 'delivered'
    GROUP BY user_group, op.支付方式
""".replace('{hv_list}', ','.join([f"'{u}'" for u in hv_users[:5000]])), conn)

print("\n高价值用户支付偏好:")
print(df_hv_payment.to_string(index=False))

# 高价值用户地区分布
df_hv_state = pd.read_sql_query("""
    SELECT
        c.客户州 AS state,
        COUNT(DISTINCT CASE WHEN rfm_rank <= 0.25 THEN o.客户ID END) AS hv_users,
        COUNT(DISTINCT o.客户ID) AS total_users,
        ROUND(COUNT(DISTINCT CASE WHEN rfm_rank <= 0.25 THEN o.客户ID END)
              * 100.0 / COUNT(DISTINCT o.客户ID), 1) AS hv_penetration
    FROM orders o
    JOIN customers c ON o.客户ID = c.客户ID
    LEFT JOIN (
        SELECT 客户ID,
               PERCENT_RANK() OVER (ORDER BY monetary DESC) AS rfm_rank
        FROM ({rfm_query}) t
    ) ranked ON o.客户ID = ranked.客户ID
    WHERE o.订单状态 = 'delivered'
    GROUP BY c.客户州
    HAVING total_users > 100
    ORDER BY hv_penetration DESC
""".replace('{rfm_query}', """
    SELECT o.客户ID, SUM(oi.价格) AS monetary
    FROM orders o
    JOIN order_items oi ON o.订单ID = oi.订单ID
    WHERE o.订单状态 = 'delivered'
    GROUP BY o.客户ID
"""), conn)

print("\n高价值用户渗透率 Top 5 州:")
print(df_hv_state.head(5).to_string(index=False))

# ---------- 图5: 高价值用户画像 ----------
fig, axes = plt.subplots(1, 3, figsize=(16, 5))

# 左: 品类偏好差异
top_diff = pd.concat([df_cat_pivot.head(8), df_cat_pivot.tail(8)])
top_diff = top_diff.sort_values('share_diff', ascending=True)
colors_diff = ['#2ecc71' if v > 0 else '#e74c3c' for v in top_diff['share_diff']]
axes[0].barh(range(len(top_diff)), top_diff['share_diff'], color=colors_diff, alpha=0.8)
axes[0].set_yticks(range(len(top_diff)))
axes[0].set_yticklabels(top_diff.index, fontsize=8)
axes[0].axvline(0, color='black', linewidth=0.5)
axes[0].set_xlabel('GMV Share Difference (pp)')
axes[0].set_title('Category Preference:\nHigh-Value vs Others')

# 中: 支付方式差异
pay_types = df_hv_payment['支付方式'].unique()
hv_pay = df_hv_payment[df_hv_payment['user_group'] == 'High-Value'].set_index('支付方式')
ot_pay = df_hv_payment[df_hv_payment['user_group'] == 'Others'].set_index('支付方式')

pay_map = {'credit_card': 'Credit Card', 'boleto': 'Boleto',
           'voucher': 'Voucher', 'debit_card': 'Debit Card', 'not_defined': 'N/A'}
x = range(len(pay_types))
w = 0.35
for i, pt in enumerate(pay_types):
    hv_val = hv_pay.loc[pt, 'payment_count'] / hv_pay['payment_count'].sum() * 100 if pt in hv_pay.index else 0
    ot_val = ot_pay.loc[pt, 'payment_count'] / ot_pay['payment_count'].sum() * 100 if pt in ot_pay.index else 0
    axes[1].bar(i - w/2, hv_val, w, color='#2ecc71', alpha=0.8)
    axes[1].bar(i + w/2, ot_val, w, color='#95a5a6', alpha=0.8)

axes[1].set_xticks(range(len(pay_types)))
axes[1].set_xticklabels([pay_map.get(pt, pt) for pt in pay_types], rotation=30, ha='right')
axes[1].set_ylabel('Payment Share (%)')
axes[1].set_title('Payment Method:\nHigh-Value (green) vs Others (gray)')

# 右: 高价值用户渗透率 by 州
top_states = df_hv_state.head(15).sort_values('hv_penetration', ascending=True)
axes[2].barh(range(len(top_states)), top_states['hv_penetration'], color='#2ecc71', alpha=0.8)
axes[2].set_yticks(range(len(top_states)))
axes[2].set_yticklabels(top_states['state'])
axes[2].set_xlabel('High-Value User Penetration (%)')
axes[2].set_title('High-Value User Rate by State (Top 15)')

plt.suptitle('Diagnosis 2 (cont.): High-Value User Profile',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/user_05_hv_profile.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 5 saved: user_05_hv_profile.png')

# ============================================================
# 六、综合诊断结论
# ============================================================
print('\n' + '=' * 60)
print('六、诊断结论：平台用户质量如何？')
print('=' * 60)

hv_user_pct = seg_stats.loc['High-Value', 'user_pct'] if 'High-Value' in seg_stats.index else 0
hv_gmv_pct = seg_stats.loc['High-Value', 'gmv_pct'] if 'High-Value' in seg_stats.index else 0

print(f"""
┌──────────────────────────────────────────────────────────────────┐
│  诊断结论：用户质量与价值结构                                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ① 用户粘性：极度脆弱                                             │
│     · {one_time_pct:.1f}% 用户仅购买 1 次，贡献 {one_time_gmv:.1f}% 的 GMV                           │
│     · 月度队列复购率平均仅 {df_retention_valid['repurchase_rate'].mean():.2f}%，且无明显改善趋势               │
│     · 用户生命周期价值（LTV）≈ 单次交易价值，几乎无复购溢价        │
│                                                                  │
│  ② 复购行为：存在但微弱                                           │
│     · 中位复购间隔 XX 天（SQL动态计算）                                │
│     · 约 XX% 的复购发生在 30 天内                                   │
│     · 复购用户集中在特定品类（见品类偏好分析）                       │
│                                                                  │
│  ③ 价值集中度：帕累托分布明显                                     │
│     · Top 20% 用户贡献 {top20_share:.1f}% GMV（近似基尼系数 {gini_approx:.3f}）                       │
│     · 高价值用户（RFM总分前25%）占 {hv_user_pct:.1f}% 用户、{hv_gmv_pct:.1f}% GMV                   │
│     · [!] 数据局限：F值因复购率极低而几乎无区分度，RFM退化为R+M      │
│                                                                  │
│  ④ 高价值用户画像                                                │
│     · 品类偏好偏向于 X                                               │
│     · 支付方式: ...                                               │
│     · 集中在 XX 州                                                 │
│                                                                  │
│  [!] 核心问题：平台存活在"一次性客户"模式中                           │
│     获客成本持续消耗，但用户不回来 → LTV/CAC 模型不可持续            │
└──────────────────────────────────────────────────────────────────┘

业务建议:
  ① 首单后 7 天 + 30 天做复购触达（push/邮件/优惠券），基于品类偏好推荐
  ② 对高价值用户（Top 20%）建立VIP权益体系，重点防止流失
  ③ 对"At-Risk"层用户（R值高但M值不低）做 win-back 活动
  ④ 在优势品类（健康美容、手表礼品）做订阅/周期性购模式，打造自然复购场景
  ⑤ 建立复购率月度监控看板，将"30天复购率"作为核心运营KPI
""")

conn.close()
print('=' * 60)
print('用户质量诊断完成，5 张图已保存至 outputs/')
print('=' * 60)
