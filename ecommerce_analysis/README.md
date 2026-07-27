# 电商平台用户消费行为分析

基于 Olist 巴西电商平台 9 张业务表、160 万行真实交易数据，使用 MySQL + Python + Excel 完成从数据入库到业务结论输出的全链路分析。

---

## 数据概况

| 表名 | 行数 | 说明 |
|---|---|---|
| orders | 10.8 万 | 订单记录（时间、状态） |
| order_items | 11.2 万 | 商品明细（价格、运费） |
| order_payments | 10.9 万 | 支付记录（方式、分期） |
| order_reviews | 9.9 万 | 用户评价（评分、评论） |
| customers | 10.5 万 | 客户信息 |
| products | 3.0 万 | 商品信息 |
| sellers | 0.3 万 | 卖家信息 |
| geolocation | 100 万 | 地理位置 |
| product_category_translation | 71 | 品类名称翻译 |

---

## 项目流程

### Day 1: 数据入库
将 9 个 CSV 文件导入 MySQL，完成表结构设计与批量数据写入（day1_import.py）

### Day 2: SQL 数据探查
12 条 SQL 查询覆盖数据量级、时间跨度、订单状态分布、支付方式、评分分布及多表关联（day2_explore.sql）

### Day 3: SQL + Python 可视化
SQL 聚合 → Python 接收并生成 4 张分析图（day3_analysis.py）

### Day 4: 业务分析
- RFM 用户分层（高价值客户占 33.7%）
- 客户消费金额分层
- 评分与消费行为关联分析（相关系数 -0.33）

### Day 5: Excel 交叉验证
核心指标导出 CSV，Excel 数据透视表独立验证

---

## 核心发现

- 平台月度订单量稳定增长，2017 年底至 2018 年初为高峰期
- 信用卡占支付方式的 74%，为主要支付渠道
- 用户评分集中在 4-5 分（占 76%），整体满意度较高
- 高评分用户消费金额略低于低评分用户，提示差评可能来自高价商品不满
- 平台复购率接近 0%，核心问题在用户留存而非获客

---

## 技术栈

**MySQL / SQL / Python (pandas, matplotlib) / Excel**

---

## 文件说明

| 文件 | 内容 |
|---|---|
| day1_import.py | CSV 导入 MySQL 脚本 |
| day2_explore.sql | 数据探查 SQL 查询 |
| day3_analysis.py | 可视化分析（月度趋势、品类、支付、评分） |
| day4_business.py | RFM 分层、消费分层、评分关联 |
| day5_export.py | Excel 验证数据导出 |
| outputs/ | 分析图表 |
