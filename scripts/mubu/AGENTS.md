# mubu 模块

CLI 请求与文档操作实现；保持现有认证、默认预览和不确定写入不重发的边界。

## 成员

- `__init__.py`：包版本。
- `cli.py`：命令入口与命令分发。
- `agent_cli.py`：无交互 JSON 结果、稳定错误码。
- `client.py`：HTTP 封装与旧文档管理能力。
- `config.py`：配置、端点、异常类型，以及 Unix flock／Windows msvcrt 的 Token 与回收站写入互斥。
- `desktop.py`：只读发现桌面登录会话。
- `convert.py`：Markdown、OPML 等文档格式转换。
- `nodes.py`：定位节点、构建单次事件和预期文档，比较整篇内容。
- `outline.py`：校验纯文本 JSON 大纲并构建新节点树；不联网。
- `node_service.py`：读取快照、单次提交、整篇回读、私有操作记录。
- `node_cli.py`：节点及大纲导入参数、默认预览。
- `rich_text.py`：保留格式的局部文字和链接处理。
- `media.py`：图片上传与附件绑定、验证。
- `media_cli.py`：媒体命令参数与结果。
- `operations.py`：只读操作记录查询与云端核验。

大纲导入复用 `node_cli → nodes/outline → node_service`，不调用整体覆盖接口；同一文档由一个写入者操作。新增接口同步 `docs/node-editing.md`、`docs/agent-usage.md` 和根 `SKILL.md`。

CLI 标准流、文本文件与 JSON 操作记录统一为 UTF-8。已有 Token／回收站文件通过同目录临时文件和 `os.replace` 替换；Windows 不能把文件锁降级为空操作。独立脚本和旧 `mubu_api.py` 导入均不得要求 Unix 专用模块。

[PROTOCOL]: 变更时更新此头部，然后检查 AGENTS.md
