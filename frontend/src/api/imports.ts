import type { ImportPreview, ImportReport } from '../types'

// 专项导入接口（SPECIAL_PROJECT §五·B）：仅 admin/manager；专项域全量重置。
// 与常规导入（/api/import/preview + /api/import/excel）同路由族，
// 用原生 fetch 上传 multipart（与 ProjectListPage 常规导入一致）。

/** 专项导入前差异报告：将清空 N 个专项项目、导入 M 个（不落库、无副作用）。 */
export async function specialImportPreview(file: File): Promise<ImportPreview> {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await fetch('/api/import/special-preview', { method: 'POST', body: formData })
  if (!resp.ok) {
    const err = await resp.json().catch(() => null)
    throw new Error(err?.detail || `预览失败 (HTTP ${resp.status})`)
  }
  return resp.json()
}

/** 专项导入：删除全部 is_special=true 项目，按文件重建（阶段类型原样存储）。 */
export async function importSpecial(file: File): Promise<ImportReport> {
  const formData = new FormData()
  formData.append('file', file)
  const resp = await fetch('/api/import/special', { method: 'POST', body: formData })
  if (!resp.ok) {
    const err = await resp.json().catch(() => null)
    throw new Error(err?.detail || `导入失败 (HTTP ${resp.status})`)
  }
  return resp.json()
}
