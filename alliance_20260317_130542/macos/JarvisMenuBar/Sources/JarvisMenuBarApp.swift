import AppKit
import AudioToolbox
import AVFoundation
import Combine
import SwiftUI

func appLog(_ message: String) {
    fputs("[JarvisMenuBar] \(message)\n", stderr)
}

enum MenuBarIconFactory {
    static let image: NSImage = {
        let size = NSSize(width: 18, height: 18)
        let image = NSImage(size: size)
        image.lockFocus()

        NSColor.black.setFill()
        let badgeRect = NSRect(x: 2.5, y: 2.5, width: 13, height: 13)
        NSBezierPath(roundedRect: badgeRect, xRadius: 3.5, yRadius: 3.5).fill()

        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .center

        let glyphRect = NSRect(x: 0, y: 2.4, width: size.width, height: size.height)
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 10, weight: .black),
            .foregroundColor: NSColor.white,
            .paragraphStyle: paragraph,
        ]
        NSString(string: "J").draw(in: glyphRect, withAttributes: attributes)

        image.unlockFocus()
        image.isTemplate = true
        return image
    }()
}

@MainActor
final class NavigationPanelController {
    private let panel: NSPanel
    private let host: NSHostingController<NavigationAssistView>
    private var cancellables: Set<AnyCancellable> = []
    private unowned let viewModel: JarvisMenuBarViewModel

    init(viewModel: JarvisMenuBarViewModel) {
        self.viewModel = viewModel
        self.host = NSHostingController(rootView: NavigationAssistView(viewModel: viewModel))
        self.panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 420, height: 520),
            styleMask: [.nonactivatingPanel, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        panel.isFloatingPanel = true
        panel.level = .popUpMenu
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary, .transient, .ignoresCycle]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.hidesOnDeactivate = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.isMovableByWindowBackground = true
        panel.contentViewController = host

        observeViewModel()
    }

    private func observeViewModel() {
        viewModel.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] in
                self?.refresh()
            }
            .store(in: &cancellables)
    }

    func refresh() {
        host.rootView = NavigationAssistView(viewModel: viewModel)
        guard viewModel.shouldShowNavigationPanel else {
            panel.orderOut(nil)
            return
        }
        positionPanel()
        panel.orderFront(nil)
        panel.orderFrontRegardless()
        panel.makeKey()
    }

    private func positionPanel() {
        guard let screen = NSScreen.main ?? NSScreen.screens.first else { return }
        let visible = screen.visibleFrame
        let size = panel.frame.size
        let origin = NSPoint(
            x: visible.maxX - size.width - 22,
            y: visible.maxY - size.height - 52
        )
        panel.setFrameOrigin(origin)
    }
}

enum VoiceLoopPhase: String {
    case idle = "idle"
    case recording = "recording"
    case pauseDetected = "pause_detected"
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

enum InteractionMode: String, CaseIterable, Identifiable {
    case generalQuery = "general_query"
    case sourceExploration = "source_exploration"
    case documentExploration = "document_exploration"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .generalQuery:
            return "일반 질의 모드"
        case .sourceExploration:
            return "소스 탐색 모드"
        case .documentExploration:
            return "문서 탐색 모드"
        }
    }
}

enum SourceExplorationFocus: String {
    case files = "files"
    case classes = "classes"
    case functions = "functions"
    case detail = "detail"

    var title: String {
        switch self {
        case .files:
            return "파일 후보"
        case .classes:
            return "클래스 후보"
        case .functions:
            return "함수 후보"
        case .detail:
            return "선택 상세"
        }
    }
}

enum DocumentExplorationFocus: String {
    case documents = "documents"
    case detail = "detail"

    var title: String {
        switch self {
        case .documents:
            return "문서 후보"
        case .detail:
            return "문서 상세"
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

/// Records microphone audio to a WAV file using AVCaptureDevice natively.
///
/// The session stays running between recordings to keep the microphone
/// hardware warm.  `record()` only toggles the file-writing flag,
/// so recording starts instantly without device initialization delay.
@MainActor
final class JarvisMenuBarViewModel: ObservableObject {
    private static let selectedInputDeviceDefaultsKey = "selectedInputDeviceID"
    private static let diagnosticsDirectory = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".jarvis", isDirectory: true)
        .appendingPathComponent("diagnostics", isDirectory: true)

    @Published var query = ""
    @Published var response: MenuResponse? {
        didSet {
            syncExplorationSelection()
        }
    }
    @Published var navigationWindow: MenuExplorationState?
    @Published var navigationPhaseLabel = ""
    @Published var navigationSummaryText = ""
    @Published var isLoading = false
    @Published var streamingText = ""
    @Published var isStreaming = false
    @Published var errorMessage: String?
    @Published var exportMessage: String?
    @Published var selectedExplorationItemID = ""
    @Published var sourceExplorationSessionActive = false
    @Published var sourceExplorationFocus: SourceExplorationFocus = .files
    @Published var documentExplorationSessionActive = false
    @Published var documentExplorationFocus: DocumentExplorationFocus = .documents
    @Published var showApprovalPanel = false
    @Published var exportFilename = "jarvis-draft.txt"
    @Published var exportFormat: ExportFormat = .txt
    @Published var exportLocation: ExportLocation = .jarvisExports
    @Published var voiceLoopEnabled = false
    @Published var wakeWordEnabled = false
    private var wakeWordSession: WakeWordSession?
    @Published var voiceLoopPhase: VoiceLoopPhase = .idle
    @Published var isSpeaking = false
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
            // Mic will re-activate with new device on next recording
            nativeRecorder.deactivate()
        }
    }
    @Published var inputDeviceStatusMessage = "시스템 기본 입력 장치를 사용합니다."

    private let bridge: JarvisBridge
    private let bypassMonitor = AudioBypassMonitor()
    private let liveTranscriber = LiveSpeechTranscriber()
    let nativeRecorder = NativeAudioRecorder()
    private var voiceLoopTask: Task<Void, Never>?
    private var ttsPlaybackTask: Task<Void, Never>?
    private let successLoopDelay: Duration = .seconds(1.2)
    private let errorLoopDelay: Duration = .seconds(4)
    private let maxConsecutiveLoopErrors = 3
    private let pttDurationSeconds: Double
    private var phaseTransitionTask: Task<Void, Never>?
    private var navigationUpdateTask: Task<Void, Never>?
    private var navigationHideTask: Task<Void, Never>?
    private var queryNormalizationTask: Task<Void, Never>?
    private var partialTranscriptionActive = false
    private var navigationPanelVisibleUntil: Date?

    @Published var microphoneReady = false

    init(bridge: JarvisBridge = JarvisBridge()) {
        self.bridge = bridge
        self.pttDurationSeconds = Double(ProcessInfo.processInfo.environment["JARVIS_PTT_SECONDS"] ?? "8") ?? 8
        self.selectedInputDeviceID = UserDefaults.standard.string(forKey: Self.selectedInputDeviceDefaultsKey) ?? ""
        // CoreAudio-based device scan is safe to call synchronously (no blocking)
        refreshAudioInputDevices()
        Task { await refreshHealth() }

        // Eagerly start the persistent Python server so the first query is fast.
        Task { await bridge.warmup() }

        liveTranscriber.onPartialTranscript = { [weak self] transcript in
            Task { @MainActor [weak self] in
                guard let self, self.partialTranscriptionActive else { return }
                self.lastTranscript = transcript
                self.query = transcript
                self.normalizeLiveQuery(transcript)
                self.refreshNavigationWindow(for: transcript, immediate: true)
            }
        }

        // Pre-warm the audio engine so the first recording doesn't have
        // a cold-start delay. Runs on background to avoid blocking UI.
        Task.detached { [nativeRecorder, selectedInputDeviceID] in
            let deviceID = selectedInputDeviceID.isEmpty ? nil : selectedInputDeviceID
            do {
                try nativeRecorder.activate(deviceID: deviceID)
                appLog("Audio engine pre-warmed")
            } catch {
                appLog("Pre-warm failed (will retry on first recording): \(error)")
            }
        }
    }

    private func startLiveTranscription() {
        partialTranscriptionActive = true
        nativeRecorder.onLiveAudioBuffer = { [weak self] buffer in
            self?.liveTranscriber.append(buffer)
        }
        Task { [liveTranscriber] in
            await liveTranscriber.start()
        }
    }

    private func stopLiveTranscription() {
        partialTranscriptionActive = false
        queryNormalizationTask?.cancel()
        nativeRecorder.onLiveAudioBuffer = nil
        liveTranscriber.stop()
    }

    private func normalizeLiveQuery(_ rawQuery: String) {
        let trimmed = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        queryNormalizationTask?.cancel()
        guard !trimmed.isEmpty else { return }
        queryNormalizationTask = Task { [weak self] in
            guard let self else { return }
            do {
                let normalized = try await bridge.normalizeQuery(trimmed)
                await MainActor.run {
                    guard self.partialTranscriptionActive else { return }
                    if self.lastTranscript == rawQuery {
                        self.query = normalized
                    }
                }
            } catch {
                // Keep raw partial transcript if normalization fails.
            }
        }
    }

    private func extendNavigationPanelVisibility(for seconds: TimeInterval) {
        let deadline = Date().addingTimeInterval(seconds)
        navigationPanelVisibleUntil = deadline
        navigationHideTask?.cancel()
        navigationHideTask = Task { @MainActor [weak self] in
            guard let self else { return }
            let remaining = deadline.timeIntervalSinceNow
            if remaining > 0 {
                try? await Task.sleep(for: .milliseconds(Int((remaining * 1000).rounded())))
            }
            guard !Task.isCancelled else { return }
            if let currentDeadline = self.navigationPanelVisibleUntil,
               currentDeadline <= Date(),
               !self.partialTranscriptionActive,
               !self.isLoading,
               !self.voiceLoopEnabled,
               !self.wakeWordEnabled,
               !self.isStreaming {
                self.navigationPanelVisibleUntil = nil
                self.navigationWindow = nil
            }
        }
    }

    func refreshNavigationWindow(for rawQuery: String, immediate: Bool = false) {
        let trimmed = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        navigationUpdateTask?.cancel()
        guard !trimmed.isEmpty else {
            navigationPanelVisibleUntil = nil
            navigationWindow = nil
            navigationPhaseLabel = ""
            navigationSummaryText = ""
            return
        }
        if immediate, currentInteractionMode != .generalQuery {
            navigationWindow = MenuExplorationState(
                mode: currentInteractionMode.rawValue,
                targetFile: "",
                targetDocument: "",
                fileCandidates: [],
                documentCandidates: [],
                classCandidates: [],
                functionCandidates: []
            )
            navigationPhaseLabel = "실시간 추정"
            navigationSummaryText = "음성 입력을 기준으로 후보를 추정하는 중입니다"
            extendNavigationPanelVisibility(for: 1.2)
        }
        navigationUpdateTask = Task { [weak self] in
            guard let self else { return }
            if !immediate {
                try? await Task.sleep(for: .milliseconds(220))
            }
            if Task.isCancelled { return }
            do {
                let nav = try await bridge.navigationWindow(query: trimmed)
                await MainActor.run {
                    self.navigationWindow = nav
                    self.navigationPhaseLabel = immediate ? "실시간 후보" : "정리된 후보"
                    self.navigationSummaryText = self.navigationSummary(for: nav, final: false)
                    self.extendNavigationPanelVisibility(for: immediate ? 1.2 : 2.5)
                    self.syncExplorationSelection()
                }
            } catch {
                await MainActor.run {
                    self.navigationPanelVisibleUntil = nil
                    self.navigationWindow = nil
                    self.navigationPhaseLabel = ""
                    self.navigationSummaryText = ""
                }
            }
        }
    }

    private func hasExplorationCandidates(_ exploration: MenuExplorationState?) -> Bool {
        guard let exploration else { return false }
        return !exploration.fileCandidates.isEmpty
            || !exploration.documentCandidates.isEmpty
            || !exploration.classCandidates.isEmpty
            || !exploration.functionCandidates.isEmpty
    }

    private func keepBestExploration(_ exploration: MenuExplorationState?) {
        if hasExplorationCandidates(exploration) {
            navigationWindow = exploration
            navigationPhaseLabel = "최종 확정"
            navigationSummaryText = navigationSummary(for: exploration, final: true)
            extendNavigationPanelVisibility(for: 12.0)
            syncExplorationSelection()
            return
        }
        if hasExplorationCandidates(navigationWindow) {
            navigationPhaseLabel = "최종 확정"
            navigationSummaryText = navigationSummary(for: navigationWindow, final: true)
            extendNavigationPanelVisibility(for: 12.0)
            syncExplorationSelection()
            return
        }
        navigationWindow = exploration
        navigationPhaseLabel = "응답 반영"
        navigationSummaryText = "응답은 완료되었지만 확정 후보는 제한적입니다"
        extendNavigationPanelVisibility(for: 3.0)
        syncExplorationSelection()
    }

    private func navigationSummary(for exploration: MenuExplorationState?, final: Bool) -> String {
        guard let exploration else { return "" }
        let prefix = final ? "최종 기준" : "현재 기준"
        if !exploration.targetFile.isEmpty, let firstClass = exploration.classCandidates.first?.label {
            return "\(prefix) 파일 \(exploration.targetFile), 클래스 \(firstClass)"
        }
        if !exploration.targetDocument.isEmpty {
            return "\(prefix) 문서 \(exploration.targetDocument)"
        }
        if let firstFile = exploration.fileCandidates.first?.label {
            return "\(prefix) 파일 후보 \(firstFile)"
        }
        if let firstClass = exploration.classCandidates.first?.label {
            return "\(prefix) 클래스 후보 \(firstClass)"
        }
        if let firstFunction = exploration.functionCandidates.first?.label {
            return "\(prefix) 함수 후보 \(firstFunction)"
        }
        return final ? "최종 후보를 정리했습니다" : "후보를 찾는 중입니다"
    }

    func activateMicrophone() async {
        let granted = await AVCaptureDevice.requestAccess(for: .audio)
        guard granted else {
            inputDeviceStatusMessage = "마이크 권한이 거부되었습니다. 시스템 설정에서 허용해 주세요."
            return
        }
        let deviceID = selectedInputDeviceID.isEmpty ? nil : selectedInputDeviceID
        appLog("Activating mic session for device: \(deviceID ?? "system default")")
        do {
            try nativeRecorder.activate(deviceID: deviceID)
            microphoneReady = true
            appLog("Microphone session active, isRunning=\(nativeRecorder.isSessionRunning)")
        } catch {
            appLog("Microphone activation failed: \(error.localizedDescription)")
            inputDeviceStatusMessage = "마이크 활성화 실패: \(error.localizedDescription)"
        }
    }

    func submit() {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return
        }
        guard let resolvedQuery = prepareQueryForSubmission(trimmed) else {
            return
        }

        isLoading = true
        isStreaming = true
        streamingText = ""
        errorMessage = nil
        response = nil
        transitionToAnswering()
        Task {
            let stream = await bridge.askStreaming(resolvedQuery)
            for await event in stream {
                switch event {
                case .token(let token):
                    streamingText += token
                case .done(let finalResponse):
                    if let finalResponse {
                        response = finalResponse
                        lastTranscript = finalResponse.query
                        keepBestExploration(finalResponse.exploration)
                    }
                    isStreaming = false
                case .error(let message):
                    appLog("streaming ask failed: \(message)")
                    // Fallback to non-streaming
                    do {
                        let payload = try await bridge.ask(resolvedQuery)
                        response = payload
                        lastTranscript = payload.query
                        keepBestExploration(payload.exploration)
                    } catch {
                        errorMessage = error.localizedDescription
                        cancelPhaseTransition()
                        voiceLoopPhase = .error
                    }
                    isStreaming = false
                }
            }
            if isStreaming { isStreaming = false }  // Safety
            exportMessage = nil
            isLoading = false

            // TTS — speak the final response
            if let finalText = response?.response ?? (streamingText.isEmpty ? nil : streamingText) {
                speakResponse(finalText)
            }
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
                // Step 1: Native recording via AVCaptureDevice (no ffmpeg)
                let deviceID = selectedInputDeviceID.isEmpty ? nil : selectedInputDeviceID
                startLiveTranscription()
                let audioURL = try await nativeRecorder.record(
                    deviceID: deviceID,
                    duration: pttDurationSeconds
                )
                stopLiveTranscription()
                appLog("Recording done: \(audioURL.path)")

                cancelPhaseTransition()
                voiceLoopPhase = .transcribing

                // Step 2: Transcribe via Python whisper-cli
                let transcript = try await bridge.transcribeFile(audioPath: audioURL.path)
                lastTranscript = transcript.transcript
                query = transcript.transcript
                refreshNavigationWindow(for: transcript.transcript)
                guard let resolvedQuery = prepareQueryForSubmission(transcript.transcript) else {
                    isLoading = false
                    if !voiceLoopEnabled {
                        cancelPhaseTransition()
                        voiceLoopPhase = .idle
                    }
                    return
                }

                // Step 3: Search + Answer via Python LLM
                voiceLoopPhase = .answering
                let payload = try await bridge.ask(resolvedQuery)
                response = payload
                keepBestExploration(payload.exploration)
                exportMessage = nil

                // Step 4: TTS — speak the response
                speakResponse(payload.response)
            } catch {
                stopLiveTranscription()
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

    // MARK: - Wake Word

    func toggleWakeWord() {
        if wakeWordEnabled {
            stopWakeWord()
        } else {
            startWakeWord()
        }
    }

    private func startWakeWord() {
        wakeWordEnabled = true
        appLog("JARVIS mode active — continuous voice interaction")
        // Start continuous voice loop with TTS responses
        if !voiceLoopEnabled {
            startVoiceLoop()
        }
    }

    // MARK: - TTS Playback

    private var ttsProcess: Process?

    /// Speak response text via the Python bridge so menu bar playback uses the
    /// same persona-aware TTS path as the core runtime.
    func speakResponse(_ text: String) {
        let stripped = Self.stripForTTS(text)
        guard !stripped.isEmpty else { return }

        stopTTS()
        isSpeaking = true

        let playbackTask = Task.detached(priority: .userInitiated) { [weak self] in
            guard let self else { return }
            do {
                let speech = try await self.bridge.synthesizeSpeech(text: stripped)
                try Task.checkCancellation()

                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/usr/bin/afplay")
                process.arguments = [speech.audioPath]
                process.standardOutput = FileHandle.nullDevice
                process.standardError = FileHandle.nullDevice
                await MainActor.run {
                    self.ttsProcess = process
                }
                try process.run()
                process.waitUntilExit()
            } catch {
                appLog("TTS failed: \(error.localizedDescription)")
            }
            await MainActor.run {
                self.isSpeaking = false
                self.ttsProcess = nil
            }
        }
        ttsPlaybackTask = playbackTask
    }

    /// Strip markdown and meta-commentary for natural TTS reading.
    /// Only keeps the core answer — cuts off when meta-commentary starts.
    static func stripForTTS(_ text: String) -> String {
        var result = text

        // Strip markdown formatting
        result = result.replacingOccurrences(of: "**", with: "")
        result = result.replacingOccurrences(of: "`", with: "")
        result = result.replacingOccurrences(of: "### ", with: "")
        result = result.replacingOccurrences(of: "## ", with: "")
        result = result.replacingOccurrences(of: "# ", with: "")

        // Strip citation labels [1], [2] and file references
        result = result.replacingOccurrences(
            of: "\\[\\d+\\]", with: "", options: .regularExpression
        )
        result = result.replacingOccurrences(
            of: "\\[[^\\]]*\\.[a-z]{2,5}\\]", with: "", options: .regularExpression
        )

        // Cut off at meta-commentary — only keep lines before it starts
        let cutoffPhrases = [
            "제공된 증거",
            "주어진 데이터",
            "정확한 메뉴를 알고",
            "정확한 답변을",
            "이 정보는",
            "출처:",
            "참고:",
            "Note:",
            "다만,",
            "하지만 예시로",
        ]
        let lines = result.components(separatedBy: "\n")
        var kept: [String] = []
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }
            // Stop at first meta-commentary line
            if cutoffPhrases.contains(where: { trimmed.hasPrefix($0) }) { break }
            kept.append(trimmed)
        }
        // Convert newlines to periods for natural speech pauses
        result = kept.joined(separator: ". ")

        // Clean extra periods and whitespace
        result = result.replacingOccurrences(
            of: "\\.\\s*\\.+", with: ".", options: .regularExpression
        )
        result = result.replacingOccurrences(
            of: "  +", with: " ", options: .regularExpression
        )
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Stop any currently playing TTS.
    func stopTTS() {
        ttsPlaybackTask?.cancel()
        ttsPlaybackTask = nil
        ttsProcess?.terminate()
        ttsProcess = nil
        isSpeaking = false
    }

    private func stopWakeWord() {
        wakeWordEnabled = false
        if voiceLoopEnabled {
            stopVoiceLoop()
        }
        stopTTS()
        appLog("JARVIS mode stopped")
    }

    func shutdownBridge() async {
        await bridge.shutdown()
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
        // Use CoreAudio APIs exclusively — AVCaptureDevice APIs can hang on
        // aggregate devices (Revelator통합 6ch) and lock the entire audio system.

        var defaultDeviceUID: String = ""
        var devices: [AudioInputDevice] = []

        // 1) Get default input device UID
        var defAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDefaultInputDevice,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var defDevID: AudioDeviceID = 0
        var defSize = UInt32(MemoryLayout<AudioDeviceID>.size)
        if AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &defAddress, 0, nil, &defSize, &defDevID) == noErr {
            defaultDeviceUID = Self.getDeviceUID(defDevID) ?? ""
        }

        // 2) Enumerate all audio devices with input channels
        var devicesAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var propSize: UInt32 = 0
        AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &devicesAddress, 0, nil, &propSize)
        let count = Int(propSize) / MemoryLayout<AudioDeviceID>.size
        var deviceIDs = [AudioDeviceID](repeating: 0, count: count)
        AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &devicesAddress, 0, nil, &propSize, &deviceIDs)

        for devID in deviceIDs {
            // Check if device has input channels
            var inputAddress = AudioObjectPropertyAddress(
                mSelector: kAudioDevicePropertyStreamConfiguration,
                mScope: kAudioObjectPropertyScopeInput,
                mElement: kAudioObjectPropertyElementMain
            )
            var bufSize: UInt32 = 0
            guard AudioObjectGetPropertyDataSize(devID, &inputAddress, 0, nil, &bufSize) == noErr, bufSize > 0 else { continue }
            let bufferList = UnsafeMutablePointer<AudioBufferList>.allocate(capacity: Int(bufSize))
            defer { bufferList.deallocate() }
            guard AudioObjectGetPropertyData(devID, &inputAddress, 0, nil, &bufSize, bufferList) == noErr else { continue }
            let inputChannels = UnsafeMutableAudioBufferListPointer(bufferList).reduce(0) { $0 + Int($1.mNumberChannels) }
            guard inputChannels > 0 else { continue }

            // Get device name and UID
            guard let uid = Self.getDeviceUID(devID) else { continue }
            var nameAddress = AudioObjectPropertyAddress(
                mSelector: kAudioObjectPropertyName,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            var name: Unmanaged<CFString>?
            var nameSize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
            guard AudioObjectGetPropertyData(devID, &nameAddress, 0, nil, &nameSize, &name) == noErr,
                  let deviceName = name?.takeRetainedValue() as String? else { continue }

            devices.append(AudioInputDevice(id: uid, name: deviceName))
        }

        devices.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }

        defaultInputDeviceID = defaultDeviceUID
        availableInputDevices = devices

        if selectedInputDeviceID.isEmpty {
            inputDeviceStatusMessage = "시스템 기본 입력 장치를 사용합니다."
        } else if !devices.contains(where: { $0.id == selectedInputDeviceID }) {
            selectedInputDeviceID = ""
            inputDeviceStatusMessage = "선택한 마이크를 찾을 수 없어 시스템 기본 입력으로 전환했습니다."
        }
    }

    private static func getDeviceUID(_ deviceID: AudioDeviceID) -> String? {
        var uidAddress = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyDeviceUID,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        var uid: Unmanaged<CFString>?
        var uidSize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
        guard AudioObjectGetPropertyData(deviceID, &uidAddress, 0, nil, &uidSize, &uid) == noErr,
              let uidStr = uid?.takeRetainedValue() as String? else { return nil }
        return uidStr
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
        stopLiveTranscription()
        stopTTS()
        navigationPanelVisibleUntil = nil
        navigationWindow = nil
        cancelPhaseTransition()
        isLoading = false
        voiceLoopPhase = .stopped
        consecutiveLoopErrors = 0
    }

    private func runVoiceLoopIteration() async -> Duration? {
        isLoading = true
        beginRecordingPhase()

        do {
            let deviceID = selectedInputDeviceID.isEmpty ? nil : selectedInputDeviceID
            startLiveTranscription()
            let audioURL = try await nativeRecorder.record(
                deviceID: deviceID,
                duration: pttDurationSeconds
            )
            stopLiveTranscription()
            if Task.isCancelled {
                return nil
            }
            cancelPhaseTransition()
            voiceLoopPhase = .transcribing

            let transcript = try await bridge.transcribeFile(audioPath: audioURL.path)
            lastTranscript = transcript.transcript
            query = transcript.transcript
            refreshNavigationWindow(for: transcript.transcript)
            guard let resolvedQuery = prepareQueryForSubmission(transcript.transcript) else {
                isLoading = false
                voiceLoopPhase = .cooldown
                return successLoopDelay
            }

            voiceLoopPhase = .answering
            let payload = try await bridge.ask(resolvedQuery)
            if Task.isCancelled {
                return nil
            }
            response = payload
            keepBestExploration(payload.exploration)
            exportMessage = nil
            errorMessage = nil
            consecutiveLoopErrors = 0
            isLoading = false

            // TTS — speak the response
            speakResponse(payload.response)

            voiceLoopPhase = .cooldown
            return successLoopDelay
        } catch {
            stopLiveTranscription()
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

    func copyResponse() {
        guard let response else {
            return
        }
        let fullContent: String
        if let path = response.fullResponsePath, !path.isEmpty,
           let fileContent = try? String(contentsOfFile: path, encoding: .utf8) {
            fullContent = fileContent
        } else {
            fullContent = response.response
        }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(fullContent, forType: .string)
        exportMessage = "응답을 클립보드에 복사했습니다."
    }

    var currentInteractionMode: InteractionMode {
        if sourceExplorationSessionActive {
            return .sourceExploration
        }
        if documentExplorationSessionActive {
            return .documentExploration
        }
        if let raw = response?.renderHints?.interactionMode,
           let mode = InteractionMode(rawValue: raw) {
            return mode
        }
        let lowered = query.lowercased()
        if lowered.contains("소스")
            || lowered.contains("코드")
            || lowered.contains("클래스")
            || lowered.contains("함수")
            || lowered.contains("메서드")
            || lowered.contains("메소드")
            || lowered.contains(".py")
            || lowered.contains(".ts")
            || lowered.contains(".js")
            || lowered.contains("python")
            || lowered.contains("class")
            || lowered.contains("function")
            || lowered.contains("method") {
            return .sourceExploration
        }
        if lowered.contains("문서")
            || lowered.contains("pdf")
            || lowered.contains("ppt")
            || lowered.contains("doc")
            || lowered.contains("보고서")
            || lowered.contains("가이드")
            || lowered.contains("매뉴얼")
            || lowered.contains("요약") {
            return .documentExploration
        }
        return .generalQuery
    }

    var currentExplorationItems: [MenuExplorationItem] {
        let exploration = navigationWindow ?? response?.exploration
        guard let exploration else {
            return []
        }
        return exploration.fileCandidates
            + exploration.documentCandidates
            + exploration.classCandidates
            + exploration.functionCandidates
    }

    var currentSelectedExplorationItem: MenuExplorationItem? {
        currentExplorationItems.first(where: { $0.id == selectedExplorationItemID })
    }

    var activeExplorationState: MenuExplorationState? {
        navigationWindow ?? response?.exploration
    }

    var shouldShowNavigationPanel: Bool {
        guard let exploration = activeExplorationState else {
            return false
        }
        let hasCandidates =
            !exploration.fileCandidates.isEmpty
            || !exploration.documentCandidates.isEmpty
            || !exploration.classCandidates.isEmpty
            || !exploration.functionCandidates.isEmpty
        let shouldShowLoadingState =
            !hasCandidates
            && currentInteractionMode != .generalQuery
            && (partialTranscriptionActive || isLoading || isStreaming)
        guard hasCandidates || shouldShowLoadingState else {
            return false
        }
        if isLoading || voiceLoopEnabled || wakeWordEnabled || partialTranscriptionActive || isStreaming {
            return true
        }
        if let deadline = navigationPanelVisibleUntil, deadline > Date() {
            return true
        }
        return false
    }

    func candidateNumber(for item: MenuExplorationItem) -> Int? {
        currentExplorationItems.firstIndex(where: { $0.id == item.id }).map { $0 + 1 }
    }

    func selectExplorationItem(_ item: MenuExplorationItem) {
        selectedExplorationItemID = item.id
        if item.kind == "document" {
            documentExplorationSessionActive = true
            documentExplorationFocus = .detail
            sourceExplorationSessionActive = false
        } else {
            sourceExplorationSessionActive = true
            sourceExplorationFocus = item.kind == "function" ? .detail : (item.kind == "class" ? .functions : .classes)
            documentExplorationSessionActive = false
        }
        exportMessage = "\(modeLabel(for: item.kind)) 선택: \(item.label)"
    }

    func prepareQueryForSubmission(_ rawQuery: String) -> String? {
        if processLocalVoiceCommand(rawQuery) {
            return nil
        }
        return resolvedSubmissionQuery(rawQuery)
    }

    func resolvedSubmissionQuery(_ rawQuery: String) -> String {
        let exploration = navigationWindow ?? response?.exploration
        guard let exploration else {
            return rawQuery
        }
        if currentInteractionMode == .documentExploration || documentExplorationSessionActive {
            if let selected = resolveExplorationSelection(from: rawQuery), selected.kind == "document" {
                let targetDocument = !exploration.targetDocument.isEmpty ? exploration.targetDocument : selected.label
                let enriched = [
                    rawQuery,
                    "선택 대상 document \(selected.label)",
                    "대상 문서 \(targetDocument)",
                    documentExplorationIntentSuffix(for: rawQuery, selected: selected),
                ]
                .filter { !$0.isEmpty }
                .joined(separator: " ")
                exportMessage = "문서 선택: \(selected.label)"
                return enriched
            }
            return rawQuery
        }
        guard currentInteractionMode == .sourceExploration || sourceExplorationSessionActive else {
            return rawQuery
        }
        guard let selected = resolveExplorationSelection(from: rawQuery) else {
            return rawQuery
        }

        let targetFile = !exploration.targetFile.isEmpty ? exploration.targetFile : selected.path
        let enriched = [
            rawQuery,
            "선택 대상 \(selected.kind) \(selected.label)",
            targetFile.isEmpty ? "" : "대상 파일 \(targetFile)",
            sourceExplorationFocus == .detail ? "소스 탐색 상세 모드" : "소스 탐색 진행 중",
            sourceExplorationIntentSuffix(for: rawQuery, selected: selected),
        ]
        .filter { !$0.isEmpty }
        .joined(separator: " ")
        exportMessage = "\(modeLabel(for: selected.kind)) 선택: \(selected.label)"
        return enriched
    }

    private func resolveExplorationSelection(from rawQuery: String) -> MenuExplorationItem? {
        if let selected = currentSelectedExplorationItem {
            let lowered = rawQuery.lowercased()
            if lowered.contains("선택")
                || lowered.contains("이거")
                || lowered.contains("이 파일")
                || lowered.contains("이 클래스")
                || lowered.contains("이 함수") {
                return selected
            }
        }

        let items = currentExplorationItems
        guard !items.isEmpty else {
            return nil
        }
        if let ordinal = detectedOrdinal(in: rawQuery),
           ordinal >= 1, ordinal <= items.count {
            let item = items[ordinal - 1]
            selectedExplorationItemID = item.id
            return item
        }

        let lowered = rawQuery.lowercased()
        if let item = items.first(where: { item in
            lowered.contains(item.label.lowercased())
                || (!item.path.isEmpty && lowered.contains((item.path as NSString).lastPathComponent.lowercased()))
        }) {
            selectedExplorationItemID = item.id
            return item
        }
        return currentSelectedExplorationItem
    }

    private func processLocalVoiceCommand(_ rawQuery: String) -> Bool {
        let lowered = rawQuery.lowercased()
        if lowered.contains("소스코드 분석 시작")
            || lowered.contains("소스 분석 시작")
            || lowered.contains("소스 탐색 시작") {
            sourceExplorationSessionActive = true
            sourceExplorationFocus = .files
            exportMessage = "소스 탐색 모드를 시작했습니다. 파일 이름이나 후보를 말해 주세요."
            return true
        }
        if lowered.contains("소스 탐색 종료")
            || lowered.contains("소스코드 분석 종료")
            || lowered.contains("소스 분석 종료") {
            sourceExplorationSessionActive = false
            sourceExplorationFocus = .files
            selectedExplorationItemID = ""
            exportMessage = "소스 탐색 모드를 종료했습니다."
            return true
        }
        if lowered.contains("문서 탐색 시작")
            || lowered.contains("문서 분석 시작") {
            documentExplorationSessionActive = true
            documentExplorationFocus = .documents
            sourceExplorationSessionActive = false
            exportMessage = "문서 탐색 모드를 시작했습니다. 문서 이름이나 후보를 말해 주세요."
            return true
        }
        if lowered.contains("문서 탐색 종료")
            || lowered.contains("문서 분석 종료") {
            documentExplorationSessionActive = false
            documentExplorationFocus = .documents
            if currentSelectedExplorationItem?.kind == "document" {
                selectedExplorationItemID = ""
            }
            exportMessage = "문서 탐색 모드를 종료했습니다."
            return true
        }
        if lowered.contains("이전으로") || lowered.contains("뒤로") {
            if documentExplorationSessionActive {
                moveDocumentExplorationBack()
            } else {
                moveSourceExplorationBack()
            }
            return true
        }
        if lowered.contains("파일 후보 보여줘") || lowered.contains("파일 목록 보여줘") {
            sourceExplorationSessionActive = true
            sourceExplorationFocus = .files
            exportMessage = "파일 후보를 보고 있습니다. 번호나 파일명을 말해 주세요."
            return true
        }
        if lowered.contains("클래스 후보 보여줘") || lowered.contains("클래스 목록 보여줘") {
            sourceExplorationSessionActive = true
            sourceExplorationFocus = .classes
            exportMessage = "클래스 후보를 보고 있습니다. 번호나 클래스명을 말해 주세요."
            return true
        }
        if lowered.contains("함수 후보 보여줘") || lowered.contains("함수 목록 보여줘") {
            sourceExplorationSessionActive = true
            sourceExplorationFocus = .functions
            exportMessage = "함수 후보를 보고 있습니다. 번호나 함수명을 말해 주세요."
            return true
        }
        if lowered.contains("문서 후보 보여줘") || lowered.contains("문서 목록 보여줘") {
            documentExplorationSessionActive = true
            documentExplorationFocus = .documents
            exportMessage = "문서 후보를 보고 있습니다. 번호나 문서명을 말해 주세요."
            return true
        }
        return false
    }

    private func moveSourceExplorationBack() {
        sourceExplorationSessionActive = true
        switch sourceExplorationFocus {
        case .detail:
            sourceExplorationFocus = .functions
        case .functions:
            sourceExplorationFocus = .classes
        case .classes:
            sourceExplorationFocus = .files
        case .files:
            sourceExplorationSessionActive = false
        }
        exportMessage = sourceExplorationSessionActive
            ? "\(sourceExplorationFocus.title) 단계로 이동했습니다."
            : "소스 탐색 모드를 종료했습니다."
    }

    private func moveDocumentExplorationBack() {
        switch documentExplorationFocus {
        case .detail:
            documentExplorationFocus = .documents
            exportMessage = "문서 후보 단계로 이동했습니다."
        case .documents:
            documentExplorationSessionActive = false
            exportMessage = "문서 탐색 모드를 종료했습니다."
        }
    }

    private func detectedOrdinal(in text: String) -> Int? {
        let lowered = text.lowercased()
        let mappings: [(String, Int)] = [
            ("첫 번째", 1), ("첫번째", 1), ("1번", 1), ("first", 1), ("one", 1),
            ("두 번째", 2), ("두번째", 2), ("2번", 2), ("second", 2), ("two", 2),
            ("세 번째", 3), ("세번째", 3), ("3번", 3), ("third", 3), ("three", 3),
            ("네 번째", 4), ("네번째", 4), ("4번", 4), ("fourth", 4), ("four", 4),
        ]
        for (token, value) in mappings where lowered.contains(token) {
            return value
        }
        return nil
    }

    private func modeLabel(for kind: String) -> String {
        switch kind {
        case "filename":
            return "파일"
        case "document":
            return "문서"
        case "class":
            return "클래스"
        case "function":
            return "함수"
        default:
            return "항목"
        }
    }

    private func sourceExplorationIntentSuffix(
        for rawQuery: String,
        selected: MenuExplorationItem
    ) -> String {
        let lowered = rawQuery.lowercased()
        let targetFile = (navigationWindow ?? response?.exploration)?.targetFile ?? ""

        if lowered.contains("어디서 쓰")
            || lowered.contains("사용처")
            || lowered.contains("누가 부르")
            || lowered.contains("참조")
            || lowered.contains("reference")
            || lowered.contains("usage") {
            return "현재 선택된 \(modeLabel(for: selected.kind)) \(selected.label)의 usage, references, callers를 기준으로 분석해줘. \(targetFile.isEmpty ? "" : "파일은 \(targetFile).")"
        }

        if lowered.contains("호출 관계")
            || lowered.contains("호출 흐름")
            || lowered.contains("call graph")
            || lowered.contains("caller")
            || lowered.contains("callee") {
            return "현재 선택된 \(modeLabel(for: selected.kind)) \(selected.label)의 call graph, callers, callees, invocation flow를 중심으로 설명해줘. \(targetFile.isEmpty ? "" : "파일은 \(targetFile).")"
        }

        if lowered.contains("정의")
            || lowered.contains("역할")
            || lowered.contains("무엇")
            || lowered.contains("설명")
            || lowered.contains("어떻게 작동")
            || lowered.contains("what")
            || lowered.contains("explain")
            || lowered.contains("describe") {
            return "현재 선택된 \(modeLabel(for: selected.kind)) \(selected.label)의 definition, responsibilities, key methods를 중심으로 설명해줘. \(targetFile.isEmpty ? "" : "파일은 \(targetFile).")"
        }

        if lowered.contains("보여줘")
            || lowered.contains("열어줘")
            || lowered.contains("show") {
            return "현재 선택된 \(modeLabel(for: selected.kind)) \(selected.label)의 선언부와 핵심 구현을 중심으로 보여줘. \(targetFile.isEmpty ? "" : "파일은 \(targetFile).")"
        }

        return ""
    }

    private func syncExplorationSelection() {
        let items = currentExplorationItems
        guard !items.isEmpty else {
            selectedExplorationItemID = ""
            return
        }
        if items.contains(where: { $0.id == selectedExplorationItemID }) {
            return
        }
        if let preferred = items.first(where: { $0.kind == "class" })
            ?? items.first(where: { $0.kind == "document" })
            ?? items.first(where: { $0.kind == "filename" })
            ?? items.first {
            selectedExplorationItemID = preferred.id
            if preferred.kind == "document" {
                documentExplorationSessionActive = true
            } else {
                sourceExplorationSessionActive = true
            }
        }
    }

    private func documentExplorationIntentSuffix(
        for rawQuery: String,
        selected: MenuExplorationItem
    ) -> String {
        let lowered = rawQuery.lowercased()
        if lowered.contains("요약") || lowered.contains("summary") {
            return "현재 선택된 문서 \(selected.label)의 핵심 내용을 요약해줘."
        }
        if lowered.contains("섹션") || lowered.contains("section") || lowered.contains("부분") {
            return "현재 선택된 문서 \(selected.label)의 관련 섹션과 핵심 문장을 중심으로 설명해줘."
        }
        if lowered.contains("근거") || lowered.contains("출처") || lowered.contains("citation") {
            return "현재 선택된 문서 \(selected.label)의 근거 문장과 출처 중심으로 설명해줘."
        }
        if lowered.contains("보여줘") || lowered.contains("열어줘") {
            return "현재 선택된 문서 \(selected.label)의 관련 부분을 보여줘."
        }
        return "현재 선택된 문서 \(selected.label)을 기준으로 답변해줘."
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
                let fullContent: String
                if let path = response.fullResponsePath, !path.isEmpty,
                   let fileContent = try? String(contentsOfFile: path, encoding: .utf8) {
                    fullContent = fileContent
                } else {
                    fullContent = response.response
                }
                let result = try await bridge.exportDraft(
                    content: fullContent,
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
        case .pauseDetected:
            "말이 끊겼습니다. 이어서 말하면 계속 녹음합니다..."
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
        if !selectedInputDeviceID.isEmpty {
            return selectedInputDeviceName
        }
        // No explicit selection — return nil (use system default)
        return nil
    }

    var phaseStatusText: String {
        switch voiceLoopPhase {
        case .idle:
            return "대기 중"
        case .recording:
            return "녹음 중 \(recordingElapsedLabel) / \(maxRecordingLabel)"
        case .pauseDetected:
            return "⏸ 말이 끊김 — 이어서 말하면 계속 녹음합니다"
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

        // Wire VAD state changes to UI phases
        nativeRecorder.onVadStateChanged = { [weak self] vadState in
            guard let self else { return }
            switch vadState {
            case .listening:
                self.voiceLoopPhase = .recording
                self.errorMessage = nil
            case .tentativeEnd:
                self.voiceLoopPhase = .pauseDetected
            case .confirmedEnd:
                self.voiceLoopPhase = .transcribing
            case .idle:
                break
            }
        }

        // Wire guidance messages
        nativeRecorder.onGuidanceMessage = { [weak self] message in
            self?.errorMessage = message
        }

        // Elapsed time counter
        phaseTransitionTask = Task { [weak self] in
            guard let self else { return }
            let start = Date()
            while !Task.isCancelled {
                recordingElapsedSeconds = Date().timeIntervalSince(start)
                try? await Task.sleep(for: .milliseconds(150))
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
        case .pauseDetected:
            return .yellow
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
        case .pauseDetected:
            return "일시 정지"
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

    private var toneColor: Color {
        let lowered = detail.lowercased()
        if ok {
            if lowered.contains("ready") || lowered.contains("lazy-loaded") {
                return .yellow
            }
            return .green
        }
        if lowered.contains("disabled") || lowered.contains("fts-only") || lowered.contains("not configured") {
            return .orange
        }
        return .red
    }

    private var stateLabel: String {
        let lowered = detail.lowercased()
        if lowered.contains("active") || lowered == "ok" || lowered.hasPrefix("ok ") || lowered.hasPrefix("ok(") {
            return "active"
        }
        if lowered.contains("ready") || lowered.contains("lazy-loaded") {
            return "ready"
        }
        if lowered.contains("disabled") || lowered.contains("fts-only") {
            return "disabled"
        }
        if lowered.contains("not configured") {
            return "optional"
        }
        return ok ? "ok" : "issue"
    }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Circle()
                .fill(toneColor)
                .frame(width: 8, height: 8)
                .padding(.top, 5)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(name)
                        .font(.caption.weight(.semibold))
                    ToneBadge(title: stateLabel, color: toneColor)
                }
                Text(detail)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
    }
}

struct NavigationAssistView: View {
    @ObservedObject var viewModel: JarvisMenuBarViewModel

    private var exploration: MenuExplorationState? {
        viewModel.activeExplorationState
    }

    var body: some View {
        Group {
            if let exploration {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 6) {
                        Text(viewModel.currentInteractionMode == .documentExploration ? "Document Navigator" : "Navigation Window")
                            .font(.headline)
                        Spacer()
                        if !viewModel.navigationPhaseLabel.isEmpty {
                            ToneBadge(title: viewModel.navigationPhaseLabel, color: .blue)
                        }
                        ToneBadge(
                            title: viewModel.currentInteractionMode.title,
                            color: viewModel.currentInteractionMode == .documentExploration ? .orange : .mint
                        )
                    }

                    if !exploration.targetFile.isEmpty {
                        Text("대상 파일: \(exploration.targetFile)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !exploration.targetDocument.isEmpty {
                        Text("대상 문서: \(exploration.targetDocument)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !viewModel.navigationSummaryText.isEmpty {
                        Text(viewModel.navigationSummaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if viewModel.currentExplorationItems.isEmpty {
                        HStack(spacing: 10) {
                            ProgressView()
                                .controlSize(.small)
                            Text("실시간 후보를 찾는 중입니다")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 20)
                    } else {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 8) {
                                if !exploration.documentCandidates.isEmpty {
                                    navigationSection("문서 후보", items: exploration.documentCandidates, tint: .orange)
                                }
                                if !exploration.fileCandidates.isEmpty {
                                    navigationSection("파일 후보", items: exploration.fileCandidates, tint: .mint)
                                }
                                if !exploration.classCandidates.isEmpty {
                                    navigationSection("클래스 후보", items: exploration.classCandidates, tint: .mint)
                                }
                                if !exploration.functionCandidates.isEmpty {
                                    navigationSection("함수 후보", items: exploration.functionCandidates, tint: .mint)
                                }
                            }
                        }
                        .frame(maxHeight: 260)
                    }

                    if let selected = viewModel.currentSelectedExplorationItem,
                       !selected.preview.isEmpty {
                        Divider()
                        Text(selected.label)
                            .font(.caption.weight(.semibold))
                        ScrollView {
                            Text(selected.preview)
                                .font(.system(.caption, design: .monospaced))
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(maxHeight: 150)
                    }

                    Text(viewModel.currentInteractionMode == .documentExploration ? "예: 첫 번째, guide.pdf 문서, 이 문서 요약해줘" : "예: 첫 번째, Pipeline 클래스, 이 클래스 설명해줘")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(14)
                .frame(width: 420)
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.white.opacity(0.16), lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.22), radius: 16, x: 0, y: 12)
            }
        }
        .padding(10)
        .background(Color.clear)
    }

    @ViewBuilder
    private func navigationSection(_ title: String, items: [MenuExplorationItem], tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
            ForEach(items) { item in
                HStack(alignment: .top, spacing: 8) {
                    Text("\(viewModel.candidateNumber(for: item) ?? 0).")
                        .font(.caption.monospacedDigit())
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.label)
                            .font(.caption.weight(.semibold))
                        if !item.path.isEmpty {
                            Text(item.path)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                }
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(viewModel.currentSelectedExplorationItem?.id == item.id ? tint.opacity(0.18) : Color.black.opacity(0.08))
                )
            }
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
        case .pauseDetected:
            return .yellow
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
        var messages: [String] = []

        if health.failedChecks.contains("knowledge_base") {
            messages.append("지식 베이스 폴더가 아직 준비되지 않았습니다.")
        }
        if health.failedChecks.contains("database") {
            messages.append("로컬 데이터베이스 점검이 필요합니다.")
        }
        if health.failedChecks.contains("model") {
            messages.append("생성 모델을 바로 사용할 수 없는 상태입니다.")
        }
        if health.failedChecks.contains("vector_search") || health.failedChecks.contains("vector_db") {
            messages.append("현재는 FTS-only 검색 경로로 동작 중입니다.")
        }
        if health.failedChecks.contains("embeddings") {
            messages.append("임베딩 런타임이 비활성 상태입니다.")
        }
        if health.failedChecks.contains("reranker") {
            messages.append("reranker가 비활성이라 기본 순위로 응답합니다.")
        }

        if messages.isEmpty {
            return "확인이 필요한 항목: \(health.failedChecks.joined(separator: ", "))"
        }
        return messages.joined(separator: " ")
    }

    private func runtimeDetail(_ key: String) -> String {
        viewModel.health?.details[key] ?? "unavailable"
    }

    private func runtimeTone(_ detail: String) -> Color {
        let lowered = detail.lowercased()
        if lowered.contains("active") || lowered == "ok" || lowered.hasPrefix("ok ") || lowered.hasPrefix("ok(") {
            return .green
        }
        if lowered.contains("ready") || lowered.contains("lazy-loaded") {
            return .yellow
        }
        if lowered.contains("disabled") || lowered.contains("fts-only") || lowered.contains("unavailable") {
            return .orange
        }
        return .secondary
    }

    private func runtimeSummaryLabel(_ detail: String) -> String {
        let lowered = detail.lowercased()
        if lowered.contains("active") || lowered == "ok" || lowered.hasPrefix("ok ") || lowered.hasPrefix("ok(") {
            return "active"
        }
        if lowered.contains("ready") || lowered.contains("lazy-loaded") {
            return "ready"
        }
        if lowered.contains("disabled") || lowered.contains("fts-only") || lowered.contains("unavailable") {
            return "disabled"
        }
        return "issue"
    }

    private func humanizedHealthDetail(for key: String, detail: String) -> String {
        switch key {
        case "vector_search":
            if detail.lowercased().contains("fts-only") {
                return "벡터 검색 비활성. 현재는 FTS-only 모드입니다."
            }
        case "embeddings":
            if detail.lowercased().contains("ready") || detail.lowercased().contains("lazy-loaded") {
                return "임베딩 런타임 준비 완료. 첫 질의에서 로드됩니다."
            }
            if detail.lowercased().contains("disabled") {
                return "임베딩 런타임 비활성. semantic 검색이 제한됩니다."
            }
        case "reranker":
            if detail.lowercased().contains("ready") || detail.lowercased().contains("lazy-loaded") {
                return "reranker 준비 완료. 필요 시 지연 로드됩니다."
            }
            if detail.lowercased().contains("disabled") {
                return "reranker 비활성. 기본 검색 순위를 그대로 사용합니다."
            }
        case "knowledge_base":
            if detail == "not configured" {
                return "지식 베이스 경로가 설정되지 않았습니다."
            }
        default:
            break
        }
        return detail
    }

    private func interactionModeColor(_ mode: InteractionMode) -> Color {
        if viewModel.currentInteractionMode == mode {
            switch mode {
            case .generalQuery:
                return .blue
            case .sourceExploration:
                return .mint
            case .documentExploration:
                return .orange
            }
        }
        return .gray
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
                            HStack(spacing: 6) {
                                ForEach(InteractionMode.allCases) { mode in
                                    ToneBadge(
                                        title: mode.title,
                                        color: interactionModeColor(mode)
                                    )
                                }
                            }
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
                                .onChange(of: viewModel.query) { _, newValue in
                                    viewModel.refreshNavigationWindow(for: newValue)
                                }
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

                                if viewModel.isSpeaking {
                                    Button("Stop Voice") {
                                        viewModel.stopTTS()
                                    }
                                }

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
                        // Streaming text display (tokens arriving in real-time)
                        if viewModel.isStreaming && !viewModel.streamingText.isEmpty {
                            ScrollView {
                                Text(viewModel.streamingText)
                                    .font(.body)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .animation(.none, value: viewModel.streamingText)
                            }
                            .frame(minHeight: 100, maxHeight: 340)
                        }

                        if let response = viewModel.response {
                            if let status = response.status {
                                HStack(spacing: 6) {
                                    ToneBadge(title: status.mode, color: .blue)
                                    ToneBadge(title: "safe", color: status.safeMode ? .orange : .gray)
                                    ToneBadge(title: "degraded", color: status.degradedMode ? .orange : .gray)
                                    ToneBadge(title: "write-block", color: status.writeBlocked ? .red : .gray)
                                    ToneBadge(title: viewModel.currentInteractionMode.title, color: interactionModeColor(viewModel.currentInteractionMode))
                                }
                            }

                            ScrollView {
                                VStack(alignment: .leading, spacing: 10) {
                                    Text(response.response)
                                        .font(.body)
                                        .textSelection(.enabled)

                                    HStack(spacing: 8) {
                                        Button("Copy Response") {
                                            viewModel.copyResponse()
                                        }
                                        Button("Export Draft") {
                                            viewModel.requestExport()
                                        }
                                        if viewModel.isSpeaking {
                                            Button("Stop Voice") {
                                                viewModel.stopTTS()
                                            }
                                        }
                                        if let path = response.fullResponsePath, !path.isEmpty {
                                            Button("...more") {
                                                NSWorkspace.shared.open(URL(fileURLWithPath: path))
                                            }
                                            .buttonStyle(.borderless)
                                            .foregroundStyle(.blue)
                                            .font(.caption)
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

                                HStack(spacing: 6) {
                                    ToneBadge(title: "embed \(runtimeSummaryLabel(runtimeDetail("embeddings")))", color: runtimeTone(runtimeDetail("embeddings")))
                                    ToneBadge(title: "vector \(runtimeSummaryLabel(runtimeDetail("vector_search")))", color: runtimeTone(runtimeDetail("vector_search")))
                                    ToneBadge(title: "reranker \(runtimeSummaryLabel(runtimeDetail("reranker")))", color: runtimeTone(runtimeDetail("reranker")))
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
                                            detail: humanizedHealthDetail(
                                                for: key,
                                                detail: health.details[key] ?? ""
                                            )
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

                Divider()

                HStack {
                    Spacer()
                    Button("Quit JARVIS  ⌘Q") {
                        Task { await viewModel.shutdownBridge() }
                        NSApplication.shared.terminate(nil)
                    }
                    .keyboardShortcut("q", modifiers: .command)
                    .controlSize(.small)
                    .foregroundStyle(.secondary)
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
        .overlay {
            if viewModel.showApprovalPanel {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
                    .onTapGesture { viewModel.declineExport() }
                    .overlay {
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
                            if let msg = viewModel.exportMessage {
                                Text(msg)
                                    .font(.caption)
                                    .foregroundStyle(msg.hasPrefix("Exported") ? .green : .secondary)
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
                        .frame(width: 380)
                        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
                        .shadow(radius: 8)
                    }
            }
        }
    }
}


@main
struct JarvisMenuBarApp: App {
    @StateObject private var viewModel: JarvisMenuBarViewModel
    private let navigationPanelController: NavigationPanelController

    init() {
        let model = JarvisMenuBarViewModel()
        _viewModel = StateObject(wrappedValue: model)
        navigationPanelController = NavigationPanelController(viewModel: model)
    }

    var body: some Scene {
        return MenuBarExtra("JARVIS", systemImage: "sparkles.rectangle.stack") {
            JarvisMenuContentView(viewModel: viewModel)
        }
        .menuBarExtraStyle(.window)
        .commands {
            CommandGroup(after: .appInfo) {
                Button("Refresh Navigation Window") {
                    navigationPanelController.refresh()
                }
            }
        }
    }
}
