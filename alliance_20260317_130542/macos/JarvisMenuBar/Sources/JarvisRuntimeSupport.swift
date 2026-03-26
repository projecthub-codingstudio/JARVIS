import Foundation

private func shellQuote(_ value: String) -> String {
    "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
}

struct BridgeConfiguration {
    let allianceRoot: URL
    let pythonExecutable: String

    var pythonPath: String {
        allianceRoot.appendingPathComponent("src").path
    }

    var defaultKnowledgeBasePath: String {
        let fileManager = FileManager.default
        let candidates = [
            allianceRoot.deletingLastPathComponent().appendingPathComponent("knowledge_base", isDirectory: true).path,
            allianceRoot.appendingPathComponent("knowledge_base", isDirectory: true).path,
        ]
        return candidates.first(where: { fileManager.fileExists(atPath: $0) }) ?? candidates[0]
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

func configuredBridgeEnvironment(
    from base: [String: String],
    configuration: BridgeConfiguration,
    knowledgeBaseOverridePath: String? = nil
) -> [String: String] {
    var env = base
    env["PYTHONPATH"] = configuration.pythonPath
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = env["HF_HUB_DISABLE_PROGRESS_BARS"] ?? "1"
    env["TRANSFORMERS_VERBOSITY"] = env["TRANSFORMERS_VERBOSITY"] ?? "error"
    env["TOKENIZERS_PARALLELISM"] = env["TOKENIZERS_PARALLELISM"] ?? "false"
    env["HF_HUB_DISABLE_TELEMETRY"] = env["HF_HUB_DISABLE_TELEMETRY"] ?? "1"
    env["TRUST_REMOTE_CODE"] = env["TRUST_REMOTE_CODE"] ?? "1"
    if let knowledgeBaseOverridePath {
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

func configureShellPythonProcess(
    _ process: Process,
    configuration: BridgeConfiguration,
    environment: [String: String],
    arguments: [String]
) {
    let shellURL = URL(fileURLWithPath: "/bin/zsh")
    let exportSegments = environment.keys.sorted().compactMap { key -> String? in
        guard let value = environment[key] else { return nil }
        return "export \(key)=\(shellQuote(value))"
    }
    let commandSegments = [
        "cd \(shellQuote(configuration.allianceRoot.path))",
        exportSegments.joined(separator: "; "),
        "exec " + ([configuration.pythonExecutable] + arguments).map(shellQuote).joined(separator: " "),
    ]
    process.executableURL = shellURL
    process.currentDirectoryURL = configuration.allianceRoot
    process.arguments = ["-lc", commandSegments.filter { !$0.isEmpty }.joined(separator: "; ")]
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
