import React from 'react';
import { FileIcon, FileText, Image, Code, FileSpreadsheet } from 'lucide-react';
import { cn } from '../lib/utils';
import { Artifact } from '../types';

interface AssetCardProps {
  artifact: Artifact;
  onClick: () => void;
  isSelected?: boolean;
}

export const AssetCard: React.FC<AssetCardProps> = ({ artifact, onClick, isSelected }) => {
  const getIcon = () => {
    const type = artifact.type.toLowerCase();
    const viewerKind = artifact.viewer_kind?.toLowerCase();
    
    if (type.includes('image') || viewerKind === 'image') {
      return <Image size={16} className="text-blue-400" />;
    }
    if (type.includes('code') || viewerKind === 'code') {
      return <Code size={16} className="text-green-500" />;
    }
    if (type.includes('pdf')) {
      return <FileText size={16} className="text-red-500" />;
    }
    if (type.includes('spreadsheet') || type.includes('excel')) {
      return <FileSpreadsheet size={16} className="text-emerald-500" />;
    }
    return <FileIcon size={16} className="text-yellow-500" />;
  };

  return (
    <div
      onClick={onClick}
      className={cn(
        "bg-surface-high group hover:bg-surface-highest transition-colors",
        "flex flex-col cursor-pointer border border-outline/10",
        isSelected && "border-primary/50 ring-1 ring-primary/50"
      )}
    >
      <div className="p-4 border-b border-outline/10 flex justify-between items-center">
        <div className="flex items-center gap-3">
          {getIcon()}
          <span className="text-xs font-mono text-on-surface uppercase tracking-wider">
            {artifact.title}
          </span>
        </div>
      </div>
      
      {artifact.preview && (
        <div className="p-4 flex-1">
          <p className="text-xs text-on-surface-variant font-headline leading-relaxed line-clamp-3">
            {artifact.preview}
          </p>
        </div>
      )}
      
      <div className="p-4 flex justify-between items-center bg-surface-low/30 border-t border-outline/10">
        <span className="text-[10px] font-mono text-outline uppercase">
          {artifact.subtitle || artifact.source_type}
        </span>
      </div>
    </div>
  );
};
