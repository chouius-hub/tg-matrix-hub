import { Layers } from 'lucide-react'

interface PlaceholderPageProps {
  title: string
  phase: string
  description: string
}

/**
 * Phase 4 与 Phase 5 业务模块占位页。
 */
export function PlaceholderPage({ title, phase, description }: PlaceholderPageProps) {
  return (
    <div className="rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 p-10 text-center space-y-3">
      <div className="w-12 h-12 rounded-xl bg-indigo-500/10 text-indigo-500 flex items-center justify-center mx-auto">
        <Layers className="w-6 h-6" />
      </div>
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto">
        {description}
      </p>
      <div className="inline-block px-3 py-1 text-xs rounded-full bg-indigo-500/10 text-indigo-500 font-medium">
        将于 {phase} 完成前后端联调上线
      </div>
    </div>
  )
}

