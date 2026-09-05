"use client";

import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { api, Notification } from "@/lib/api";
import { useUserId } from "@/lib/use-user";

export function NotificationBell() {
  const userId = useUserId();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);

  async function load() {
    if (!userId) return;
    setNotifications(await api.listNotifications(userId, true));
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [userId]);

  async function markAllRead() {
    if (!userId) return;
    await api.markAllNotificationsRead(userId);
    setNotifications([]);
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative text-muted hover:text-text p-1.5"
      >
        <Bell size={16} strokeWidth={1.75} />
        {notifications.length > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-gold" />
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 border border-line bg-surface rounded-sm shadow-lg z-30">
          <div className="flex items-center justify-between px-3 py-2 border-b border-line">
            <span className="text-xs text-muted">Notifications</span>
            {notifications.length > 0 && (
              <button onClick={markAllRead} className="text-xs text-gold">
                Mark all read
              </button>
            )}
          </div>
          {notifications.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted">All caught up.</div>
          ) : (
            <div className="max-h-80 overflow-y-auto">
              {notifications.map((n) => (
                <div key={n.id} className="ledger-row px-3 py-2.5">
                  <div className="text-sm">{n.title}</div>
                  {n.detail && <div className="text-xs text-muted mt-0.5">{n.detail}</div>}
                  <div className="text-[10px] text-muted mt-1 tnum">
                    {new Date(n.created_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
