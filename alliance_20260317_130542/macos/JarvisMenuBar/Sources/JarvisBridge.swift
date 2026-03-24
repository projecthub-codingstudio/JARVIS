import Foundation

private func bridgeLog(_ message: String) {
    fputs("[JarvisBridge] \(message)\n", stderr)
}

struct BridgeConfiguration {
    let allianceRoot: URL
    let pythonExecutable: String

    var pythonPath: String {
        allianceRoot.appendingPathComponent("src").path
    }

    var knowledgeBasePath: String? {
        let fileManager = FileManager.default
        let candidates = [
            allianceRoot.appendingPathComponent("knowledge_base").path,
            allianceRoot.deletingLastPathComponent().appendingPathComponent("knowledge_base").path,
        ]
        return candidates.first(where: { fileManager.fileExists(atPath: $0) })
    }

    var defaultSTTBinary: String? {
        let fileManager = FileManager.default
        let candidates = [
            allianceRoot.appendingPathComponent(".venv/bin/whisper-cli").path,
            allianceRoot.appendingPathComponent(".venv/bin/main").path,
            "/opt/homebrew/bin/whisper-cli",
            "/opt/homebrew/bin/main",
            "/usr/local/bin/whisper-cli",
            "/usr/local/bin/main",
            "/usr/bin/whisper-cli",
            "/usr/bin/main",
        ]
        return candidates.first(where: { fileManager.fileExists(atPath: $0) })
    }

    var defaultSTTModel: String? {
        let fileManager = FileManager.default
        let candidates = [
            allianceRoot.appendingPathComponent("models/ggml-small.bin").path,
            allianceRoot.appendingPathComponent("models/ggml-base.bin").path,
            allianceRoot.appendingPathComponent("models/ggml-medium.bin").path,
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".jarvis/models/ggml-small.bin").path,
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".jarvis/models/ggml-base.bin").path,
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".jarvis/models/ggml-medium.bin").path,
        ]
        return candidates.first(where: { fileManager.fileExists(atPath: $0) })
    }

    static func `default`() -> BridgeConfiguration {
        if let explicitRoot = ProcessInfo.processInfo.environment["JARVIS_ALLIANCE_ROOT"] {
            let rootURL = URL(fileURLWithPath: explicitRoot, isDirectory: true)
            return BridgeConfiguration(
                allianceRoot: rootURL,
                pythonExecutable: resolvePythonExecutable(
                    preferred: ProcessInfo.processInfo.environment["JARVIS_PYTHON"],
                    allianceRoot: rootURL
                )
            )
        }

        var rootURL = URL(fileURLWithPath: #filePath, isDirectory: false)
        for _ in 0..<4 {
            rootURL.deleteLastPathComponent()
        }
        return BridgeConfiguration(
            allianceRoot: rootURL,
            pythonExecutable: resolvePythonExecutable(
                preferred: ProcessInfo.processInfo.environment["JARVIS_PYTHON"],
                allianceRoot: rootURL
            )
        )
    }

    private static func resolvePythonExecutable(preferred: String?, allianceRoot: URL) -> String {
        let fileManager = FileManager.default

        if let preferred, fileManager.fileExists(atPath: preferred) {
            return preferred
        }

        let candidates = [
            allianceRoot.appendingPathComponent(".venv/bin/python3").path,
            allianceRoot.appendingPathComponent(".venv/bin/python").path,
            "/opt/homebrew/opt/python@3.12/bin/python3.12",
            "/usr/bin/python3",
        ]

        for candidate in candidates where fileManager.fileExists(atPath: candidate) {
            return candidate
        }

        return allianceRoot.appendingPathComponent(".venv/bin/python3").path
    }
}

private func configuredBridgeEnvironment(
    from base: [String: String],
    configuration: BridgeConfiguration
) -> [String: String] {
    var env = base
    env["PYTHONPATH"] = configuration.pythonPath
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = env["HF_HUB_DISABLE_PROGRESS_BARS"] ?? "1"
    env["TRANSFORMERS_VERBOSITY"] = env["TRANSFORMERS_VERBOSITY"] ?? "error"
    env["TOKENIZERS_PARALLELISM"] = env["TOKENIZERS_PARALLELISM"] ?? "false"
    env["HF_HUB_DISABLE_TELEMETRY"] = env["HF_HUB_DISABLE_TELEMETRY"] ?? "1"
    env["TRUST_REMOTE_CODE"] = env["TRUST_REMOTE_CODE"] ?? "1"
    if let knowledgeBasePath = configuration.knowledgeBasePath {
        env["JARVIS_KNOWLEDGE_BASE"] = env["JARVIS_KNOWLEDGE_BASE"] ?? knowledgeBasePath
    }
    if let sttBinary = configuration.defaultSTTBinary {
        env["JARVIS_STT_BINARY"] = env["JARVIS_STT_BINARY"] ?? sttBinary
    }
    if let sttModel = configuration.defaultSTTModel {
        env["JARVIS_STT_MODEL"] = env["JARVIS_STT_MODEL"] ?? sttModel
    }
    return env
}

enum BridgeError: LocalizedError {
    case missingPython(String)
    case processFailed(String)
    case emptyResponse
    case decodeFailed(String)
    case serverNotReady

    var errorDescription: String? {
        switch self {
        case .missingPython(let path):
            return "Python 실행 파일을 찾을 수 없습니다: \(path)"
        case .processFailed(let message):
            return "JARVIS 브리지 실행 실패: \(message)"
        case .emptyResponse:
            return "JARVIS 브리지에서 응답이 비어 있습니다."
        case .decodeFailed(let payload):
            return "브리지 JSON 파싱 실패: \(payload)"
        case .serverNotReady:
            return "JARVIS 서버가 아직 준비되지 않았습니다. 잠시 후 다시 시도해 주세요."
        }
    }
}

// MARK: - Persistent Server Session

/// Manages a single persistent Python bridge server process.
/// The process stays alive across multiple commands.
final class ServerSession: @unchecked Sendable {
    let process: Process
    let stdinPipe: Pipe
    let stdoutPipe: Pipe
    let stderrPipe: Pipe
    private let decoder = JSONDecoder()
    private var readBuffer = Data()
    private var stderrDrainThread: Thread?

    init(process: Process, stdinPipe: Pipe, stdoutPipe: Pipe, stderrPipe: Pipe) {
        self.process = process
        self.stdinPipe = stdinPipe
        self.stdoutPipe = stdoutPipe
        self.stderrPipe = stderrPipe

        // Drain stderr in background to prevent pipe buffer deadlock.
        // Without this, Python blocks when stderr buffer (64KB) fills up.
        let errHandle = stderrPipe.fileHandleForReading
        let thread = Thread {
            while true {
                let data = errHandle.availableData
                if data.isEmpty { break }  // EOF — process exited
                if let text = String(data: data, encoding: .utf8), !text.isEmpty {
                    for line in text.split(whereSeparator: \.isNewline) {
                        bridgeLog("py: \(line)")
                    }
                }
            }
        }
        thread.qualityOfService = .utility
        thread.name = "jarvis-stderr-drain"
        thread.start()
        stderrDrainThread = thread
    }

    var isRunning: Bool { process.isRunning }

    /// Send a JSON command to the server's stdin.
    func sendJSON(_ payload: [String: Any]) throws {
        let data = try JSONSerialization.data(withJSONObject: payload)
        stdinPipe.fileHandleForWriting.write(data)
        stdinPipe.fileHandleForWriting.write("\n".data(using: .utf8)!)
    }

    /// Read the next complete JSON envelope from stdout (blocking).
    func readEnvelope() -> CommandEnvelope? {
        if let envelope = extractEnvelopeFromBuffer() {
            return envelope
        }
        while true {
            let data = stdoutPipe.fileHandleForReading.availableData
            if data.isEmpty { return nil }
            readBuffer.append(data)
            if let envelope = extractEnvelopeFromBuffer() {
                return envelope
            }
        }
    }

    private func extractEnvelopeFromBuffer() -> CommandEnvelope? {
        while let newlineIndex = readBuffer.firstIndex(of: UInt8(ascii: "\n")) {
            let lineData = readBuffer[readBuffer.startIndex..<newlineIndex]
            readBuffer = Data(readBuffer[readBuffer.index(after: newlineIndex)...])
            guard !lineData.isEmpty else { continue }
            if let envelope = try? decoder.decode(CommandEnvelope.self, from: Data(lineData)) {
                return envelope
            }
        }
        return nil
    }

    func shutdown() {
        try? sendJSON(["command": "shutdown"])
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) { [process] in
            if process.isRunning { process.terminate() }
        }
    }
}

// MARK: - JarvisBridge Actor

actor JarvisBridge {
    private let configuration: BridgeConfiguration
    private var session: ServerSession?
    private(set) var isServerReady = false
    private var startingUp = false
    private var startupWaiters: [CheckedContinuation<ServerSession, Error>] = []

    init(configuration: BridgeConfiguration = .default()) {
        self.configuration = configuration
    }

    // MARK: - Server Lifecycle

    /// Launch the persistent server if not already running.
    /// Uses async continuation so the actor is NOT blocked during startup.
    private func ensureServer() async throws -> ServerSession {
        if let session, session.isRunning {
            return session
        }

        // If another caller is already starting the server, wait for it
        if startingUp {
            return try await withCheckedThrowingContinuation { continuation in
                startupWaiters.append(continuation)
            }
        }

        // Clean up dead session
        session = nil
        isServerReady = false
        startingUp = true

        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            finishStartup(error: BridgeError.missingPython(pythonURL.path))
            throw BridgeError.missingPython(pythonURL.path)
        }

        let process = Process()
        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = pythonURL
        process.currentDirectoryURL = configuration.allianceRoot
        process.arguments = ["-u", "-m", "jarvis.cli.menu_bridge", "server"]

        var env = configuredBridgeEnvironment(
            from: ProcessInfo.processInfo.environment,
            configuration: configuration
        )
        // Vocabulary hint for STT: domain-specific terms that whisper often misrecognizes.
        // Passed as --prompt to whisper.cpp to bias the decoder toward correct transcription.
        env["JARVIS_STT_VOCAB"] = env["JARVIS_STT_VOCAB"] ?? "JARVIS, OLE, API, SQL, JSON, YAML, MLX, EXAONE, Qwen, LLM, RAG, FTS, RRF, STT, TTS, VAD, MCP, BGE, LanceDB, PyMuPDF, 개체, 속성, 스키마, 인덱스, 벡터, 임베딩, 토큰, 프롬프트, 파이프라인"

        process.environment = env
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()
        bridgeLog("Persistent server launched (pid=\(process.processIdentifier))")

        let newSession = ServerSession(
            process: process,
            stdinPipe: stdinPipe,
            stdoutPipe: stdoutPipe,
            stderrPipe: stderrPipe
        )

        // Wait for "ready" WITHOUT blocking the actor — use continuation
        do {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                DispatchQueue.global(qos: .userInitiated).async {
                    while true {
                        guard let envelope = newSession.readEnvelope() else {
                            continuation.resume(throwing: BridgeError.processFailed("Server exited before ready"))
                            return
                        }
                        if envelope.kind == "ready" {
                            continuation.resume()
                            return
                        }
                        if envelope.kind == "error" {
                            continuation.resume(throwing: BridgeError.processFailed(envelope.error ?? "Startup error"))
                            return
                        }
                    }
                }
            }
        } catch {
            finishStartup(error: error)
            throw error
        }

        bridgeLog("Persistent server ready")
        self.session = newSession
        self.isServerReady = true
        finishStartup(session: newSession)
        return newSession
    }

    /// Resume any waiters after server startup completes or fails.
    private func finishStartup(session: ServerSession? = nil, error: Error? = nil) {
        startingUp = false
        for waiter in startupWaiters {
            if let session {
                waiter.resume(returning: session)
            } else if let error {
                waiter.resume(throwing: error)
            }
        }
        startupWaiters.removeAll()
    }

    /// Eagerly start the server in the background so the first query is fast.
    func warmup() async {
        do {
            _ = try await ensureServer()
        } catch {
            bridgeLog("Warmup failed: \(error.localizedDescription)")
        }
    }

    /// Shut down the persistent server process.
    func shutdown() {
        session?.shutdown()
        session = nil
        isServerReady = false
        bridgeLog("Server shutdown requested")
    }

    // MARK: - Commands via Persistent Server

    func ask(_ query: String) async throws -> MenuResponse {
        let server = try await ensureServer()
        try server.sendJSON(["command": "ask", "query": query])
        while let envelope = server.readEnvelope() {
            switch envelope.kind {
            case "query_result":
                guard let response = envelope.queryResult else {
                    throw BridgeError.decodeFailed("missing query_result")
                }
                return response
            case "error":
                throw BridgeError.processFailed(envelope.error ?? "unknown server error")
            default:
                continue
            }
        }
        throw BridgeError.emptyResponse
    }

    func askStreaming(_ query: String) async -> AsyncStream<StreamEvent> {
        // Actor-isolated setup: start server and send command
        let server: ServerSession
        do {
            server = try await ensureServer()
            try server.sendJSON(["command": "ask", "query": query, "stream": true])
        } catch {
            return AsyncStream { continuation in
                continuation.yield(.error(error.localizedDescription))
                continuation.finish()
            }
        }

        // Streaming read runs on a detached task (ServerSession is Sendable)
        return AsyncStream { continuation in
            Task.detached {
                while true {
                    guard let envelope = server.readEnvelope() else {
                        continuation.yield(.error("서버 연결이 끊어졌습니다."))
                        break
                    }
                    switch envelope.kind {
                    case "stream_chunk":
                        if let token = envelope.token {
                            continuation.yield(.token(token))
                        }
                    case "stream_done":
                        continuation.yield(.done(envelope.queryResult))
                        continuation.finish()
                        return
                    case "error":
                        continuation.yield(.error(envelope.error ?? "unknown server error"))
                        continuation.finish()
                        return
                    default:
                        break
                    }
                }
                continuation.finish()
            }
        }
    }

    func recordOnce(device: String? = nil) async throws -> MenuResponse {
        let server = try await ensureServer()
        var payload: [String: Any] = ["command": "record-once"]
        if let device, !device.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["device"] = device
        }
        try server.sendJSON(payload)
        while let envelope = server.readEnvelope() {
            switch envelope.kind {
            case "query_result":
                guard let response = envelope.queryResult else {
                    throw BridgeError.decodeFailed("missing query_result")
                }
                return response
            case "stream_chunk":
                continue  // Ignore streaming chunks in non-streaming mode
            case "stream_done":
                guard let response = envelope.queryResult else {
                    throw BridgeError.decodeFailed("missing query_result in stream_done")
                }
                return response
            case "error":
                throw BridgeError.processFailed(envelope.error ?? "unknown server error")
            default:
                continue
            }
        }
        throw BridgeError.emptyResponse
    }

    func recordOnceStreaming(device: String? = nil) async -> AsyncStream<StreamEvent> {
        let server: ServerSession
        do {
            server = try await ensureServer()
            var payload: [String: Any] = ["command": "record-once", "stream": true]
            if let device, !device.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                payload["device"] = device
            }
            try server.sendJSON(payload)
        } catch {
            return AsyncStream { continuation in
                continuation.yield(.error(error.localizedDescription))
                continuation.finish()
            }
        }

        return AsyncStream { continuation in
            Task.detached {
                while true {
                    guard let envelope = server.readEnvelope() else {
                        continuation.yield(.error("서버 연결이 끊어졌습니다."))
                        break
                    }
                    switch envelope.kind {
                    case "stream_chunk":
                        if let token = envelope.token {
                            continuation.yield(.token(token))
                        }
                    case "stream_done":
                        continuation.yield(.done(envelope.queryResult))
                        continuation.finish()
                        return
                    case "query_result":
                        continuation.yield(.done(envelope.queryResult))
                        continuation.finish()
                        return
                    case "error":
                        continuation.yield(.error(envelope.error ?? "unknown server error"))
                        continuation.finish()
                        return
                    default:
                        break
                    }
                }
                continuation.finish()
            }
        }
    }

    func transcribeOnce(device: String? = nil) async throws -> TranscriptionResponse {
        let server = try await ensureServer()
        var payload: [String: Any] = ["command": "transcribe-once"]
        if let device, !device.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["device"] = device
        }
        try server.sendJSON(payload)
        while let envelope = server.readEnvelope() {
            switch envelope.kind {
            case "transcription_result":
                guard let response = envelope.transcriptionResult else {
                    throw BridgeError.decodeFailed("missing transcription_result")
                }
                return response
            case "error":
                throw BridgeError.processFailed(envelope.error ?? "unknown server error")
            default:
                continue
            }
        }
        throw BridgeError.emptyResponse
    }

    func transcribeFile(audioPath: String) async throws -> TranscriptionResponse {
        let server = try await ensureServer()
        try server.sendJSON(["command": "transcribe-file", "audio": audioPath])
        while let envelope = server.readEnvelope() {
            switch envelope.kind {
            case "transcription_result":
                guard let response = envelope.transcriptionResult else {
                    throw BridgeError.decodeFailed("missing transcription_result")
                }
                return response
            case "error":
                throw BridgeError.processFailed(envelope.error ?? "unknown server error")
            default:
                continue
            }
        }
        throw BridgeError.emptyResponse
    }

    func navigationWindow(query: String) async throws -> MenuExplorationState {
        try runOneShotNavigationWindow(query: query)
    }

    func normalizeQuery(_ query: String) async throws -> String {
        try runOneShotNormalizeQuery(query: query)
    }

    func synthesizeSpeech(text: String) async throws -> SpeechResponse {
        let server = try await ensureServer()
        try server.sendJSON(["command": "synthesize-speech", "text": text])
        while let envelope = server.readEnvelope() {
            switch envelope.kind {
            case "speech_result":
                guard let response = envelope.speechResult else {
                    throw BridgeError.decodeFailed("missing speech_result")
                }
                return response
            case "error":
                throw BridgeError.processFailed(envelope.error ?? "unknown server error")
            default:
                continue
            }
        }
        throw BridgeError.emptyResponse
    }

    func exportDraft(content: String, destination: String, approved: Bool) async throws -> ExportResponse {
        let server = try await ensureServer()
        try server.sendJSON([
            "command": "export-draft",
            "content": content,
            "destination": destination,
            "approved": approved,
        ])
        while let envelope = server.readEnvelope() {
            switch envelope.kind {
            case "export_result":
                guard let response = envelope.exportResult else {
                    throw BridgeError.decodeFailed("missing export_result")
                }
                return response
            case "error":
                throw BridgeError.processFailed(envelope.error ?? "unknown server error")
            default:
                continue
            }
        }
        throw BridgeError.emptyResponse
    }

    // MARK: - Health (lightweight one-shot, no server needed)

    func health() async throws -> HealthResponse {
        // Use persistent server if available (instant)
        if let session, session.isRunning {
            try session.sendJSON(["command": "health"])
            while let envelope = session.readEnvelope() {
                switch envelope.kind {
                case "health_result":
                    guard let response = envelope.healthResult else {
                        throw BridgeError.decodeFailed("missing health_result")
                    }
                    return response
                case "error":
                    throw BridgeError.processFailed(envelope.error ?? "unknown server error")
                default:
                    continue
                }
            }
            throw BridgeError.emptyResponse
        }

        // Fallback: lightweight one-shot health (fast, ~1s)
        return try runOneShotHealth()
    }

    private func runOneShotHealth() throws -> HealthResponse {
        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = pythonURL
        process.currentDirectoryURL = configuration.allianceRoot
        process.arguments = ["-u", "-m", "jarvis.cli.menu_bridge", "health"]

        process.environment = configuredBridgeEnvironment(
            from: ProcessInfo.processInfo.environment,
            configuration: configuration
        )
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()
        process.waitUntilExit()

        let output = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        guard !output.isEmpty else { throw BridgeError.emptyResponse }

        let decoder = JSONDecoder()
        let outputText = String(decoding: output, as: UTF8.self)
        let lines = outputText
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        // Try last line first (may have stderr noise before JSON)
        for line in lines.reversed() {
            if let data = line.data(using: .utf8),
               let envelope = try? decoder.decode(CommandEnvelope.self, from: data),
               let health = envelope.healthResult {
                return health
            }
        }
        throw BridgeError.decodeFailed(outputText)
    }

    private func runOneShotNavigationWindow(query: String) throws -> MenuExplorationState {
        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = pythonURL
        process.currentDirectoryURL = configuration.allianceRoot
        process.arguments = ["-u", "-m", "jarvis.cli.menu_bridge", "navigation-window", "--query", query]
        process.environment = configuredBridgeEnvironment(
            from: ProcessInfo.processInfo.environment,
            configuration: configuration
        )
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()
        process.waitUntilExit()

        let output = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        guard !output.isEmpty else {
            let stderrText = String(decoding: stderr, as: UTF8.self)
            if !stderrText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                throw BridgeError.processFailed(stderrText)
            }
            throw BridgeError.emptyResponse
        }

        let decoder = JSONDecoder()
        let outputText = String(decoding: output, as: UTF8.self)
        let lines = outputText
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        for line in lines.reversed() {
            if let data = line.data(using: .utf8),
               let envelope = try? decoder.decode(CommandEnvelope.self, from: data) {
                if let response = envelope.navigationResult {
                    return response
                }
                if let error = envelope.error, !error.isEmpty {
                    throw BridgeError.processFailed(error)
                }
            }
        }

        let stderrText = String(decoding: stderr, as: UTF8.self)
        if !stderrText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw BridgeError.decodeFailed(outputText + "\n" + stderrText)
        }
        throw BridgeError.decodeFailed(outputText)
    }

    private func runOneShotNormalizeQuery(query: String) throws -> String {
        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = pythonURL
        process.currentDirectoryURL = configuration.allianceRoot
        process.arguments = ["-u", "-m", "jarvis.cli.menu_bridge", "normalize-query", "--query", query]
        process.environment = configuredBridgeEnvironment(
            from: ProcessInfo.processInfo.environment,
            configuration: configuration
        )
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()
        process.waitUntilExit()

        let output = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        guard !output.isEmpty else {
            let stderrText = String(decoding: stderr, as: UTF8.self)
            if !stderrText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                throw BridgeError.processFailed(stderrText)
            }
            throw BridgeError.emptyResponse
        }

        let decoder = JSONDecoder()
        let outputText = String(decoding: output, as: UTF8.self)
        let lines = outputText
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        for line in lines.reversed() {
            if let data = line.data(using: .utf8),
               let envelope = try? decoder.decode(CommandEnvelope.self, from: data) {
                if let response = envelope.normalizationResult {
                    return response.normalizedQuery
                }
                if let error = envelope.error, !error.isEmpty {
                    throw BridgeError.processFailed(error)
                }
            }
        }

        let stderrText = String(decoding: stderr, as: UTF8.self)
        if !stderrText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw BridgeError.decodeFailed(outputText + "\n" + stderrText)
        }
        throw BridgeError.decodeFailed(outputText)
    }

    // MARK: - Wake Word (separate server process)

    func startWakeWordSession() async throws -> WakeWordSession {
        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        let process = Process()
        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = pythonURL
        process.currentDirectoryURL = configuration.allianceRoot
        process.arguments = ["-u", "-m", "jarvis.cli.menu_bridge", "server"]

        process.environment = configuredBridgeEnvironment(
            from: ProcessInfo.processInfo.environment,
            configuration: configuration
        )
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()
        bridgeLog("Wake word server launched")

        let decoder = JSONDecoder()
        let fileHandle = stdoutPipe.fileHandleForReading

        // Wait for ready
        var ready = false
        while !ready {
            let available = fileHandle.availableData
            if available.isEmpty { continue }
            for lineData in available.split(separator: UInt8(ascii: "\n")) {
                if let envelope = try? decoder.decode(CommandEnvelope.self, from: Data(lineData)),
                   envelope.kind == "ready" {
                    ready = true
                }
            }
        }

        // Send wake-listen-start
        let startCmd = try JSONSerialization.data(withJSONObject: ["command": "wake-listen-start"])
        stdinPipe.fileHandleForWriting.write(startCmd)
        stdinPipe.fileHandleForWriting.write("\n".data(using: .utf8)!)

        // Wait for wake_ready
        var wakeReady = false
        while !wakeReady {
            let available = fileHandle.availableData
            if available.isEmpty { continue }
            for lineData in available.split(separator: UInt8(ascii: "\n")) {
                if let envelope = try? decoder.decode(CommandEnvelope.self, from: Data(lineData)),
                   envelope.kind == "wake_ready" {
                    wakeReady = true
                }
            }
        }

        bridgeLog("Wake word session ready")
        return WakeWordSession(
            process: process,
            stdinPipe: stdinPipe,
            stdoutPipe: stdoutPipe,
            decoder: decoder
        )
    }
}

// MARK: - Wake Word Session

/// Persistent session for sending audio chunks to Python wake word detector.
final class WakeWordSession: @unchecked Sendable {
    private let process: Process
    private let stdinPipe: Pipe
    private let stdoutPipe: Pipe
    private let decoder: JSONDecoder
    private var buffer = Data()

    init(process: Process, stdinPipe: Pipe, stdoutPipe: Pipe, decoder: JSONDecoder) {
        self.process = process
        self.stdinPipe = stdinPipe
        self.stdoutPipe = stdoutPipe
        self.decoder = decoder
    }

    /// Send a 16kHz mono Int16 PCM audio chunk for wake word detection.
    ///
    /// Returns true if wake word was detected in this chunk.
    func sendAudioChunk(_ pcmData: Data) -> Bool {
        let b64 = pcmData.base64EncodedString()
        let payload: [String: Any] = ["command": "wake-audio", "pcm_b64": b64]
        guard let json = try? JSONSerialization.data(withJSONObject: payload) else { return false }
        stdinPipe.fileHandleForWriting.write(json)
        stdinPipe.fileHandleForWriting.write("\n".data(using: .utf8)!)

        // Check for detection response (non-blocking read)
        let available = stdoutPipe.fileHandleForReading.availableData
        if available.isEmpty { return false }
        buffer.append(available)

        while let newlineIndex = buffer.firstIndex(of: UInt8(ascii: "\n")) {
            let lineData = buffer[buffer.startIndex..<newlineIndex]
            buffer = Data(buffer[buffer.index(after: newlineIndex)...])

            guard !lineData.isEmpty,
                  let envelope = try? decoder.decode(CommandEnvelope.self, from: Data(lineData)),
                  envelope.kind == "wake_detected"
            else { continue }

            bridgeLog("Wake word detected via bridge (score=\(envelope.score ?? 0))")
            return true
        }
        return false
    }

    /// Stop the wake word session and terminate the Python process.
    func stop() {
        let stopCmd = try? JSONSerialization.data(withJSONObject: ["command": "shutdown"])
        if let cmd = stopCmd {
            stdinPipe.fileHandleForWriting.write(cmd)
            stdinPipe.fileHandleForWriting.write("\n".data(using: .utf8)!)
        }
        process.terminate()
    }

    var isRunning: Bool { process.isRunning }
}
