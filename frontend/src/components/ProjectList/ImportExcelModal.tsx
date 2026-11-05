// Excel 导入两步流（2026-11-05 拆分批次从 ProjectListPage 原样搬出：逻辑体不变，只改 import 与 props 传递）。
// 第一步选文件只解析出差异报告（预检，不落库）；第二步确认后按合并/替换模式真正导入，成功后回调刷新列表。
// 工具栏按钮与预检弹窗共用同一份预检状态（本组件同时渲染两处，状态不外泄到页面）。
import { useState } from 'react'
import { Modal, Radio, Tag, Upload, Button, message } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import type { ImportPreview, ImportReport } from '../../types'

// 供页面在导入成功后刷新列表
export function useImportExcel(onImported: () => void) {
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null)
  const [pendingImportFile, setPendingImportFile] = useState<File | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importMode, setImportMode] = useState<'merge' | 'replace'>('merge')

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
      onImported()
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
                <div style={{ background: 'var(--alert-info-bg)', padding: '8px 12px', borderRadius: 6, marginBottom: 8 }}>
                  <b style={{ color: '#d48806', fontSize: 13 }}>
                    ⚠️ 新增阶段待关联依赖（{report.pending_link_phases.length} 个）：
                  </b>
                  <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--text-secondary)' }}>
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

  // 取消预检：清空差异报告与暂存文件（原弹窗 onCancel 的两行 setState 原样封装）
  const cancelImport = () => {
    setImportPreview(null)
    setPendingImportFile(null)
  }

  return { importPreview, previewLoading, importing, importMode, setImportMode, handleImport, confirmImport, cancelImport }
}

// 工具栏入口按钮：选文件后立刻进入预检（在页面 Card 头部渲染）
export function ImportExcelButton(props: { onImport: (file: File) => Promise<boolean>; loading: boolean }) {
  return (
    <Upload accept=".xlsx,.xls" beforeUpload={props.onImport} showUploadList={false}>
      <Button icon={<DownloadOutlined />} loading={props.loading}>导入 Excel</Button>
    </Upload>
  )
}

// 预检弹窗：差异报告确认（确认后才真正导入；在页面底部渲染）
export function ImportExcelModal(props: {
  importPreview: ImportPreview | null
  importMode: 'merge' | 'replace'
  importing: boolean
  onModeChange: (m: 'merge' | 'replace') => void
  onCancel: () => void
  onConfirm: () => void
}) {
  const { importPreview, importMode, importing } = props
  return (
    <Modal
      title="导入确认 — 差异报告"
      open={!!importPreview}
      onCancel={props.onCancel}
      onOk={props.onConfirm}
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
            onChange={(e) => props.onModeChange(e.target.value)}
            style={{ marginBottom: 12 }}
          >
            <Radio.Button value="merge">合并导入（新增+更新，不删除）</Radio.Button>
            <Radio.Button value="replace">替换导入（清空重建）</Radio.Button>
          </Radio.Group>

          {importMode === 'merge' ? (
            <>
              {/* 合并差异：新增 / 更新 / 保留 */}
              <div style={{ background: 'var(--alert-ok-bg)', padding: '12px 16px', borderRadius: 6, marginBottom: 12 }}>
                <p style={{ margin: 0, color: '#389e0d', fontWeight: 600 }}>
                  📥 新增 {importPreview.created_projects.length} 个项目 / 📝 更新{' '}
                  {importPreview.updated_projects.length} 个项目 / 🔒 保留{' '}
                  {importPreview.kept_count} 个项目（不在文件中，不做改动）
                </p>
                <p style={{ margin: '4px 0 0', color: 'var(--text-secondary)', fontSize: 13 }}>
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
                        <span style={{ color: 'var(--text-tertiary)' }}>（{p.phases} 阶段）</span>
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
                        <span style={{ color: 'var(--text-tertiary)' }}>（{p.phases} 阶段）</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 新增阶段待关联依赖提示 */}
              {importPreview.pending_link_phases.length > 0 && (
                <div style={{ background: 'var(--alert-info-bg)', padding: '8px 12px', borderRadius: 6, marginBottom: 12 }}>
                  <b style={{ color: '#d48806', fontSize: 13 }}>
                    ⚠️ 新增阶段将提示待关联依赖（{importPreview.pending_link_phases.length} 个）：
                  </b>
                  <p style={{ margin: '4px 0', fontSize: 12, color: 'var(--text-secondary)' }}>
                    导入后需到对应项目甘特图中手动拖拽连线
                  </p>
                </div>
              )}
            </>
          ) : (
            <>
              {/* 替换模式：红色警示 */}
              <div style={{ background: 'var(--alert-warn-bg)', padding: '12px 16px', borderRadius: 6, marginBottom: 12 }}>
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
                        <span style={{ color: 'var(--text-tertiary)' }}>（{p.phases} 阶段）</span>
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
  )
}
