import { z, type ZodTypeAny } from "zod";

import type { JsonSchema } from "@/lib/api/client";

/**
 * Minimal JSON Schema → Zod converter. Covers the subset we emit from the
 * backend: string / number / integer / boolean with constraints, enums, and
 * object schemas with required[] + properties.
 */
export function jsonSchemaToZod(schema: JsonSchema | undefined): ZodTypeAny {
  if (!schema) return z.any();
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type;

  if (schema.enum && schema.enum.length > 0) {
    const values = schema.enum.filter(
      (v): v is string => typeof v === "string",
    );
    if (values.length === schema.enum.length) {
      return values.length === 1
        ? z.literal(values[0])
        : z.enum([values[0], ...values.slice(1)] as [string, ...string[]]);
    }
    return z.any().refine((v) => schema.enum?.includes(v as never), {
      message: "Value not in enum",
    });
  }

  switch (type) {
    case "string": {
      let s = z.string();
      if (schema.minLength !== undefined) s = s.min(schema.minLength);
      if (schema.maxLength !== undefined) s = s.max(schema.maxLength);
      if (schema.format === "email") s = s.email();
      if (schema.format === "uri") s = s.url();
      return s;
    }
    case "integer": {
      let n = z.number().int();
      if (schema.minimum !== undefined) n = n.min(schema.minimum);
      if (schema.maximum !== undefined) n = n.max(schema.maximum);
      return n;
    }
    case "number": {
      let n = z.number();
      if (schema.minimum !== undefined) n = n.min(schema.minimum);
      if (schema.maximum !== undefined) n = n.max(schema.maximum);
      return n;
    }
    case "boolean":
      return z.boolean();
    case "array":
      return z.array(jsonSchemaToZod(schema.items));
    case "object":
    default: {
      const shape: Record<string, ZodTypeAny> = {};
      const required = new Set(schema.required ?? []);
      const props = schema.properties ?? {};
      for (const [key, value] of Object.entries(props)) {
        const base = jsonSchemaToZod(value);
        shape[key] = required.has(key) ? base : base.optional();
      }
      return z.object(shape);
    }
  }
}
