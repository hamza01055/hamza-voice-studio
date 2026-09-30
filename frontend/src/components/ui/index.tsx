import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as SwitchPrimitive from "@radix-ui/react-switch";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, Loader2, X, XCircle } from "lucide-react";
import {
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean; icon?: ReactNode }
>(function Button({ variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition-colors select-none",
        "disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap",
        size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-9 px-3.5 text-sm",
        variant === "primary" && "bg-accent text-accent-fg hover:opacity-90",
        variant === "secondary" && "bg-panel border border-line text-fg hover:bg-panel-2",
        variant === "ghost" && "text-fg hover:bg-panel-2",
        variant === "danger" && "bg-danger text-white hover:opacity-90 dark:text-bg",
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

export function IconButton({
  label,
  icon,
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; icon: ReactNode }) {
  return (
    <Tooltip content={label}>
      <button
        aria-label={label}
        className={clsx(
          "inline-flex size-8 items-center justify-center rounded-lg text-muted hover:bg-panel-2 hover:text-fg",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          className,
        )}
        {...rest}
      >
        {icon}
      </button>
    </Tooltip>
  );
}

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <TooltipPrimitive.Root delayDuration={300}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={6}
          className="z-50 max-w-xs rounded-md bg-fg px-2 py-1 text-xs text-bg shadow-lg"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export function Badge({
  tone = "neutral",
  children,
  className,
  title,
}: {
  tone?: "neutral" | "accent" | "ok" | "warn" | "danger";
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        tone === "neutral" && "bg-panel-2 text-muted",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "ok" && "bg-ok-soft text-ok",
        tone === "warn" && "bg-warn-soft text-warn",
        tone === "danger" && "bg-danger-soft text-danger",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={clsx("rounded-xl border border-line bg-panel", className)}>{children}</div>;
}

/** Determinate when value is a number; honest indeterminate animation when null. */
export function Progress({ value, label, className }: { value: number | null; label: string; className?: string }) {
  const pct = value == null ? undefined : Math.round(value * 100);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct}
      aria-valuetext={pct == null ? "In progress" : `${pct}%`}
      className={clsx("relative h-1.5 w-full overflow-hidden rounded-full bg-panel-2", className)}
    >
      {pct == null ? (
        <div className="animate-indeterminate absolute inset-y-0 w-2/5 rounded-full bg-accent/70" />
      ) : (
        <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${pct}%` }} />
      )}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("size-4 animate-spin text-muted", className)} aria-label="Loading" />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-panel-2", className)} aria-hidden />;
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="flex size-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">{icon}</div>
      <h3 className="text-base font-semibold">{title}</h3>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
      {action}
    </div>
  );
}

export function Notice({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: "info" | "warn" | "danger" | "ok";
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  const Icon = { info: Info, warn: AlertTriangle, danger: XCircle, ok: CheckCircle2 }[tone];
  return (
    <div
      role={tone === "danger" ? "alert" : "note"}
      className={clsx(
        "flex gap-2.5 rounded-lg border px-3 py-2.5 text-sm",
        tone === "info" && "border-line bg-panel-2 text-fg",
        tone === "warn" && "border-warn/30 bg-warn-soft text-fg",
        tone === "danger" && "border-danger/30 bg-danger-soft text-fg",
        tone === "ok" && "border-ok/30 bg-ok-soft text-fg",
        className,
      )}
    >
      <Icon
        className={clsx(
          "mt-0.5 size-4 shrink-0",
          tone === "info" && "text-muted",
          tone === "warn" && "text-warn",
          tone === "danger" && "text-danger",
          tone === "ok" && "text-ok",
        )}
        aria-hidden
      />
      <div className="min-w-0">
        {title && <div className="font-medium">{title}</div>}
        <div className={clsx(title && "text-muted")}>{children}</div>
      </div>
    </div>
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-[13px] font-medium">
        {label}
      </label>
      {children}
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </div>
  );
}

const widthOf = (c?: string) => (c && /(^|\s)w-/.test(c) ? "" : "w-full");
const inputCls =
  "rounded-lg border border-line bg-panel px-3 text-sm text-fg placeholder:text-muted/70 focus:border-accent focus:outline-none disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={clsx(inputCls, widthOf(className), "h-9", className)} {...rest} />;
});

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={clsx(inputCls, widthOf(className), "h-9 pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea(
  { className, ...rest },
  ref,
) {
  return <textarea ref={ref} className={clsx(inputCls, widthOf(className), "py-2 leading-relaxed", className)} {...rest} />;
});

export function Switch({
  checked,
  onChange,
  label,
  id,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  id?: string;
  disabled?: boolean;
}) {
  return (
    <SwitchPrimitive.Root
      id={id}
      aria-label={label}
      checked={checked}
      disabled={disabled}
      onCheckedChange={onChange}
      className="relative h-5 w-9 shrink-0 rounded-full bg-line transition-colors data-[state=checked]:bg-accent disabled:opacity-50"
    >
      <SwitchPrimitive.Thumb className="block size-4 translate-x-0.5 rounded-full bg-white shadow transition-transform data-[state=checked]:translate-x-[18px]" />
    </SwitchPrimitive.Root>
  );
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  wide,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[1px]" />
        <DialogPrimitive.Content
          className={clsx(
            "fixed left-1/2 top-1/2 z-50 flex max-h-[88vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col",
            "rounded-2xl border border-line bg-panel shadow-2xl",
            wide ? "max-w-3xl" : "max-w-lg",
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div>
              <DialogPrimitive.Title className="text-base font-semibold">{title}</DialogPrimitive.Title>
              {description ? (
                <DialogPrimitive.Description className="mt-1 text-sm text-muted">{description}</DialogPrimitive.Description>
              ) : (
                <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close asChild>
              <button aria-label="Close" className="rounded-md p-1 text-muted hover:bg-panel-2 hover:text-fg">
                <X className="size-4" />
              </button>
            </DialogPrimitive.Close>
          </div>
          <div className="scroll-thin overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  children,
  confirmLabel,
  onConfirm,
  busy,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  busy?: boolean;
}) {
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      footer={
        <>
          <Button onClick={() => onOpenChange(false)}>Keep</Button>
          <Button variant="danger" loading={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-sm">{children}</div>
    </Modal>
  );
}

// ---------------------------------------------------------------- toasts
type Toast = { id: number; tone: "ok" | "danger" | "info" | "warn"; text: string };
const ToastCtx = createContext<(tone: Toast["tone"], text: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, tone, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "danger" ? 8000 : 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed right-4 bottom-24 z-[60] flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div key={t.id} className="pointer-events-auto shadow-lg">
            <Notice tone={t.tone}>{t.text}</Notice>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);
