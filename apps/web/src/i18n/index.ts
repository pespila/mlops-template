import { useCallback } from "react";

import { useUiStore } from "@/state/uiStore";

import de from "./de.json";
import en from "./en.json";

type Dict = Record<string, unknown>;

const DICTS: Record<"en" | "de", Dict> = { en: en as Dict, de: de as Dict };

function lookup(dict: Dict, key: string): string {
  const parts = key.split(".");
  let current: unknown = dict;
  for (const part of parts) {
    if (current && typeof current === "object" && part in (current as Dict)) {
      current = (current as Dict)[part];
    } else {
      return key;
    }
  }
  return typeof current === "string" ? current : key;
}

export function useT(): (key: string) => string {
  const language = useUiStore((s) => s.language);
  return useCallback((key: string) => lookup(DICTS[language], key), [language]);
}
