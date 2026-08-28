# -*- coding: utf-8 -*-
"""
ai-shop-saas · 数据库层
========================
阶段3 · 第3课：产品化工程（支付 + 部署 + 用户系统）

多租户 SaaS 数据模型：
  users      → 店主（注册/登录，每个店主一个店铺）
  shops      → 店铺（店名、欢迎语、报价表 JSON）
  orders     → 订单（客户下单，关联支付）
  payments   → 支付记录（模拟支付网关）
  messages   → 客户咨询记录（AI 客服对话留痕）

SQLite 单文件数据库，生产可换 PostgreSQL（模型不变）。
"""

import os
import json
import sqlite3
import time
import hashlib

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saas.db")


# ============ 连接 ============
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT UNIQUE NOT NULL,
        password    TEXT NOT NULL,          -- sha256(password + salt)
        salt        TEXT NOT NULL,
        created_at  INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS shops (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id    INTEGER NOT NULL REFERENCES users(id),
        name        TEXT NOT NULL,
        welcome_msg TEXT DEFAULT '您好，欢迎光临！有什么可以帮您？',
        price_table TEXT DEFAULT '{}',      -- JSON: {"iPhone 16 Pro Max 512G": 6100, ...}
        plan        TEXT DEFAULT 'free',    -- free | pro | enterprise
        created_at  INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS orders (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id     INTEGER NOT NULL REFERENCES shops(id),
        customer    TEXT NOT NULL,
        item        TEXT NOT NULL,
        amount      REAL NOT NULL,
        status      TEXT DEFAULT 'pending', -- pending | paid | shipped | done | cancelled
        created_at  INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS payments (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id    INTEGER NOT NULL REFERENCES orders(id),
        method      TEXT NOT NULL,          -- wechat | alipay | card
        amount      REAL NOT NULL,
        status      TEXT DEFAULT 'pending', -- pending | success | failed
        tx_id       TEXT UNIQUE,            -- 模拟交易号
        created_at  INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id     INTEGER NOT NULL REFERENCES shops(id),
        role        TEXT NOT NULL,          -- user | assistant
        content     TEXT NOT NULL,
        created_at  INTEGER NOT NULL
    );
    """)
    conn.commit()
    conn.close()


# ============ 用户系统 ============
def hash_password(password, salt):
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


def register(username, password):
    """注册店主。成功返回 user_id，失败抛 ValueError"""
    conn = get_db()
    try:
        exists = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            raise ValueError("用户名已存在")
        salt = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        cur = conn.execute(
            "INSERT INTO users (username, password, salt, created_at) VALUES (?,?,?,?)",
            (username, hash_password(password, salt), salt, int(time.time())),
        )
        uid = cur.lastrowid
        # 自动创建默认店铺
        conn.execute(
            "INSERT INTO shops (owner_id, name, welcome_msg, price_table, plan, created_at) VALUES (?,?,?,?,?,?)",
            (uid, f"{username}的手机店", "您好，欢迎光临！有什么可以帮您？",
             json.dumps({"iPhone 16 Pro Max 512G": 6100, "iPhone 16 Pro Max 256G": 5400}, ensure_ascii=False),
             "free", int(time.time())),
        )
        conn.commit()
        return uid
    finally:
        conn.close()


def login(username, password):
    """登录。成功返回 user dict，失败返回 None"""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        if row["password"] != hash_password(password, row["salt"]):
            return None
        return dict(row)
    finally:
        conn.close()


def get_shop(owner_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM shops WHERE owner_id=?", (owner_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_price_table(owner_id, price_table):
    """更新店铺报价表（JSON 字符串）"""
    conn = get_db()
    try:
        conn.execute("UPDATE shops SET price_table=? WHERE owner_id=?", (price_table, owner_id))
        conn.commit()
    finally:
        conn.close()


# ============ 订单 + 支付 ============
def create_order(shop_id, customer, item, amount):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO orders (shop_id, customer, item, amount, status, created_at) VALUES (?,?,?,?,?,?)",
            (shop_id, customer, item, amount, "pending", int(time.time())),
        )
        oid = cur.lastrowid
        conn.commit()
        return oid
    finally:
        conn.close()


def get_order(order_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_orders(shop_id, limit=20):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE shop_id=? ORDER BY id DESC LIMIT ?",
            (shop_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ============ 模拟支付网关 ============
def create_payment(order_id, method):
    """创建支付单，返回支付信息（含模拟支付链接）"""
    order = get_order(order_id)
    if not order:
        raise ValueError("订单不存在")
    conn = get_db()
    try:
        tx_id = f"TX{int(time.time())}{order_id}"
        cur = conn.execute(
            "INSERT INTO payments (order_id, method, amount, status, tx_id, created_at) VALUES (?,?,?,?,?,?)",
            (order_id, method, order["amount"], "pending", tx_id, int(time.time())),
        )
        conn.commit()
        return {
            "payment_id": cur.lastrowid,
            "tx_id": tx_id,
            "amount": order["amount"],
            "method": method,
            "pay_url": f"/api/pay/confirm/{tx_id}",  # 模拟支付链接
        }
    finally:
        conn.close()


def confirm_payment(tx_id, success=True):
    """模拟支付回调：确认支付结果"""
    conn = get_db()
    try:
        pay = conn.execute("SELECT * FROM payments WHERE tx_id=?", (tx_id,)).fetchone()
        if not pay:
            return False, "支付单不存在"
        if pay["status"] == "success":
            return True, "已支付"
        status = "success" if success else "failed"
        conn.execute("UPDATE payments SET status=? WHERE id=?", (status, pay["id"]))
        if success:
            # 支付成功 → 订单状态改为 paid
            conn.execute("UPDATE orders SET status='paid' WHERE id=?", (pay["order_id"],))
        conn.commit()
        return True, f"支付{'成功' if success else '失败'}"
    finally:
        conn.close()


# ============ 消息记录 ============
def save_message(shop_id, role, content):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO messages (shop_id, role, content, created_at) VALUES (?,?,?,?)",
            (shop_id, role, content, int(time.time())),
        )
        conn.commit()
    finally:
        conn.close()


def list_messages(shop_id, limit=50):
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM messages WHERE shop_id=? ORDER BY id DESC LIMIT ?",
            (shop_id, limit),
        ).fetchall()
        return [dict(r) for r in rows][::-1]
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("✅ 数据库初始化完成:", DB_PATH)
    # 自测
    uid = register("test_boss", "123456")
    print(f"✅ 注册店主 test_boss → id={uid}")
    u = login("test_boss", "123456")
    print(f"✅ 登录: {'成功' if u else '失败'}")
    shop = get_shop(uid)
    print(f"✅ 店铺: {shop['name']} (plan={shop['plan']})")
    oid = create_order(shop["id"], "张哥", "iPhone 16 Pro Max 512G", 6100)
    print(f"✅ 创建订单 #{oid}")
    pay = create_payment(oid, "wechat")
    print(f"✅ 创建支付: {pay['tx_id']} 金额{pay['amount']}")
    ok, msg = confirm_payment(pay["tx_id"])
    print(f"✅ 模拟支付回调: {msg}")
    order = get_order(oid)
    print(f"✅ 订单状态: {order['status']}")
    save_message(shop["id"], "user", "老板在吗？")
    save_message(shop["id"], "assistant", "在的！")
    print(f"✅ 消息记录: {len(list_messages(shop['id']))} 条")
    print("\n🎉 数据库层自测全部通过")
