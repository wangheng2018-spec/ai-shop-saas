# 🏪 ai-shop-saas — AI 客服 SaaS（支付 + 部署 + 用户系统）

> 阶段3 · 第3课：产品化工程 —— 把前两课的 Agent 能力包装成**能收钱的 SaaS**

## 🎯 这课解决什么

前两课做出了会**记忆**、会**规划**的 AI 客服，但：
- ❌ 没有用户系统 → 谁都能用，没法收费
- ❌ 没有订单/支付 → AI 只会聊天，不能成交
- ❌ 单机脚本 → 没法给别人部署

本课：**多租户 SaaS** —— 每个店主注册一个账号、开一家店、配自己的报价表，AI 客服自动接待客户，客户下单走模拟支付。

## 🏗️ 架构

```
┌─────────────────────────────────────────────┐
│  Flask Web (app.py)                          │
│  ├─ 用户系统   注册/登录/token 鉴权           │
│  ├─ 店铺管理   报价表/欢迎语/套餐(多租户隔离)  │
│  ├─ AI 客服    POST /api/chat                │
│  ├─ 订单支付   下单→支付→回调→订单状态流转    │
│  └─ 演示页     浏览器控制台                   │
├─────────────────────────────────────────────┤
│  AI 引擎 (ai_engine.py)  记忆+报价+下单意图   │
├─────────────────────────────────────────────┤
│  数据库 (db.py)  SQLite 多表                 │
│   users / shops / orders / payments / messages│
└─────────────────────────────────────────────┘
```

## 🚀 运行

```bash
# 1. 设置 Key
$env:DEEPSEEK_API_KEY = "sk-xxx"

# 2. 启动（自带演示控制台）
python app.py
# 打开 http://localhost:5000
```

## 📡 API 一览

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | /api/register | 注册店主（自动开店） | - |
| POST | /api/login | 登录拿 token | - |
| GET | /api/shop | 我的店铺信息 | ✅ |
| PUT | /api/shop/prices | 更新报价表 | ✅ |
| POST | /api/chat | 客户咨询 AI 客服 | - |
| POST | /api/order | 创建订单 | - |
| POST | /api/pay | 创建支付（模拟） | - |
| POST | /api/pay/confirm | 支付回调 | - |
| GET | /api/orders | 订单列表 | - |
| GET | /api/messages | 咨询记录 | - |

## 🐳 Docker 部署

```bash
docker build -t ai-shop-saas .
docker run -d -p 5000:5000 -e DEEPSEEK_API_KEY=sk-xxx ai-shop-saas
```

## 🧠 关键技术点（产品化必会）

1. **多租户隔离**：所有表带 `shop_id`，引擎/记忆按店铺实例化，A 店看不到 B 店数据
2. **Token 鉴权**：`secrets.token_hex` + 装饰器 `@require_auth`（生产换 JWT/Redis）
3. **支付状态机**：订单 `pending→paid→shipped→done`，支付单 `pending→success/failed`，回调幂等（已成功不重复处理）
4. **AI 引擎插拔**：`ShopAIEngine` 封装 记忆+报价+下单意图，Flask 只做 HTTP 层
5. **下单意图检测**：规则优先（"下单/买了"关键词 + 机型匹配）保证稳定，LLM 负责自然对话
6. **部署分层**：Dockerfile + 清华源加速 + 环境变量注入 key

## 📌 踩坑记录

- **机型模糊匹配误伤**：客户要 iPhone 13 却匹配到 16 Pro Max（数字子串）→ 改为"型号数字精确相等 + 容量校验"
- **PowerShell 中文请求体乱码**：Invoke-RestMethod 发中文会变 `??`，用 `python -c` 或 UTF-8 显式编码（服务端无此问题）
- **Flask 3 语法**：`@app.post/@app.get` 简写路由可用

## 🔗 关联作品（阶段3 系列）

1. ai-knowledge-shop — RAG 深度工程（知识库）
2. ai-memory-agent — Agent 记忆系统（记得客户）
3. ai-react-planner — Agent 规划能力（会想办法）
4. **ai-shop-saas — 产品化（能收钱）** ← 本课

## 🎯 学完能干什么

- 把任意单机 Agent 项目升级成多租户 Web 服务
- 接真实支付（微信/支付宝）时只需替换 `db.create_payment/confirm_payment` 为 SDK 调用
- 部署到云服务器（Docker + Nginx + HTTPS）就能上线接单
