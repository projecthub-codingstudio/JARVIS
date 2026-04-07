import { useCallback } from 'react';
import { useAppStore } from '../store/app-store';
import { apiClient, AskRequest, AskResponse } from '../lib/api-client';
import { normalizeResponseText } from '../lib/response-text';
import { Message } from '../types';

export const useJarvis = () => {
  const {
    addMessage,
    setLoading,
    setError,
    setAssets,
    setCitations,
    setGuide,
    setPresentation,
    setHasEvidence,
    sessionId,
    addLog,
  } = useAppStore();

  const { isLoading } = useAppStore();

  const sendMessage = useCallback(async (text: string, options?: { contextDocumentPath?: string }) => {
    if (!text.trim() || isLoading) return;

    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'operator',
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      }),
      content: text,
    };
    addMessage(userMessage);
    setLoading(true);
    setError(null);

    try {
      // Send to JARVIS backend
      const request: AskRequest = {
        text: text,
        session_id: sessionId,
        ...(options?.contextDocumentPath ? { context_document_path: options.contextDocumentPath } : {}),
      };

      const response: AskResponse = await apiClient.ask(request);
      const assistantText = normalizeResponseText(response.answer.text || response.response.response || '');

      // Add assistant message
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'architect',
        timestamp: new Date().toLocaleTimeString([], { 
          hour: '2-digit', 
          minute: '2-digit', 
          second: '2-digit', 
          hour12: false 
        }),
        content: assistantText,
        citations: response.response.citations?.map(c => ({
          label: c.label,
          source_path: c.source_path,
          full_source_path: c.full_source_path,
          source_type: c.source_type,
          quote: normalizeResponseText(c.quote),
          relevance_score: c.relevance_score,
        })),
        has_evidence: response.response.has_evidence,
        answer_kind: response.answer.kind,
        task_id: response.answer.task_id || undefined,
        structured_payload: response.answer.structured_payload ?? null,
      };
      addMessage(assistantMessage);

      // Update store with JARVIS response data
      setHasEvidence(response.response.has_evidence);
      const answerKind = response.answer.kind || 'retrieval_result';
      const nextCitations = (response.response.citations || []).map(c => ({
        label: c.label,
        source_path: c.source_path,
        full_source_path: c.full_source_path,
        source_type: c.source_type,
        quote: normalizeResponseText(c.quote),
        relevance_score: c.relevance_score,
      }));

      if (answerKind === 'utility_result' || answerKind === 'action_result') {
        setCitations([]);
        setAssets([]);
        setPresentation(null);
      } else {
        setCitations(nextCitations);
        setAssets(response.guide.artifacts || []);
        setPresentation(response.guide.presentation || null);
      }

      setGuide(response.guide);

      // Log system event
      addLog({
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Query processed: ${text.slice(0, 50)}...`,
      });

      // Handle clarification prompts (only when genuinely asking for clarification, not echoing the answer)
      if (response.guide.has_clarification
        && response.guide.clarification_prompt
        && response.guide.missing_slots.length > 0
        && response.guide.clarification_prompt !== response.answer.text) {
        const clarificationMessage: Message = {
          id: (Date.now() + 2).toString(),
          role: 'architect',
          timestamp: new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
          }),
          content: normalizeResponseText(response.guide.clarification_prompt),
        };
        addMessage(clarificationMessage);
      }

    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Request failed';
      setError(errorMessage);
      
      addLog({
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        type: 'error',
        message: `Error: ${errorMessage}`,
      });

      // Add error message to chat
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'architect',
        timestamp: new Date().toLocaleTimeString([], { 
          hour: '2-digit', 
          minute: '2-digit', 
          second: '2-digit', 
          hour12: false 
        }),
        content: `Error: ${errorMessage}. Please check if the JARVIS backend is running.`,
      });
    } finally {
      setLoading(false);
    }
  }, [sessionId, isLoading, addMessage, setLoading, setError, setAssets, setCitations, setGuide, setPresentation, setHasEvidence, addLog]);

  const handleSuggestedReply = useCallback((reply: string) => {
    sendMessage(reply);
  }, [sendMessage]);

  const sendMessageWithImage = useCallback(async (text: string, image: File) => {
    if (isLoading) return;
    const displayText = text.trim() || '(이미지 분석)';

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'operator',
      timestamp: new Date().toLocaleTimeString([], {
        hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
      }),
      content: `📷 ${image.name}\n\n${displayText}`,
    };
    addMessage(userMessage);
    setLoading(true);
    setError(null);

    try {
      const result = await apiClient.askVision(displayText, image);
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'architect',
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
        }),
        content: normalizeResponseText(result.answer),
        has_evidence: false,
        answer_kind: 'retrieval_result',
      };
      addMessage(assistantMessage);
      addLog({
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        type: 'info',
        message: `Vision query (${result.model_id}, ${result.elapsed_ms}ms): ${image.name}`,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Vision request failed';
      setError(msg);
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'architect',
        timestamp: new Date().toLocaleTimeString([], {
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
        }),
        content: `Vision error: ${msg}`,
      });
    } finally {
      setLoading(false);
    }
  }, [isLoading, addMessage, setLoading, setError, addLog]);

  return {
    sendMessage,
    sendMessageWithImage,
    handleSuggestedReply,
    sessionId,
  };
};
