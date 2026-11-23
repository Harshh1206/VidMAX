import { ClipboardPaste, LoaderCircle, Search, X } from 'lucide-react'
import { useState } from 'react'

interface UrlFormProps {
  value: string
  loading: boolean
  error: string | null
  onChange: (value: string) => void
  onSubmit: () => void
}

export function UrlForm({ value, loading, error, onChange, onSubmit }: UrlFormProps) {
  const [pasteError, setPasteError] = useState<string | null>(null)

  const handlePaste = async () => {
    setPasteError(null)
    try {
      if (!navigator.clipboard?.readText) {
        throw new Error('Clipboard unavailable')
      }
      const text = await navigator.clipboard.readText()
      onChange(text.trim())
    } catch {
      setPasteError('Paste didn’t work. Use your keyboard to paste the link.')
    }
  }

  return (
    <form
      className="mt-8"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit()
      }}
      noValidate
    >
      <label htmlFor="video-url" className="text-sm font-medium text-copy">
        Video link
      </label>

      <div className="mt-3 flex flex-col gap-3 sm:flex-row">
        <div className="relative min-w-0 flex-1">
          <input
            id="video-url"
            type="url"
            inputMode="url"
            autoComplete="url"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            value={value}
            onChange={(event) => {
              onChange(event.target.value)
              setPasteError(null)
            }}
            placeholder="https://www.youtube.com/watch?v=…"
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'url-error url-hint' : 'url-hint'}
            className="h-14 w-full min-w-0 rounded-xl border border-hairline bg-panel-raised/70 py-3 pl-4 pr-12 text-[15px] text-copy placeholder:text-muted/60 transition-colors hover:border-muted/50 focus:border-accent focus:bg-panel-raised focus:outline-none focus-visible:outline-none"
          />
          {value.length > 0 && (
            <button
              type="button"
              onClick={() => onChange('')}
              aria-label="Clear link"
              className="absolute right-2 top-2 grid size-10 place-items-center rounded-lg text-muted transition-colors hover:bg-hairline/60 hover:text-copy"
            >
              <X className="size-4" aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => void handlePaste()}
            disabled={loading}
            aria-label="Paste link from clipboard"
            title="Paste link from clipboard"
            className="grid size-14 shrink-0 place-items-center rounded-xl border border-hairline bg-panel-raised/70 text-muted transition-colors hover:border-accent/60 hover:text-accent-soft disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ClipboardPaste className="size-5" aria-hidden="true" />
          </button>
          <button
            type="submit"
            disabled={loading || value.trim().length === 0}
            className="inline-flex h-14 min-w-[9.5rem] flex-1 items-center justify-center gap-2 rounded-xl bg-accent px-5 text-[15px] font-semibold text-ink transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:bg-hairline disabled:text-muted sm:flex-none"
          >
            {loading ? (
              <>
                <LoaderCircle className="size-[18px] animate-spin" aria-hidden="true" />
                Inspecting
              </>
            ) : (
              <>
                <Search className="size-[18px]" aria-hidden="true" />
                Inspect link
              </>
            )}
          </button>
        </div>
      </div>

      <p id="url-hint" className="mt-3 text-xs leading-5 text-muted/75">
        YouTube and Facebook links only for now.
      </p>
      {error && (
        <p id="url-error" role="alert" className="mt-3 text-sm leading-6 text-bad">
          {error}
        </p>
      )}
      {pasteError && (
        <p role="alert" className="mt-2 text-sm leading-6 text-caution">
          {pasteError}
        </p>
      )}
    </form>
  )
}
