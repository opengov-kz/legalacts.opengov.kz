"use client";

import * as RadixSelect from "@radix-ui/react-select";
import { cn } from "@/lib/cn";

export const Select = RadixSelect.Root;
export const SelectValue = RadixSelect.Value;

export function SelectTrigger({ className, children, ...props }: RadixSelect.SelectTriggerProps) {
  return (
    <RadixSelect.Trigger
      className={cn(
        "inline-flex h-9 items-center justify-between rounded-md border border-baseline bg-surface-card px-3 text-sm",
        className,
      )}
      {...props}
    >
      {children}
    </RadixSelect.Trigger>
  );
}

export function SelectContent({ children, ...props }: RadixSelect.SelectContentProps) {
  return (
    <RadixSelect.Portal>
      <RadixSelect.Content
        className="overflow-hidden rounded-md border border-gridline bg-surface-card shadow-md"
        {...props}
      >
        <RadixSelect.Viewport className="p-1">{children}</RadixSelect.Viewport>
      </RadixSelect.Content>
    </RadixSelect.Portal>
  );
}

export function SelectItem({ className, children, ...props }: RadixSelect.SelectItemProps) {
  return (
    <RadixSelect.Item
      className={cn(
        "cursor-pointer rounded px-2 py-1.5 text-sm outline-none data-[highlighted]:bg-surface-page",
        className,
      )}
      {...props}
    >
      <RadixSelect.ItemText>{children}</RadixSelect.ItemText>
    </RadixSelect.Item>
  );
}
