import React from 'react';
import { MessageCircle, ArrowRight } from 'lucide-react';
import { cn } from '../lib/utils';

interface ClarificationPromptProps {
  prompt: string;
  suggestedReplies: string[];
  onReplySelect: (reply: string) => void;
}

export const ClarificationPrompt: React.FC<ClarificationPromptProps> = ({
  prompt,
  suggestedReplies,
  onReplySelect,
}) => {
  if (!prompt && suggestedReplies.length === 0) {
    return null;
  }

  return (
    <div className="bg-surface-high/30 border border-outline/10 p-4 md:p-6 rounded-sm space-y-4">
      <div className="flex items-start gap-3">
        <MessageCircle size={18} className="text-primary shrink-0 mt-0.5" />
        <div className="flex-1 space-y-4">
          {prompt && (
            <div>
              <p className="text-xs font-mono text-primary uppercase tracking-wider mb-2">
                Clarification Required
              </p>
              <p className="text-sm text-on-surface leading-relaxed">
                {prompt}
              </p>
            </div>
          )}
          
          {suggestedReplies.length > 0 && (
            <div className="space-y-2">
              <p className="text-[10px] font-mono text-outline uppercase tracking-wider">
                Suggested Replies
              </p>
              <div className="flex flex-wrap gap-2">
                {suggestedReplies.map((reply, index) => (
                  <button
                    key={index}
                    onClick={() => onReplySelect(reply)}
                    className={cn(
                      "px-3 py-2 bg-surface-low border border-outline/20",
                      "text-xs text-on-surface-variant font-mono",
                      "hover:bg-primary/10 hover:border-primary/30 hover:text-primary",
                      "transition-all duration-200"
                    )}
                  >
                    {reply}
                    <ArrowRight size={12} className="inline ml-1.5" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
