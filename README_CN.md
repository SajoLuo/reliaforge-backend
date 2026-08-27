# ReliaForge 后端

[English](README.md)

ReliaForge 是一个轻量级平台，用于将运维工具组织成相互隔离、具备生命周期管理的
Python 插件。本仓库包含公开的后端运行时、两个中立示例插件和一个插件脚手架；不附带
监控存储、告警套件或任何组织专属集成。

可选的 React 管理界面位于
[`reliaforge-frontend`](https://github.com/SajoLuo/reliaforge-frontend)。
跨仓库指南请访问 [ReliaForge 项目站点](https://sajoluo.github.io/reliaforge/zh/)，也可以在
不运行后端的情况下体验[只读在线 Demo](https://sajoluo.github.io/reliaforge-frontend/#/zh/)。

## 包含内容

- 类型化的插件清单与 API 模型。
- SemVer 依赖校验和确定性的启动顺序。
- 相互独立的生命周期状态与无副作用健康快照。
- 由提供方拥有的服务容器，以及带截止时间、故障隔离的内存事件总线。
- 以 Python Settings 类作为插件字段和公开 JSON Schema 的唯一来源。
- 只读目录与健康 API，以及需要授权的插件路由和生命周期操作。
- 中立示例接口：`GET /api/v1/plugins/demo/greeting`。
- 只读跨插件 Runbook 预览：`GET /api/v1/plugins/runbook/preview`。
- 可复制的插件脚手架和确定性的仓库开源卫生检查。

## 快速开始

需要 Python 3.11 或更高版本。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
reliaforge
```

Windows PowerShell 请使用 `.venv\Scripts\Activate.ps1` 激活环境。开发命令默认绑定
`127.0.0.1`。打开 `http://127.0.0.1:8000/api/v1/status`，然后请求：

```bash
curl http://127.0.0.1:8000/api/v1/plugins
curl http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

仅在需要本地覆盖配置时，把 `.env.example` 复制为不受 Git 跟踪的 `.env`，绝不能提交
生成的文件。示例明确允许公开前端的开发源 `http://127.0.0.1:5530`；空的
`RELIAFORGE_CORS_ORIGINS` 列表不会产生跨域响应头，通配符来源会被拒绝。

## 创建插件

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
RELIAFORGE_PLUGIN_PATHS=./local-plugins reliaforge
```

脚手架与 Demo 使用相同的清单和生命周期契约。具体契约见
[`docs/zh/plugin-development.md`](docs/zh/plugin-development.md)，验证命令见
[`docs/zh/development.md`](docs/zh/development.md)。

## API 契约

- `GET /api/v1/status`
- `GET /api/v1/live`
- `GET /api/v1/ready`
- `GET /api/v1/plugins`
- `GET /api/v1/plugins/{plugin_id}`
- `POST /api/v1/plugins/{plugin_id}/start`
- `POST /api/v1/plugins/{plugin_id}/stop`
- `POST /api/v1/plugins/{plugin_id}/restart`

`/live` 表示进程存活；`/ready` 表示当前进程的关键启动流程是否完成；`/status` 为运维人员
和 UI 汇总插件状态。三者都只读取内存状态，不探测依赖，也不执行修复写入。Restart 会对
现有插件实例执行停止、重新初始化和启动，不会从磁盘重新加载代码。

目录读取是公开的。每条插件自有路由和每次生命周期写入都使用已配置的管理认证边界，
插件清单不能选择绕过认证。匿名管理模式只允许显式的 development/test 环境并要求绑定
回环地址。生产环境必须使用代理模式，提供身份请求头、强共享密钥以及至少一个可信直连
对端网络。只有来自已配置网络的请求才会接受身份请求头；无效的生产配置会阻止启动。
打包的 `reliaforge` 命令会关闭转发地址重写，使校验基于 TCP 直连对端；全地址可信网络也
会被拒绝。生产环境同时关闭交互式 API 文档和 OpenAPI 端点。开发环境中的浏览器管理
写入，只接受后端自身来源或 `RELIAFORGE_CORS_ORIGINS` 显式列出的来源。

每条目录/详情记录都包含 `available_actions`。后端根据已加载实例、生命周期状态、依赖
可用性和活动依赖方计算它。加载失败的记录以及受运行中依赖方保护的提供方都不暴露操作。
客户端应直接渲染该字段，不要复制生命周期策略；服务器仍会授权并重新校验每次请求。

插件字段只在 `PluginSettings` 子类中声明一次。管理器从
`RELIAFORGE_<PLUGIN_ID>_` 进程环境变量读取字段（嵌套字段使用 `__`），把一个经过校验的
实例注入插件上下文，并从该类生成目录 JSON Schema。Restart 会重新构造 Settings 实例。
插件 Settings 不会自行解析平台 `.env`，因此无关的应用或插件键不会污染校验。

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
