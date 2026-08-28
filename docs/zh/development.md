# 开发

[English](../development.md)

## 准备环境

使用 Python 3.11 或更高版本，并创建虚拟环境：

```bash
python -m pip install -e ".[dev]"
```

ReliaForge 使用带 `RELIAFORGE_` 前缀的环境变量。`.env.example` 包含安全的本地默认值。后端
不需要数据库、队列、对象存储或私有网络。

应用可以读取不受 Git 跟踪的 `.env`。插件配置从进程环境读取
`RELIAFORGE_<PLUGIN_ID>_` 变量。请在 Shell 或部署环境中导出插件专用配置。

## 配置浏览器访问

`RELIAFORGE_CORS_ORIGINS` 是准确 HTTP 来源的 JSON 列表。`.env.example` 已允许本地前端
`http://127.0.0.1:5530`。空列表会关闭跨域访问，通配符来源会被拒绝。带 `Origin` 请求头的
浏览器管理请求必须来自后端来源或该列表。

## 配置生产认证

`RELIAFORGE_PROXY_TRUSTED_NETWORKS` 是代理直连 CIDR 范围的 JSON 列表。ReliaForge 检查
Socket 对端地址，不使用转发地址请求头。共享密钥应保存在部署密钥存储中，并至少包含 32 个
字符。可信网络不能是 `0.0.0.0/0` 或 `::/0`。

打包的 `reliaforge` 命令会关闭 Uvicorn 代理请求头解析。直接启动 Uvicorn 时请使用：

```bash
uvicorn reliaforge.app:create_app --factory --no-proxy-headers
```

生产环境会关闭交互式 API 文档和 OpenAPI 文档。

## 设置启停超时

`RELIAFORGE_PLUGIN_OPERATION_TIMEOUT_SECONDS` 为一次启动、停止或重启设置总时间限制，其中也
包括排队等待其他操作的时间。重启过程中的停止、初始化、启动和清理共享这一个时间限制。

## 运行质量检查

在仓库根目录运行全部命令：

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

任何非零结果都表示失败。测试要求至少 85% 的分支感知源码覆盖率，把 Python Warning 视为
错误，并运行严格的 mypy 检查。`audit-requirements.txt` 是本地生成文件，不能提交。

## 检查运行中的后端

启动 `reliaforge`，再调用真实 HTTP 接口：

```bash
curl --fail http://127.0.0.1:8000/api/v1/status
curl --fail http://127.0.0.1:8000/api/v1/live
curl --fail http://127.0.0.1:8000/api/v1/ready
curl --fail http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl --fail http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

正常停止进程，确保插件清理也会执行。
