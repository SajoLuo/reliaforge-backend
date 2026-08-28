# 插件开发

[English](../plugin-development.md)

先生成插件，再把示例服务替换为你的运维任务：

```bash
reliaforge-scaffold sample_tool --destination ./local-plugins
```

## 插件中的文件

- `manifest.json` 说明插件信息。
- 插件类处理初始化、启动、健康检查和停止。
- 设置类读取环境变量。
- 服务包含运维任务，不导入 FastAPI。
- 路由校验 HTTP 输入并调用服务。
- 测试覆盖插件 API、状态变化、健康检查和清理。

## Manifest

支持的字段包括：

- `id`、`name`、`version`、`description` 和 `api_version`；
- `entrypoint`，使用相对于插件目录的 `module:Class` 形式；
- `dependencies`，包含插件 `id` 和可接受的 SemVer `version` 范围；
- `capabilities`，插件所提供服务的唯一点分名称；
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
和重复能力名称都会阻止受影响的插件加载。

## 启停与健康检查

插件管理器按以下顺序调用钩子：

```text
discover -> validate -> initialize -> start -> health -> stop
```

启停钩子是异步的，必须响应取消。同步 I/O 应放入有边界的工作线程，并设置超时。健康检查必须
是快速、同步的快照，不能发起网络、数据库、文件系统或命令调用。

初始化时，需要注册 `capabilities` 中列出的每项服务。插件停止时，ReliaForge 会移除该插件的
服务和事件订阅，即使停止过程失败也会清理。

`context.publish(...)` 会把进程内事件发送给当前订阅者。处理器并发运行并有超时限制，单个
处理器失败不会让发布者失败。事件不会持久化，因此不能用作任务队列。

## 路由与共享服务

ReliaForge 把每个路由挂载到 `/api/v1/plugins/{plugin_id}` 下。业务逻辑放在服务中，HTTP
校验放在路由中。根路径下的 `/start`、`/stop` 和 `/restart` 保留给插件启停操作。

使用其他插件的服务时，先定义自己需要的接口，再按能力名称向上下文获取：

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class GreetingCapability(Protocol):
    def message(self) -> str: ...


greeting = context.get_service("demo.greeting", GreetingCapability)
```

## Settings

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
