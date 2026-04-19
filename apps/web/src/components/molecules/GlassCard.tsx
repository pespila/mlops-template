import { clsx } from "clsx";
import type { HTMLAttributes, PropsWithChildren } from "react";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export function GlassCard({
  children,
  className,
  ...rest
}: PropsWithChildren<GlassCardProps>) {
  return (
    <div className={clsx("glass-card animate-fade-in", className)} {...rest}>
      {children}
    </div>
  );
}
