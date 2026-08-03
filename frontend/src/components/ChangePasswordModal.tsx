import { useState } from 'react'
import { Modal, Form, Input, message } from 'antd'
import { changePassword } from '../api/auth'

interface Props {
  open: boolean
  forceChange: boolean // true=首登强制改（不可取消），false=主动改（可取消）
  onCancel: () => void
  onSuccess: () => void
}

export default function ChangePasswordModal({ open, forceChange, onCancel, onSuccess }: Props) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      await changePassword(values.old_password, values.new_password)
      message.success('密码已修改')
      form.resetFields()
      onSuccess()
    } catch (e) {
      if ((e as any).errorFields) return
      message.error((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={forceChange ? '首次登录，请修改密码' : '修改密码'}
      open={open}
      onCancel={forceChange ? undefined : onCancel}
      closable={!forceChange}
      maskClosable={!forceChange}
      keyboard={!forceChange}
      onOk={handleSubmit}
      okText="确认修改"
      cancelText={forceChange ? undefined : '取消'}
      cancelButtonProps={{ style: { display: forceChange ? 'none' : undefined } }}
      confirmLoading={loading}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item name="old_password" label="原密码" rules={[{ required: true }]}>
          <Input.Password autoComplete="current-password" />
        </Form.Item>
        <Form.Item name="new_password" label="新密码" rules={[
          { required: true, message: '请输入新密码' },
          { min: 4, message: '至少 4 位' },
        ]}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item
          name="confirm_password"
          label="确认新密码"
          dependencies={['new_password']}
          rules={[
            { required: true, message: '请确认密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                return Promise.reject(new Error('两次密码不一致'))
              },
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
