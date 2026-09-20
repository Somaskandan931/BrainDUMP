import { InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/format";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...rest }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full rounded-md border border-hairline bg-surface-raised px-3 py-2 text-[13px] text-ink",
        "placeholder:text-ink-faint focus:border-primary focus:outline-none",
        className
      )}
      {...rest}
    />
  )
);
Input.displayName = "Input";
