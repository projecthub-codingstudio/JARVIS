# JARVIS Web UI Integration Guide

## Overview

This guide explains how to run the integrated JARVIS web UI with the Python backend.

## Architecture

```
┌─────────────────────┐      HTTP/WebSocket      ┌─────────────────────┐
│   React Web UI      │ ◄──────────────────────► │   FastAPI Bridge    │
│   (Port 3000)       │                          │   (Port 8000)       │
└─────────────────────┘                          └─────────┬───────────┘
                                                           │
                                                           │ Unix Socket
                                                           ▼
                                                  ┌─────────────────────┐
                                                  │   JARVIS Backend    │
                                                  │   (Python Service)  │
                                                  └─────────────────────┘
```

## Prerequisites

- Python 3.12+
- Node.js 18+
- npm or bun

## Installation

### 1. Backend Setup

```bash
cd alliance_20260317_130542

# Install JARVIS with web dependencies
pip install -e ".[web]"

# Or upgrade if already installed
pip install -U fastapi uvicorn pydantic
```

### 2. Frontend Setup

```bash
cd ../ProjectHub-terminal-architect

# Install dependencies
npm install

# Dependencies already installed:
# - zustand (state management)
# - @tanstack/react-query (data fetching)
```

## Running the Application

### Option 1: Run Both Servers (Recommended)

**Terminal 1 - Backend:**
```bash
cd alliance_20260317_130542
python -m jarvis.web_api --reload
```

The FastAPI server will start at: http://localhost:8000
- API Docs: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws/{session_id}

**Terminal 2 - Frontend:**
```bash
cd ProjectHub-terminal-architect
npm run dev
```

The React app will start at: http://localhost:3000

### Option 2: Using Environment Variables

Create `.env` file in `ProjectHub-terminal-architect/`:

```env
VITE_JARVIS_API_URL=http://localhost:8000
VITE_JARVIS_WS_URL=ws://localhost:8000/ws
```

## Available API Endpoints

### POST /api/ask
Process a text query and return JARVIS response.

**Request:**
```json
{
  "text": "프로젝트 구조 알려줘",
  "session_id": "uuid-here"
}
```

**Response:**
```json
{
  "response": {
    "query": "프로젝트 구조 알려줘",
    "response": "프로젝트는 다음과 같은 구조로...",
    "has_evidence": true,
    "citations": [...],
    "render_hints": {...},
    "exploration": {...}
  },
  "answer": {
    "text": "프로젝트는 다음과 같은 구조로...",
    "citation_count": 3
  },
  "guide": {
    "loop_stage": "presenting",
    "artifacts": [...],
    "presentation": {...}
  }
}
```

### GET /api/health
Check backend health status.

### POST /api/normalize
Normalize a Korean query.

### WebSocket /ws/{session_id}
Real-time bidirectional communication.

## Features Implemented

### Frontend (ProjectHub-terminal-architect)

- ✅ Zustand state management
- ✅ JARVIS API client
- ✅ Real-time chat with loading states
- ✅ Asset grid with JARVIS artifacts
- ✅ Citation viewer
- ✅ Clarification prompts
- ✅ System logs dashboard
- ✅ Dark/Light theme
- ✅ Mobile responsive

### New Components

- `AssetCard.tsx` - Display JARVIS artifacts
- `CitationList.tsx` - Show evidence citations
- `ClarificationPrompt.tsx` - Handle clarification requests

### New Hooks

- `useJarvis.ts` - Main JARVIS integration hook
- Handles sendMessage, error states, and response parsing

### Backend (alliance_20260317_130542)

- ✅ FastAPI bridge server
- ✅ CORS configuration for localhost:3000
- ✅ HTTP endpoints (/api/ask, /api/health, /api/normalize)
- ✅ WebSocket support for real-time streaming
- ✅ RPC protocol integration with JARVIS service

## Testing the Integration

1. **Start the backend:**
   ```bash
   cd alliance_20260317_130542
   python -m jarvis.web_api --reload
   ```

2. **Test health endpoint:**
   ```bash
   curl http://localhost:8000/api/health
   ```

3. **Start the frontend:**
   ```bash
   cd ProjectHub-terminal-architect
   npm run dev
   ```

4. **Open browser:** http://localhost:3000

5. **Send a query:**
   - Type a message in the chat input
   - Press [SEND_COMMAND] or hit Enter
   - Watch the loading indicator
   - View the response with citations and artifacts

## Troubleshooting

### Backend won't start

**Error: Module not found**
```bash
pip install -e ".[web]"
```

**Error: Port 8000 already in use**
```bash
python -m jarvis.web_api --port 8001
```

### Frontend can't connect to backend

**Check CORS:**
- Ensure backend is running on http://localhost:8000
- Check browser console for CORS errors

**Check API URL:**
```env
# .env file
VITE_JARVIS_API_URL=http://localhost:8000
```

### Chat not responding

1. Verify backend is running: `curl http://localhost:8000/api/health`
2. Check browser console for errors
3. Verify network tab shows requests to localhost:8000

## Development Workflow

### Hot Reload

Both frontend and backend support hot reload:

- **Frontend:** Vite automatically reloads on file changes
- **Backend:** Use `--reload` flag for auto-reload

### Debugging

**Backend logs:**
```bash
# Run with verbose logging
RUST_LOG=debug python -m jarvis.web_api --reload
```

**Frontend logs:**
- Open browser DevTools (F12)
- Check Console and Network tabs

## Next Steps

### Phase 1 (Completed ✅)
- Basic API integration
- Chat functionality
- Asset display
- Citation viewer

### Phase 2 (In Progress)
- Voice recording integration
- WebSocket streaming
- Real-time response updates

### Phase 3 (Planned)
- Document upload UI
- Settings panel for model selection
- Conversation history persistence
- MCP server integration

## File Structure

```
ProjectHub-terminal-architect/
├── src/
│   ├── components/
│   │   ├── AssetCard.tsx          # NEW
│   │   ├── CitationList.tsx       # NEW
│   │   ├── ClarificationPrompt.tsx # NEW
│   │   └── VoiceWaveform.tsx
│   ├── hooks/
│   │   └── useJarvis.ts           # NEW
│   ├── lib/
│   │   └── api-client.ts          # NEW
│   ├── store/
│   │   └── app-store.ts           # NEW
│   ├── App.tsx                    # UPDATED
│   └── types.ts                   # UPDATED
└── .env.example

alliance_20260317_130542/
├── src/jarvis/
│   ├── service/
│   │   ├── application.py
│   │   └── protocol.py
│   └── web_api.py                 # NEW
└── pyproject.toml                 # UPDATED
```

## API Response Flow

```
User Input
    ↓
App.tsx (handleSendMessage)
    ↓
useJarvis Hook
    ↓
API Client (apiClient.ask)
    ↓
FastAPI Backend (/api/ask)
    ↓
JarvisApplicationService.handle()
    ↓
RPC Request (ask_text)
    ↓
JARVIS Core (RAG Pipeline)
    ↓
Response
    ↓
App.tsx (update store)
    ↓
UI (messages, assets, citations)
```

## License

MIT License - Same as main JARVIS project

## Support

For issues or questions:
1. Check the main JARVIS documentation
2. Review the integration report: `INTEGRATION_REPORT.md`
3. Check browser console and backend logs
