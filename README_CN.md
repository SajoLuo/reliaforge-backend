# ReliaForge 后端

[English](README.md)

ReliaForge 后端用一个 FastAPI 服务运行多个 Python 运维插件。它读取插件信息、检查依赖、
按顺序启动插件、报告健康状态，并提供经过认证的启动、停止和重启操作。

本仓库包含后端、两个安全示例插件，以及生成新插件的命令。可选的 Web 控制台位于
[`reliaforge-frontend`](https://github.com/SajoLuo/reliaforge-frontend)。可以查看
[项目文档](https://reliaforge.dev/zh/)，也可以打开[只读在线演示](https://demo.reliaforge.dev/#/zh/)。

## 快速开始

需要 Python 3.11 或更高版本。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
reliaforge
```

Windows PowerShell 请使用 `.venv\Scripts\Activate.ps1` 激活环境。服务器默认监听
`127.0.0.1:8000`。

检查后端和内置插件：

```bash
curl http://127.0.0.1:8000/api/v1/status
curl http://127.0.0.1:8000/api/v1/plugins
curl http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

需要覆盖本地配置时，把 `.env.example` 复制为不受 Git 跟踪的 `.env`。示例已经允许前端开发
地址 `http://127.0.0.1:5530`。

## 创建插件

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
RELIAFORGE_PLUGIN_PATHS=./local-plugins reliaforge
```

生成的插件包含说明文件、配置、启停钩子、服务、API 路由和测试。接下来请阅读
[插件开发指南](docs/zh/plugin-development.md)。

## 主要 API

- `GET /api/v1/status` — 后端和插件摘要
- `GET /api/v1/live` — 进程存活状态
- `GET /api/v1/ready` — 启动就绪状态
- `GET /api/v1/plugins` — 插件列表
- `GET /api/v1/plugins/{plugin_id}` — 插件详情
- `POST /api/v1/plugins/{plugin_id}/start`
- `POST /api/v1/plugins/{plugin_id}/stop`
- `POST /api/v1/plugins/{plugin_id}/restart`

状态和插件列表接口只读。插件路由和启停操作使用管理认证。本地开发只有绑定回环地址时才能允许
匿名管理；生产环境使用可信反向代理、操作者身份请求头、共享密钥和可信对端网络。配置方法见
[开发](docs/zh/development.md)，状态和故障行为见[架构](docs/zh/architecture.md)。

## 验证

```bash
uv sync --all-extras --frozen --default-index https://pypi.org/simple
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run python -m compileall -q reliaforge scripts
uv run coverage erase
uv run coverage run -m pytest
uv run coverage report
uv build
uv run twine check dist/*
uv export --quiet --all-extras --frozen --no-emit-project --no-hashes --output-file audit-requirements.txt
uv run pip-audit --strict --requirement audit-requirements.txt
uv run python scripts/check_open_source_hygiene.py .
```

ReliaForge 采用 [MIT License](LICENSE)。
