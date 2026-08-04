import type { ElementType, ReactNode } from "react";

interface BilingualTextProps {
  zh: ReactNode;
  en?: ReactNode;
  as?: ElementType;
  className?: string;
  compact?: boolean;
  align?: "left" | "center" | "right";
}

const UI_VALUE_LABELS: Record<string, string> = {
  created: "已创建",
  running: "运行中",
  needs_review: "待审核",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
  pending: "待执行",
  blocked: "受阻",
  theme: "主题扫描",
  anchor: "锚点扫描",
  proposed: "待采集",
  captured: "待审核",
  agent_reviewed: "Agent 已审核",
  reviewed: "人工已审核",
  rejected: "已拒绝",
  empty: "暂无证据",
  suggestions_only: "仅有候选来源",
  partial: "部分就绪",
  strict: "严格模式",
  suggested: "待处理",
  selected: "已选择",
  source_suggested: "来源待捕获",
  capture_pending: "正在捕获",
  dismissed: "已忽略",
  capture_failed: "捕获失败",
  duplicate: "重复来源",
  regulator: "监管机构",
  issuer: "公司官方",
  other: "其他",
  accept: "纳入研究",
  watch: "重点观察",
  downgrade: "降低置信",
  high: "高",
  medium: "中",
  low: "低",
  research: "研究中",
  validated: "已验证",
  triggered: "已触发",
  invalidated: "已失效",
  archived: "已归档",
  active: "运行中",
  degraded: "服务降级",
  exhausted: "额度暂停",
  not_configured: "等待配置",
  off: "已关闭",
  replay: "样例回放",
  standby: "待命",
  connecting: "连接中",
  connected: "已连接",
  reconnecting: "正在重连",
  single_channel: "单通道",
  matched: "双通道匹配",
  divergent: "通道有差异",
  signal_only: "仅为线索",
  official_source_pending: "等待官方补证",
  evidence_linked: "证据已链接",
  flash: "快讯",
  calendar: "财经日历",
  quote: "行情",
  news: "资讯",
  mcp: "MCP 轮询",
  websocket: "实时推送",
  fixture: "冻结样例",
  rules_only: "仅规则分析",
  skipped: "已跳过",
  positive: "正向",
  negative: "负向",
  neutral: "中性",
  mixed: "影响混合",
  verify: "补证核验",
  monitor: "继续监测",
  mute: "静默",
  income_statement: "利润表",
  cash_flow: "现金流量表",
  balance_sheet: "资产负债表",
  supplemental: "补充披露",
  reported: "已披露",
  derived: "系统推导",
  restated: "重述数据",
  missing: "未披露",
  ready: "已连接",
  reachable: "可用",
  not_installed: "未安装",
  login_required: "等待登录",
  live_probe_pending: "已保存，待实流验证",
  not_checked: "等待检测",
  wrong_auth_mode: "不是 ChatGPT 登录",
  unreachable: "连接失败",
  chatgpt_subscription: "ChatGPT 订阅",
  api_key: "API 按量计费",
  none: "无需计费",
  local: "本机执行",
  metadata_only: "仅保留元数据",
  provider_usage_not_exposed: "供应商未返回用量",
  not_applicable: "不适用",
  pass: "通过",
  fail: "未通过",
  "define theme boundary": "定义主题边界",
  "build player census": "建立参与者清单",
  "map grounded supply chain": "绘制有证据的产业链",
  "audit evidence": "审核证据",
  "score bottlenecks": "评估瓶颈",
  "bull / bear review": "多空复核",
  "issue structured verdict": "形成结构化结论",
  "resolve anchor identity": "确认锚点身份",
  "explain anchor repricing": "解释锚点重估",
  "map 360° neighbours": "绘制全景邻居",
  "audit relationship evidence": "审核关系证据",
  "compare neighbour fundamentals": "比较邻居基本面",
  "define catalyst and timeline": "定义催化与时间线",
  "map transmission paths": "绘制传导路径",
  "issue scenario verdict": "形成情景结论",
  "theme analyst": "主题分析员",
  "universe analyst": "标的池分析员",
  "chain mapper": "产业链分析员",
  "evidence auditor": "证据审核员",
  "bottleneck analyst": "瓶颈分析员",
  "research team": "研究团队",
  "research manager": "研究经理",
  "anchor analyst": "锚点分析员",
  "market analyst": "市场分析员",
  "financial analyst": "财务分析员",
  "catalyst analyst": "催化分析员",
  "awaiting execution": "等待执行",
  "step completed": "步骤已完成",
  "step execution failed": "步骤执行失败",
  filing: "监管申报",
  company_disclosure: "公司披露",
  government: "政府披露",
  transcript: "会议文字稿",
  market_data: "市场数据",
  industry_inference: "行业推断",
  ephemeral: "临时保留",
  licensed_archive: "授权归档",
  unread: "未读",
  read: "已读",
  complete: "覆盖完整",
  signal: "信号",
  observation: "观测",
  analysis: "分析",
  user: "用户",
  run: "研究任务",
  verification_task: "核验任务",
  evidence: "证据",
  evidence_link: "证据链接",
  "signal.verification_state_changed": "信号核验状态变更",
  "verification_task.created": "已创建核验任务",
  "verification_task.source_suggested": "已登记官方来源候选",
  "verification_task.capture_started": "已开始捕获官方来源",
  "verification_task.capture_failed": "官方来源捕获失败",
  "verification_task.source_captured": "已捕获官方来源",
  "verification_task.evidence_rejected": "已拒绝捕获材料",
  "verification_task.evidence_linked": "已链接审核证据",
  "run.linked_reevaluation_created": "已创建链接复评",
  "run.context_attached": "已挂接研究上下文",
  "signal.version": "信号版本",
  "observation.received": "收到观测",
  "analysis.completed": "分析完成",
  "user.action": "用户操作",
};

export function BilingualText({
  zh,
  en,
  as: Component = "span",
  className = "",
  compact = false,
  align = "left",
}: BilingualTextProps) {
  const classes = [
    "bilingual-text",
    compact ? "compact" : "",
    `align-${align}`,
    className,
  ].filter(Boolean).join(" ");

  return (
    <Component className={classes}>
      <span className="bilingual-primary">{zh}</span>
      {en !== undefined && en !== null && en !== "" && (
        <small className="bilingual-secondary">{en}</small>
      )}
    </Component>
  );
}

export function humanizeUiValue(value: string): string {
  return value.replaceAll("_", " ").trim();
}

export function translateUiValue(value?: string | null, fallback = "—"): string {
  if (!value) return fallback;
  return UI_VALUE_LABELS[value.toLocaleLowerCase()] ?? humanizeUiValue(value);
}

interface LocalizedValueProps {
  value?: string | null;
  fallbackZh?: string;
  fallbackEn?: string;
  className?: string;
  compact?: boolean;
}

export function LocalizedValue({
  value,
  fallbackZh = "暂无",
  fallbackEn = "none",
  className,
  compact = true,
}: LocalizedValueProps) {
  const raw = value ? humanizeUiValue(value) : fallbackEn;
  return (
    <BilingualText
      zh={translateUiValue(value, fallbackZh)}
      en={raw}
      className={className}
      compact={compact}
    />
  );
}
