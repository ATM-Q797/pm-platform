import { useState } from 'react'
import { Card, Segmented, Space, Tag } from 'antd'
import ResourceView from '../components/Resource/ResourceView'
import PhaseEditor from '../components/PhaseEditor/PhaseEditor'

/**
 * 资源负载页面：全员多行甘特图（只读）。
 *
 * 每人一行，行内显示其参与的所有项目/阶段，一眼看谁在忙、谁有空。
 * 甘特条不可编辑，点击只弹出只读查看面板。
 * 所有阶段调整请在项目管理页面操作。
 */
export default function ResourcePage() {
  const [scale, setScale] = useState<'day' | 'week' | 'month'>('week')
  const [editingPhase, setEditingPhase] = useState<number | null>(null)

  return (
    <Card
      title={
        <Space>
          <span>资源负载视图</span>
          <Tag color="blue">每人一行 · 显示所有参与项目</Tag>
        </Space>
      }
      extra={
        <Segmented
          options={[
            { label: '日', value: 'day' },
            { label: '周', value: 'week' },
            { label: '月', value: 'month' },
          ]}
          value={scale}
          onChange={(val) => setScale(val as 'day' | 'week' | 'month')}
        />
      }
    >
      <div style={{ marginBottom: 8 }}>
        <Space size="middle" wrap>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>图例：</span>
          {[
            { color: 'var(--gantt-done)', label: '已完成' },
            { color: 'var(--gantt-active)', label: '进行中' },
            { color: 'var(--gantt-pending)', label: '未开始' },
            { color: 'var(--gantt-delayed)', label: '延期' },
            { color: 'var(--gantt-blocked)', label: '已搁置' },
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
      <ResourceView scale={scale} onPhaseClick={setEditingPhase} />
      <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
        提示：每人一行，行内的甘特条为其参与的项目阶段（按状态着色）。点击阶段条可查看详情（只读）。阶段调整请在项目管理页面操作。
      </div>
      <PhaseEditor
        phaseId={editingPhase}
        onClose={() => setEditingPhase(null)}
        onSaved={() => {}}
        readonly
        hideExtra
      />
    </Card>
  )
}
