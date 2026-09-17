'use client'

import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Tabs } from '@/components/ui/Tabs'
import {
  ISSUE_STATUSES,
  MILESTONE_STATUSES,
  PROJECT_STATUSES,
  SEVERITIES,
  TASK_STATUSES,
  archiveDispatch,
  archiveStockItem,
  deleteDeal,
  archiveSupplier,
  archiveIssue,
  archiveMilestone,
  archiveProject,
  archiveTask,
  confirmComplete,
  createDeal,
  createDispatch,
  createStockItem,
  createSupplier,
  createIssue,
  createMilestone,
  createProject,
  createTask,
  fetchOps,
  setDispatchRule,
  type Confirmation,
  type Ops,
} from '@/lib/ops-client'

/**
 * Recording projects and tasks — `doc/15` S10.1.
 *
 * Three rules this component holds, each of which is easy to lose:
 *
 * **Nothing is computed here.** The counts a founder reads live on the
 * Operations tiles, served by `grounding/compute.py` from `calculators/ops.py`.
 * This page lists rows. A "3 of 12 done" line added here would be a figure the
 * browser invented, which is I1's prohibition arriving from the friendliest
 * possible direction.
 *
 * **No permission rule is copied.** Whether this caller may write is
 * `routes/ops._may_write`'s decision and arrives as a 403 with a sentence
 * written for a person. Hiding the form on a guess would be a second copy of
 * the rule, and the copy that disagrees is the one on the screen.
 *
 * **Archive, never delete.** The button says what it does.
 */

type Feedback = { kind: 'error' | 'done'; text: string } | null

/**
 * The page's controls, in two constants.
 *
 * Every input, select and date field here reads `FIELD` and every label reads
 * `LABEL`, which is why the audit's finding about this page — that its controls
 * were the browser's defaults beside a product with a 14px radius and a warm
 * border — is fixable in two lines rather than twenty-five call sites.
 *
 * `.control` and `.field-label` are the same classes the rest of the product's
 * forms use, so `/work` and `/settings` stopped being two conventions by
 * pointing at one. `.control` handles the native select's arrow and the date
 * picker's indicator; see `globals.css`.
 */
const FIELD = 'control'
const LABEL = 'field-label'

function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

/**
 * *"Is this all of your projects?"* — `doc/15` S10.2, ADR 0035 (D29).
 *
 * **The one fact the database cannot hold about itself.** Every row is evidence
 * that a project exists; nothing in the table is evidence that no other project
 * does. Without an answer here, every ops rate — S10.4's on-time dispatch and
 * everything after it — divides by a denominator nobody vouched for.
 *
 * Asked per entity, because somebody can plausibly have recorded every project
 * and a third of the tasks, and one switch covering both would let the honest
 * half vouch for the careless one.
 *
 * **Re-confirmable, and never a checkbox.** A checkbox reads as a setting that
 * stays true; this is a statement somebody made on a day, and it goes stale
 * without anybody being told. So the answer is always shown with its date, and
 * saying it again appends rather than replaces.
 */
function Completeness({
  noun,
  confirmed,
  busy,
  onConfirm,
}: {
  noun: string
  confirmed: Confirmation | null
  busy: boolean
  onConfirm: () => void
}) {
  return (
    <div className="flex max-w-2xl flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-data border border-ink-100 bg-bone-50 px-4 py-2.5">
      {confirmed ? (
        <p className="text-meta text-ink-500">
          You confirmed this is all of your {noun}, as of {confirmed.complete_as_of}.
        </p>
      ) : (
        <p className="max-w-read text-meta text-ink-600">
          Is this all of your {noun}? Until you say, NEXUS counts what is written down and
          will not work out any rate from it.
        </p>
      )}

      <Button
        size="sm"
        variant="secondary"
        onClick={onConfirm}
        loading={busy}
        loadingLabel="Recording…"
        aria-label={`Confirm this is all of your ${noun}`}
        className="shrink-0"
      >
        {confirmed ? 'Still all of them' : `Yes — this is all of my ${noun}`}
      </Button>
    </div>
  )
}

/**
 * The eight things a founder can record, as one rail.
 *
 * `count` is how many of that kind exist, and it is a length rather than a
 * computed figure — I1 is about numbers *derived* from records, and "how many
 * rows are in this list" is the list. Everything a founder reads as a
 * measurement still comes from `calculators/ops.py` via the Operations tiles.
 */
const TABS = [
  { key: 'projects', label: 'Projects' },
  { key: 'tasks', label: 'Tasks' },
  { key: 'milestones', label: 'Milestones' },
  { key: 'issues', label: 'Issues' },
  { key: 'dispatch', label: 'Orders' },
  { key: 'stock', label: 'Stock' },
  { key: 'suppliers', label: 'Suppliers' },
  { key: 'deals', label: 'Deals' },
] as const

export function WorkRecorder() {
  /**
   * Which kind of record is on screen.
   *
   * The audit's finding about this page was that it rendered all eight forms,
   * expanded, in one 4,063-pixel scroll — so recording a supplier meant
   * scrolling past six forms for other things, and each form was followed by a
   * near-identical "Is this all of your X?" card, eight times. The page read as
   * a blank input sheet rather than as a workspace with content in it.
   *
   * Every section stays **mounted** and is hidden with `display: none` rather
   * than unmounted. That is deliberate: a half-typed project must survive a
   * glance at the task list, and unmounting would discard it silently. The cost
   * is that all eight forms exist in the DOM, which is what they did before
   * anyway — the change is that seven of them are no longer between the reader
   * and the eighth.
   */
  const [tab, setTab] = useState<string>('projects')
  const [ops, setOps] = useState<Ops | null>(null)
  const [loadError, setLoadError] = useState('')
  // **One flag per form, not one for the page.** Shared, pressing "Record
  // project" relabelled the task button to "Recording…" and disabled it — the
  // screen claiming a task was being saved when none was. Against Neon a write
  // plus its reload is a few seconds, so it was not a flicker.
  const [savingProject, setSavingProject] = useState(false)
  const [savingTask, setSavingTask] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const [confirming, setConfirming] = useState('')
  const [feedback, setFeedback] = useState<Feedback>(null)

  const [projectName, setProjectName] = useState('')
  const [projectStatus, setProjectStatus] = useState<string>('active')
  const [projectClient, setProjectClient] = useState('')
  const [projectDue, setProjectDue] = useState('')

  const [taskTitle, setTaskTitle] = useState('')
  const [taskStatus, setTaskStatus] = useState<string>('todo')
  const [taskProject, setTaskProject] = useState('')
  const [taskDue, setTaskDue] = useState('')

  const [milestoneTitle, setMilestoneTitle] = useState('')
  const [milestoneProject, setMilestoneProject] = useState('')
  const [milestonePlanned, setMilestonePlanned] = useState('')
  const [savingMilestone, setSavingMilestone] = useState(false)

  const [dispatchRef, setDispatchRef] = useState('')
  const [dispatchPromised, setDispatchPromised] = useState('')
  const [dispatchSent, setDispatchSent] = useState('')
  const [savingDispatch, setSavingDispatch] = useState(false)
  const [grace, setGrace] = useState('')

  const [stockName, setStockName] = useState('')
  const [stockOnHand, setStockOnHand] = useState('')
  const [stockMinimum, setStockMinimum] = useState('')
  const [savingStock, setSavingStock] = useState(false)

  const [dealName, setDealName] = useState('')
  const [dealAmount, setDealAmount] = useState('')
  const [savingDeal, setSavingDeal] = useState(false)

  const [supplierName, setSupplierName] = useState('')
  const [supplierSpend, setSupplierSpend] = useState('')
  const [savingSupplier, setSavingSupplier] = useState(false)
  const [savingRule, setSavingRule] = useState(false)

  const [issueTitle, setIssueTitle] = useState('')
  const [issueSeverity, setIssueSeverity] = useState<string>('medium')
  const [issueProject, setIssueProject] = useState('')
  const [issueDue, setIssueDue] = useState('')
  const [savingIssue, setSavingIssue] = useState(false)

  async function reload() {
    try {
      setOps(await fetchOps())
      setLoadError('')
    } catch (error) {
      setLoadError(messageOf(error, 'Could not read what you have recorded.'))
    }
  }

  useEffect(() => {
    void reload()
  }, [])

  async function submitProject(event: React.FormEvent) {
    event.preventDefault()
    setSavingProject(true)
    setFeedback(null)
    try {
      await createProject({
        name: projectName,
        status: projectStatus,
        // Empty is absent, not "". A blank client name stored as an empty
        // string is a value somebody typed, which it is not (I10).
        client: projectClient.trim() || null,
        due_on: projectDue || null,
      })
      setProjectName('')
      setProjectClient('')
      setProjectDue('')
      setFeedback({ kind: 'done', text: 'Project recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that project.') })
    } finally {
      setSavingProject(false)
    }
  }

  async function submitTask(event: React.FormEvent) {
    event.preventDefault()
    setSavingTask(true)
    setFeedback(null)
    try {
      await createTask({
        title: taskTitle,
        status: taskStatus,
        project_id: taskProject || null,
        due_on: taskDue || null,
      })
      setTaskTitle('')
      setTaskDue('')
      setFeedback({ kind: 'done', text: 'Task recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that task.') })
    } finally {
      setSavingTask(false)
    }
  }

  async function submitMilestone(event: React.FormEvent) {
    event.preventDefault()
    setSavingMilestone(true)
    setFeedback(null)
    try {
      await createMilestone({
        title: milestoneTitle,
        project_id: milestoneProject,
        planned_on: milestonePlanned,
        status: 'planned',
      })
      setMilestoneTitle('')
      setMilestonePlanned('')
      setFeedback({ kind: 'done', text: 'Milestone recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that milestone.') })
    } finally {
      setSavingMilestone(false)
    }
  }

  async function submitIssue(event: React.FormEvent) {
    event.preventDefault()
    setSavingIssue(true)
    setFeedback(null)
    try {
      await createIssue({
        title: issueTitle,
        status: 'open',
        severity: issueSeverity,
        project_id: issueProject || null,
        due_on: issueDue || null,
      })
      setIssueTitle('')
      setIssueDue('')
      setFeedback({ kind: 'done', text: 'Issue recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that issue.') })
    } finally {
      setSavingIssue(false)
    }
  }

  async function submitDispatch(event: React.FormEvent) {
    event.preventDefault()
    setSavingDispatch(true)
    setFeedback(null)
    try {
      await createDispatch({
        reference: dispatchRef,
        promised_on: dispatchPromised,
        dispatched_on: dispatchSent || null,
        project_id: null,
      })
      setDispatchRef('')
      setDispatchSent('')
      setFeedback({ kind: 'done', text: 'Order recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that order.') })
    } finally {
      setSavingDispatch(false)
    }
  }

  async function submitRule(event: React.FormEvent) {
    event.preventDefault()
    setSavingRule(true)
    setFeedback(null)
    try {
      await setDispatchRule(Number(grace))
      setFeedback({ kind: 'done', text: 'Saved. The on-time figure can be worked out now.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not save that rule.') })
    } finally {
      setSavingRule(false)
    }
  }

  async function submitStock(event: React.FormEvent) {
    event.preventDefault()
    setSavingStock(true)
    setFeedback(null)
    try {
      await createStockItem({
        name: stockName,
        on_hand: Number(stockOnHand),
        minimum: Number(stockMinimum),
        unit: null,
      })
      setStockName('')
      setStockOnHand('')
      setStockMinimum('')
      setFeedback({ kind: 'done', text: 'Stock line recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that stock line.') })
    } finally {
      setSavingStock(false)
    }
  }

  async function submitSupplier(event: React.FormEvent) {
    event.preventDefault()
    setSavingSupplier(true)
    setFeedback(null)
    try {
      await createSupplier({
        name: supplierName,
        // Major units in, minor units stored — money in a float stops adding
        // up, and the API takes the integer.
        spend_minor: supplierSpend ? Math.round(Number(supplierSpend) * 100) : null,
        category: null,
      })
      setSupplierName('')
      setSupplierSpend('')
      setFeedback({ kind: 'done', text: 'Supplier recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that supplier.') })
    } finally {
      setSavingSupplier(false)
    }
  }

  async function submitDeal(event: React.FormEvent) {
    event.preventDefault()
    setSavingDeal(true)
    setFeedback(null)
    try {
      await createDeal({
        name: dealName,
        // Together or neither — an amount with no currency is a number with no
        // unit, and the table's CHECK says the same.
        amount_minor: dealAmount ? Math.round(Number(dealAmount) * 100) : null,
        currency: dealAmount ? 'OMR' : null,
        stage: null,
      })
      setDealName('')
      setDealAmount('')
      setFeedback({ kind: 'done', text: 'Deal recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that deal.') })
    } finally {
      setSavingDeal(false)
    }
  }

  const ARCHIVERS = {
    project: archiveProject,
    task: archiveTask,
    milestone: archiveMilestone,
    issue: archiveIssue,
    dispatch: archiveDispatch,
    stock: archiveStockItem,
    supplier: archiveSupplier,
    deal: deleteDeal,
  } as const

  async function archive(kind: keyof typeof ARCHIVERS, id: string) {
    setArchiving(true)
    setFeedback(null)
    try {
      await ARCHIVERS[kind](id)
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not archive that.') })
    } finally {
      setArchiving(false)
    }
  }

  async function confirm(entity: string) {
    setConfirming(entity)
    setFeedback(null)
    try {
      // `null` rather than today's date: the API supplies the date. Two clocks
      // on one fact, and the browser's is the one nobody can audit.
      await confirmComplete(entity, null)
      setFeedback({ kind: 'done', text: 'Thank you — that is recorded.' })
      await reload()
    } catch (error) {
      setFeedback({ kind: 'error', text: messageOf(error, 'Could not record that.') })
    } finally {
      setConfirming('')
    }
  }

  const projects = ops?.projects ?? []
  const tasks = ops?.tasks ?? []
  const milestones = ops?.milestones ?? []
  const issues = ops?.issues ?? []
  const dispatches = ops?.dispatches ?? []
  const stock = ops?.stock ?? []
  const suppliers = ops?.suppliers ?? []
  const deals = ops?.deals ?? []
  const nothingYet =
    ops !== null &&
    projects.length === 0 &&
    tasks.length === 0 &&
    milestones.length === 0 &&
    issues.length === 0 &&
    dispatches.length === 0 &&
    stock.length === 0 &&
    suppliers.length === 0 &&
    deals.length === 0
  /**
   * How many of each kind exist, for the rail.
   *
   * A length, not a measurement. I1 forbids the browser *deriving* a figure —
   * "8 of 12 done" would be arithmetic nobody computed server-side — and the
   * number of rows in a list the browser is already holding is not that. It is
   * also the one thing that makes a rail better than a scroll: you can see
   * where your records are without opening each tab to find out.
   *
   * `undefined` rather than `0` while `ops` is null, so the rail shows no count
   * rather than claiming an empty list during the load (I10). `Tabs` renders
   * nothing for a count it is not given.
   */
  const counts = useMemo<Record<string, number | undefined>>(
    () =>
      ops === null
        ? {}
        : {
            projects: projects.length,
            tasks: tasks.length,
            milestones: milestones.length,
            issues: issues.length,
            dispatch: dispatches.length,
            stock: stock.length,
            suppliers: suppliers.length,
            deals: deals.length,
          },
    [ops, projects, tasks, milestones, issues, dispatches, stock, suppliers, deals],
  )

  const confirmedFor = (entity: string) =>
    (ops?.completeness ?? []).find((entry) => entry.entity === entity) ?? null

  return (
    <div className="mt-8 flex flex-col gap-8">
      {loadError ? (
        <p role="alert" className="text-sm text-clay-600">
          {loadError}
        </p>
      ) : null}

      {feedback ? (
        <p
          role="status"
          className={`text-sm ${feedback.kind === 'error' ? 'text-clay-600' : 'text-steel-600'}`}
        >
          {feedback.text}
        </p>
      ) : null}

      {nothingYet ? (
        /* The state the Operations tiles render as `locked`. Said here in the
           same words the tile uses, so somebody who arrived from it recognises
           where they landed. */
        <p className="max-w-prose rounded-data border border-ink-100 bg-bone-50 px-4 py-3 text-body text-ink-600">
          Nothing recorded yet. Your first project turns on the Operations tiles — there is no
          tool to connect for this one, because the records are your own.
        </p>
      ) : null}

      <div className="sticky top-[var(--app-header-h)] z-sticky -mx-[var(--app-x)] border-b border-ink-100 bg-bone-50/90 px-[var(--app-x)] py-2 backdrop-blur-md">
        <Tabs
          label="What to record"
          active={tab}
          onChange={setTab}
          tabs={TABS.map((entry) => ({
            key: entry.key,
            label: entry.label,
            count: counts[entry.key],
          }))}
        />
      </div>

      <section
        aria-label="Projects"
        className={tab === 'projects' ? 'flex flex-col gap-4' : 'hidden'}
      >

        <form onSubmit={submitProject} className="grid max-w-2xl gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={LABEL} htmlFor="project-name">
              Name
            </label>
            <input
              id="project-name"
              required
              maxLength={200}
              value={projectName}
              onChange={(event) => setProjectName(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="project-status">
              Status
            </label>
            <select
              id="project-status"
              value={projectStatus}
              onChange={(event) => setProjectStatus(event.target.value)}
              className={`mt-1 ${FIELD}`}
            >
              {PROJECT_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={LABEL} htmlFor="project-client">
              Client <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="project-client"
              maxLength={200}
              value={projectClient}
              onChange={(event) => setProjectClient(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="project-due">
              Due <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="project-due"
              type="date"
              value={projectDue}
              onChange={(event) => setProjectDue(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
            {/* Stated rather than assumed away: nothing with no date is ever
                counted as late, and somebody deciding whether to fill this in
                deserves to know that before they skip it. */}
            <p className="mt-1 text-2xs text-ink-400">
              Left blank, it is never counted as overdue.
            </p>
          </div>

          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={savingProject}
              className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
            >
              {savingProject ? 'Recording…' : 'Record project'}
            </button>
          </div>
        </form>

        {projects.length > 0 ? (
          <Completeness
            noun="projects"
            confirmed={confirmedFor('projects')}
            busy={confirming === 'projects'}
            onConfirm={() => void confirm('projects')}
          />
        ) : null}

        {projects.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {projects.map((project) => (
              <li key={project.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{project.name}</span>
                <span className="font-mono text-2xs uppercase tracking-[0.08em] text-ink-500">
                  {project.status}
                </span>
                <span className="text-2xs text-ink-400">{project.due_on ?? 'no date'}</span>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('project', project.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section
        aria-label="Tasks"
        className={tab === 'tasks' ? 'flex flex-col gap-4' : 'hidden'}
      >

        <form onSubmit={submitTask} className="grid max-w-2xl gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={LABEL} htmlFor="task-title">
              Title
            </label>
            <input
              id="task-title"
              required
              maxLength={300}
              value={taskTitle}
              onChange={(event) => setTaskTitle(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="task-status">
              Status
            </label>
            <select
              id="task-status"
              value={taskStatus}
              onChange={(event) => setTaskStatus(event.target.value)}
              className={`mt-1 ${FIELD}`}
            >
              {TASK_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={LABEL} htmlFor="task-project">
              Project <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <select
              id="task-project"
              value={taskProject}
              onChange={(event) => setTaskProject(event.target.value)}
              className={`mt-1 ${FIELD}`}
            >
              <option value="">No project</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={LABEL} htmlFor="task-due">
              Due <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="task-due"
              type="date"
              value={taskDue}
              onChange={(event) => setTaskDue(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={savingTask}
              className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
            >
              {savingTask ? 'Recording…' : 'Record task'}
            </button>
          </div>
        </form>

        {tasks.length > 0 ? (
          <Completeness
            noun="tasks"
            confirmed={confirmedFor('tasks')}
            busy={confirming === 'tasks'}
            onConfirm={() => void confirm('tasks')}
          />
        ) : null}

        {tasks.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {tasks.map((task) => (
              <li key={task.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{task.title}</span>
                <span className="font-mono text-2xs uppercase tracking-[0.08em] text-ink-500">
                  {task.status}
                </span>
                <span className="text-2xs text-ink-400">{task.due_on ?? 'no date'}</span>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('task', task.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section
        aria-label="Milestones"
        className={tab === 'milestones' ? 'flex flex-col gap-4' : 'hidden'}
      >

        {projects.length === 0 ? (
          /* A milestone belongs to a project — it is a point in that project's
             plan. Saying so beats a form whose only option is "no project". */
          <p className="max-w-prose text-sm text-ink-500">
            Record a project first. A milestone is a point in a project&rsquo;s plan, so it
            needs one to belong to.
          </p>
        ) : (
          <form onSubmit={submitMilestone} className="grid max-w-2xl gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={LABEL} htmlFor="milestone-title">
                Title
              </label>
              <input
                id="milestone-title"
                required
                maxLength={300}
                value={milestoneTitle}
                onChange={(event) => setMilestoneTitle(event.target.value)}
                className={`mt-1 ${FIELD}`}
              />
            </div>

            <div>
              <label className={LABEL} htmlFor="milestone-project">
                Project
              </label>
              <select
                id="milestone-project"
                required
                value={milestoneProject}
                onChange={(event) => setMilestoneProject(event.target.value)}
                className={`mt-1 ${FIELD}`}
              >
                <option value="">Choose a project</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className={LABEL} htmlFor="milestone-planned">
                Planned date
              </label>
              <input
                id="milestone-planned"
                type="date"
                required
                value={milestonePlanned}
                onChange={(event) => setMilestonePlanned(event.target.value)}
                className={`mt-1 ${FIELD}`}
              />
              {/* Required, unlike every other date on this page. */}
              <p className="mt-1 text-2xs text-ink-400">
                A timeline cannot draw a milestone with no date.
              </p>
            </div>

            <div className="sm:col-span-2">
              <button
                type="submit"
                disabled={savingMilestone}
                className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
              >
                {savingMilestone ? 'Recording…' : 'Record milestone'}
              </button>
            </div>
          </form>
        )}

        {milestones.length > 0 ? (
          <Completeness
            noun="milestones"
            confirmed={confirmedFor('milestones')}
            busy={confirming === 'milestones'}
            onConfirm={() => void confirm('milestones')}
          />
        ) : null}

        {milestones.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {milestones.map((milestone) => (
              <li key={milestone.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{milestone.title}</span>
                <span className="font-mono text-2xs uppercase tracking-[0.08em] text-ink-500">
                  {milestone.status}
                </span>
                <span className="text-2xs text-ink-400">{milestone.planned_on}</span>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('milestone', milestone.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section
        aria-label="Issues and snags"
        className={tab === 'issues' ? 'flex flex-col gap-4' : 'hidden'}
      >

        <form onSubmit={submitIssue} className="grid max-w-2xl gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={LABEL} htmlFor="issue-title">
              What is the issue?
            </label>
            <input
              id="issue-title"
              required
              maxLength={300}
              value={issueTitle}
              onChange={(event) => setIssueTitle(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="issue-severity">
              Severity
            </label>
            <select
              id="issue-severity"
              value={issueSeverity}
              onChange={(event) => setIssueSeverity(event.target.value)}
              className={`mt-1 ${FIELD}`}
            >
              {SEVERITIES.map((severity) => (
                <option key={severity} value={severity}>
                  {severity}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={LABEL} htmlFor="issue-project">
              Project <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <select
              id="issue-project"
              value={issueProject}
              onChange={(event) => setIssueProject(event.target.value)}
              className={`mt-1 ${FIELD}`}
            >
              <option value="">No project</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={LABEL} htmlFor="issue-due">
              Due <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="issue-due"
              type="date"
              value={issueDue}
              onChange={(event) => setIssueDue(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div className="sm:col-span-2">
            <button
              type="submit"
              disabled={savingIssue}
              className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
            >
              {savingIssue ? 'Recording…' : 'Record issue'}
            </button>
          </div>
        </form>

        {issues.length > 0 ? (
          <Completeness
            noun="issues"
            confirmed={confirmedFor('issues')}
            busy={confirming === 'issues'}
            onConfirm={() => void confirm('issues')}
          />
        ) : null}

        {issues.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {issues.map((issue) => (
              <li key={issue.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{issue.title}</span>
                <span className="font-mono text-2xs uppercase tracking-[0.08em] text-ink-500">
                  {issue.severity}
                </span>
                <span className="font-mono text-2xs uppercase tracking-[0.08em] text-ink-400">
                  {issue.status}
                </span>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('issue', issue.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section
        aria-label="Orders and dispatch"
        className={tab === 'dispatch' ? 'flex flex-col gap-4' : 'hidden'}
      >

        {/* **The rule the on-time figure is computed under — D32.**
            Asked as a number rather than read from the onboarding answer, which
            is free prose: parsing "a day or two after we said" into a threshold
            would be us inventing the rule this figure is judged by. Until it is
            set, the tile shows counts and says what is missing. */}
        <form
          onSubmit={submitRule}
          className="flex max-w-2xl flex-wrap items-end gap-3 rounded-xl border border-ink-100 bg-bone-50 px-4 py-3"
        >
          <div className="grow">
            <label className={LABEL} htmlFor="dispatch-grace">
              When is an order late?
            </label>
            <p className="mt-1 text-sm text-ink-600">
              {ops?.grace_days === null || ops?.grace_days === undefined
                ? 'Until you say, NEXUS counts your orders but will not work out an on-time percentage.'
                : `Now: more than ${ops.grace_days} ${ops.grace_days === 1 ? 'day' : 'days'} past the promised date.`}
            </p>
          </div>
          <div>
            <label className={LABEL} htmlFor="dispatch-grace">
              Days of grace
            </label>
            <input
              id="dispatch-grace"
              type="number"
              min={0}
              max={365}
              required
              value={grace}
              onChange={(event) => setGrace(event.target.value)}
              className={`mt-1 w-28 ${FIELD}`}
            />
          </div>
          <button
            type="submit"
            disabled={savingRule}
            className="rounded-lg border border-ink-200 px-3 py-2 text-sm font-medium text-ink-700 hover:border-ink-300 hover:text-ink-900 disabled:opacity-60"
          >
            {savingRule ? 'Saving…' : 'Save rule'}
          </button>
        </form>

        <form onSubmit={submitDispatch} className="grid max-w-2xl gap-3 sm:grid-cols-3">
          <div>
            <label className={LABEL} htmlFor="dispatch-ref">
              Order reference
            </label>
            <input
              id="dispatch-ref"
              required
              maxLength={200}
              value={dispatchRef}
              onChange={(event) => setDispatchRef(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="dispatch-promised">
              Promised for
            </label>
            <input
              id="dispatch-promised"
              type="date"
              required
              value={dispatchPromised}
              onChange={(event) => setDispatchPromised(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>

          <div>
            <label className={LABEL} htmlFor="dispatch-sent">
              Sent on <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="dispatch-sent"
              type="date"
              value={dispatchSent}
              onChange={(event) => setDispatchSent(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
            {/* Blank is the ordinary state of a live order, and it is what keeps
                the rate's denominator honest. */}
            <p className="mt-1 text-2xs text-ink-400">
              Leave blank until it goes out. Orders still waiting are not counted in the
              on-time figure.
            </p>
          </div>

          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={savingDispatch}
              className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
            >
              {savingDispatch ? 'Recording…' : 'Record order'}
            </button>
          </div>
        </form>

        {dispatches.length > 0 ? (
          <Completeness
            noun="orders"
            confirmed={confirmedFor('dispatches')}
            busy={confirming === 'dispatches'}
            onConfirm={() => void confirm('dispatches')}
          />
        ) : null}

        {dispatches.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {dispatches.map((dispatch) => (
              <li key={dispatch.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{dispatch.reference}</span>
                <span className="text-2xs text-ink-500">promised {dispatch.promised_on}</span>
                <span className="text-2xs text-ink-400">
                  {dispatch.dispatched_on ? `sent ${dispatch.dispatched_on}` : 'not sent'}
                </span>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('dispatch', dispatch.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section
        aria-label="Stock"
        className={tab === 'stock' ? 'flex flex-col gap-4' : 'hidden'}
      >
        {/* Recording one of these is what answers "do you hold stock, or order
            per job?" — asked at onboarding as prose that nothing reads. The
            record is the answer. */}
        <p className="max-w-prose text-sm text-ink-600">
          The minimum is yours. NEXUS says which lines are under it and by how much, and
          never what to order — that needs lead times and consumption nobody has given it.
        </p>

        <form onSubmit={submitStock} className="grid max-w-2xl gap-3 sm:grid-cols-3">
          <div>
            <label className={LABEL} htmlFor="stock-name">
              Item
            </label>
            <input
              id="stock-name"
              required
              maxLength={200}
              value={stockName}
              onChange={(event) => setStockName(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="stock-on-hand">
              On hand
            </label>
            <input
              id="stock-on-hand"
              type="number"
              min={0}
              required
              value={stockOnHand}
              onChange={(event) => setStockOnHand(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="stock-minimum">
              Minimum
            </label>
            <input
              id="stock-minimum"
              type="number"
              min={0}
              required
              value={stockMinimum}
              onChange={(event) => setStockMinimum(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>
          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={savingStock}
              className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
            >
              {savingStock ? 'Recording…' : 'Record stock line'}
            </button>
          </div>
        </form>

        {stock.length > 0 ? (
          <Completeness
            noun="stock lines"
            confirmed={confirmedFor('stock')}
            busy={confirming === 'stock'}
            onConfirm={() => void confirm('stock')}
          />
        ) : null}

        {stock.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {stock.map((item) => (
              <li key={item.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{item.name}</span>
                <span className="text-2xs text-ink-500">
                  {item.on_hand} on hand, minimum {item.minimum}
                </span>
                {item.on_hand < item.minimum ? (
                  <span className="font-mono text-2xs uppercase tracking-[0.08em] text-clay-600">
                    short {item.minimum - item.on_hand}
                  </span>
                ) : null}
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('stock', item.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section
        aria-label="Suppliers"
        className={tab === 'suppliers' ? 'flex flex-col gap-4' : 'hidden'}
      >
        {/* The founder enters what they spend. The share is what NEXUS works
            out — asking for a percentage would be a self-reported figure
            wearing a computed one's clothes. */}
        <p className="max-w-prose text-sm text-ink-600">
          Enter what you spend with each one and NEXUS works out how exposed you are to the
          largest. Leave the amount blank if you do not have it — that supplier is counted,
          and left out of the share.
        </p>

        <form onSubmit={submitSupplier} className="grid max-w-2xl gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className={LABEL} htmlFor="supplier-name">
              Supplier
            </label>
            <input
              id="supplier-name"
              required
              maxLength={200}
              value={supplierName}
              onChange={(event) => setSupplierName(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="supplier-spend">
              Spend <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="supplier-spend"
              type="number"
              min={0}
              step="0.01"
              value={supplierSpend}
              onChange={(event) => setSupplierSpend(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>
          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={savingSupplier}
              className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
            >
              {savingSupplier ? 'Recording…' : 'Record supplier'}
            </button>
          </div>
        </form>

        {suppliers.length > 0 ? (
          <Completeness
            noun="suppliers"
            confirmed={confirmedFor('suppliers')}
            busy={confirming === 'suppliers'}
            onConfirm={() => void confirm('suppliers')}
          />
        ) : null}

        {suppliers.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {suppliers.map((supplier) => (
              <li key={supplier.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{supplier.name}</span>
                <span className="text-2xs text-ink-400">
                  {supplier.spend_minor === null
                    ? 'no figure'
                    : (supplier.spend_minor / 100).toLocaleString()}
                </span>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('supplier', supplier.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Archive
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section
        aria-label="Deals"
        className={tab === 'deals' ? 'flex flex-col gap-4' : 'hidden'}
      >
        {/* These are counted on their own Sales tile and never mixed with a
            connected CRM's — `retrieval/deals.py` partitions the table by
            provenance (ADR 0038). */}
        <p className="max-w-prose text-sm text-ink-600">
          For tracking deals without a CRM. They are counted separately from anything a
          connected CRM reports, and the tile says they are your own records.
        </p>

        <form onSubmit={submitDeal} className="grid max-w-2xl gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className={LABEL} htmlFor="deal-name">
              Deal
            </label>
            <input
              id="deal-name"
              required
              maxLength={300}
              value={dealName}
              onChange={(event) => setDealName(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="deal-amount">
              Amount <span className="font-normal text-ink-400">(optional)</span>
            </label>
            <input
              id="deal-amount"
              type="number"
              min={0}
              step="0.01"
              value={dealAmount}
              onChange={(event) => setDealAmount(event.target.value)}
              className={`mt-1 ${FIELD}`}
            />
            <p className="mt-1 text-2xs text-ink-400">
              Left blank, it is counted and not added to the total.
            </p>
          </div>
          <div className="sm:col-span-3">
            <button
              type="submit"
              disabled={savingDeal}
              className="rounded-lg bg-ink-800 px-4 py-2 text-sm font-medium text-bone-50 disabled:opacity-60"
            >
              {savingDeal ? 'Recording…' : 'Record deal'}
            </button>
          </div>
        </form>

        {deals.length > 0 ? (
          <ul className="max-w-2xl divide-y divide-ink-100 rounded-xl border border-ink-100">
            {deals.map((deal) => (
              <li key={deal.id} className="flex flex-wrap items-baseline gap-x-3 px-4 py-3">
                <span className="min-w-0 grow text-sm text-ink-800">{deal.name}</span>
                <span className="text-2xs text-ink-400">
                  {deal.amount_minor === null
                    ? 'no amount'
                    : `${deal.currency} ${(deal.amount_minor / 100).toLocaleString()}`}
                </span>
                <button
                  type="button"
                  disabled={archiving}
                  onClick={() => void archive('deal', deal.id)}
                  className="text-2xs text-ink-500 underline hover:text-ink-800 disabled:opacity-60"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    </div>
  )
}
