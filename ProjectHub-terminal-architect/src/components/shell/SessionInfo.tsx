import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { UserRound } from 'lucide-react';
import { useClickOutside } from '../../hooks/useClickOutside';

interface SessionInfoProps {
  sessionId: string;
  backendStatus: 'checking' | 'online' | 'offline';
  artifactCount: number;
  citationCount: number;
  messageCount: number;
}

export function SessionInfo({ sessionId, backendStatus, artifactCount, citationCount, messageCount }: SessionInfoProps) {
  const [open, setOpen] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const statusColor = backendStatus === 'online' ? 'text-secondary' : backendStatus === 'checking' ? 'text-primary' : 'text-[#ffb4ab]';

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="flex h-7 w-7 items-center justify-center rounded-sm border border-white/10 bg-surface-container-highest text-outline transition hover:border-primary/30 hover:text-on-surface"
      >
        <UserRound size={14} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-2 w-64 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Session
              </span>
            </div>

            <div className="space-y-2 p-3">
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Session ID</span>
                <span className="font-mono text-on-surface-variant">{sessionId.slice(0, 8)}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Backend</span>
                <span className={statusColor}>{backendStatus}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Messages</span>
                <span className="text-primary">{messageCount}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Artifacts</span>
                <span className="text-primary">{artifactCount}</span>
              </div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-outline">Citations</span>
                <span className="text-secondary">{citationCount}</span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
