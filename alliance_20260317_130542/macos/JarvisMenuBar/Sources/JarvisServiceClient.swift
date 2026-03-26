import Foundation

private func serviceClientLog(_ message: String) {
    fputs("[JarvisServiceClient] \(message)\n", stderr)
}

private let defaultMenuBarAskModels = ["stub"]
private let menuBarAskTimeoutSeconds = 20.0

private func resolveMenuBarAskModels() -> [String] {
    let raw = ProcessInfo.processInfo.environment["JARVIS_MENU_BAR_MODEL_CHAIN"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if raw.isEmpty {
        return defaultMenuBarAskModels
    }
    let models = raw
        .split(separator: ",")
        .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        .filter { !$0.isEmpty }
    return models.isEmpty ? defaultMenuBarAskModels : models
}

protocol JarvisBackendClient: Sendable {
    func ask(_ query: String) async throws -> ServiceAskResponse
    func askStreaming(_ query: String) async -> AsyncStream<StreamEvent>
    func transcribeFile(audioPath: String) async throws -> TranscriptionResponse
    func navigationWindow(query: String) async throws -> MenuExplorationState
    func normalizeQuery(_ query: String) async throws -> String
    func synthesizeSpeech(text: String) async throws -> SpeechResponse
    func exportDraft(content: String, destination: String, approved: Bool) async throws -> ExportResponse
    func health() async throws -> HealthResponse
    func runtimeState() async -> JarvisRuntimeState
    func warmup() async
    func shutdown() async
    func updateKnowledgeBasePath(_ path: String?) async
}

struct JarvisRuntimeState: Sendable {
    let health: HealthResponse?
    let startupInProgress: Bool
    let startupMessage: String
    let errorMessage: String?
}

private struct ServiceRpcRequest: Encodable {
    let requestID: String
    let sessionID: String
    let requestType: String
    let payload: [String: CodableValue]

    enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case sessionID = "session_id"
        case requestType = "request_type"
        case payload
    }
}

enum CodableValue: Codable {
    case string(String)
    case bool(Bool)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(String.self) {
            self = .string(value)
            return
        }
        if let value = try? container.decode(Bool.self) {
            self = .bool(value)
            return
        }
        throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported CodableValue")
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value):
            try container.encode(value)
        case .bool(let value):
            try container.encode(value)
        }
    }
}

private struct ServiceRpcError: Decodable {
    let code: String
    let message: String
    let retryable: Bool
}

private struct ServiceRpcEnvelope: Decodable {
    let requestID: String
    let sessionID: String
    let ok: Bool
    let payload: [String: JSONValue]
    let error: ServiceRpcError?

    enum CodingKeys: String, CodingKey {
        case requestID = "request_id"
        case sessionID = "session_id"
        case ok
        case payload
        case error
    }
}

private struct ServiceRuntimePayload {
    let health: HealthResponse?
}

enum JSONValue: Decodable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Int.self) {
            self = .int(value)
        } else if let value = try? container.decode(Double.self) {
            self = .double(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    func toObject<T: Decodable>(_ type: T.Type, decoder: JSONDecoder = JSONDecoder()) throws -> T {
        let data = try JSONSerialization.data(withJSONObject: foundationObject(), options: [.fragmentsAllowed])
        return try decoder.decode(type, from: data)
    }

    private func foundationObject() -> Any {
        switch self {
        case .string(let value):
            return value
        case .int(let value):
            return value
        case .double(let value):
            return value
        case .bool(let value):
            return value
        case .object(let dict):
            return dict.mapValues { $0.foundationObject() }
        case .array(let values):
            return values.map { $0.foundationObject() }
        case .null:
            return NSNull()
        }
    }
}

private final class ServicePipeBuffer: @unchecked Sendable {
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

actor JarvisServiceClient: JarvisBackendClient {
    enum TransportMode {
        case stdio
        case unixSocket(String)
    }

    private let configuration: BridgeConfiguration
    private var knowledgeBaseOverridePath: String?
    private let sessionID = UUID().uuidString
    private let transportMode: TransportMode
    private let serviceManager: JarvisServiceManager?

    init(
        configuration: BridgeConfiguration = .default(),
        transportMode: TransportMode? = nil,
        knowledgeBaseOverridePath: String? = nil
    ) {
        self.configuration = configuration
        self.knowledgeBaseOverridePath = knowledgeBaseOverridePath
        let resolvedTransport = transportMode ?? Self.resolveTransportMode()
        self.transportMode = resolvedTransport
        switch resolvedTransport {
        case .stdio:
            self.serviceManager = nil
        case .unixSocket(let socketPath):
            self.serviceManager = JarvisServiceManager(
                configuration: configuration,
                socketPath: socketPath,
                knowledgeBaseOverridePath: knowledgeBaseOverridePath
            )
        }
    }

    func ask(_ query: String) async throws -> ServiceAskResponse {
        do {
            let envelope = try await runServiceRequest(
                requestType: "ask_text",
                payload: ["text": .string(query)]
            )
            return try decodeAskResponse(from: envelope)
        } catch {
            serviceClientLog("ask_text service path failed; falling back to direct menu_bridge ask: \(error.localizedDescription)")
            return try await runLegacyAsk(query: query)
        }
    }

    func askStreaming(_ query: String) async -> AsyncStream<StreamEvent> {
        AsyncStream { continuation in
            Task.detached {
                do {
                    let response = try await self.ask(query)
                    continuation.yield(.done(response))
                } catch {
                    continuation.yield(.error(error.localizedDescription))
                }
                continuation.finish()
            }
        }
    }

    func transcribeFile(audioPath: String) async throws -> TranscriptionResponse {
        let envelope = try await runServiceRequest(
            requestType: "transcribe_file",
            payload: ["audio_path": .string(audioPath)]
        )
        guard let transcriptValue = envelope.payload["transcript"] else {
            throw BridgeError.decodeFailed("missing payload.transcript")
        }
        let transcript = try transcriptValue.toObject(String.self)
        return TranscriptionResponse(transcript: transcript)
    }

    func navigationWindow(query: String) async throws -> MenuExplorationState {
        let envelope = try await runServiceRequest(
            requestType: "navigation_window",
            payload: ["text": .string(query)]
        )
        guard let navigationValue = envelope.payload["navigation"] else {
            throw BridgeError.decodeFailed("missing payload.navigation")
        }
        return try navigationValue.toObject(MenuExplorationState.self)
    }

    func normalizeQuery(_ query: String) async throws -> String {
        let envelope = try await runServiceRequest(
            requestType: "normalize_query",
            payload: ["text": .string(query)]
        )
        guard let normalizedValue = envelope.payload["normalized_query"] else {
            throw BridgeError.decodeFailed("missing payload.normalized_query")
        }
        return try normalizedValue.toObject(String.self)
    }

    func synthesizeSpeech(text: String) async throws -> SpeechResponse {
        let envelope = try await runServiceRequest(
            requestType: "synthesize_speech",
            payload: ["text": .string(text)]
        )
        guard let speechValue = envelope.payload["speech"] else {
            throw BridgeError.decodeFailed("missing payload.speech")
        }
        return try speechValue.toObject(SpeechResponse.self)
    }

    func exportDraft(content: String, destination: String, approved: Bool) async throws -> ExportResponse {
        let envelope = try await runServiceRequest(
            requestType: "export_draft",
            payload: [
                "content": .string(content),
                "destination": .string(destination),
                "approved": .bool(approved),
            ]
        )
        guard let exportValue = envelope.payload["export"] else {
            throw BridgeError.decodeFailed("missing payload.export")
        }
        return try exportValue.toObject(ExportResponse.self)
    }

    func health() async throws -> HealthResponse {
        let envelope = try await runServiceRequest(requestType: "health")
        guard let healthValue = envelope.payload["health"] else {
            throw BridgeError.decodeFailed("missing payload.health")
        }
        return try healthValue.toObject(HealthResponse.self)
    }

    func runtimeState() async -> JarvisRuntimeState {
        let startupInProgress = await serviceManager?.startupInProgress() ?? false
        let startupMessage = await serviceManager?.currentStartupProgress() ?? ""
        do {
            let envelope = try await runServiceRequest(requestType: "runtime_state")
            let payload = try decodeRuntimePayload(from: envelope)
            return JarvisRuntimeState(
                health: payload.health,
                startupInProgress: startupInProgress,
                startupMessage: startupMessage,
                errorMessage: nil
            )
        } catch {
            return JarvisRuntimeState(
                health: nil,
                startupInProgress: startupInProgress,
                startupMessage: startupMessage,
                errorMessage: error.localizedDescription
            )
        }
    }

    func warmup() async {
        if let serviceManager {
            try? await serviceManager.ensureRunning()
            return
        }
        _ = try? await runServiceRequest(requestType: "health")
    }

    func shutdown() async {
        await serviceManager?.shutdown()
    }

    func updateKnowledgeBasePath(_ path: String?) async {
        knowledgeBaseOverridePath = path
        await serviceManager?.updateKnowledgeBasePath(path)
    }

    private func runServiceRequest(
        requestType: String,
        payload: [String: CodableValue] = [:]
    ) async throws -> ServiceRpcEnvelope {
        if case .unixSocket(let socketPath) = transportMode {
            do {
                try await serviceManager?.ensureRunning()
                let request = ServiceRpcRequest(
                    requestID: UUID().uuidString,
                    sessionID: sessionID,
                    requestType: requestType,
                    payload: payload
                )
                let requestData = try JSONEncoder().encode(request)
                let responseData = try JarvisSocketTransport(socketPath: socketPath).send(requestData: requestData)
                return try decodeServiceResponse(
                    responseData,
                    stderr: Data(),
                    requestType: requestType,
                )
            } catch {
                serviceClientLog("UDS request failed for \(requestType); falling back to stdio: \(error.localizedDescription)")
                return try await runStdioServiceRequest(
                    requestType: requestType,
                    payload: payload
                )
            }
        }

        return try await runStdioServiceRequest(
            requestType: requestType,
            payload: payload
        )
    }

    private func decodeRuntimePayload(from envelope: ServiceRpcEnvelope) throws -> ServiceRuntimePayload {
        let health: HealthResponse?
        if let healthValue = envelope.payload["health"] {
            health = try healthValue.toObject(HealthResponse.self)
        } else {
            health = nil
        }
        return ServiceRuntimePayload(health: health)
    }

    private func decodeAskResponse(from envelope: ServiceRpcEnvelope) throws -> ServiceAskResponse {
        guard let responseValue = envelope.payload["response"] else {
            throw BridgeError.decodeFailed("missing payload.response")
        }
        let response = try responseValue.toObject(MenuResponse.self)
        let answer = try envelope.payload["answer"]?.toObject(ServiceAnswerPayload.self)
        let guide = try envelope.payload["guide"]?.toObject(ServiceGuidePayload.self)
        return ServiceAskResponse(response: response, answer: answer, guide: guide)
    }

    private func runLegacyAsk(query: String) async throws -> ServiceAskResponse {
        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        var lastError: Error?
        for model in resolveMenuBarAskModels() {
            serviceClientLog("legacy ask launch python=\(pythonURL.path) model=\(model) cwd=\(configuration.allianceRoot.path)")
            let process = Process()
            let stdoutPipe = Pipe()
            let stderrPipe = Pipe()
            configureShellPythonProcess(
                process,
                configuration: configuration,
                environment: serviceEnvironment(),
                arguments: ["-u", "-m", "jarvis.cli.menu_bridge", "ask", "--query", query, "--model", model]
            )
            process.standardOutput = stdoutPipe
            process.standardError = stderrPipe

            do {
                try process.run()
            } catch {
                lastError = error
                continue
            }

            let stdoutTask = Task.detached(priority: .userInitiated) {
                stdoutPipe.fileHandleForReading.readDataToEndOfFile()
            }
            let stderrTask = Task.detached(priority: .userInitiated) {
                stderrPipe.fileHandleForReading.readDataToEndOfFile()
            }

            try await waitForProcessExit(
                process,
                timeoutSeconds: menuBarAskTimeoutSeconds,
                timeoutMessage: "legacy ask timed out after \(Int(menuBarAskTimeoutSeconds))s"
            )

            let output = await stdoutTask.value
            let stderr = await stderrTask.value
            guard !output.isEmpty else {
                let stderrText = String(decoding: stderr, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
                lastError = stderrText.isEmpty
                    ? BridgeError.processFailed("legacy ask failed (status=\(process.terminationStatus), empty stdout)")
                    : BridgeError.processFailed("legacy ask failed (status=\(process.terminationStatus)): \(stderrText)")
                continue
            }

            let outputText = String(decoding: output, as: UTF8.self)
            let lines = outputText
                .split(whereSeparator: \.isNewline)
                .map(String.init)
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }

            let decoder = JSONDecoder()
            for line in lines.reversed() {
                if let data = line.data(using: .utf8),
                   let envelope = try? decoder.decode(CommandEnvelope.self, from: data),
                   let response = envelope.queryResult {
                    let guide = response.guideDirective.map { directive in
                        ServiceGuidePayload(
                            loopStage: directive.loopStage,
                            clarificationPrompt: directive.clarificationPrompt,
                            suggestedReplies: directive.suggestedReplies,
                            clarificationOptions: directive.suggestedReplies,
                            missingSlots: directive.missingSlots,
                            clarificationReasons: directive.missingSlots,
                            intent: directive.intent,
                            skill: directive.skill,
                            shouldHold: directive.shouldHold,
                            hasClarification: !directive.clarificationPrompt.isEmpty || !directive.missingSlots.isEmpty,
                            interactionMode: response.renderHints?.interactionMode ?? "",
                            explorationMode: response.exploration?.mode ?? "",
                            targetFile: response.exploration?.targetFile ?? "",
                            targetDocument: response.exploration?.targetDocument ?? ""
                        )
                    }
                    let answerText = guide?.clarificationPrompt.isEmpty == false
                        ? (guide?.clarificationPrompt ?? response.response)
                        : (response.spokenResponse ?? response.response)
                    let answer = ServiceAnswerPayload(
                        text: answerText,
                        spokenText: response.spokenResponse ?? answerText,
                        hasEvidence: response.hasEvidence,
                        citationCount: response.citations.count,
                        fullResponsePath: response.fullResponsePath
                    )
                    return ServiceAskResponse(response: response, answer: answer, guide: guide)
                }
            }

            let stderrText = String(decoding: stderr, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            lastError = stderrText.isEmpty
                ? BridgeError.decodeFailed(outputText)
                : BridgeError.decodeFailed(outputText + "\n" + stderrText)
        }

        throw lastError ?? BridgeError.processFailed("legacy ask failed: no models configured")
    }

    private func runStdioServiceRequest(
        requestType: String,
        payload: [String: CodableValue]
    ) async throws -> ServiceRpcEnvelope {
        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        let process = Process()
        let stdinPipe = Pipe()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()

        configureShellPythonProcess(
            process,
            configuration: configuration,
            environment: serviceEnvironment(),
            arguments: ["-u", "-m", "jarvis.service.stdio_server"]
        )
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe

        let request = ServiceRpcRequest(
            requestID: UUID().uuidString,
            sessionID: sessionID,
            requestType: requestType,
            payload: payload
        )
        let requestData = try JSONEncoder().encode(request)

        try process.run()
        stdinPipe.fileHandleForWriting.write(requestData)
        stdinPipe.fileHandleForWriting.write("\n".data(using: .utf8)!)
        try? stdinPipe.fileHandleForWriting.close()

        let stdoutTask = Task.detached(priority: .userInitiated) {
            stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        }
        let stderrTask = Task.detached(priority: .userInitiated) {
            stderrPipe.fileHandleForReading.readDataToEndOfFile()
        }

        try await waitForProcessExit(
            process,
            timeoutSeconds: menuBarAskTimeoutSeconds,
            timeoutMessage: "service \(requestType) timed out after \(Int(menuBarAskTimeoutSeconds))s"
        )

        let output = await stdoutTask.value
        let stderr = await stderrTask.value
        guard !output.isEmpty else {
            let stderrText = String(decoding: stderr, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            if !stderrText.isEmpty {
                throw BridgeError.processFailed("service \(requestType) failed (status=\(process.terminationStatus)): \(stderrText)")
            }
            throw BridgeError.processFailed("service \(requestType) failed (status=\(process.terminationStatus), empty stdout)")
        }

        return try decodeServiceResponse(output, stderr: stderr, requestType: requestType)
    }

    private func decodeServiceResponse(
        _ output: Data,
        stderr: Data,
        requestType: String
    ) throws -> ServiceRpcEnvelope {
        let outputText = String(decoding: output, as: UTF8.self)
        let lines = outputText
            .split(whereSeparator: \.isNewline)
            .map(String.init)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }

        let decoder = JSONDecoder()
        for line in lines.reversed() {
            if let data = line.data(using: .utf8),
               let envelope = try? decoder.decode(ServiceRpcEnvelope.self, from: data) {
                if envelope.ok {
                    return envelope
                }
                if let error = envelope.error {
                    throw BridgeError.processFailed("service \(requestType) failed [\(error.code)]: \(error.message)")
                }
                throw BridgeError.processFailed("service \(requestType) failed with unknown error")
            }
        }

        let stderrText = String(decoding: stderr, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
        if !stderrText.isEmpty {
            throw BridgeError.decodeFailed(outputText + "\n" + stderrText)
        }
        throw BridgeError.decodeFailed(outputText)
    }

    private func serviceEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        env["PYTHONPATH"] = configuration.pythonPath
        env["HF_HUB_DISABLE_PROGRESS_BARS"] = env["HF_HUB_DISABLE_PROGRESS_BARS"] ?? "1"
        env["TRANSFORMERS_VERBOSITY"] = env["TRANSFORMERS_VERBOSITY"] ?? "error"
        env["TOKENIZERS_PARALLELISM"] = env["TOKENIZERS_PARALLELISM"] ?? "false"
        env["HF_HUB_DISABLE_TELEMETRY"] = env["HF_HUB_DISABLE_TELEMETRY"] ?? "1"
        env["TRUST_REMOTE_CODE"] = env["TRUST_REMOTE_CODE"] ?? "1"
        if let knowledgeBaseOverridePath,
           !knowledgeBaseOverridePath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            env["JARVIS_KNOWLEDGE_BASE"] = knowledgeBaseOverridePath
        } else if let configured = env["JARVIS_KNOWLEDGE_BASE"],
                  !configured.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            env["JARVIS_KNOWLEDGE_BASE"] = configured
        } else {
            env["JARVIS_KNOWLEDGE_BASE"] = configuration.defaultKnowledgeBasePath
        }
        if let sttBinary = configuration.defaultSTTBinary {
            env["JARVIS_STT_BINARY"] = env["JARVIS_STT_BINARY"] ?? sttBinary
        }
        if let sttModel = configuration.defaultSTTModel {
            env["JARVIS_STT_MODEL"] = env["JARVIS_STT_MODEL"] ?? sttModel
        }
        return env
    }

    private static func resolveTransportMode() -> TransportMode {
        let environment = ProcessInfo.processInfo.environment
        let transport = environment["JARVIS_SERVICE_TRANSPORT"]?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if transport == "stdio" {
            return .stdio
        }
        let socketPath = environment["JARVIS_SERVICE_SOCKET"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let socketPath, !socketPath.isEmpty {
            return .unixSocket(socketPath)
        }
        return .unixSocket(NSTemporaryDirectory().appending("jarvis_service.sock"))
    }
}
