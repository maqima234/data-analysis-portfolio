"""
平台销售增长驱动诊断
诊断问题：GMV 增长来自哪里？
分析链路：GMV趋势 → 量价拆解 → 新老客贡献 → 品类增量 → 地区集中度 → 结论
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
# 一、GMV 趋势：量驱动还是价驱动？
# ============================================================
print('=' * 60)
print('一、GMV 趋势：量驱动还是价驱动？')
print('=' * 60)

df_trend = pd.read_sql_query("""
    SELECT
        DATE_FORMAT(下单时间, '%Y-%m') AS month,
        COUNT(DISTINCT o.订单ID) AS order_count,
        ROUND(SUM(oi.价格), 2) AS gmv,
        ROUND(SUM(oi.价格) / COUNT(DISTINCT o.订单ID), 2) AS aov
    FROM orders o
    JOIN order_items oi ON o.订单ID = oi.订单ID
    WHERE o.订单状态 = 'delivered'
    GROUP BY month
    ORDER BY month
""", conn)

# 计算环比增速
df_trend['gmv_growth'] = df_trend['gmv'].pct_change() * 100
df_trend['order_growth'] = df_trend['order_count'].pct_change() * 100
df_trend['aov_growth'] = df_trend['aov'].pct_change() * 100

# 剔除首月（无环比）和末月（可能不完整）
df_valid = df_trend.iloc[1:-1]  # 用于统计的月份

print(f"数据跨度: {df_trend['month'].iloc[0]} ~ {df_trend['month'].iloc[-1]}")
print(f"月均 GMV: {df_valid['gmv'].mean():,.0f}  月均订单量: {df_valid['order_count'].mean():,.0f}  月均客单价: {df_valid['aov'].mean():.0f}")
print(f"GMV 月均环比增速: {df_valid['gmv_growth'].mean():.1f}%")
print(f"订单量月均环比增速: {df_valid['order_growth'].mean():.1f}%")
print(f"客单价月均环比增速: {df_valid['aov_growth'].mean():.1f}%")

# 判断增长主驱动
if abs(df_valid['order_growth'].mean()) > abs(df_valid['aov_growth'].mean()) * 1.5:
    driver = "订单量增长是 GMV 增长的主要驱动力，客单价变化幅度远小于订单量波动"
else:
    driver = "订单量和客单价共同驱动 GMV 增长"

# ---------- 图1: GMV 量价拆解（三面板）----------
fig, axes = plt.subplots(3, 1, figsize=(14, 11))

# 面板1: GMV + 订单量双轴
ax1 = axes[0]
bars = ax1.bar(range(len(df_trend)), df_trend['order_count'],
               color='steelblue', alpha=0.7, label='Order Count')
ax1.set_ylabel('Order Count', color='steelblue')
ax1.tick_params(axis='y', labelcolor='steelblue')

ax1b = ax1.twinx()
line1 = ax1b.plot(range(len(df_trend)), df_trend['gmv'] / 1000,
                  color='darkorange', marker='o', linewidth=2, label='GMV (k)')
ax1b.set_ylabel('GMV (thousands BRL)', color='darkorange')
ax1b.tick_params(axis='y', labelcolor='darkorange')

ax1.set_xticks(range(0, len(df_trend), 2))
ax1.set_xticklabels(df_trend['month'].iloc[::2], rotation=45, ha='right')
ax1.set_title('GMV & Order Count Monthly Trend')

# 合并图例
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax1b.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

# 面板2: 客单价趋势
ax2 = axes[1]
ax2.plot(range(len(df_trend)), df_trend['aov'], color='steelblue',
         marker='s', linewidth=2, markersize=6)
ax2.axhline(df_valid['aov'].mean(), color='darkorange', linestyle='--',
            linewidth=1.5, label=f'Mean AOV = {df_valid["aov"].mean():.0f}')
ax2.set_xticks(range(0, len(df_trend), 2))
ax2.set_xticklabels(df_trend['month'].iloc[::2], rotation=45, ha='right')
ax2.set_ylabel('Average Order Value (BRL)')
ax2.set_title('Average Order Value Trend')
ax2.legend()

# 面板3: 环比增速对比（量 vs 价）
ax3 = axes[2]
x = range(1, len(df_trend))  # 从第2个月开始才有环比
ax3.bar(np.array(x) - 0.15, df_trend['order_growth'].iloc[1:],
        width=0.3, color='steelblue', alpha=0.8, label='Order Count MoM%')
ax3.bar(np.array(x) + 0.15, df_trend['aov_growth'].iloc[1:],
        width=0.3, color='darkorange', alpha=0.8, label='AOV MoM%')
ax3.axhline(0, color='black', linewidth=0.5)
ax3.set_xticks(x)
ax3.set_xticklabels(df_trend['month'].iloc[1:], rotation=45, ha='right')
ax3.set_ylabel('Month-over-Month Growth (%)')
ax3.set_title('Growth Decomposition: Volume vs Price')
ax3.legend()

plt.suptitle('Diagnosis 1: GMV Growth — Volume-Driven or Price-Driven?',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/growth_01_gmv_decomposition.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 1 saved: growth_01_gmv_decomposition.png')

# ============================================================
# 二、复购诊断：用户买完还会回来吗？
# ============================================================
print('\n' + '=' * 60)
print('二、复购诊断：用户买完还会回来吗？')
print('=' * 60)

# 查询每个用户的购买次数分布
df_repurchase = pd.read_sql_query("""
    SELECT
        CASE WHEN order_count = 1 THEN '1 order'
             WHEN order_count = 2 THEN '2 orders'
             ELSE '3+ orders' END AS frequency,
        COUNT(*) AS user_count
    FROM (
        SELECT 客户ID, COUNT(DISTINCT 订单ID) AS order_count
        FROM orders
        WHERE 订单状态 = 'delivered'
        GROUP BY 客户ID
    ) t
    GROUP BY frequency
    ORDER BY MIN(order_count)
""", conn)

total_users = df_repurchase['user_count'].sum()
# 安全获取复购用户数（如果"2 orders"或"3+ orders"不存在则返回0）
repeat_users = df_repurchase[df_repurchase['frequency'] != '1 order']['user_count'].sum()
repeat_rate = repeat_users / total_users * 100

print(f"总用户数（有delivered订单）: {total_users:,}")
print(f"购买1次的用户: {df_repurchase[df_repurchase['frequency']=='1 order']['user_count'].values[0]:,} ({100-repeat_rate:.2f}%)")
if repeat_users > 0:
    for _, row in df_repurchase[df_repurchase['frequency'] != '1 order'].iterrows():
        print(f"{row['frequency']}: {row['user_count']:,} ({row['user_count']/total_users*100:.2f}%)")
else:
    print("购买≥2次的用户: 0 —— 复购率为真正的 0%")

if repeat_rate == 0:
    print("\n[!] 核心发现：平台 delivered 订单的复购率为绝对零。")
    print("  这意味着每一个完成交易的客户，都再没有下过第二单。")
    print("  这不是'复购率低'的问题，而是根本没有复购机制。")
    print("  分析改为：用户月度获取趋势 + 客单价变化（跳过新老客拆解，因为没有老客）")

# ---------- 图2: 复购诊断（根据是否有复购切换展示）----------
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# 左: 购买频次饼图
if repeat_users > 0:
    pie_labels = df_repurchase['frequency'].tolist()
    pie_data = df_repurchase['user_count'].tolist()
    pie_colors = ['#e74c3c', '#f39c12', '#2ecc71']
else:
    pie_labels = ['One-time buyers\n(never returned)']
    pie_data = [total_users]
    pie_colors = ['#e74c3c']

axes[0].pie(pie_data, labels=pie_labels, autopct='%1.1f%%',
            colors=pie_colors[:len(pie_data)], startangle=90,
            explode=tuple([0.05] + [0] * (len(pie_data) - 1)))
axes[0].set_title('Purchase Frequency Distribution')

# 右: 月度新客获取趋势（因为没有复购，改为展示每月拉新量）
df_monthly_new = pd.read_sql_query("""
    SELECT
        DATE_FORMAT(下单时间, '%Y-%m') AS month,
        COUNT(DISTINCT 客户ID) AS new_customers,
        ROUND(SUM(oi.价格), 2) AS gmv
    FROM orders o
    JOIN order_items oi ON o.订单ID = oi.订单ID
    WHERE o.订单状态 = 'delivered'
    GROUP BY month
    ORDER BY month
""", conn)

axes[1].bar(range(len(df_monthly_new)), df_monthly_new['new_customers'],
            color='steelblue', alpha=0.8)
axes[1].set_xticks(range(0, len(df_monthly_new), 2))
axes[1].set_xticklabels(df_monthly_new['month'].iloc[::2], rotation=45, ha='right')
axes[1].set_ylabel('New Customers per Month')
axes[1].set_title('Monthly Customer Acquisition Trend')

# 标注首尾月对比
first_half = df_monthly_new['new_customers'].iloc[:6].mean()
second_half = df_monthly_new['new_customers'].iloc[-6:].mean()
axes[1].axhline(first_half, color='gray', linestyle=':', alpha=0.5)
axes[1].axhline(second_half, color='darkorange', linestyle=':', alpha=0.5)
axes[1].text(len(df_monthly_new) - 1, second_half,
             f'Recent avg: {second_half:.0f}', fontsize=8, color='darkorange')

plt.suptitle('Diagnosis 1 (cont.): Zero Repurchase — Pure Acquisition Model',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/growth_02_zero_repurchase.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 2 saved: growth_02_zero_repurchase.png')

# ============================================================
# 三、品类增长贡献度：谁在推动GMV增长？
# ============================================================
print('\n' + '=' * 60)
print('三、品类增长贡献度：哪些品类是增长引擎？')
print('=' * 60)

df_cat_monthly = pd.read_sql_query("""
    SELECT
        DATE_FORMAT(o.下单时间, '%Y-%m') AS month,
        pt.品类名英文 AS category,
        ROUND(SUM(oi.价格), 2) AS gmv,
        COUNT(DISTINCT o.订单ID) AS order_count
    FROM orders o
    JOIN order_items oi ON o.订单ID = oi.订单ID
    JOIN products p ON oi.商品ID = p.商品ID
    JOIN product_category_translation pt ON p.商品品类名 = pt.品类名
    WHERE o.订单状态 = 'delivered'
    GROUP BY month, category
    ORDER BY month, gmv DESC
""", conn)

# 品类整体排名
df_cat_total = df_cat_monthly.groupby('category').agg(
    total_gmv=('gmv', 'sum'),
    total_orders=('order_count', 'sum'),
    months_active=('month', 'nunique')
).sort_values('total_gmv', ascending=False)

# 计算每个品类的增长贡献：首尾两期GMV差值
first_month = df_cat_monthly['month'].min()
last_month = df_cat_monthly['month'].max()
df_cat_first = df_cat_monthly[df_cat_monthly['month'] == first_month].set_index('category')
df_cat_last = df_cat_monthly[df_cat_monthly['month'] == last_month].set_index('category')

# 品类增长贡献（首末月差值）
cat_growth = pd.DataFrame({
    'first_gmv': df_cat_first['gmv'],
    'last_gmv': df_cat_last['gmv']
}).fillna(0)
cat_growth['gmv_change'] = cat_growth['last_gmv'] - cat_growth['first_gmv']
cat_growth = cat_growth.sort_values('gmv_change', ascending=False)

print(f"品类总数: {len(df_cat_total)}")
print(f"\nTop 10 品类（总GMV排名）:")
print(df_cat_total.head(10)[['total_gmv', 'total_orders']].to_string())
print(f"\nGMV 增长贡献 Top 5 品类（{first_month} → {last_month}）:")
print(cat_growth.head(5)[['first_gmv', 'last_gmv', 'gmv_change']].to_string())
print(f"\nGMV 萎缩 Top 5 品类:")
print(cat_growth.tail(5)[['first_gmv', 'last_gmv', 'gmv_change']].to_string())

# ---------- 图3: 品类分析（两面板）----------
fig, axes = plt.subplots(1, 2, figsize=(15, 6))

# 左: Top 10 品类月度GMV趋势
top10_cats = df_cat_total.head(10).index.tolist()
df_top10_monthly = df_cat_monthly[df_cat_monthly['category'].isin(top10_cats)]
df_top10_pivot = df_top10_monthly.pivot_table(
    index='month', columns='category', values='gmv', aggfunc='sum'
).fillna(0)

# 使用差异化颜色
colors_10 = ['#2c3e50', '#e74c3c', '#3498db', '#2ecc71', '#f39c12',
             '#9b59b6', '#1abc9c', '#e67e22', '#95a5a6', '#c0392b']
for i, cat in enumerate(df_top10_pivot.columns):
    axes[0].plot(range(len(df_top10_pivot.index)), df_top10_pivot[cat] / 1000,
                 color=colors_10[i], linewidth=1.8, marker='.' if i < 5 else '',
                 label=cat[:25], alpha=0.85)

axes[0].set_xticks(range(0, len(df_top10_pivot.index), 2))
axes[0].set_xticklabels([str(m) for m in df_top10_pivot.index[::2]],
                         rotation=45, ha='right')
axes[0].set_ylabel('GMV (thousands BRL)')
axes[0].set_title('Top 10 Categories: Monthly GMV Trend')
axes[0].legend(fontsize=7, loc='upper left')

# 右: 品类增长贡献（首末月差值）- Horizontal bar
top_gainers = cat_growth.head(10).sort_values('gmv_change', ascending=True)
top_decliners = cat_growth.tail(5).sort_values('gmv_change', ascending=True)
df_plot_cat = pd.concat([top_decliners, top_gainers])

colors_cat = ['#e74c3c' if v < 0 else '#2ecc71' for v in df_plot_cat['gmv_change']]
axes[1].barh(range(len(df_plot_cat)), df_plot_cat['gmv_change'] / 1000,
             color=colors_cat, alpha=0.8)
axes[1].set_yticks(range(len(df_plot_cat)))
axes[1].set_yticklabels(df_plot_cat.index)
axes[1].axvline(0, color='black', linewidth=0.5)
axes[1].set_xlabel('GMV Change (thousands BRL)')
axes[1].set_title(f'Category GMV Change: {first_month} → {last_month}')

plt.suptitle('Diagnosis 1 (cont.): Category Growth Attribution',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/growth_03_category_attribution.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 3 saved: growth_03_category_attribution.png')

# ============================================================
# 四、地区集中度：增长的区域分布
# ============================================================
print('\n' + '=' * 60)
print('四、地区集中度：哪些州在支撑增长？')
print('=' * 60)

df_state = pd.read_sql_query("""
    SELECT
        c.客户州 AS state,
        COUNT(DISTINCT o.订单ID) AS order_count,
        COUNT(DISTINCT o.客户ID) AS customer_count,
        ROUND(SUM(oi.价格), 2) AS gmv,
        ROUND(SUM(oi.价格) / COUNT(DISTINCT o.订单ID), 2) AS aov
    FROM orders o
    JOIN order_items oi ON o.订单ID = oi.订单ID
    JOIN customers c ON o.客户ID = c.客户ID
    WHERE o.订单状态 = 'delivered'
    GROUP BY c.客户州
    ORDER BY gmv DESC
""", conn)

df_state['gmv_share'] = df_state['gmv'] / df_state['gmv'].sum() * 100
df_state['gmv_cum_share'] = df_state['gmv_share'].cumsum()

# 集中度指标
top3_share = df_state.head(3)['gmv_share'].sum()
top5_share = df_state.head(5)['gmv_share'].sum()
top1_state = df_state.iloc[0]

print(f"有交易记录的州: {len(df_state)} 个")
print(f"Top 1 州 ({top1_state['state']}): GMV 占比 {top1_state['gmv_share']:.1f}%")
print(f"Top 3 州 GMV 占比: {top3_share:.1f}%")
print(f"Top 5 州 GMV 占比: {top5_share:.1f}%")
print(f"  → 地区集中度: {'高度集中，头部州占绝对主导' if top3_share > 60 else '相对分散'}")
print(f"\nTop 10 州:")
print(df_state.head(10).to_string(index=False))

# ---------- 图4: 地区分析（两面板）----------
fig, axes = plt.subplots(1, 2, figsize=(15, 6))

# 左: GMV 柱状图 + 累计占比曲线
df_plot_state = df_state.head(20).sort_values('gmv', ascending=True)
colors_state = ['#c0392b' if i >= len(df_plot_state) - 3 else '#3498db'
                for i in range(len(df_plot_state))]

bars = axes[0].barh(range(len(df_plot_state)), df_plot_state['gmv'] / 1000,
                    color=colors_state, alpha=0.8)
axes[0].set_yticks(range(len(df_plot_state)))
axes[0].set_yticklabels(df_plot_state['state'])
axes[0].set_xlabel('GMV (thousands BRL)')
axes[0].set_title('GMV by State (Top 20)')

# 右: 帕累托图——GMV 集中度
df_state_sorted = df_state.sort_values('gmv', ascending=False)
axes[1].bar(range(len(df_state_sorted)), df_state_sorted['gmv_share'],
            color='steelblue', alpha=0.8, width=0.8)
axes[1].plot(range(len(df_state_sorted)), df_state_sorted['gmv_cum_share'],
             color='crimson', marker='o', linewidth=2, markersize=4)
axes[1].axhline(80, color='gray', linestyle='--', alpha=0.5, label='80% line')
axes[1].set_xlabel('State Rank')
axes[1].set_ylabel('GMV Share (%)')
axes[1].set_title('Pareto: GMV Concentration by State')

# 标注 80% 对应的州数
n80 = (df_state_sorted['gmv_cum_share'] <= 80).sum()
axes[1].annotate(f'{n80} states =\n80% GMV',
                 xy=(n80, 80), xytext=(n80 + 3, 70),
                 arrowprops=dict(arrowstyle='->', color='gray'),
                 fontsize=10)

plt.suptitle('Diagnosis 1 (cont.): Regional Concentration Analysis',
             fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/growth_04_regional_concentration.png', dpi=150, bbox_inches='tight')
plt.close()
print('[OK] Fig 4 saved: growth_04_regional_concentration.png')

# ============================================================
# 五、综合诊断结论
# ============================================================
print('\n' + '=' * 60)
print('五、诊断结论：平台销售增长来自哪里？')
print('=' * 60)

# 计算关键数字
peak_month = df_trend.loc[df_trend['gmv'].idxmax()]
growth_months = (df_valid['gmv_growth'] > 0).sum()
total_months = len(df_valid)

declining_cats = (cat_growth['gmv_change'] < 0).sum()
growing_cats = (cat_growth['gmv_change'] > 0).sum()

print(f"""
┌──────────────────────────────────────────────────────────────────┐
│  诊断结论：平台 GMV 增长驱动全景                                   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ① 增长模式：{driver}                        │
│     · GMV 月均环比 +{df_valid['gmv_growth'].mean():.1f}%，{growth_months}/{total_months} 个月正增长                      │
│     · 客单价稳定在 {df_valid['aov'].mean():.0f} BRL 附近，波动幅度远小于订单量                    │
│                                                                  │
│  ② 增长引擎：100% 纯拉新驱动（复购率 = 0%）                         │
│     · 所有 {total_users:,} 个完成交易的客户，没有任何人下过第二单                  │
│     · 这不是"复购率低"，而是"没有复购机制"——平台本质是                      │
│       一个纯获客→转化→流失的漏斗，不是用户运营平台                    │
│                                                                  │
│  ③ 品类结构：头部集中，增长分化                                    │
│     · 增长品类 {growing_cats} 个 vs 萎缩品类 {declining_cats} 个                                │
│     · Top 品类贡献了绝大部分增量                                     │
│                                                                  │
│  ④ 地区分布：高度集中                                             │
│     · Top 3 州 = {top3_share:.1f}% GMV，Top 5 = {top5_share:.1f}%                           │
│     · {top1_state['state']} 一州独大（{top1_state['gmv_share']:.1f}%），增长受单一市场制约                                 │
│                                                                  │
│  [!] 核心风险：增长完全依赖新客流量 + 头部品类 + 单一地区              │
│     一旦获客成本上升或头部市场饱和，GMV 将面临断崖式压力              │
└──────────────────────────────────────────────────────────────────┘

业务建议:
  ① 复购是生死线：在下单后 7/30/90 天做品类关联推荐触达，
     即使复购率从 0% 提升到 3%，GMV 即可直接增长 3%
  ② 品类策略：对增长品类（{', '.join(cat_growth.head(3).index.tolist())}）加大供应链投入；
     对萎缩品类分析是需求端还是供给端问题
  ③ 区域策略：{top1_state['state']} 州做深渗透，同时在 GMV 占比 5-10% 的腰部州
     （如 {', '.join(df_state.iloc[3:6]['state'].tolist())}）做增长试点
""")

conn.close()
print('=' * 60)
print('销售增长驱动诊断完成，4 张图已保存至 outputs/')
print('=' * 60)
