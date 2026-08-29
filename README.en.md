# 🏪 ai-shop-saas — AI Customer Service SaaS (Payments + Deployment + User System)

> Stage 3 · Lesson 3: Product Engineering — Turning the Agent capabilities from the previous two lessons into a **revenue-generating SaaS**

## 🎯 What This Lesson Solves

The previous two lessons built AI customer service agents with **memory** and **planning** capabilities, but:
- ❌ No user system → accessible to everyone, impossible to charge
- ❌ No orders/payments → AI can only chat, can't close deals
- ❌ Standalone scripts → impossible to deploy for others

This lesson: **Multi-tenant SaaS** — Each shop owner registers an account, opens a store, configures their own price list. The AI customer service automatically handles customers, and orders flow through simulated payments.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│  Flask Web (app.py)                          │
│  ├─ User System   Register/Login/Token Auth  │
│  ├─ Shop Management  Price List/Welcome/     │
│  │                  Plans (Multi-tenant)     │
│  ├─ AI Customer Service  POST /api/chat      │
│  ├─ Order & Payment  Order→Pay→Callback→     │
│  │                  Order Status Flow        │
│  └─ Demo Page     Browser Console            │
├─────────────────────────────────────────────┤
│  AI Engine (ai_engine.py)  Memory + Pricing  │
│                            + Order Intent    │
├─────────────────────────────────────────────┤
│  Database (db.py)  SQLite Multi-table        │
│   users / shops / orders / payments / messages│
└─────────────────────────────────────────────┘
```

## 🚀 Quick Start

```bash
# 1. Set your API Key
$env:DEEPSEEK_API_KEY = "sk-xxx"

# 2. Launch (includes demo console)
python app.py
# Open http://localhost:5000
```

## 📡 API Overview

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | /api/register | Register shop owner (auto-creates store) | - |
| POST | /api/login | Login to get token | - |
| GET | /api/shop | Get my shop info | ✅ |
| PUT | /api/shop/prices | Update price list | ✅ |
| POST | /api/chat | Customer consults AI agent | - |
| POST | /api/order | Create order | - |
| POST | /api/pay | Create payment (simulated) | - |
| POST | /api/pay/confirm | Payment callback | - |
| GET | /api/orders | List orders | - |
| GET | /api/messages | Chat history | - |

## 🐳 Docker Deployment

```bash
docker build -t ai-shop-saas .
docker run -d -p 5000:5000 -e DEEPSEEK_API_KEY=sk-xxx ai-shop-saas
```

## 🧠 Key Technical Points (Essential for Productization)

1. **Multi-tenant Isolation**: All tables carry `shop_id`; engine/memory instantiated per shop — Store A cannot see Store B's data
2. **Token Authentication**: `secrets.token_hex` + `@require_auth` decorator (swap for JWT/Redis in production)
3. **Payment State Machine**: Orders `pending→paid→shipped→done`; payments `pending→success/failed`; callbacks are idempotent (already-successful payments are not reprocessed)
4. **Pluggable AI Engine**: `ShopAIEngine` encapsulates memory + pricing + order intent; Flask handles only the HTTP layer
5. **Order Intent Detection**: Rule-first approach ("order/buy" keywords + model matching) for stability; LLM handles natural conversation
6. **Layered Deployment**: Dockerfile + Tsinghua mirror acceleration + environment variable key injection

## 📌 Pitfalls & Lessons Learned

- **Fuzzy model matching false positives**: Customer asking for iPhone 13 got matched to 16 Pro Max (digit substring) → fixed with "exact model number match + storage validation"
- **PowerShell Chinese request body encoding**: `Invoke-RestMethod` mangles Chinese to `??` — use `python -c` or explicit UTF-8 encoding (server-side unaffected)
- **Flask 3 syntax**: `@app.post/@app.get` shorthand routes work fine

## 🔗 Related Projects (Stage 3 Series)

1. ai-knowledge-shop — RAG deep engineering (knowledge base)
2. ai-memory-agent — Agent memory system (remembers customers)
3. ai-react-planner — Agent planning capabilities (finds solutions)
4. **ai-shop-saas — Productization (generates revenue)** ← This lesson

## 🎯 What You'll Be Able to Do

- Upgrade any standalone Agent project into a multi-tenant web service
- Integrate real payments (WeChat/Alipay) by simply swapping `db.create_payment/confirm_payment` with SDK calls
- Deploy to a cloud server (Docker + Nginx + HTTPS) and go live for clients

---