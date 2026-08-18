import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Table, Card, Select, Input, Button, Space, Tag, Upload, Modal, Form, DatePicker, message, Spin, Popconfirm, Radio } from 'antd'
import { DownloadOutlined, ReloadOutlined, UploadOutlined, PlusOutlined, EditOutlined, DeleteOutlined, StarFilled, StarOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { ColumnsType } from 'antd/es/table'
import { listProjects, createProject, updateProject, deleteProject, applyTemplate, setFavorite } from '../api/projects'
import { listTemplates } from '../api/templates'
import { listUsers } from '../api/users'
import { requestDeleteProject } from '../api/audit'
import { getMe } from '../api/auth'
import { MARKET_OPTION_ITEMS, MARKET_OPTIONS } from '../types'
import type { ImportPreview, Project, ImportReport, Template, UserInfo } from '../types'

// 状态 → Tag 颜色
const STATUS_COLOR: Record<string, string> = {
  进行中: 'processing',
  已完成: 'success',
  未开始: 'default',
  已搁置: 'warning',
  延期: 'error',
}

export default function ProjectListPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ status: '', market: '', category: '' })
  // 创建项目
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)
  const [templates, setTemplates] = useState<Template[]>([])
  const [managers, setManagers] = useState<UserInfo[]>([])  // 可选为项目负责人的用户（manager + admin）
  const [myRole, setMyRole] = useState<string>('viewer')
  const [deleteReasonOpen, setDeleteReasonOpen] = useState<Project | null>(null)
  const [deleteReason, setDeleteReason] = useState('')
  // 导入预检（差异报告确认后执行导入）
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [pendingImportFile, setPendingImportFile] = useState<File | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importMode, setImportMode] = useState<'merge' | 'replace'>('merge')
  const [form] = Form.useForm()
  const [editForm] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      // 项目列表和当前用户信息所有角色都需要
      const [data, me] = await Promise.all([
        listProjects({
          status: filters.status || undefined,
          market: filters.market || undefined,
          category: filters.category || undefined,
        }),
        getMe(),
      ])
      setProjects(data)
      setMyRole(me.role)

      // 模板列表和用户列表仅 admin/manager 需要（创建项目表单用），容错获取
      const canCreate = me.role === 'admin' || me.role === 'manager'
      if (canCreate) {
        try {
          const [tpls, users] = await Promise.all([listTemplates(), listUsers()])
          setTemplates(tpls)
          setManagers(users.filter((u) => u.role === 'manager' || u.role === 'admin'))
        } catch {
          // 静默失败，不影响列表展示
        }
      }
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters])

  // 第一步：选择文件 → 只解析生成差异报告（不导入）
  const handleImport = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    setPreviewLoading(true)
    setImportMode('merge') // 每次选择文件默认合并模式
    try {
      const resp = await fetch('/api/import/preview', { method: 'POST', body: formData })
      if (!resp.ok) {
        const err = await resp.json().catch(() => null)
        throw new Error(err?.detail || `预览失败 (HTTP ${resp.status})`)
      }
      const preview: ImportPreview = await resp.json()
      setImportPreview(preview)
      setPendingImportFile(file)
    } catch (e) {
      message.error('解析失败：' + (e as Error).message)
    } finally {
      setPreviewLoading(false)
    }
    return false // 阻止 antd Upload 默认上传行为
  }

  // 第二步：确认后真正导入（按当前模式）
  const confirmImport = async () => {
    if (!pendingImportFile) return
    const hide = message.loading('正在导入 Excel...', 0)
    const formData = new FormData()
    formData.append('file', pendingImportFile)
    setImporting(true)
    try {
      const resp = await fetch(`/api/import/excel?mode=${importMode}`, { method: 'POST', body: formData })
      if (!resp.ok) {
        const err = await resp.json().catch(() => null)
        throw new Error(err?.detail || `导入失败 (HTTP ${resp.status})`)
      }
      const report: ImportReport = await resp.json()
      hide()
      setImportPreview(null)
      setPendingImportFile(null)
      showImportResult(report)
      load()
    } catch (e) {
      hide()
      message.error('导入失败：' + (e as Error).message)
    } finally {
      setImporting(false)
    }
  }

  const showImportResult = (report: ImportReport) => {
    const isMerge = report.projects_created > 0 || report.projects_updated > 0
    Modal.info({
      title: isMerge ? '导入完成（合并）' : '导入完成（替换）',
      width: 640,
      content: (
        <div>
          {isMerge ? (
            <>
              <p>
                📥 新增 <b>{report.projects_created}</b> 个项目 / 📝 更新{' '}
                <b>{report.projects_updated}</b> 个项目
              </p>
              <p>
                阶段：新增 <b>{report.phases_created}</b> 个 / 更新 <b>{report.phases_updated}</b> 个
                {report.resources_created > 0 && <> / 新人员 {report.resources_created} 个</>}
              </p>
              <p>
                错误 {(report.errors || []).length} 条，警告 {(report.warnings || []).length} 条
              </p>
              {report.pending_link_phases.length > 0 && (
                <div style={{ background: '#fffbe6', padding: '8px 12px', borderRadius: 6, marginBottom: 8 }}>
                  <b style={{ color: '#d48806', fontSize: 13 }}>
                    ⚠️ 新增阶段待关联依赖（{report.pending_link_phases.length} 个）：
                  </b>
                  <p style={{ margin: '4px 0', fontSize: 12, color: '#666' }}>
                    以下阶段未自动关联依赖，请到对应项目甘特图中拖拽连线：
                  </p>
                  <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12, margin: 0, paddingLeft: 20 }}>
                    {report.pending_link_phases.map((p, i) => (
                      <li key={i}>
                        {p.project_name} · {p.phase_name}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <>
              <p>
                导入 <b>{report.projects_imported}</b> 个项目 / {report.phases_imported} 个阶段 /{' '}
                {report.resources_created} 个人员
              </p>
              <p>
                错误 {(report.errors || []).length} 条，警告 {(report.warnings || []).length} 条
              </p>
            </>
          )}
          {(report.errors || []).length > 0 && (
            <>
              <b>错误：</b>
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

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      setCreating(true)
      // 从 managed_by（user_id）反查用户姓名，同步填入 owner（兼容显示/旧逻辑）
      const managerUser = managers.find((m) => m.id === values.managed_by)
      // 项目编号由系统自动生成（连续整数），无需前端填写
      const project = await createProject({
        category: values.category,
        name: values.name,
        owner: managerUser?.name || '',
        managed_by: values.managed_by,
        market: values.market,
        plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
        plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
      })
      // 应用模板（如果选了）
      if (values.template_id) {
        try {
          await applyTemplate(project.id, values.template_id)
          message.success(`项目已创建并应用模板，跳转甘特图`)
        } catch (e) {
          message.warning(`项目已创建，但模板应用失败：${(e as Error).message}`)
        }
        navigate(`/projects/${project.id}`)
      } else {
        message.success('项目已创建')
        setCreateOpen(false)
        load()
      }
    } catch (e) {
      if ((e as any).errorFields) return
      message.error((e as Error).message)
    } finally {
      setCreating(false)
    }
  }

  const handleEdit = (project: Project) => {
    setEditing(project)
    editForm.setFieldsValue({
      category: project.category,
      name: project.name,
      owner: project.owner,
      market: project.market,
      status: project.status,
      priority: project.priority,
      plan_start: project.plan_start ? dayjs(project.plan_start) : null,
      plan_end: project.plan_end ? dayjs(project.plan_end) : null,
      remark: project.remark,
    })
    setEditOpen(true)
  }

  const handleEditSubmit = async () => {
    if (!editing) return
    try {
      const values = await editForm.validateFields()
      await updateProject(editing.id, {
        category: values.category,
        name: values.name,
        owner: values.owner,
        market: values.market,
        status: values.status,
        priority: values.priority,
        plan_start: values.plan_start?.format('YYYY-MM-DD') || null,
        plan_end: values.plan_end?.format('YYYY-MM-DD') || null,
        remark: values.remark,
      })
      message.success('项目信息已更新')
      setEditOpen(false)
      load()
    } catch (e) {
      if ((e as any).errorFields) return
      message.error((e as Error).message)
    }
  }

  const handleDelete = async (project: Project) => {
    if (myRole === 'admin') {
      // 管理员直接删
      try {
        await deleteProject(project.id)
        message.success(`已删除项目 "${project.name}"`)
        load()
      } catch (e) {
        message.error((e as Error).message)
      }
    } else {
      // manager 弹出申请框
      setDeleteReasonOpen(project)
      setDeleteReason('')
    }
  }

  const handleDeleteRequest = async () => {
    if (!deleteReasonOpen) return
    try {
      await requestDeleteProject(deleteReasonOpen.id, deleteReason || undefined)
      message.success('删除申请已提交，等待管理员审核')
      setDeleteReasonOpen(null)
      setDeleteReason('')
      load()
    } catch (e) {
      message.error('申请失败：' + (e as Error).message)
    }
  }

  const toggleFavorite = async (r: Project) => {
    const target = !r.is_favorite
    // 乐观更新：立即切换星标状态，失败回滚
    setProjects((prev) => prev.map((p) => (p.id === r.id ? { ...p, is_favorite: target } : p)))
    try {
      await setFavorite(r.id, target)
      // 置顶：关注后项目应排到前面（后端排序规则：is_favorite DESC, id）
      if (target) {
        load()
      }
    } catch (e) {
      setProjects((prev) => prev.map((p) => (p.id === r.id ? { ...p, is_favorite: !target } : p)))
      message.error('操作失败：' + (e as Error).message)
    }
  }

  const columns: ColumnsType<Project> = [
    {
      title: '★',
      width: 50,
      align: 'center',
      render: (_, r) => (
        <a
          onClick={(e) => { e.stopPropagation(); toggleFavorite(r) }}
          style={{ fontSize: 16, color: r.is_favorite ? '#fadb14' : '#d9d9d9' }}
          title={r.is_favorite ? '取消关注' : '关注（置顶）'}
        >
          {r.is_favorite ? <StarFilled /> : <StarOutlined />}
        </a>
      ),
    },
    { title: '编号', width: 70, align: 'center',
      render: (_: unknown, _r: Project, index: number) => index + 1 },
    {
      title: '项目名称',
      dataIndex: 'name',
      render: (_, r) => (
        <a onClick={() => navigate(`/projects/${r.id}`)}>{r.name}</a>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      align: 'center',
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: '类目', dataIndex: 'category', width: 100, align: 'center' },
    {
      title: '市场',
      dataIndex: 'market',
      width: 80,
      align: 'center',
      render: (m: string) => <Tag color="blue">{m}</Tag>,
    },
    { title: '负责人', dataIndex: 'owner', width: 100 },
    { title: '计划开始', dataIndex: 'plan_start', width: 120, align: 'center' },
    { title: '计划结束', dataIndex: 'plan_end', width: 120, align: 'center' },
    {
      title: '操作',
      width: 140,
      align: 'center',
      render: (_: unknown, r: Project) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={(e) => { e.stopPropagation(); handleEdit(r) }}>
            编辑
          </Button>
          <Popconfirm
            title={myRole === 'admin' ? `删除项目 "${r.name}"？此操作不可恢复` : `申请删除项目 "${r.name}"？`}
            onConfirm={() => handleDelete(r)}
            okText={myRole === 'admin' ? '删除' : '申请'}
            okType="danger"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
    <Card
      title={
        <Space>
          <span>项目列表</span>
          <Tag color="blue">{projects.length} 个项目</Tag>
        </Space>
      }
      extra={
        <Space>
          {myRole !== 'engineer' && myRole !== 'viewer' && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>
              新建项目
            </Button>
          )}
          <Upload accept=".xlsx,.xls" beforeUpload={handleImport} showUploadList={false}>
            <Button icon={<DownloadOutlined />} loading={previewLoading}>导入 Excel</Button>
          </Upload>
          <Button icon={<UploadOutlined />} onClick={() => window.open('/api/export/excel')}>
            导出 Excel
          </Button>
          <Button icon={<ReloadOutlined />} onClick={load} />
        </Space>
      }
    >
      <Space style={{ marginBottom: 16 }} size="middle">
        <Select
          placeholder="状态筛选"
          allowClear
          style={{ width: 140 }}
          value={filters.status || undefined}
          onChange={(v) => setFilters({ ...filters, status: v || '' })}
          options={[
            { value: '进行中', label: '进行中' },
            { value: '已完成', label: '已完成' },
            { value: '未开始', label: '未开始' },
            { value: '已搁置', label: '已搁置' },
          ]}
        />
        <Select
          placeholder="市场筛选"
          allowClear
          style={{ width: 120 }}
          value={filters.market || undefined}
          onChange={(v) => setFilters({ ...filters, market: v || '' })}
          options={MARKET_OPTION_ITEMS}
        />
        <Select
          placeholder="类目筛选"
          allowClear
          style={{ width: 140 }}
          value={filters.category || undefined}
          onChange={(v) => setFilters({ ...filters, category: v || '' })}
          options={[
            { value: '新需求', label: '新需求' },
            { value: '量产', label: '量产' },
            { value: '定制', label: '定制' },
            { value: '改造', label: '改造' },
          ]}
        />
      </Space>
      <Spin spinning={loading}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={projects}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          size="middle"
        />
      </Spin>
    </Card>

      {/* 新建项目 */}
      <Modal
        title="新建项目"
        open={createOpen}
        onOk={handleCreate}
        onCancel={() => setCreateOpen(false)}
        confirmLoading={creating}
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
          <Form.Item name="managed_by" label="项目负责人" rules={[{ required: true, message: '请选择负责人' }]}>
            <Select
              placeholder="选择项目负责人"
              showSearch
              optionFilterProp="label"
              options={managers.map((m) => ({ value: m.id, label: `${m.name}（${m.username}）` }))}
            />
          </Form.Item>
          <Space style={{ display: 'flex' }}>
            <Form.Item name="plan_start" label="计划开始">
              <DatePicker style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="plan_end" label="计划结束">
              <DatePicker style={{ width: 200 }} />
            </Form.Item>
          </Space>
          <Form.Item name="template_id" label="应用模板" extra="创建后自动生成阶段和依赖（可选）">
            <Select
              allowClear
              placeholder="不选则创建空项目"
              options={templates.map((t) => ({ value: t.id, label: `${t.name}（${t.category}）` }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑项目 */}
      <Modal
        title="编辑项目"
        open={editOpen}
        onOk={handleEditSubmit}
        onCancel={() => { setEditOpen(false); setEditing(null) }}
        width={520}
        okText="保存"
      >
        <Form form={editForm} layout="vertical" style={{ marginTop: 16 }} preserve={false}>
          <Form.Item name="code" label="项目编号" rules={[{ required: true }]}>
            <Input placeholder="项目编号（唯一）" />
          </Form.Item>
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
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
          <Form.Item name="owner" label="项目负责人" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={[
              { value: '未开始', label: '未开始' },
              { value: '进行中', label: '进行中' },
              { value: '已完成', label: '已完成' },
              { value: '已搁置', label: '已搁置' },
            ]} />
          </Form.Item>
          <Form.Item name="priority" label="优先级">
            <Select allowClear options={[
              { value: '高', label: '高' },
              { value: '中', label: '中' },
              { value: '低', label: '低' },
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
        </Form>
      </Modal>

      {/* 删除申请（manager） */}
      <Modal
        title="申请删除项目"
        open={!!deleteReasonOpen}
        onOk={handleDeleteRequest}
        onCancel={() => { setDeleteReasonOpen(null); setDeleteReason('') }}
        okText="提交申请"
        okType="danger"
      >
        <p>项目：{deleteReasonOpen?.name}</p>
        <p style={{ color: '#999', fontSize: 12 }}>申请将提交给管理员审核，通过后项目才会被删除。</p>
        <Input.TextArea
          placeholder="删除原因（可选）"
          rows={3}
          value={deleteReason}
          onChange={(e) => setDeleteReason(e.target.value)}
        />
      </Modal>

      {/* 导入预检：差异报告确认（确认后才真正导入） */}
      <Modal
        title="导入确认 — 差异报告"
        open={!!importPreview}
        onCancel={() => { setImportPreview(null); setPendingImportFile(null) }}
        onOk={confirmImport}
        okText={importMode === 'merge' ? '确认合并导入' : '确认替换导入并清空现有数据'}
        okType={importMode === 'merge' ? 'primary' : 'danger'}
        confirmLoading={importing}
        okButtonProps={{ disabled: !!importPreview && importPreview.errors.length > 0 }}
        width={680}
      >
        {importPreview && (
          <div>
            {/* 模式切换 */}
            <Radio.Group
              value={importMode}
              onChange={(e) => setImportMode(e.target.value)}
              style={{ marginBottom: 12 }}
            >
              <Radio.Button value="merge">合并导入（新增+更新，不删除）</Radio.Button>
              <Radio.Button value="replace">替换导入（清空重建）</Radio.Button>
            </Radio.Group>

            {importMode === 'merge' ? (
              <>
                {/* 合并差异：新增 / 更新 / 保留 */}
                <div style={{ background: '#f6ffed', padding: '12px 16px', borderRadius: 6, marginBottom: 12 }}>
                  <p style={{ margin: 0, color: '#389e0d', fontWeight: 600 }}>
                    📥 新增 {importPreview.created_projects.length} 个项目 / 📝 更新{' '}
                    {importPreview.updated_projects.length} 个项目 / 🔒 保留{' '}
                    {importPreview.kept_count} 个项目（不在文件中，不做改动）
                  </p>
                  <p style={{ margin: '4px 0 0', color: '#666', fontSize: 13 }}>
                    阶段：新增 {importPreview.phases_created} 个 / 更新 {importPreview.phases_updated} 个
                    （任何现有数据都不会被删除）
                  </p>
                </div>

                {/* 新增项目列表 */}
                {importPreview.created_projects.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    <b style={{ fontSize: 13 }}>📥 将新增项目：</b>
                    <ul style={{ maxHeight: 100, overflow: 'auto', fontSize: 12, margin: '4px 0 0', paddingLeft: 20 }}>
                      {importPreview.created_projects.map((p, i) => (
                        <li key={i}>
                          {p.name} <Tag style={{ fontSize: 11 }}>{p.market}</Tag>
                          <span style={{ color: '#999' }}>（{p.phases} 阶段）</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 更新项目列表 */}
                {importPreview.updated_projects.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    <b style={{ fontSize: 13 }}>📝 将合并更新：</b>
                    <ul style={{ maxHeight: 100, overflow: 'auto', fontSize: 12, margin: '4px 0 0', paddingLeft: 20 }}>
                      {importPreview.updated_projects.map((p, i) => (
                        <li key={i}>
                          {p.name} <Tag style={{ fontSize: 11 }}>{p.market}</Tag>
                          <span style={{ color: '#999' }}>（{p.phases} 阶段）</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 新增阶段待关联依赖提示 */}
                {importPreview.pending_link_phases.length > 0 && (
                  <div style={{ background: '#fffbe6', padding: '8px 12px', borderRadius: 6, marginBottom: 12 }}>
                    <b style={{ color: '#d48806', fontSize: 13 }}>
                      ⚠️ 新增阶段将提示待关联依赖（{importPreview.pending_link_phases.length} 个）：
                    </b>
                    <p style={{ margin: '4px 0', fontSize: 12, color: '#666' }}>
                      导入后需到对应项目甘特图中手动拖拽连线
                    </p>
                  </div>
                )}
              </>
            ) : (
              <>
                {/* 替换模式：红色警示 */}
                <div style={{ background: '#fff7e6', padding: '12px 16px', borderRadius: 6, marginBottom: 12 }}>
                  <p style={{ margin: 0, color: '#fa8c16', fontWeight: 600 }}>
                    ⚠️ 本次导入将【清空现有 {importPreview.existing.projects} 个项目
                    （{importPreview.existing.phases} 个阶段 / {importPreview.existing.resources} 个人员）】
                  </p>
                  <p style={{ margin: '4px 0 0', color: '#389e0d', fontWeight: 600 }}>
                    ✅ 文件包含 {importPreview.incoming.projects} 个项目 / {importPreview.incoming.phases} 个阶段
                  </p>
                </div>
                <p style={{ margin: '0 0 8px', fontSize: 13 }}>
                  项目对比：
                  <Tag color="green">{importPreview.match.matched} 个与现有同名</Tag>
                  <Tag color="blue">{importPreview.match.new} 个新增</Tag>
                  <Tag color={importPreview.match.missing > 0 ? 'red' : 'default'}>
                    {importPreview.match.missing} 个现有项目不在文件中
                  </Tag>
                  {importPreview.match.missing > 0 && (
                    <span style={{ color: '#ff4d4f', fontSize: 12, marginLeft: 4 }}>
                      （文件可能不完整，请确认）
                    </span>
                  )}
                </p>
                {importPreview.projects_preview.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <b style={{ fontSize: 13 }}>文件内项目：</b>
                    <ul style={{ maxHeight: 140, overflow: 'auto', fontSize: 12, margin: '4px 0 0', paddingLeft: 20 }}>
                      {importPreview.projects_preview.map((p, i) => (
                        <li key={i}>
                          {p.name} <Tag style={{ fontSize: 11 }}>{p.market}</Tag>
                          <span style={{ color: '#999' }}>（{p.phases} 阶段）</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}

            {/* 错误（存在则禁用确认） */}
            {importPreview.errors.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <b style={{ color: '#ff4d4f', fontSize: 13 }}>❌ 错误 {importPreview.errors.length} 条（请修正后重新上传）：</b>
                <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12, color: '#ff4d4f', margin: '4px 0 0', paddingLeft: 20 }}>
                  {importPreview.errors.map((e, i) => (
                    <li key={i}>[{e.sheet} R{e.row}] {e.message}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* 警告 */}
            {importPreview.warnings.length > 0 && (
              <div>
                <b style={{ fontSize: 13 }}>⚠️ 警告 {importPreview.warnings.length} 条：</b>
                <ul style={{ maxHeight: 120, overflow: 'auto', fontSize: 12, color: '#faad14', margin: '4px 0 0', paddingLeft: 20 }}>
                  {importPreview.warnings.map((w, i) => (
                    <li key={i}>[{w.sheet} R{w.row}] {w.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  )
}
