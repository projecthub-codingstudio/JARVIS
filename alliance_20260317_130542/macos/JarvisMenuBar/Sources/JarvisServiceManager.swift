import Foundation

actor JarvisServiceManager {
    private let configuration: BridgeConfiguration
    private let socketPath: String
    private var knowledgeBaseOverridePath: String?
    private var process: Process?
    private var startupProgressMessage = ""
    private var startingUp = false

    init(
        configuration: BridgeConfiguration = .default(),
        socketPath: String,
        knowledgeBaseOverridePath: String? = nil
    ) {
        self.configuration = configuration
        self.socketPath = socketPath
        self.knowledgeBaseOverridePath = knowledgeBaseOverridePath
    }

    func ensureRunning() async throws {
        if let process, process.isRunning, FileManager.default.fileExists(atPath: socketPath) {
            return
        }

        startingUp = true
        startupProgressMessage = "JARVIS service를 시작하는 중입니다."
        defer {
            startingUp = false
            startupProgressMessage = ""
        }

        if let process, process.isRunning {
            process.terminate()
        }
        process = nil

        let pythonURL = URL(fileURLWithPath: configuration.pythonExecutable)
        guard FileManager.default.fileExists(atPath: pythonURL.path) else {
            throw BridgeError.missingPython(pythonURL.path)
        }

        try? FileManager.default.removeItem(atPath: socketPath)

        let newProcess = Process()
        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        newProcess.executableURL = pythonURL
        newProcess.currentDirectoryURL = configuration.allianceRoot
        newProcess.arguments = ["-u", "-m", "jarvis.service", "--transport=socket"]
        newProcess.environment = managerEnvironment()
        newProcess.standardOutput = stdoutPipe
        newProcess.standardError = stderrPipe

        fputs(
            "[JarvisServiceManager] launching service python=\(pythonURL.path) cwd=\(configuration.allianceRoot.path) socket=\(socketPath)\n",
            stderr
        )

        try newProcess.run()
        process = newProcess

        let start = Date()
        while Date().timeIntervalSince(start) < 5 {
            if FileManager.default.fileExists(atPath: socketPath) {
                return
            }
            if !newProcess.isRunning {
                let stderr = String(decoding: stderrPipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                let message = stderr.trimmingCharacters(in: .whitespacesAndNewlines)
                if !message.isEmpty {
                    throw BridgeError.processFailed("service socket startup failed: \(message)")
                }
                throw BridgeError.processFailed("service socket startup failed with status=\(newProcess.terminationStatus)")
            }
            try await Task.sleep(nanoseconds: 100_000_000)
        }

        throw BridgeError.processFailed("service socket did not become ready: \(socketPath)")
    }

    func shutdown() {
        process?.terminate()
        process = nil
        startupProgressMessage = ""
        startingUp = false
    }

    func updateKnowledgeBasePath(_ path: String?) {
        knowledgeBaseOverridePath = path
        if let process, process.isRunning {
            process.terminate()
            self.process = nil
        }
        try? FileManager.default.removeItem(atPath: socketPath)
    }

    func startupInProgress() -> Bool {
        startingUp
    }

    func currentStartupProgress() -> String {
        startupProgressMessage
    }

    private func managerEnvironment() -> [String: String] {
        var env = configuredBridgeEnvironment(
            from: ProcessInfo.processInfo.environment,
            configuration: configuration,
            knowledgeBaseOverridePath: knowledgeBaseOverridePath
        )
        env["JARVIS_SERVICE_SOCKET"] = socketPath
        return env
    }
}
