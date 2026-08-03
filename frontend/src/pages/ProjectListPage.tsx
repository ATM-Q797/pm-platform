import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Table, Card, Select, Input, Button, Space, Tag, Upload, Modal, Form, DatePicker, message, Spin } from 'antd'
import { UploadOutlined, ReloadOutlined, DownloadOutlined, PlusOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { ColumnsType } from 'antd/es/table'
import { listProjects, createProject, applyTemplate } from '../api/projects'
import { listTemplates } from '../api/templates'
import type { Project, ImportReport, Template } from '../types'

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
  const [templates, setTemplates] = useState<Template[]>([])
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [data, tpls] = await Promise.all([
        listProjects({
          status: filters.status || undefined,
          market: filters.market || undefined,
          category: filters.category || undefined,
        }),
        listTemplates(),
      ])
      setProjects(data)
      setTemplates(tpls)
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

  const handleImport = async (file: File) => {
    const hide = message.loading('正在导入 Excel...', 0)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const resp = await fetch('/api/import/excel', { method: 'POST', body: formData })
      const report: ImportReport = await resp.json()
      hide()
      Modal.info({
        title: '导入完成',
        width: 640,
        content: (
          <div>
            <p>
              导入 <b>{report.projects_imported}</b> 个项目 / {report.phases_imported} 个阶段 /{' '}
              {report.resources_created} 个人员
            </p>
            <p>
              错误 {report.errors.length} 条，警告 {report.warnings.length} 条
            </p>
            {report.errors.length > 0 && (
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
            {report.warnings.length > 0 && (
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
      load()
    } catch (e) {
      hide()
      message.error('导入失败：' + (e as Error).message)
    }
    return false // 阻止 antd Upload 默认上传行为
  }

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      setCreating(true)
      const project = await createProject({
        code: values.code,
        category: values.category,
        name: values.name,
        owner: values.owner,
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

  const columns: ColumnsType<Project> = [
    { title: '编号', dataIndex: 'code', width: 70, align: 'center' },
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
      render: (m: string) => <Tag color={m === '海外' ? 'purple' : 'blue'}>{m}</Tag>,
    },
    { title: '负责人', dataIndex: 'owner', width: 100 },
    { title: '计划开始', dataIndex: 'plan_start', width: 120, align: 'center' },
    { title: '计划结束', dataIndex: 'plan_end', width: 120, align: 'center' },
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateOpen(true) }}>
            新建项目
          </Button>
          <Upload accept=".xlsx,.xls" beforeUpload={handleImport} showUploadList={false}>
            <Button icon={<UploadOutlined />}>导入 Excel</Button>
          </Upload>
          <Button icon={<DownloadOutlined />} onClick={() => window.open('/api/export/excel')}>
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
          options={[
            { value: '国内', label: '国内' },
            { value: '海外', label: '海外' },
          ]}
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
          onRow={(r) => ({ onClick: () => navigate(`/projects/${r.id}`) })}
          style={{ cursor: 'pointer' }}
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
          initialValues={{ category: '新需求', market: '国内', status: '未开始' }}>
          <Form.Item name="code" label="项目编号" rules={[{ required: true, message: '请输入项目编号' }]}>
            <Input placeholder="如 TCM10-015" />
          </Form.Item>
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
              <Select options={[
                { value: '国内', label: '国内' },
                { value: '海外', label: '海外' },
              ]} />
            </Form.Item>
          </Space>
          <Form.Item name="owner" label="项目负责人" rules={[{ required: true, message: '请输入负责人' }]}>
            <Input placeholder="负责人姓名" />
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
    </>
  )
}
