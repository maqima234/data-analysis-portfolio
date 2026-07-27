-- ============================================================
-- Day 2: SQL 数据探查与清洗
-- 目标：搞懂每张表的含义、数据质量、关键字段、表之间怎么关联
-- 用法：选中一条查询，按 Ctrl+Enter 执行
-- ============================================================

USE ecommerce_analysis;


-- ============================================================
-- 第一组：各表数据量摸底
-- ============================================================

-- 1.1 九张表各有多少行
SELECT '客户表' AS 表名, COUNT(*) AS 行数 FROM customers
UNION ALL
SELECT '订单表', COUNT(*) FROM orders
UNION ALL
SELECT '订单商品明细表', COUNT(*) FROM order_items
UNION ALL
SELECT '支付表', COUNT(*) FROM order_payments
UNION ALL
SELECT '评价表', COUNT(*) FROM order_reviews
UNION ALL
SELECT '商品表', COUNT(*) FROM products
UNION ALL
SELECT '卖家表', COUNT(*) FROM sellers
UNION ALL
SELECT '地理位置表', COUNT(*) FROM geolocation
UNION ALL
SELECT '品类翻译表', COUNT(*) FROM product_category_translation;


-- ============================================================
-- 第二组：时间维度
-- ============================================================

-- 2.1 数据覆盖的时间跨度
SELECT
    MIN(下单时间) AS 最早订单,
    MAX(下单时间) AS 最晚订单,
    DATEDIFF(MAX(下单时间), MIN(下单时间)) AS 跨度天数
FROM orders;


-- 2.2 月度订单量变化趋势
SELECT
    DATE_FORMAT(下单时间, '%Y-%m') AS 月份,
    COUNT(*) AS 订单量
FROM orders
GROUP BY 月份
ORDER BY 月份;


-- ============================================================
-- 第三组：订单状态与数据质量
-- ============================================================

-- 3.1 订单状态分布
SELECT
    订单状态,
    COUNT(*) AS 数量,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders), 2) AS 占比
FROM orders
GROUP BY 订单状态
ORDER BY 数量 DESC;


-- 3.2 异常数据：签收时间早于下单时间？
SELECT
    COUNT(*) AS 异常数,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM orders WHERE 客户签收时间 IS NOT NULL), 2) AS 占比
FROM orders
WHERE 客户签收时间 IS NOT NULL
  AND 客户签收时间 < 下单时间;


-- 3.3 订单各环节耗时（仅 delivered 订单）
SELECT
    AVG(TIMESTAMPDIFF(HOUR, 下单时间, 订单确认时间)) AS 平均确认耗时小时,
    AVG(TIMESTAMPDIFF(DAY, 订单确认时间, 交付物流时间)) AS 平均发货天数,
    AVG(TIMESTAMPDIFF(DAY, 交付物流时间, 客户签收时间)) AS 平均物流天数,
    AVG(TIMESTAMPDIFF(DAY, 下单时间, 客户签收时间)) AS 平均全程天数
FROM orders
WHERE 订单状态 = 'delivered';


-- ============================================================
-- 第四组：支付分析
-- ============================================================

-- 4.1 支付方式分布
SELECT
    支付方式,
    COUNT(*) AS 数量,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM order_payments), 2) AS 占比,
    ROUND(AVG(支付金额), 2) AS 平均金额,
    ROUND(SUM(支付金额), 2) AS 总金额
FROM order_payments
GROUP BY 支付方式
ORDER BY 数量 DESC;


-- 4.2 信用卡分期情况
SELECT
    分期期数,
    COUNT(*) AS 数量,
    ROUND(AVG(支付金额), 2) AS 平均金额
FROM order_payments
WHERE 支付方式 = 'credit_card'
GROUP BY 分期期数
ORDER BY 分期期数;


-- ============================================================
-- 第五组：商品与评分
-- ============================================================

-- 5.1 各品类商品数量（取前 15）
SELECT
    t.品类名英文 AS 品类,
    COUNT(*) AS 商品数量
FROM products p
JOIN product_category_translation t
    ON p.商品品类名 = t.品类名
GROUP BY t.品类名英文
ORDER BY 商品数量 DESC
LIMIT 15;


-- 5.2 评分分布
SELECT
    评分,
    COUNT(*) AS 数量,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM order_reviews), 2) AS 占比
FROM order_reviews
GROUP BY 评分
ORDER BY 评分 DESC;


-- ============================================================
-- 第六组：多表关联（核心）
-- ============================================================

-- 6.1 订单 + 商品明细 + 品类（四表 JOIN）
SELECT
    o.订单ID,
    o.下单时间,
    o.订单状态,
    t.品类名英文 AS 品类,
    oi.价格,
    oi.运费
FROM orders o
JOIN order_items oi ON o.订单ID = oi.订单ID
JOIN products p ON oi.商品ID = p.商品ID
JOIN product_category_translation t ON p.商品品类名 = t.品类名
WHERE o.订单状态 = 'delivered'
LIMIT 20;


-- 6.2 每品类月度销售额（分析的核心基础查询）
SELECT
    DATE_FORMAT(o.下单时间, '%Y-%m') AS 月份,
    t.品类名英文 AS 品类,
    ROUND(SUM(oi.价格), 2) AS 销售额,
    COUNT(DISTINCT o.订单ID) AS 订单量,
    COUNT(DISTINCT o.客户ID) AS 客户数
FROM orders o
JOIN order_items oi ON o.订单ID = oi.订单ID
JOIN products p ON oi.商品ID = p.商品ID
JOIN product_category_translation t ON p.商品品类名 = t.品类名
WHERE o.订单状态 = 'delivered'
GROUP BY 月份, 品类
ORDER BY 月份, 销售额 DESC;
