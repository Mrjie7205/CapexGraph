# Alphabet 2026年Q2实时验收案例

本案例使用刚发布的非Fixture公司披露，检验CapexGraph的真实工作路径。

首次实时基线、已发现缺口和研究结论见`ACCEPTANCE_REPORT.md`。

研究主题：

```text
Alphabet 2026年Q2 AI资本开支传导
```

证据包只包含Alphabet和Google一手材料。标准化财务指标均由这些材料转录，并保留
证据ID。案例主要检验：

- 公共PDF/HTML采集、哈希和审核；
- 带期间、单位与来源的财务指标；
- 主营经营表现与巨额股权证券收益的分离；
- Theme Scan能否从AI基础设施需求映射到瓶颈层，同时避免虚构具名供应商；
- 模型配置缺失和Catalyst Scan尚未实现时，系统能否如实暴露失败状态。

创建实时运行：

```powershell
$subject = "Alphabet 2026年Q2 AI资本开支传导"
capexgraph theme $subject --market US --as-of 2026-07-22
capexgraph evidence pack <run-id> .\cases\alphabet_q2_2026\evidence_pack.json
capexgraph evidence review <run-id> alphabet-q2-2026-earnings-release
capexgraph evidence review <run-id> alphabet-q2-2026-ceo-remarks
capexgraph financials import <run-id> .\cases\alphabet_q2_2026\financial_metrics.csv
```

运行无需API Key的中文确定性回放：

```powershell
capexgraph demo-alphabet-q2
```

Theme Scan的非Fixture执行仍需要明确的结构化输出Provider。当前OpenAI Provider要求
配置`OPENAI_API_KEY`和`CAPEXGRAPH_MODEL`，并且不会自主发现信源。在没有完成这些
条件时，不得把该案例描述成模型自主生成的实时报告。
