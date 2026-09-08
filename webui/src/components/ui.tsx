import type { ReactNode } from 'react';

/**
 * The primitives the original UI used, rebuilt on plain Tailwind.
 *
 * The class strings and the palette (#111c35 sidebar, #6d5dfc accent, #f5f7fb
 * page) are carried over from kosuzu123/Multimodal-rag-UI so the console keeps
 * that design. Its own components sit on @base-ui/react plus a Cloudflare/vinext
 * build that this repository cannot run, and pulling that toolchain in to get
 * four wrappers would have made the demo harder to start than to skip.
 */

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div
      className={cx(
        'rounded-xl border-0 bg-white shadow-[0_8px_30px_rgba(31,42,68,0.05)] ring-1 ring-slate-200/80',
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardHeader({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx('border-b border-slate-100 px-5 py-4', className)}>{children}</div>;
}

export function CardTitle({ className, children }: { className?: string; children: ReactNode }) {
  return <h3 className={cx('text-sm font-semibold tracking-tight', className)}>{children}</h3>;
}

export function CardContent({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx('p-5', className)}>{children}</div>;
}

const BADGE_TONES = {
  neutral: 'bg-slate-100 text-slate-700',
  accent: 'bg-violet-100 text-violet-700',
  gold: 'bg-amber-100 text-amber-800',
  good: 'bg-emerald-50 text-emerald-700',
  warn: 'bg-amber-50 text-amber-700',
  bad: 'bg-rose-50 text-rose-700',
  outline: 'border border-slate-200 bg-white text-slate-600',
} as const;

export function Badge({
  tone = 'neutral',
  className,
  title,
  children,
}: {
  tone?: keyof typeof BADGE_TONES;
  className?: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={cx(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium whitespace-nowrap',
        BADGE_TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Button({
  onClick,
  disabled,
  variant = 'primary',
  className,
  title,
  ariaLabel,
  children,
}: {
  onClick?: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'ghost' | 'outline';
  className?: string;
  title?: string;
  ariaLabel?: string;
  children: ReactNode;
}) {
  const tones = {
    primary: 'bg-[#6d5dfc] text-white hover:bg-[#5949e8]',
    ghost: 'bg-white/10 text-white hover:bg-white/15',
    outline: 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
  };
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-medium transition disabled:pointer-events-none disabled:opacity-50',
        tones[variant],
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Stat({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'neutral' | 'good' | 'warn';
}) {
  const tones = { neutral: 'text-slate-900', good: 'text-emerald-700', warn: 'text-amber-700' };
  return (
    <div className="rounded-lg bg-[#f6f7fb] p-3">
      <p className="text-[10px] text-slate-500">{label}</p>
      <p className={cx('mt-1 text-lg font-semibold tracking-tight tabular-nums', tones[tone])}>{value}</p>
      {hint ? <p className="mt-0.5 text-[10px] leading-4 text-slate-500">{hint}</p> : null}
    </div>
  );
}

export function Notes({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="rounded-xl border border-amber-200/70 bg-amber-50/50 p-4">
      <p className="text-[10px] font-semibold tracking-[0.16em] text-amber-800 uppercase">{title}</p>
      <ul className="mt-2 space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-xs leading-5 text-amber-900/90">
            <span aria-hidden className="mt-[7px] size-1 shrink-0 rounded-full bg-amber-500" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-xs text-slate-500">{children}</p>;
}

export function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-[10px] tracking-wider text-slate-500 uppercase">{label}</dt>
      <dd className="mt-0.5 text-xs font-medium break-words text-slate-800">{value}</dd>
    </div>
  );
}
