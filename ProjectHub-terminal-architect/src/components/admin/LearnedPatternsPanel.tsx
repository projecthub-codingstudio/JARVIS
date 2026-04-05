/**
 * LearnedPatternsPanel — view and manage learned query patterns.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Brain, RefreshCw, Trash2 } from 'lucide-react';
import { cn } from '../../lib/utils';
import { apiClient } from '../../lib/api-client';
import type { LearnedPatternSummary } from '../../types';

const REFORMULATION_COLORS: Record<string, string> = {
  specialization: 'bg-emerald-500/20 text-emerald-300',
  error_correction: 'bg-blue-500/20 text-blue-300',
  parallel_move: 'bg-amber-500/20 text-amber-300',
  generalization: 'bg-gray-500/20 text-gray-300',
};

function formatDate(unixSeconds: number): string {
  const d = new Date(unixSeconds * 1000);
  return d.toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' });
}

export function LearnedPatternsPanel() {
  const [patterns, setPatterns] = useState<LearnedPatternSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.listLearnedPatterns();
      setPatterns(res.patterns);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = useCallback(async (patternId: string) => {
    if (!confirm('이 학습 패턴을 삭제하시겠습니까?')) return;
    await apiClient.forgetLearnedPattern(patternId);
    load();
  }, [load]);

  const handleDeleteAll = useCallback(async () => {
    if (!confirm('모든 학습 패턴을 삭제하시겠습니까? 되돌릴 수 없습니다.')) return;
    await apiClient.forgetLearnedPattern();
    load();
  }, [load]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white/70">
            Learned Patterns ({patterns.length})
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="rounded-md p-1.5 text-white/50 hover:bg-white/5 hover:text-white"
            title="새로고침"
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          </button>
          {patterns.length > 0 && (
            <button
              onClick={handleDeleteAll}
              className="rounded-md px-2 py-1 text-xs text-red-400 hover:bg-red-500/10"
            >
              전체 삭제
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="p-4 text-sm text-red-400">에러: {error}</div>
        )}
        {!loading && patterns.length === 0 && !error && (
          <div className="p-8 text-center text-sm text-white/30">
            아직 학습된 패턴이 없습니다.<br />
            실패→성공 쿼리 쌍이 감지되면 여기에 표시됩니다.
          </div>
        )}
        <div className="divide-y divide-white/5">
          {patterns.map((p) => (
            <div key={p.pattern_id} className="p-4 hover:bg-white/5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={cn(
                      'rounded px-1.5 py-0.5 text-[10px] font-medium uppercase',
                      REFORMULATION_COLORS[p.reformulation_type] || 'bg-white/10 text-white/60'
                    )}>
                      {p.reformulation_type}
                    </span>
                    <span className="text-[10px] text-white/40 font-mono">{p.retrieval_task}</span>
                    <span className="text-[10px] text-white/40">× {p.success_count}</span>
                  </div>
                  <div className="text-sm text-white/90 mb-1 break-words">{p.canonical_query}</div>
                  {p.failed_variants.length > 0 && (
                    <div className="text-xs text-white/40 mb-1">
                      ↶ {p.failed_variants[0]}
                    </div>
                  )}
                  <div className="text-xs text-white/50 font-mono break-words">
                    {JSON.stringify(p.entity_hints)}
                  </div>
                  <div className="text-[10px] text-white/30 mt-1">
                    생성: {formatDate(p.created_at)} · 최근 사용: {formatDate(p.last_used_at)}
                  </div>
                </div>
                <button
                  onClick={() => handleDelete(p.pattern_id)}
                  className="rounded-md p-1 text-white/30 hover:bg-red-500/10 hover:text-red-400"
                  title="삭제"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
