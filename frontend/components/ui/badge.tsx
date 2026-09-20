import { cn } from "@/lib/cn";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-baseline px-2 py-0.5 text-xs text-ink-secondary",
        className,
      )}
      {...props}
    />
  );
}
