# Skill 制造工厂 —— 后端系统

> 基于 [skill-creator](https://skillsmp.com/skills/openclaw-openclaw-skills-skill-creator-skill-md) 内核的 OpenClaw Skill 制造工厂后端。

## 项目概述

本系统是一个以"Skill 制造"为核心的后端服务。与普通对话系统不同，它是一条完整的 **Skill 制造流水线**：

```
中文需求输入
  → AI 多轮引导补全
  → 需求结构化沉淀
  → skill-creator 内核执行创建（生成 SKILL.md + scripts/）
  → 工作区文件管理
  → Docker 沙盒测试验证 Skill 实际效果
  → 测试结果反馈迭代
```

### 核心定位

- **AI 模型**：需求理解与编排助手，负责多轮对话、引导补全、结构化转译
- **skill-creator**：Skill 创建执行内核（真实 Skill，非抽象概念），位于 `backend/kernels/skill-creator/`
- **本系统**：将两者连接，实现完整的 Skill 制造闭环

---

## 技术栈

| 组件 | 技术 |
|------|------|
| Web 框架 | Flask + Flask-SQLAlchemy |
| 数据库 | PostgreSQL（开发可用 SQLite） |
| 任务队列 | Celery + Redis |
| AI 接入 | OpenAI 兼容 API（支持本地 Ollama/vLLM 等） |
| 沙盒隔离 | Docker subprocess |
| 部署 | Docker Compose |

---

## 目录结构

```
skill-creator/
├── backend/
│   ├── kernels/
│   │   └── skill-creator/          ← skill-creator 内核（独立存放）
│   │       ├── SKILL.md
│   │       ├── scripts/
│   │       │   └── eval_description.py
│   │       └── kernel.json
│   ├── app/
│   │   ├── api/v1/                  ← API 蓝图
│   │   │   ├── config.py            ← 模型配置接口
│   │   │   ├── kernels.py           ← 内核管理接口
│   │   │   ├── sessions.py          ← 会话接口
│   │   │   ├── tasks.py             ← 任务管理接口
│   │   │   ├── files.py             ← 文件管理接口
│   │   │   └── tests.py             ← 沙盒测试接口
│   │   ├── kernel/                  ← 内核适配层（关键边界）
│   │   │   ├── base.py              ← KernelAdapter 抽象接口
│   │   │   ├── registry.py          ← KernelRegistry 注册表
│   │   │   └── skill_creator_impl.py ← 具体实现
│   │   ├── model/                   ← AI 模型接入层
│   │   │   ├── provider.py
│   │   │   └── encryption.py
│   │   ├── services/                ← 业务编排层
│   │   │   ├── session_service.py
│   │   │   ├── skill_creation_service.py
│   │   │   ├── file_service.py
│   │   │   └── sandbox_service.py
│   │   ├── tasks/                   ← Celery 异步任务
│   │   │   ├── skill_creation_task.py
│   │   │   └── sandbox_test_task.py
│   │   ├── models/                  ← 数据库模型
│   │   │   ├── model_config.py
│   │   │   ├── session.py
│   │   │   ├── skill_creation_task.py
│   │   │   ├── sandbox_test.py
│   │   │   └── task_event_log.py
│   │   ├── sandbox/                 ← 沙盒执行器
│   │   │   └── docker_runner.py
│   │   ├── workspace/               ← 用户 Skill 工作区（运行时）
│   │   └── sandboxes/               ← 沙盒测试区（运行时）
│   ├── scripts/
│   │   ├── download_kernel.py       ← 内核下载脚本
│   │   └── init_db.py               ← 数据库初始化脚本
│   ├── tests/
│   ├── wsgi.py
│   ├── requirements.txt
│   └── Dockerfile
├── docker/
│   └── sandbox/
│       └── Dockerfile.sandbox       ← 沙盒专用镜像
├── docker-compose.yml
└── .env.example
```

---

## 快速开始

### 1. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 设置数据库密码、加密密钥等
```

### 2. 构建沙盒镜像

```bash
docker build -f docker/sandbox/Dockerfile.sandbox -t skillfactory-sandbox:latest .
```

### 3. 启动所有服务

```bash
docker-compose up -d
```

### 4. 初始化数据库

```bash
docker-compose exec api flask db upgrade
# 或（首次开发环境快速启动）：
docker-compose exec api python scripts/init_db.py --no-migrate --seed
```

### 5. 验证服务正常

```bash
# 检查内核是否加载
curl http://localhost:5000/api/v1/kernels

# 查看 API 文档（开发环境）
curl http://localhost:5000/api/v1/kernels/skill-creator/guide
```

---

## API 接口概览

### 模型配置 `/api/v1/config/models`
```
GET    /models              # 列出所有模型配置
POST   /models              # 新增模型配置
PUT    /models/{id}         # 更新配置
DELETE /models/{id}         # 删除配置
POST   /models/{id}/activate # 激活配置
POST   /models/{id}/test    # 测试连通性
```

### 多轮会话 `/api/v1/sessions`
```
POST   /sessions            # 创建会话（含初始需求）
GET    /sessions/{id}       # 获取会话详情
POST   /sessions/{id}/messages  # 发送消息
POST   /sessions/{id}/confirm   # 确认需求触发创建
```

### 任务管理 `/api/v1/tasks`
```
GET    /tasks               # 列出任务
GET    /tasks/{id}          # 获取任务状态
GET    /tasks/{id}/logs     # 获取任务日志
POST   /tasks/{id}/retry    # 重试失败任务
```

### 文件管理 `/api/v1/tasks/{task_id}/files`
```
GET    /files               # 文件目录树
GET    /files/{path}        # 读取文件
PUT    /files/{path}        # 写入文件
DELETE /files/{path}        # 删除文件
POST   /files/rename        # 重命名文件
```

### 沙盒测试 `/api/v1/tasks/{task_id}/tests`
```
POST   /tests               # 触发测试
GET    /tests               # 测试历史
GET    /tests/{id}          # 测试结果详情
GET    /tests/{id}/logs     # 测试原始日志
```

---

## 典型使用流程

```bash
# 1. 添加模型配置
curl -X POST http://localhost:5000/api/v1/config/models \
  -H "Content-Type: application/json" \
  -d '{"name":"本地Qwen","provider":"local_openai_compat","model_name":"qwen2.5:7b","api_base_url":"http://host.docker.internal:11434/v1"}'

# 2. 激活模型
curl -X POST http://localhost:5000/api/v1/config/models/{id}/activate

# 3. 创建会话（开始需求采集）
curl -X POST http://localhost:5000/api/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"message": "我想创建一个帮助用户润色中文文章的 Skill"}'

# 4. 继续对话补全需求
curl -X POST http://localhost:5000/api/v1/sessions/{session_id}/messages \
  -H "Content-Type: application/json" \
  -d '{"message": "主要用于润色学术论文和商务邮件"}'

# 5. 确认需求并触发创建
curl -X POST http://localhost:5000/api/v1/sessions/{session_id}/confirm

# 6. 轮询任务状态
curl http://localhost:5000/api/v1/tasks/{task_id}

# 7. 查看生成的文件
curl http://localhost:5000/api/v1/tasks/{task_id}/files

# 8. 触发沙盒测试
curl -X POST http://localhost:5000/api/v1/tasks/{task_id}/tests

# 9. 查看测试结果
curl http://localhost:5000/api/v1/tasks/{task_id}/tests/{test_id}
```

---

## skill-creator 内核说明

内核位于 `backend/kernels/skill-creator/`，来源于：
- https://skillsmp.com/skills/openclaw-openclaw-skills-skill-creator-skill-md

**重要原则**：
- 内核目录**只读**，任何业务代码不得向此目录写入
- 外围代码只通过 `KernelAdapter` 接口访问内核，不直接读取内核文件
- 内核升级时只需替换目录并调用 `/api/v1/kernels/skill-creator/reload`

更新内核：
```bash
python backend/scripts/download_kernel.py --force
```

---

## 开发调试

```bash
# 运行测试
cd backend && pytest tests/ -v

# 查看 Celery 任务监控
open http://localhost:5555

# 查看数据库
docker-compose exec db psql -U skilluser -d skillfactory
```
