# 插件开发

[English](../plugin-development.md)

每个插件目录包含 `manifest.json`、`__init__.py`、入口点模块、Service、Model、Settings 和
一个薄 Router。使用 `reliaforge-scaffold` 创建初始文件。

## 清单

公开清单字段包括：

- `id`、`name`、`version`、`description` 和 `api_version`。
- `entrypoint`，采用相对插件目录的 `module:Class` 形式。
- `dependencies`，对象列表；每个对象包含插件 `id` 和允许的 SemVer `version` 范围。
- `capabilities`，唯一的点分公开服务名称列表。
- `frontend`，可选的通用目录分类元数据。

`settings_schema`、前端 `route`/`icon` 和服务注册版本刻意不属于清单字段。UI 根据
`/plugins/{plugin_id}` 生成路由，Settings Schema 来自 Python，而提供方插件的 SemVer
依赖是兼容性边界。

插件 ID 使用小写 snake case。ReliaForge 0.1 接受 `api_version: "v1"`。依赖使用新的
公开对象形式；旧的纯字符串依赖声明会被明确拒绝：

```json
{
  "dependencies": [
    { "id": "metrics_provider", "version": "^1.2.0" }
  ]
}
```

依赖解析是确定性的，并会拒绝插件缺失、版本不兼容或依赖环。在导入任何入口点之前，
系统会先校验完整清单集合。

## 生命周期

管理器驱动以下顺序：

```text
discover -> validate -> initialize -> start -> health -> stop
```

Initialize 通过 `PluginContext` 注册本地服务；start 使服务可用；stop 释放资源。生命周期
Hook 是异步的，必须遵守取消语义。生命周期状态使用 `running`；运行质量下降只通过
`HealthStatus.DEGRADED` 表示。同步 I/O 必须移到有界执行域，并设置显式超时。Health 是
同步、无副作用的快照。

`context.publish(...)` 返回 `EventDeliveryReport`。订阅者在平台处理器超时内并发执行。
一个订阅者的异常或超时会以稳定的 `handler_error` 或 `handler_timeout` 原因记录，不会让
发布者失败；发布者自身取消仍会向上传播。事件投递只在进程内发生且不持久；每份报告只
描述对应的 publish 调用，因此不能把事件总线当作工作流队列。无论 stop 成功还是失败，
上下文拥有的订阅和服务都会被移除。

通过 `context.register_service(...)` 注册的每项服务都必须出现在提供方清单的
capabilities 中。声明的能力没有注册，或者两个清单声明同一能力时，初始化也会失败。

## 路由与服务

平台把插件 Router 挂载在 `/api/v1/plugins/{plugin_id}`。Router 只负责校验和 HTTP 错误
转换；领域行为留在不导入 FastAPI 的 Service 中。平台保留根相对的 `/start`、`/stop`
和 `/restart` 路径用于生命周期操作。如果插件 Router 能匹配这些路径，无论是字面量、
动态参数、Catch-all 还是尾部斜杠，校验都会用稳定的 `reserved_route` 原因隔离该插件。
插件仍可使用 `/admin/start` 等嵌套路径。

开发 CORS 刻意只允许 `GET` 和 `POST`。需要其他 HTTP Method 的插件应采用同源部署，
不要假设存在更宽泛的跨域契约。

插件通过调用方自己定义的运行时 Protocol 请求另一个插件的公开能力；不支持直接导入
另一个插件包：

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class GreetingCapability(Protocol):
    def message(self) -> str: ...


greeting = context.get_service("demo.greeting", GreetingCapability)
```

## Settings

只在平台基类的子类中声明一次字段，并让插件类指向它：

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

管理器拥有 `RELIAFORGE_<PLUGIN_ID>_` 前缀和 `__` 嵌套分隔符。它会在 Initialize Hook 前
创建一个实例，生成公开 Schema，并在 Restart 时重新创建 Settings。Secret 使用
`SecretStr`，并通过进程环境或部署 Secret Storage 注入。不要提供 Secret 默认值，也不要
记录 Validation Exception 原文。

平台把所有插件路由挂在管理认证之后。Catalog、detail、`/live`、`/ready` 和 `/status`
保持公开只读，清单不能选择匿名开放插件路由。

Catalog 和 detail 响应包含值为 `start`、`stop`、`restart` 的 `available_actions`。管理器
根据运行时状态和依赖保护生成列表，插件代码和客户端都不能声明它。该字段是 UI Affordance，
不是授权：每个生命周期请求仍会经过认证和重新校验。

管理 `restart` 会在已加载插件上执行 stop、initialize 和 start，不会从磁盘重新加载 Python
源码或清单。

内置 Runbook 示例展示了 `demo ^1.0.0`、类型化能力查找、确定性预览数据、反向关闭顺序和
提供方生命周期保护，全程不会执行命令，也不进行网络、数据库或文件系统 I/O。
