import Foundation

private func bridgeLog(_ message: String) {
    fputs("[JarvisBridge] \(message)\n", stderr)
}

private struct OneShotCommandResult {
    let output: Data
    let stderr: Data
    let terminationStatus: Int32
}

private final class OneShotPipeBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var data = Data()

    func set(_ newData: Data) {
        lock.lock()
        data = newData
        lock.unlock()
    }

    func get() -> Data {
        lock.lock()
        defer { lock.unlock() }
        return data
    }
}

private func summarizeOneShotFailure(_ result: OneShotCommandResult, label: String) -> String {
    let stderrText = String(decoding: result.stderr, as: UTF8.self)
        .trimmingCharacters(in: .whitespacesAndNewlines)
    if !stderrText.isEmpty {
        return "\(label) failed (status=\(result.terminationStatus)): \(stderrText)"
    }
    return "\(label) failed (status=\(result.terminationStatus), stdout=\(result.output.count)B, stderr=\(result.stderr.count)B)"
}

private func legacyAskResponse(_ response: MenuResponse?) -> ServiceAskResponse? {
    guard let response else { return nil }
    return ServiceAskResponse(response: response, answer: nil, guide: nil)
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
    private let stderrLock = NSLock()
    private var recentStderrLines: [String] = []

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
                        let lineString = String(line)
                        self.stderrLock.lock()
                        self.recentStderrLines.append(lineString)
                        if self.recentStderrLines.count > 20 {
                            self.recentStderrLines.removeFirst(self.recentStderrLines.count - 20)
                        }
                        self.stderrLock.unlock()
                        bridgeLog("py: \(lineString)")
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
            let data = Data(lineData)
            do {
                let envelope = try decoder.decode(CommandEnvelope.self, from: data)
                return envelope
            } catch {
                let preview = String(data: data.prefix(200), encoding: .utf8) ?? "<binary>"
                bridgeLog("⚠️ envelope decode failed: \(error.localizedDescription) — raw: \(preview)")
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

    func stderrSummary() -> String {
        stderrLock.lock()
        defer { stderrLock.unlock() }
        return recentStderrLines.suffix(5).joined(separator: " | ")
    }
}

// MARK: - JarvisBridge Actor

actor JarvisBridge {
    private let maxStartupAttempts = 3
    private let configuration: BridgeConfiguration
    private var knowledgeBaseOverridePath: String?
    private var session: ServerSession?
    private(set) var isServerReady = false
    private var startingUp = false
    private var startupProgressMessage = ""
    private var startupWaiters: [CheckedContinuation<ServerSession, Error>] = []

    init(configuration: BridgeConfiguration = .default(), knowledgeBaseOverridePath: String? = nil) {
        self.configuration = configuration
        self.knowledgeBaseOverridePath = Self.normalizedKnowledgeBasePath(knowledgeBaseOverridePath)
    }

    private static func normalizedKnowledgeBasePath(_ path: String?) -> String? {
        guard let path else { return nil }
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        let expanded = (trimmed as NSString).expandingTildeInPath
        return URL(fileURLWithPath: expanded, isDirectory: true).standardizedFileURL.path
    }

    private func bridgeEnvironment() -> [String: String] {
        configuredBridgeEnvironment(
            from: ProcessInfo.processInfo.environment,
            configuration: configuration,
            knowledgeBaseOverridePath: knowledgeBaseOverridePath
        )
    }

    func effectiveKnowledgeBasePath() -> String {
        knowledgeBaseOverridePath ?? configuration.defaultKnowledgeBasePath
    }

    func currentStartupProgress() -> String {
        startupProgressMessage
    }

    func startupInProgress() -> Bool {
        startingUp
    }

    func updateKnowledgeBasePath(_ path: String?) {
        let normalized = Self.normalizedKnowledgeBasePath(path)
        guard normalized != knowledgeBaseOverridePath else { return }
        session?.shutdown()
        session = nil
        isServerReady = false
        knowledgeBaseOverridePath = normalized
        startupProgressMessage = ""
        bridgeLog("Knowledge base path updated: \(effectiveKnowledgeBasePath())")
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
        startupProgressMessage = "지식기반과 런타임을 준비하는 중입니다."

        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            finishStartup(error: BridgeError.missingPython(pythonURL.path))
            throw BridgeError.missingPython(pythonURL.path)
        }

        for attempt in 1...maxStartupAttempts {
            let newSession = try launchServerProcess(pythonURL: pythonURL)
            do {
                try await waitForServerReady(newSession)
                bridgeLog("Persistent server ready")
                self.session = newSession
                self.isServerReady = true
                finishStartup(session: newSession)
                return newSession
            } catch {
                let isRetriableStartupFailure = error.localizedDescription.contains("Server exited before ready")
                if isRetriableStartupFailure && attempt < maxStartupAttempts {
                    bridgeLog("Retrying persistent server startup (attempt \(attempt + 1)/\(maxStartupAttempts))")
                    try? await Task.sleep(nanoseconds: 250_000_000)
                    continue
                }
                finishStartup(error: error)
                throw error
            }
        }
        let fallbackError = BridgeError.processFailed("Server exited before ready after \(maxStartupAttempts) attempts")
        finishStartup(error: fallbackError)
        throw fallbackError
    }

    private func launchServerProcess(pythonURL: URL) throws -> ServerSession {
        let process = Process()
        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = pythonURL
        process.currentDirectoryURL = configuration.allianceRoot
        process.arguments = ["-u", "-m", "jarvis.cli.menu_bridge", "server"]

        var env = bridgeEnvironment()
        // Vocabulary hint for STT: domain-specific terms that whisper often misrecognizes.
        // Passed as --prompt to whisper.cpp to bias the decoder toward correct transcription.
        env["JARVIS_STT_VOCAB"] = env["JARVIS_STT_VOCAB"] ?? "JARVIS, OLE, API, SQL, JSON, YAML, MLX, EXAONE, Qwen, LLM, RAG, FTS, RRF, STT, TTS, VAD, MCP, BGE, LanceDB, PyMuPDF, 개체, 속성, 스키마, 인덱스, 벡터, 임베딩, 토큰, 프롬프트, 파이프라인"

        process.environment = env
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        try process.run()
        bridgeLog("Persistent server launched (pid=\(process.processIdentifier))")

        return ServerSession(
            process: process,
            stdinPipe: stdinPipe,
            stdoutPipe: stdoutPipe,
            stderrPipe: stderrPipe
        )
    }

    private func waitForServerReady(_ newSession: ServerSession) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            DispatchQueue.global(qos: .userInitiated).async {
                while true {
                    guard let envelope = newSession.readEnvelope() else {
                        if newSession.process.isRunning {
                            newSession.process.waitUntilExit()
                        }
                        continuation.resume(
                            throwing: BridgeError.processFailed(Self.startupFailureDetail(for: newSession))
                        )
                        return
                    }
                    if envelope.kind == "ready" {
                        Task { await self.clearStartupProgress() }
                        continuation.resume()
                        return
                    }
                    if envelope.kind == "progress" {
                        Task { await self.setStartupProgress(envelope.progressResult?.message ?? "") }
                        continue
                    }
                    if envelope.kind == "error" {
                        continuation.resume(throwing: BridgeError.processFailed(envelope.error ?? "Startup error"))
                        return
                    }
                }
            }
        }
    }

    private static func startupFailureDetail(for session: ServerSession) -> String {
        let status = session.process.terminationStatus
        let reason: String
        switch session.process.terminationReason {
        case .uncaughtSignal:
            reason = "signal"
        case .exit:
            reason = "exit"
        @unknown default:
            reason = "unknown"
        }
        let stderrSummary = session.stderrSummary()
        if stderrSummary.isEmpty {
            return "Server exited before ready (\(reason)=\(status))"
        }
        return "Server exited before ready (\(reason)=\(status)): \(stderrSummary)"
    }

    /// Resume any waiters after server startup completes or fails.
    private func finishStartup(session: ServerSession? = nil, error: Error? = nil) {
        startingUp = false
        if error != nil {
            startupProgressMessage = ""
        }
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
            let description = error.localizedDescription
            if description.contains("Server exited before ready") {
                bridgeLog("Warmup retry after early exit before ready")
                do {
                    _ = try await ensureServer()
                    return
                } catch {
                    bridgeLog("Warmup retry failed: \(error.localizedDescription)")
                }
            }
            bridgeLog("Warmup failed: \(description)")
        }
    }

    /// Shut down the persistent server process.
    func shutdown() {
        session?.shutdown()
        session = nil
        isServerReady = false
        startupProgressMessage = ""
        bridgeLog("Server shutdown requested")
    }

    private func setStartupProgress(_ message: String) {
        startupProgressMessage = message
    }

    private func clearStartupProgress() {
        startupProgressMessage = ""
    }

    // MARK: - Commands via Persistent Server

    func ask(_ query: String) async throws -> MenuResponse {
        try runOneShotAsk(query: query)
    }

    func askStreaming(_ query: String) async -> AsyncStream<StreamEvent> {
        return AsyncStream { continuation in
            Task.detached {
                do {
                    let response = try await self.ask(query)
                    continuation.yield(.done(legacyAskResponse(response)))
                } catch {
                    continuation.yield(.error(error.localizedDescription))
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
                        continuation.yield(.done(legacyAskResponse(envelope.queryResult)))
                        continuation.finish()
                        return
                    case "query_result":
                        continuation.yield(.done(legacyAskResponse(envelope.queryResult)))
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
        try runOneShotTranscribeFile(audioPath: audioPath)
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
        let result = try runOneShotProcess(
            arguments: ["-u", "-m", "jarvis.cli.menu_bridge", "health"],
            logLabel: "health"
        )
        let output = result.output
        guard !output.isEmpty else {
            throw BridgeError.processFailed(summarizeOneShotFailure(result, label: "health"))
        }

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
        let result = try runOneShotProcess(
            arguments: ["-u", "-m", "jarvis.cli.menu_bridge", "navigation-window", "--query", query],
            logLabel: "navigation-window"
        )
        let output = result.output
        let stderr = result.stderr
        guard !output.isEmpty else {
            throw BridgeError.processFailed(summarizeOneShotFailure(result, label: "navigation-window"))
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
        let result = try runOneShotProcess(
            arguments: ["-u", "-m", "jarvis.cli.menu_bridge", "normalize-query", "--query", query],
            logLabel: "normalize-query"
        )
        let output = result.output
        let stderr = result.stderr
        guard !output.isEmpty else {
            throw BridgeError.processFailed(summarizeOneShotFailure(result, label: "normalize-query"))
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

    private func runOneShotAsk(query: String) throws -> MenuResponse {
        let result = try runOneShotProcess(
            arguments: ["-u", "-m", "jarvis.cli.menu_bridge", "ask", "--query", query],
            logLabel: "ask"
        )
        let output = result.output
        let stderr = result.stderr
        guard !output.isEmpty else {
            throw BridgeError.processFailed(summarizeOneShotFailure(result, label: "ask"))
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
                if let response = envelope.queryResult {
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

    private func runOneShotTranscribeFile(audioPath: String) throws -> TranscriptionResponse {
        let result = try runOneShotProcess(
            arguments: ["-u", "-m", "jarvis.cli.menu_bridge", "transcribe-file", "--audio", audioPath],
            logLabel: "transcribe-file"
        )
        let output = result.output
        let stderr = result.stderr
        guard !output.isEmpty else {
            throw BridgeError.processFailed(summarizeOneShotFailure(result, label: "transcribe-file"))
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
                if let response = envelope.transcriptionResult {
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

    private func runOneShotProcess(arguments: [String], logLabel: String) throws -> OneShotCommandResult {
        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        let process = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        process.executableURL = pythonURL
        process.currentDirectoryURL = configuration.allianceRoot
        process.arguments = arguments
        process.environment = bridgeEnvironment()
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        bridgeLog("One-shot \(logLabel) started")
        try process.run()
        let group = DispatchGroup()
        let outputBuffer = OneShotPipeBuffer()
        let stderrBuffer = OneShotPipeBuffer()

        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            let data = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
            outputBuffer.set(data)
            group.leave()
        }

        group.enter()
        DispatchQueue.global(qos: .userInitiated).async {
            let data = stderrPipe.fileHandleForReading.readDataToEndOfFile()
            stderrBuffer.set(data)
            group.leave()
        }

        process.waitUntilExit()
        group.wait()
        bridgeLog("One-shot \(logLabel) finished with status=\(process.terminationStatus)")

        return OneShotCommandResult(
            output: outputBuffer.get(),
            stderr: stderrBuffer.get(),
            terminationStatus: process.terminationStatus
        )
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

        process.environment = bridgeEnvironment()
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

        // Each wake-audio chunk receives either wake_idle or wake_detected.
        // That keeps the pipe flowing and avoids stalling on the first read.
        let available = stdoutPipe.fileHandleForReading.availableData
        if available.isEmpty { return false }
        buffer.append(available)

        while let newlineIndex = buffer.firstIndex(of: UInt8(ascii: "\n")) {
            let lineData = buffer[buffer.startIndex..<newlineIndex]
            buffer = Data(buffer[buffer.index(after: newlineIndex)...])

            guard !lineData.isEmpty,
                  let envelope = try? decoder.decode(CommandEnvelope.self, from: Data(lineData))
            else { continue }

            if envelope.kind == "wake_detected" {
                bridgeLog("Wake word detected via bridge (score=\(envelope.score ?? 0))")
                return true
            }
            if envelope.kind == "wake_idle" {
                return false
            }
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
