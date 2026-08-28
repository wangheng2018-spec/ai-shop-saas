# ai-shop-saas · AI 客服 SaaS
FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制代码
COPY . .

# 端口
EXPOSE 5000

# 启动
CMD ["python", "app.py"]
