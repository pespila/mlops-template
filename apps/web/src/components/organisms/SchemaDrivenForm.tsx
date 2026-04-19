import { useState } from "react";
import { useForm, type FieldValues } from "react-hook-form";

import { Button } from "@/components/atoms/Button";
import type { JsonSchema } from "@/lib/api/client";
import { cn } from "@/lib/cn";
import { jsonSchemaToZod } from "@/lib/schema/jsonSchemaToZod";

type Primitive = string | number | boolean;

interface SchemaDrivenFormProps {
  schema: JsonSchema;
  defaults?: Record<string, Primitive | null>;
  submitLabel?: string;
  onSubmit: (values: Record<string, unknown>) => void | Promise<void>;
  className?: string;
  busy?: boolean;
}

export function SchemaDrivenForm({
  schema,
  defaults,
  submitLabel = "Submit →",
  onSubmit,
  className,
  busy,
}: SchemaDrivenFormProps) {
  const zodSchema = jsonSchemaToZod(schema);
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const { register, handleSubmit } = useForm<FieldValues>({
    defaultValues: defaults as FieldValues | undefined,
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  return (
    <form
      className={cn("flex flex-col gap-4", className)}
      onSubmit={handleSubmit(async (values) => {
        const parsed = zodSchema.safeParse(values);
        if (!parsed.success) {
          const errs: Record<string, string> = {};
          for (const issue of parsed.error.issues) {
            const path = issue.path.join(".") || "_form";
            if (!errs[path]) errs[path] = issue.message;
          }
          setFieldErrors(errs);
          return;
        }
        setFieldErrors({});
        await onSubmit(parsed.data as Record<string, unknown>);
      })}
      noValidate
    >
      {Object.entries(properties).map(([name, spec]) => {
        const type = Array.isArray(spec.type) ? spec.type[0] : spec.type;
        const errorMessage = fieldErrors[name];
        const inputClass = cn(
          "w-full rounded border bg-bg px-3 py-2 text-sm text-fg1",
          "border-[color:var(--border)] focus:border-primary focus:outline-none",
          errorMessage && "border-danger",
        );

        return (
          <label key={name} className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold uppercase tracking-[0.08em] text-fg2">
              {spec.title ?? name}
              {required.has(name) ? <span className="ml-0.5 text-danger">*</span> : null}
            </span>
            {spec.enum && spec.enum.length > 0 ? (
              <select
                className={inputClass}
                defaultValue={defaults?.[name] as string | undefined}
                {...register(name)}
              >
                <option value="">Select…</option>
                {spec.enum.map((opt) => (
                  <option key={String(opt)} value={String(opt)}>
                    {String(opt)}
                  </option>
                ))}
              </select>
            ) : type === "boolean" ? (
              <input
                type="checkbox"
                className="h-5 w-5 accent-[color:var(--primary)]"
                {...register(name)}
              />
            ) : type === "integer" || type === "number" ? (
              <input
                type="number"
                step={type === "integer" ? 1 : "any"}
                placeholder={spec.description ?? ""}
                className={inputClass}
                {...register(name, { valueAsNumber: true })}
              />
            ) : (
              <input
                type={spec.format === "password" ? "password" : "text"}
                placeholder={spec.description ?? ""}
                className={inputClass}
                {...register(name)}
              />
            )}
            {spec.description ? (
              <span className="text-xs text-fg3">{spec.description}</span>
            ) : null}
            {errorMessage ? (
              <span className="text-xs font-semibold text-danger">{errorMessage}</span>
            ) : null}
          </label>
        );
      })}
      <div>
        <Button type="submit" disabled={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
