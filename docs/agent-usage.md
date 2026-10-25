# Agent 调用约定（1.4.0，待发布）

面向 Agent 的入口仍是 `scripts/mubu_api.py`，统一在子命令前加 `--agent`。不需要安装全局短命令，也不需要 MCP。省略 `--agent` 时保留既有 CLI 的输出与交互行为。

LoreLab 成套安装使用 `lorelab tool mubu -- --agent …`；以下独立源码示例中的 `.venv/bin/python scripts/mubu_api.py` 前缀应替换为 `lorelab tool mubu --`，其余参数保持不变，避免误用全局 Python 或其他源码版本。

## 调用流程

```sh
# 只读验证已有桌面登录
.venv/bin/python scripts/mubu_api.py --agent --auth desktop auth-status

# 读取目标与版本
.venv/bin/python scripts/mubu_api.py --agent --auth desktop nodes DOC_ID --node-id NODE_ID

# 预览，再在用户已授权的范围内执行；两次使用相同修改参数
.venv/bin/python scripts/mubu_api.py --agent --auth desktop node-update DOC_ID \
  --node-id NODE_ID --text '新内容'
.venv/bin/python scripts/mubu_api.py --agent --auth desktop node-update DOC_ID \
  --node-id NODE_ID --text '新内容' --expect-version VERSION --execute
```

Agent 模式下节点和媒体写命令执行时**必须**提供 `--expect-version`，其值来自预览结果的 `data.version`。冲突后重新读取和预览，不直接套用旧版本。预览与执行是程序流程，不要求每次向用户重复确认已有授权。

同一文档串行操作。版本检查不是服务端锁；不能防止其他客户端在检查后插入修改。

## 输出与退出码

stdout 始终是一份 JSON；日志在 stderr，参数错误和 `--help` 也输出 JSON。成功结果例如：

```json
{
  "schema_version": 1,
  "cli_version": "1.4.0",
  "command": "create",
  "ok": true,
  "status": "ok",
  "data": {"doc_id": "DOCUMENT_ID"}
}
```

失败含 `error.code`、`message`、`retryable`、`next_action`。节点与媒体失败的操作 ID、阶段等证据放在 `data` 中。不要解析中文文案决定下一步；按错误码和状态处理。

| 退出码 | 含义 | Agent 后续动作 |
| --- | --- | --- |
| `0` | 调用成功、预览、无变化或完成限定范围核验 | 读取 `status` 和 `data`，成功不等于执行过写入 |
| `1` | 鉴权、输入、请求、旧命令写入未确认，或搜索/导出部分失败 | 按 `error.code` 与 `next_action` 处理 |
| `2` | 参数错误或版本冲突 | 修正参数，或重新读取并预览 |
| `3` | 节点/媒体写入被拒绝、结果不确定，或复核证据不足 | 查操作记录与云端状态，不直接重试 |

常用错误码：`AUTH_REQUIRED`、`DESKTOP_ACCESS_DENIED`、`INPUT_REQUIRED`、`VERSION_REQUIRED`、`INVALID_ARGUMENTS`、`VERSION_CONFLICT`、`WRITE_UNCONFIRMED`、`WRITE_UNCERTAIN`、`WRITE_REJECTED`、`PARTIAL_FAILURE`。

- `DESKTOP_ACCESS_DENIED` 表示系统拒绝读取桌面数据，尚未发送网络请求。检查运行 CLI 的宿主应用对幕布数据目录的访问权限；macOS 在“系统设置 → 隐私与安全性”中检查。不要误导用户重新登录，也不要改用其他账号或绕过系统访问控制。权限恢复后再运行 `auth-status`。
- `login` 缺凭据立即失败，不调用 `input/getpass`。桌面会话失效仍需在幕布端登录；不接管验证码等登录交互。
- `save` 必须显式提供 `--file`、`--md` 或 `--content`，不等待标准输入。
- `search` 保留 `truncated`、`limit`、`max_depth`、`errors` 和失败对象；`truncated: true` 不能解释成完整搜索。
- `export-tree` 遇失败项或深度截断返回 `partial`、非零退出码和统计；已写出的本地文件不会自动撤销。
- 创建响应缺少文档/文件夹 ID 时返回 `WRITE_UNCONFIRMED`，不能把空 ID 当成成功。
- Agent 模式的 API 请求不自动重试，包含读取请求；收到鉴权错误后也不重登并重发原请求。密码模式仍可在发送前使用已配置凭据登录。所有错误默认 `retryable: false`，不会自动重传写入。
- 旧 `create/mkdir/save/move/rename/purge` 没有节点操作日志，原有写入语义不变；不确定时读取目标目录或文档核对，不能假定这些命令具有默认预览或自动恢复。

## 只读操作查询与核验

```sh
# 不需要登录，也不输出文档正文、事件或完整快照
.venv/bin/python scripts/mubu_api.py --agent operations --doc-id DOC_ID --limit 20
.venv/bin/python scripts/mubu_api.py --agent operation-status OPERATION_ID

# 使用原记录读取云端；不会重新上传、绑定、修改文档或操作记录
.venv/bin/python scripts/mubu_api.py --agent --auth desktop operation-status OPERATION_ID --verify
```

操作记录仍位于 `MUBU_STATE_DIR/operations`，默认 `~/.local/state/mubu-cli/operations`。列表按文件修改时间倒序；`truncated` 表示还有记录，`invalid_records` 表示扫描过程中遇到损坏记录。`record_status` 是原操作留下的状态，不代表此刻云端状态。

| `--verify` 结果 | 证据范围 |
| --- | --- |
| `verified` + `whole_document` | 新节点记录的完整预期文档相符，且版本恰好递增一次 |
| `observed` + `image_binding` | 目标节点存在记录中的图片引用；不证明整篇文档未变化 |
| `verified` + `attachment_content` | 已知附件 ID 仍存在、原附件列表仍保留，且下载 SHA-256 相符 |
| `uncertain` | 旧记录缺字段、缺附件 ID、发生后续编辑或核验不一致；不能据此断言原操作失败 |

所有复核都是只读，`executed: false` 指本次复核未写入，不能解释为原操作没有执行。未看到预期结果不代表可以安全重试；不按同名文件猜测附件已绑定。当前不提供自动补绑、重传、回滚或孤立资源删除。

## 本轮取舍

已补齐 Agent 必需的无交互调用、结构化结果、部分失败识别、请求不重发和只读核验。`node-import` 支持一次追加多棵大纲子树，契约见 [批量大纲](node-editing.md#批量追加大纲分支)；它沿用预览、版本绑定、操作记录和整篇核验。全局命令安装、任意富文本、更多媒体管理与导出不在本轮范围。MCP、多人协作、双向同步、数据库/知识库工作流继续排除。

## 验证

Python 3.9 / 3.12 各 216 项测试通过，ruff 通过。真实只读验收覆盖登录状态、操作摘要及既有测试附件的下载哈希核验，没有新增云端写入。Python 3.9 环境有既存 LibreSSL 警告；联网验收使用 Python 3.12。
