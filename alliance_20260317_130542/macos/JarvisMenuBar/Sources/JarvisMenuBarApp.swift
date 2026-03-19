import AppKit
import AVFoundation
import SwiftUI

private func appLog(_ message: String) {
    fputs("[JarvisMenuBar] \(message)\n", stderr)
}

enum VoiceLoopPhase: String {
    case idle = "idle"
    case recording = "recording"
    case transcribing = "transcribing"
    case answering = "answering"
    case cooldown = "cooldown"
    case stopped = "stopped"
    case error = "error"
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

enum MenuPanel: String, CaseIterable, Identifiable {
    case assistant = "assistant"
    case health = "health"
    case audio = "audio"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .assistant:
            return "Assistant"
        case .health:
            return "Health"
        case .audio:
            return "Audio"
        }
    }
}

struct AudioInputDevice: Identifiable, Equatable {
    let id: String
    let name: String
}

final class AudioBypassMonitor {
    private let session = AVCaptureSession()
    private let previewOutput = AVCaptureAudioPreviewOutput()
    private var currentInput: AVCaptureDeviceInput?
    private let queue = DispatchQueue(label: "jarvis.audio.bypass")

    func start(deviceID: String?) throws {
        var thrownError: Error?
        queue.sync {
            do {
                try configureSession(deviceID: deviceID)
                if !session.isRunning {
                    session.startRunning()
                }
            } catch {
                thrownError = error
            }
        }
        if let thrownError {
            throw thrownError
        }
    }

    func stop() {
        queue.sync {
            if session.isRunning {
                session.stopRunning()
            }
        }
    }

    private func configureSession(deviceID: String?) throws {
        session.beginConfiguration()
        defer { session.commitConfiguration() }

        if let currentInput {
            session.removeInput(currentInput)
            self.currentInput = nil
        }
        for output in session.outputs where output == previewOutput {
            session.removeOutput(output)
        }

        let availableDevices = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.microphone, .external],
            mediaType: .audio,
            position: .unspecified
        ).devices

        let device = if let deviceID, !deviceID.isEmpty {
            availableDevices.first(where: { $0.uniqueID == deviceID })
        } else {
            AVCaptureDevice.default(for: .audio)
        }

        guard let device else {
            throw NSError(domain: "JarvisMenuBar", code: 1, userInfo: [
                NSLocalizedDescriptionKey: "바이패스용 입력 장치를 찾을 수 없습니다."
            ])
        }

        let input = try AVCaptureDeviceInput(device: device)
        if session.canAddInput(input) {
            session.addInput(input)
            currentInput = input
        } else {
            throw NSError(domain: "JarvisMenuBar", code: 2, userInfo: [
                NSLocalizedDescriptionKey: "바이패스 입력을 추가할 수 없습니다."
            ])
        }

        previewOutput.volume = 1.0
        if session.canAddOutput(previewOutput) {
            session.addOutput(previewOutput)
        } else {
            throw NSError(domain: "JarvisMenuBar", code: 3, userInfo: [
                NSLocalizedDescriptionKey: "바이패스 출력을 추가할 수 없습니다."
            ])
        }
    }
}

@MainActor
final class JarvisMenuBarViewModel: ObservableObject {
    private static let selectedInputDeviceDefaultsKey = "selectedInputDeviceID"
    private static let diagnosticsDirectory = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".jarvis", isDirectory: true)
        .appendingPathComponent("diagnostics", isDirectory: true)

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
    @Published var selectedPanel: MenuPanel = .assistant
    @Published var availableInputDevices: [AudioInputDevice] = []
    @Published var defaultInputDeviceID = ""
    @Published var bypassEnabled = false
    @Published var bypassStatusMessage = "바이패스 꺼짐"
    @Published var recordingElapsedSeconds = 0.0
    @Published var selectedInputDeviceID = "" {
        didSet {
            UserDefaults.standard.set(selectedInputDeviceID, forKey: Self.selectedInputDeviceDefaultsKey)
            if selectedInputDeviceID.isEmpty {
                inputDeviceStatusMessage = "시스템 기본 입력 장치를 사용합니다."
            } else if let selectedInputDeviceName {
                inputDeviceStatusMessage = "선택된 입력 장치: \(selectedInputDeviceName)"
            }
            if bypassEnabled {
                restartBypass()
            }
        }
    }
    @Published var inputDeviceStatusMessage = "시스템 기본 입력 장치를 사용합니다."

    private let bridge: JarvisBridge
    private let bypassMonitor = AudioBypassMonitor()
    private var voiceLoopTask: Task<Void, Never>?
    private let successLoopDelay: Duration = .seconds(1.2)
    private let errorLoopDelay: Duration = .seconds(4)
    private let maxConsecutiveLoopErrors = 3
    private let pttDurationSeconds: Double
    private var phaseTransitionTask: Task<Void, Never>?

    init(bridge: JarvisBridge = JarvisBridge()) {
        self.bridge = bridge
        self.pttDurationSeconds = Double(ProcessInfo.processInfo.environment["JARVIS_PTT_SECONDS"] ?? "8") ?? 8
        self.selectedInputDeviceID = UserDefaults.standard.string(forKey: Self.selectedInputDeviceDefaultsKey) ?? ""
        refreshAudioInputDevices()
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
        transitionToAnswering()
        Task {
            do {
                let payload = try await bridge.ask(trimmed)
                transitionToAnswering()
                response = payload
                exportMessage = nil
                lastTranscript = payload.query
            } catch {
                appLog("ask failed: \(error.localizedDescription)")
                errorMessage = error.localizedDescription
                cancelPhaseTransition()
                voiceLoopPhase = .error
            }
            isLoading = false
            if !voiceLoopEnabled {
                cancelPhaseTransition()
                voiceLoopPhase = .idle
            }
        }
    }

    func recordOnce() {
        isLoading = true
        errorMessage = nil
        beginRecordingPhase()
        Task {
            do {
                let transcript = try await bridge.transcribeOnce(device: selectedInputDeviceBridgeValue)
                cancelPhaseTransition()
                lastTranscript = transcript.transcript
                query = transcript.transcript
                transitionToAnswering()
                let payload = try await bridge.ask(transcript.transcript)
                voiceLoopPhase = .answering
                response = payload
                exportMessage = nil
            } catch {
                appLog("recordOnce failed: \(error.localizedDescription)")
                errorMessage = error.localizedDescription
                cancelPhaseTransition()
                voiceLoopPhase = .error
            }
            isLoading = false
            if !voiceLoopEnabled {
                cancelPhaseTransition()
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
            if !payload.failedChecks.isEmpty {
                appLog("health warning: \(payload.failedChecks.joined(separator: ","))")
                if let modelDetail = payload.details["model"] {
                    appLog("health model detail: \(modelDetail)")
                }
                if let vectorDetail = payload.details["vector_db"] {
                    appLog("health vector_db detail: \(vectorDetail)")
                }
            }
        } catch {
            appLog("health failed: \(error.localizedDescription)")
            healthMessage = error.localizedDescription
        }
    }

    func refreshAudioInputDevices() {
        let previousSelection = selectedInputDeviceID
        let defaultDeviceID = AVCaptureDevice.default(for: .audio)?.uniqueID ?? ""
        defaultInputDeviceID = defaultDeviceID
        let devices = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.microphone, .external],
            mediaType: .audio,
            position: .unspecified
        ).devices
            .map { AudioInputDevice(id: $0.uniqueID, name: $0.localizedName) }
            .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
        availableInputDevices = devices

        if selectedInputDeviceID.isEmpty {
            inputDeviceStatusMessage = "시스템 기본 입력 장치를 사용합니다."
            return
        }
        if !devices.contains(where: { $0.id == selectedInputDeviceID }) {
            selectedInputDeviceID = ""
            inputDeviceStatusMessage = previousSelection.isEmpty
                ? "시스템 기본 입력 장치를 사용합니다."
                : "선택한 마이크를 찾을 수 없어 시스템 기본 입력으로 전환했습니다."
        }
    }

    func toggleBypass() {
        if bypassEnabled {
            stopBypass()
        } else {
            startBypass()
        }
    }

    func copyErrorMessage() {
        let payload = diagnosticMessage()
        guard !payload.isEmpty else {
            return
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(payload, forType: .string)
        exportMessage = "진단 메시지를 클립보드에 복사했습니다."
    }

    func saveErrorMessage() {
        let payload = diagnosticMessage()
        guard !payload.isEmpty else {
            return
        }
        saveDiagnostic(payload, filename: "jarvis-error.txt")
    }

    func copyHealthSummary() {
        guard let health else {
            return
        }
        let lines = [
            "message: \(health.message)",
            "failed_checks: \(health.failedChecks.joined(separator: ", "))",
        ] + health.checks.keys.sorted().map { key in
            let ok = health.checks[key] ?? false
            let detail = health.details[key] ?? ""
            return "\(key): \(ok ? "OK" : "FAIL") - \(detail)"
        }
        let payload = lines.joined(separator: "\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(payload, forType: .string)
        exportMessage = "health 상태를 클립보드에 복사했습니다."
    }

    func saveHealthSummary() {
        guard let health else {
            return
        }
        let lines = [
            "message: \(health.message)",
            "failed_checks: \(health.failedChecks.joined(separator: ", "))",
        ] + health.checks.keys.sorted().map { key in
            let ok = health.checks[key] ?? false
            let detail = health.details[key] ?? ""
            return "\(key): \(ok ? "OK" : "FAIL") - \(detail)"
        }
        saveDiagnostic(lines.joined(separator: "\n"), filename: "jarvis-health.txt")
    }

    func diagnosticMessage() -> String {
        if let errorMessage, !errorMessage.isEmpty {
            return errorMessage
        }
        guard let health else {
            return ""
        }
        let failed = health.failedChecks
        if failed.isEmpty {
            return health.message
        }
        let lines = ["message: \(health.message)"] + failed.map { key in
            let detail = health.details[key] ?? ""
            return "\(key): \(detail)"
        }
        return lines.joined(separator: "\n")
    }

    private func saveDiagnostic(_ payload: String, filename: String) {
        do {
            try Self.diagnosticsDirectory.createDirectoryIfNeeded()
            let fileURL = Self.diagnosticsDirectory.appendingPathComponent(filename)
            try payload.write(to: fileURL, atomically: true, encoding: .utf8)
            exportMessage = "저장됨: \(fileURL.path)"
        } catch {
            errorMessage = "진단 파일 저장 실패: \(error.localizedDescription)"
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
        cancelPhaseTransition()
        isLoading = false
        voiceLoopPhase = .stopped
        consecutiveLoopErrors = 0
    }

    private func runVoiceLoopIteration() async -> Duration? {
        isLoading = true
        beginRecordingPhase()

        do {
            let transcript = try await bridge.transcribeOnce(device: selectedInputDeviceBridgeValue)
            if Task.isCancelled {
                return nil
            }
            cancelPhaseTransition()
            lastTranscript = transcript.transcript
            query = transcript.transcript
            transitionToAnswering()
            let payload = try await bridge.ask(transcript.transcript)
            if Task.isCancelled {
                return nil
            }
            voiceLoopPhase = .answering
            response = payload
            exportMessage = nil
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
            appLog("voice loop iteration failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
            isLoading = false
            cancelPhaseTransition()
            voiceLoopPhase = .error
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
                appLog("export failed: \(error.localizedDescription)")
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
        case .transcribing:
            "transcribing"
        case .answering:
            "answering"
        case .cooldown:
            consecutiveLoopErrors > 0
                ? "cooldown after error (\(consecutiveLoopErrors))"
                : "cooldown between recordings"
        case .stopped:
            "voice loop stopped"
        case .error:
            "last action ended with an error"
        }
    }

    var selectedInputDeviceName: String? {
        availableInputDevices.first(where: { $0.id == selectedInputDeviceID })?.name
    }

    var selectedInputDeviceBridgeValue: String? {
        guard !selectedInputDeviceID.isEmpty else { return nil }
        if selectedInputDeviceID == defaultInputDeviceID {
            return nil
        }
        return selectedInputDeviceName
    }

    var phaseStatusText: String {
        switch voiceLoopPhase {
        case .idle:
            return "대기 중"
        case .recording:
            return "녹음 중 \(recordingElapsedLabel) / \(maxRecordingLabel)"
        case .transcribing:
            return "녹음이 끝났습니다. 음성을 텍스트로 변환하는 중입니다."
        case .answering:
            return "전사가 끝났습니다. 검색 및 응답을 생성하는 중입니다."
        case .cooldown:
            return "다음 입력을 준비하는 중입니다."
        case .stopped:
            return "라이브 루프가 중지되었습니다."
        case .error:
            return "최근 음성 작업에서 오류가 발생했습니다."
        }
    }

    private func beginRecordingPhase() {
        cancelPhaseTransition()
        voiceLoopPhase = .recording
        recordingElapsedSeconds = 0
        phaseTransitionTask = Task { [weak self] in
            guard let self else { return }
            let start = Date()
            while !Task.isCancelled {
                let elapsed = Date().timeIntervalSince(start)
                recordingElapsedSeconds = min(elapsed, pttDurationSeconds)
                if elapsed >= pttDurationSeconds {
                    break
                }
                try? await Task.sleep(for: .milliseconds(150))
            }
            if !Task.isCancelled && isLoading {
                voiceLoopPhase = .transcribing
            }
        }
    }

    private func transitionToAnswering() {
        cancelPhaseTransition()
        voiceLoopPhase = .answering
    }

    private func cancelPhaseTransition() {
        phaseTransitionTask?.cancel()
        phaseTransitionTask = nil
    }

    private func startBypass() {
        do {
            try bypassMonitor.start(deviceID: selectedInputDeviceID.isEmpty ? nil : selectedInputDeviceID)
            bypassEnabled = true
            bypassStatusMessage = selectedInputDeviceName.map { "\($0) → 스피커 바이패스 중" } ?? "시스템 기본 입력 → 스피커 바이패스 중"
        } catch {
            bypassEnabled = false
            bypassStatusMessage = "바이패스 시작 실패: \(error.localizedDescription)"
            errorMessage = bypassStatusMessage
            appLog("bypass failed: \(error.localizedDescription)")
        }
    }

    private func stopBypass() {
        bypassMonitor.stop()
        bypassEnabled = false
        bypassStatusMessage = "바이패스 꺼짐"
    }

    private func restartBypass() {
        stopBypass()
        startBypass()
    }

    private var recordingElapsedLabel: String {
        String(format: "%.1f초", recordingElapsedSeconds)
    }

    private var maxRecordingLabel: String {
        String(format: "%.1f초", pttDurationSeconds)
    }
}

private extension URL {
    func createDirectoryIfNeeded() throws {
        try FileManager.default.createDirectory(at: self, withIntermediateDirectories: true)
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

struct ToneBadge: View {
    let title: String
    let color: Color

    var body: some View {
        Text(title)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 9)
            .padding(.vertical, 5)
            .background(color.opacity(0.14))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }
}

struct SectionCard<Content: View>: View {
    let title: String
    let subtitle: String?
    @ViewBuilder let content: Content

    init(_ title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.headline.weight(.semibold))
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(Color(NSColor.windowBackgroundColor).opacity(0.96))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Color.primary.opacity(0.08), lineWidth: 1)
        )
    }
}

struct ActivityDots: View {
    let activeColor: Color
    let active: Bool

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<4, id: \.self) { index in
                Circle()
                    .fill(active ? activeColor.opacity(0.35 + (Double(index) * 0.15)) : Color.gray.opacity(0.18))
                    .frame(width: 7, height: 7)
            }
        }
    }
}

struct VoicePhaseIndicator: View {
    let phase: VoiceLoopPhase
    let active: Bool
    @State private var pulse = false

    private var tint: Color {
        switch phase {
        case .idle, .stopped:
            return .gray
        case .recording:
            return .red
        case .transcribing:
            return .orange
        case .answering:
            return .blue
        case .cooldown:
            return .mint
        case .error:
            return .red
        }
    }

    private var label: String {
        switch phase {
        case .idle:
            return "Ready"
        case .recording:
            return "Listening"
        case .transcribing:
            return "Transcribing"
        case .answering:
            return "Answering"
        case .cooldown:
            return "Cooldown"
        case .stopped:
            return "Stopped"
        case .error:
            return "Error"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                ForEach(0..<5, id: \.self) { index in
                    Capsule()
                        .fill(tint.opacity(active ? 0.95 : 0.35))
                        .frame(width: 8, height: barHeight(at: index))
                }
            }
            .frame(height: 30, alignment: .bottom)
            .animation(
                active ? .easeInOut(duration: 0.6).repeatForever(autoreverses: true) : .easeOut(duration: 0.2),
                value: pulse
            )

            Text(label)
                .font(.caption.weight(.semibold))
                .foregroundStyle(tint)
        }
        .onAppear {
            pulse = active
        }
        .onChange(of: active) { _, newValue in
            pulse = newValue
        }
    }

    private func barHeight(at index: Int) -> CGFloat {
        let base: [CGFloat] = [10, 18, 26, 18, 10]
        guard active else { return base[index] }
        let offset = pulse ? CGFloat(index % 3) * 6 : CGFloat((4 - index) % 3) * 6
        return base[index] + offset
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

    private var phaseColor: Color {
        switch viewModel.voiceLoopPhase {
        case .idle, .stopped:
            return .gray
        case .recording:
            return .red
        case .transcribing:
            return .orange
        case .answering:
            return .blue
        case .cooldown:
            return .mint
        case .error:
            return .red
        }
    }

    private var healthColor: Color {
        guard let health = viewModel.health else { return .gray }
        switch health.statusLevel {
        case "healthy":
            return .green
        case "warning":
            return .orange
        default:
            return .red
        }
    }

    private var primaryIssueSummary: String {
        guard let health = viewModel.health else { return viewModel.healthMessage }
        if health.failedChecks.isEmpty {
            return "모든 런타임 상태가 정상입니다."
        }
        return "확인이 필요한 항목: \(health.failedChecks.joined(separator: ", "))"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                SectionCard("JARVIS", subtitle: "Menu bar runtime console") {
                    HStack(alignment: .center, spacing: 12) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(primaryIssueSummary)
                                .font(.subheadline.weight(.semibold))
                            Text(viewModel.phaseStatusText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 8) {
                            VoicePhaseIndicator(
                                phase: viewModel.voiceLoopPhase,
                                active: viewModel.isLoading || viewModel.voiceLoopEnabled
                            )
                            if let health = viewModel.health {
                                Text("\(health.chunkCount) chunks")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    if viewModel.isLoading {
                        VStack(alignment: .leading, spacing: 6) {
                            ProgressView()
                                .controlSize(.small)
                            Text(viewModel.phaseStatusText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Picker("패널", selection: $viewModel.selectedPanel) {
                    ForEach(MenuPanel.allCases) { panel in
                        Text(panel.title).tag(panel)
                    }
                }
                .pickerStyle(.segmented)

                if viewModel.selectedPanel == .assistant {
                    SectionCard("Input", subtitle: "질문과 녹음 제어") {
                        VStack(alignment: .leading, spacing: 10) {
                            TextField("질문을 입력하세요", text: $viewModel.query)
                                .textFieldStyle(.roundedBorder)
                                .onSubmit {
                                    viewModel.submit()
                                }

                            HStack(spacing: 8) {
                                Button {
                                    viewModel.recordOnce()
                                } label: {
                                    Label("Record Once", systemImage: "mic.fill")
                                }
                                .help("Push-to-talk once")

                                Button(viewModel.voiceLoopEnabled ? "Stop Loop" : "Live Loop") {
                                    viewModel.toggleVoiceLoop()
                                }

                                Button(viewModel.bypassEnabled ? "Bypass Off" : "Bypass On") {
                                    viewModel.toggleBypass()
                                }

                                Button("Ask") {
                                    viewModel.submit()
                                }
                                .keyboardShortcut(.return, modifiers: [.command])

                                Spacer()
                            }
                        }
                    }

                    SectionCard("Transcript", subtitle: "최근 수음 결과") {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 6) {
                                ToneBadge(title: viewModel.voiceLoopPhase.rawValue, color: phaseColor)
                                if viewModel.voiceLoopEnabled {
                                    ToneBadge(title: "live-loop", color: .blue)
                                }
                                if viewModel.bypassEnabled {
                                    ToneBadge(title: "bypass", color: .mint)
                                }
                            }
                            Text(viewModel.lastTranscript.isEmpty ? "아직 전사된 텍스트가 없습니다." : viewModel.lastTranscript)
                                .font(.body)
                                .foregroundStyle(viewModel.lastTranscript.isEmpty ? .secondary : .primary)
                                .textSelection(.enabled)
                        }
                    }

                    if let errorMessage = viewModel.errorMessage {
                        SectionCard("Error", subtitle: "최근 브리지 또는 런타임 오류") {
                            ScrollView {
                                Text(errorMessage)
                                    .font(.callout)
                                    .foregroundStyle(.red)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .textSelection(.enabled)
                            }
                            .frame(maxHeight: 120)
                        }
                    }

                    if let exportMessage = viewModel.exportMessage {
                        SectionCard("Activity", subtitle: "최근 작업 결과") {
                            Text(exportMessage)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                    }

                    SectionCard("Response", subtitle: "응답과 출처") {
                        if let response = viewModel.response {
                            if let status = response.status {
                                HStack(spacing: 6) {
                                    ToneBadge(title: status.mode, color: .blue)
                                    ToneBadge(title: "safe", color: status.safeMode ? .orange : .gray)
                                    ToneBadge(title: "degraded", color: status.degradedMode ? .orange : .gray)
                                    ToneBadge(title: "write-block", color: status.writeBlocked ? .red : .gray)
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
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .frame(minHeight: 220, maxHeight: 340)
                        } else {
                            Text("텍스트 질의와 수음 결과, 응답 본문만 우선 표시합니다.")
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                } else if viewModel.selectedPanel == .health {
                    SectionCard("Health", subtitle: viewModel.healthMessage) {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(spacing: 8) {
                                Button("Refresh Health") {
                                    Task {
                                        await viewModel.refreshHealth()
                                    }
                                }
                                .controlSize(.small)

                                Button("Copy Health") {
                                    viewModel.copyHealthSummary()
                                }
                                .controlSize(.small)

                                Button("Save Health") {
                                    viewModel.saveHealthSummary()
                                }
                                .controlSize(.small)

                                Button("Copy Error") {
                                    viewModel.copyErrorMessage()
                                }
                                .controlSize(.small)

                                Button("Save Error") {
                                    viewModel.saveErrorMessage()
                                }
                                .controlSize(.small)
                            }

                            if let health = viewModel.health {
                                HStack(spacing: 6) {
                                    ToneBadge(title: health.statusLevel, color: healthColor)
                                    ToneBadge(title: health.bridgeMode, color: .blue)
                                    ToneBadge(title: "\(health.chunkCount) chunks", color: .secondary)
                                }

                                if !health.failedChecks.isEmpty {
                                    Text("Issues: \(health.failedChecks.joined(separator: ", "))")
                                        .font(.caption)
                                        .foregroundStyle(.orange)
                                        .textSelection(.enabled)
                                }

                                if !health.knowledgeBasePath.isEmpty {
                                    Text(health.knowledgeBasePath)
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                        .textSelection(.enabled)
                                }

                                VStack(alignment: .leading, spacing: 6) {
                                    ForEach(health.checks.keys.sorted(), id: \.self) { key in
                                        HealthCheckRow(
                                            name: key,
                                            ok: health.checks[key] ?? false,
                                            detail: health.details[key] ?? ""
                                        )
                                    }
                                }
                            }
                        }
                    }
                } else {
                    SectionCard("Audio", subtitle: "입력 장치와 실시간 상태") {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(spacing: 8) {
                                Picker("마이크", selection: $viewModel.selectedInputDeviceID) {
                                    Text("시스템 기본 입력").tag("")
                                    ForEach(viewModel.availableInputDevices) { device in
                                        Text(device.name).tag(device.id)
                                    }
                                }
                                .pickerStyle(.menu)

                                Button("장치 새로고침") {
                                    viewModel.refreshAudioInputDevices()
                                }
                                .controlSize(.small)
                            }

                            HStack(spacing: 8) {
                                Button(viewModel.bypassEnabled ? "Bypass Off" : "Bypass On") {
                                    viewModel.toggleBypass()
                                }
                                .controlSize(.small)

                                Text(viewModel.bypassStatusMessage)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }

                            Text(viewModel.inputDeviceStatusMessage)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                    }
                }
            }
            .padding(16)
        }
        .frame(width: 500, height: 860)
        .background(
            LinearGradient(
                colors: [
                    Color(NSColor.controlBackgroundColor),
                    Color(NSColor.windowBackgroundColor),
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
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
