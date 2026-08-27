# 架构

[English](../architecture.md)

ReliaForge 将平台控制面与插件领域逻辑分离。

```text
FastAPI application
  -> management router
  -> plugin manager
       -> manifest loader
       -> dependency resolver
       -> plugin records (candidate / instance / safe error category)
       -> lifecycle state machine
       -> controlled plugin context
            -> service container
            -> failure-isolating event bus
  -> plugin routers -> plugin services
```

插件发现阶段首先读取并校验所有 `manifest.json`，不会导入插件代码。管理器会针对完整清单
集合拒绝重复身份、不支持的 API 版本、缺失或版本不兼容的依赖、依赖环，以及重复的能力
提供方；完成这些检查后，才按依赖顺序导入入口点。导入失败、入口点检查失败或构造失败
都会成为不泄露敏感信息的 `load_error` 记录。其依赖方不会被导入，并会成为
`dependency_unavailable`；其他独立分支和管理平面仍可继续运行。失败导入会清理隔离的模块
命名空间，后续加载不会复用半导入状态。

每个插件都会获得提供方范围内的上下文。服务注册会记录所有权，清理时只移除该插件拥有
的资源。插件不能直接导入其他插件的实现；消费方使用自己定义的
`@runtime_checkable Protocol` 解析能力。服务缺失和结构不兼容会产生不同的稳定错误。
清单中的能力是可执行服务契约：插件不能注册未声明的服务；声明的能力未完成注册时，
启动也会失败。

每个插件可以声明一个 `PluginSettings` 子类。管理器使用规范的
`RELIAFORGE_<PLUGIN_ID>_` 前缀构造实例，将其注入 `PluginContext`，并通过
`model_json_schema()` 生成公开 Schema。清单不包含手写 Settings Schema。目录数据和
生命周期错误消息永远不包含 Secret 值。

`/live`、`/ready` 和 `/status` 读取进程本地的生命周期与服务快照，不查询外部系统，
也不修复状态。初始化和启动都在已配置的截止时间内执行。插件是受信任的进程内扩展，
不是沙箱边界。

生命周期状态不使用 `degraded`；该值只属于健康状态。平台计数会把每条记录恰好归类为
running、degraded、stopped 或 error。插件自有路由继承与生命周期操作相同的管理认证
依赖；liveness、readiness、status、catalog 和 detail 保持公开只读。

事件总线会并发调用当前订阅者，并为每个处理器设置截止时间。处理器异常和超时与发布者
隔离，并以稳定、不泄露敏感信息的投递报告表示；发布者自身的取消仍会向上传播。投递只在
当前进程内发生，既不是持久队列，也不是诊断存储。插件停止时始终释放上下文拥有的服务
和订阅，即使停止 Hook 或事件投递失败也不例外。

生命周期操作的截止时间包含等待管理器操作锁的时间。受支持的 ASGI Server 会在调用
lifespan shutdown 前排空请求任务。`stop_all` 仍把防御性的锁等待计入关闭预算；如果等待
超时，它会直接返回，不会与当前锁拥有者竞争或修改其插件上下文，进程退出仍是最终恢复
手段。

目录中的生命周期操作同样由服务器拥有。`available_actions` 根据运行时实例、状态、
运行中的依赖和活动依赖方计算。加载失败记录，或正受到运行中依赖方保护的提供方，会暴露
空列表，防止客户端猜测管理器会拒绝的规则。
