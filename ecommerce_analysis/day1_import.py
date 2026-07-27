"""
Day 1: CSV → MySQL 数据库表
目标：创建 ecommerce_analysis 数据库，导入 Olist 电商数据集
"""
import pymysql
import csv
import os

# ============ 配置 ============
MYSQL_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': '123456',
    'charset': 'utf8mb4'
}
DATA_DIR = r'C:\Users\86186\Desktop\ecommerce_project\data'

# ============ 连接 MySQL（先不指定数据库） ============
conn = pymysql.connect(**MYSQL_CONFIG)
cur = conn.cursor()

# ============ 1. 创建数据库 ============
cur.execute("DROP DATABASE IF EXISTS ecommerce_analysis")
cur.execute("CREATE DATABASE ecommerce_analysis DEFAULT CHARSET utf8mb4")
cur.execute("USE ecommerce_analysis")
print("[OK] 数据库 ecommerce_analysis 创建成功")

# ============ 2. 创建所有表 ============

# 客户表
cur.execute("""
CREATE TABLE customers (
    customer_id VARCHAR(32) PRIMARY KEY,
    customer_unique_id VARCHAR(32) NOT NULL,
    customer_zip_code_prefix VARCHAR(10),
    customer_city VARCHAR(100),
    customer_state VARCHAR(2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 订单表
cur.execute("""
CREATE TABLE orders (
    order_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    order_status VARCHAR(20),
    order_purchase_timestamp DATETIME,
    order_approved_at DATETIME,
    order_delivered_carrier_date DATETIME,
    order_delivered_customer_date DATETIME,
    order_estimated_delivery_date DATETIME,
    INDEX idx_customer (customer_id),
    INDEX idx_purchase_date (order_purchase_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 订单商品明细表
cur.execute("""
CREATE TABLE order_items (
    order_id VARCHAR(32),
    order_item_id INT,
    product_id VARCHAR(32),
    seller_id VARCHAR(32),
    shipping_limit_date DATETIME,
    price DECIMAL(10,2),
    freight_value DECIMAL(10,2),
    PRIMARY KEY (order_id, order_item_id),
    INDEX idx_product (product_id),
    INDEX idx_seller (seller_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 支付表
cur.execute("""
CREATE TABLE order_payments (
    order_id VARCHAR(32),
    payment_sequential INT,
    payment_type VARCHAR(20),
    payment_installments INT,
    payment_value DECIMAL(10,2),
    PRIMARY KEY (order_id, payment_sequential)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 评价表（注意：review_id 有重复，这是真实数据特征）
cur.execute("""
CREATE TABLE order_reviews (
    review_id VARCHAR(32) NOT NULL,
    order_id VARCHAR(32) NOT NULL,
    review_score INT,
    review_comment_title TEXT,
    review_comment_message TEXT,
    review_creation_date DATETIME,
    review_answer_timestamp DATETIME,
    INDEX idx_review (review_id),
    INDEX idx_order_review (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 商品表
cur.execute("""
CREATE TABLE products (
    product_id VARCHAR(32) PRIMARY KEY,
    product_category_name VARCHAR(100),
    product_name_lenght INT,
    product_description_lenght INT,
    product_photos_qty INT,
    product_weight_g INT,
    product_length_cm INT,
    product_height_cm INT,
    product_width_cm INT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 卖家表
cur.execute("""
CREATE TABLE sellers (
    seller_id VARCHAR(32) PRIMARY KEY,
    seller_zip_code_prefix VARCHAR(10),
    seller_city VARCHAR(100),
    seller_state VARCHAR(2)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 地理位置表
cur.execute("""
CREATE TABLE geolocation (
    geolocation_zip_code_prefix VARCHAR(10),
    geolocation_lat DECIMAL(15,12),
    geolocation_lng DECIMAL(15,12),
    geolocation_city VARCHAR(100),
    geolocation_state VARCHAR(2),
    INDEX idx_zip (geolocation_zip_code_prefix)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

# 品类名称翻译表
cur.execute("""
CREATE TABLE product_category_translation (
    product_category_name VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""")

print("[OK] 9 张表创建完成")

# ============ 3. 导入 CSV 数据 ============

def import_csv(table_name, csv_filename, clean_func=None):
    """把 CSV 文件导入到 MySQL 表"""
    filepath = os.path.join(DATA_DIR, csv_filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        # 处理 BOM 字符
        first_line = f.readline()
        first_line = first_line.lstrip('﻿')
        f.seek(0)

        reader = csv.reader(f)
        headers = next(reader)
        # 清理 BOM
        headers[0] = headers[0].lstrip('﻿')

        placeholders = ', '.join(['%s'] * len(headers))
        cols = ', '.join([f'`{h}`' for h in headers])
        sql = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

        batch = []
        count = 0
        for row in reader:
            if clean_func:
                row = clean_func(row)
            # 空字符串转 None（NULL）
            row = [None if v == '' else v for v in row]
            batch.append(row)
            if len(batch) >= 5000:
                cur.executemany(sql, batch)
                conn.commit()
                count += len(batch)
                batch = []
                print(f'  {table_name}: {count:,} rows...', end='\r')

        if batch:
            cur.executemany(sql, batch)
            conn.commit()
            count += len(batch)

        print(f'  {table_name}: {count:,} rows imported     ')

# 按依赖顺序导入（先导被外键引用的表）
import_csv('customers',         'olist_customers_dataset.csv')
import_csv('sellers',           'olist_sellers_dataset.csv')
import_csv('products',          'olist_products_dataset.csv')
import_csv('orders',            'olist_orders_dataset.csv')
import_csv('order_items',       'olist_order_items_dataset.csv')
import_csv('order_payments',    'olist_order_payments_dataset.csv')
import_csv('order_reviews',     'olist_order_reviews_dataset.csv')
import_csv('geolocation',       'olist_geolocation_dataset.csv')
import_csv('product_category_translation', 'product_category_name_translation.csv')

print("\n[OK] 全部数据导入完成！")

# ============ 4. 验证数据 ============
cur.execute("""
    SELECT TABLE_NAME, TABLE_ROWS
    FROM information_schema.TABLES
    WHERE TABLE_SCHEMA = 'ecommerce_analysis'
    ORDER BY TABLE_NAME
""")
print("\n========== 数据验证 ==========")
for table_name, row_count in cur.fetchall():
    print(f"  {table_name:35s} {row_count:>12,} rows")

cur.close()
conn.close()
print("\n[Done] Day 1 完成！9 张表已全部导入 MySQL 数据库 ecommerce_analysis")
