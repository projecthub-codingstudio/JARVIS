import { useCallback } from 'react';
import { useAppStore } from '../store/app-store';
import { apiClient, AskRequest, AskResponse } from '../lib/api-client';
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

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim()) return;

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
      };

      const response: AskResponse = await apiClient.ask(request);

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
        content: response.answer.text,
        citations: response.response.citations?.map(c => ({
          label: c.label,
          source_path: c.source_path,
          full_source_path: c.full_source_path,
          source_type: c.source_type,
          quote: c.quote,
          relevance_score: c.relevance_score,
        })),
        has_evidence: response.response.has_evidence,
      };
      addMessage(assistantMessage);

      // Update store with JARVIS response data
      setHasEvidence(response.response.has_evidence);
      
      if (response.response.citations) {
        setCitations(response.response.citations.map(c => ({
          label: c.label,
          source_path: c.source_path,
          full_source_path: c.full_source_path,
          source_type: c.source_type,
          quote: c.quote,
          relevance_score: c.relevance_score,
        })));
      }

      if (response.guide.artifacts) {
        setAssets(response.guide.artifacts);
      }

      if (response.guide.presentation) {
        setPresentation(response.guide.presentation);
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
          content: response.guide.clarification_prompt,
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
  }, [sessionId, addMessage, setLoading, setError, setAssets, setCitations, setGuide, setPresentation, setHasEvidence, addLog]);

  const handleSuggestedReply = useCallback((reply: string) => {
    sendMessage(reply);
  }, [sendMessage]);

  return {
    sendMessage,
    handleSuggestedReply,
    sessionId,
  };
};
