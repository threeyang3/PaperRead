# Feed v2

Feed v2 新增：

- `capabilities: {raw, ai, community}`；
- `community_data_schema_version`；
- schemas、licenses 和 policy 契约；
- current 中的贡献、评审、贡献者和应用版本计数；
- `manifests/community/<paper_uid>.jsonl`；
- `papers/<uid>/community/<github>/<contribution>/rN.json`；
- profiles 和 retractions 的版本化 Schema。

Raw/AI 路径与 v1 不变。1.5 reader 可读取 v1；v1 reader 遇到 v2 会提示升级，
不会猜测社区数据。基础 Raw/AI 的 `minimum_reader_version` 保持 1.4.0，社区
能力由独立 Schema 版本协商，因此 Feed 不要求尚未发布的读者。

社区发布是独立 opt-in。publisher 只读取 outbox，不读取 User 标注目录。
