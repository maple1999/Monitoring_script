# 开发说明（DEV SPEC）

版本：V1.0（依据 PRD 基线 2026-03-04）

## 1. 目标概述

- 每天 08:45（Asia/Singapore）发送 1 封 Daily Digest 邮件，包含 3 条：比赛/活动/实习各 Top1。
- 来源采用“站点白名单 + 关键词检索”，限制每日候选上限，优先推送新增条目。
- LLM 仅用于难点评估/匹配度/评价/补充信息与必要翻译（非主链路字段抽取）。
- 异常与降级必须可控：日报可降级发送，必要时发送告警，避免静默失败。

## 2. 范围与非目标

- 范围：Contest（Kaggle + 国内权威/大厂赛事）、Activity（开发者/算法活动）、Internship（CV/多模态/AIGC/VLM/LLM，兼容 AI 产品岗）。
- 非目标：通用网页全自动字段抽取；管理后台；付费邮件服务依赖；大规模爬虫。

## 3. 系统架构

- Scheduler：定时触发（Asia/Singapore）、幂等执行。
- Source Manager：白名单与关键词管理（`domains_allowlist.yaml` 自动生成 + 人工覆盖）。
- Collector：按类别抓取候选（Contest/Activity ≤15，Internship ≤30），控制超时/重试/速率。
- Parser/Normalizer：规则抽取核心字段并统一为 Item Schema；缺失需明确标注。
- Deduplicator：URL 去重、`item_id=hash(source+url)`；可选标题相似去重。
- Scorer/Selector：评分、排序与 Top1 选取；不足用存量（默认 30 天）补位。
- LLM Evaluator：固定模板输出段落与翻译策略；失败走 Fallback，并触发告警/标注降级。
- Mail Renderer/Sender：HTML + Text 渲染；SMTP 发送日报与告警。
- Store/Logger：SQLite（或 JSONL）记录 items、runs、send_log；结构化日志与 Run ID。
- Alert Manager：异常检测（Run/Crawl/LLM/Content）、降级与告警邮件。

## 4. 运行流程

1) 加载 config 与环境变量
2) 收集候选（contest/activity/internship）
3) 解析/规范化（Item Schema）
4) 去重 + `is_new` 标注
5) 评分与排序（含规模/方向/紧迫度）
6) 每类取 Top1（不足走存量补位）
7) LLM 段落（失败走 Fallback）
8) 生成与发送日报
9) 写 run/send 日志
10) 异常与降级时发送告警/顶部标注

## 5. 数据模型

最小必需字段（Item）：

- 识别：`item_id`（hash(source+url)）、`category`（contest/activity/internship）、`title`、`url`、`source`。
- 详情：`company_or_org`、`summary`、`requirements`、`location`（实习）、`work_mode`（默认 offline）、`deadline`（赛/活可选）。
- LLM：`llm_block`（固定模板段落）、`match_score`（0-5）。
- 追踪：`tags`、`first_seen_time`、`last_seen_time`、`is_new`、`status`（active/expired/invalid）。
- 展示：`title_en/title_zh`、`summary_en/summary_zh`（纯英文时必填）。

SQLite 表（建议）：

- `items(item_id PK, url UNIQUE, category, title, source, ...; first_seen_time, last_seen_time, status, is_new, llm_block, match_score)`
- `runs(run_id PK, time, version, status, stats_json, error_summary)`
- `send_log(run_id, mail_type, to, subject, status, error)`

索引：`items(url)` 唯一；`items(category, status)`；`items(first_seen_time)`。

## 6. 配置与环境

`config.yaml` + 环境变量：

- 调度：`schedule.time`，`schedule.timezone`（默认 Asia/Singapore）。
- 限额：`limits.contest_candidates`，`limits.activity_candidates`，`limits.internship_candidates`，`output.daily_items_per_category`。
- 新旧/补位：`staleness.max_days_active`（默认 30）、`deadline.remind_days`（默认 14）、`dedup.by_url`。
- 语言/翻译：`language.primary`（zh）、`translation.english_only`、`translation.mode`（title_and_summary）。
- 关键词：`keywords.include/exclude`、`pm.prefer_ai_pm`、`pm.allow_general_pm_fallback`。
- 来源：`sources.domains_allowlist_autogen`（true）、外置 `configs/domains_allowlist.yaml`。
- 邮件/告警：`smtp.*`（host/port/use_tls/sender/receiver）、`alerts.enabled`、`alerts.send_separate_email`。
- 环境变量：`SMTP_PASSWORD`、`LLM_API_KEY`、其他 Token。

## 7. 采集与解析

- 站点白名单：Kaggle 固定域、公司官网/招聘/开发者/社区、国家级竞赛平台域。
- 抓取：站内列表/搜索关键词过滤；解析标题、摘要、DDL（赛/活）；实习解析公司、地点、工作模式。
- 解析优先级：结构元素 > 半结构列表 > 关键段落；未解析需标注“未解析到/页面未提供”。
- 时间/DDL：多语种格式识别（dateparser），赛/活 ≤ remind_days 触发“临近截止”。
- 工作模式：remote/onsite/hybrid 识别，缺省 offline。
- 限流鲁棒：UA 池、超时/重试（tenacity）、速率限制、失败来源计数与汇报。

## 8. 评分与选取

- 新增优先：新增 > 非新增；同档按时间近（`first_seen_time/last_seen_time`），可配置。
- 规模/权威（赛/活）：主办级别（国家/官方 > 一线大厂 > 其他）> 奖金 > 线下终赛/发布会。
- 实习偏好：方向（CV > 多模态 > AIGC > VLM > LLM）、岗位（研究/算法/AI 产品优先），排除测试/运维等黑名单。
- DDL 约束：过期直接失效；存量有效期 `first_seen_time + N` 天（默认 30）。
- 打分建议：`score = w_new + w_time + w_scale + w_topic + w_urgency`（权重可配置）。

## 9. LLM 与模板闸门

- 输入仅为已抽取的安全片段（标题/摘要/关键信息），显式“不编造”。
- 输出固定顺序：难点评估（三维）→ 匹配度（R/5 + 理由）→ 评价（2 句）→ 补充信息（无则“无”）。
- 校验：模板完整性、关键词审计（缺失信息必须如实标注）。
- 降级：LLM 失败使用 Fallback 简述并标注“LLM 不可用”，触发告警或在日报顶部标红（按配置）。

## 10. 邮件规范

- 主题：`Daily CV Digest - YYYY-MM-DD（比赛/活动/实习各 1）`
- 顶部概览：运行状态（成功/降级）、新增概况、临近截止项汇总。
- 正文三条：类别 + 新增/存量标识 + 标题（中英规则） + 链接 + 关键字段 + LLM 段落。
- 运行信息：候选抓取数、失败来源简述、Run ID。
- 告警邮件：错误类型（Run/Crawl/LLM/Content）、影响范围、关键信息、Run ID/日志位置、是否仍发送日报、建议操作。

## 11. 日志与调度

- 统一日志（INFO/ERROR），Run ID 贯穿；文件轮转；关键指标（候选数、去重率、失败来源）。
- 失败快照：错误类型与最小复现信息；LLM 请求仅摘要日志。
- 调度：APScheduler（Asia/Singapore），UTC 落盘时间戳，失败在下次日报顶部提示“上次失败”。

## 12. 依赖与结构建议

- 依赖：httpx/requests、beautifulsoup4/selectolax、dateparser、apscheduler、jinja2、sqlite3/sqlmodel、pydantic、tenacity。
- 目录：
  - `src/config.py`，`src/scheduler.py`，`src/sources/`，`src/collector/`，`src/parser/`，`src/normalizer.py`，`src/dedup.py`，`src/scorer.py`，`src/selector.py`，`src/llm.py`，`src/mailer.py`，`src/renderer.py`，`src/storage/`，`src/alerts.py`，`src/main.py`
  - `configs/config.yaml`，`configs/domains_allowlist.yaml`，`tests/**`，`data/fixtures/**`

## 13. 测试策略与验收

- 单元：解析器（离线 HTML 夹具）、时间/DDL、去重/打分/选取、模板校验。
- 集成：端到端（禁网，用夹具），邮件渲染快照。
- 回归：空候选、全部过期、LLM 失败、SMTP 失败。
- DoD 对齐：固定 3 条、DDL 提醒、LLM 模板合规、降级/告警完整。

