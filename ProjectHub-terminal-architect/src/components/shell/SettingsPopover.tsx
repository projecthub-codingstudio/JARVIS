import React, { useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Settings, Trash2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import { useClickOutside } from '../../hooks/useClickOutside';
import { apiClient } from '../../lib/api-client';

interface SettingsPopoverProps {
  onClearMessages: () => void;
  addLog: (log: { id: string; timestamp: string; type: 'info' | 'warning' | 'error'; message: string }) => void;
}

export function SettingsPopover({ onClearMessages, addLog }: SettingsPopoverProps) {
  const [open, setOpen] = useState(false);
  const [forgetting, setForgetting] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  const apiUrl = import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000';

  const handleForgetConversations = useCallback(async () => {
    if (forgetting) return;
    setForgetting(true);
    try {
      const result = await apiClient.forgetData('conversations');
      onClearMessages();
      addLog({
        id: `${Date.now()}-forget`,
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Conversations cleared: ${JSON.stringify(result.deleted)}`,
      });
    } catch (error) {
      addLog({
        id: `${Date.now()}-forget-err`,
        timestamp: new Date().toISOString(),
        type: 'error',
        message: `Failed to clear conversations: ${error instanceof Error ? error.message : 'Unknown error'}`,
      });
    } finally {
      setForgetting(false);
    }
  }, [forgetting, onClearMessages, addLog]);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="text-primary transition hover:bg-surface-container-high hover:text-on-surface"
      >
        <Settings size={16} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute right-0 top-full mt-2 w-72 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Settings
              </span>
            </div>

            <div className="space-y-3 p-3">
              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  API Endpoint
                </div>
                <div className="rounded-sm bg-surface-container-lowest/40 px-2 py-1.5 font-mono text-[11px] text-on-surface-variant">
                  {apiUrl}
                </div>
              </div>

              <div>
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  Theme
                </div>
                <div className="text-[11px] text-on-surface-variant">Dark (default)</div>
              </div>

              <div className="border-t border-white/5 pt-3">
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#ffb4ab]">
                  Data Privacy
                </div>
                <button
                  onClick={handleForgetConversations}
                  disabled={forgetting}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-[11px] transition',
                    forgetting
                      ? 'cursor-not-allowed text-outline'
                      : 'text-[#ffb4ab] hover:bg-surface-container',
                  )}
                >
                  <Trash2 size={12} />
                  {forgetting ? 'Clearing...' : 'Clear Conversation History'}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
