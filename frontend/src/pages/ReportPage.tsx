import { useEffect, useState } from 'react'
import { Button, Card, Select, Space, message, Spin, Typography } from 'antd'
import { CopyOutlined, FileTextOutlined, SyncOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import { listProjects } from '../api/projects'
import { generateWeeklyReport } from '../api/reports'
import type { Project, WeeklyReport } from '../types'

export default function ReportPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [report, setReport] = useState<WeeklyReport | null>(null)
  const [loading, setLoading] = useState(false)

  // 首次进入加载项目列表（用于多选）
  useEffect(() => {
    listProjects().then(setProjects).catch(() => {})
  }, [])

  const generate = async () => {
    setLoading(true)
    try {
      const data = await generateWeeklyReport(selectedIds)
      setReport(data)
    } catch (e) {
      message.error('周报生成失败：' + (e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const copy = async () => {
    if (!report) return
    try {
      await navigator.clipboard.writeText(report.plain_text)
      message.success('已复制到剪贴板')
    } catch {
      message.error('复制失败，请手动选择文本复制')
    }
  }

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Typography.Text strong>项目范围：</Typography.Text>
          <Select
            mode="multiple"
            allowClear
            placeholder="不选 = 全部项目"
            style={{ minWidth: 420 }}
            value={selectedIds}
            onChange={setSelectedIds}
            options={projects.map((p) => ({ value: p.id, label: `${p.name}（#${p.id}）` }))}
            optionFilterProp="label"
            maxTagCount={3}
          />
          <Button type="primary" icon={<SyncOutlined />} loading={loading} onClick={generate}>
            生成周报
          </Button>
          {report && (
            <Button icon={<CopyOutlined />} onClick={copy}>
              一键复制
            </Button>
          )}
        </Space>
        <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
          周报内容：整体进度概览 / 风险预警（延期+即将到期）/ 本周完成 / 进行中 / 下周计划。复制为纯文本格式，可直接粘贴邮件。
        </div>
      </Card>

      {loading && !report && (
        <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />
      )}

      {report && (
        <Card
          title={
            <Space>
              <FileTextOutlined />
              周报预览
              <span style={{ color: '#999', fontSize: 12, fontWeight: 400 }}>
                生成于 {report.generated_at.replace('T', ' ')}
              </span>
            </Space>
          }
        >
          <div className="report-markdown">
            <ReactMarkdown>{report.markdown}</ReactMarkdown>
          </div>
        </Card>
      )}
    </div>
  )
}
