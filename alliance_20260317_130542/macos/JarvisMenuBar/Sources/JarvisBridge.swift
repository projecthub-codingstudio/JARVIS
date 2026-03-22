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

enum BridgeError: LocalizedError {
    case missingPython(String)
    case processFailed(String)
    case emptyResponse
    case decodeFailed(String)

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
        }
    }
}

actor JarvisBridge {
    private let configuration: BridgeConfiguration

    init(configuration: BridgeConfiguration = .default()) {
        self.configuration = configuration
    }

    func ask(_ query: String) async throws -> MenuResponse {
        try await send(query, command: "ask")
    }

    func recordOnce(device: String? = nil) async throws -> MenuResponse {
        var payload: [String: Any] = ["command": "record-once"]
        if let device, !device.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["device"] = device
        }
        let envelope = try await send(payload)
        guard let response = envelope.queryResult else {
            throw BridgeError.decodeFailed("missing query_result")
        }
        return response
    }

    func transcribeOnce(device: String? = nil) async throws -> TranscriptionResponse {
        var payload: [String: Any] = ["command": "transcribe-once"]
        if let device, !device.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            payload["device"] = device
        }
        let envelope = try await send(payload)
        guard let response = envelope.transcriptionResult else {
            throw BridgeError.decodeFailed("missing transcription_result")
        }
        return response
    }

    func transcribeFile(audioPath: String) async throws -> TranscriptionResponse {
        let envelope = try await send([
            "command": "transcribe-file",
            "audio": audioPath,
        ])
        guard let response = envelope.transcriptionResult else {
            throw BridgeError.decodeFailed("missing transcription_result")
        }
        return response
    }

    func exportDraft(content: String, destination: String, approved: Bool) async throws -> ExportResponse {
        let envelope = try await send([
            "command": "export-draft",
            "content": content,
            "destination": destination,
            "approved": approved,
        ])
        guard let response = envelope.exportResult else {
            throw BridgeError.decodeFailed("missing export_result")
        }
        return response
    }

    func health() async throws -> HealthResponse {
        let envelope = try await send(["command": "health"])
        guard let response = envelope.healthResult else {
            throw BridgeError.decodeFailed("missing health_result")
        }
        return response
    }

    private func runCommand(_ payload: [String: Any]) throws -> CommandEnvelope {
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
        process.arguments = [
            "-u",
            "-m", "jarvis.cli.menu_bridge",
            String(payload["command"] as? String ?? "ask"),
        ]

        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = configuration.pythonPath
        if environment["HF_HUB_DISABLE_PROGRESS_BARS"] == nil {
            environment["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        }
        if environment["TRANSFORMERS_VERBOSITY"] == nil {
            environment["TRANSFORMERS_VERBOSITY"] = "error"
        }
        if environment["TOKENIZERS_PARALLELISM"] == nil {
            environment["TOKENIZERS_PARALLELISM"] = "false"
        }
        // Suppress HuggingFace interactive prompts and tqdm output
        if environment["HF_HUB_DISABLE_TELEMETRY"] == nil {
            environment["HF_HUB_DISABLE_TELEMETRY"] = "1"
        }
        if environment["TRUST_REMOTE_CODE"] == nil {
            environment["TRUST_REMOTE_CODE"] = "1"
        }
        if environment["JARVIS_STT_BINARY"] == nil, let sttBinary = configuration.defaultSTTBinary {
            environment["JARVIS_STT_BINARY"] = sttBinary
        }
        if environment["JARVIS_STT_MODEL"] == nil, let sttModel = configuration.defaultSTTModel {
            environment["JARVIS_STT_MODEL"] = sttModel
        }
        bridgeLog("STT binary=\(environment["JARVIS_STT_BINARY"] ?? "nil") model=\(environment["JARVIS_STT_MODEL"] ?? "nil")")
        bridgeLog("args=\(process.arguments ?? [])")
        process.environment = environment
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        for (key, value) in payload {
            guard key != "command" else { continue }
            if let boolValue = value as? Bool {
                if boolValue {
                    process.arguments?.append("--\(key)")
                }
                continue
            }
            process.arguments?.append("--\(key)=\(String(describing: value))")
        }
        bridgeLog("launch command=\(payload["command"] as? String ?? "unknown") cwd=\(configuration.allianceRoot.path)")
        bridgeLog("python=\(pythonURL.path)")
        try process.run()
        process.waitUntilExit()

        let output = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        let stdoutText = String(decoding: output, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        let stderrText = String(decoding: stderr, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        if !stderrText.isEmpty {
            bridgeLog("stderr=\(stderrText)")
        }
        if process.terminationStatus != 0 {
            bridgeLog("terminationStatus=\(process.terminationStatus)")
            throw BridgeError.processFailed(stderrText.isEmpty ? "bridge process terminated" : stderrText)
        }
        guard !output.isEmpty else {
            bridgeLog("empty stdout from bridge process")
            throw BridgeError.emptyResponse
        }
        let envelope: CommandEnvelope
        do {
            envelope = try decodeEnvelope(from: output)
        } catch {
            bridgeLog("stdout=\(stdoutText)")
            bridgeLog("decode error=\(error.localizedDescription)")
            throw error
        }
        if envelope.kind == "error" {
            bridgeLog("envelope error=\(envelope.error ?? "unknown bridge error")")
            throw BridgeError.processFailed(envelope.error ?? "unknown bridge error")
        }
        if let health = envelope.healthResult, !health.failedChecks.isEmpty {
            bridgeLog("health failed_checks=\(health.failedChecks.joined(separator: ","))")
            if let modelDetail = health.details["model"] {
                bridgeLog("health model detail=\(modelDetail)")
            }
            if let vectorDetail = health.details["vector_db"] {
                bridgeLog("health vector_db detail=\(vectorDetail)")
            }
        }
        return envelope
    }

    private func decodeEnvelope(from output: Data) throws -> CommandEnvelope {
        let decoder = JSONDecoder()
        if let envelope = try? decoder.decode(CommandEnvelope.self, from: output) {
            return envelope
        }

        let outputText = String(decoding: output, as: UTF8.self)
        let lines = outputText
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        if let candidate = lines.last,
           let candidateData = candidate.data(using: .utf8),
           let envelope = try? decoder.decode(CommandEnvelope.self, from: candidateData) {
            return envelope
        }

        throw BridgeError.decodeFailed(outputText)
    }

    // MARK: - Streaming

    /// Ask a query with streaming token delivery via server mode.
    ///
    /// Launches the Python bridge in server mode (persistent stdin/stdout),
    /// sends the query with `"stream": true`, and yields tokens as they
    /// arrive. The final event contains the complete MenuResponse.
    func askStreaming(_ query: String) -> AsyncStream<StreamEvent> {
        AsyncStream { continuation in
            Task.detached { [configuration] in
                do {
                    let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
                    guard FileManager.default.fileExists(atPath: pythonURL.path) else {
                        continuation.yield(.error("Python not found"))
                        continuation.finish()
                        return
                    }

                    let process = Process()
                    let stdinPipe = Pipe()
                    let stdoutPipe = Pipe()
                    let stderrPipe = Pipe()

                    process.executableURL = pythonURL
                    process.currentDirectoryURL = configuration.allianceRoot
                    process.arguments = ["-u", "-m", "jarvis.cli.menu_bridge", "server"]

                    var environment = ProcessInfo.processInfo.environment
                    environment["PYTHONPATH"] = configuration.pythonPath
                    environment["HF_HUB_DISABLE_PROGRESS_BARS"] = environment["HF_HUB_DISABLE_PROGRESS_BARS"] ?? "1"
                    environment["TRANSFORMERS_VERBOSITY"] = environment["TRANSFORMERS_VERBOSITY"] ?? "error"
                    environment["TOKENIZERS_PARALLELISM"] = environment["TOKENIZERS_PARALLELISM"] ?? "false"
                    environment["HF_HUB_DISABLE_TELEMETRY"] = environment["HF_HUB_DISABLE_TELEMETRY"] ?? "1"
                    environment["TRUST_REMOTE_CODE"] = environment["TRUST_REMOTE_CODE"] ?? "1"
                    if let sttBinary = configuration.defaultSTTBinary {
                        environment["JARVIS_STT_BINARY"] = environment["JARVIS_STT_BINARY"] ?? sttBinary
                    }
                    if let sttModel = configuration.defaultSTTModel {
                        environment["JARVIS_STT_MODEL"] = environment["JARVIS_STT_MODEL"] ?? sttModel
                    }
                    process.environment = environment
                    process.standardInput = stdinPipe
                    process.standardOutput = stdoutPipe
                    process.standardError = stderrPipe

                    try process.run()
                    bridgeLog("Server mode launched for streaming query")

                    let decoder = JSONDecoder()
                    let fileHandle = stdoutPipe.fileHandleForReading

                    // Wait for "ready" signal
                    var ready = false
                    while !ready {
                        guard let lineData = fileHandle.availableData.split(separator: UInt8(ascii: "\n")).first else {
                            continue
                        }
                        if let envelope = try? decoder.decode(CommandEnvelope.self, from: Data(lineData)) {
                            if envelope.kind == "ready" { ready = true }
                        }
                    }

                    // Send streaming query
                    let payload = try JSONSerialization.data(
                        withJSONObject: ["command": "ask", "query": query, "stream": true]
                    )
                    stdinPipe.fileHandleForWriting.write(payload)
                    stdinPipe.fileHandleForWriting.write("\n".data(using: .utf8)!)

                    // Read streaming responses line by line
                    var buffer = Data()
                    var done = false
                    while !done {
                        let chunk = fileHandle.availableData
                        if chunk.isEmpty { break }
                        buffer.append(chunk)

                        // Process complete JSON lines
                        while let newlineIndex = buffer.firstIndex(of: UInt8(ascii: "\n")) {
                            let lineData = buffer[buffer.startIndex..<newlineIndex]
                            buffer = Data(buffer[buffer.index(after: newlineIndex)...])

                            guard !lineData.isEmpty,
                                  let envelope = try? decoder.decode(CommandEnvelope.self, from: Data(lineData))
                            else { continue }

                            switch envelope.kind {
                            case "stream_chunk":
                                if let token = envelope.token {
                                    continuation.yield(.token(token))
                                }
                            case "stream_done":
                                continuation.yield(.done(envelope.queryResult))
                                done = true
                            case "error":
                                continuation.yield(.error(envelope.error ?? "unknown error"))
                                done = true
                            default:
                                break
                            }
                        }
                    }

                    // Shutdown server
                    let shutdownPayload = try JSONSerialization.data(
                        withJSONObject: ["command": "shutdown"]
                    )
                    stdinPipe.fileHandleForWriting.write(shutdownPayload)
                    stdinPipe.fileHandleForWriting.write("\n".data(using: .utf8)!)
                    process.waitUntilExit()

                } catch {
                    continuation.yield(.error(error.localizedDescription))
                }
                continuation.finish()
            }
        }
    }

    private func send(_ query: String, command: String) async throws -> MenuResponse {
        let envelope = try runCommand([
            "command": command,
            "query": query,
        ])
        guard let response = envelope.queryResult else {
            throw BridgeError.decodeFailed("missing query_result")
        }
        return response
    }

    private func send(_ payload: [String: Any]) async throws -> CommandEnvelope {
        try runCommand(payload)
    }
}
