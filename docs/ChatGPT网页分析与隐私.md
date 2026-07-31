# ChatGPT 网页分析与隐私

`chatgpt-web` 与 OpenAI API 是两个独立 Provider。PaperFlow 使用本机 Playwright 和 Microsoft Edge，不读取或保存账号密码。

- 登录态位于 Vault 外的 `%LOCALAPPDATA%\PaperFlow\ChatGPTWeb`。
- 浏览器只由 PaperFlow 选择并上传 `.paperflow/runtime/staging/<run_id>/paper.pdf`。
- 原始 Vault 路径不会填入网页。
- 上传许可默认关闭，可随时在控制中心撤销。
- 模型按可配置强度顺序从当前账号可见菜单中选择，并记录实际网页标签。
- 无法确认最强模型、出现验证码或页面结构变化时暂停，等待用户接管。
- 返回内容必须通过 `paper-analysis.schema.json` 和 UTF-8 质量校验；格式错误最多请求修复一次。

上传论文前，用户仍应确认其有权将该 PDF 提供给第三方服务，并遵守对应账户、机构和论文许可要求。
