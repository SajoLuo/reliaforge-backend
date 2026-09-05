# 插件开发

[English](../plugin-development.md)

这篇教程会给一个 Python 函数提供 API，用它查询某个服务由哪个团队负责。你会生成插件、
放入函数、添加 HTTP 接口，再测试插件运行和停止时的返回结果。

请在后端仓库目录中操作，并先激活 Python 环境。尚未安装后端时，先按
[快速开始](../../README_CN.md#快速开始)完成安装。

## 1. 生成插件

如果当前目录中已有后端正在运行，先用 Ctrl+C 停止，再执行：

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
```

如果已经在快速开始中生成了 `sample_tool`，直接使用那个目录；命令不会覆盖已有文件。
下面的文件路径都相对于 `local-plugins/sample_tool/`。

## 2. 放入你的函数

新建 `ownership.py`，内容如下：

```python
"""Example service ownership records for the plugin tutorial."""

OWNERS = {
    "payments": "payments-ops",
    "search": "search-ops",
}


def find_owner(service_name: str) -> str | None:
    return OWNERS.get(service_name)
```

这里的两条记录是示例数据。函数接收服务名称，返回负责团队；查不到时返回 `None`。
把工具本身的代码放在这样的模块里，它就可以继续脱离 FastAPI 单独使用。

## 3. 给函数增加 API

用下面的内容替换 `router.py`。它保留模板原有的 `/message`，新增 `/owner` 接口。
新接口读取 `service_name` 参数，调用 `find_owner`，然后返回 JSON 对象。

```python
"""Thin HTTP routes for Sample Tool."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from reliaforge.plugins.contract import PluginState

from .models import Message
from .ownership import find_owner
from .service import MessageUnavailableError

if TYPE_CHECKING:
    from .plugin import Plugin


class ServiceOwner(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: str
    team: str


def create_router(plugin: Plugin) -> APIRouter:
    router = APIRouter(tags=["sample_tool"])

    @router.get("/message", response_model=Message)
    async def message() -> Message:
        try:
            return plugin.get_message()
        except MessageUnavailableError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Plugin is not running",
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            plugin.logger.error("generated plugin request failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc

    @router.get("/owner", response_model=ServiceOwner)
    async def owner(
        service_name: Annotated[str, Query(min_length=1, max_length=64)],
    ) -> ServiceOwner:
        if plugin.state is not PluginState.RUNNING:
            raise HTTPException(status_code=503, detail="Plugin is not running")
        team = find_owner(service_name)
        if team is None:
            raise HTTPException(status_code=404, detail="Service not found")
        return ServiceOwner(service=service_name, team=team)

    return router
```

接口只在插件运行时允许查询。停止插件后，状态检查会返回 `503`；查不到服务时返回 `404`。
FastAPI 负责检查必填参数，并根据 `ServiceOwner` 说明返回结果的格式。

本例只查询内存中的字典。接入需要等待网络或数据库的函数时，请使用异步 I/O，或使用设置了
并发上限和超时的工作线程，具体要求见[启停与健康检查](#启停与健康检查)。

## 4. 加载并调用接口

在后端目录中启动进程，把插件的父目录传给后端：

```bash
RELIAFORGE_PLUGIN_PATHS=./local-plugins reliaforge
```

PowerShell 使用：

```powershell
$env:RELIAFORGE_PLUGIN_PATHS = "./local-plugins"
reliaforge
```

另开一个终端，调用接口：

```bash
curl "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=payments"
```

预期返回：

```json
{"service": "payments", "team": "payments-ops"}
```

本地开发时，可以在 `http://127.0.0.1:8000/api/v1/docs` 浏览和试用新接口。
控制台的插件列表应显示 `sample_tool` 正在运行。

再检查查不到服务、参数缺失和停止后的情况：

```bash
curl -i "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=unknown"
curl -i "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner"
curl -X POST http://127.0.0.1:8000/api/v1/plugins/sample_tool/stop
curl -i "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=payments"
curl -X POST http://127.0.0.1:8000/api/v1/plugins/sample_tool/start
curl "http://127.0.0.1:8000/api/v1/plugins/sample_tool/owner?service_name=payments"
```

查询不存在的服务时返回 `404`，缺少参数时返回 `422`。停止请求返回插件的 `stopped` 状态，
之后查询会返回 `503`。重新启动后返回 `running`，最后一次查询应返回 `200` 和之前相同的团队。

进入插件目录，运行模板自带的启停测试：

```bash
python -m pytest tests/test_plugin.py
```

## 5. 把插件和用法交给团队

把 `sample_tool` 目录和需要安装的 Python 依赖交给部署维护者。维护者安装依赖，把插件的
父目录加入 `RELIAFORGE_PLUGIN_PATHS`，再重启后端。以后修改代码也要重启后端；控制台中的
插件重启按钮会继续使用已经加载的代码。

在插件 README 中写清接口 URL、必填的 `service_name` 参数、返回字段，以及上面的 `404`、
`422` 和 `503` 分别代表什么。生产环境的使用者需要先通过部署代理完成身份验证，才能调用 API。
部署维护者可以参考[生产认证配置](development.md#配置生产认证)。

后面的章节说明继续开发插件时会用到的字段和运行规则。

## Manifest

Manifest 说明平台应该加载什么。支持的字段包括：

- `id`、`name`、`version`、`description` 和 `api_version`；
- `entrypoint`，使用相对于插件目录的 `module:Class` 形式；
- `dependencies`，包含插件 `id` 和可接受的 SemVer `version` 范围；
- `capabilities`，提供给其他插件调用的共享 Python 服务名称，使用唯一的点分名称；
- 可选的 `frontend.category`，用于在控制台中对插件分组。

插件 ID 使用小写蛇形命名。`api_version` 设为 `"v1"`。依赖示例如下：

```json
{
  "dependencies": [
    { "id": "metrics_provider", "version": "^1.2.0" }
  ]
}
```

导入插件代码之前，ReliaForge 会检查全部 Manifest。依赖缺失、版本不匹配、循环依赖、重复 ID
或重复能力名称都会让后端在导入任何插件代码前停止启动。

## 启停与健康检查

后端发现并检查插件后，先调用 `_on_initialize()`，再调用 `_on_start()`。查看运行中插件的
健康状态时，会读取 `_on_health_check()`；释放资源时会调用 `_on_stop()`。运行期间可能
多次读取健康状态。

启动和停止方法是异步的，必须响应取消。访问网络和数据库时优先使用异步客户端；同步 I/O
放到工作线程中执行，限制同时运行的调用数，并为 I/O 本身设置超时。取消等待的协程不会
终止已经运行的线程。

健康检查只报告内存中已有的信息，应当快速、同步地返回。不要在 `_on_health_check()` 中访问
网络、数据库、文件系统或执行命令。

初始化时需要注册 `capabilities` 中列出的每项服务。不向其他插件共享 Python 对象时，可以
使用空列表。提供 HTTP 接口不需要额外声明 capability。

初始化失败或被取消后，管理器会在本次操作剩余的时间内调用 `_on_stop()`。这个钩子必须能处理
只创建了一部分资源的情况：先检查客户端或任务是否存在，再释放它，并用 `finally` 确保本地
清理逻辑执行。尝试停止后，平台会移除服务注册和事件订阅。超时机制无法强制不响应取消的
Python 代码释放资源。

测试中直接调用 `BasePlugin.initialize()` 时，即使返回 `False`，也要在 `finally` 中调用
`stop()`。停止之前，上下文会保留，以便钩子释放初始化过程中已经创建的资源。

`context.publish(...)` 会把进程内事件发送给当前订阅者。处理器并发运行并有超时限制，单个
处理器失败不会让发布者失败。事件不会持久化，因此不能用作任务队列。

## 路由与共享服务

ReliaForge 把每个路由挂载到 `/api/v1/plugins/{plugin_id}` 下。业务逻辑放在服务中，HTTP
校验放在路由中。根路径下的 `/start`、`/stop` 和 `/restart` 保留给插件启停操作。

跨域开发请求支持 `GET` 和 `POST`。插件路由需要其他 HTTP Method 时，请把前端和后端部署在
同一个来源下，即协议、主机和端口都相同。

使用其他插件共享的 Python 服务时，先把提供者写进 `dependencies`，再定义需要的接口，按
名称从上下文获取服务。未声明提供者依赖时，平台会拒绝这次获取：

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class GreetingCapability(Protocol):
    def message(self) -> str: ...


greeting = context.get_service("demo.greeting", GreetingCapability)
```

## 加载并调用服务

将 `RELIAFORGE_PLUGIN_PATHS` 指向包含生成插件的父目录，然后重启后端。默认模板提供
`GET /api/v1/plugins/sample_tool/message`，请求成功时会返回示例服务定义的消息。

请为插件使用者写一份 README，列出接口、参数、返回结果、配置和认证要求。控制台会列出已
加载的插件，并管理它的启停。修改代码或 Manifest 后需要重启后端；控制台中的插件重启操作
会继续使用已加载的代码。

## 配置

在 `PluginSettings` 子类中声明配置项：

```python
from pydantic import Field
from reliaforge.plugins.settings import PluginSettings


class SampleSettings(PluginSettings):
    message: str = Field(default="Ready", min_length=1, max_length=200)


class Plugin(BasePlugin):
    settings_class = SampleSettings

    async def _on_initialize(self) -> None:
        settings = self.context.get_settings(SampleSettings)
```

环境变量使用 `RELIAFORGE_<PLUGIN_ID>_` 前缀，用 `__` 表示嵌套字段。重启插件时会重新读取
配置。密钥请使用 `SecretStr`，并通过进程环境或部署密钥存储注入。不要把密钥写入默认值、
日志、Schema 或错误信息。

插件路由和启停操作需要管理认证，插件列表和状态读取保持公开。后端会在每个插件响应中返回
`available_actions`；客户端展示该列表，后端仍会认证和检查每项操作请求。

内置的 `demo` 和 `runbook` 插件展示了提供者与消费者如何使用带类型的共享服务。
