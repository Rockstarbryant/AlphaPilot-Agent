import { KeyboardEvent, ReactNode } from "react";
import clsx from "clsx";

export function Panel({
  children,
  className,
  title,
  action,
}: {
  children: ReactNode;
  className?: string;
  title?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={clsx("border border-line bg-surface rounded-sm", className)}>
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-line">
          <h2 className="text-sm text-muted">{title}</h2>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function StatusPill({
  tone,
  children,
}: {
  tone: "gain" | "loss" | "watch" | "gold" | "muted";
  children: ReactNode;
}) {
  const toneClasses: Record<string, string> = {
    gain: "text-gain border-gain/40 bg-gain/10",
    loss: "text-loss border-loss/40 bg-loss/10",
    watch: "text-watch border-watch/40 bg-watch/10",
    gold: "text-gold border-gold/40 bg-gold/10",
    muted: "text-muted border-line bg-white/[0.02]",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-sm border text-xs",
        toneClasses[tone]
      )}
    >
      {children}
    </span>
  );
}

export function Stat({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss";
  sub?: string;
}) {
  return (
    <div>
      <div className="text-xs text-muted mb-1">{label}</div>
      <div
        className={clsx(
          "tnum text-2xl",
          tone === "gain" && "text-gain",
          tone === "loss" && "text-loss",
          !tone && "text-text"
        )}
      >
        {value}
      </div>
      {sub && <div className="text-xs text-muted mt-0.5">{sub}</div>}
    </div>
  );
}

export function Button({
  children,
  onClick,
  variant = "default",
  disabled,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "default" | "danger" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  const variants: Record<string, string> = {
    default: "bg-gold text-ink hover:bg-gold-dim disabled:opacity-40",
    danger: "bg-loss text-white hover:bg-loss/80 disabled:opacity-40",
    ghost: "border border-line text-text hover:bg-surface-raised disabled:opacity-40",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "px-3 py-1.5 rounded-sm text-sm transition-colors disabled:cursor-not-allowed",
        variants[variant]
      )}
    >
      {children}
    </button>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <div className="px-4 py-10 text-center text-sm text-muted">{message}</div>;
}

export function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
  onKeyDown,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: "text" | "number";
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      className="w-full bg-surface-raised border border-line rounded-sm px-3 py-1.5 text-sm text-text placeholder:text-muted focus:outline-none focus:border-gold/60"
    />
  );
}
