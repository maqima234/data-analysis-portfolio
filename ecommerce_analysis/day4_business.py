"""
Day 4: 业务分析实战
三个分析：RFM用户分层 / 复购率漏斗 / 评分与消费关联
"""
import pymysql
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False
import warnings
warnings.filterwarnings('ignore')

conn = pymysql.connect(
    host='127.0.0.1', user='root', password='123456',
    database='ecommerce_analysis', charset='utf8mb4'
)

# ============================================================
# 分析一：RFM 用户分层
# ============================================================
print('=== 分析一：RFM 用户分层 ===')

# SQL 计算每个客户的 R、F、M
query_rfm = """
SELECT
    o.客户ID,
    DATEDIFF('2018-10-01', MAX(o.下单时间)) AS R值,
    COUNT(DISTINCT o.订单ID) AS F值,
    ROUND(SUM(oi.价格), 2) AS M值
FROM orders o
JOIN order_items oi ON o.订单ID = oi.订单ID
WHERE o.订单状态 = 'delivered'
GROUP BY o.客户ID
"""
df_rfm = pd.read_sql_query(query_rfm, conn)

# 用百分位数分三层打1-3分
def percentile_score(series, ascending=True):
    """按33%和67%分位数切成三层，返回1/2/3分"""
    p33 = series.quantile(1/3)
    p67 = series.quantile(2/3)
    if ascending:
        return series.apply(lambda x: 3 if x >= p67 else (2 if x >= p33 else 1))
    else:
        return series.apply(lambda x: 3 if x <= p33 else (2 if x <= p67 else 1))

df_rfm['R分'] = percentile_score(df_rfm['R值'], ascending=False)
df_rfm['F分'] = percentile_score(df_rfm['F值'], ascending=True)
df_rfm['M分'] = percentile_score(df_rfm['M值'], ascending=True)

# 总分
df_rfm['RFM总分'] = df_rfm['R分'].astype(int) + df_rfm['F分'].astype(int) + df_rfm['M分'].astype(int)

# 分层命名（按总分相对位置：前25%高价值，中间50%潜力/一般，后25%流失）
max_score = df_rfm['RFM总分'].max()
q75 = df_rfm['RFM总分'].quantile(0.75)
q50 = df_rfm['RFM总分'].quantile(0.50)
q25 = df_rfm['RFM总分'].quantile(0.25)
def label_rfm(score):
    if score >= q75: return '高价值客户'
    elif score >= q50: return '潜力客户'
    elif score >= q25: return '一般客户'
    else: return '流失客户'

df_rfm['用户层级'] = df_rfm['RFM总分'].apply(label_rfm)

print('用户分层分布:')
print(df_rfm['用户层级'].value_counts())
print(f'\n高价值客户占比: {(df_rfm["用户层级"]=="高价值客户").mean()*100:.1f}%')

# 分层饼图
layer_counts = df_rfm['用户层级'].value_counts()
colors = ['#2ecc71', '#3498db', '#f39c12', '#e74c3c']
plt.figure(figsize=(8, 8))
plt.pie(layer_counts, labels=layer_counts.index, autopct='%1.1f%%',
        colors=colors, startangle=90, explode=(0.05, 0, 0, 0))
plt.title('RFM 用户分层')
plt.tight_layout()
plt.savefig('output_RFM分层.png', dpi=150)
plt.close()
print('[OK] RFM分层图已保存')


# ============================================================
# 分析二：客户消费金额分层
# ============================================================
print('\n=== 分析二：客户消费金额分层 ===')

query_spend = """
SELECT
    o.客户ID,
    ROUND(SUM(oi.价格 + oi.运费), 2) AS 总消费
FROM orders o
JOIN order_items oi ON o.订单ID = oi.订单ID
WHERE o.订单状态 = 'delivered'
GROUP BY o.客户ID
"""
df_spend = pd.read_sql_query(query_spend, conn)

# 分层标签
p75 = df_spend['总消费'].quantile(0.75)
p50 = df_spend['总消费'].quantile(0.50)
p25 = df_spend['总消费'].quantile(0.25)
def level(v):
    if v >= p75: return '高消费'
    elif v >= p50: return '中消费'
    elif v >= p25: return '低消费'
    else: return '极低消费'
df_spend['消费层级'] = df_spend['总消费'].apply(level)

dist = df_spend['消费层级'].value_counts()
print('消费金额分层:')
print(dist)
print(f'平均客单价: {df_spend["总消费"].mean():.0f}')
print(f'中位客单价: {df_spend["总消费"].median():.0f}')
print(f'最高客单价: {df_spend["总消费"].max():.0f}')

# 分布直方图
plt.figure(figsize=(10, 5))
plt.hist(df_spend[df_spend['总消费'] < 500]['总消费'], bins=50, color='steelblue', alpha=0.8, edgecolor='white')
plt.axvline(df_spend['总消费'].median(), color='darkorange', linestyle='--', linewidth=2, label=f'中位数={df_spend["总消费"].median():.0f}')
plt.axvline(df_spend['总消费'].mean(), color='crimson', linestyle='--', linewidth=2, label=f'均值={df_spend["总消费"].mean():.0f}')
plt.xlabel('消费金额（雷亚尔）')
plt.ylabel('客户数')
plt.title('客户消费金额分布')
plt.legend()
plt.tight_layout()
plt.savefig('output_消费分层.png', dpi=150)
plt.close()
print('[OK] 消费金额分层图已保存')


# ============================================================
# 分析三：评分与消费行为关联
# ============================================================
print('\n=== 分析三：评分与消费关联 ===')

query_score = """
SELECT
    rv.评分,
    COUNT(DISTINCT rv.订单ID) AS 订单数,
    ROUND(AVG(oi.价格 + oi.运费), 2) AS 平均消费金额,
    ROUND(SUM(oi.价格 + oi.运费), 2) AS 总消费金额
FROM order_reviews rv
JOIN order_items oi ON rv.订单ID = oi.订单ID
GROUP BY rv.评分
ORDER BY rv.评分 DESC
"""
df_score = pd.read_sql_query(query_score, conn)
print(df_score.to_string(index=False))

# 评分与消费金额关系
plt.figure(figsize=(10, 5))
bars = plt.bar(df_score['评分'], df_score['平均消费金额'], color='steelblue', alpha=0.8, width=0.5)
plt.xlabel('评分')
plt.ylabel('平均消费金额（雷亚尔）')
plt.title('不同评分用户的平均消费金额')
for bar, val in zip(bars, df_score['平均消费金额']):
    plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
             f'{val:.0f}', ha='center', fontsize=10)
plt.tight_layout()
plt.savefig('output_评分消费.png', dpi=150)
plt.close()

# 相关系数
corr = df_score['评分'].corr(df_score['平均消费金额'])
print(f'\n评分与平均消费金额的相关系数: {corr:.3f}')
print('[OK] 评分消费关系图已保存')

conn.close()
print('\n=== Day 4 完成，3 张分析图已生成 ===')
