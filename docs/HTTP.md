# 阶段接口

`POST /api/stages/<stage>` 接收 `multipart/form-data`。字段 `sample=dirty`、`sample=clean` 或 `file=<CSV>` 三选一。阶段为 `intake`、`prepare`、`calculate`、`policy`、`balance`。预览不入库。

`POST /api/runs` 接收同样的输入，执行全批并返回运行报告（同时留存原始来源字节，供交账后重算）。`GET /api/runs` 返回最近 50 批。`GET /api/runs/<id>` 查询一批和当前复核状态；已交账批次会附带 `adjustment` 补证视图。

`PATCH /api/runs/<id>` 接收 `revision`、`status` 和 `note`。状态使用 `APPROVED`、`HELD` 或 `CLOSED`。冲突返回 409，客户端读取新版本后重试。

- `APPROVED` 要求对账平衡且无隔离、无失败组（`releasable=true`）。
- `CLOSED`（交账）只要求账平（每行都有着落，`balanced=true`），允许保留隔离的待核冲突记录，避免等补证错过结账；交账后批次冻结，不能再改复核意见。
- 交账不会把待核记录算作已采信：隔离数与失败组判定保持原样。

## 交账后补证

仅 `CLOSED` 批次可登记补证，所有操作都基于冻结的原始来源重算，原批次报告不变。

- `GET /api/runs/<id>/adjustment`：返回冲突记录清单、补证登记和重算后的对账视图。
- `POST /api/runs/<id>/supplements`：JSON 入参 `record`、`action`、`note`（3-200 字）。
  - `action=DENY`：只否认一份定义、不给正确定义，该记录仍计为隔离，不改变放行结论。
  - `action=CORRECT`：附 `definition`（`field`、`data_type`、`scale`、`nullable`、`has_default`），按来源同规则校验；通过后该记录恢复采信，受影响业务组重算，其他组保持原结论。
  - 同一记录同时只允许一条生效补证，重复登记返回 409 `SUPPLEMENT_EXISTS`。
- `POST /api/runs/<id>/supplements/<supplementId>/withdraw`：入参 `revision`。仅 `CORRECT` 补证可撤回；撤回后记录退回隔离，受影响组失去通过资格，其他组照旧，乐观锁冲突返回 409。
- `GET /api/runs/<id>/evidence`：原批次证据（`review-evidence/1`），内容始终冻结可查。
- `GET /api/runs/<id>/adjustment/evidence`：补证证据包（`review-evidence/2`），内含冻结快照、冲突清单、补证留痕与重算结果。
