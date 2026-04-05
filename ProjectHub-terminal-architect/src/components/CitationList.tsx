import React from 'react';
import { Quote, FileText, Code, Globe } from 'lucide-react';
import { cn } from '../lib/utils';
import { Citation } from '../types';

interface CitationListProps {
  citations: Citation[];
  onCitationClick?: (citation: Citation) => void;
}

export const CitationList: React.FC<CitationListProps> = ({ citations, onCitationClick }) => {
  if (!citations || citations.length === 0) {
    return null;
  }

  const getSourceIcon = (sourceType: string) => {
    const type = sourceType.toLowerCase();
    if (type === 'code') {
      return <Code size={14} className="text-green-500" />;
    }
    if (type === 'web') {
      return <Globe size={14} className="text-blue-400" />;
    }
    return <FileText size={14} className="text-primary" />;
  };

  const getSourceLabel = (citation: Citation) => {
    if (citation.heading_path) {
      const parts = citation.heading_path.split('>');
      return parts[parts.length - 1]?.trim() || citation.source_path;
    }
    return citation.source_path;
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 mb-4">
        <Quote size={16} className="text-primary" />
        <span className="text-xs font-mono text-primary uppercase tracking-wider">
          근거 자료 ({citations.length}개)
        </span>
      </div>
      
      <div className="space-y-2">
        {citations.map((citation, index) => (
          <div
            key={index}
            onClick={() => onCitationClick?.(citation)}
            className={cn(
              "bg-surface-high/50 border border-outline/10 p-3 rounded-sm",
              "hover:bg-surface-highest hover:border-primary/30 transition-all cursor-pointer"
            )}
          >
            <div className="flex items-start gap-3">
              <div className="shrink-0 mt-0.5">
                {getSourceIcon(citation.source_type)}
              </div>
              
              <div className="flex-1 min-w-0 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] font-mono text-primary uppercase tracking-wider">
                    [{citation.label}]
                  </span>
                  <span className="text-[9px] font-mono text-outline">
                    관련도: {citation.relevance_score.toFixed(3)}
                  </span>
                </div>
                
                <div className="space-y-1">
                  <p className="text-[10px] font-mono text-on-surface-variant truncate">
                    {getSourceLabel(citation)}
                  </p>
                  
                  {citation.quote && (
                    <blockquote className="text-xs text-on-surface-variant italic border-l-2 border-outline/20 pl-3">
                      {citation.quote.length > 150 
                        ? citation.quote.slice(0, 150) + '...' 
                        : citation.quote}
                    </blockquote>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
