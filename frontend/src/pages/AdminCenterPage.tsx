import { useState } from 'react'
import { Segmented } from 'antd'
import UserManagePage from './UserManagePage'
import ReviewPage from './ReviewPage'

export default function AdminCenterPage() {
  const [tab, setTab] = useState<string>('users')
  return (
    <div>
      <Segmented
        options={[
          { label: '用户管理', value: 'users' },
          { label: '审核中心', value: 'review' },
        ]}
        value={tab}
        onChange={(v) => setTab(v as string)}
        style={{ marginBottom: 16 }}
      />
      {tab === 'users' ? <UserManagePage /> : <ReviewPage />}
    </div>
  )
}
