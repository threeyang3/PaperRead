# Zotero UI 集成

插件在 Zotero 提供以下公开 API 适配：

- Item Tree 状态列：AI、阅读、复盘、复现、同步。
- Item Pane 的 PaperFlow 区域，显示同一组高频状态。
- `Notifier` 的 item add/modify/delete 防抖队列，默认 1 秒合并事件。
- 条目上下文菜单中的“将选中论文加入 Collection”。
- 条目上下文菜单中的“连接 Core”和“分析选中论文”。Core 地址与会话令牌只保存于
  Zotero 本机偏好设置；令牌来自被忽略的 `.paperflow/runtime` 配对命令。
- “同步订阅预览”和“社区发布预览”菜单。前者只创建本机 Core 队列项，后者只生成
  需要用户确认的发布计划；两者都不会在 Zotero 回调中直接访问网络或写数据库。

状态列只读取本地缓存或认证 Core 返回的状态；Core 不可用时显示占位符，不会在每一行实时
启动 Python、AI 或公网请求。事件只提交公开条目键、附件键和身份提示，分析由 Core worker
在 pipeline lock 下执行。不同 Zotero 版本缺少 Item Tree/Item Pane API 时，插件
仅跳过对应 UI 并保留其他功能，不修改 Zotero DOM，也不访问数据库。
