import React from 'react';
import { motion } from 'motion/react';

export const VoiceWaveform = () => {
  return (
    <div className="relative flex items-center justify-center w-12 h-12 rounded-full bg-surface-highest/60 backdrop-blur-xl border border-primary/20">
      <motion.div 
        className="absolute inset-0 rounded-full bg-primary/5"
        animate={{ scale: [1, 1.2, 1] }}
        transition={{ duration: 2, repeat: Infinity }}
      />
      <div className="flex items-end gap-[2px] h-4">
        {[0.4, 0.8, 0.6, 1, 0.4].map((h, i) => (
          <motion.div
            key={i}
            className="w-1 bg-primary"
            animate={{ height: [`${h * 40}%`, `${h * 100}%`, `${h * 40}%`] }}
            transition={{ duration: 1, repeat: Infinity, delay: i * 0.1 }}
          />
        ))}
      </div>
      <div className="absolute inset-0 rounded-full shadow-[0_0_20px_rgba(16,185,129,0.15)] pointer-events-none" />
    </div>
  );
};
