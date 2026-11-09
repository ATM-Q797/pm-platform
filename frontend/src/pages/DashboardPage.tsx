import { useEffect, useState, lazy, Suspense } from 'react'
import { useNavigate } from 'react-router-dom'
import { Alert, Button, Card, Col, Row, Space, Tag, Empty, Spin, Tooltip, message, Drawer, List, Modal } from 'antd'
import {
  ProjectOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  FieldTimeOutlined,
  ThunderboltOutlined,
  ToolOutlined,
  FireOutlined,
  FundOutlined,
  QuestionCircleOutlined,
  FileExcelOutlined,
  AlertOutlined,
  CalendarOutlined,
} from '@ant-design/icons'
import { getDashboardStats } from '../api/dashboard'
import { getResourceConflicts } from '../api/resources'
import { runSnapshot } from '../api/analysis'
import type { DashboardStats, ResourceConflict, ProjectHealthSummary } from '../types'

// 项目分析弹窗懒加载（含 ECharts，避免影响看板首屏）
const AnalysisModal = lazy(() => import('../components/Analysis/AnalysisModal'))

// 明细抽屉类型
type DrawerKey = 'delayed' | 'due' | 'conflict' | 'rework' | null

// 卡片左侧图标块配色（语义色）+ 顶部 3px 渐变条（每卡不同色相，见 tech.css .pm-stat-card）
const CARD_STYLE: Record<string, { bg: string; color: string; bar: string }> = {
  total: { bg: 'rgba(22,119,255,.1)', color: '#1677ff', bar: 'linear-gradient(90deg,#00d4ff,#7b61ff)' },
  active: { bg: 'rgba(34,229,138,.12)', color: '#16a34a', bar: 'linear-gradient(90deg,#22e58a,#00d4ff)' },
  delayed: { bg: 'rgba(255,77,109,.12)', color: '#e11d48', bar: 'linear-gradient(90deg,#ff4d6d,#fa8c16)' },
  due: { bg: 'rgba(251,191,36,.14)', color: '#b45309', bar: 'linear-gradient(90deg,#fbbf24,#fa8c16)' },
  conflict: { bg: 'rgba(250,140,22,.12)', color: '#c2410c', bar: 'linear-gradient(90deg,#fa8c16,#ff4d6d)' },
  rework: { bg: 'rgba(123,97,255,.12)', color: '#6d5ae0', bar: 'linear-gradient(90deg,#7b61ff,#00d4ff)' },
}

// 口径说明文案（8-1 ③：每卡 Tooltip 内嵌；与 PHASE8_PLAN §一 各指标口径一致）
const CARD_CALIBER: Record<string, string> = {
  total: '项目总数 = 非专项项目数（专项项目独立监控，不计入看板）',
  active: '进行中 = 状态为「进行中」的非专项项目数',
  delayed: '延期 = 阶段 plan_end < 今天 且状态 ∉ {已完成, 搁置}，排除专项；延期项目 = 名下存在此类逾期阶段的项目',
  due: '即将到期 = 阶段 plan_end 在未来 7 天内（含今天）且状态 ∈ {未开始, 进行中}，所属项目未搁置，排除专项',
  conflict: '卡面数字 = 今日风险队列中的冲突行数（同一冲突对跨资源去重为 1 行）；「较上周」小字 = 冲突对数口径（快照 conflict_pairs，按资源计对，含跨资源重复）；冲突明细抽屉按资源计对数。三处口径不同，以此为准',
  rework: '返工次数 = 各阶段返工次数之和（阶段每返工一次记 1），排除专项',
}

// 风险分析弹窗（2026-11-06 用户指令：今日风险内容去除——今日聚焦/即将到期卡已覆盖，不分散注意力；
// 只留红/黄档风险项目 2 分板块，精简聚焦决策）；见 return 区 Modal 节点

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  // 明细抽屉
  const [drawerKey, setDrawerKey] = useState<DrawerKey>(null)
  const [conflicts, setConflicts] = useState<ResourceConflict[]>([])
  const [conflictsLoading, setConflictsLoading] = useState(false)
  // 项目分析弹窗开关（裁定 ②：看板按钮 → 弹窗）
  const [analysisOpen, setAnalysisOpen] = useState(false)
  // 风险分析弹窗（合并版）：红/黄档风险项目 2 分板块，行点击跳项目详情
  const [riskOpen, setRiskOpen] = useState(false)
  // 8-1：快照采集进行中标记
  const [snapshotRunning, setSnapshotRunning] = useState(false)

  // 风险队列守卫（评审 #59 🔵：版本偏斜时旧后端不返回 risk_queue，
  // 2026-11-05 本地白屏事故的根因模式——所有读取点统一走这份空数组兜底）
  const riskQueue = stats?.risk_queue ?? []
  // 风险项目（8-2）：同模式兜底——旧后端不返回 risk_projects → 空数组，不报错
  const riskProjects: ProjectHealthSummary[] = stats?.risk_projects ?? []

  useEffect(() => {
    // 甘特消除后同步刷新本抽屉（用户 2026-08-28 决策 ③：消除统一在甘特，其他视图只同步）
    const onConflictChanged = () => {
      if (drawerKey === 'conflict') {
        setConflictsLoading(true)
        getResourceConflicts().then(setConflicts).catch(() => {}).finally(() => setConflictsLoading(false))
      }
    }
    window.addEventListener('conflict-changed', onConflictChanged)
    return () => window.removeEventListener('conflict-changed', onConflictChanged)
  }, [drawerKey])

  const load = async () => {
    setLoading(true)
    try {
      const data = await getDashboardStats()
      setStats(data)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // 打开明细抽屉（冲突数据按需加载）
  const openDrawer = (key: Exclude<DrawerKey, null>) => {
    setDrawerKey(key)
    if (key === 'conflict' && conflicts.length === 0) {
      setConflictsLoading(true)
      getResourceConflicts()
        .then(setConflicts)
        .catch((e) => message.error('冲突明细加载失败：' + (e as Error).message))
        .finally(() => setConflictsLoading(false))
    }
  }

  // 触发采集（8-1 ⑤）：POST /api/analysis/snapshots/run（admin）后重载看板
  const triggerSnapshot = async () => {
    setSnapshotRunning(true)
    try {
      await runSnapshot()
      message.success('快照采集完成')
      load()
    } catch (e) {
      message.error('采集失败：' + (e as Error).message)
    } finally {
      setSnapshotRunning(false)
    }
  }

  const drawerTitle: Record<Exclude<DrawerKey, null>, string> = {
    delayed: '延期项目明细（按逾期天数倒序）',
    due: '即将到期明细（未来 7 天）',
    conflict: '资源冲突明细（按重叠天数倒序）',
    rework: '返工阶段明细',
  }

  if (loading && !stats) {
    return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />
  }

  if (!stats) {
    return <Card>暂无数据</Card>
  }

  // 6 卡环比取数（8-1；2026-11-09 补进行中/返工）：weekly_delta 为 null 或该键为 null（无对比基期/基期缺键）→ 小字显示「较上周 —」
  const deltaOf = (k: 'projects_total' | 'active_projects' | 'delayed_projects' | 'due_soon_phases' | 'conflict_pairs' | 'total_rework_count') =>
    stats?.weekly_delta ? stats.weekly_delta[k] ?? null : null

  // 统计卡片渲染：左侧着色图标块 + 右侧数值（8-1：口径 Tooltip + 环比小字）
  const renderCard = (
    key: string,
    title: string,
    value: number,
    icon: React.ReactNode,
    onClick: () => void,
    dangerHighlight = false,
    delta?: number | null, // 环比（8-1）：undefined = 该卡不展示环比；null = 无对比基期
  ) => {
    const c = CARD_STYLE[key] || CARD_STYLE.total
    const isDanger = dangerHighlight && value > 0
    // 环比着色：延期/风险类上升红下降绿；总数类上升蓝下降灰；0/无基期灰
    const deltaColor =
      delta == null || delta === 0
        ? 'var(--text-secondary)'
        : key === 'total'
          ? delta > 0 ? '#1677ff' : 'var(--text-secondary)'
          : delta > 0 ? '#e11d48' : '#16a34a'
    const deltaText =
      delta == null ? '较上周 —' : delta > 0 ? `较上周 +${delta}` : delta < 0 ? `较上周 −${Math.abs(delta)}` : '较上周 持平'
    return (
      <Col span={8} style={{ display: 'flex' }}>
        <Card
          hoverable
          onClick={onClick}
          className="pm-stat-card"
          style={{ cursor: 'pointer', flex: 1, '--stat-bar': c.bar, '--stat-color': c.color } as React.CSSProperties}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: 10,
                background: c.bg,
                color: c.color,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 22,
                flexShrink: 0,
              }}
            >
              {icon}
            </div>
            <div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 2 }}>
                {title}
                <Tooltip title={CARD_CALIBER[key]}>
                  <QuestionCircleOutlined style={{ marginLeft: 4, fontSize: 11, cursor: 'help' }} />
                </Tooltip>
              </div>
              <div className={isDanger ? 'pm-stat-value pm-stat-danger' : 'pm-stat-value'}>
                {value}
              </div>
              {delta !== undefined && (
                <div style={{ fontSize: 11, color: deltaColor, marginTop: 2 }}>{deltaText}</div>
              )}
            </div>
          </div>
        </Card>
      </Col>
    )
  }

  return (
    <div>
      {/* 头部操作区：数据截至（8-1 ⑤）+ 三按钮（导出 Excel / 风险分析 / 项目分析，用户 2026-11-05 指令 ③ 顺序、2026-11-05 改名）
          不用 ghost 变体：ghost 文字取主色，在渐变底上对比度不足（用户 2026-10-26：字看不清）——
          实心主按钮文字为白色，对比稳定 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, flexWrap: 'wrap', gap: 8 }}>
        <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          <CalendarOutlined style={{ marginRight: 6 }} />
          数据截至 {stats.snapshot_date ?? '暂无快照'}
        </span>
        <Space>
          <Button icon={<FileExcelOutlined />} onClick={() => window.open('/api/export/excel')}>导出 Excel</Button>
          <Button
            icon={<AlertOutlined style={{ color: '#e11d48' }} />}
            onClick={() => setRiskOpen(true)}
          >
            风险分析
          </Button>
          <Button type="primary" icon={<FundOutlined />} onClick={() => setAnalysisOpen(true)}>
            项目分析
          </Button>
        </Space>
      </div>

      {/* 无快照空态（8-1 ⑤）：提示 + 触发采集入口（POST /api/analysis/snapshots/run） */}
      {stats.snapshot_date === null && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="暂无快照数据"
          description="暂无快照数据，请在分析弹窗中触发采集；环比与数据日期将在采集后可用。"
          action={<Button size="small" type="primary" loading={snapshotRunning} onClick={triggerSnapshot}>触发采集</Button>}
        />
      )}

      {/* 统计卡片：6 卡等高（用户 2026-11-05 指令 ④：带环比小字的卡比不带的高——
          对齐 antd 网格，整行拉伸同高、卡片纵向铺满；环比缺基期或基期缺键时 deltaOf 返 null 占位（显示「较上周 —」不捏造事实，
          与后端「不用 0 冒充无变化」原则同源，snapshot.py build_weekly_delta 注释），高度与真实环比行一致） */}
      <Row gutter={[16, 16]} style={{ marginBottom: 32, alignItems: 'stretch' }}>
        {renderCard('total', '项目总数', stats.total_projects, <ProjectOutlined />, () => navigate('/projects'), false, deltaOf('projects_total'))}
        {renderCard('active', '进行中', stats.active_projects, <ClockCircleOutlined />, () => navigate('/projects'), false, deltaOf('active_projects'))}
        {renderCard('delayed', '延期项目', stats.delayed_count, <WarningOutlined />, () => openDrawer('delayed'), true, deltaOf('delayed_projects'))}
      </Row>
      <Row gutter={[16, 16]} style={{ alignItems: 'stretch' }}>
        {renderCard('due', '即将到期', stats.due_soon_count, <FieldTimeOutlined />, () => openDrawer('due'), true, deltaOf('due_soon_phases'))}
        {renderCard('conflict', '资源冲突', riskQueue.filter((r) => r.type === 'conflict').length, <ThunderboltOutlined />, () => openDrawer('conflict'), true, deltaOf('conflict_pairs'))}
        {renderCard('rework', '返工次数', stats.total_rework_count, <ToolOutlined />, () => openDrawer('rework'), true, deltaOf('total_rework_count'))}
      </Row>

      {/* 风险分析弹窗（2026-11-06 合并重设计）：2 分板块（红档·立即处理 / 黄档·需要关注），
          只列需要处理的风险项目，行点击跳项目详情；今日风险内容不在此展示（今日聚焦/即将到期卡已覆盖）；
          绿/灰不上卡，搁置不评；底部固定文案（考核防火墙） */}
      <Modal
        title={
          <span>
            <AlertOutlined style={{ color: '#e11d48', marginRight: 8 }} />
            风险分析（{riskProjects.length}）
            <Tooltip title="红档 = 阶段逾期 ≥7 天；黄档 = 逾期 1–6 天或资源冲突 ≥3 对；按严重度排序，点行进详情">
              <QuestionCircleOutlined style={{ marginLeft: 4, fontSize: 12, color: 'var(--text-secondary)', cursor: 'help' }} />
            </Tooltip>
          </span>
        }
        open={riskOpen}
        onCancel={() => setRiskOpen(false)}
        footer={null}
        width={720}
      >
        <div style={{ maxHeight: '60vh', overflowY: 'auto' }}>
          {(['red', 'yellow'] as const).map((band) => {
            const rows = riskProjects.filter((r) => r.band === band)
            return (
              <div key={band} style={{ marginBottom: 16 }}>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: band === 'red' ? '#e11d48' : '#d48806',
                    marginBottom: 8,
                  }}
                >
                  {band === 'red' ? '🔴 红档 · 立即处理' : '🟡 黄档 · 需要关注'}（{rows.length}）
                </div>
                {rows.length > 0 ? (
                  <List
                    size="small"
                    dataSource={rows}
                    renderItem={(item) => (
                      <List.Item
                        style={{ cursor: 'pointer', padding: '8px 0' }}
                        onClick={() => navigate(`/projects/${item.project_id}`)}
                      >
                        <span style={{ fontSize: 13 }}>
                          <span
                            style={{
                              display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                              background: band === 'red' ? '#ff4d4f' : '#faad14',
                              marginRight: 8, verticalAlign: 'middle',
                            }}
                          />
                          {item.project_name}
                          <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>
                            （{item.owner || '—'}）
                          </span>
                          <span style={{ color: 'var(--text-secondary)', fontSize: 12, marginLeft: 8 }}>
                            {item.reason}
                          </span>
                        </span>
                      </List.Item>
                    )}
                  />
                ) : (
                  <div style={{ fontSize: 12, color: 'var(--text-tertiary)', padding: '8px 0' }}>
                    无{band === 'red' ? '红档' : '黄档'}项目
                  </div>
                )}
              </div>
            )
          })}
          <div
            style={{
              fontSize: 12,
              color: 'var(--text-secondary)',
              marginTop: 8,
              paddingTop: 8,
              borderTop: '1px solid var(--border-color, #333)',
            }}
          >
            本评级为项目状态参考，不构成绩效考核
          </div>
        </div>
      </Modal>

      {/* 今日聚焦：延期项目 + 即将到期 各前 5 */}
      <Card
        title={
          <span>
            <FireOutlined style={{ color: '#fa8c16', marginRight: 8 }} />
            今日聚焦
          </span>
        }
        className="pm-focus-card"
        style={{ marginTop: 32 }}
      >
        <Row gutter={24}>
          <Col span={12}>
            <div style={{ marginBottom: 8, color: 'var(--text-secondary)', fontSize: 13 }}>
              🔴 延期项目（{stats.delayed_projects.length}）
            </div>
            {stats.delayed_projects.length > 0 ? (
              <List
                size="small"
                dataSource={stats.delayed_projects.slice(0, 5)}
                locale={{ emptyText: <Empty description="暂无" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                renderItem={(d) => (
                  <List.Item
                    style={{ cursor: 'pointer', padding: '6px 0' }}
                    onClick={() => navigate(`/projects/${d.id}`)}
                  >
                    <List.Item.Meta
                      title={
                        <span style={{ fontSize: 13 }}>
                          {d.name}
                          <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>{d.market}</Tag>
                        </span>
                      }
                      description={
                        d.due_phases?.length > 0 ? (
                          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                            阶段：{d.due_phases.join('、')}
                          </span>
                        ) : undefined
                      }
                    />
                    <Tag color="error">逾期 {d.overdue_days} 天</Tag>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无延期项目 🎉" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Col>
          <Col span={12}>
            <div style={{ marginBottom: 8, color: 'var(--text-secondary)', fontSize: 13 }}>
              🟡 即将到期（{stats.due_soon_count}）
            </div>
            {stats.due_soon_phases.length > 0 ? (
              <List
                size="small"
                dataSource={stats.due_soon_phases.slice(0, 5)}
                locale={{ emptyText: <Empty description="暂无" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                renderItem={(d) => (
                  <List.Item
                    style={{ cursor: 'pointer', padding: '6px 0' }}
                    onClick={() => navigate(`/projects/${d.project_id}`)}
                  >
                    <List.Item.Meta
                      title={
                        <span style={{ fontSize: 13 }}>
                          {d.project_name} · {d.phase_name}
                        </span>
                      }
                    />
                    <Tag color={d.days_left <= 3 ? 'error' : 'warning'}>{d.days_left} 天后到期</Tag>
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无即将到期" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
          </Col>
        </Row>
      </Card>

      {/* 明细抽屉 */}
      <Drawer
        title={drawerKey ? drawerTitle[drawerKey] : ''}
        styles={{ wrapper: { width: 640 } }}
        open={drawerKey !== null}
        onClose={() => setDrawerKey(null)}
      >
        {drawerKey === 'delayed' && (
          <List
            dataSource={stats.delayed_projects}
            locale={{ emptyText: <Empty description="暂无延期项目 🎉" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            renderItem={(d) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/projects/${d.id}`)}
              >
                <List.Item.Meta
                  title={
                    <span>
                      <Tag color="blue">{d.market}</Tag>
                      {d.name}
                    </span>
                  }
                  description={`负责人：${d.owner || '—'} ｜ 计划结束：${d.plan_end || '—'}`}
                />
                <Tag color="error">逾期 {d.overdue_days} 天</Tag>
              </List.Item>
            )}
          />
        )}

        {drawerKey === 'due' && (
          <List
            dataSource={stats.due_soon_phases}
            locale={{ emptyText: <Empty description="暂无即将到期" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            renderItem={(d) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/projects/${d.project_id}`)}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {d.project_name} · {d.phase_name}
                    </span>
                  }
                  description={`剩余 ${d.days_left} 天`}
                />
                <Tag color={d.days_left <= 3 ? 'error' : 'warning'}>{d.days_left} 天后到期</Tag>
              </List.Item>
            )}
          />
        )}

        {drawerKey === 'conflict' && (
          <Spin spinning={conflictsLoading}>
            {conflicts.length === 0 && !conflictsLoading ? (
              <Empty description="暂无资源冲突 🎉" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              conflicts.map((rc) => (
                <div key={rc.resource_id} style={{ marginBottom: 16 }}>
                  <b style={{ fontSize: 14 }}>{rc.resource_name}</b>
                  <Tag color="orange" style={{ marginLeft: 8, color: '#b45309' }}>
                    {rc.conflicts.length} 个冲突
                  </Tag>
                  <List
                    dataSource={rc.conflicts}
                    renderItem={(c) => (
                      <List.Item
                        style={{ cursor: 'pointer', padding: '8px 0' }}
                        onClick={() => navigate(`/projects/${c.project_a_id}`)}
                      >
                        <List.Item.Meta
                          title={
                            <span style={{ fontSize: 13 }}>
                              {c.project_a_name}·{c.phase_a_name} × {c.project_b_name}·
                              {c.phase_b_name}
                            </span>
                          }
                        />
                        <Tag color="red">重叠 {c.overlap_days} 天</Tag>
                      </List.Item>
                    )}
                  />
                </div>
              ))
            )}
          </Spin>
        )}

        {drawerKey === 'rework' && (
          <List
            dataSource={stats.rework_phases}
            locale={{ emptyText: <Empty description="暂无返工" image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
            renderItem={(r) => (
              <List.Item
                style={{ cursor: 'pointer' }}
                onClick={() => navigate(`/projects/${r.project_id}`)}
              >
                <List.Item.Meta
                  title={
                    <span>
                      {r.project_name} · {r.phase_name}
                    </span>
                  }
                />
                <Tag color="orange" style={{ color: '#b45309' }}>{r.rework_count} 次返工</Tag>
              </List.Item>
            )}
          />
        )}
      </Drawer>

      {/* 项目分析弹窗（ECharts 懒加载分包，不进看板首屏） */}
      {analysisOpen && (
        <Suspense fallback={
          <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
            <Spin description="正在加载分析组件…" size="large" />
          </div>
        }>
          <AnalysisModal open={analysisOpen} onClose={() => setAnalysisOpen(false)} />
        </Suspense>
      )}
    </div>
  )
}
