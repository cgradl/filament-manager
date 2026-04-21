import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { Project, ProjectDetail, PrintJob } from '../types'
import { Plus, Pencil, Trash2, X, FolderOpen, ChevronDown, ChevronRight, Layers } from 'lucide-react'
import { useHATZ } from '../hooks/useHATZ'
import { formatDateTimeTZ } from '../utils/time'

// ── Inline modal shell (matches Prints.tsx pattern) ───────────────────────────

function ModalShell({ title, onClose, wide, children }: {
  title: string
  onClose: () => void
  wide?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className={`bg-surface-2 border border-surface-3 rounded-2xl w-full ${wide ? 'max-w-2xl' : 'max-w-md'} max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-3">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} className="btn-ghost p-1"><X size={16} /></button>
        </div>
        <div className="p-5">
          {children}
        </div>
      </div>
    </div>
  )
}

// ── Project Form ──────────────────────────────────────────────────────────────

function ProjectForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Project
  onSave: (data: { name: string; description: string | null }) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')

  return (
    <div className="space-y-4">
      <div>
        <label className="label">{t('projects.name')} *</label>
        <input
          className="input"
          value={name}
          onChange={e => setName(e.target.value)}
          placeholder={t('projects.namePlaceholder')}
          autoFocus
        />
      </div>
      <div>
        <label className="label">{t('projects.description')}</label>
        <textarea
          className="input h-20 resize-none"
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder={t('projects.descriptionPlaceholder')}
        />
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <button className="btn-ghost px-4 py-2" onClick={onCancel}>{t('common.cancel')}</button>
        <button
          className="btn-primary px-4 py-2"
          disabled={!name.trim()}
          onClick={() => onSave({ name: name.trim(), description: description.trim() || null })}
        >
          {t('common.save')}
        </button>
      </div>
    </div>
  )
}

// ── Assign prints modal ───────────────────────────────────────────────────────

function AssignPrintsModal({
  project,
  onClose,
}: {
  project: ProjectDetail
  onClose: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const tz = useHATZ()

  const assignedIds = new Set(project.print_jobs.map(j => j.id))

  const { data: allPrints = [] } = useQuery<PrintJob[]>({
    queryKey: ['prints', 1000, 0],
    queryFn: () => api.getPrints(1000, 0),
  })

  const eligible = allPrints.filter(j => !j.fm_project_id || j.fm_project_id === project.id)

  const [selected, setSelected] = useState<Set<number>>(new Set(assignedIds))

  const assignMut = useMutation({
    mutationFn: async () => {
      const toAssign = [...selected].filter(id => !assignedIds.has(id))
      const toUnassign = [...assignedIds].filter(id => !selected.has(id))
      let latest: Project | undefined
      if (toAssign.length > 0) latest = await api.assignPrintsToProject(project.id, toAssign)
      if (toUnassign.length > 0) latest = await api.unassignPrintsFromProject(project.id, toUnassign)
      return latest
    },
    onSuccess: (latest) => {
      // Immediately patch the project in the list cache with the fresh server data
      // so the card stats update without waiting for a background refetch
      if (latest) {
        qc.setQueryData<Project[]>(['projects'], old =>
          old ? old.map(p => p.id === latest.id ? latest : p) : old
        )
      }
      qc.invalidateQueries({ queryKey: ['projects'] })
      qc.invalidateQueries({ queryKey: ['prints'] })
      onClose()
    },
  })

  const toggle = (id: number) => setSelected(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  return (
    <ModalShell title={t('projects.assignPrints', { name: project.name })} onClose={onClose} wide>
      <div className="space-y-3">
        <p className="text-xs text-gray-400">{t('projects.assignHint')}</p>
        <div className="max-h-96 overflow-y-auto space-y-1">
          {eligible.length === 0 && (
            <p className="text-sm text-gray-500 py-4 text-center">{t('common.noData')}</p>
          )}
          {eligible.map(job => (
            <label key={job.id} className="flex items-center gap-3 p-2 rounded hover:bg-surface-3 cursor-pointer">
              <input
                type="checkbox"
                checked={selected.has(job.id)}
                onChange={() => toggle(job.id)}
                className="w-4 h-4 accent-accent"
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-white truncate">{job.name}</span>
                  {job.success
                    ? <span className="text-xs text-green-400">✓</span>
                    : <span className="text-xs text-red-400">✗</span>}
                </div>
                <div className="text-xs text-gray-400">
                  {formatDateTimeTZ(job.started_at, tz)}
                  {job.printer_name && ` · ${job.printer_name}`}
                  {job.total_grams > 0 && ` · ${job.total_grams.toFixed(1)}g`}
                </div>
              </div>
            </label>
          ))}
        </div>
        <div className="flex justify-between items-center pt-2">
          <span className="text-xs text-gray-400">{selected.size} {t('projects.selected')}</span>
          <div className="flex gap-2">
            <button className="btn-ghost px-4 py-2" onClick={onClose}>{t('common.cancel')}</button>
            <button
              className="btn-primary px-4 py-2"
              onClick={() => assignMut.mutate()}
              disabled={assignMut.isPending}
            >
              {t('common.save')}
            </button>
          </div>
        </div>
      </div>
    </ModalShell>
  )
}

// ── Project Card ──────────────────────────────────────────────────────────────

function ProjectCard({
  project,
  onEdit,
  onDelete,
  onManagePrints,
}: {
  project: Project
  onEdit: () => void
  onDelete: () => void
  onManagePrints: () => void
}) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)

  const { data: detail } = useQuery<ProjectDetail>({
    queryKey: ['projects', project.id],
    queryFn: () => api.getProject(project.id),
    enabled: expanded,
  })

  const durationH = project.total_duration_seconds > 0
    ? (project.total_duration_seconds / 3600).toFixed(1)
    : null

  return (
    <div className="card">
      <div
        className="flex items-center gap-3 cursor-pointer"
        onClick={() => setExpanded(e => !e)}
      >
        <span className="text-accent shrink-0">
          {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        </span>
        <FolderOpen size={16} className="text-accent shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white truncate">{project.name}</span>
            <span className="text-xs text-gray-500 shrink-0">{project.print_count} {t('projects.prints')}</span>
          </div>
          {project.description && (
            <p className="text-xs text-gray-400 truncate">{project.description}</p>
          )}
        </div>

        <div className="hidden sm:flex items-center gap-4 text-xs text-gray-400 shrink-0">
          {project.total_grams > 0 && (
            <span>{(project.total_grams / 1000).toFixed(2)} {t('common.kg')}</span>
          )}
          {project.total_cost > 0 && (
            <span>€{project.total_cost.toFixed(2)}</span>
          )}
          {project.total_energy_kwh != null && (
            <span>
              {project.total_energy_kwh.toFixed(3)} kWh
              {project.total_energy_cost != null && <> · €{project.total_energy_cost.toFixed(4)}</>}
            </span>
          )}
          {durationH && <span>{durationH}h</span>}
          {project.materials.length > 0 && (
            <span className="hidden lg:inline">{project.materials.join(', ')}</span>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0" onClick={e => e.stopPropagation()}>
          <button
            className="btn-ghost p-1.5"
            onClick={onManagePrints}
            title={t('projects.managePrints')}
          >
            <Layers size={14} />
          </button>
          <button className="btn-ghost p-1.5" onClick={onEdit} title={t('common.edit')}>
            <Pencil size={14} />
          </button>
          <button className="btn-ghost p-1.5 text-red-400" onClick={onDelete} title={t('common.delete')}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-surface-3">
          {!detail && (
            <p className="text-xs text-gray-500">{t('common.loading')}</p>
          )}
          {detail && detail.print_jobs.length === 0 && (
            <p className="text-xs text-gray-500">{t('projects.noPrints')}</p>
          )}
          {detail && detail.print_jobs.map(job => (
            <PrintJobRow key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  )
}

function PrintJobRow({ job }: { job: PrintJob }) {
  const tz = useHATZ()
  return (
    <div className="flex items-center gap-3 py-1.5 text-sm border-b border-surface-3 last:border-0">
      <span className={job.success ? 'text-green-400' : 'text-red-400'}>
        {job.success ? '✓' : '✗'}
      </span>
      <span className="flex-1 truncate text-gray-200">{job.name}</span>
      <span className="text-xs text-gray-400 shrink-0">{formatDateTimeTZ(job.started_at, tz)}</span>
      {job.total_grams > 0 && (
        <span className="text-xs text-gray-400 shrink-0">{job.total_grams.toFixed(1)}g</span>
      )}
      {job.nozzle_diameter && (
        <span className="text-xs text-blue-400 shrink-0">⌀{job.nozzle_diameter}</span>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Projects() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)
  const [deleting, setDeleting] = useState<Project | null>(null)
  const [managingPrints, setManagingPrints] = useState<Project | null>(null)

  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: api.getProjects,
  })

  const { data: managingDetail } = useQuery<ProjectDetail>({
    queryKey: ['projects', managingPrints?.id],
    queryFn: () => api.getProject(managingPrints!.id),
    enabled: !!managingPrints,
  })

  const createMut = useMutation({
    mutationFn: (data: { name: string; description: string | null }) => api.createProject(data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects'] }); setShowForm(false) },
  })

  const updateMut = useMutation({
    mutationFn: (data: { name: string; description: string | null }) =>
      api.updateProject(editing!.id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects'] }); setEditing(null) },
  })

  const deleteMut = useMutation({
    mutationFn: () => api.deleteProject(deleting!.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['projects'] }); setDeleting(null) },
  })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white">{t('projects.title')}</h1>
          <p className="text-sm text-gray-400">{t('projects.subtitle')}</p>
        </div>
        <button className="btn-primary flex items-center gap-2 px-3 py-2" onClick={() => setShowForm(true)}>
          <Plus size={16} />
          <span className="hidden sm:inline">{t('projects.new')}</span>
        </button>
      </div>

      {isLoading && <p className="text-sm text-gray-400">{t('common.loading')}</p>}
      {!isLoading && projects.length === 0 && (
        <div className="card text-center py-12">
          <FolderOpen size={32} className="mx-auto text-gray-600 mb-3" />
          <p className="text-gray-400">{t('projects.empty')}</p>
          <button className="mt-4 btn-primary px-4 py-2" onClick={() => setShowForm(true)}>
            {t('projects.createFirst')}
          </button>
        </div>
      )}
      {projects.map(p => (
        <ProjectCard
          key={p.id}
          project={p}
          onEdit={() => setEditing(p)}
          onDelete={() => setDeleting(p)}
          onManagePrints={() => setManagingPrints(p)}
        />
      ))}

      {showForm && (
        <ModalShell title={t('projects.newTitle')} onClose={() => setShowForm(false)}>
          <ProjectForm
            onSave={data => createMut.mutate(data)}
            onCancel={() => setShowForm(false)}
          />
        </ModalShell>
      )}

      {editing && (
        <ModalShell title={t('projects.editTitle')} onClose={() => setEditing(null)}>
          <ProjectForm
            initial={editing}
            onSave={data => updateMut.mutate(data)}
            onCancel={() => setEditing(null)}
          />
        </ModalShell>
      )}

      {deleting && (
        <ModalShell title={t('projects.deleteTitle')} onClose={() => setDeleting(null)}>
          <p className="text-sm text-gray-300 mb-4">
            {t('projects.deleteConfirm', { name: deleting.name })}
          </p>
          <p className="text-xs text-gray-400 mb-6">{t('projects.deleteNote')}</p>
          <div className="flex justify-end gap-2">
            <button className="btn-ghost px-4 py-2" onClick={() => setDeleting(null)}>
              {t('common.cancel')}
            </button>
            <button
              className="btn-danger px-4 py-2"
              onClick={() => deleteMut.mutate()}
              disabled={deleteMut.isPending}
            >
              {t('common.delete')}
            </button>
          </div>
        </ModalShell>
      )}

      {managingPrints && managingDetail && (
        <AssignPrintsModal
          project={managingDetail}
          onClose={() => setManagingPrints(null)}
        />
      )}
    </div>
  )
}
