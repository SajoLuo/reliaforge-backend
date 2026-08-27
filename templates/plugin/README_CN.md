# {{plugin_name}}

[English](README.md)

本插件由 ReliaForge 公开模板生成。

- 自定义 `manifest.json` 时不要改变其中的 ID。
- 将领域行为保留在 `service.py`。
- Router 只负责校验、委托和 HTTP 错误映射。
- 在 `settings.py` 的 `PluginSettings` 子类中一次性定义非敏感字段。
- 把插件依赖声明为 `{ "id": "provider", "version": "^1.0.0" }` 对象。
- 通过部署配置注入 Secret，绝不能把它加入清单。

安装 `pytest` 和 `pytest-asyncio` 后运行初始行为测试。即使 pytest-asyncio 使用 Strict
模式，显式的 asyncio Marker 仍然有效：

```console
python -m pytest tests/test_plugin.py
```
