import SwiftUI

enum VoiceLoopPhase: String {
    case idle = "idle"
    case recording = "recording"
    case processing = "processing"
    case cooldown = "cooldown"
    case stopped = "stopped"
}

enum ExportFormat: String, CaseIterable, Identifiable {
    case txt = "txt"
    case md = "md"

    var id: String { rawValue }

    var suggestedFilename: String {
        switch self {
        case .txt:
            return "jarvis-draft.txt"
        case .md:
            return "jarvis-draft.md"
        }
    }
}

enum ExportLocation: String, CaseIterable, Identifiable {
    case jarvisExports = "jarvis_exports"
    case desktop = "desktop"
    case documents = "documents"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .jarvisExports:
            return ".jarvis/exports"
        case .desktop:
            return "Desktop"
        case .documents:
            return "Documents"
        }
    }
}

@MainActor
final class JarvisMenuBarViewModel: ObservableObject {
    @Published var query = ""
    @Published var response: MenuResponse?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var exportMessage: String?
    @Published var showApprovalPanel = false
    @Published var exportFilename = "jarvis-draft.txt"
    @Published var exportFormat: ExportFormat = .txt
    @Published var exportLocation: ExportLocation = .jarvisExports
    @Published var voiceLoopEnabled = false
    @Published var voiceLoopPhase: VoiceLoopPhase = .idle
    @Published var lastTranscript = ""
    @Published var health: HealthResponse?
    @Published var healthMessage = "health pending"
    @Published var consecutiveLoopErrors = 0

    private let bridge: JarvisBridge
    private var voiceLoopTask: Task<Void, Never>?
    private let successLoopDelay: Duration = .seconds(1.2)
    private let errorLoopDelay: Duration = .seconds(4)
    private let maxConsecutiveLoopErrors = 3

    init(bridge: JarvisBridge = JarvisBridge()) {
        self.bridge = bridge
        Task {
            await refreshHealth()
        }
    }

    func submit() {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return
        }

        isLoading = true
        errorMessage = nil
        voiceLoopPhase = .processing
        Task {
            do {
                let payload = try await bridge.ask(trimmed)
                response = payload
                exportMessage = nil
                lastTranscript = payload.query
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoading = false
            if !voiceLoopEnabled {
                voiceLoopPhase = .idle
            }
        }
    }

    func recordOnce() {
        isLoading = true
        errorMessage = nil
        voiceLoopPhase = .recording
        Task {
            do {
                voiceLoopPhase = .processing
                let payload = try await bridge.recordOnce()
                query = payload.query
                response = payload
                exportMessage = nil
                lastTranscript = payload.query
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoading = false
            if !voiceLoopEnabled {
                voiceLoopPhase = .idle
            }
        }
    }

    func toggleVoiceLoop() {
        if voiceLoopEnabled {
            stopVoiceLoop()
        } else {
            startVoiceLoop()
        }
    }

    func refreshHealth() async {
        do {
            let payload = try await bridge.health()
            health = payload
            healthMessage = payload.message
        } catch {
            healthMessage = error.localizedDescription
        }
    }

    private func startVoiceLoop() {
        guard voiceLoopTask == nil else {
            return
        }
        voiceLoopEnabled = true
        errorMessage = nil
        exportMessage = nil
        voiceLoopPhase = .recording
        consecutiveLoopErrors = 0

        voiceLoopTask = Task { [weak self] in
            guard let self else { return }
            while !Task.isCancelled {
                let delay = await self.runVoiceLoopIteration()
                if Task.isCancelled {
                    break
                }
                if let delay {
                    try? await Task.sleep(for: delay)
                }
            }
        }
    }

    private func stopVoiceLoop() {
        voiceLoopEnabled = false
        voiceLoopTask?.cancel()
        voiceLoopTask = nil
        isLoading = false
        voiceLoopPhase = .stopped
        consecutiveLoopErrors = 0
    }

    private func runVoiceLoopIteration() async -> Duration? {
        isLoading = true
        voiceLoopPhase = .recording

        do {
            voiceLoopPhase = .processing
            let payload = try await bridge.recordOnce()
            if Task.isCancelled {
                return nil
            }
            query = payload.query
            response = payload
            exportMessage = nil
            lastTranscript = payload.query
            errorMessage = nil
            consecutiveLoopErrors = 0
            isLoading = false
            voiceLoopPhase = .cooldown
            return successLoopDelay
        } catch {
            if Task.isCancelled {
                return nil
            }
            consecutiveLoopErrors += 1
            errorMessage = error.localizedDescription
            isLoading = false
            if consecutiveLoopErrors >= maxConsecutiveLoopErrors {
                errorMessage = "live loop stopped after \(consecutiveLoopErrors) consecutive errors: \(error.localizedDescription)"
                stopVoiceLoop()
                return nil
            }
            voiceLoopPhase = .cooldown
            return errorLoopDelay
        }
    }

    func requestExport() {
        guard response != nil else {
            return
        }
        if exportFilename.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            exportFilename = exportFormat.suggestedFilename
        }
        exportMessage = nil
        showApprovalPanel = true
    }

    func approveExport() {
        guard let response else {
            return
        }
        let destination = exportDestination()
        isLoading = true
        errorMessage = nil
        Task {
            do {
                let result = try await bridge.exportDraft(
                    content: response.response,
                    destination: destination.path,
                    approved: true
                )
                exportMessage = result.success
                    ? "Exported: \(result.destination)"
                    : result.errorMessage
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoading = false
            showApprovalPanel = false
        }
    }

    func declineExport() {
        showApprovalPanel = false
        exportMessage = "Export canceled"
    }

    func exportDestination() -> URL {
        let home = FileManager.default.homeDirectoryForCurrentUser
        let base: URL = switch exportLocation {
        case .jarvisExports:
            home.appendingPathComponent(".jarvis").appendingPathComponent("exports", isDirectory: true)
        case .desktop:
            home.appendingPathComponent("Desktop", isDirectory: true)
        case .documents:
            home.appendingPathComponent("Documents", isDirectory: true)
        }
        return base.appendingPathComponent(normalizedExportFilename())
    }

    func normalizedExportFilename() -> String {
        let trimmed = exportFilename.trimmingCharacters(in: .whitespacesAndNewlines)
        let baseName = trimmed.isEmpty ? exportFormat.suggestedFilename : trimmed
        let sanitized = baseName.replacingOccurrences(of: "/", with: "-")
        let ext = ".\(exportFormat.rawValue)"
        if sanitized.lowercased().hasSuffix(ext) {
            return sanitized
        }
        if let dot = sanitized.lastIndex(of: ".") {
            return String(sanitized[..<dot]) + ext
        }
        return sanitized + ext
    }

    var exportWillOverwrite: Bool {
        FileManager.default.fileExists(atPath: exportDestination().path)
    }

    var voiceLoopSummary: String {
        if voiceLoopEnabled {
            return "live voice loop active"
        }
        return switch voiceLoopPhase {
        case .idle:
            "voice loop idle"
        case .recording:
            "recording"
        case .processing:
            "processing"
        case .cooldown:
            consecutiveLoopErrors > 0
                ? "cooldown after error (\(consecutiveLoopErrors))"
                : "cooldown between recordings"
        case .stopped:
            "voice loop stopped"
        }
    }
}

struct StatusBadge: View {
    let title: String
    let active: Bool

    var body: some View {
        Text(title)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(active ? Color.orange.opacity(0.18) : Color.gray.opacity(0.12))
            .foregroundStyle(active ? Color.orange : Color.secondary)
            .clipShape(Capsule())
    }
}

struct HealthCheckRow: View {
    let name: String
    let ok: Bool
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Circle()
                .fill(ok ? Color.green : Color.orange)
                .frame(width: 8, height: 8)
                .padding(.top, 5)
            VStack(alignment: .leading, spacing: 2) {
                Text(name)
                    .font(.caption.weight(.semibold))
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }
}

struct JarvisMenuContentView: View {
    @ObservedObject var viewModel: JarvisMenuBarViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("JARVIS")
                .font(.title3.weight(.bold))

            HStack(spacing: 8) {
                TextField("질문을 입력하세요", text: $viewModel.query)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit {
                        viewModel.submit()
                    }
                Button {
                    viewModel.recordOnce()
                } label: {
                    Image(systemName: "mic.fill")
                }
                .help("Push-to-talk once")
                Button(viewModel.voiceLoopEnabled ? "Stop Loop" : "Live Loop") {
                    viewModel.toggleVoiceLoop()
                }
                Button("Ask") {
                    viewModel.submit()
                }
                .keyboardShortcut(.return, modifiers: [.command])
                Button("Health") {
                    Task {
                        await viewModel.refreshHealth()
                    }
                }
            }

            if viewModel.isLoading {
                ProgressView(viewModel.voiceLoopEnabled ? "음성 루프 처리 중..." : "검색 및 응답 생성 중...")
                    .controlSize(.small)
            }

            HStack(spacing: 6) {
                StatusBadge(title: viewModel.voiceLoopPhase.rawValue, active: true)
                StatusBadge(title: "live-loop", active: viewModel.voiceLoopEnabled)
            }

            Text(viewModel.voiceLoopSummary)
                .font(.caption)
                .foregroundStyle(.secondary)

            if let health = viewModel.health {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 6) {
                        StatusBadge(title: health.statusLevel, active: health.statusLevel == "healthy")
                        StatusBadge(title: health.bridgeMode, active: true)
                        StatusBadge(title: "\(health.chunkCount) chunks", active: true)
                    }
                    Text(viewModel.healthMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if !health.failedChecks.isEmpty {
                        Text("Issues: \(health.failedChecks.joined(separator: ", "))")
                            .font(.caption2)
                            .foregroundStyle(.orange)
                    }
                    if !health.knowledgeBasePath.isEmpty {
                        Text(health.knowledgeBasePath)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .textSelection(.enabled)
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(health.checks.keys.sorted(), id: \.self) { key in
                            HealthCheckRow(
                                name: key,
                                ok: health.checks[key] ?? false,
                                detail: health.details[key] ?? ""
                            )
                        }
                    }
                }
            } else {
                Text(viewModel.healthMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if let errorMessage = viewModel.errorMessage {
                Text(errorMessage)
                    .font(.callout)
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
            }

            if let exportMessage = viewModel.exportMessage {
                Text(exportMessage)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            if !viewModel.lastTranscript.isEmpty {
                Text("Last transcript: \(viewModel.lastTranscript)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }

            if let response = viewModel.response {
                if let status = response.status {
                    HStack(spacing: 6) {
                        StatusBadge(title: status.mode, active: true)
                        StatusBadge(title: "safe", active: status.safeMode)
                        StatusBadge(title: "degraded", active: status.degradedMode)
                        StatusBadge(title: "write-block", active: status.writeBlocked)
                    }
                }

                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(response.response)
                            .font(.body)
                            .textSelection(.enabled)

                        HStack(spacing: 8) {
                            Button("Export Draft") {
                                viewModel.requestExport()
                            }
                            if let status = response.status, status.generationBlocked || status.safeMode {
                                Text("검색 전용 상태")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }

                        if !response.citations.isEmpty {
                            Divider()
                            Text("Sources")
                                .font(.headline)
                            ForEach(response.citations) { citation in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("\(citation.label) \(citation.sourcePath)")
                                        .font(.caption.weight(.semibold))
                                    Text(citation.quote)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text("\(citation.sourceType) • \(citation.state)")
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }

                        Divider()
                        Text("Approval panel, PTT once, live voice loop가 메뉴바 UI에 연결되었습니다.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(width: 420, height: 320)
            } else {
                Text("텍스트 질의, PTT once, live voice loop, 승인형 초안 export를 연결한 메뉴바 셸입니다.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .frame(width: 420, alignment: .leading)
            }
        }
        .padding(16)
        .frame(width: 460)
        .sheet(isPresented: $viewModel.showApprovalPanel) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Export Approval")
                    .font(.title3.weight(.bold))
                Text("기술문서 기준 승인형 쓰기 정책을 따릅니다. 파일 쓰기는 명시 승인 후에만 진행됩니다.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                TextField("Filename", text: $viewModel.exportFilename)
                    .textFieldStyle(.roundedBorder)
                Picker("Format", selection: $viewModel.exportFormat) {
                    ForEach(ExportFormat.allCases) { format in
                        Text(format.rawValue.uppercased()).tag(format)
                    }
                }
                .pickerStyle(.segmented)
                Picker("Location", selection: $viewModel.exportLocation) {
                    ForEach(ExportLocation.allCases) { location in
                        Text(location.title).tag(location)
                    }
                }
                Text(viewModel.exportDestination().path)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                if viewModel.exportWillOverwrite {
                    Text("Existing file will be overwritten.")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
                HStack {
                    Button("Cancel") {
                        viewModel.declineExport()
                    }
                    Button("Approve Export") {
                        viewModel.approveExport()
                    }
                    .keyboardShortcut(.defaultAction)
                }
            }
            .padding(20)
            .frame(width: 420)
        }
    }
}

@main
struct JarvisMenuBarApp: App {
    @StateObject private var viewModel = JarvisMenuBarViewModel()

    var body: some Scene {
        MenuBarExtra("JARVIS", systemImage: "sparkles.rectangle.stack") {
            JarvisMenuContentView(viewModel: viewModel)
        }
        .menuBarExtraStyle(.window)
    }
}
