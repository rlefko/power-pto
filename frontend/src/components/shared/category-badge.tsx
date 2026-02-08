import { cn } from "@/lib/utils";
import type { PolicyCategory } from "@/lib/api/types";
import { POLICY_CATEGORY_CONFIG } from "@/lib/utils/constants";

interface CategoryBadgeProps {
  category: PolicyCategory;
  className?: string;
}

export function CategoryBadge({ category, className }: CategoryBadgeProps) {
  const config = POLICY_CATEGORY_CONFIG[category];
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
}
