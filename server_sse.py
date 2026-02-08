#!/usr/bin/env python3
"""
MCP Riddle Game Server - HTTP/SSE 模式
符合 MCP 官方 SSE 传输规范
"""

import json
import logging
import random
import uuid
from threading import Lock
from pathlib import Path
from typing import Any, Dict, List, Optional
from asyncio import Queue

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
import uvicorn


# ============ 配置日志 ============
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)


# ============ 1. 加载谜语库 ============
def load_riddles() -> List[Dict]:
    import os
    riddles_json = os.environ.get("RIDDLES_JSON", "").strip()
    if riddles_json:
        try:
            riddles = json.loads(riddles_json)
            logger.info(f"✅ 从环境变量加载了 {len(riddles)} 道谜语")
            return riddles
        except json.JSONDecodeError as e:
            logger.error(f"❌ 环境变量 JSON 解析失败: {e}")

    riddles_path = Path(__file__).parent / "riddles.json"
    try:
        with open(riddles_path, "r", encoding="utf-8") as f:
            riddles = json.load(f)
        logger.info(f"✅ 从文件加载了 {len(riddles)} 道谜语")
        return riddles
    except Exception as e:
        logger.error(f"❌ 加载谜语失败: {e}")
        return []


# ============ 2. Session 管理 ============
class SessionManager:
    def __init__(self):
        self.sessions = {}
    
    def create_session(self, queue: Queue):
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = queue
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Queue]:
        return self.sessions.get(session_id)
    
    def remove_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    async def send_to_session(self, session_id: str, message: Dict):
        queue = self.get_session(session_id)
        if queue:
            await queue.put(message)


session_manager = SessionManager()
sequential_cursors: Dict[str, int] = {}
sequential_lock = Lock()


# ============ 3. 工具定义 ============
def get_tools() -> List[Dict]:
    return [
        {
            "name": "get_riddle_random",
            "description": "随机获取一道谜语。支持 random/sequential/category 模式。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["random", "sequential", "category"], "default": "random"},
                    "category": {"type": "string", "description": "分类名称"}
                },
                "required": ["mode"]
            }
        },
        {
            "name": "get_riddle_answer",
            "description": "验证谜底答案。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "谜面"},
                    "answer": {"type": "string", "description": "猜测的答案"}
                },
                "required": ["question"]
            }
        },
        {
            "name": "list_categories",
            "description": "获取所有谜语分类列表",
            "inputSchema": {"type": "object", "properties": {}}
        },
        {
            "name": "get_riddle_count",
            "description": "获取谜语统计",
            "inputSchema": {"type": "object", "properties": {}}
        }
    ]


# ============ 4. 工具处理函数 ============
def handle_get_riddle(args: Dict, riddles: List[Dict]) -> str:
    mode = args.get("mode", "random")
    category = args.get("category", None)
    filtered = riddles
    
    if mode == "category" and category:
        filtered = [r for r in riddles if r.get("category") == category]
        if not filtered:
            return f"❌ 未找到分类 '{category}' 的谜语"
    
    if not filtered:
        return "❌ 谜语库为空"

    if mode == "sequential":
        # Keep a stable cursor per list scope so sequential calls return deterministic order.
        scope_key = f"category:{category}" if category else "__all__"
        with sequential_lock:
            current = sequential_cursors.get(scope_key, 0)
            selected = filtered[current % len(filtered)]
            sequential_cursors[scope_key] = current + 1
    else:
        selected = random.choice(filtered)

    result = json.dumps(selected, ensure_ascii=False, indent=2)
    return f"✅ 获取谜语成功：\n{result}"


def handle_check_answer(args: Dict, riddles: List[Dict]) -> str:
    question = args.get("question", "").strip()
    user_answer = args.get("answer", "").strip()
    
    matched = None
    for riddle in riddles:
        if question in riddle.get("question", "") or riddle.get("question", "") in question:
            matched = riddle
            break
    
    if not matched:
        return "❌ 未找到匹配的谜语"
    
    correct = matched.get("answer", "").strip()
    is_correct = user_answer.lower().replace(" ", "") == correct.lower().replace(" ", "")
    
    if is_correct:
        return f"🎉 恭喜！答案正确！\n谜底是：{correct}\n分类：{matched.get('category', '未知')}"
    else:
        return f"❌ 答案不正确。提示：谜底是 {len(correct)} 个字"


def handle_list_categories(riddles: List[Dict]) -> str:
    categories = sorted(set(r.get("category", "未分类") for r in riddles))
    stats = {cat: sum(1 for r in riddles if r.get("category") == cat) for cat in categories}
    result = "📚 可用的谜语分类：\n\n" + "\n".join(f"• {cat}: {stats[cat]} 道" for cat in categories)
    result += f"\n\n总计: {len(riddles)} 道谜语"
    return result


def handle_get_count(riddles: List[Dict]) -> str:
    total = len(riddles)
    categories = {}
    for riddle in riddles:
        cat = riddle.get("category", "未分类")
        categories[cat] = categories.get(cat, 0) + 1
    result = f"📊 谜语库统计\n\n总计: {total} 道谜语\n\n"
    result += "\n".join(f"• {cat}: {count} 道" for cat, count in sorted(categories.items(), key=lambda x: -x[1]))
    return result


# ============ 5. MCP 消息处理 ============
def handle_mcp_message(message: Dict, riddles: List[Dict]) -> Dict:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mcp-riddle-game", "version": "1.0.0"}
            }
        }
    
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": get_tools()}
        }
    
    if method == "tools/call":
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})
        
        if tool_name == "get_riddle_random":
            text = handle_get_riddle(tool_args, riddles)
        elif tool_name == "get_riddle_answer":
            text = handle_check_answer(tool_args, riddles)
        elif tool_name == "list_categories":
            text = handle_list_categories(riddles)
        elif tool_name == "get_riddle_count":
            text = handle_get_count(riddles)
        else:
            text = f"❌ 未知工具: {tool_name}"
        
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": text}]}
        }
    
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}


# ============ 6. 加载数据 ============
riddles_data = load_riddles()


# ============ 7. Starlette 路由 ============
async def sse_endpoint(request):
    """SSE 端点 - GET 建连, POST 兼容消息调用"""
    if request.method == "POST":
        return await messages_endpoint(request)

    from asyncio import Queue
    from sse_starlette.sse import EventSourceResponse
    
    queue = Queue()
    session_id = session_manager.create_session(queue)
    
    async def event_generator():
        # 发送 session ID
        yield {"event": "message", "data": json.dumps({"type": "session", "sessionId": session_id})}
        
        try:
            while True:
                message = await queue.get()
                yield {"event": "message", "data": json.dumps(message)}
                if message.get("type") == "close":
                    break
        except Exception as e:
            logger.error(f"SSE Error: {e}")
        finally:
            session_manager.remove_session(session_id)
    
    return EventSourceResponse(event_generator())


def _extract_session_id(request, message: Dict) -> Optional[str]:
    # 兼容不同 MCP 客户端: query/header/body 的 session id 传递方式
    for key in ("session_id", "sessionId", "sid"):
        value = request.query_params.get(key)
        if value:
            return value.strip()

    for key in ("mcp-session-id", "x-mcp-session-id", "x-session-id"):
        value = request.headers.get(key)
        if value:
            return value.strip()

    for key in ("session_id", "sessionId", "sid"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    params = message.get("params")
    if isinstance(params, dict):
        for key in ("session_id", "sessionId", "sid"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        meta = params.get("_meta")
        if isinstance(meta, dict):
            for key in ("session_id", "sessionId", "sid"):
                value = meta.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

    return None


async def messages_endpoint(request):
    """处理 POST 消息 - 支持 SSE session"""
    try:
        body = await request.body()
        message = json.loads(body.decode())
        logger.info(f"收到消息: {message}")
        
        # 兼容多种 session id 传递方式
        session_id = _extract_session_id(request, message)
        
        # 处理消息
        response = handle_mcp_message(message, riddles_data)
        
        # 如果有 session_id，通过 SSE 发送响应
        if session_id:
            await session_manager.send_to_session(session_id, response)
            return JSONResponse({"status": "sent", "session_id": session_id})
        
        return JSONResponse(response)
    except Exception as e:
        logger.error(f"处理消息错误: {e}")
        return JSONResponse({"error": str(e)}, status_code=400)


async def health_check(request):
    return JSONResponse({
        "status": "healthy",
        "riddles_count": len(riddles_data),
        "server": "mcp-riddle-game"
    })


starlette_app = Starlette(routes=[
    Route("/sse", sse_endpoint, methods=["GET", "POST"]),
    Route("/mcp", sse_endpoint, methods=["GET", "POST"]),
    Route("/sse/messages", messages_endpoint, methods=["POST"]),
    Route("/messages", messages_endpoint, methods=["POST"]),
    Route("/health", health_check),
])

starlette_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 8. 启动服务 ============
if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║          MCP 猜谜游戏服务 - HTTP/SSE 模式          ║
    ║                                                           ║
    ║  SSE 端点: http://<IP>:8000/sse                      ║
    ║  HTTP 端点: http://<IP>:8000/messages               ║
    ║  健康检查: http://<IP>:8000/health                  ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    uvicorn.run(starlette_app, host="0.0.0.0", port=8000, log_level="info")
