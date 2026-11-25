# 数仓契约兼容矩阵规则登记

- 规模：中型

## 功能模块

| 模块 | 动作 | 接口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 样例采信 | 预览并定位坏行 | `POST /api/stages/intake` | `app/intake/service.py` | `tests/test_intake.py` |
| M2 字段注册 | 检查领域约束 | `POST /api/stages/prepare` | `app/modules/prepare.py` | `tests/test_prepare.py` |
| M3 读写匹配 | 查看业务计算结果 | `POST /api/stages/calculate` | `app/modules/calculate.py` | `tests/test_calculate.py` |
| M4 兼容签收 | 查看签收判定 | `POST /api/stages/policy` | `app/modules/policy.py` | `tests/test_policy.py` |
| M5 运行对账 | 对照输入、采信和隔离行 | `POST /api/stages/balance` | `app/modules/reconcile.py` | `tests/test_reconcile.py` |
| M6 批次复核 | 执行批次并签发或暂缓 | `POST /api/runs、PATCH /api/runs/<id>` | `app/review/service.py` | `tests/test_review.py` |
| M7 证据交付 | 下载复核清单 | `GET /api/runs/<id>/evidence` | `app/evidence/render.py` | `tests/test_evidence.py` |
| M8 交账补证 | 账平交账、否认/补正确认、撤回重算 | `PATCH /api/runs/<id>`、`/api/runs/<id>/supplements` | `app/adjustment/service.py` | `tests/test_closing.py`、`tests/test_supplements.py`、`tests/test_supplement_concurrency.py` |

## 输入陷阱

| 编号 | 规则 | 处理 | 测试 |
|---|---|---|---|
| TRAP-02 | 去除 BOM | `app/intake/reader.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-03 | 按逻辑记录读取引号内换行 | `app/intake/reader.py` | `tests/test_intake.py::test_quoted_newline_is_one_logical_record` |
| TRAP-04 | 重复表头计入忽略行 | `app/intake/service.py` | `tests/test_intake.py::test_repeated_header_is_counted` |
| TRAP-05 | 异常列数隔离 | `app/intake/schema.py` | `tests/test_intake.py::test_extra_column_is_isolated` |
| TRAP-06 | 归一化全角数字和千分位 | `app/intake/numeric.py` | `tests/test_intake.py::test_full_width_and_grouping_are_canonical` |
| TRAP-07 | 空值行隔离 | `app/intake/numeric.py` | `tests/test_intake.py::test_sentinel_keeps_row_out_of_total` |
| TRAP-08 | 记录键保留前导零 | `app/intake/schema.py` | `tests/test_intake.py::test_bom_preserves_identifier` |
| TRAP-14 | 冲突版本都进入隔离 | `app/intake/resolve.py` | `tests/test_intake.py::test_duplicate_conflict_removes_both_copies` |
| TRAP-16 | 引号未闭合时拒收文件 | `app/intake/reader.py` | `tests/test_intake.py::test_unclosed_quote_invalidates_source` |
| TRAP-18 | 区分空文件、全空白和仅表头 | `app/intake/reader.py` | `tests/test_intake.py::test_empty_states_have_distinct_causes` |
| TRAP-26 | 拒绝旧版本复核 | `app/review/store.py` | `tests/test_review.py::test_review_optimistic_lock` |

## 领域反例

类型 1 为 int32，2 为 int64，3 为文本，4 为 Decimal。Decimal 的整数位在生产者和读取器之间固定，只比较小数位。默认值只供缺列回填，不能覆盖生产者明确写入的 null。字段由稳定编号匹配。

`sample_data/incoming.csv` 的 0003 组触发预检异常，0004 组触发业务判定。`tests/test_calculate.py` 还核对逐组结论和证据字段。

## 交账与补证规则

- 交账（`CLOSED`）的门槛是账平而非零隔离：每条物理行都有着落即可交，冲突记录继续留在隔离区，不会被算成已采信。
- `DENY` 只否认一份冲突定义，未提供正确定义，记录维持隔离；`DENY` 补证没有采信动作，因此不允许撤回。
- `CORRECT` 提供完整字段定义，经过与来源文件相同的结构和领域校验后，冲突记录恢复为一条逻辑采信行（k 个冲突物理行收敛为 1 行），所在业务组整体重算并标记 `basis=ADJUSTED`，未涉及的组保持 `ORIGINAL`。
- 撤回已采信的 `CORRECT` 补证后，该记录退回隔离，受影响组按当前数据重算并可能失去通过资格；其他组结论不变。撤回后可重新登记补证，历史补证行保留留痕。
- 原批次报告、原证据（`review-evidence/1`）永久冻结；补证后的对账通过 `review-evidence/2` 单独交付。
- 同一记录的生效补证受唯一部分索引约束，补证撤回沿用乐观版本号，并发下只有一个写入成功。
