// Het vinkje van shadcn/ui, op Radix: toetsenbord en schermlezer goed geregeld.
import * as CheckboxPrimitive from '@radix-ui/react-checkbox';
import { cn } from '../../lib/utils.js';

export function Checkbox({ className, ...props }) {
  return (
    <CheckboxPrimitive.Root
      className={cn(
        'peer size-[1.15rem] shrink-0 rounded-[5px] border border-zacht bg-papier outline-none',
        'focus-visible:ring-2 focus-visible:ring-groen focus-visible:ring-offset-2 focus-visible:ring-offset-papier',
        'data-[state=checked]:border-groen-donker data-[state=checked]:bg-groen-donker data-[state=checked]:text-papier',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="flex items-center justify-center text-current">
        <svg viewBox="0 0 16 16" aria-hidden="true" className="size-3.5" fill="none" stroke="currentColor" strokeWidth="2.2">
          <path d="M3.5 8.5l3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
