import { useEffect, useState } from 'react'
import { Card, Segmented, Space, Tag } from 'antd'
import ResourceView from '../components/Resource/ResourceView'
import HeatmapView from '../components/Resource/HeatmapView'
import PhaseEditor from '../components/PhaseEditor/PhaseEditor'

type ViewTab = 'heatmap' | 'gantt'

/**
 * 资源负载页面：双 Tab（热力图 | 甘特，默认热力图，RESOURCE_HEATMAP §3.1）。
 *
 * - 热力图：人员 × 时间负载矩阵，谁忙/谁闲/谁撞车一眼可读（只读）
 * - 甘特：每人一行多行甘特（只读）；冲突消除唯一入口——点击黄色冲突条
 *   消除该甘特条（该阶段不计入该人员并行计算，CONFLICT_MODEL_V2 v2.1）
 * - 冲突报告与消除记录在「审核中心 → 资源冲突」（用户 2026-08-28 决策 ④）
 * 所有阶段调整请在项目管理页面操作。
 */
export default function ResourcePage() {
  const [tab, setTab] = useState<ViewTab>('heatmap')
  const [scale, setScale] = useState<'day' | 'week' | 'month'>('week')
  const [editingPhase, setEditingPhase] = useState<number | null>(null)

  // 跨视图冲突同步（用户 2026-08-28 决策 ③）：甘特消除后 bump conflictVersion，
  // 热力图随 prop 变化自动重载；同时广播 'conflict-changed' 事件供其他页面（Dashboard
  // 抽屉/审核中心）联动。
  const [conflictVersion, setConflictVersion] = useState(0)
  const bumpConflict = () => {
    setConflictVersion((v) => v + 1)
    window.dispatchEvent(new Event('conflict-changed'))
  }

  useEffect(() => {
    // 其他页面（审核中心撤销消除）后同步刷新本页——监听器不 dispatch，避免与 bumpConflict 互发成环
    const onExternalConflictChange = () => setConflictVersion((v) => v + 1)
    window.addEventListener('conflict-changed', onExternalConflictChange)
    return () => window.removeEventListener('conflict-changed', onExternalConflictChange)
  }, [])

  return (
    <Card
      className="pm-no-blur"
      title={
        <Space>
          <span>资源负载视图</span>
          {tab === 'heatmap' ? (
            <Tag color="blue">人员 × 时间负载矩阵 · 谁忙/谁闲/谁撞车</Tag>
          ) : (
            <Tag color="blue">每人一行 · 显示所有参与项目</Tag>
          )}
        </Space>
      }
      extra={
        tab === 'heatmap' ? (
          <Segmented
            options={[
              { label: '热力图', value: 'heatmap' },
              { label: '甘特', value: 'gantt' },
            ]}
            value={tab}
            onChange={(val) => setTab(val as ViewTab)}
          />
        ) : (
          <Space>
            <Segmented
              options={[
                { label: '热力图', value: 'heatmap' },
                { label: '甘特', value: 'gantt' },
              ]}
              value={tab}
              onChange={(val) => setTab(val as ViewTab)}
            />
            <Segmented
              options={[
                { label: '日', value: 'day' },
                { label: '周', value: 'week' },
                { label: '月', value: 'month' },
              ]}
              value={scale}
              onChange={(val) => setScale(val as 'day' | 'week' | 'month')}
            />
          </Space>
        )
      }
    >
      {tab === 'heatmap' ? (
        <HeatmapView conflictVersion={conflictVersion} />
      ) : (
        <>
          <div style={{ marginBottom: 8 }}>
            <Space size="middle" wrap>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>图例：</span>
              {[
                { color: 'var(--gantt-done)', label: '已完成' },
                { color: 'var(--gantt-active)', label: '进行中' },
                { color: 'var(--gantt-pending)', label: '未开始' },
                { color: 'var(--gantt-delayed)', label: '延期' },
                { color: 'var(--gantt-blocked)', label: '搁置' },
                { color: 'transparent', label: '黄色边框+⚠ = 资源冲突', border: '2px solid var(--gantt-conflict)', glow: 'var(--gantt-conflict)' },
              ].map((item) => (
                <span key={item.label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--text-secondary)' }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 14,
                      height: 10,
                      borderRadius: 2,
                      background: item.color,
                      border: item.border || '1px solid var(--gantt-pending-border)',
                      // 图例发光色块：同色微光（边框项用边框色发光）
                      boxShadow: `0 0 6px ${item.glow || item.color}`,
                    }}
                  />
                  {item.label}
                </span>
              ))}
            </Space>
          </div>
          <ResourceView scale={scale} onPhaseClick={setEditingPhase} conflictVersion={conflictVersion} onConflictChanged={bumpConflict} />
          <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
            提示：每人一行，行内的甘特条为其参与的项目阶段（按状态着色）。点击阶段条可查看详情（只读）。阶段调整请在项目管理页面操作。
          </div>
        </>
      )}
      <PhaseEditor
        phaseId={editingPhase}
        onClose={() => setEditingPhase(null)}
        onSaved={() => {}}
        readonly
        hideExtra
      />
      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
        冲突消除统一在甘特图：点击黄色冲突条 → 消除该甘特条（该阶段不计入该人员的并行计算）。
        冲突报告与消除记录见「审核中心 → 资源冲突」。
      </div>
    </Card>
  )
}
