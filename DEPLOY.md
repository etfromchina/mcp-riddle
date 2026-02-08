# MCP 猜谜游戏服务 - 部署指南

## 项目结构

```
mcp-riddle/
├── server_sse.py      # 主服务代码
├── requirements.txt   # Python 依赖
├── Dockerfile         # Docker 构建文件
├── riddles.json       # 谜语库
└── DEPLOY.md          # 部署文档（本文件）
```

## 快速部署

### 方式一：Docker CLI

```bash
# 1. 进入项目目录
cd mcp-riddle

# 2. 构建镜像
docker build -t mcp-riddle .

# 3. 运行容器
docker run -d \
  --name mcp-riddle-server \
  -p 48080:8000 \
  --restart always \
  mcp-riddle

# 4. 查看日志
docker logs -f mcp-riddle-server
```

### 方式二：1Panel

1. 在 1Panel「容器」界面点击「创建」
2. 填写配置：
   - 镜像：`mcp-riddle`（或自定义标签）
   - 端口映射：`48080 -> 8000`
   - 重启策略：`always`
3. 点击「创建」

## 验证部署

```bash
# 健康检查
curl http://localhost:48080/health

# 预期返回：
# {"status":"healthy","riddles_count":12,"server":"mcp-riddle-game"}
```

## AI Agent 接入配置

### Dify / FastGPT 配置

```json
{
  "server_url": "http://<服务器IP>:48080/sse",
  "timeout": 60,
  "enable_db": false
}
```

### Claude Desktop 配置 (Windows)

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "riddle-game": {
      "command": "cmd",
      "args": ["/c", "python", "C:\\path\\to\\mcp-riddle\\server_sse.py"],
      "env": {}
    }
  }
}
```

### Claude Desktop 配置 (Linux/macOS)

```json
{
  "mcpServers": {
    "riddle-game": {
      "command": "python3",
      "args": ["/path/to/mcp-riddle/server_sse.py"],
      "env": {}
    }
  }
}
```

## 可用工具

| 工具名称 | 功能 | 参数 |
|---------|------|------|
| `get_riddle_random` | 获取谜语 | `mode`: random/sequential/category, `category`: 分类名 |
| `get_riddle_answer` | 验证答案 | `question`: 题目, `answer`: 你的答案 |
| `list_categories` | 查看分类 | 无 |
| `get_riddle_count` | 统计信息 | 无 |

## 常见问题

### 1. 连接拒绝

- 检查防火墙：`48080` 端口是否放行
- 检查云服务器安全组

### 2. 获取不到谜语

- 检查 `riddles.json` 是否存在且格式正确
- 查看容器日志：`docker logs mcp-riddle-server`

### 3. 提示绑定了 127.0.0.1

- 确保使用的是 `server_sse.py` 中的手动构建模式
- 不要使用 `FastMCP.run()` 自动启动

## 添加更多谜语

编辑 `riddles.json` 文件，添加新谜语：

```json
{
  "id": 13,
  "category": "你的分类",
  "question": "你的谜面",
  "answer": "谜底"
}
```

然后重新构建镜像：

```bash
docker build -t mcp-riddle . && docker restart mcp-riddle-server
```
