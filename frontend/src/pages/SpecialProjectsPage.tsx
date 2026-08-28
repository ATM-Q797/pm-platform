import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Col, Row, Tag, Button, Space, Modal, Form, Input, Select,
  DatePicker, Switch, Progress, Spin, message, Empty, Upload,
} from 'antd'
import { PlusOutlined, EditOutlined, UploadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { listSpecialProjects, createProject, updateProject } from '../api/projects'
import { importSpecial, specialImportPreview } from '../api/imports'
import { listUsers } from '../api/users'
import { getMe } from '../api/auth'
import { MARKET_OPTION_ITEMS, MARKET_OPTIONS } from '../types'
import type { ImportPreview, ImportReport, Project, UserInfo } from '../types'

// 状态 → Tag 颜色（与项目列表页一致，双 key 兼容旧值「已搁置」）
const STATUS_COLOR: Record<string, string> = {
  进行中: 'processing',
  已完成: 'success',
  未开始: 'default',
  搁置: 'warning',
  已搁置: 'warning',
}

// 预警角标（SPECIAL_PROJECT §4.1，口径与 Dashboard 一致）
// 优先级：延期 🔴 > 即将到期 🟡 > 无阶段 ⚠️（同时成立只显示最高级——评审处置 #7）
// 边界（评审处置 #11）：搁置/已完成不触发；plan_end 为空不触发延期/到期
interface Badge {
  key: 'overdue' | 'due' | 'nophase'
  text: string
  color: string
}

function computeBadge(p: Project): Badge | null {
  if (p.status === '搁置' || p.status === '已搁置' || p.status === '已完成') return null
  const today = dayjs().startOf('day')
  if (p.plan_end) {
    const end = dayjs(p.plan_end)
    if (end.isBefore(today)) {
      return { key: 'overdue', text: `🔴 延期 ${today.diff(end, 'day')} 天`, color: '#ff4d4f' }
    }
    const daysLeft = end.diff(today, 'day')
    if (daysLeft <= 7) {
      return { key: 'due', text: daysLeft === 0 ? '🟡 今天到期' : `🟡 ${daysLeft} 天后到期`, color: '#faad14' }
    }
  }
  if (!p.phases || p.phases.length === 0) {
    return { key: 'nophase', text: '⚠️ 无阶段', color: '#fa8c16' }
  }
  return null
}

export default function SpecialProjectsPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)
  const [saving, setSaving] = useState(false)
  const [managers, setManagers] = useState<UserInfo[]>([])
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()
  // 专项导入（SPECIAL_PROJECT §五·B）：上传 → 预览（专项域口径）→ 确认 → 全量重置专项域
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [pendingImportFile, setPendingImportFile] = useState<File | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [importing, setImporting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [data, me] = await Promise.all([listSpecialProjects(), getMe()])
      setProjects(data)
      // 负责人候选：manager + admin（与项目列表页一致）
      if (me.role === 'admin' || me.role === 'manager') {
        listUsers()
          .then((users) => setManagers(users.filter((u) => u.role === 'manager' || u.role === 'admin')))
          .catch(() => {})
      }
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      // 负责人 = 自由文本（可自定义创建，用户 2026-08-28）；匹配系统用户则绑定 managed_by（权限锚点），否则留空
      const ownerName = (values.managed_by as string || '').trim()
      const managerUser = managers.find((m) => m.name === ownerName)
      await createProject({
        category: values.category,
        name: values.name,
        owner: ownerName,
        managed_by: managerUser?.id ?? null,
        market: values.market,
        plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
        plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
        is_special: true, // 专项页创建固定为专项项目
      })
      message.success('专项项目已创建')
      setCreateOpen(false)
      load()
    } catch (e) {
      if ((e as any).errorFields) return
      message.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = (p: Project) => {
    setEditing(p)
    editForm.setFieldsValue({
      name: p.name,
      category: p.category,
      market: p.market,
      owner: p.owner,
      status: p.status,
      plan_start: p.plan_start ? dayjs(p.plan_start) : null,
      plan_end: p.plan_end ? dayjs(p.plan_end) : null,
      remark: p.remark,
      is_special: p.is_special ?? true,
    })
    setEditOpen(true)
  }

  const handleEditSubmit = async () => {
    if (!editing) return
    try {
      const values = await editForm.validateFields()
      setSaving(true)
      const payload = {
        name: values.name,
        category: values.category,
        owner: values.owner,
        market: values.market,
        status: values.status,
        plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
        plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
        remark: values.remark,
        is_special: values.is_special !== false, // 取消开关 → 转为普通项目（进入普通列表）
      }
      await updateProject(editing.id, payload)
      message.success(values.is_special === false ? '已转为普通项目' : '专项项目已更新')
      setEditOpen(false)
      setEditing(null)
      load()
    } catch (e) {
      if ((e as any).errorFields) return
      message.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  // 专项导入：第一步 选择文件 → 预览（专项域口径："将清空 N 个专项项目、导入 M 个"）
  const handleSpecialImport = async (file: File) => {
    setPreviewLoading(true)
    try {
      const preview = await specialImportPreview(file)
      setImportPreview(preview)
      setPendingImportFile(file)
    } catch (e) {
      message.error('解析失败：' + (e as Error).message)
    } finally {
      setPreviewLoading(false)
    }
    return false // 阻止 antd Upload 默认上传行为
  }

  // 专项导入：第二步 确认 → 全量重置专项域（常规项目/人员不受影响）
  const confirmSpecialImport = async () => {
    if (!pendingImportFile) return
    const hide = message.loading('正在导入专项数据...', 0)
    setImporting(true)
    try {
      const report = await importSpecial(pendingImportFile)
      hide()
      setImportPreview(null)
      setPendingImportFile(null)
      showSpecialImportResult(report)
      load()
    } catch (e) {
      hide()
      message.error('导入失败：' + (e as Error).message)
    } finally {
      setImporting(false)
    }
  }

  const showSpecialImportResult = (report: ImportReport) => {
    Modal.info({
      title: '专项导入完成',
      width: 640,
      content: (
        <div>
          <p>
            📥 导入 <b>{report.projects_imported}</b> 个专项项目 / {report.phases_imported} 个阶段 /{' '}
            {report.resources_created} 个人员
          </p>
          <p>错误 {(report.errors || []).length} 条，警告 {(report.warnings || []).length} 条</p>
          {(report.errors || []).length > 0 && (
            <>
              <b style={{ color: '#ff4d4f' }}>错误：</b>
              <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12 }}>
                {report.errors.map((e, i) => (
                  <li key={i}>
                    [{e.sheet} R{e.row}] {e.message}
                  </li>
                ))}
              </ul>
            </>
          )}
          {(report.warnings || []).length > 0 && (
            <>
              <b>警告：</b>
              <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12 }}>
                {report.warnings.map((w, i) => (
                  <li key={i}>
                    [{w.sheet} R{w.row}] {w.message}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ),
    })
  }

  return (
    <Card
      className="pm-no-blur"
      title={
        <Space>
          <span>专项项目</span>
          <Tag color="purple">{projects.length} 个专项</Tag>
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)', fontWeight: 400 }}>
            独立监控对象 · 不占资源负载（热力图/甘特/冲突）
          </span>
        </Space>
      }
      extra={
        <Space>
          <Upload accept=".xlsx,.xls" beforeUpload={handleSpecialImport} showUploadList={false}>
            <Button icon={<UploadOutlined />} loading={previewLoading}>导入专项数据</Button>
          </Upload>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>
            新建专项项目
          </Button>
        </Space>
      }
    >
      <Spin spinning={loading}>
        {projects.length === 0 && !loading ? (
          <Empty description="暂无专项项目" />
        ) : (
          <Row gutter={[16, 16]}>
            {projects.map((p) => {
              const badge = computeBadge(p)
              // 阶段进度：各阶段 progress 平均值（与甘特项目行口径一致）
              const phases = p.phases || []
              const progress = phases.length
                ? Math.round(phases.reduce((s, ph) => s + (ph.progress || 0), 0) / phases.length)
                : 0
              return (
                <Col key={p.id} xs={24} sm={12} lg={8} xl={6}>
                  <Card
                    hoverable
                    size="small"
                    onClick={() => navigate(`/projects/${p.id}`)}
                    title={
                      <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 14, fontWeight: 600 }}>{p.name}</span>
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={(e) => { e.stopPropagation(); handleEdit(p) }}
                        >
                          编辑
                        </Button>
                      </Space>
                    }
                  >
                    <Space size="small" wrap style={{ marginBottom: 8 }}>
                      <Tag color={STATUS_COLOR[p.status] || 'default'}>{p.status}</Tag>
                      <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>负责人：{p.owner || '—'}</span>
                    </Space>
                    {badge && (
                      <div style={{ color: badge.color, fontWeight: 600, marginBottom: 8, fontSize: 13 }}>
                        {badge.text}
                      </div>
                    )}
                    <div style={{ marginBottom: 4, display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-secondary)' }}>
                      <span>阶段进度</span>
                      <span>{progress}%</span>
                    </div>
                    <Progress percent={progress} size="small" showInfo={false} />
                    <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-tertiary)' }}>
                      计划：{p.plan_start || '?'} ~ {p.plan_end || '?'}
                    </div>
                  </Card>
                </Col>
              )
            })}
          </Row>
        )}
      </Spin>

      {/* 新建专项项目 */}
      <Modal
        title="新建专项项目"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={saving}
        width={520}
        okText="创建"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}
          initialValues={{ category: '新需求', market: MARKET_OPTIONS[0], status: '未开始' }}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="项目全称" />
          </Form.Item>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="category" label="类目" style={{ flex: 1 }}>
              <Select options={[
                { value: '新需求', label: '新需求' },
                { value: '量产', label: '量产' },
                { value: '定制', label: '定制' },
                { value: '改造', label: '改造' },
              ]} />
            </Form.Item>
            <Form.Item name="market" label="市场" style={{ flex: 1 }}>
              <Select options={MARKET_OPTION_ITEMS} />
            </Form.Item>
          </Space>
          <Form.Item name="managed_by" label="项目负责人" rules={[{ required: true, message: '请输入负责人' }]}>
            <Input placeholder="可输入任意人员姓名（不限于系统用户）" />
          </Form.Item>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="plan_start" label="计划开始">
              <DatePicker style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="plan_end" label="计划结束">
              <DatePicker style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Form.Item label="专项项目" extra="专项项目独立监控：仅本页可见、不占资源负载、阶段类型可自定义">
            <Switch checked disabled /> {/* 专项页创建固定为专项项目 */}
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑专项项目 */}
      <Modal
        title="编辑专项项目"
        open={editOpen}
        onOk={handleEditSubmit}
        onCancel={() => { setEditOpen(false); setEditing(null) }}
        confirmLoading={saving}
        width={520}
        okText="保存"
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 16 }} preserve={false}>
          <Form.Item name="name" label="项目名称" rules={[{ required: true, message: '请输入项目名称' }]}>
            <Input placeholder="项目全称" />
          </Form.Item>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="category" label="类目" style={{ flex: 1 }}>
              <Select options={[
                { value: '新需求', label: '新需求' },
                { value: '量产', label: '量产' },
                { value: '定制', label: '定制' },
                { value: '改造', label: '改造' },
              ]} />
            </Form.Item>
            <Form.Item name="market" label="市场" style={{ flex: 1 }}>
              <Select options={MARKET_OPTION_ITEMS} />
            </Form.Item>
          </Space>
          <Form.Item name="owner" label="项目负责人" rules={[{ required: true, message: '请输入负责人' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={[
              { value: '未开始', label: '未开始' },
              { value: '进行中', label: '进行中' },
              { value: '已完成', label: '已完成' },
              { value: '搁置', label: '搁置' },
              { value: '已搁置', label: '已搁置（保存时转为搁置）' },
            ]} />
          </Form.Item>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="plan_start" label="计划开始">
              <DatePicker style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="plan_end" label="计划结束">
              <DatePicker style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Form.Item name="remark" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="is_special" label="专项项目" valuePropName="checked"
            extra="取消勾选后转为普通项目（进入普通项目列表，恢复资源负载统计）">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      {/* 专项导入预览（§五·B：全量替换专项域，仅 admin/manager 可见本页） */}
      <Modal
        title="专项导入预览"
        open={!!importPreview}
        onCancel={() => { setImportPreview(null); setPendingImportFile(null) }}
        onOk={confirmSpecialImport}
        okText="确认导入并替换全部专项项目"
        okType="danger"
        confirmLoading={importing}
        okButtonProps={{ disabled: !!importPreview && importPreview.errors.length > 0 }}
        width={640}
      >
        {importPreview && (
          <div>
            <p style={{ marginBottom: 8 }}>
              🔴 本次导入将【全量替换全部专项项目】：清空现有{' '}
              <b>{importPreview.existing.projects}</b> 个专项项目（{importPreview.existing.phases} 个阶段）
            </p>
            <p style={{ marginBottom: 8 }}>
              ✅ 文件包含 <b>{importPreview.incoming.projects}</b> 个项目 /{' '}
              {importPreview.incoming.phases} 个阶段
            </p>
            <p style={{ marginBottom: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
              🛡️ 常规项目与人员数据不受影响；阶段类型按文件原样导入（不映射 P1-P8）
            </p>
            {importPreview.projects_preview.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <b style={{ fontSize: 13 }}>文件内项目：</b>
                <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12, margin: '4px 0 0', paddingLeft: 20 }}>
                  {importPreview.projects_preview.map((p, i) => (
                    <li key={i}>
                      {p.name}（{p.phases} 个阶段）
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {importPreview.errors.length > 0 && (
              <div>
                <b style={{ color: '#ff4d4f', fontSize: 13 }}>
                  ❌ 错误 {importPreview.errors.length} 条（请修正后重新上传）：
                </b>
                <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12, margin: '4px 0 0', paddingLeft: 20 }}>
                  {importPreview.errors.map((e, i) => (
                    <li key={i}>
                      [{e.sheet} R{e.row}] {e.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {importPreview.warnings.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <b style={{ fontSize: 13 }}>⚠️ 警告 {importPreview.warnings.length} 条：</b>
                <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12, margin: '4px 0 0', paddingLeft: 20 }}>
                  {importPreview.warnings.map((w, i) => (
                    <li key={i}>
                      [{w.sheet} R{w.row}] {w.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>
    </Card>
  )
}
