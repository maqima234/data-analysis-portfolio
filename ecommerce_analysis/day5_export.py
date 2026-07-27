"""
Day 5: Excel 交叉验证
将 SQL 聚合结果导出为 CSV，在 Excel 中用数据透视表复核算
"""
import pymysql
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

conn = pymysql.connect(
    host='127.0.0.1', user='root', password='123456',
    database='ecommerce_analysis', charset='utf8mb4'
)

# ---- 1. 月度销售额（用于 Excel 折线图 / 透视表验证）----
df1 = pd.read_sql_query("""
SELECT DATE_FORMAT(下单时间, '%Y-%m') AS 月份,
       ROUND(SUM(oi.价格), 2) AS 销售额,
       COUNT(DISTINCT o.订单ID) AS 订单量
FROM orders o
JOIN order_items oi ON o.订单ID = oi.订单ID
WHERE o.订单状态 = 'delivered'
GROUP BY 月份 ORDER BY 月份
""", conn)
df1.to_csv('verify_月度销售额.csv', index=False, encoding='utf-8-sig')
print('[OK] verify_月度销售额.csv')

# ---- 2. 品类销售额（用于 Excel 柱状图验证）----
df2 = pd.read_sql_query("""
SELECT t.品类名英文 AS 品类, ROUND(SUM(oi.价格), 2) AS 销售额
FROM order_items oi
JOIN products p ON oi.商品ID = p.商品ID
JOIN product_category_translation t ON p.商品品类名 = t.品类名
JOIN orders o ON oi.订单ID = o.订单ID
WHERE o.订单状态 = 'delivered'
GROUP BY t.品类名英文 ORDER BY 销售额 DESC
""", conn)
df2.to_csv('verify_品类销售额.csv', index=False, encoding='utf-8-sig')
print('[OK] verify_品类销售额.csv')

# ---- 3. 支付方式分布（用于 Excel 饼图验证）----
df3 = pd.read_sql_query("""
SELECT 支付方式, COUNT(*) AS 笔数,
       ROUND(SUM(支付金额), 2) AS 总金额
FROM order_payments
GROUP BY 支付方式 ORDER BY 笔数 DESC
""", conn)
df3.to_csv('verify_支付方式.csv', index=False, encoding='utf-8-sig')
print('[OK] verify_支付方式.csv')

# ---- 4. 评分分布（用于 Excel 柱状图验证）----
df4 = pd.read_sql_query("""
SELECT 评分, COUNT(*) AS 数量
FROM order_reviews GROUP BY 评分 ORDER BY 评分 DESC
""", conn)
df4.to_csv('verify_评分分布.csv', index=False, encoding='utf-8-sig')
print('[OK] verify_评分分布.csv')

# ---- 5. RFM 分层统计（用于 Excel 核对）----
df5 = pd.read_sql_query("""
SELECT o.客户ID,
       DATEDIFF('2018-10-01', MAX(o.下单时间)) AS R值,
       COUNT(DISTINCT o.订单ID) AS F值,
       ROUND(SUM(oi.价格), 2) AS M值
FROM orders o
JOIN order_items oi ON o.订单ID = oi.订单ID
WHERE o.订单状态 = 'delivered'
GROUP BY o.客户ID
""", conn)
df5.to_csv('verify_RFM明细.csv', index=False, encoding='utf-8-sig')
print('[OK] verify_RFM明细.csv')

conn.close()
print('\n=== Day 5: 5 个 CSV 已导出，用 Excel 打开验证 ===')
