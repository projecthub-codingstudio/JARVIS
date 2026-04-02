import React, { useMemo } from 'react';
import DOMPurify from 'dompurify';
import type { RendererProps } from './TextRenderer';

const HtmlRenderer: React.FC<RendererProps> = ({ artifact, content }) => {
  const html = content || artifact.preview || '';
  const sanitizedHtml = useMemo(() => DOMPurify.sanitize(html), [html]);

  return (
    <div className="h-full flex flex-col">
      <iframe
        srcDoc={sanitizedHtml}
        sandbox=""
        title={artifact.title}
        className="flex-1 w-full border-0 bg-white"
      />
    </div>
  );
};

export default HtmlRenderer;
