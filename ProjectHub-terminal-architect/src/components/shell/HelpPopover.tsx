import React, { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { HelpCircle } from 'lucide-react';
import { useClickOutside } from '../../hooks/useClickOutside';

interface HelpPopoverProps {
  backendStatus: 'checking' | 'online' | 'offline';
}

const SHORTCUTS = [
  { keys: ['Cmd', 'K'], description: 'Command Palette' },
  { keys: ['Enter'], description: 'Send message' },
  { keys: ['Esc'], description: 'Close palette / popover' },
  { keys: ['\u2191', '\u2193'], description: 'Navigate palette results' },
];

export function HelpPopover({ backendStatus }: HelpPopoverProps) {
  const [open, setOpen] = useState(false);
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false));

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="text-outline transition hover:text-on-surface"
      >
        <HelpCircle size={18} />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -4 }}
            transition={{ duration: 0.12 }}
            className="absolute bottom-0 left-full ml-3 w-64 border border-white/10 bg-surface-container-low shadow-xl"
          >
            <div className="border-b border-white/5 px-3 py-2">
              <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-on-surface-variant">
                Help
              </span>
            </div>

            <div className="space-y-3 p-3">
              <div>
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  Keyboard Shortcuts
                </div>
                <div className="space-y-1.5">
                  {SHORTCUTS.map((shortcut) => (
                    <div key={shortcut.description} className="flex items-center justify-between">
                      <span className="text-[11px] text-on-surface-variant">{shortcut.description}</span>
                      <div className="flex gap-1">
                        {shortcut.keys.map((key) => (
                          <kbd key={key} className="rounded border border-white/10 px-1.5 py-0.5 text-[9px] font-mono text-outline">
                            {key}
                          </kbd>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t border-white/5 pt-3">
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-outline">
                  Quick Guide
                </div>
                <ul className="space-y-1 text-[11px] text-on-surface-variant">
                  <li>Type a question in the input to ask JARVIS</li>
                  <li>Use Repository to browse knowledge base files</li>
                  <li>Skills manages automation profiles</li>
                  <li>Admin shows system activity and statistics</li>
                </ul>
              </div>

              <div className="border-t border-white/5 pt-3">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-outline">Version</span>
                  <span className="text-on-surface-variant">ProjectHub-JARVIS v1.0</span>
                </div>
                <div className="mt-1 flex items-center justify-between text-[10px]">
                  <span className="text-outline">Backend</span>
                  <span className={backendStatus === 'online' ? 'text-secondary' : 'text-[#ffb4ab]'}>{backendStatus}</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
