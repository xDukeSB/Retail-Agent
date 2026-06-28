"use client";

import { cn } from "@/lib/utils";

interface SectionHeaderProps {
  title: string;
  description?: string;
  children?: React.ReactNode;
  className?: string;
}

export function SectionHeader({ title, description, children, className }: SectionHeaderProps) {
  return (
    <div className={cn("flex items-center justify-between mb-4", className)}>
      <div>
        <h2 className="text-sm font-semibold text-gray-900">{title}</h2>
        {description && <p className="text-xs text-gray-500 mt-0.5">{description}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  );
}

interface CardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  description?: string;
  action?: React.ReactNode;
}

export function Card({ children, className, title, description, action }: CardProps) {
  return (
    <div className={cn("rounded-xl border border-gray-200 bg-white p-5 shadow-sm", className)}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-4">
          <div>
            {title && <h3 className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">{title}</h3>}
            {description && <p className="text-xs text-gray-500 mt-1">{description}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function Badge({
  children,
  variant = "default",
  className,
}: {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "error" | "info";
  className?: string;
}) {
  const variants = {
    default: "bg-gray-100 text-gray-600 border-gray-200",
    success: "bg-emerald-50 text-emerald-600 border-emerald-200",
    warning: "bg-amber-50 text-amber-600 border-amber-200",
    error:   "bg-rose-50 text-rose-600 border-rose-200",
    info:    "bg-blue-50 text-blue-600 border-blue-200",
  };
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide border",
      variants[variant], className
    )}>
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rounded-md bg-gray-100 animate-pulse", className)} />;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-12 h-12 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-center mb-4">
        <Icon className="w-6 h-6 text-gray-300" />
      </div>
      <p className="text-sm font-semibold text-gray-500">{title}</p>
      {description && <p className="text-xs text-gray-400 mt-1 max-w-xs">{description}</p>}
    </div>
  );
}
