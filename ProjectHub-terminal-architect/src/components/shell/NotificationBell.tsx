import React, { useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Bell } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useClickOutside } from '../../hooks/useClickOutside';
import type { SystemLog } from '../../types';

interface NotificationBellProps {
  logs: SystemLog[];
  unreadCount: number;
  onMarkRead: () => void;
  onClearAll: () => void;
}

function getLogDot(type: SystemLog['type']) {
  switch (type) {
    case 'error': return 'bg-[#ffb4ab]';
    case 'warning': return 'bg-tertiary';
    default: return 'bg-secondary';
  }
}

export function NotificationBell({ logs, unreadCount, onMarkRead, onClearAll }: NotificationBellProps) {
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => {
    setOpen((prev) => {
      if (!prev) onMarkRead();
      return !prev;
    });
  }, [onMarkRead]);

  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const recent = logs.slice(-20).reverse();

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={toggle}
        className="relative text-primary transition hover:bg-surface-container-high hover:text-on-surface"
      >
        <Bell size={16} />
        {unreadCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-[#ffb4ab] text-[8px] font-bold text-black">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-2 w-80 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Notifications
              </span>
              {recent.length > 0 && (
                <button
                  onClick={onClearAll}
                  className="text-[10px] text-outline transition hover:text-on-surface"
                >
                  Clear All
                </button>
              )}
            </div>
            <div className="max-h-64 overflow-y-auto custom-scrollbar">
              {recent.length === 0 ? (
                <div className="px-3 py-4 text-center text-xs text-outline">
                  No notifications
                </div>
              ) : (
                recent.map((log) => (
                  <div key={log.id} className="border-b border-white/5 px-3 py-2 last:border-0">
                    <div className="flex items-center gap-2">
                      <span className={cn('inline-flex h-1.5 w-1.5 rounded-full', getLogDot(log.type))} />
                      <span className="text-[10px] font-mono text-outline">
                        {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                      </span>
                      <span className="text-[10px] font-semibold uppercase text-on-surface-variant">{log.type}</span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">{log.message}</p>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
