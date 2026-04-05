# JARVIS Web UI Integration Report

## Executive Summary

This report analyzes the current state of the **ProjectHub-terminal-architect** web UI and provides a comprehensive integration plan to connect it with the **JARVIS** Python backend.

---

## 1. Current State Analysis

### 1.1 Web UI (ProjectHub-terminal-architect)

| Aspect | Status |
|--------|--------|
| **Framework** | React 19 + Vite + Tailwind CSS v4 |
| **State Management** | Local `useState` (no external library) |
| **API Layer** | ❌ Not implemented |
| **Backend Connection** | ❌ None (mock data only) |
| **TypeScript** | ✅ Fully typed |
| **Responsive Design** | ✅ Mobile-first |
| **Theme** | ✅ Dark/Light mode |

**Key Files:**
- `src/App.tsx` - Main component (924 lines, single-file architecture)
- `src/types.ts` - TypeScript interfaces
- `src/constants.ts` - Mock data
- `package.json` - Dependencies

### 1.2 JARVIS Backend (alliance_20260317_130542)

| Aspect | Status |
|--------|--------|
| **Language** | Python 3.12 (mypy strict) |
| **Service Layer** | ✅ `JarvisApplicationService` |
| **Transport** | stdio, Unix domain socket |
| **RPC Protocol** | ✅ Request/Response JSON |
| **Core Features** | RAG, citations, voice (STT/TTS), indexing |

**Available RPC Methods:**
| Request Type | Description |
|--------------|-------------|
| `health` | System health check |
| `runtime_state` | Full runtime state |
| `normalize_query` | Korean query normalization |
| `repair_transcript` | Voice transcript repair |
| `navigation_window` | Document/code exploration |
| `transcribe_file` | Speech-to-text (whisper.cpp) |
| `synthesize_speech` | Text-to-speech (Qwen3-TTS) |
| `warmup_tts` | Warm up TTS engine |
| `prefetch_query_tts` | Predictive TTS caching |
| `export_draft` | Export response to file |
| `ask_text` | **Main query endpoint** |

---

## 2. Integration Architecture

### 2.1 Recommended Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Web UI (React 19 + Vite)                                   │
│  - Dashboard, Chat, Asset views                             │
│  - State: Zustand (recommended)                             │
│  - HTTP Client: TanStack Query + fetch                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTP/WebSocket
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  API Bridge Layer (New - TypeScript/Node.js or FastAPI)     │
│  - REST API endpoints                                       │
│  - WebSocket for streaming                                  │
│  - Session management                                       │
│  - Request/Response transformation                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ Unix Domain Socket or stdio
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  JARVIS Backend (Python)                                    │
│  - JarvisApplicationService                                 │
│  - RPC Protocol (JSON over socket/stdio)                    │
│  - RAG Pipeline, LLM, STT/TTS                               │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Integration Options

#### Option A: FastAPI Bridge (Recommended)
**Pros:**
- Native async support
- Automatic OpenAPI docs
- Easy WebSocket streaming
- Python ecosystem (same as JARVIS)

**Cons:**
- Additional Python process

**Implementation:**
```python
# New file: alliance_20260317_130542/src/jarvis/web_api.py
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = JarvisApplicationService()

@app.post("/api/ask")
async def ask(query: str, session_id: str):
    request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id=session_id,
        request_type="ask_text",
        payload={"text": query}
    )
    response = service.handle(request)
    return response.payload
```

#### Option B: Direct Socket Connection
**Pros:**
- No additional layer
- Direct RPC communication

**Cons:**
- Browser cannot use Unix sockets directly
- Requires WebSocket proxy

#### Option C: stdio via Node.js Bridge
**Pros:**
- Leverages existing Node.js dependencies in web project
- Express already in package.json

**Cons:**
- More complex process management

---

## 3. Implementation Plan

### Phase 1: Foundation (Week 1)

#### 3.1.1 Add State Management (Zustand)

```bash
cd ProjectHub-terminal-architect
npm install zustand @tanstack/react-query
```

**New file: `src/store/app-store.ts`**
```typescript
import { create } from 'zustand';
import { Message, Asset, SystemLog } from '../types';

interface AppState {
  // State
  messages: Message[];
  assets: Asset[];
  logs: SystemLog[];
  isLoading: boolean;
  error: string | null;
  sessionId: string;
  
  // Actions
  addMessage: (message: Message) => void;
  setAssets: (assets: Asset[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearMessages: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  messages: [],
  assets: [],
  logs: [],
  isLoading: false,
  error: null,
  sessionId: crypto.randomUUID(),
  
  addMessage: (message) => 
    set((state) => ({ messages: [...state.messages, message] })),
  setAssets: (assets) => set({ assets }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  clearMessages: () => set({ messages: [] }),
}));
```

#### 3.1.2 Create API Client

**New file: `src/lib/api-client.ts`**
```typescript
const API_BASE_URL = import.meta.env.VITE_JARVIS_API_URL || 'http://localhost:8000';

export interface AskRequest {
  text: string;
  session_id: string;
}

export interface AskResponse {
  response: {
    query: string;
    response: string;
    spoken_response: string;
    has_evidence: boolean;
    citations: Array<{
      label: string;
      source_path: string;
      quote: string;
      relevance_score: number;
    }>;
    status: {
      mode: string;
      safe_mode: boolean;
      degraded_mode: boolean;
    };
    render_hints: {
      response_type: string;
      primary_source_type: string;
      interaction_mode: string;
      citation_count: number;
    };
    exploration: {
      mode: string;
      document_candidates: Array<{
        label: string;
        kind: string;
        path: string;
        preview: string;
      }>;
    };
    source_presentation: {
      kind: string;
      title: string;
      preview_lines: string[];
    };
  };
  answer: {
    text: string;
    spoken_text: string;
    has_evidence: boolean;
    citation_count: number;
  };
  guide: {
    loop_stage: string;
    clarification_prompt: string;
    suggested_replies: string[];
    missing_slots: string[];
    presentation: {
      layout: string;
      title: string;
      blocks: Array<{
        id: string;
        kind: string;
        title: string;
        artifact_ids: string[];
      }>;
    };
    artifacts: Array<{
      id: string;
      type: string;
      title: string;
      path: string;
      preview: string;
    }>;
  };
}

export const apiClient = {
  async ask(request: AskRequest): Promise<AskResponse> {
    const response = await fetch(`${API_BASE_URL}/api/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    });
    
    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }
    
    return response.json();
  },
  
  async health(): Promise<{ health: object }> {
    const response = await fetch(`${API_BASE_URL}/api/health`);
    return response.json();
  },
};
```

#### 3.1.3 Update Types

**Update: `src/types.ts`**
```typescript
// Add new types for JARVIS integration
export interface Citation {
  label: string;
  source_path: string;
  full_source_path: string;
  source_type: string;
  quote: string;
  relevance_score: number;
}

export interface EvidenceItem {
  id: string;
  type: 'document' | 'code' | 'web' | 'image';
  title: string;
  path: string;
  preview: string;
  score: number;
}

export interface GuideDirective {
  loop_stage: 'presenting' | 'clarifying' | 'waiting_user_reply';
  clarification_prompt: string;
  suggested_replies: string[];
  missing_slots: string[];
}

export interface Message {
  id: string;
  role: 'operator' | 'architect';
  timestamp: string;
  content: string;
  citations?: Citation[];
  has_evidence?: boolean;
}

// ... existing types
```

### Phase 2: Backend Bridge (Week 2)

#### 3.2.1 Create FastAPI Bridge

**New file: `alliance_20260317_130542/src/jarvis/web_api.py`**
```python
"""FastAPI bridge for web UI integration."""

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid
import asyncio
import json

from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest, RpcResponse

app = FastAPI(title="JARVIS Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = JarvisApplicationService()


class AskRequest(BaseModel):
    text: str
    session_id: str


class AskResponse(BaseModel):
    response: dict
    answer: dict
    guide: dict


@app.post("/api/ask")
async def ask(request: AskRequest) -> AskResponse:
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id=request.session_id,
        request_type="ask_text",
        payload={"text": request.text},
    )
    rpc_response: RpcResponse = service.handle(rpc_request)
    
    if not rpc_response.ok:
        raise HTTPException(
            status_code=400,
            detail=rpc_response.error.message if rpc_response.error else "Unknown error"
        )
    
    return AskResponse(**rpc_response.payload)


@app.get("/api/health")
async def health():
    rpc_request = RpcRequest(
        request_id=str(uuid.uuid4()),
        session_id="health-check",
        request_type="health",
        payload={},
    )
    rpc_response: RpcResponse = service.handle(rpc_request)
    return rpc_response.payload


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            rpc_request = RpcRequest(
                request_id=str(uuid.uuid4()),
                session_id=session_id,
                request_type=payload.get("request_type", "ask_text"),
                payload=payload.get("payload", {}),
            )
            rpc_response: RpcResponse = service.handle(rpc_request)
            
            await websocket.send_json(rpc_response.payload)
    except Exception as e:
        await websocket.close(code=1011, reason=str(e))
```

#### 3.2.2 Update pyproject.toml

```toml
[project.optional-dependencies]
web = [
    "fastapi>=0.109",
    "uvicorn[standard]>=0.27",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.6",
    "mypy>=1.11",
]
```

### Phase 3: UI Integration (Week 2-3)

#### 3.3.1 Update App.tsx Chat Handler

**Update: `src/App.tsx`**
```typescript
// Replace mock handler with real API call
const handleSendMessage = async (e: React.FormEvent) => {
  e.preventDefault();
  if (!inputValue.trim()) return;

  const userMessage: Message = {
    id: Date.now().toString(),
    role: 'operator',
    timestamp: new Date().toLocaleTimeString(),
    content: inputValue
  };

  addMessage(userMessage);
  setInputValue('');
  setLoading(true);

  try {
    const response = await apiClient.ask({
      text: inputValue,
      session_id: sessionId
    });

    // Parse JARVIS response
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'architect',
      timestamp: new Date().toLocaleTimeString(),
      content: response.answer.text,
      citations: response.response.citations,
      has_evidence: response.response.has_evidence
    };

    addMessage(assistantMessage);
    
    // Update assets from exploration data
    if (response.guide.artifacts) {
      const assets: Asset[] = response.guide.artifacts.map(artifact => ({
        id: artifact.id,
        type: mapArtifactType(artifact.type),
        name: artifact.title,
        description: artifact.preview,
        path: artifact.path
      }));
      setAssets(assets);
    }
    
    // Handle clarification prompts
    if (response.guide.has_clarification) {
      addMessage({
        id: (Date.now() + 2).toString(),
        role: 'architect',
        timestamp: new Date().toLocaleTimeString(),
        content: response.guide.clarification_prompt
      });
    }
  } catch (error) {
    setError(error instanceof Error ? error.message : 'Request failed');
    addMessage({
      id: (Date.now() + 1).toString(),
      role: 'architect',
      timestamp: new Date().toLocaleTimeString(),
      content: 'Error: Request failed. Please try again.'
    });
  } finally {
    setLoading(false);
  }
};
```

#### 3.3.2 Create Asset Components

**New file: `src/components/AssetCard.tsx`**
```typescript
import React from 'react';
import { Asset } from '../types';
import { FileIcon, FileText, Image, Code } from 'lucide-react';
import { cn } from '../lib/utils';

interface AssetCardProps {
  asset: Asset;
  onClick: () => void;
}

export const AssetCard: React.FC<AssetCardProps> = ({ asset, onClick }) => {
  const getIcon = () => {
    switch (asset.type) {
      case 'pdf': return <FileText className="text-red-500" />;
      case 'image': return <Image className="text-blue-400" />;
      case 'code': return <Code className="text-green-500" />;
      default: return <FileIcon className="text-yellow-500" />;
    }
  };

  return (
    <div
      onClick={onClick}
      className={cn(
        "bg-surface-high group hover:bg-surface-highest transition-colors",
        "flex flex-col cursor-pointer border border-outline/10"
      )}
    >
      <div className="p-4 border-b border-outline/10 flex justify-between items-center">
        <div className="flex items-center gap-3">
          {getIcon()}
          <span className="text-xs font-mono text-on-surface uppercase">
            {asset.name}
          </span>
        </div>
      </div>
      {asset.description && (
        <div className="p-4 flex-1">
          <p className="text-xs text-on-surface-variant font-headline">
            {asset.description}
          </p>
        </div>
      )}
    </div>
  );
};
```

### Phase 4: Advanced Features (Week 3-4)

#### 3.4.1 Voice Integration

```typescript
// src/hooks/useVoice.ts
export const useVoice = () => {
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState('');

  const startRecording = async () => {
    // Request microphone permission
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    // Record audio
    const mediaRecorder = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: 'audio/webm' });
      
      // Send to backend for transcription
      const formData = new FormData();
      formData.append('audio', blob);
      
      const response = await fetch(`${API_BASE_URL}/api/transcribe`, {
        method: 'POST',
        body: formData,
      });
      
      const data = await response.json();
      setTranscript(data.transcript);
    };
    
    mediaRecorder.start();
    setIsRecording(true);
  };

  return { isRecording, transcript, startRecording };
};
```

#### 3.4.2 Real-time Streaming

```typescript
// src/hooks/useStreaming.ts
export const useStreaming = (sessionId: string) => {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);
    
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      // Handle streaming response
    };
    
    wsRef.current = ws;
    return () => ws.close();
  }, [sessionId]);

  const send = (request: object) => {
    wsRef.current?.send(JSON.stringify(request));
  };

  return { connected, send };
};
```

---

## 4. File Structure After Integration

```
ProjectHub-terminal-architect/
├── src/
│   ├── components/
│   │   ├── VoiceWaveform.tsx
│   │   ├── AssetCard.tsx          # NEW
│   │   ├── CitationList.tsx       # NEW
│   │   └── ClarificationPrompt.tsx # NEW
│   ├── lib/
│   │   ├── utils.ts
│   │   └── api-client.ts          # NEW
│   ├── store/
│   │   └── app-store.ts           # NEW (Zustand)
│   ├── hooks/
│   │   ├── useVoice.ts            # NEW
│   │   └── useStreaming.ts        # NEW
│   ├── App.tsx                    # UPDATED
│   ├── types.ts                   # UPDATED
│   └── constants.ts
├── .env                           # NEW (API_URL)
└── package.json                   # UPDATED

alliance_20260317_130542/
├── src/jarvis/
│   ├── service/
│   │   ├── application.py
│   │   ├── protocol.py
│   │   └── ...
│   └── web_api.py                 # NEW (FastAPI)
├── pyproject.toml                 # UPDATED
└── ...
```

---

## 5. Environment Configuration

**.env (ProjectHub-terminal-architect)**
```env
VITE_JARVIS_API_URL=http://localhost:8000
VITE_JARVIS_WS_URL=ws://localhost:8000/ws
```

**.env (JARVIS Backend)**
```env
JARVIS_SERVICE_TRANSPORT=socket
JARVIS_MENU_BAR_MODEL_CHAIN=stub,qwen3.5:9b,exaone4.0:32b
JARVIS_TTS_BACKEND=qwen3
```

---

## 6. Development Workflow

### 6.1 Start Backend
```bash
# Terminal 1: JARVIS service
cd alliance_20260317_130542
pip install -e ".[web]"
python -m jarvis.web_api --reload
```

### 6.2 Start Frontend
```bash
# Terminal 2: Web UI
cd ProjectHub-terminal-architect
npm install
npm run dev
```

### 6.3 Access
- Web UI: http://localhost:3000
- API Docs: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws/{session_id}

---

## 7. Key Integration Points

### 7.1 Chat → `ask_text`
```
User Input → API Client → FastAPI → RpcRequest(ask_text) 
→ JarvisApplicationService → MLX/Ollama → Response
```

### 7.2 Assets → `navigation_window`
```
Query → navigation_window RPC → Exploration State 
→ Artifact List → Asset Cards
```

### 7.3 Voice → `transcribe_file` + `synthesize_speech`
```
Browser Mic → MediaRecorder → Blob → /api/transcribe 
→ Whisper.cpp → Transcript

Text → /api/synthesize → Qwen3-TTS → Audio File → <audio>
```

### 7.4 Citations → Response Parsing
```
JARVIS Response.citations[] → CitationList Component 
→ Click → Source Preview
```

---

## 8. Recommendations

### 8.1 Immediate Actions
1. **Install Zustand** for state management
2. **Create FastAPI bridge** layer
3. **Implement `ask_text`** integration first
4. **Update types** to match JARVIS response schema

### 8.2 Medium-term
1. Add **WebSocket streaming** for real-time responses
2. Implement **voice recording** in browser
3. Create **citation viewer** component
4. Add **clarification prompt** UI

### 8.3 Long-term
1. **MCP server** integration for tool calls
2. **Document upload** UI for indexing
3. **Settings panel** for model selection
4. **Conversation history** persistence

---

## 9. Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Backend performance | High | Use stub model for quick responses |
| CORS issues | Medium | Configure FastAPI CORS properly |
| State sync complexity | Medium | Use Zustand for centralized state |
| Voice browser compatibility | Low | Use standard MediaRecorder API |

---

## 10. Conclusion

The web UI is well-structured with a clean design system. The main gaps are:
1. No API layer
2. Mock data only
3. No state management library

**Recommended approach:**
1. Add Zustand + TanStack Query
2. Create FastAPI bridge (Python, same as backend)
3. Implement incrementally: chat → assets → voice → streaming

**Estimated effort:** 2-4 weeks for full integration

---

## Appendix A: Sample API Response Mapping

```typescript
// JARVIS Backend Response
{
  "response": {
    "query": "프로젝트 구조 알려줘",
    "response": "프로젝트는 다음과 같은 구조로...",
    "citations": [...],
    "render_hints": {
      "interaction_mode": "source_exploration",
      "citation_count": 3
    },
    "exploration": {
      "file_candidates": [...]
    }
  },
  "answer": {
    "text": "프로젝트는 다음과 같은 구조로...",
    "citation_count": 3
  },
  "guide": {
    "loop_stage": "presenting",
    "artifacts": [...],
    "presentation": {
      "layout": "master_detail",
      "blocks": [...]
    }
  }
}

// Web UI State Update
{
  messages: [
    { role: 'operator', content: '프로젝트 구조 알려줘' },
    { role: 'architect', content: '프로젝트는 다음과 같은 구조로...', citations: [...] }
  ],
  assets: [...], // from guide.artifacts
  view: 'dashboard' // or 'detail_code' based on presentation.layout
}
```

---

*Report generated: 2026-04-02*
*Author: JARVIS Code Analysis*
