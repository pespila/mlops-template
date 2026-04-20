import { Check, Pencil, Trash2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface EditableHeadingProps {
  value: string;
  onSave: (next: string) => void | Promise<void>;
  onDelete?: () => void | Promise<void>;
  deleteConfirm?: string;
  placeholder?: string;
  className?: string;
  saving?: boolean;
  deleting?: boolean;
}

/**
 * Inline-editable heading used on Experiment / Run / Model detail pages.
 * Click the pencil to rename; click the trash to delete (with confirm).
 */
export function EditableHeading({
  value,
  onSave,
  onDelete,
  deleteConfirm = "Delete this? This cannot be undone.",
  placeholder,
  className,
  saving,
  deleting,
}: EditableHeadingProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  async function handleSave() {
    const next = draft.trim();
    if (!next || next === value) {
      setEditing(false);
      return;
    }
    await onSave(next);
    setEditing(false);
  }

  return (
    <div className={"flex items-center gap-2 " + (className ?? "")}>
      {editing ? (
        <>
          <input
            ref={inputRef}
            value={draft}
            onChange={(ev) => setDraft(ev.target.value)}
            onKeyDown={(ev) => {
              if (ev.key === "Enter") handleSave();
              if (ev.key === "Escape") setEditing(false);
            }}
            placeholder={placeholder}
            className="min-w-0 flex-1 rounded border border-[color:var(--border)] bg-bg px-2 py-1 font-display text-display-lg font-extrabold tracking-tight text-fg1 focus:border-primary focus:outline-none"
          />
          <button
            type="button"
            aria-label="Save"
            onClick={handleSave}
            disabled={saving}
            className="rounded p-2 text-primary hover:bg-[color:var(--primary-soft)] disabled:opacity-40"
          >
            <Check size={18} strokeWidth={2} />
          </button>
          <button
            type="button"
            aria-label="Cancel"
            onClick={() => setEditing(false)}
            className="rounded p-2 text-fg3 hover:bg-bg-muted"
          >
            <X size={18} strokeWidth={2} />
          </button>
        </>
      ) : (
        <>
          <h1 className="min-w-0 truncate font-display text-display-lg font-extrabold tracking-tight text-fg1">
            {value}
          </h1>
          <button
            type="button"
            aria-label="Rename"
            onClick={() => setEditing(true)}
            className="rounded p-2 text-fg3 hover:bg-bg-muted hover:text-fg1"
          >
            <Pencil size={16} strokeWidth={2} />
          </button>
          {onDelete ? (
            <button
              type="button"
              aria-label="Delete"
              disabled={deleting}
              onClick={() => {
                if (window.confirm(deleteConfirm)) onDelete();
              }}
              className="rounded p-2 text-fg3 hover:bg-danger/10 hover:text-danger disabled:opacity-40"
            >
              <Trash2 size={16} strokeWidth={2} />
            </button>
          ) : null}
        </>
      )}
    </div>
  );
}
