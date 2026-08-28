# -*- coding: utf-8 -*-
"""
ai-shop-saas · Web 服务层（Flask）
===================================
阶段3 · 第3课：产品化工程

API 一览（多租户 SaaS）：
  POST /api/register         店主注册 → 自动开店
  POST /api/login            登录 → 返回 token
  GET  /api/shop             查看我的店铺
  PUT  /api/shop/prices      更新报价表
  POST /api/chat             客户咨询 AI 客服 {shop_id, customer, message}
  POST /api/order            创建订单 {shop_id, customer, item, amount}
  POST /api/pay              创建支付 {order_id, method} → 模拟支付链接
  POST /api/pay/confirm      支付回调 {tx_id} → 支付成功
  GET  /api/orders           订单列表 {shop_id}
  GET  /api/messages         消息记录 {shop_id}

安全：token 鉴权（简单版，生产用 JWT）+ 多租户隔离（shop 归属校验）

运行: python app.py  →  http://localhost:5000
"""

import os
import json
import time
import hashlib
import secrets
from functools import wraps

from flask import Flask, request, jsonify, render_template_string

import db
from ai_engine import ShopAIEngine

app = Flask(__name__)

# ============ Token 管理（内存版，生产换 Redis/JWT） ============
_tokens = {}  # token -> user_id


def make_token(user_id):
    token = secrets.token_hex(16)
    _tokens[token] = user_id
    return token


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        uid = _tokens.get(token)
        if not uid:
            return jsonify({"ok": False, "msg": "未登录或登录过期"}), 401
        return fn(*args, **kwargs, uid=uid)
    return wrapper


# ============ 用户系统 ============
@app.post("/api/register")
def api_register():
    data = request.get_json(force=True)
    username, password = data.get("username", "").strip(), data.get("password", "")
    if not username or not password:
        return jsonify({"ok": False, "msg": "用户名和密码不能为空"})
    if len(password) < 6:
        return jsonify({"ok": False, "msg": "密码至少6位"})
    try:
        uid = db.register(username, password)
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)})
    return jsonify({"ok": True, "user_id": uid, "token": make_token(uid)})


@app.post("/api/login")
def api_login():
    data = request.get_json(force=True)
    user = db.login(data.get("username", ""), data.get("password", ""))
    if not user:
        return jsonify({"ok": False, "msg": "用户名或密码错误"})
    return jsonify({"ok": True, "user_id": user["id"], "token": make_token(user["id"])})


# ============ 店铺管理 ============
@app.get("/api/shop")
@require_auth
def api_get_shop(uid):
    shop = db.get_shop(uid)
    if not shop:
        return jsonify({"ok": False, "msg": "店铺不存在"})
    shop["price_table"] = json.loads(shop["price_table"] or "{}")
    return jsonify({"ok": True, "shop": shop})


@app.put("/api/shop/prices")
@require_auth
def api_update_prices(uid):
    data = request.get_json(force=True)
    prices = data.get("price_table")
    if not isinstance(prices, dict):
        return jsonify({"ok": False, "msg": "price_table 必须是 JSON 对象"})
    db.update_price_table(uid, json.dumps(prices, ensure_ascii=False))
    return jsonify({"ok": True, "msg": "报价表已更新"})


# ============ AI 客服 ============
_engines = {}       # shop_id -> ShopAIEngine
_memory_stores = {} # shop_id -> {customer: [history]}


def get_engine(shop):
    sid = shop["id"]
    if sid not in _engines:
        _memory_stores[sid] = {}
        _engines[sid] = ShopAIEngine(
            shop_id=sid,
            shop_name=shop["name"],
            welcome=shop["welcome_msg"],
            price_table=json.loads(shop["price_table"] or "{}"),
            memory_store=_memory_stores[sid],
        )
    return _engines[sid]


@app.post("/api/chat")
def api_chat():
    """客户咨询（无需登录，客户不登录系统）"""
    data = request.get_json(force=True)
    shop_id = data.get("shop_id")
    customer = data.get("customer", "游客")
    message = data.get("message", "").strip()
    if not shop_id or not message:
        return jsonify({"ok": False, "msg": "缺少 shop_id 或 message"})
    # 校验店铺存在
    import sqlite3
    conn = db.get_db()
    try:
        shop_row = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
    finally:
        conn.close()
    if not shop_row:
        return jsonify({"ok": False, "msg": "店铺不存在"})
    shop = dict(shop_row)

    # 保存客户消息
    db.save_message(shop_id, "user", message)

    # AI 回复
    engine = get_engine(shop)
    result = engine.chat(customer, message, auto_order=False)

    # 保存 AI 回复
    db.save_message(shop_id, "assistant", result["reply"])

    return jsonify({"ok": True, "reply": result["reply"]})


# ============ 订单 + 支付 ============
@app.post("/api/order")
def api_create_order():
    data = request.get_json(force=True)
    shop_id, customer, item, amount = (
        data.get("shop_id"), data.get("customer", "游客"),
        data.get("item", ""), data.get("amount", 0),
    )
    if not shop_id or not item or not amount:
        return jsonify({"ok": False, "msg": "缺少 shop_id/item/amount"})
    oid = db.create_order(shop_id, customer, item, float(amount))
    return jsonify({"ok": True, "order_id": oid, "status": "pending"})


@app.post("/api/pay")
def api_create_pay():
    data = request.get_json(force=True)
    try:
        pay = db.create_payment(data.get("order_id"), data.get("method", "wechat"))
    except ValueError as e:
        return jsonify({"ok": False, "msg": str(e)})
    return jsonify({"ok": True, "payment": pay})


@app.post("/api/pay/confirm")
def api_pay_confirm():
    data = request.get_json(force=True)
    ok, msg = db.confirm_payment(data.get("tx_id", ""))
    return jsonify({"ok": ok, "msg": msg})


@app.get("/api/orders")
def api_list_orders():
    shop_id = request.args.get("shop_id")
    if not shop_id:
        return jsonify({"ok": False, "msg": "缺少 shop_id"})
    return jsonify({"ok": True, "orders": db.list_orders(int(shop_id))})


@app.get("/api/messages")
def api_list_messages():
    shop_id = request.args.get("shop_id")
    if not shop_id:
        return jsonify({"ok": False, "msg": "缺少 shop_id"})
    return jsonify({"ok": True, "messages": db.list_messages(int(shop_id))})


# ============ 演示页面 ============
INDEX_HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>AI 店铺 SaaS · 演示</title>
<style>
  body { font-family: system-ui; max-width: 900px; margin: 40px auto; padding: 0 20px; background:#f7f8fa; }
  h1 { color: #1a73e8; }
  .card { background:#fff; border-radius:12px; padding:20px; margin:16px 0; box-shadow:0 2px 8px rgba(0,0,0,.08); }
  input, button, select { padding:8px 12px; margin:4px; border-radius:8px; border:1px solid #ddd; font-size:14px; }
  button { background:#1a73e8; color:#fff; border:none; cursor:pointer; }
  button:hover { background:#1558b0; }
  pre { background:#f0f0f0; padding:10px; border-radius:8px; overflow-x:auto; }
  .ok { color:green; } .err { color:red; }
</style>
</head>
<body>
<h1>🏪 AI 店铺 SaaS · 演示控制台</h1>

<div class="card">
  <h3>① 注册店主（自动开店）</h3>
  <input id="reg_u" placeholder="用户名"><input id="reg_p" type="password" placeholder="密码(≥6位)">
  <button onclick="register()">注册</button>
  <span id="reg_res"></span>
</div>

<div class="card">
  <h3>② 登录（拿 token）</h3>
  <input id="login_u" placeholder="用户名"><input id="login_p" type="password" placeholder="密码">
  <button onclick="login()">登录</button>
  <span id="login_res"></span>
</div>

<div class="card">
  <h3>③ 我的店铺</h3>
  <button onclick="getShop()">查看店铺</button>
  <pre id="shop_res">(登录后点此查看)</pre>
</div>

<div class="card">
  <h3>④ 客户咨询 AI 客服</h3>
  <input id="chat_shop" placeholder="shop_id" value="1" style="width:70px">
  <input id="chat_cust" placeholder="客户名" value="张哥">
  <input id="chat_msg" placeholder="问点什么…" value="16 Pro Max 512G 多少钱？" style="width:280px">
  <button onclick="chat()">发送</button>
  <pre id="chat_res"></pre>
</div>

<div class="card">
  <h3>⑤ 下单 + 模拟支付</h3>
  <input id="ord_shop" placeholder="shop_id" value="1" style="width:70px">
  <input id="ord_item" value="iPhone 16 Pro Max 512G">
  <input id="ord_amount" value="6100" style="width:90px">
  <button onclick="createOrder()">创建订单</button>
  <pre id="ord_res"></pre>
</div>

<script>
let TOKEN = '';
async function api(url, method='GET', body=null) {
  const opt = {method, headers: {'Content-Type': 'application/json'}};
  if (TOKEN) opt.headers['Authorization'] = 'Bearer ' + TOKEN;
  if (body) opt.body = JSON.stringify(body);
  const r = await fetch(url, opt);
  return r.json();
}
function show(el, obj) { document.getElementById(el).textContent = JSON.stringify(obj, null, 2); }
async function register() {
  const r = await api('/api/register', 'POST', {username: document.getElementById('reg_u').value, password: document.getElementById('reg_p').value});
  if (r.token) TOKEN = r.token;
  document.getElementById('reg_res').textContent = r.ok ? '✅ 注册成功 token=' + r.token.slice(0,8)+'...' : '❌ ' + r.msg;
  show('shop_res', r);
}
async function login() {
  const r = await api('/api/login', 'POST', {username: document.getElementById('login_u').value, password: document.getElementById('login_p').value});
  if (r.token) TOKEN = r.token;
  document.getElementById('login_res').textContent = r.ok ? '✅ 登录成功 token=' + r.token.slice(0,8)+'...' : '❌ ' + r.msg;
}
async function getShop() { show('shop_res', await api('/api/shop')); }
async function chat() {
  const r = await api('/api/chat', 'POST', {
    shop_id: parseInt(document.getElementById('chat_shop').value),
    customer: document.getElementById('chat_cust').value,
    message: document.getElementById('chat_msg').value,
  });
  show('chat_res', r);
}
async function createOrder() {
  const r = await api('/api/order', 'POST', {
    shop_id: parseInt(document.getElementById('ord_shop').value),
    customer: '张哥',
    item: document.getElementById('ord_item').value,
    amount: parseFloat(document.getElementById('ord_amount').value),
  });
  show('ord_res', r);
  if (r.order_id) {
    const pay = await api('/api/pay', 'POST', {order_id: r.order_id, method: 'wechat'});
    document.getElementById('ord_res').textContent += '\\n\\n【模拟支付】' + JSON.stringify(pay, null, 2);
    if (pay.payment && pay.payment.tx_id) {
      const conf = await api('/api/pay/confirm', 'POST', {tx_id: pay.payment.tx_id});
      document.getElementById('ord_res').textContent += '\\n\\n【支付回调】' + JSON.stringify(conf, null, 2);
    }
  }
}
</script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(INDEX_HTML)


if __name__ == "__main__":
    db.init_db()
    print("✅ 数据库就绪")
    print("🌐 打开 http://localhost:5000 体验 SaaS 演示控制台")
    app.run(host="0.0.0.0", port=5000, debug=False)
