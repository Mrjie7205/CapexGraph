# CapexGraph v0.3 执行计划

- 目标版本：`v0.3.0 — Trustworthy live research`
- 计划状态：已完成，作为`v0.3.0`交付记录保留
- 基线版本：`v0.2.0`
- 实施分支：`codex/v0-3-trustworthy-live-research`
- 对应GitHub任务：[#4](https://github.com/Mrjie7205/CapexGraph/issues/4)、
  [#5](https://github.com/Mrjie7205/CapexGraph/issues/5)、
  [#6](https://github.com/Mrjie7205/CapexGraph/issues/6)、
  [#7](https://github.com/Mrjie7205/CapexGraph/issues/7)

本文件是`ROADMAP.md`中v0.3里程碑的执行级拆解。`ROADMAP.md`仍是版本方向和优先级的
最终依据；本文件负责说明实施顺序、交付物、依赖关系和验收方法。
后续版本编号已在2026-07-29重新排序；下文“明确不属于v0.3”的归属以当前`ROADMAP.md`
和`docs/V0_4_PLAN.md`为准。

## 1. 版本目标

v0.3要把CapexGraph从“可以运行冻结案例和手工拼接实时材料”，推进到：

> 用户输入一个非Fixture主题或锚点后，可以在CLI或Cockpit中发现官方信源、采集并审核
> 原文、运行有证据约束的研究流程、提取可追溯的财务事实，并得到一份明确暴露覆盖缺口
> 的研究报告，全程不需要手工编辑JSON。

v0.3的成功标准不是增加更多Agent，也不是让报告语气更像投资结论，而是让真实研究路径
具备以下特征：

- 可重复；
- 可恢复；
- 可审计；
- 不掩盖失败和缺失数据；
- 中高置信度结论只能来自已经审核且哈希未变化的证据；
- 升级不能破坏现有v0.2运行记录和跟踪成绩。

## 2. v0.3完成后的用户路径

```mermaid
flowchart LR
    A["输入主题或锚点"] --> B["创建持久化ResearchRun"]
    B --> C["发现官方信源建议"]
    C --> D["人工选择并采集"]
    D --> E["哈希校验与人工审核"]
    E --> F["执行Theme或Anchor工作流"]
    F --> G["提取并校验财务事实"]
    G --> H["证据审计与研究决策"]
    H --> I["中文/英文报告与候选跟踪"]

    C -. "建议不是证据" .-> D
    D -. "已采集不等于已验证解释" .-> E
    E -. "未审核证据不能支撑中高置信度" .-> F
```

### Web路径

1. 在Cockpit输入主题或锚点并创建运行。
2. 查看官方信源建议、来源类型、域名和发现原因。
3. 选择信源进行采集，查看下载、重定向、重复或安全拦截状态。
4. 阅读已提取文本，批准或驳回证据。
5. 执行或恢复研究流程。
6. 查看证据覆盖、财务事实、关系图、候选、局限性和报告。

### CLI路径

目标命令形态：

```powershell
capexgraph theme "AI数据中心电力" --market CN
capexgraph sources discover <run-id>
capexgraph sources list <run-id>
capexgraph sources capture <run-id> <suggestion-id>
capexgraph evidence review <run-id> <evidence-id>
capexgraph financials extract <run-id>
capexgraph run <run-id> --provider openai
capexgraph report render <run-id>
```

命令名称可在实现时微调，但用户路径不得要求修改`state.json`、`manifest.json`或fixture。

## 3. 实施原则

1. **先保护持久化数据，再改变Schema。** 数据库迁移是所有v0.3持久化改动的前置条件。
2. **发现建议不是证据。** 搜索结果、模型建议和URL候选不能直接进入已采集或已审核状态。
3. **先采集，再推理。** 需要中高置信度的关系必须引用已审核证据。
4. **代码负责事实完整性。** 期间、单位、ticker、哈希、重复检测、公式和引用完整性由确定性
   代码处理。
5. **Agent负责有限判断。** Agent可以解释、比较和提出假设，但不能补造缺失数据或供应商
   关系。
6. **失败必须持久化。** Provider失败、下载失败、审核待办和覆盖不足必须能在CLI、API和
   Cockpit中看到并恢复。
7. **保留无Key路径。** 既有黄金案例以及Alphabet冻结回放继续无需API Key。

## 4. 里程碑与执行顺序

### M0 — 合并验收基线 ✅

目标：将Alphabet验收工作作为v0.3的可复现起点，并避免本地状态与GitHub主分支分叉。

#### 工作内容

- 将`codex/alphabet-q2-acceptance`通过PR合并到`main`；
- 确认Alphabet一手材料、财务指标、中文报告和冻结响应测试进入主分支；
- 固化v0.2数据库样本，作为后续迁移测试输入；
- 记录v0.3开始前的完整测试和构建基线。

#### 退出条件

- GitHub `main`包含Alphabet验收案例；
- 工作树干净，CI通过；
- 已保存不含敏感信息的v0.2数据库fixture；
- `docs/CURRENT_STATUS.md`明确v0.3实施已开始。

### M1 — 数据库版本、迁移与备份恢复 ✅

对应任务：[#4](https://github.com/Mrjie7205/CapexGraph/issues/4)  
优先级：P0  
依赖：M0

目标：在增加信源队列和财务事实表之前，为SQLite建立正式升级契约。

#### 工作内容

- 将目前分散在`runtime/store.py`和`tracking/store.py`的建表责任收口到统一迁移入口；
- 为无版本的v0.2数据库识别一个明确的legacy基线；
- 新增`schema_migrations`表和按顺序执行的迁移注册表；
- 迁移必须具备事务性、幂等性和失败回滚；
- 使用SQLite backup API实现一致性备份；
- 提供状态、升级、备份和恢复命令；
- API和应用启动时只执行安全、可解释的升级策略，不静默破坏旧数据。

#### 目标命令

```powershell
capexgraph db status
capexgraph db backup --output .\backup\capexgraph.db
capexgraph db upgrade
capexgraph db restore .\backup\capexgraph.db
```

#### 主要代码范围

- `src/capexgraph/runtime/migrations/`
- `src/capexgraph/runtime/store.py`
- `src/capexgraph/tracking/store.py`
- `src/capexgraph/cli.py`
- `tests/fixtures/databases/`
- `tests/test_migrations.py`

#### 退出条件

- 现有v0.2数据库升级后，运行、checkpoint、跟踪、快照和触发事件数量不变；
- 全新数据库与升级数据库达到相同最新Schema；
- 重复执行升级不产生副作用；
- 模拟中断后，旧数据库仍可读取；
- 备份、恢复和升级均有自动测试和文档。

### M2 — 官方信源发现与审核队列 ✅

对应任务：[#5](https://github.com/Mrjie7205/CapexGraph/issues/5)  
优先级：P0  
依赖：M1

目标：从“用户必须先知道URL”，升级为“系统提出官方来源候选，用户决定是否采集和审核”。

#### 信任边界

建议引入独立的`SourceSuggestion`对象，而不是把搜索结果伪装成`Evidence`：

```text
suggested → selected → capture_pending → captured
       ↘ dismissed          ↘ capture_failed
```

成功采集后才创建`Evidence(status=captured)`；人工批准后才变为`reviewed`。

这一对象会改变持久化和Provider契约，实施前需要在`docs/DECISIONS.md`新增正式决定。

#### 工作内容

- 定义`SourceDiscoveryProvider`协议；
- 定义`SourceSuggestion`、发现原因、官方性、来源类型、Provider版本和状态；
- v0.3至少实现：
  - SEC/EDGAR公司申报文件发现；
  - 用户提供官方URL的确定性入口；
  - issuer/regulator域名识别与优先级；
- 对规范化URL和内容哈希分别去重；
- 保留现有SSRF、重定向、凭据、大小、Content-Type和保留地址保护；
- 把下载错误、安全拦截、重复来源和待审核状态持久化；
- 增加建议列表、采集、驳回和重试API/CLI。

#### v0.3范围控制

- 不承诺覆盖所有国家交易所和全部A股公告搜索；
- 优先完成一个稳定的SEC官方Provider和手工官方URL路径；
- A股先保证已有交易所/公司披露可以安全进入同一队列，自动发现能力后续扩展；
- 不接入社交媒体、付费新闻库或来历不明的聚合源作为“官方来源”。

#### 主要代码范围

- `src/capexgraph/domain/`
- `src/capexgraph/providers/sources/`
- `src/capexgraph/tools/evidence.py`
- `src/capexgraph/api/app.py`
- `src/capexgraph/cli.py`
- `apps/web/src/`
- `tests/test_source_discovery.py`

#### 退出条件

- 搜索建议永远不会自动获得`captured`或`reviewed`状态；
- 每次采集记录URL、最终URL、时间、哈希、Content-Type、本地文件和结果状态；
- 重复URL和重复内容能够解释性去重；
- 私网、回环、链路本地、保留地址、带凭据URL和不安全重定向继续被阻止；
- 冻结响应测试覆盖成功、重复、重定向、超限、失败和安全拦截；
- Cockpit可以查看、采集、驳回和重试建议。

### M3 — 非Fixture实时Theme/Anchor闭环 ✅

对应任务：[#6](https://github.com/Mrjie7205/CapexGraph/issues/6)  
优先级：P0  
依赖：M1、M2

目标：用户无需编辑JSON，即可从输入主题或锚点走到有证据约束的最终报告。

#### 工作内容

- 在研究执行前增加证据覆盖preflight；
- 把已采集和已审核证据明确注入Theme/Anchor上下文；
- 保持现有七阶段checkpoint兼容，避免为了加信源流程而破坏v0.2运行；
- 在manifest中记录：
  - 模型Provider、模型和版本；
  - 信源发现Provider和版本；
  - 数据Provider和版本；
  - `as_of_date`；
  - 证据策略；
  - 覆盖状态和待审核数量；
- 未审核或模型单独提出的关系只能保持低置信度；
- Provider、来源或模型失败必须checkpoint并支持resume；
- CLI、API和Cockpit提供同一条用户路径；
- 报告明确显示事实、推断、未验证假设和覆盖缺口。

#### 执行策略

- 不要求所有运行必须审核全部建议后才能继续；
- 允许用户在证据不足时生成低置信度、`needs_review`报告；
- 如果用户选择“严格证据模式”，则在中高置信度所需证据未审核时阻塞相应阶段；
- 原始运行保持不可变，恢复和重评不得偷偷覆盖既有checkpoint。

#### 贯穿验收案例

1. **Alphabet Q2 2026**
   - 官方财报和管理层发言；
   - GOOGL身份与行情；
   - 财务指标；
   - 不得虚构具名供应商；
   - 冻结网络响应可重复运行。
2. **A股回归案例**
   - 继续运行硅片和兆易创新黄金案例；
   - 验证A股ticker、中文报告和旧fixture不因实时路径而退化。

#### 主要代码范围

- `src/capexgraph/research/theme.py`
- `src/capexgraph/research/anchor.py`
- `src/capexgraph/runtime/executor.py`
- `src/capexgraph/providers/`
- `src/capexgraph/api/app.py`
- `src/capexgraph/cli.py`
- `apps/web/src/`
- `tests/test_live_vertical.py`

#### 退出条件

- 新用户可以在CLI和Cockpit完成一个非Fixture运行，不修改JSON；
- 运行中断或Provider失败后可以从最后checkpoint恢复；
- 未审核证据无法支撑中高置信度；
- 报告展示Provider、覆盖状态、待审核项和局限性；
- 冻结响应集成测试可以重复完整路径；
- 两个旧黄金案例继续无需Key并通过。

### M4 — 财报事实自动结构化与推理上下文 ✅

对应任务：[#7](https://github.com/Mrjie7205/CapexGraph/issues/7)  
优先级：P1  
依赖：M1、M2、M3

目标：从官方申报文件自动生成可追溯财务事实，并让Theme/Anchor真正使用这些事实。

#### 数据契约

现有`FinancialMetric`需要演进为能够表达以下字段的版本化事实：

- canonical company/ticker；
- statement与标准化metric；
- 原始XBRL concept；
- period start/end、fiscal year、fiscal period；
- form、filed date、accession；
- value与unit；
- `reported`、`derived`、`restated`或`missing`；
- source evidence ID和文档定位；
- 对derived值保存公式与输入fact ID。

#### 工作内容

- 定义`FilingFactsProvider`协议；
- 首个实现使用SEC inline XBRL/XBRL实例或官方Company Facts数据；
- 原始申报/XBRL响应必须先进入证据采集与哈希流程；
- 期间、单位、公司身份和statement归属由代码校验；
- restatement以新版本事实保存，不静默覆盖旧值；
- 缺失值明确记录，不使用0代替；
- 生成Theme/Anchor可消费的比较和趋势artifact；
- 把相关事实注入Agent上下文，并限制上下文大小；
- 在HTML报告和Cockpit中显示数值、期间、单位、事实类型和来源定位。

#### v0.3最小指标范围

- Income statement：营收、营业利润、净利润；
- Cash flow：经营现金流、资本开支、自由现金流；
- Balance sheet：现金、债务、物业与设备；
- 主题相关补充指标：Cloud收入、积压订单等仍可来自公司披露，但必须使用单独metric
  namespace并保留来源。

#### 退出条件

- 每一项存储事实都能追溯到同一运行中的已采集/已审核官方材料；
- 期间或单位冲突确定性失败；
- restatement不覆盖历史事实；
- 三张报表、缺失数据和重复事实都有冻结案例；
- Theme/Anchor提示上下文实际包含相关财务事实；
- 报告显示来源定位，而不只显示一个证据ID。

### M5 — Cockpit收口、端到端验收与v0.3发布 ✅

优先级：P0收口  
依赖：M1至M4

目标：把前述能力变成非开发者可以使用的完整产品路径，并正式发布v0.3.0。

#### Cockpit交付

- 官方信源建议和审核队列；
- 下载失败、重复、安全拦截和Provider失败状态；
- 证据覆盖摘要；
- 财务事实表、期间、单位和来源定位；
- 执行、暂停、恢复和重新尝试；
- 报告中的事实/推断/假设区分；
- 空状态、部分完成和`needs_review`解释。

为控制范围，v0.3只拆分实现新功能所必需的`App.tsx`模块；全面前端重构、搜索库和多运行
对比仍留在v0.6。

#### 发布工作

- 同步更新Python、Web和包内版本到`0.3.0`；
- 更新README、CURRENT_STATUS、CHANGELOG、工作流文档和升级指南；
- 构建并检查wheel；
- 执行新数据库和v0.2升级数据库两套smoke test；
- GitHub CI覆盖迁移、冻结网络响应、完整Python测试和Web生产构建；
- 创建`v0.3.0` release，仅在所有验收门槛通过后标记完成。

#### 退出条件

- 非开发用户可以只通过Cockpit完成核心实时研究路径；
- CLI、API和Web针对同一运行返回一致状态；
- 旧v0.2数据库原地升级后仍可读取和继续跟踪；
- Alphabet实时案例和冻结回放均通过；
- A股黄金案例不回归；
- 文档明确哪些来源和市场仍不受支持；
- Catalyst、自动调度和团队权限没有被误写成已发布。

## 5. PR拆分建议

| 顺序 | PR | 对应任务 | 合并门槛 |
|---|---|---|---|
| 0 | 合并Alphabet验收基线 | M0 | 当前测试、Web构建、证据案例 |
| 1 | SQLite迁移、备份恢复 | #4 | legacy/fresh/interrupted/restore测试 |
| 2 | SourceSuggestion与发现Provider | #5 | Provider契约、去重和SSRF测试 |
| 3 | 审核队列API、CLI和Cockpit | #5 | 完整建议→采集→审核路径 |
| 4 | 非Fixture Theme/Anchor闭环 | #6 | 冻结网络端到端测试 |
| 5 | Filing facts与工作流上下文 | #7 | 三张报表、期间、单位和restatement测试 |
| 6 | Cockpit收口与v0.3.0发布 | 跨任务 | 新装、升级、Web和wheel验收 |

每个PR必须可以独立回滚，不把数据库迁移、Provider契约和大规模前端重构塞进同一个提交。

## 6. 测试矩阵

| 层级 | 必测场景 |
|---|---|
| 数据库 | legacy升级、全新安装、重复升级、中断回滚、备份恢复、原有scorecard保留 |
| 信源发现 | 官方来源、空结果、Provider失败、重复URL、重复内容、排序与原因 |
| 安全采集 | 私网、回环、链路本地、保留地址、凭据URL、恶意重定向、超大文件、错误Content-Type |
| 证据审核 | capture后哈希、篡改检测、批准、驳回、重新采集、旧审核失效 |
| 置信度 | 模型单独提出、已采集未审核、已审核、混合证据、缺少evidence ID |
| 财务事实 | 三张报表、单位冲突、期间冲突、重复、restatement、missing、derived公式 |
| 工作流 | Theme、Anchor、失败checkpoint、resume、strict/partial evidence模式 |
| API/CLI/Web | 同一运行的状态一致性、错误可见性、无JSON编辑路径 |
| 回归 | A股硅片、兆易创新、Alphabet冻结回放、中文报告、tracking |
| 发布 | Python支持版本、Web production build、wheel内容、新装与升级smoke |

## 7. v0.3 Definition of Done

以下条件必须全部满足：

- [x] `main`包含Alphabet验收基线；
- [x] SQLite具备正式版本、迁移、备份和恢复；
- [x] 至少一个官方信源Provider可用；
- [x] 发现建议与Evidence在状态和Schema上明确分离；
- [x] CLI和Cockpit均能完成建议、采集、审核和研究执行；
- [x] 一个非Fixture Theme或Anchor运行无需编辑JSON即可完成；
- [x] 未审核证据不能支撑中高置信度；
- [x] 官方财报事实能够自动提取、校验、保存和追溯；
- [x] Theme/Anchor实际消费相关财务事实；
- [x] 报告明确展示Provider、证据覆盖、财务来源和局限性；
- [x] v0.2数据库升级无数据损失；
- [x] 旧黄金案例继续无Key运行；
- [x] Python测试、Ruff、Web构建、wheel和CI全部通过；
- [x] 版本、CHANGELOG、升级文档和CURRENT_STATUS同步到`0.3.0`。

## 8. 明确不属于v0.3

- 定时任务、无人值守行情快照和自动重评：v0.4；
- 跨市场公告、财报和事件日历：v0.5；
- 一致预期修正：v0.6；
- Catalyst Scan、跨运行图谱记忆和证据复用：v0.7；
- 完整Cockpit重构、搜索库和运行对比：v0.8；
- 云端多用户、组织权限和协作审核：v0.8以后；
- 券商交易、自动组合管理和下单：长期非目标；
- 将私有Serenity数据或代码作为CapexGraph运行时依赖：禁止。

## 9. 主要风险与控制

| 风险 | 控制方式 |
|---|---|
| 数据库升级损坏历史运行 | 迁移前备份、事务、legacy fixture、恢复测试 |
| 搜索建议被误当成事实 | 独立SourceSuggestion对象，采集和审核后才生成Evidence |
| SSRF兼容性修复削弱安全 | 默认规则不放松，环境代理兼容采用显式配置和测试 |
| 模型引用不存在或未审核来源 | Schema引用校验、置信度门禁、edge audit |
| XBRL taxonomy和单位复杂 | 首版限制指标范围，保留原始concept与unit，冲突直接失败 |
| 前端范围膨胀 | 只拆新功能所需模块，产品化重构留给当前路线图中的v0.8 |
| 为赶版本提前实现Catalyst | 测试和文档继续强制“Catalyst仅为scaffold” |
| 本地能力未进入公库 | M0先合并验收基线，后续每阶段通过PR和CI交付 |

## 10. 实施记录

M0至M5按既定依赖顺序完成。下一次开发Session应从`docs/V0_4_PLAN.md`中的M0开始，
不应重复实现本计划，也不应因为`RunMode.CATALYST`已经存在就提前启动v0.7。
