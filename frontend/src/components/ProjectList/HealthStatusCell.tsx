// 健康度评级展示组件（8-2 规则灯，2026-11-06 用户裁定）：
// - HealthStatusCell：列表单元格（色点 + 主因短语，一目了然；搁置/无评级显示「—」）
// - HealthFactList：事实清单（详情页：档位徽章 + 事实行 + 考核防火墙文案）
// 口径唯一来源 backend health_score.py——前端零计算只展示（批次 §2 决策 4）。
import type { HealthStatus, HealthFact } from '../../types'

// 档位 → 展示色（neu.css 1b 文字级语义 token 值直取：小字过线为准、图标同值；原值 → 各行出处注释）
export const BAND_COLOR: Record<string, string> = {
  green: 'var(--neu-success)', // 原 #52c41a
  yellow: 'var(--neu-warning)', // 原 #faad14
  red: 'var(--neu-danger)', // 原 #ff4d4f
  gray: 'var(--text-tertiary)', // 原 #8c8c8c（未评估中性——1b 无灰语义档，取 index.css 弱文字 token）
}

// 档位 → 徽章淡染底（原 = BAND_COLOR + '22' 十六进制 alpha 拼接，token 化后 var() 不可拼接——
// 语义三档改 1b 图标块淡染底 token 值直取；灰档/兜底 = 同 13% 淡染从 --text-tertiary 派生（原 '22' = 13%））
const BAND_BG: Record<string, string> = {
  green: 'var(--neu-success-bg)',
  yellow: 'var(--neu-warning-bg)',
  red: 'var(--neu-danger-bg)',
  gray: 'color-mix(in srgb, var(--text-tertiary) 13%, transparent)',
}

// 档位 → 徽章词（详情页/弹窗分板块用）
export const BAND_LABEL: Record<string, string> = {
  green: '正常',
  yellow: '关注',
  red: '风险',
  gray: '未评估',
}

// 搁置/专项（health=null）→ 「—」；有评级 → 色点 + 主因短语（无 hover 依赖，扫一眼即懂）
export function HealthStatusCell({ health }: { health?: HealthStatus | null }) {
  if (!health) return <span style={{ color: 'var(--text-tertiary)' }}>—</span>
  return (
    <span style={{ whiteSpace: 'nowrap' }}>
      <span
        style={{
          display: 'inline-block',
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: BAND_COLOR[health.band] || 'var(--text-tertiary)',
          marginRight: 6,
          verticalAlign: 'middle',
        }}
      />
      <span style={{ fontSize: 12 }}>{health.reason}</span>
    </span>
  )
}

// 事实清单（详情页）：档位徽章 + 事实行（带对象名）+ 固定文案
export function HealthFactList({ health }: { health: HealthStatus }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
      <span
        style={{
          padding: '2px 10px',
          borderRadius: 6,
          fontSize: 13,
          fontWeight: 600,
          whiteSpace: 'nowrap',
          background: BAND_BG[health.band] || BAND_BG.gray,
          color: BAND_COLOR[health.band] || 'var(--text-tertiary)',
        }}
      >
        {health.band === 'green' ? '🟢' : health.band === 'yellow' ? '🟡' : health.band === 'red' ? '🔴' : '⚪'}{' '}
        {BAND_LABEL[health.band] || health.band}
      </span>
      {health.facts.map((f: HealthFact, i: number) => (
        <span key={f.kind + f.detail + i} style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
          {f.detail}
        </span>
      ))}
      <span style={{ fontSize: 11, color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
        {health.disclaimer || '本评级为项目状态参考，不构成绩效考核'}
      </span>
    </div>
  )
}
