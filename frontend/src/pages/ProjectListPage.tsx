import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Table, Card, Select, Input, Button, Space, Tag, Modal, Form, DatePicker, message, Spin, Segmented } from 'antd'
import { ReloadOutlined, UploadOutlined, PlusOutlined, ClearOutlined } from '@ant-design/icons'
import { listProjects, createProject, deleteProject, applyTemplate, setFavorite } from '../api/projects'
import ProjectEditModal from '../components/ProjectEditModal'
import { buildColumns, buildFavoriteColumns } from '../components/ProjectList/columns'
import { ImportExcelButton, ImportExcelModal, useImportExcel } from '../components/ProjectList/ImportExcelModal'
import { listTemplates } from '../api/templates'
import { listUsers } from '../api/users'
import { requestDeleteProject } from '../api/audit'
import { getMe } from '../api/auth'
import { MARKET_OPTION_ITEMS, MARKET_OPTIONS, PROJECT_LIST_FILTERS_KEY as FILTERS_KEY, PROJECT_LIST_SEARCH_KEY as SEARCH_KEY, PROJECT_LIST_VIEW_KEY as VIEW_KEY } from '../types'
import type { Project, Template, UserInfo } from '../types'

// 列表筛选持久化（用户 2026-10-26：返回列表不重置、刷新才重置）：
// sessionStorage 保存筛选，组件重挂时恢复；刷新页面由 App.tsx 统一清除（键名常量在 types/index.ts）。
const _DEFAULT_FILTERS = { status: '', market: '', category: '' }
const _readFilters = (): typeof _DEFAULT_FILTERS => {
  try {
    const raw = sessionStorage.getItem(FILTERS_KEY)
    if (!raw) return { ..._DEFAULT_FILTERS }
    const v = JSON.parse(raw)
    return { status: v.status || '', market: v.market || '', category: v.category || '' }
  } catch {
    return { ..._DEFAULT_FILTERS }
  }
}

export default function ProjectListPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(false)
  const [filters, setFiltersState] = useState(_readFilters)
  const updateFilters = (next: typeof _DEFAULT_FILTERS) => {
    setFiltersState(next)
    try { sessionStorage.setItem(FILTERS_KEY, JSON.stringify(next)) } catch { /* 存储满/禁用时静默：筛选仍可用，仅不跨页保留 */ }
  }
  const [searchText, setSearchTextState] = useState(() => {
    try { return sessionStorage.getItem(SEARCH_KEY) || '' } catch { return '' } // 读取与 _readFilters 同等兜底（评审 🔵#4 关联）
  }) // 项目名称搜索（前端过滤）
  const updateSearchText = (v: string) => {
    setSearchTextState(v)
    try { sessionStorage.setItem(SEARCH_KEY, v) } catch { /* 同上 */ }
  }
  // 重置筛选（用户 2026-10-27：筛选栏加“重置”按钮）——清空全部条件+搜索词，同步清 sessionStorage
  const resetFilters = () => {
    setFiltersState({ ..._DEFAULT_FILTERS })
    setSearchTextState('')
    try {
      sessionStorage.removeItem(FILTERS_KEY)
      sessionStorage.removeItem(SEARCH_KEY)
    } catch { /* 同上：清不掉也不影响本次重置生效 */ }
  }
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
  const [form] = Form.useForm()

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
  // Excel 导入两步流（预检 → 确认导入）：状态与逻辑在 ImportExcelModal 内（原样搬移），成功后回调刷新列表
  const excel = useImportExcel(load)

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      setCreating(true)
      // 负责人 = 自由文本（可自定义创建，用户 2026-08-28）；若输入匹配系统用户则绑定 managed_by（权限锚点），否则留空
      const ownerName = (values.managed_by as string || '').trim()
      const managerUser = managers.find((m) => m.name === ownerName)
      // 项目编号由系统自动生成（连续整数），无需前端填写
      const project = await createProject({
        category: values.category,
        name: values.name,
        owner: ownerName,
        managed_by: managerUser?.id ?? null,
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
    setEditOpen(true)
  }

  // 保存逻辑在共享组件 ProjectEditModal 内(handleOk),保存成功后回调 load() 刷新列表

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
    // 乐观更新：立即切换星标状态，失败回滚（星标只作标记，不再置顶——
    // 两页面排序统一按计划开始时间，置顶会打破一一对应，用户 2026-10-30 指令）
    setProjects((prev) => prev.map((p) => (p.id === r.id ? { ...p, is_favorite: target } : p)))
    try {
      await setFavorite(r.id, target)
    } catch (e) {
      setProjects((prev) => prev.map((p) => (p.id === r.id ? { ...p, is_favorite: !target } : p)))
      message.error('操作失败：' + (e as Error).message)
    }
  }

  // 「我的关注」副板块（用户 2026-11-04 批复）：关注项目独立视图，不显示序号列——
  // 序号 = 全量有序列表位置，只取关注子集会导致编号跳跃，故此视图不显示序号。
  // 视图切换仅前端过滤，不重拉数据；取消关注后若当前行不在关注集则自动移出视图。
  const [viewMode, setViewMode] = useState<'all' | 'favorites'>(
    () => {
      // 存储被禁用时静默回退到全部视图（与文件内其余 sessionStorage 访问同一兜底模式）
      try { return sessionStorage.getItem(VIEW_KEY) === 'favorites' ? 'favorites' : 'all' }
      catch { return 'all' }
    })
  const changeViewMode = (v: 'all' | 'favorites') => {
    setViewMode(v)
    try { sessionStorage.setItem(VIEW_KEY, v) } catch { /* 存储满/禁用时静默：视图仍可切换，仅刷新后不记忆 */ }
  }
  const favoriteProjects = projects.filter((p) => p.is_favorite)
  const viewProjects = viewMode === 'favorites' ? favoriteProjects : projects

  // 列定义与关注列派生已拆至 components/ProjectList/columns.tsx（2026-11-05 拆分批次），页面仅注入行为回调
  const columns = buildColumns({ projects, myRole, navigate, toggleFavorite, handleEdit, handleDelete })
  const favoriteColumns = buildFavoriteColumns(columns)

  return (
    <>
    <Card
      className="pm-no-blur"
      title={
        <Space>
          <span>项目列表</span>
          <Segmented
            value={viewMode}
            onChange={(v) => changeViewMode(v as 'all' | 'favorites')}
            options={[
              { label: '全部项目', value: 'all' },
              { label: `我的关注 (${favoriteProjects.length})`, value: 'favorites' },
            ]}
          />
          {viewMode === 'all' && <Tag color="blue">{projects.length} 个项目</Tag>}
        </Space>
      }
      extra={
        <Space>
          {myRole !== 'engineer' && myRole !== 'viewer' && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>
              新建项目
            </Button>
          )}
          <ImportExcelButton onImport={excel.handleImport} loading={excel.previewLoading} />
          <Button icon={<UploadOutlined />} onClick={() => window.open('/api/export/excel')}>
            导出 Excel
          </Button>
          <Button icon={<ReloadOutlined />} onClick={load} />
        </Space>
      }
    >
      <div className="pm-toolbar">
      <Space size="middle" wrap>
        <Input.Search
          placeholder="搜索项目名称"
          allowClear
          style={{ width: 240 }}
          value={searchText}
          onChange={(e) => updateSearchText(e.target.value)}
        />
        <Select
          placeholder="状态"
          style={{ width: 120 }}
          value={filters.status}
          onChange={(v) => updateFilters({ ...filters, status: v })}
          options={[
            { value: '', label: '全部' },
            { value: '进行中', label: '进行中' },
            { value: '已完成', label: '已完成' },
            { value: '未开始', label: '未开始' },
            { value: '搁置', label: '搁置' },
          ]}
        />
        <Select
          placeholder="市场"
          style={{ width: 120 }}
          value={filters.market}
           onChange={(v) => updateFilters({ ...filters, market: v })}
           options={[{ value: '', label: '全部' }, ...MARKET_OPTION_ITEMS]}
         />
         <Select
          placeholder="类目"
          style={{ width: 120 }}
          value={filters.category}
          onChange={(v) => updateFilters({ ...filters, category: v })}
          options={[
            { value: '', label: '全部' },
            { value: '新需求', label: '新需求' },
            { value: '量产升级', label: '量产升级' },
            { value: '定制', label: '定制' },
            { value: '改造', label: '改造' },
          ]}
        />
        {/* 重置筛选（用户 2026-10-27：置于筛选栏最右） */}
        <Button icon={<ClearOutlined />} onClick={resetFilters}>重置</Button>
      </Space>
      </div>
      <Spin spinning={loading}>
        <Table
          rowKey="id"
          columns={viewMode === 'favorites' ? favoriteColumns : columns}
          dataSource={viewProjects.filter((p) =>
            searchText ? p.name.toLowerCase().includes(searchText.trim().toLowerCase()) : true)}
          // 关注视图沿用分页（pageSize 20）：关注数可能超过一屏，一页拉满滚动反而难用；
          // 仅底栏文案区分视图（用户批复只约束「不显示序号」，分页不关）
          pagination={{
            pageSize: 20,
            showSizeChanger: false,
            showTotal: (t) => (viewMode === 'favorites' ? `共 ${t} 个关注项目` : `共 ${t} 个项目`),
          }}
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
                { value: '量产升级', label: '量产升级' },
                { value: '定制', label: '定制' },
                { value: '改造', label: '改造' },
              ]} />
            </Form.Item>
            <Form.Item name="market" label="市场" style={{ flex: 1 }}>
              <Select options={MARKET_OPTION_ITEMS} />
            </Form.Item>
          </Space>
          <Form.Item name="managed_by" label="项目负责人" rules={[{ required: true, message: '请选择负责人' }]}>
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
          <Form.Item name="template_id" label="应用模板" extra="创建后自动生成阶段和依赖（可选）">
            <Select
              allowClear
              placeholder="不选则创建空项目"
              options={templates.map((t) => ({ value: t.id, label: `${t.name}（${t.category}）` }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑项目（共享组件,与详情页同一弹窗） */}
      <ProjectEditModal
        project={editing}
        open={editOpen}
        onClose={() => { setEditOpen(false); setEditing(null) }}
        onSaved={load}
      />

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
        <p style={{ color: 'var(--text-tertiary)', fontSize: 12 }}>申请将提交给管理员审核，通过后项目才会被删除。</p>
        <Input.TextArea
          placeholder="删除原因（可选）"
          rows={3}
          value={deleteReason}
          onChange={(e) => setDeleteReason(e.target.value)}
        />
      </Modal>

      {/* 导入预检：差异报告确认（确认后才真正导入） */}
      <ImportExcelModal
        importPreview={excel.importPreview}
        importMode={excel.importMode}
        importing={excel.importing}
        onModeChange={excel.setImportMode}
        onCancel={excel.cancelImport}
        onConfirm={excel.confirmImport}
      />
    </>
  )
}
