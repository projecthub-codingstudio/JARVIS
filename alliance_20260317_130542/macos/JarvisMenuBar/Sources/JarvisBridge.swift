import Foundation

struct BridgeConfiguration {
    let allianceRoot: URL
    let pythonExecutable: String

    var pythonPath: String {
        allianceRoot.appendingPathComponent("src").path
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
    private var process: Process?
    private var stdinPipe: Pipe?
    private var stdoutHandle: FileHandle?
    private var stderrHandle: FileHandle?
    private var stdoutBuffer = Data()

    init(configuration: BridgeConfiguration = .default()) {
        self.configuration = configuration
    }

    func ask(_ query: String) async throws -> MenuResponse {
        try await send(query, command: "ask")
    }

    func recordOnce() async throws -> MenuResponse {
        let envelope = try await send(["command": "record-once"])
        guard let response = envelope.queryResult else {
            throw BridgeError.decodeFailed("missing query_result")
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

    deinit {
        process?.terminate()
    }

    private func ensureServerStarted() throws {
        if let process, process.isRunning {
            return
        }

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
            "server",
        ]

        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = configuration.pythonPath
        process.environment = environment
        process.standardInput = stdinPipe
        process.standardOutput = stdoutPipe
        process.standardError = stderrPipe
        try process.run()

        self.process = process
        self.stdinPipe = stdinPipe
        self.stdoutHandle = stdoutPipe.fileHandleForReading
        self.stderrHandle = stderrPipe.fileHandleForReading
        self.stdoutBuffer.removeAll(keepingCapacity: true)

        let ready = try readEnvelope()
        guard ready.kind == "ready" else {
            throw BridgeError.decodeFailed("expected ready envelope")
        }
    }

    private func send(_ payload: [String: Any]) async throws -> CommandEnvelope {
        try ensureServerStarted()
        guard let stdinPipe, let stdinData = try? JSONSerialization.data(withJSONObject: payload) else {
            throw BridgeError.processFailed("stdin not available")
        }
        let stdinHandle = stdinPipe.fileHandleForWriting

        stdinHandle.write(stdinData)
        stdinHandle.write(Data([0x0a]))

        let envelope = try readEnvelope()
        if envelope.kind == "error" {
            throw BridgeError.processFailed(envelope.error ?? "unknown bridge error")
        }
        return envelope
    }

    private func readEnvelope() throws -> CommandEnvelope {
        guard let stdoutHandle else {
            throw BridgeError.processFailed("stdout handle missing")
        }

        while true {
            if let newlineRange = stdoutBuffer.firstRange(of: Data([0x0a])) {
                let lineData = stdoutBuffer.subdata(in: 0..<newlineRange.lowerBound)
                stdoutBuffer.removeSubrange(0...newlineRange.lowerBound)
                if lineData.isEmpty {
                    continue
                }
                let response = try JSONDecoder().decode(CommandEnvelope.self, from: lineData)
                return response
            }

            let chunk = try stdoutHandle.read(upToCount: 4096) ?? Data()
            if chunk.isEmpty {
                let stderrText = readStderrSnapshot()
                throw BridgeError.processFailed(stderrText.isEmpty ? "bridge process terminated" : stderrText)
            }
            stdoutBuffer.append(chunk)
        }
    }

    private func readStderrSnapshot() -> String {
        guard let stderrHandle else {
            return ""
        }
        let data = (try? stderrHandle.readToEnd()) ?? Data()
        return String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func send(_ query: String, command: String) async throws -> MenuResponse {
        let envelope = try await send([
            "command": command,
            "query": query,
        ])
        guard let response = envelope.queryResult else {
            throw BridgeError.decodeFailed("missing query_result")
        }
        return response
    }
}
