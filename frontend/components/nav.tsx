"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, TrendingUp, Wallet, ShieldAlert, Bot, Activity, Landmark, PiggyBank, Settings,
} from "lucide-react";
import clsx from "clsx";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/opportunities", label: "Opportunities", icon: TrendingUp },
  { href: "/positions", label: "Positions", icon: Wallet },
  { href: "/margin", label: "Margin", icon: ShieldAlert },
  { href: "/earn", label: "Earn", icon: PiggyBank },
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/risk", label: "Risk", icon: Landmark },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function SideNav() {
  const pathname = usePathname();
  return (
    <nav className="hidden md:flex flex-col w-56 shrink-0 border-r border-line bg-surface">
      <div className="px-4 py-5 border-b border-line">
        <div className="text-gold text-sm tracking-wide">ALPHAPILOT</div>
        <div className="text-[11px] text-muted mt-0.5">Market Operations</div>
      </div>
      <div className="flex-1 py-2">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 px-4 py-2.5 text-sm border-l-2",
                active
                  ? "border-gold text-text bg-surface-raised"
                  : "border-transparent text-muted hover:text-text hover:bg-surface-raised/50"
              )}
            >
              <Icon size={16} strokeWidth={1.75} />
              {label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 border-t border-line bg-surface flex overflow-x-auto z-20">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname?.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex-shrink-0 basis-1/5 flex flex-col items-center gap-0.5 py-2.5 text-[10px]",
              active ? "text-gold" : "text-muted"
            )}
          >
            <Icon size={18} strokeWidth={1.75} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}