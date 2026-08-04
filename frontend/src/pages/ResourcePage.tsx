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
      <ResourceView scale={scale} onPhaseClick={setEditingPhase} />
      <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
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
