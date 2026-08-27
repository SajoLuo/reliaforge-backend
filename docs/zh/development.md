# 开发

[English](../development.md)

## 环境

使用 Python 3.11 或更高版本和虚拟环境，只从公开 Python 软件包索引安装依赖：

```bash
python -m pip install -e ".[dev]"
```

配置使用 `RELIAFORGE_` 前缀。`.env.example` 记录安全的本地默认值。运行时不要求数据库、
队列、对象存储或私有网络。

平台 `AppSettings` 可以读取不受 Git 跟踪的 `.env`。插件 `PluginSettings` 类只从进程
环境读取规范的 `RELIAFORGE_<PLUGIN_ID>_` 值，不会单独解析这个共享文件。请在 Shell 或
部署环境中导出插件覆盖值。

`RELIAFORGE_CORS_ORIGINS` 是精确 HTTP Origin 的 JSON 列表。示例允许本地前端
`http://127.0.0.1:5530`。默认列表为空；通配符来源会被拒绝；浏览器凭据或代理认证请求头
不会通过 CORS 开放。带 `Origin` 请求头的开发管理请求必须来自后端自身来源或这个配置
列表，避免无关网站向本机回环地址发起写入。

代理认证还要求 `RELIAFORGE_PROXY_TRUSTED_NETWORKS`，其值是直连对端 CIDR 范围的 JSON
列表。ReliaForge 校验 Socket 对端地址，绝不会把转发地址请求头用于这个边界。共享密钥
应保存在部署 Secret Storage 中，并至少包含 32 个字符。`reliaforge` 命令会关闭 Uvicorn
代理请求头解析；如果直接启动 Uvicorn，请使用
`uvicorn reliaforge.app:create_app --factory --no-proxy-headers` 保持该边界。`0.0.0.0/0` 和
`::/0` 等全地址网络会被拒绝，因为它们会移除独立的直连对端信任因子。

交互式 API 文档和 OpenAPI 文档在 development/test 环境可用。生产环境关闭这两个端点，
以保持最小管理面。

`RELIAFORGE_PLUGIN_OPERATION_TIMEOUT_SECONDS` 是一次生命周期请求的端到端截止时间，包含
排队等待其他生命周期操作的时间。Restart 会在 stop、initialize、start 和超时清理之间
共享同一预算，而不是每个阶段重新获得完整时间。Shutdown 同样把操作锁等待计入总预算，
且不会绕过锁去修改正在执行的插件。

## 质量门禁

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

任何非零结果都表示失败。Coverage 强制至少 85% 的分支感知源码覆盖率，pytest 把 Warning
视为 Error，mypy 以 Strict 模式检查运行时、测试和卫生扫描脚本。GitHub Actions 会在
Python 3.11 和 3.13 上执行相同序列。不可用的命令不能标记为通过。
`audit-requirements.txt` 是本地生成文件，不能提交。

## HTTP 冒烟验证

启动 `reliaforge`，然后验证真实数据路径：

```bash
curl --fail http://127.0.0.1:8000/api/v1/status
curl --fail http://127.0.0.1:8000/api/v1/live
curl --fail http://127.0.0.1:8000/api/v1/ready
curl --fail http://127.0.0.1:8000/api/v1/plugins/demo/greeting
curl --fail http://127.0.0.1:8000/api/v1/plugins/runbook/preview
```

正常停止进程，确保插件关闭生命周期得到执行。
