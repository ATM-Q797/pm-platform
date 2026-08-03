import { useState } from 'react'
import { Card, Segmented, Space, Tag, message } from 'antd'
import ResourceView from '../components/Resource/ResourceView'
import PhaseEditor from '../components/PhaseEditor/PhaseEditor'

/**
 * 资源负载页面：全员多行甘特图。
 *
 * 每人一行，行内显示其参与的所有项目/阶段，一眼看谁在忙、谁有空。
 * 点击阶段条弹出 PhaseEditor 查看详情（复用项目详情页的编辑面板）。
 */
export default function ResourcePage() {
  const [scale, setScale] = useState<'day' | 'week' | 'month'>('week')
  const [editingPhase, setEditingPhase] = useState<number | null>(null)
  // 用于强制刷新 ResourceView（编辑保存后重新加载）
  const [viewKey, setViewKey] = useState(0)

  const handlePhaseSaved = () => {
    setViewKey((k) => k + 1)
  }

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
      <ResourceView key={viewKey} scale={scale} onPhaseClick={setEditingPhase} />
      <div style={{ marginTop: 8, fontSize: 12, color: '#999' }}>
        提示：每人一行，行内的甘特条为其参与的项目阶段（按状态着色）。点击阶段条可查看/编辑详情。
      </div>
      <PhaseEditor phaseId={editingPhase} onClose={() => setEditingPhase(null)} onSaved={handlePhaseSaved} />
    </Card>
  )
}
