# -*- coding: utf-8 -*-
"""
ai-shop-saas · AI 引擎层
=========================
阶段3 · 第3课：把前两课的能力（记忆 + 规划）整合成 SaaS 的"客服大脑"

能力清单（模块化，可插拔）：
  1. 知识库 RAG：用店铺报价表 + 通用政策回答（复用 ai-knowledge-shop 思路）
  2. 客户记忆：按 customer 名/ID 记住历史（复用 ai-memory-agent 思路，简化版）
  3. 工具调用：查报价 / 创建订单（复用 ai-react-planner 思路）
  4. 多租户隔离：每个店铺独立的报价表、记忆、消息记录
"""

import os
import json
import re
import time
import requests

# ============ 配置 ============
DS_API_URL = "https://api.deepseek.com/chat/completions"
DS_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DS_MODEL = "deepseek-chat"


def call_llm(messages, temperature=0.4, max_tokens=600, retries=3):
    payload = {"model": DS_MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.post(DS_API_URL, json=payload, headers={
                "Authorization": "Bearer " + DS_API_KEY,
                "Content-Type": "application/json",
            }, timeout=60)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    raise last_err


# ============ 店铺 AI 引擎 ============
SHOP_SYSTEM_PROMPT = """你是{shop_name}的 AI 客服小助手，老板做二手手机生意。

【店铺资料】
- 欢迎语：{welcome}
- 当前报价表：{price_table}
- 交易政策：
  1. 支持闲鱼平台担保交易，同城可面交
  2. 发货前录制验机视频
  3. 7天无理由退换，15天内质量问题免费换机，1年店铺保修
  4. 请务必通过平台下单付款，不要私下转账
- 常用机型参考价（没有的请说"帮您问下老板"）：
{price_lines}

【客户记忆】
{memory}

【你的能力】
1. 报价：根据报价表回答，引导客户提供 型号+存储
2. 议价：可以小幅让步（95折底线），超过权限就说"帮您跟老板申请"
3. 售后：按交易政策回答
4. 下单：客户确定要买时，引导说"老板帮我下单"，系统会生成订单

【风格】
口语化、真诚、简短（2~4句），emoji不超过3个。记不得的客户信息不要编造。
"""


class ShopAIEngine:
    """一个店铺的 AI 客服引擎（多租户：每个店铺一个实例，记忆/报价隔离）"""

    def __init__(self, shop_id, shop_name, welcome, price_table, memory_store=None):
        self.shop_id = shop_id
        self.shop_name = shop_name
        self.welcome = welcome
        self.price_table = price_table  # dict
        self.memory_store = memory_store  # {customer: [历史消息]} 会话级
        self.conversation = []  # 当前会话上下文

    # ---- 构建系统提示 ----
    def _system_prompt(self, customer):
        price_lines = "\n".join(f"  - {k}: ¥{v}" for k, v in self.price_table.items()) or "  - （暂无）"
        memory_text = "无历史记录"
        if self.memory_store and customer in self.memory_store:
            history = self.memory_store[customer]
            memory_text = "\n".join(f"- {h}" for h in history[-6:])
        return SHOP_SYSTEM_PROMPT.format(
            shop_name=self.shop_name,
            welcome=self.welcome,
            price_table=json.dumps(self.price_table, ensure_ascii=False),
            price_lines=price_lines,
            memory=memory_text,
        )

    # ---- 工具：查报价 ----
    def _tool_query_price(self, text):
        # 优先精确匹配整串机型名
        for model in self.price_table:
            if model in text:
                return {"ok": True, "model": model, "price": self.price_table[model]}
        # 数字+容量匹配（如 "13 128G"）
        nums = re.findall(r"(\d{2,3})\s*(Pro\s*Max|Pro|Plus|mini)?\s*(\d{2,4}G)?", text)
        if nums:
            # 按文本中出现的顺序匹配，取最长的机型名
            candidates = []
            for n, suffix, capacity in nums:
                for model in self.price_table:
                    model_parts = model.replace("iPhone ", "").split()
                    model_num = model_parts[0] if model_parts else ""
                    if model_num == n and (not capacity or capacity.lower() in model.lower()):
                        candidates.append(model)
            if candidates:
                # 取容量最匹配的
                best = candidates[0]
                for model in candidates:
                    if capacity and capacity.lower() in model.lower():
                        best = model
                        break
                return {"ok": True, "model": best, "price": self.price_table[best]}
        return {"ok": False, "msg": "未找到匹配机型"}

    # ---- 工具：下单意向检测 ----
    def _tool_order_intent(self, text):
        """检测客户是否想下单（返回要买的机型，或 None）"""
        if any(k in text for k in ["下单", "买", "要了", "成交", "拍下", "就要"]):
            hit = self._tool_query_price(text)
            if hit["ok"]:
                return {"ok": True, "model": hit["model"], "price": hit["price"]}
        return {"ok": False}

    # ---- 主入口：回复客户 ----
    def chat(self, customer, user_msg, auto_order=True):
        """返回 {reply, order_created, order_id}"""
        # 1. 先检测下单意图（规则优先，保证稳定）
        order_intent = None
        if auto_order:
            order_intent = self._tool_order_intent(user_msg)
            if order_intent["ok"]:
                # 走 LLM 确认一下（更自然），同时准备下单
                pass

        # 2. 查报价（给 LLM 参考）
        price_hit = self._tool_query_price(user_msg)

        # 3. 拼上下文
        self.conversation.append({"role": "user", "content": user_msg})
        messages = [{"role": "system", "content": self._system_prompt(customer)}]
        messages += self.conversation[-8:]  # 最近8轮

        # 4. 调 LLM
        try:
            reply = call_llm(messages)
        except Exception as e:
            reply = f"抱歉，系统开小差了（{str(e)[:40]}），请稍后再试～"

        self.conversation.append({"role": "assistant", "content": reply})

        # 5. 记忆更新
        if self.memory_store is not None:
            self.memory_store.setdefault(customer, []).append(f"客:{user_msg}")
            self.memory_store[customer].append(f"店:{reply}")

        # 6. 下单
        order_created, order_id = False, None
        if auto_order and order_intent and order_intent["ok"]:
            order_created, order_id = True, order_intent["model"]
        return {
            "reply": reply,
            "order_created": order_created,
            "order_model": order_id if order_created else None,
            "price_hit": price_hit if price_hit["ok"] else None,
        }


if __name__ == "__main__":
    print("=" * 60)
    print("AI 引擎层自测")
    print("=" * 60)
    demo_prices = {"iPhone 16 Pro Max 512G": 6100, "iPhone 16 Pro Max 256G": 5400, "iPhone 13 128G": 2600}
    engine = ShopAIEngine(
        shop_id=1,
        shop_name="老王手机店",
        welcome="您好，欢迎光临！",
        price_table=demo_prices,
        memory_store={},
    )
    # 测试1: 报价
    r = engine.chat("张哥", "16 Pro Max 512G 多少钱？")
    print(f"\n[报价] {r['reply']}")
    # 测试2: 记忆（第二次来，应该记得）
    r2 = engine.chat("张哥", "上次那个还能便宜吗？")
    print(f"\n[记忆] {r2['reply']}")
    # 测试3: 下单
    r3 = engine.chat("李姐", "iPhone 13 128G 我要了，帮我下单")
    print(f"\n[下单] {r3['reply']}")
    print(f"  order_created={r3['order_created']}, model={r3['order_model']}")
