"""
Day 3: SQL + Python 串联分析
"""
import pymysql
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

# 连接 MySQL
conn = pymysql.connect(
    host='127.0.0.1',
    user='root',
    password='123456',
    database='ecommerce_analysis',
    charset='utf8mb4'
)

# ============================================================
# 分析一：月度销售额与订单量趋势
# ============================================================
query1 = """
SELECT
    DATE_FORMAT(下单时间, '%Y-%m') AS 月份,
    ROUND(SUM(oi.价格), 2) AS 销售额,
    COUNT(DISTINCT o.订单ID) AS 订单量
FROM orders o
JOIN order_items oi ON o.订单ID = oi.订单ID
WHERE o.订单状态 = 'delivered'
GROUP BY 月份
ORDER BY 月份;
"""
df1 = pd.read_sql_query(query1, conn)

fig, ax1 = plt.subplots(figsize=(12, 5))
ax1.bar(df1['月份'], df1['订单量'], color='steelblue', alpha=0.7, label='订单量')
ax1.set_xlabel('月份')
ax1.set_ylabel('订单量', color='steelblue')
ax1.tick_params(axis='y', labelcolor='steelblue')
ax1.tick_params(axis='x', rotation=45)

ax2 = ax1.twinx()
ax2.plot(df1['月份'], df1['销售额'], color='darkorange', marker='o', linewidth=2, label='销售额')
ax2.set_ylabel('销售额（巴西雷亚尔）', color='darkorange')
ax2.tick_params(axis='y', labelcolor='darkorange')

plt.title('月度销售额与订单量趋势')
fig.legend(loc='upper left', bbox_to_anchor=(0.1, 0.9))
plt.tight_layout()
plt.savefig('output_月度趋势.png', dpi=150)
plt.close()
print('[OK] 分析一：月度趋势图已保存')


# ============================================================
# 分析二：Top 10 品类销售额排名
# ============================================================
query2 = """
SELECT
    t.品类名英文 AS 品类,
    ROUND(SUM(oi.价格), 2) AS 销售额
FROM order_items oi
JOIN products p ON oi.商品ID = p.商品ID
JOIN product_category_translation t ON p.商品品类名 = t.品类名
JOIN orders o ON oi.订单ID = o.订单ID
WHERE o.订单状态 = 'delivered'
GROUP BY t.品类名英文
ORDER BY 销售额 DESC
LIMIT 10;
"""
df2 = pd.read_sql_query(query2, conn)

plt.figure(figsize=(10, 6))
plt.barh(df2['品类'], df2['销售额'], color='steelblue', alpha=0.8)
plt.xlabel('销售额（巴西雷亚尔）')
plt.title('Top 10 品类销售额排名')
plt.gca().invert_yaxis()
plt.tight_layout()
plt.savefig('output_品类排名.png', dpi=150)
plt.close()
print('[OK] 分析二：品类排名图已保存')


# ============================================================
# 分析三：支付方式分布
# ============================================================
query3 = """
SELECT
    支付方式,
    COUNT(*) AS 笔数,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM order_payments), 1) AS 占比
FROM order_payments
GROUP BY 支付方式
ORDER BY 笔数 DESC;
"""
df3 = pd.read_sql_query(query3, conn)

# 翻译支付方式
type_map = {
    'credit_card': '信用卡',
    'boleto': 'Boleto凭证',
    'voucher': '代金券',
    'debit_card': '借记卡',
    'not_defined': '未定义'
}
df3['支付方式中文'] = df3['支付方式'].map(type_map)

plt.figure(figsize=(8, 8))
plt.pie(df3['笔数'], labels=df3['支付方式中文'], autopct='%1.1f%%',
        colors=['steelblue', 'darkorange', 'forestgreen', 'crimson', 'gray'],
        startangle=90)
plt.title('支付方式分布')
plt.tight_layout()
plt.savefig('output_支付方式.png', dpi=150)
plt.close()
print('[OK] 分析三：支付方式分布图已保存')


# ============================================================
# 分析四：评分分布
# ============================================================
query4 = """
SELECT
    评分,
    COUNT(*) AS 数量,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM order_reviews), 1) AS 占比
FROM order_reviews
GROUP BY 评分
ORDER BY 评分 DESC;
"""
df4 = pd.read_sql_query(query4, conn)

plt.figure(figsize=(8, 5))
plt.bar(df4['评分'], df4['数量'], color='steelblue', alpha=0.8, width=0.6)
plt.xlabel('评分')
plt.ylabel('评价数量')
plt.title('用户评分分布')
for i, (score, cnt) in enumerate(zip(df4['评分'], df4['数量'])):
    plt.text(score, cnt + 500, f'{cnt:,}', ha='center', fontsize=9)
plt.tight_layout()
plt.savefig('output_评分分布.png', dpi=150)
plt.close()
print('[OK] 分析四：评分分布图已保存')

conn.close()
print('\n=== Day 3 完成，4 张分析图已生成 ===')
