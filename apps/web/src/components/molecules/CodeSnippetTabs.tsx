import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

export type CodeLanguage = "curl" | "python" | "javascript";

interface CodeSnippetTabsProps {
  snippets: Record<CodeLanguage, string>;
  className?: string;
}

const TABS: Array<{ key: CodeLanguage; label: string }> = [
  { key: "curl", label: "curl" },
  { key: "python", label: "Python" },
  { key: "javascript", label: "JavaScript" },
];

export function CodeSnippetTabs({ snippets, className }: CodeSnippetTabsProps) {
  const [active, setActive] = useState<CodeLanguage>("curl");
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(snippets[active]);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-[color:var(--border-primary)] bg-teal-50",
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-[color:var(--border-primary)] bg-bg/70 px-2">
        <div role="tablist" className="flex">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={active === tab.key}
              onClick={() => setActive(tab.key)}
              className={cn(
                "px-3 py-2 text-sm font-semibold transition-colors",
                active === tab.key
                  ? "text-primary border-b-2 border-primary"
                  : "text-fg2 hover:text-fg1",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs font-semibold text-fg2 hover:bg-bg-muted hover:text-fg1"
        >
          {copied ? (
            <>
              <Check size={14} strokeWidth={2} /> Copied
            </>
          ) : (
            <>
              <Copy size={14} strokeWidth={2} /> Copy
            </>
          )}
        </button>
      </div>
      <pre className="m-0 overflow-x-auto p-4 font-mono text-xs leading-relaxed text-teal-900">
        {snippets[active]}
      </pre>
    </div>
  );
}
