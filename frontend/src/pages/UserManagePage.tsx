import { useEffect, useState } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  message,
  Popconfirm,
} from 'antd'
import { PlusOutlined, ReloadOutlined, KeyOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  forceDeleteUser,
  resetPassword,
  type UserCreatePayload,
} from '../api/users'
import { listResources } from '../api/resources'
import type { UserInfo, Resource } from '../types'

const ROLE_COLOR: Record<string, string> = {
  admin: 'red',
  manager: 'blue',
  engineer: 'green',
  viewer: 'default',
  reporter: 'purple',
}

const ROLE_LABEL: Record<string, string> = {
  admin: '管理员',
  manager: '项目负责人',
  engineer: '工程师',
  viewer: '观察者',
  reporter: '填报人',
}

export default function UserManagePage() {
  const [users, setUsers] = useState<UserInfo[]>([])
  const [resources, setResources] = useState<Resource[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<UserInfo | null>(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      const [us, rs] = await Promise.all([listUsers(), listResources()])
      setUsers(us)
      setResources(rs)
    } catch (e) {
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const handleAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ role: 'engineer' })
    setModalOpen(true)
  }

  const handleEdit = (u: UserInfo) => {
    setEditing(u)
    form.setFieldsValue({
      username: u.username,
      name: u.name,
      role: u.role,
      resource_id: u.resource_id,
      is_active: u.is_active,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editing) {
        // 编辑（不改密码）
        await updateUser(editing.id, {
          name: values.name,
          role: values.role,
          is_active: values.is_active,
          resource_id: values.resource_id || null,
        })
        message.success('已更新')
      } else {
        // 新建
        const payload: UserCreatePayload = {
          username: values.username,
          name: values.name,
          role: values.role,
          password: values.password || '123456',
          resource_id: values.resource_id || null,
        }
        await createUser(payload)
        message.success('已创建，初始密码：' + (values.password || '123456'))
      }
      setModalOpen(false)
      load()
    } catch (e) {
      if ((e as any).errorFields) return
      message.error((e as Error).message)
    }
  }

  // 强制删除（用户 2026-10-29 指令）：3 次删除失败后，第 4 次删除+确认时弹「强制删除」询问
  const [deleteCounts, setDeleteCounts] = useState<Record<number, number>>({})
  const [forceTarget, setForceTarget] = useState<UserInfo | null>(null)

  const handleDelete = async (u: UserInfo) => {
    try {
      await deleteUser(u.id)
      message.success('已删除')
      load()
    } catch (e) {
      const msg = (e as Error).message
      // 评审 #6+#8：仅审计保护类 400 计入升级计数——拦截器抛裸 Error（无 .response，
      // client.ts:22），唯一可靠信号是后端 400 文案含"审计"二字（users.py 引导文案独有）
      if (!msg.includes('审计')) {
        message.error(msg)
        return
      }
      const n = (deleteCounts[u.id] ?? 0) + 1
      setDeleteCounts((c) => ({ ...c, [u.id]: n }))
      if (n >= 4) {
        // 第 4 次：升级为强制删除询问
        setForceTarget(u)
      } else {
        message.error(`${msg}（第 ${n} 次，第 4 次可选强制删除）`)
      }
    }
  }

  const handleForceDelete = async () => {
    if (!forceTarget) return
    try {
      await forceDeleteUser(forceTarget.id)
      message.success(`${forceTarget.name} 已强制删除（操作日志保留）`)
      setForceTarget(null)
      load()
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  const handleResetPwd = async (u: UserInfo) => {
    try {
      await resetPassword(u.id)
      message.success(`已重置 ${u.name} 的密码为 123456`)
    } catch (e) {
      message.error((e as Error).message)
    }
  }

  // 已被关联的 resource id 集合（用于下拉过滤）
  const usedResourceIds = new Set(
    users.filter((u) => u.resource_id && u.id !== editing?.id).map((u) => u.resource_id!)
  )

  const columns: ColumnsType<UserInfo> = [
    { title: 'ID', dataIndex: 'id', width: 60, align: 'center' },
    { title: '用户名', dataIndex: 'username', width: 120 },
    { title: '姓名', dataIndex: 'name', width: 120 },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      align: 'center',
      render: (r: string) => <Tag color={ROLE_COLOR[r]}>{ROLE_LABEL[r]}</Tag>,
    },
    {
      title: '关联人员',
      dataIndex: 'resource_id',
      width: 120,
      render: (rid: number | null) => {
        if (!rid) return <Tag>无</Tag>
        const res = resources.find((r) => r.id === rid)
        return res?.name || `#${rid}`
      },
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 80,
      align: 'center',
      render: (active: boolean) =>
        active ? <Tag color="success">启用</Tag> : <Tag color="default">禁用</Tag>,
    },
    {
      title: '操作',
      width: 240,
      render: (_: unknown, u: UserInfo) => (
        <Space size="small">
          <Button size="small" onClick={() => handleEdit(u)}>编辑</Button>
          <Button size="small" icon={<KeyOutlined />} onClick={() => handleResetPwd(u)}>
            重置密码
          </Button>
          {u.role !== 'admin' && (
            <Popconfirm title={`删除用户 ${u.name}？`} onConfirm={() => handleDelete(u)}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title={
        <Space>
          <span>用户管理</span>
          <Tag color="blue">{users.length} 人</Tag>
        </Space>
      }
      extra={
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            新建用户
          </Button>
          <Button icon={<ReloadOutlined />} onClick={load} />
        </Space>
      }
    >
      <Table
        rowKey="id"
        columns={columns}
        dataSource={users}
        loading={loading}
        pagination={false}
        size="middle"
      />

      <Modal
        title={editing ? '编辑用户' : '新建用户'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        width={460}
        okText={editing ? '保存' : '创建'}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          {!editing && (
            <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
              <Input placeholder="登录用户名" />
            </Form.Item>
          )}
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
            <Input placeholder="真实姓名" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'admin', label: '管理员（全局管理）' },
                { value: 'manager', label: '项目负责人（管理自己的项目）' },
                { value: 'engineer', label: '工程师（更新分配的阶段）' },
                { value: 'viewer', label: '观察者（只读）' },
                { value: 'reporter', label: '填报人（信息填报页，过渡期角色）' },
              ]}
            />
          </Form.Item>
          {!editing && (
            <Form.Item name="password" label="初始密码" extra="留空则默认 123456">
              <Input.Password placeholder="123456" />
            </Form.Item>
          )}
          <Form.Item name="resource_id" label="关联人员（资源）" extra="关联后可被分配为阶段负责人">
            <Select
              allowClear
              placeholder="选择对应的人员（可空）"
              options={resources
                .filter((r) => !usedResourceIds.has(r.id))
                .map((r) => ({ value: r.id, label: `${r.name}${r.role ? '（' + r.role + '）' : ''}` }))}
            />
          </Form.Item>
          {editing && (
            <Form.Item name="is_active" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 强制删除确认（用户 2026-10-29 指令）：第 4 次删除失败后弹出——墓碑式，日志保留 */}
      <Modal
        open={!!forceTarget}
        title={`强制删除用户 ${forceTarget?.name ?? ''}？`}
        onOk={handleForceDelete}
        onCancel={() => setForceTarget(null)}
        okText="确认强制删除"
        okButtonProps={{ danger: true }}
        cancelText="取消"
      >
        <p>该账号有操作记录，普通删除被审计保护拒绝。</p>
        <p style={{ marginBottom: 0 }}><b>强制删除效果：</b></p>
        <ul style={{ margin: '8px 0 0', paddingLeft: 22 }}>
          <li>用户从用户管理列表消失、无法登录</li>
          <li>操作日志<b>完整保留</b>（历史记录显示“已强制删除”标记）</li>
          <li>项目负责人等指派保留（项目历史不失真）</li>
        </ul>
      </Modal>
    </Card>
  )
}
