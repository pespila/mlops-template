import type { PropsWithChildren } from "react";

export function BadgeGlow({ children }: PropsWithChildren) {
  return <span className="badge-glow">{children}</span>;
}
