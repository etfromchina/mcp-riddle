# MCP Riddle Game 开发日志

**开发日期**: 2026-02-03  
**开发者**: OpenClaw AI Assistant  
**项目位置**: `/root/.openclaw/workspace/mcp-riddle/`  
**服务器**: `http://185.201.226.133:8000`

---

## 📋 目录

1. [项目概述](#项目概述)
2. [开发时间线](#开发时间线)
3. [遇到的问题与解决方案](#遇到的问题与解决方案)
4. [最终代码结构](#最终代码结构)
5. [测试结果](#测试结果)
6. [部署配置](#部署配置)
7. [使用方法](#使用方法)

---

## 项目概述

基于 Model Context Protocol (MCP) 的猜谜游戏服务器，提供 4 个工具：
- `get_riddle_random` - 随机获取谜语
- `get_riddle_answer` - 验证谜底答案
- `list_categories` - 获取分类列表
- `get_riddle_count` - 获取谜语统计

---

## 开发时间线

### 2026-02-03 14:00-14:08 (UTC)

| 时间 | 操作 | 结果 |
|------|------|------|
| 14:00 | 原始代码检查 | 发现多个问题 |
| 14:02 | 修复 `/messages` 端点 | HTTP POST 模式工作 |
| 14:04 | 首次 SSE 测试 | 连接被关闭 |
| 14:06 | 移除 mcp SDK | 直接实现 JSON-RPC |
| 14:07 | SSE session 管理 | 实现 Queue 机制 |
| 14:08 | 跨服务器测试 | ✅ 全部通过 |

---

## 遇到的问题与解决方案

### 问题 1: `/messages` 端点只返回 `{"status":"ok"}`

**症状**: HTTP POST 请求返回 200，但响应内容只有 `{"status":"ok"}`

**原因**: 原始代码没有真正处理 MCP 协议消息

**解决方案**: 
```python
async def messages_endpoint(request):
    body = await request.body()
    message = json.loads(body.decode())
    
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params", {})
    
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mcp-riddle-game", "version": "1.0.0"}
            }
        })
    # ... 处理其他方法
```

---

### 问题 2: SSE 模式连接被关闭

**症状**: 使用 MCP SDK 的 `sse_client` 连接时返回 "Connection closed"

**原因**: 
1. 旧版 SSE 实现没有正确管理 session
2. MCP SDK 的 API (1.0+) 发生了变化

**解决方案**: 
1. 移除了 `mcp>=1.0.0` 依赖
2. 直接实现 MCP JSON-RPC 协议
3. 使用自研的 Session 管理器

```python
class SessionManager:
    def __init__(self):
        self.sessions = {}
    
    def create_session(self, queue: Queue):
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = queue
        return session_id
    
    async def send_to_session(self, session_id: str, message: Dict):
        queue = self.get_session(session_id)
        if queue:
            await queue.put(message)
```

---

### 问题 3: 外部服务器连接超时

**症状**: 从 149.28.193.160 连接 185.201.226.133:8000 超时

**原因**: 
1. `/sse` 端点实现不正确
2. 没有正确返回 session ID

**解决方案**: 
1. 重写 `/sse` 端点，初始化时返回 session ID
2. `/messages` 端点接收 `session_id` 查询参数
3. 通过 Queue 在 session 中路由消息

```python
async def sse_endpoint(request):
    queue = Queue()
    session_id = session_manager.create_session(queue)
    
    async def event_generator():
        yield {"event": "message", "data": json.dumps({"type": "session", "sessionId": session_id})}
        # ... 等待并发送消息
    
    return EventSourceResponse(event_generator())
```

---

### 问题 4: 容器健康检查显示 0 道谜语

**症状**: `{"status":"healthy","riddles_count":0}`

**原因**: Dockerfile 设置了 `ENV RIDDLES_JSON="[]"` 默认值

**解决方案**: 
```dockerfile
# 移除了默认 ENV RIDDLES_JSON="[]"
# 现在从 riddles.json 文件加载
```

---

## 最终代码结构

```
mcp-riddle/
├── server_sse.py      # 主服务器代码 (10.6KB)
├── Dockerfile         # Docker 构建文件
├── requirements.txt   # Python 依赖
├── riddles.json       # 谜语数据 (12 道谜语)
├── DEPLOY.md         # 部署文档
└── CHANGELOG.md      # 本文档
```

### 核心组件

| 文件 | 描述 |
|------|------|
| `server_sse.py` | Starlette 应用 + MCP 协议实现 |
| `Dockerfile` | Python 3.11-slim 基础镜像 |
| `requirements.txt` | starlette, uvicorn, sse-starlette, httpx, anyio |

---

## 测试结果

### 本地测试 (ASC-db → localhost:8000)

```
✅ initialize: mcp-riddle-game v1.0.0
✅ tools/list: 4 个工具
✅ get_riddle_random: 返回谜语
✅ get_riddle_answer: 验证正确
✅ list_categories: 2 个分类
✅ get_riddle_count: 12 道谜语
```

### 跨服务器测试 (149.28.193.160 → 185.201.226.133:8000)

```
✅ HTTP POST 模式: 全部通过
✅ SSE 模式: 全部通过
   - Session 建立成功
   - 消息路由正常
   - 响应正确返回
```

---

## 部署配置

### Docker

```bash
cd /root/.openclaw/workspace/mcp-riddle
docker build -t mcp-riddle:latest .
docker run -d -p 8000:8000 --name mcp-riddle-server mcp-riddle:latest
```

### 健康检查

```bash
curl http://185.201.226.133:8000/health
# 返回: {"status":"healthy","riddles_count":12,"server":"mcp-riddle-game"}
```

---

## 使用方法

### AI 客户端配置 (SSE 模式)

```json
{
  "mcpServers": {
    "riddle-game": {
      "url": "http://185.201.226.133:8000/sse",
      "transport": "sse"
    }
  }
}
```

### AI 客户端配置 (HTTP 模式)

```json
{
  "mcpServers": {
    "riddle-game": {
      "url": "http://185.201.226.133:8000/messages",
      "transport": "http"
    }
  }
}
```

### 手动测试

```bash
# HTTP POST 模式
curl -X POST http://185.201.226.133:8000/messages \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}}}'
```

---

## 总结

✅ **成功实现了符合 MCP 协议的猜谜游戏服务器**

- 直接实现 JSON-RPC 2.0 协议
- 支持 HTTP POST 和 SSE 两种传输模式
- 完整的工具定义和处理函数
- 跨服务器测试通过
- 容器化部署

---

*文档生成时间: 2026-02-03 14:30 UTC*
