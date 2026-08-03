# CapexGraph v0.5 执行计划

- 目标版本：`v0.5.0 — Cross-market disclosures, filing facts, and event calendar`
- 计划状态：M0-M5技术交付完成并并入`v0.5.1`
- 基线：v0.4 跨市场行情、点时主题与主线监控
- 完成分支：`codex/pre-v0-6-completion`
- 最后更新：2026-08-03

> 完成说明：SEC、CNINFO、沪深北交易所、OpenDART和KIND官方发现路径，保守事件映射，
> 点时版本，SEC历史分片，OpenDART财务事实，审核后公告事实候选，事件驱动人工重评
> 提案和Cockpit入口均已实现。Provider授权、实时可用性和缺失字段继续按能力矩阵显式
> 展示；标题或聚合消息不会被当成已审核事实。

本计划把官方披露、财报事实和事件日历变成可追溯、可做点时查询的系统对象。开发期曾在
v0.4其余能力之前先交付SEC纵切；截至2026-08-03，v0.4依赖和v0.5中韩纵切均已补齐。
官方事件仍只能进入确定性监控和人工门控的重评提案，不能绕过Evidence审核或自动产生
模型费用。

用户同时批准了`v0.5.1`实时事件网关扩展：金十MCP轮询与开放平台WebSocket是两个
同等优先级的正式信息通道。开发共用契约并行推进，前期先让MCP进入真实运行；获得
Secret-Key后WebSocket加入持续采集，但不替代或降级MCP。冻结事件流继续保留无Key路径。
该扩展的完整产品、架构、前端、操作和验收计划见
[`V0_5_1_PLAN.html`](V0_5_1_PLAN.html)。金十消息属于市场信号和研究线索，不是官方
Evidence；v0.5.1可以提出链接重评。v0.4主线引擎随后独立完成，其默认政策仍保持实验状态。

## 1. 用户路径

```text
创建研究运行
  → 从官方监管源发现披露
  → 保存SourceSuggestion
  → 映射为类型化事件版本
  → 捕获原文并形成Evidence
  → 追加带Evidence链接的新事件版本
  → 按当前或历史观察时间查询
  → 后续触发监控与链接重评
```

首条可运行路径：

```powershell
capexgraph events sync <run-id> --identifier GOOGL --form 10-Q --form 8-K
capexgraph events list <run-id>
capexgraph sources capture <run-id> <suggestion-id>
capexgraph events list <run-id> --history
capexgraph events list <run-id> --as-of 2026-07-23
```

发现阶段只证明SEC元数据中存在一份正式提交；捕获阶段才形成有字节和哈希的Evidence。
事件映射不会因为8-K中“可能包含业绩”就猜测为业绩事件：10-K、10-Q、20-F和40-F映射为
`financial_report`，其他表单先保守映射为`regulatory_filing`。

## 2. 时间和版本语义

每个`CorporateEventVersion`至少保存：

```text
event_key
version
version_hash
entity_id
ticker
market
event_type
status
announced_date
expected_date
effective_date
occurred_date
cancelled_date
known_at
observed_at
source_suggestion_id
evidence_id
source_url
source_hash
provider
provider_version
external_id
revision_reason
```

- `known_at`：官方来源何时公开该信息；SEC优先使用`acceptanceDateTime`。
- `observed_at`：CapexGraph何时实际发现或捕获它。
- `announced_date`：公告或申报日期。
- `expected_date`：计划发生但尚未发生的日期。
- `effective_date`：规则、权益或变更生效日期。
- `occurred_date`：事件实际发生日期。
- `cancelled_date`：取消日期。

点时查询默认按`observed_at`限制，因为后补抓取一份旧公告不能冒充系统在过去已经知道。
`known_at`仍单独保存，用于区分“当时已公开”与“当时本系统已经采集”。

同一`event_key`的更新只能追加新版本：

- 重复抓取完全相同的语义结果保持幂等；
- 从Suggestion升级为捕获Evidence时追加版本；
- 后续日期修订、取消或状态变化追加版本；
- 不允许覆盖或删除旧版本；
- `events.json`是可移植派生物，SQLite是版本历史的查询系统。

## 3. Provider范围

| 市场 | 官方来源 | v0.5路径 | 当前状态 |
|---|---|---|---|
| US | SEC EDGAR Submissions、Company Facts、发行人IR | 提交事件、事实、原文证据 | 已完成；真实访问需识别型User-Agent |
| CN | CNINFO、上交所、深交所、北交所 | 公告发现、PDF捕获、事件/财务分类 | 已完成冻结纵切与能力声明 |
| KR | OpenDART、KIND/KRX | 公告发现、DART taxonomy、事件 | 已完成；OpenDART真实访问需Key |
| 通用 | 用户审核的官方URL/文件 | 本地导入并保留来源身份 | 已完成受控手工路径 |

SEC首条路径使用官方
[EDGAR Submissions API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)；
该接口无需API Key，但必须遵守SEC自动访问和User-Agent要求。

聚合数据商可以加速发现，但不能取代官方Evidence。未覆盖市场必须显示`unsupported`或
`partial`，不能由模型文字静默填补。

## 4. 实施顺序

### M0 — 事件契约、不可变版本与迁移

优先级：P0

交付：

- `CorporateEventType`、`CorporateEventStatus`、`CorporateEventVersion`；
- `known_at`与`observed_at`双时间；
- migration 5与`corporate_event_versions`；
- 幂等语义哈希、追加版本、当前视图和点时查询；
- `events.json`与run manifest摘要。

退出条件：

- 新旧数据库升级幂等；
- 旧run、checkpoint、tracking、facts和market bars不变；
- 时间字段必须带时区并统一到UTC；
- 相同语义重复同步不产生版本；
- 来源或状态变化只追加、不覆盖。

### M1 — SEC官方披露事件纵切

优先级：P0

交付：

- SEC Submissions元数据增加`acceptanceDateTime`、items和XBRL标志；
- accession作为稳定外部身份；
- 10-K/10-Q/20-F/40-F保守映射为财务报告事件；
- 其他表单映射为监管申报事件；
- Suggestion发现与Evidence捕获分层；
- 捕获后自动追加Evidence链接版本；
- CLI/API发现、刷新、列表、历史和`as_of`查询。

退出条件：

- 冻结SEC响应端到端通过；
- 重复发现幂等；
- 捕获前后形成两个不可变版本；
- 历史查询只能看到截止观察时刻的版本；
- 真实SEC smoke不进入默认CI。

### M2 — 中国官方公告

优先级：P0

交付：

- CNINFO和沪深北交易所Provider能力声明；
- 代码、公司、公告类型、发布日期、报告期和原文URL规范化；
- PDF/HTML原文进入现有SSRF、哈希与审核链路；
- 定期报告、业绩预告、分红、增发、解禁、停复牌和产能项目等保守映射；
- 至少一个A股冻结官方案例。

### M3 — 韩国官方公告

优先级：P0

交付：

- OpenDART公司身份、公告列表、文档和财务事实；
- KIND/KRX事件补充与授权边界；
- 韩文公告类型到内部taxonomy的显式映射；
- 至少一个韩国冻结官方案例。

### M4 — 财务事实与事件抽取

优先级：P1

交付：

- CN/US/KR报告期、单位、币种、累计/单季口径规范化；
- 指引、分红、拆股、业绩、CapEx/产能里程碑等证据链接事件；
- 内容抽取只产生候选，确定事件必须通过结构、来源和日期校验；
- 同一披露的事实与事件共享Evidence，不复制来源身份。

### M5 — 监控、重评、Cockpit与发布

优先级：P1

交付：

- 新事件进入监控触发器和链接重评提案；
- 默认不自动产生模型费用；
- Cockpit展示当前事件、历史版本、来源状态、时间字段和覆盖缺口；
- CN/US/KR冻结端到端、wheel、Web、升级和发布验证。

## 5. 完成边界与保留限制

已进入代码：

- SEC披露事件契约与mapper；
- append-only事件store和migration 5；
- Suggestion到事件、Evidence捕获到新版本；
- 点时查询、CLI、API和`events.json`。

本纵切已通过78项Python全量测试、Ruff、Web生产构建和隔离wheel内容校验。真实SEC访问
仍要求操作者在`.env`中提供含真实联系地址的`CAPEXGRAPH_SEC_USER_AGENT`；项目不会生成
虚假地址或绕过403。

已在最终纵切补齐：

- SEC历史分片按请求上限惰性回补；
- CNINFO、沪深北、OpenDART和KIND能力声明、冻结响应和规范化；
- OpenDART官方账户的保守财务事实归一化；
- 经审核Evidence生成公告事实候选，再由人工接受为不可变FinancialFact；
- 新官方事件只提出主线重评候选，不自动启动模型或修改旧运行；
- Cockpit官方来源选择、事件时间线、Evidence审核和财务候选决策。

保留限制：发行人IR日历仍通过通用人工/发行人官方URL路径处理；没有结构化字段时，
系统不会仅凭8-K或公告标题猜测具体经营数据。完整券商一致预期属于v0.6。

## 6. 测试矩阵

| 层级 | 必测 |
|---|---|
| 契约 | 时区、日期要求、生命周期约束、来源要求 |
| SEC | CIK/ticker、accession、acceptance时间、表单保守分类 |
| 版本 | 幂等、Evidence升级、修订、取消、不可变历史 |
| 点时 | `observed_at`截止、未来版本不可见 |
| 存储 | 新装、v0.2/v0.3/v0.4升级、外键、索引 |
| 证据 | Suggestion不是Evidence、捕获哈希链接、审核不被伪造 |
| API/CLI | 同一当前视图与历史视图 |
| 回归 | 既有黄金案例、market、facts、tracking和Web |
| 安全 | 官方域、SSRF、下载边界、User-Agent、无凭证泄漏 |

## 7. Definition of Done

- [x] CN、US、KR各至少一个冻结官方纵切；
- [x] 所有事件都有规范实体、来源、观察时间、有效/预期日期和状态；
- [x] 更新只追加版本，历史查询无未来函数；
- [x] 财务事实和事件共享Evidence链；
- [x] 缺少覆盖时明确显示，不由模型补写；
- [x] 新事件可进入监控与链接重评提案；
- [x] Cockpit能解释来源、时间、状态和版本；
- [x] no-key路径、Ruff、全量测试、Web、wheel和升级纳入发布门禁。

## 8. 明确不属于v0.5

- 券商一致预期与历史修正：v0.6；
- Catalyst Scan和跨运行图记忆：v0.7；
- 自动下单或组合管理；
- 把公告标题或8-K表单本身当成具体经营结论；
- 用聚合商数据替代官方原文证据。
