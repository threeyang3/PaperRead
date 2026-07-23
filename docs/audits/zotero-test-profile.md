# Zotero 写入测试边界

当前实现只在模拟 Zotero 对象上验证了公共 Collection API。真实主 Profile 未被用于写入
测试，因此本轮没有创建真实 Collection、条目或附件，也没有访问 `zotero.sqlite`。

执行真实迁移前，应启动独立测试 Profile，运行 `detect`、迁移 `plan` 和 dry-run，确认
备份与回滚清单后，再通过 Zotero 插件显式执行。插件返回的 item、attachment 和
collection keys 交给 `zotero migrate apply` 只写入 PaperFlow mapping；回滚只撤销本轮
新增的 membership/测试对象，不删除迁移前已有数据或原 Vault PDF。
