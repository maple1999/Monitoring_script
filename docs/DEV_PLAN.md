# 开发计划（DEV PLAN）

版本：V1.0（依据 PRD 基线 2026-03-04）

## 1. 里程碑与时间估算（单人）

- M0 准备（~0.5 周）
  - 项目骨架：目录/依赖/配置/日志/模型基类
  - SQLite 初始化与迁移脚本，Run ID 机制
  - 本地测试框架（pytest）与基础 CI（可选）
- M1 基线可用（~1 周）：抓取 → 去重 → 落库 → 邮件（无 LLM）
  - Source Manager + allowlist/config 加载
  - Collector + Parser（最小字段）+ Normalizer
  - Deduplicator + `is_new` 标注
  - Mail Renderer/Sender（日报最小可用）
  - SMTP/配置打通；DoD：固定发 3 条（存量可占位）
- M2 质量与业务（~1 周）：评分/Top1/补位/新增优先/DDL 提醒
  - Scorer（规模/方向/紧迫度）+ Selector（Top1）
  - DDL 解析/提醒；失效/有效期处理
  - 邮件顶部概览与排序规则
- M3 智能增强（~1 周）：LLM 段落 + 翻译 + 模板闸门
  - LLM 适配器、Prompt 与输出校验
  - 纯英文条目中英标题/摘要展示
  - Fallback 文本与显著标注
- M4 稳定与运维（~0.5–1 周）：告警/降级完善 + 白名单自动维护
  - Alert Manager（Run/Crawl/LLM/Content 四类）
  - 降级路径贯通（日报降级/告警分发）
  - allowlist 自动生成与覆盖
  - 稳定性回归与边界测试

## 2. 任务拆解（按模块）

- 配置与模型
  - `config.yaml`/env 加载，默认值与边界校验（Pydantic）
  - 数据模型：Item/Runs/SendLog，DAO/仓储封装
- 抓取与解析
  - HTTP 客户端、超时/重试/速率限制、UA 池
  - 解析器插件化（按站点或类别），离线夹具
- 数据层
  - SQLite schema、唯一约束与索引
  - 迁移/初始化脚本
- 业务层
  - 去重（URL + 可选标题相似）、新增标注
  - 评分（规模/方向/紧迫度/时间）与可配置权重
  - 选取与存量补位、状态流转（active/expired/invalid）
- LLM
  - 适配器与限流；Prompt；输出模板校验器
  - 错误分类与降级 Fallback
- 邮件
  - 模板（HTML + Text）与渲染
  - 主题/概览/排序与中英展示
  - SMTP 发送与错误处理、状态记录
- 告警
  - 触发器（Run/Crawl/LLM/Content）
  - 单独或合并发送（按配置），Run ID/日志定位
- 调度
  - APScheduler（Asia/Singapore）
  - 幂等保护与失败补告

## 3. 依赖与目录

- 依赖建议：httpx/requests、beautifulsoup4/selectolax、dateparser、apscheduler、jinja2、sqlite3/sqlmodel、pydantic、tenacity、pytest。
- 目录建议：
  - `src/config.py`，`src/scheduler.py`，`src/sources/`，`src/collector/`，`src/parser/`，`src/normalizer.py`，`src/dedup.py`，`src/scorer.py`，`src/selector.py`，`src/llm.py`，`src/mailer.py`，`src/renderer.py`，`src/storage/`，`src/alerts.py`，`src/main.py`
  - `configs/config.yaml`，`configs/domains_allowlist.yaml`，`tests/**`，`data/fixtures/**`

## 4. 测试计划

- 单元：解析器、时间/DDL、去重/打分/选取、模板校验器
- 集成：端到端（使用离线夹具），邮件渲染快照
- 回归：空候选、全部过期、LLM 失败、SMTP 失败
- 覆盖 DoD：固定 3 条、DDL 提醒、LLM 模板合规、降级/告警完整

## 5. 风险与缓解

- 源站结构变更 → 解析器插件化 + 失败来源监控 + 快速热修
- LLM 不可用 → Fallback + 明显标注 + 告警，不阻断日报
- SMTP 失败 → 本地落盘 + 下次日报顶部提示，重试与备用端口
- 反爬/配额 → 速率限制/随机 UA/存量补位，严格候选上限

## 6. 前置与交付

- 前置：`SMTP_PASSWORD`、`LLM_API_KEY`、初始关键词与站点白名单；确认服务器时区或显式使用 Asia/Singapore。
- 交付：各里程碑代码 + 配置样例 + 最小运行说明 + 日志/截图；通过 DoD 清单验收。

