FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码（包括 riddles.json）
COPY server_sse.py .
COPY riddles.json .

# 谜语数据通过环境变量传入，未设置时使用文件
# ENV RIDDLES_JSON='[{"id":1,"category":"测试","question":"测试题","answer":"测试"}]'

# 暴露端口
EXPOSE 8000

# 启动服务
CMD ["python", "server_sse.py"]
