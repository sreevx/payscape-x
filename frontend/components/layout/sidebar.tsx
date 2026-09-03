"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  FlaskConical,
  LayoutDashboard,
  ListChecks,
  ReceiptText,
  SearchCheck,
  Settings,
  TriangleAlert,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { DEMO_MODE, DEMO_MODE_LABEL } from "@/lib/demo-mode";
import { DEMO_USER } from "@/lib/demo-data";
import { BackendStatus } from "@/components/shared/backend-status";
import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown, LogOut, UserRound } from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/transactions", label: "Transactions", icon: ReceiptText },
  { href: "/investigation", label: "Investigations", icon: SearchCheck },
  { href: "/failures", label: "Failure Patterns", icon: TriangleAlert },
  { href: "/simulation", label: "Simulation Lab", icon: FlaskConical },
  { href: "/actions", label: "Action Center", icon: ListChecks },
  { href: "/events", label: "Event Explorer", icon: Activity },
];

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  const isActive = (href: string) =>
    href === "/dashboard"
      ? pathname === "/dashboard" || pathname === "/"
      : pathname.startsWith(href);

  return (
    <div className="flex h-full flex-col">
      {/* Brand */}
      <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
        <div className="flex size-6 items-center justify-center rounded border bg-foreground text-[10px] font-bold text-background">
          PX
        </div>
        <div className="leading-none">
          <p className="text-sm font-semibold tracking-tight">PAYSCAPE-X</p>
          <p className="text-[10px] text-muted-foreground">
            Payment Outcome Intelligence
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-3">
        <p className="px-2 pb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">
          Operations
        </p>
        {NAV_ITEMS.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] font-medium transition-colors",
                active
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon
                className={cn("size-4", active ? "text-foreground" : "text-muted-foreground")}
                aria-hidden
              />
              {item.label}
            </Link>
          );
        })}

        <p className="px-2 pt-4 pb-2 text-[10px] font-semibold tracking-widest text-muted-foreground uppercase">
          System
        </p>
        <Link
          href="/settings"
          onClick={onNavigate}
          aria-current={pathname.startsWith("/settings") ? "page" : undefined}
          className={cn(
            "flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] font-medium transition-colors",
            pathname.startsWith("/settings")
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          <Settings className="size-4 text-muted-foreground" aria-hidden />
          Settings
        </Link>
      </nav>

      {/* Footer: system status, demo mode, user */}
      <div className="space-y-2 border-t px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <BackendStatus />
          {DEMO_MODE ? (
            <span className="inline-flex items-center rounded border border-amber-300/60 bg-amber-50 px-1.5 py-0.5 text-[9px] font-bold tracking-widest text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-400">
              {DEMO_MODE_LABEL}
            </span>
          ) : null}
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                className="flex w-full items-center gap-2 rounded-md px-1.5 py-1.5 text-left hover:bg-muted"
              >
                <Avatar className="size-7">
                  <AvatarFallback className="text-[10px]">
                    {DEMO_USER.initials}
                  </AvatarFallback>
                </Avatar>
                <span className="min-w-0 flex-1 leading-tight">
                  <span className="block truncate text-xs font-medium text-foreground">
                    {DEMO_USER.name}
                  </span>
                  <span className="block truncate text-[10px] text-muted-foreground">
                    {DEMO_USER.role}
                  </span>
                </span>
                <ChevronDown className="size-3.5 text-muted-foreground" aria-hidden />
              </button>
            }
          />
          <DropdownMenuContent className="w-56" align="start">
            <DropdownMenuLabel>Signed in as</DropdownMenuLabel>
            <div className="px-1.5 pb-1 text-xs text-muted-foreground">
              {DEMO_USER.email}
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <UserRound /> Profile
            </DropdownMenuItem>
            <DropdownMenuItem
              render={
                <Link href="/settings" onClick={onNavigate}>
                  <Settings /> Settings
                </Link>
              }
            />
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive">
              <LogOut /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}