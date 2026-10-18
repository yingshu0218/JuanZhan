# T33 验收映射与执行

本表覆盖路线图UX-01～14及META-01～16，共30条；复用真实业务测试，不为数量复制30份镜像测试。参数化用例的全部参数均须通过。每行列出主要后端断言与补充浏览器套件；单个测试文件存在或完成构建不能视为通过。UX-12额外要求test_acceptance的真实OCR排队→完成用例：排队时不得把旧扫描正文称为可用文字，实际OCR成功后才发布新文字。机器清单见[scripts/acceptance-cases.json](../scripts/acceptance-cases.json)。

| 用例 | 核心断言 | 主要自动化证据 | 补充浏览器套件 |
|---|---|---|---|
| UX-01 | 重名及同哈希不同来源不误合并 | [tests/test_uploads.py](../tests/test_uploads.py) `test_duplicate_reject_and_explicit_keep_separate` | sources |
| UX-02 | 逻辑目录不写回磁盘 | [tests/test_source_initial.py](../tests/test_source_initial.py) `test_atomic_metadata_registration_and_independent_same_hash_documents` | sources |
| UX-03 | 增量新增入收件箱且不持续镜像 | [tests/test_source_incremental.py](../tests/test_source_incremental.py) `test_new_files_needs_review_use_new_target_and_never_recreate_tree` | sources |
| UX-04 | 有Folder仍可待整理 | [tests/test_document_api.py](../tests/test_document_api.py) `test_upload_to_detail_list_properties_triage_and_recycle` | library |
| UX-05 | 系统文件拖入与内部拖动分开 | [tests/test_uploads.py](../tests/test_uploads.py) `test_real_upload_atomic_registration_and_truthful_parse_job` | library |
| UX-06 | 标签增删及逐项失败 | [tests/test_batches.py](../tests/test_batches.py) `test_snapshot_partial_results_restart_and_guarded_undo` | library |
| UX-07 | 改名谨慎重关联且歧义暂停 | [tests/test_source_incremental.py](../tests/test_source_incremental.py) `test_duplicate_hash_move_is_ambiguous_and_does_not_create_or_merge_documents` | sources |
| UX-08 | 离线不直接判永久丢失 | [tests/test_source_incremental.py](../tests/test_source_incremental.py) `test_failure_breaks_missing_evidence_without_changing_entries` | sources |
| UX-09 | 取消索引阻止再导入 | [tests/test_exclusions.py](../tests/test_exclusions.py) `test_external_purge_keeps_rule_prevents_reimport_and_removal_allows_new_document` | sources |
| UX-10 | 回收恢复保留分类字段标签 | [tests/test_batches.py](../tests/test_batches.py) `test_restore_batch_is_scoped_versioned_and_undoable` | library |
| UX-11 | 中文正文标题字段日期联合筛选 | [tests/test_search.py](../tests/test_search.py) `test_real_fts_get_post_joint_filters_stale_failure_and_trash` | search |
| UX-12 | OCR未完成不称完整正文 | [tests/test_search.py](../tests/test_search.py) `test_scanned_pdf_without_requested_ocr_reports_limited_content` | search |
| UX-13 | 并发409而非静默覆盖 | [tests/test_metadata.py](../tests/test_metadata.py) `test_version_csrf_inactive_cross_space_trash_and_concurrent_writes` | library |
| UX-14 | 不能通过UI物理删除外部原件 | [tests/test_exclusions.py](../tests/test_exclusions.py) `test_external_purge_keeps_rule_prevents_reimport_and_removal_allows_new_document` | sources |
| META-01 | 业务类型和MIME正交 | [tests/test_catalog.py](../tests/test_catalog.py) `test_document_type_fields_are_atomic_scoped_and_preserve_values` | library |
| META-02 | 人工编号不被OCR覆盖 | [tests/test_content.py](../tests/test_content.py) `test_actual_candidate_adoption_and_reprocess_never_erase_confirmed_fields` | reading |
| META-03 | 重解析保留业务字段标签 | [tests/test_acceptance.py](../tests/test_acceptance.py) `test_converter_outage_keeps_manual_data_old_content_then_recovers_same_job` | jobs |
| META-04 | ISO日期与范围 | [tests/test_search.py](../tests/test_search.py) `test_exact_typed_filters_false_absence_and_literal_contains` | search |
| META-05 | Decimal固定缩放精确比较 | [tests/test_metadata.py](../tests/test_metadata.py) `test_decimal_boundaries_and_failed_audit_roll_back_values_and_version` | search |
| META-06 | false与null不同 | [tests/test_metadata.py](../tests/test_metadata.py) `test_seven_types_exact_storage_null_false_noop_and_audit` | search |
| META-07 | key及type身份不可静默修改 | [tests/test_fields.py](../tests/test_fields.py) `test_auth_unknown_scope_and_immutable_identity` | — |
| META-08 | 六格式统一schema及真实定位 | [tests/test_conversion_formats.py](../tests/test_conversion_formats.py) `test_six_real_formats_uniform_result_and_verified_artifacts` | reading |
| META-09 | 离线仍可读明确标记的缓存 | [tests/test_acceptance.py](../tests/test_acceptance.py) `test_offline_readonly_source_keeps_actual_cached_content` | sources |
| META-10 | 解析失败保留最近成功正文 | [tests/test_parsing.py](../tests/test_parsing.py) `test_failed_new_revision_retains_successful_content_and_business_fields` | reading |
| META-11 | HTML及脚本不执行 | [tests/test_conversion_formats.py](../tests/test_conversion_formats.py) `test_markdown_asset_contains_no_active_markup_or_links` | files |
| META-12 | 元数据版本冲突409 | [tests/test_metadata.py](../tests/test_metadata.py) `test_version_csrf_inactive_cross_space_trash_and_concurrent_writes` | reading |
| META-13 | 拒绝跨空间字段Tag类型 | [tests/test_document_api.py](../tests/test_document_api.py) `test_scope_validation_tag_deltas_and_atomic_conflict` | search |
| META-14 | 重复重建不重复当前FTS记录 | [tests/test_indexing.py](../tests/test_indexing.py) `test_rebuild_same_inputs_never_duplicates_and_repairs_duplicate_rows` | — |
| META-15 | 中英混排编号两字词检索 | [tests/test_indexing.py](../tests/test_indexing.py) `test_real_chinese_short_words_traditional_mixed_ascii_and_fts_operators` | search |
| META-16 | 改类型保留旧值 | [tests/test_metadata.py](../tests/test_metadata.py) `test_optional_values_are_still_typed_and_template_change_preserves_history` | library |

另外，META-02要求同一真实OCR用例确认人工合同编号未被识别结果覆盖。

来源边界/实际扫描、文件变化、歧义、排除和外部字节保留由sources浏览器套件在内核只读Docker挂载中验证。source_initial/incremental中的准备清单/租约注入仅用于事务和竞态验证，不把手造清单当物理扫描成功。新acceptance离线缓存用实际只读sysfs字节及真实TCP Converter；明确不宣称扩展名不支持的sysfs文件被扫描导入。浏览器Route故障只注入网络失败/延迟，不伪造成功业务响应。

## 执行

```sh
UV_CACHE_DIR=/workspace/.uv-cache JUANZHAN_CHROMIUM_PATH=/usr/bin/chromium .venv/bin/python scripts/acceptance.py
```

默认完整后端→构建→sources→library→reading→search→jobs→files，浏览器串行；sources的Docker网络操作与其他浏览器隔离。运行器只用现有依赖，输出默认私有/tmp目录；可用`--output`指定新的仓库外目录。`--phase backend`/`--phase browser`只验证选定阶段，未跑的映射显示not_run，不算整体验收通过。JUnit缺失/无测试/跳过/失败使阶段失败，保存首个非零退出码并停止，后续阶段不伪装已执行。所有结果仅指本次实际执行。运行前机器清单会核验30个ID与实际测试函数；最终判定读取JUnit，后端按参数化测试的全部结果、浏览器按对应完整套件结果，不根据文件存在判通过。若分阶段执行，可用下列命令只汇总本次真实报告（不重跑、不把not_run当passed）：

```sh
.venv/bin/python scripts/acceptance.py --phase assess --reports /tmp/current-backend /tmp/current-browser
```

后端使用临时SQLite及原件/派生目录；真实转换/OCR样本和HTTP、WAL备份/新目录恢复、租约及事务故障覆盖原件保留。sources只管理自身随机fixture容器/卷，不修改正常管理员/.env/数据卷。运行前需已有构建完成的当前版本Compose镜像与OCR模型；构建和环境准备见DEVELOPMENT。

## 故障注入证据

| 故障 | 测试 | 守住的事实 |
|---|---|---|
| Converter真实连接拒绝→恢复 | test_acceptance第一例 | 同Job有限重试、人工字段/标签及旧正文保留，恢复后新正文发布 |
| 只读来源真实离线 | test_acceptance第二例、sources浏览器 | 缓存可读且未核验提示，下载拒绝，不判永久丢失 |
| worker实际进程退出/超时 | test_jobs actual_process_crash / worker_enforces_timeout | 租约回收、旧worker围栏与累计预算 |
| 临时文件中断/发布磁盘失败 | test_storage hard_crash / disk_failure_before_publication | 不产生部分引用，不破坏已发表对象 |
| DB提交失败、解析晚到 | test_parsing publish_transaction_failure / newer_request_and_revision_and_trash | 旧成功保留、孤儿安全、过期结果不发布 |
| 索引提交中断/代次变化 | test_indexing transaction_interruption / newer_input_fences | 旧成功索引保留、后续重建不重复 |
| 备份损坏/软链/越界/中断标记 | test_backup | 拒绝坏包和覆盖、未完成恢复不启动、原实例不变 |

T33验证功能边界，不替代T34性能基线、镜像发布及实际运维切换。浏览器主要为Linux Chromium桌面1440×1000/手机390×844；未承诺真实手机、Firefox/WebKit、网络文件系统、断电硬件与大规模压力覆盖。T16外部转托管及批量reprocess/set_metadata仍明确未实现。
