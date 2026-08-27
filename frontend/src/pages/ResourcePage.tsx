import { useEffect, useState } from 'react'
import { Button, Card, Collapse, List, Popconfirm, Segmented, Space, Tag, message } from 'antd'
import ResourceView from '../components/Resource/ResourceView'
import HeatmapView from '../components/Resource/HeatmapView'
import PhaseEditor from '../components/PhaseEditor/PhaseEditor'
import ConflictOverrideModal, { type OverrideTarget } from '../components/Resource/ConflictOverrideModal'
import { getMe } from '../api/auth'
import {
  deleteConflictOverride,
  getResourceConflicts,
  listConflictOverrides,
  listResources,
} from '../api/resources'
import type { ConflictOverride, ResourceConflict, UserInfo } from '../types'

type ViewTab = 'heatmap' | 'gantt'

/**
 * 资源负载页面：双 Tab（热力图 | 甘特，默认热力图，RESOURCE_HEATMAP §3.1）。
 *
 * - 热力图：人员 × 时间负载矩阵，谁忙/谁闲/谁撞车一眼可读
 * - 甘特：原每人一行多行甘特（只读），点击阶段弹只读查看面板
 * - 底部「资源冲突报告」（CONFLICT_MODEL_V2 §2.4）：每对可消除（admin/manager），
 *   「已消除记录」折叠区可撤销（仅 admin/manager 可见，决策 3）
 * 所有阶段调整请在项目管理页面操作。
 */
export default function ResourcePage() {
  const [tab, setTab] = useState<ViewTab>('heatmap')
  const [scale, setScale] = useState<'day' | 'week' | 'month'>('week')
  const [editingPhase, setEditingPhase] = useState<number | null>(null)

  // ---- 冲突报告（CONFLICT_MODEL_V2 §2.4） ----
  const [conflicts, setConflicts] = useState<ResourceConflict[]>([])
  const [overrides, setOverrides] = useState<ConflictOverride[]>([])
  const [resourceNames, setResourceNames] = useState<Map<number, string>>(new Map())
  const [me, setMe] = useState<UserInfo | null>(null)
  const [overrideTarget, setOverrideTarget] = useState<OverrideTarget | null>(null)
  const [reportReload, setReportReload] = useState(0)
  const canOverride = me?.role === 'admin' || me?.role === 'manager'

  useEffect(() => {
    getMe().then(setMe).catch(() => {})
    listResources()
      .then((rs) => setResourceNames(new Map(rs.map((r) => [r.id, r.name]))))
      .catch(() => {})
  }, [])

  useEffect(() => {
    getResourceConflicts().then(setConflicts).catch(() => {})
    // 仅 admin/manager 可查消除记录（决策 3）；其他角色 403 → 置空
    listConflictOverrides().then(setOverrides).catch(() => setOverrides([]))
  }, [reportReload])

  const handleRevoke = async (ov: ConflictOverride) => {
    try {
      await deleteConflictOverride(ov.id)
      message.success('已撤销消除，该冲突对恢复报告')
      setReportReload((v) => v + 1)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '撤销失败，请重试')
    }
  }

  const totalPairs = conflicts.reduce((n, rc) => n + rc.conflicts.length, 0)

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
        <HeatmapView />
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
        </>
      )}
      <PhaseEditor
        phaseId={editingPhase}
        onClose={() => setEditingPhase(null)}
        onSaved={() => {}}
        readonly
        hideExtra
      />

      {/* 资源冲突报告（CONFLICT_MODEL_V2 §2.4）：消除 + 已消除记录（可撤销） */}
      <Collapse
        style={{ marginTop: 16 }}
        defaultActiveKey={totalPairs > 0 ? ['report'] : []}
        items={[
          {
            key: 'report',
            label: `资源冲突报告（${totalPairs} 对 · 深度重叠且并行超限才报）`,
            children: conflicts.length === 0 ? (
              <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>暂无资源冲突 🎉</span>
            ) : (
              conflicts.map((rc) => (
                <div key={rc.resource_id} style={{ marginBottom: 12 }}>
                  <b style={{ fontSize: 14 }}>{rc.resource_name}</b>
                  <Tag color="orange" style={{ marginLeft: 8, color: '#b45309' }}>
                    {rc.conflicts.length} 个冲突
                  </Tag>
                  <List
                    size="small"
                    dataSource={rc.conflicts}
                    renderItem={(c) => (
                      <List.Item
                        style={{ padding: '6px 0' }}
                        actions={canOverride ? [
                          <Button
                            key="override"
                            size="small"
                            danger
                            onClick={() => setOverrideTarget({
                              resourceId: rc.resource_id,
                              resourceName: rc.resource_name,
                              phaseAId: c.phase_a_id,
                              phaseBId: c.phase_b_id,
                              summary: `${rc.resource_name}：${c.project_a_name}·${c.phase_a_name} × ` +
                                `${c.project_b_name}·${c.phase_b_name}（重叠 ${c.overlap_days} 天）`,
                            })}
                          >
                            消除
                          </Button>,
                        ] : undefined}
                      >
                        <span style={{ fontSize: 13 }}>
                          {c.project_a_name}·{c.phase_a_name} × {c.project_b_name}·{c.phase_b_name}
                        </span>
                        <Tag color="red" style={{ marginLeft: 8 }}>重叠 {c.overlap_days} 天</Tag>
                      </List.Item>
                    )}
                  />
                </div>
              ))
            ),
          },
          // 已消除记录：仅 admin/manager 可见可撤销（决策 3）
          ...(canOverride ? [{
            key: 'overrides',
            label: `已消除记录（${overrides.length}）`,
            children: overrides.length === 0 ? (
              <span style={{ fontSize: 13, color: 'var(--text-tertiary)' }}>无消除记录</span>
            ) : (
              <List
                size="small"
                dataSource={overrides}
                renderItem={(ov) => (
                  <List.Item
                    style={{ padding: '6px 0' }}
                    actions={[
                      <Popconfirm
                        key="revoke"
                        title="撤销消除？该冲突对将恢复报告"
                        okText="撤销"
                        cancelText="取消"
                        onConfirm={() => handleRevoke(ov)}
                      >
                        <Button size="small">撤销</Button>
                      </Popconfirm>,
                    ]}
                  >
                    <span style={{ fontSize: 13 }}>
                      {resourceNames.get(ov.resource_id) ?? `资源#${ov.resource_id}`}
                      ：阶段 #{ov.phase_a_id} × #{ov.phase_b_id}
                      <span style={{ color: 'var(--text-tertiary)' }}>
                        ｜原因：{ov.reason}{ov.created_at ? `｜${ov.created_at.slice(0, 16).replace('T', ' ')}` : ''}
                      </span>
                    </span>
                  </List.Item>
                )}
              />
            ),
          }] : []),
        ]}
      />
      <ConflictOverrideModal
        target={overrideTarget}
        open={overrideTarget !== null}
        onClose={() => setOverrideTarget(null)}
        onOverridden={() => setReportReload((v) => v + 1)}
      />
    </Card>
  )
}
