# MCP Riddle Game Server

一个基于 Starlette 的 MCP 猜谜游戏服务，支持 `HTTP POST` 和 `SSE` 两种通信方式。

## 功能

- 提供 4 个 MCP 工具：
  - `get_riddle_random`：获取谜语（`random` / `sequential` / `category`）
  - `get_riddle_answer`：校验答案
  - `list_categories`：列出分类
  - `get_riddle_count`：谜语统计
- 支持从 `riddles.json` 加载数据
- 可通过环境变量 `RIDDLES_JSON` 覆盖谜语库

## 项目结构

```text
mcp-riddle/
├── server_sse.py
├── riddles.json
├── requirements.txt
├── Dockerfile
├── DEPLOY.md
└── README.md
```

## 本地运行

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server_sse.py
```

启动后默认监听 `0.0.0.0:8000`。

## 接口

- SSE: `GET /sse`
- MCP 消息: `POST /messages`
- 健康检查: `GET /health`

### 健康检查示例

```bash
curl http://127.0.0.1:8000/health
```

### HTTP 模式调用示例

```bash
curl -X POST http://127.0.0.1:8000/messages \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

```bash
curl -X POST http://127.0.0.1:8000/messages \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_riddle_random","arguments":{"mode":"sequential"}}}'
```

## Docker

```bash
docker build -t mcp-riddle .
docker run -d --name mcp-riddle-server -p 48080:8000 --restart always mcp-riddle
curl http://127.0.0.1:48080/health
```

## AI Agent 接入

### SSE 方式

```json
{
  "mcpServers": {
    "riddle-game": {
      "url": "http://<server-ip>:48080/sse",
      "transport": "sse"
    }
  }
}
```

### HTTP 方式

```json
{
  "mcpServers": {
    "riddle-game": {
      "url": "http://<server-ip>:48080/messages",
      "transport": "http"
    }
  }
}
```

