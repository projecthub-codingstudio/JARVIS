export function normalizeResponseText(text: string): string {
  let normalized = text.replace(/\r\n/g, '\n').replace(/[\u2028\u2029]/g, '\n').trim();

  const escapedNewlineCount = (normalized.match(/\\n/g) || []).length;
  const shouldDecodeEscapes =
    escapedNewlineCount > 0 &&
    (!normalized.includes('\n')
      || escapedNewlineCount >= 2
      || /\\n(?:[-*]\s|\d+\.\s|#{1,6}\s)/.test(normalized));

  if (shouldDecodeEscapes) {
    normalized = normalized
      .replace(/\\r\\n/g, '\n')
      .replace(/\\n/g, '\n')
      .replace(/\\r/g, '')
      .replace(/\\t/g, '  ')
      .replace(/\\"/g, '"');

    if (
      normalized.length >= 2 &&
      ((normalized.startsWith('"') && normalized.endsWith('"'))
        || (normalized.startsWith("'") && normalized.endsWith("'")))
    ) {
      normalized = normalized.slice(1, -1);
    }
  }

  return normalized.replace(/\n{3,}/g, '\n\n').trim();
}
