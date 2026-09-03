"use client";

import Link from "next/link";
import { Bell, Command, Menu, Search } from "lucide-react";

import { APP_ENV, DEMO_MODE, DEMO_MODE_LABEL } from "@/lib/demo-mode";
import { DEMO_USER, NOTIFICATIONS } from "@/lib/demo-data";
import { timeAgo } from "@/lib/format";
import { BackendStatus } from "@/components/shared/backend-status";
import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

const UNREAD_COUNT = NOTIFICATIONS.filter((n) => n.unread).length;

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  return (
    <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-3 border-b bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      {/* Mobile menu */}
      <button
        type="button"
        onClick={onMenuClick}
        aria-label="Open navigation"
        className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted lg:hidden"
      >
        <Menu className="size-4" aria-hidden />
      </button>

      {/* Command / search bar */}
      <div className="relative hidden w-full max-w-md sm:block">
        <Search
          className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <input
          type="search"
          placeholder="Search transactions, events, customers…"
          aria-label="Search"
          className="h-8 w-full rounded-md border bg-muted/40 pl-8 pr-14 text-xs outline-none placeholder:text-muted-foreground focus:border-ring focus:bg-background"
        />
        <kbd className="pointer-events-none absolute top-1/2 right-2 hidden -translate-y-1/2 items-center gap-0.5 rounded border bg-background px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground md:inline-flex">
          <Command className="size-2.5" aria-hidden />K
        </kbd>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <BackendStatus />

        {/* Environment indicator */}
        <span
          className="hidden items-center gap-1.5 rounded-full border px-2 py-1 text-[11px] font-medium text-muted-foreground md:inline-flex"
          title="Environment"
        >
          <span className="size-1.5 rounded-full bg-blue-500" aria-hidden />
          {APP_ENV}
          {DEMO_MODE ? (
            <span className="ml-1 rounded border border-amber-300/60 bg-amber-50 px-1 text-[9px] font-bold tracking-widest text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-400">
              {DEMO_MODE_LABEL}
            </span>
          ) : null}
        </span>

        {/* Notifications */}
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label={`Notifications (${UNREAD_COUNT} unread)`}
                className="relative inline-flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted"
              >
                <Bell className="size-4" aria-hidden />
                {UNREAD_COUNT > 0 ? (
                  <span className="absolute top-1.5 right-1.5 flex size-3.5 items-center justify-center rounded-full bg-red-500 text-[8px] font-semibold text-white">
                    {UNREAD_COUNT}
                  </span>
                ) : null}
              </button>
            }
          />
          <DropdownMenuContent className="w-80 p-0" align="end">
            <DropdownMenuLabel className="flex items-center justify-between px-3 py-2">
              Notifications
              <span className="text-[10px] font-normal text-muted-foreground">
                {UNREAD_COUNT} unread
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <div className="max-h-80 overflow-y-auto">
              {NOTIFICATIONS.map((notification) => (
                <div
                  key={notification.id}
                  className={cn(
                    "flex gap-2 border-b px-3 py-2 last:border-b-0",
                    notification.unread ? "bg-muted/40" : ""
                  )}
                >
                  <span
                    className={cn(
                      "mt-1.5 size-1.5 shrink-0 rounded-full",
                      notification.tone === "danger" && "bg-red-500",
                      notification.tone === "warning" && "bg-amber-500",
                      notification.tone === "info" && "bg-blue-500",
                      notification.tone === "neutral" && "bg-zinc-400",
                      notification.tone === "success" && "bg-emerald-500"
                    )}
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium text-foreground">
                      {notification.title}
                    </p>
                    <p className="truncate text-[11px] text-muted-foreground">
                      {notification.body}
                    </p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground/80">
                      {timeAgo(notification.timestamp)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
            <DropdownMenuSeparator />
            <Link
              href="/settings"
              className="block px-3 py-2 text-center text-xs font-medium text-foreground hover:bg-muted"
            >
              View all notifications
            </Link>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                aria-label="User menu"
                className="inline-flex size-8 items-center justify-center rounded-md hover:bg-muted"
              >
                <Avatar className="size-7">
                  <AvatarFallback className="text-[10px]">
                    {DEMO_USER.initials}
                  </AvatarFallback>
                </Avatar>
              </button>
            }
          />
          <DropdownMenuContent className="w-56" align="end">
            <DropdownMenuLabel>Signed in as</DropdownMenuLabel>
            <div className="px-1.5 pb-1 text-xs text-muted-foreground">
              {DEMO_USER.name} · {DEMO_USER.email}
            </div>
            <DropdownMenuSeparator />
            <Link
              href="/settings"
              className="block rounded-md px-1.5 py-1 text-sm hover:bg-accent"
            >
              Settings
            </Link>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}