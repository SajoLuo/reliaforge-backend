# {{plugin_name}}

[English](README.md)

这个插件通过 HTTP 返回一段可配置的消息。

## 运行并调用接口

在后端目录中，把 `RELIAFORGE_PLUGIN_PATHS` 设为存放本插件的父目录，再重启后端。
本地开发时，调用：

```bash
curl --fail http://127.0.0.1:8000/api/v1/plugins/{{plugin_id}}/message
```

使用生成的默认配置时，返回：

```json
{"message": "Generated plugin is running", "plugin_id": "{{plugin_id}}"}
```

插件已停止时返回 HTTP `503`。生产环境中，调用 API 前需要先通过部署代理完成身份验证。

## 加入自己的函数

[插件教程](https://github.com/SajoLuo/reliaforge-backend/blob/main/docs/zh/plugin-development.md)提供了
查询函数和调用它的 API 的完整文件、请求示例。修改当前插件时：

- 保持目录名和 Manifest 中的 ID 都为 `{{plugin_id}}`。
- 把工具代码放在 `service.py` 或其他 Python 模块中，在 `router.py` 中增加 API。
- 在 `settings.py` 中定义配置项，启动后端前设置对应的环境变量。
- 如果创建了客户端或后台任务，在 `_on_stop()` 中释放它们，启动中途失败时也要清理。
- 使用其他插件的共享 Python 服务之前，先在 `dependencies` 中列出该插件。
- 密钥放在部署配置中，不要写进代码、默认值或日志。
- 用自己的 URL、参数、结果和失败情况替换本 README 中的示例。

## 测试插件

安装 `pytest` 和 `pytest-asyncio` 后，在插件目录中运行：

```bash
python -m pytest tests/test_plugin.py
```
