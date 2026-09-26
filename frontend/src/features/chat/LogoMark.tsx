import { BookOpen } from "lucide-react";

/** Brand mark: an open book on the brand colour (also used as the favicon). */
export function LogoMark({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={`flex items-center justify-center rounded-lg bg-gradient-to-br from-brand to-brand-strong text-on-brand shadow-sm ${className}`}
    >
      <BookOpen className="size-[55%]" strokeWidth={2.25} />
    </span>
  );
}
