# 架构

[English](../architecture.md)

FastAPI 应用提供管理 API 和插件自己的路由。一个插件管理器负责加载插件并控制其状态。

```text
FastAPI application
  -> management API
  -> plugin manager
       -> reads and validates manifests
       -> orders dependencies
       -> imports plugins
       -> initializes, starts, checks, and stops plugins
       -> records status, health, and safe errors
  -> plugin API routes -> plugin services
```

## 发现与依赖检查

管理器会先读取所有 `manifest.json`，再导入 Python 代码。它会检查重复 ID、API 版本、缺失或
不兼容的依赖、循环依赖和重复能力名称。任何校验错误都会停止后端启动。完整依赖图通过后，
才会按依赖顺序导入插件。

导入或构造失败会生成一条不包含原始异常文本的 `load_error` 记录。依赖该插件的插件会变成
`dependency_unavailable`。无关插件和管理 API 仍然可用。再次加载之前，失败导入会从临时
模块命名空间中清除。

## 插件上下文与共享服务

每个插件都有自己的 `PluginContext`。上下文记录该插件创建的服务和事件订阅，因此清理时只会
移除该插件自己的注册项。插件的停止钩子负责释放客户端、任务等资源，初始化只完成了一部分
时也要能够释放。

插件在 `capabilities` 中列出共享服务，并在初始化时注册。消费者按名称获取服务，再用自己定义的
可运行时检查 Python `Protocol` 校验。声明的服务没有注册，或插件注册了未声明的服务时，启动
会失败。消费者必须先在 `dependencies` 中声明提供者，否则获取服务时会报
`UndeclaredDependencyError`，初始化失败。

## 配置

每个插件可以提供一个 `PluginSettings` 子类。管理器读取带 `RELIAFORGE_<PLUGIN_ID>_` 前缀的
变量，创建一个经过校验的实例，并放入插件上下文。同一个类还会生成公开配置 Schema。API 响应
和启停错误不会包含密钥值。

## 状态、健康和操作

运行状态记录插件是已发现、已验证、已初始化、运行中、已停止还是出错。健康状态单独记录健康、
降级、错误或停止。

`/live`、`/ready` 和 `/status` 返回内存状态，不会联系外部系统，也不会执行修复。初始化、
启动、停止和每个事件处理器都有时间限制。

每个插件响应都包含 `available_actions`。管理器根据当前实例、状态、依赖和运行中的依赖方计算
该列表。API 会认证并重新检查每项操作请求。

## 事件与关闭

事件总线并发调用当前订阅者。处理器出错或超时时，结果会写入投递报告，但不会影响其他处理器。
事件只保存在内存中，不是持久队列。

插件停止时，即使停止钩子失败，管理器也会移除它的服务和订阅。启停超时包括等待管理器锁的时间。
进程关闭时，ReliaForge 不会绕过该锁，也不会修改正在执行的插件操作。

插件会作为受信任代码在后端进程内运行。安全沙箱不会把它们与进程或其他插件隔离。
