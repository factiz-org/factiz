// Zoals in shadcn/ui: klassen samenvoegen, en bij een botsing wint de laatste.
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...invoer) {
  return twMerge(clsx(invoer));
}
