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
        try process.run()
        process.waitUntilExit()

        let output = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        if process.terminationStatus != 0 {
            let stderrText = String(decoding: stderr, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            throw BridgeError.processFailed(stderrText.isEmpty ? "bridge process terminated" : stderrText)
        }
        guard !output.isEmpty else {
            throw BridgeError.emptyResponse
        }
        let envelope = try JSONDecoder().decode(CommandEnvelope.self, from: output)
        if envelope.kind == "error" {
            throw BridgeError.processFailed(envelope.error ?? "unknown bridge error")
        }
        return envelope
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
