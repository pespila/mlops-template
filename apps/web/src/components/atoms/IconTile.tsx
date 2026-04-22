import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";

type IconTileSize = 32 | 40 | 48 | 64;

interface IconTileProps {
  icon: LucideIcon;
  size?: IconTileSize;
  className?: string;
}

const SIZE_CLASS: Record<IconTileSize, string> = {
  32: "h-8 w-8 rounded-md",
  40: "h-10 w-10 rounded-md",
  48: "h-12 w-12 rounded-md",
  64: "h-16 w-16 rounded-lg",
};

const ICON_SIZE: Record<IconTileSize, number> = {
  32: 16,
  40: 20,
  48: 24,
  64: 32,
};

export function IconTile({ icon: Icon, size = 48, className }: IconTileProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center justify-center bg-gradient-primary text-white shadow-glow",
        SIZE_CLASS[size],
        className,
      )}
    >
      <Icon size={ICON_SIZE[size]} strokeWidth={2} />
    </div>
  );
}
