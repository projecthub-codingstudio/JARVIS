import AppKit
import AudioToolbox
import AVFoundation
import SwiftUI

enum JarvisTheme {
    static let backgroundTop = Color(red: 0.03, green: 0.09, blue: 0.16)
    static let backgroundBottom = Color(red: 0.01, green: 0.03, blue: 0.08)
    static let panel = Color(red: 0.05, green: 0.10, blue: 0.18)
    static let panelRaised = Color(red: 0.08, green: 0.15, blue: 0.25)
    static let panelMuted = Color(red: 0.07, green: 0.12, blue: 0.20)

    static let cyan = Color(red: 0.27, green: 0.88, blue: 1.00)
    static let blue = Color(red: 0.31, green: 0.62, blue: 1.00)
    static let amber = Color(red: 1.00, green: 0.62, blue: 0.25)
    static let green = Color(red: 0.12, green: 0.92, blue: 0.72)
    static let red = Color(red: 1.00, green: 0.36, blue: 0.34)

    static let textPrimary = Color(red: 0.90, green: 0.96, blue: 1.00)
    static let textSecondary = Color(red: 0.60, green: 0.75, blue: 0.88)
    static let textMuted = Color(red: 0.41, green: 0.56, blue: 0.68)

    static let border = cyan.opacity(0.22)
    static let selection = cyan.opacity(0.16)
    static let shadow = Color.black.opacity(0.32)

    static var appBackground: LinearGradient {
        LinearGradient(
            colors: [backgroundTop, backgroundBottom],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    static var panelBackground: LinearGradient {
        LinearGradient(
            colors: [panelRaised.opacity(0.98), panel.opacity(0.94)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

func appLog(_ message: String) {
    fputs("[JarvisMenuBar] \(message)\n", stderr)
}

@MainActor
private final class SpeechSynthDelegateBox: NSObject, AVSpeechSynthesizerDelegate {
    var onFinish: ((Bool) -> Void)?

    private func resolve(_ finishedSpeaking: Bool) {
        guard let onFinish else { return }
        self.onFinish = nil
        onFinish(finishedSpeaking)
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in
            self?.resolve(true)
        }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) {
        Task { @MainActor [weak self] in
            self?.resolve(false)
        }
    }
}

@MainActor
private final class SpeechSynthesisCompletionBox {
    private var continuation: CheckedContinuation<Bool, Never>?
    private var resolvedValue: Bool?

    func install(_ continuation: CheckedContinuation<Bool, Never>) {
        if let resolvedValue {
            continuation.resume(returning: resolvedValue)
            return
        }
        self.continuation = continuation
    }

    func resolve(_ value: Bool) {
        guard resolvedValue == nil else { return }
        resolvedValue = value
        guard let continuation else { return }
        self.continuation = nil
        continuation.resume(returning: value)
    }
}

private enum DirectSpeechLanguage {
    case korean
    case english
}

private struct DirectSpeechUtterance {
    let text: String
    let language: DirectSpeechLanguage
}

private func monotonicSeconds() -> Double {
    Double(DispatchTime.now().uptimeNanoseconds) / 1_000_000_000
}

private func formatElapsed(_ seconds: Double) -> String {
    String(format: "%.2fs", seconds)
}

private let wakePhraseOnlyPattern = try! NSRegularExpression(
    pattern: #"^\s*(?:hey|헤이|해이|에이|하이)\s*(?:자비스(?:야)?|jarvis)\s*$"#,
    options: [.caseInsensitive]
)

private let wakePhrasePrefixPattern = try! NSRegularExpression(
    pattern: #"^\s*(?:hey|헤이|해이|에이|하이)\s*(?:자비스(?:야)?|jarvis)(?:\s+|[,.!]\s*)?(.*)$"#,
    options: [.caseInsensitive]
)

private let exitPhraseOnlyPattern = try! NSRegularExpression(
    pattern: #"^\s*(?:bye|바이)\s*(?:자비스(?:야)?|jarvis)\s*$"#,
    options: [.caseInsensitive]
)

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

enum VoiceLoopPhase: String {
    case idle = "idle"
    case awaitingCommand = "awaiting_command"
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
    private static let wakeWordEnabledDefaultsKey = "wakeWordEnabled"
    private static let knowledgeBaseDirectoryDefaultsKey = "knowledgeBaseDirectoryPath"
    private static let knowledgeBaseBookmarkDefaultsKey = "knowledgeBaseDirectoryBookmark"
    private static let diagnosticsDirectory = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".jarvis", isDirectory: true)
        .appendingPathComponent("diagnostics", isDirectory: true)

    @Published var query = ""
    @Published var isLoading = false {
        didSet { syncGuideRuntimeState() }
    }
    @Published var isStreaming = false {
        didSet { syncGuideRuntimeState() }
    }
    @Published var errorMessage: String?
    @Published var exportMessage: String?
    @Published var sourceExplorationSessionActive = false
    @Published var sourceExplorationFocus: SourceExplorationFocus = .files
    @Published var documentExplorationSessionActive = false
    @Published var documentExplorationFocus: DocumentExplorationFocus = .documents
    @Published var showApprovalPanel = false
    @Published var exportFilename = "jarvis-draft.txt"
    @Published var exportFormat: ExportFormat = .txt
    @Published var exportLocation: ExportLocation = .jarvisExports
    @Published var voiceLoopEnabled = false {
        didSet { syncGuideRuntimeState() }
    }
    @Published var wakeWordEnabled = false {
        didSet {
            syncGuideRuntimeState()
            UserDefaults.standard.set(wakeWordEnabled, forKey: Self.wakeWordEnabledDefaultsKey)
        }
    }
    private var wakeWordSession: WakeWordSession?
    private let wakeWordQueue = DispatchQueue(label: "jarvis.wake.word")
    private var wakeWordTriggerPending = false
    private var wakeAcknowledgementPlayer: AVAudioPlayer?
    private var wakeAcknowledgementProcess: Process?
    private let wakePhraseTranscriber = LiveSpeechTranscriber()
    private var passiveWakeFallbackEnabled = false
    nonisolated(unsafe) private var passiveWakeFallbackSuppressesBridge = false
    private var pendingWakeBufferedQuery: String?
    @Published var voiceLoopPhase: VoiceLoopPhase = .idle {
        didSet { syncGuideRuntimeState() }
    }
    @Published var isSpeaking = false {
        didSet { syncGuideRuntimeState() }
    }
    @Published var lastTranscript = ""
    @Published var health: HealthResponse?
    @Published var healthMessage = "health pending"
    @Published var startupGuidanceMessage: String?
    @Published var knowledgeBaseIndexingInProgress = false
    @Published var knowledgeBaseIndexingMessage = ""
    @Published var consecutiveLoopErrors = 0
    @Published var selectedPanel: MenuPanel = .assistant
    @Published var availableInputDevices: [AudioInputDevice] = []
    @Published var defaultInputDeviceID = ""
    @Published var knowledgeBaseDirectoryPath = ""
    @Published var activeKnowledgeBaseDirectoryPath = ""
    @Published var knowledgeBaseStatusMessage = "지식기반 디렉토리를 설정하세요."
    @Published var bypassEnabled = false
    @Published var bypassStatusMessage = "바이패스 꺼짐"
    @Published var recordingElapsedSeconds = 0.0
    @Published var voiceInputLevel = 0.0
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
            voiceInputLevel = 0
            nativeRecorder.deactivate()
        }
    }
    @Published var inputDeviceStatusMessage = "시스템 기본 입력 장치를 사용합니다."

    private let bridge: any JarvisBackendClient
    private let ttsPrefetchBridge: any JarvisBackendClient
    let guide = JarvisGuideState()
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
    private var queryNormalizationTask: Task<Void, Never>?
    private var partialTranscriptionActive = false
    private var guideTurnPreparedForCurrentRecording = false
    private var pendingClarificationContext: PendingClarificationContext?
    private var submittedQueryForPendingContext: String?
    private var activeKnowledgeBaseSecurityScopeURL: URL?
    private var knowledgeBaseProgressTask: Task<Void, Never>?

    @Published var microphoneReady = false

    init(
        bridge: any JarvisBackendClient = JarvisServiceClient(),
        ttsPrefetchBridge: any JarvisBackendClient = JarvisServiceClient()
    ) {
        self.bridge = bridge
        self.ttsPrefetchBridge = ttsPrefetchBridge
        self.pttDurationSeconds = Double(ProcessInfo.processInfo.environment["JARVIS_PTT_SECONDS"] ?? "20") ?? 20
        self.wakeWordEnabled = UserDefaults.standard.object(forKey: Self.wakeWordEnabledDefaultsKey) as? Bool ?? true
        self.selectedInputDeviceID = UserDefaults.standard.string(forKey: Self.selectedInputDeviceDefaultsKey) ?? ""
        let restoredKnowledgeBaseURL = Self.restoreKnowledgeBaseDirectoryURL()
        let defaultKnowledgeBasePath = restoredKnowledgeBaseURL?.path
            ?? UserDefaults.standard.string(forKey: Self.knowledgeBaseDirectoryDefaultsKey)
            ?? BridgeConfiguration.default().defaultKnowledgeBasePath
        self.knowledgeBaseDirectoryPath = defaultKnowledgeBasePath
        self.activeKnowledgeBaseDirectoryPath = defaultKnowledgeBasePath
        self.knowledgeBaseStatusMessage = "샌드박스 범위: \(defaultKnowledgeBasePath)"
        if let restoredKnowledgeBaseURL {
            activateKnowledgeBaseSecurityScope(for: restoredKnowledgeBaseURL)
        }
        // CoreAudio-based device scan is safe to call synchronously (no blocking)
        refreshAudioInputDevices()
        Task {
            await bridge.updateKnowledgeBasePath(defaultKnowledgeBasePath)
            await ttsPrefetchBridge.updateKnowledgeBasePath(defaultKnowledgeBasePath)
            await bridge.warmup()
            await refreshHealth()
        }

        liveTranscriber.onPartialTranscript = { [weak self] transcript in
            Task { @MainActor [weak self] in
                guard let self, self.partialTranscriptionActive else { return }
                if !self.guideTurnPreparedForCurrentRecording {
                    self.guide.prepareForNewTurn(mode: self.currentInteractionMode)
                    self.guideTurnPreparedForCurrentRecording = true
                }
                self.lastTranscript = transcript
                self.query = Self.compactInputText(transcript)
            }
        }

        wakePhraseTranscriber.onPartialTranscript = { [weak self] transcript in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.handlePassiveWakeTranscript(transcript)
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
        syncGuideRuntimeState()
        prepareWakeAcknowledgementTone()
        if wakeWordEnabled {
            startWakeWord()
        }
    }

    private func startLiveTranscription() {
        partialTranscriptionActive = true
        guideTurnPreparedForCurrentRecording = false
        syncGuideRuntimeState()
        nativeRecorder.onLiveAudioBuffer = { [weak self] buffer in
            self?.liveTranscriber.append(buffer)
        }
        Task { [liveTranscriber] in
            await liveTranscriber.start()
        }
    }

    private func finishLiveTranscription() async -> String {
        partialTranscriptionActive = false
        guideTurnPreparedForCurrentRecording = false
        syncGuideRuntimeState()
        queryNormalizationTask?.cancel()
        nativeRecorder.onLiveAudioBuffer = nil
        return await liveTranscriber.finish()
    }

    private func stopLiveTranscription() {
        partialTranscriptionActive = false
        guideTurnPreparedForCurrentRecording = false
        syncGuideRuntimeState()
        queryNormalizationTask?.cancel()
        nativeRecorder.onLiveAudioBuffer = nil
        liveTranscriber.stop()
    }

    private func syncGuideRuntimeState() {
        guide.updateRuntimeState(
            isLoading: isLoading,
            isStreaming: isStreaming,
            isSpeaking: isSpeaking,
            voiceLoopEnabled: voiceLoopEnabled,
            wakeWordEnabled: wakeWordEnabled,
            partialTranscriptionActive: partialTranscriptionActive,
            ambientStatusText: guideAmbientStatusText
        )
    }

    private var guideAmbientStatusText: String {
        if voiceLoopEnabled {
            return phaseStatusText
        }

        if wakeWordEnabled {
            switch voiceLoopPhase {
            case .idle, .stopped:
                return ""
            case .awaitingCommand:
                return "신호음 후에 새 명령을 말씀해 주세요."
            case .recording, .pauseDetected, .transcribing, .answering, .cooldown:
                return ""
            case .error:
                return errorMessage ?? ""
            }
        }

        return ""
    }

    private func clearGuideForAmbientSession() {
        guide.clear()
        syncGuideRuntimeState()
    }

    private func disarmWakeWordMonitoring() {
        wakeWordTriggerPending = false
        pendingWakeBufferedQuery = nil
        stopPassiveWakeFallback()
        nativeRecorder.onWakeWordAudioChunk = nil
        if let session = wakeWordSession {
            wakeWordQueue.async {
                session.stop()
            }
        }
        wakeWordSession = nil
    }

    private func normalizeLiveQuery(_ rawQuery: String) {
        queryNormalizationTask?.cancel()
        let normalized = Self.compactInputText(rawQuery)
        guard partialTranscriptionActive, lastTranscript == rawQuery else { return }
        query = normalized
    }

    func refreshNavigationWindow(for rawQuery: String, immediate: Bool = false) {
        let trimmed = rawQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        navigationUpdateTask?.cancel()
        guard !trimmed.isEmpty else {
            pendingClarificationContext = nil
            if voiceLoopEnabled {
                clearGuideForAmbientSession()
            } else {
                guide.clear()
            }
            return
        }
        let interactionMode = currentInteractionMode
        if immediate, interactionMode != .generalQuery {
            guide.showLiveEstimate(mode: interactionMode)
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
                    self.guide.applyExploration(nav, mode: interactionMode, immediate: immediate)
                }
            } catch {
                await MainActor.run {
                    self.guide.handleUpdateFailure(immediate: immediate)
                }
            }
        }
    }

    private func keepBestExploration(_ exploration: MenuExplorationState?) {
        guide.keepBestExploration(exploration, fallback: guide.activeExplorationState, mode: currentInteractionMode)
    }

    private func updatePendingClarificationContext(from payload: ServiceAskResponse, rawUserQuery: String) {
        guard let guide = payload.guide,
              guide.loopStage == JarvisGuideLoopStage.waitingUserReply.rawValue else {
            pendingClarificationContext = nil
            submittedQueryForPendingContext = nil
            return
        }
        let context = PendingClarificationContext(
            originalUserQuery: submittedQueryForPendingContext ?? rawUserQuery,
            clarificationPrompt: guide.clarificationPrompt,
            intent: guide.intent,
            skill: guide.skill,
            missingSlots: guide.missingSlots,
            suggestedReplies: guide.suggestedReplies
        )
        pendingClarificationContext = context.isActive ? context : nil
        submittedQueryForPendingContext = nil
    }

    private func consumePendingClarificationAnswer(_ rawQuery: String) -> String? {
        guard let pendingClarificationContext else {
            return nil
        }
        self.pendingClarificationContext = nil
        exportMessage = pendingClarificationContext.clarificationPrompt.isEmpty
            ? "보완 응답을 반영해 다시 처리합니다."
            : "보완 응답 반영: \(pendingClarificationContext.clarificationPrompt)"
        return pendingClarificationContext.mergedQuery(with: rawQuery)
    }

    private func applyResponsePayload(_ payload: ServiceAskResponse, rawUserQuery: String) {
        lastTranscript = rawUserQuery
        let responseText = payload.answer?.text ?? payload.response.response
        guide.presentFinalResponse(responseText, askResponse: payload)
        keepBestExploration(payload.response.exploration)
        updatePendingClarificationContext(from: payload, rawUserQuery: rawUserQuery)
    }

    func pinNavigationPanel() {
        guide.pin()
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
        let trimmed = Self.compactInputText(query)
        guard !trimmed.isEmpty else {
            return
        }
        guard let resolvedQuery = prepareQueryForSubmission(trimmed) else {
            return
        }
        let interactionMode = currentInteractionMode
        guide.prepareForNewTurn(mode: interactionMode)
        submittedQueryForPendingContext = resolvedQuery

        isLoading = true
        isStreaming = true
        errorMessage = nil
        transitionToAnswering()
        startTTSPrefetchIfSupported(for: resolvedQuery)
        Task {
            let stream = await bridge.askStreaming(resolvedQuery)
            for await event in stream {
                switch event {
                case .token(let token):
                    guide.appendStreamingToken(token)
                case .done(let finalResponse):
                    if let finalResponse {
                        applyResponsePayload(finalResponse, rawUserQuery: trimmed)
                    } else if !guide.liveResponseText.isEmpty {
                        pendingClarificationContext = nil
                        guide.presentFinalResponse(guide.liveResponseText)
                    }
                    isStreaming = false
                case .error(let message):
                    appLog("streaming ask failed: \(message)")
                    // Fallback to non-streaming
                    do {
                        let payload = try await bridge.ask(resolvedQuery)
                        applyResponsePayload(payload, rawUserQuery: trimmed)
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
            if !guide.audibleResponseText.isEmpty {
                speakResponse(guide.audibleResponseText)
            }
            if !voiceLoopEnabled {
                cancelPhaseTransition()
                voiceLoopPhase = .idle
            }
        }
    }

    func recordOnce() {
        Task {
            do {
                let turnStart = monotonicSeconds()
                isLoading = true
                errorMessage = nil
                beginRecordingPhase()
                // Step 1: Native recording via AVCaptureDevice (no ffmpeg)
                let deviceID = selectedInputDeviceID.isEmpty ? nil : selectedInputDeviceID
                startLiveTranscription()
                let recordingStart = monotonicSeconds()
                let audioURL = try await nativeRecorder.record(
                    deviceID: deviceID,
                    duration: pttDurationSeconds
                )
                let liveTranscript = await finishLiveTranscription()
                appLog("Recording done in \(formatElapsed(monotonicSeconds() - recordingStart)): \(audioURL.path)")

                cancelPhaseTransition()
                voiceLoopPhase = .transcribing

                // Step 2: Transcribe via Python whisper-cli
                let transcriptionStart = monotonicSeconds()
                let transcriptText: String
                let transcriptSource: String
                if !liveTranscript.isEmpty {
                    transcriptText = liveTranscript
                    transcriptSource = "live"
                } else {
                    appLog("Live transcription unavailable; falling back to whisper-cli")
                    let transcript = try await bridge.transcribeFile(audioPath: audioURL.path)
                    transcriptText = transcript.transcript
                    transcriptSource = "whisper"
                }
                let repairedTranscript = try await repairTranscriptForSubmission(transcriptText)
                appLog("Transcription ready in \(formatElapsed(monotonicSeconds() - transcriptionStart)) [\(transcriptSource)]: \(Self.logPreview(for: repairedTranscript.displayText))")
                lastTranscript = repairedTranscript.rawText
                query = repairedTranscript.displayText
                refreshNavigationWindow(for: repairedTranscript.displayText)
                guard let resolvedQuery = prepareQueryForSubmission(repairedTranscript.finalQuery) else {
                    isLoading = false
                    if !voiceLoopEnabled {
                        cancelPhaseTransition()
                        voiceLoopPhase = .idle
                    }
                    return
                }

                // Step 3: Search + Answer via Python LLM
                guide.prepareForNewTurn(mode: currentInteractionMode)
                voiceLoopPhase = .answering
                submittedQueryForPendingContext = resolvedQuery
                let answerStart = monotonicSeconds()
                startTTSPrefetchIfSupported(for: resolvedQuery)
                let payload = try await bridge.ask(resolvedQuery)
                appLog("Answer ready in \(formatElapsed(monotonicSeconds() - answerStart)) / total \(formatElapsed(monotonicSeconds() - turnStart))")
                applyResponsePayload(payload, rawUserQuery: repairedTranscript.displayText)
                exportMessage = nil

                // Step 4: TTS — speak the response
                speakResponse(guide.audibleResponseText)
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

    private func runWakeWordTurn() async {
        do {
            let turnStart = monotonicSeconds()
            isLoading = true
            errorMessage = nil
            beginRecordingPhase()

            let deviceID = selectedInputDeviceID.isEmpty ? nil : selectedInputDeviceID
            startLiveTranscription()
            let recordingStart = monotonicSeconds()
            let audioURL = try await nativeRecorder.record(
                deviceID: deviceID,
                duration: pttDurationSeconds
            )
            let liveTranscript = await finishLiveTranscription()
            appLog("Wake recording done in \(formatElapsed(monotonicSeconds() - recordingStart)): \(audioURL.path)")

            cancelPhaseTransition()
            voiceLoopPhase = .transcribing

            let transcriptText: String
            let transcriptSource: String
            if !liveTranscript.isEmpty {
                transcriptText = liveTranscript
                transcriptSource = "live"
            } else {
                appLog("Wake live transcription unavailable; falling back to whisper-cli")
                let transcript = try await bridge.transcribeFile(audioPath: audioURL.path)
                transcriptText = transcript.transcript
                transcriptSource = "whisper"
            }

            let repairedTranscript = resolvedWakeCommand(
                from: try await repairTranscriptForSubmission(transcriptText)
            )
            appLog(
                "Wake transcription ready in \(formatElapsed(monotonicSeconds() - recordingStart)) [\(transcriptSource)]: \(Self.logPreview(for: repairedTranscript.displayText))"
            )
            lastTranscript = repairedTranscript.rawText
            query = repairedTranscript.displayText
            refreshNavigationWindow(for: repairedTranscript.displayText)
            guard let resolvedQuery = prepareQueryForSubmission(repairedTranscript.finalQuery) else {
                isLoading = false
                cancelPhaseTransition()
                voiceLoopPhase = .idle
                return
            }

            guide.prepareForNewTurn(mode: currentInteractionMode)
            voiceLoopPhase = .answering
            submittedQueryForPendingContext = resolvedQuery
            startTTSPrefetchIfSupported(for: resolvedQuery)
            let answerStart = monotonicSeconds()
            let payload = try await bridge.ask(resolvedQuery)
            appLog(
                "Wake answer ready in \(formatElapsed(monotonicSeconds() - answerStart)) / total \(formatElapsed(monotonicSeconds() - turnStart))"
            )
            applyResponsePayload(payload, rawUserQuery: repairedTranscript.displayText)
            exportMessage = nil
            isLoading = false

            speakResponse(guide.audibleResponseText)
            await waitForSpeechPlaybackToFinish()
            cancelPhaseTransition()
            voiceLoopPhase = .idle
        } catch {
            stopLiveTranscription()
            pendingWakeBufferedQuery = nil
            if Task.isCancelled {
                return
            }
            appLog("wake word interaction failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
            isLoading = false
            cancelPhaseTransition()
            voiceLoopPhase = .error
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
        guard !voiceLoopEnabled else {
            wakeWordEnabled = true
            return
        }
        guard wakeWordSession == nil else {
            wakeWordEnabled = true
            return
        }
        wakeWordEnabled = true
        wakeWordTriggerPending = false
        pendingWakeBufferedQuery = nil
        errorMessage = nil
        exportMessage = "헤이 자비스 대기 중"
        voiceLoopPhase = .idle
        appLog("Wake word mode active — waiting for 'Hey JARVIS'")

        Task { [weak self] in
            guard let self else { return }
            let granted = await AVCaptureDevice.requestAccess(for: .audio)
            guard granted else {
                self.wakeWordEnabled = false
                self.errorMessage = "마이크 권한이 거부되었습니다. 시스템 설정에서 허용해 주세요."
                return
            }

            do {
                let session = try await self.bridge.startWakeWordSession()
                let deviceID = self.selectedInputDeviceID.isEmpty ? nil : self.selectedInputDeviceID
                try self.nativeRecorder.activate(deviceID: deviceID)
                self.microphoneReady = true
                self.wakeWordSession = session
                await self.startPassiveWakeFallbackIfAvailable()
                self.nativeRecorder.onWakeWordAudioChunk = { [weak self, session] pcmData in
                    guard let self else { return }
                    self.wakeWordQueue.async {
                        guard !self.passiveWakeFallbackSuppressesBridge else { return }
                        guard session.sendAudioChunk(pcmData) else { return }
                        Task { @MainActor [weak self] in
                            guard let self, self.wakeWordEnabled, !self.wakeWordTriggerPending else { return }
                            self.wakeWordTriggerPending = true
                            await self.handleWakeWordDetected()
                        }
                    }
                }
            } catch {
                self.nativeRecorder.onWakeWordAudioChunk = nil
                self.wakeWordSession = nil
                self.wakeWordEnabled = false
                self.errorMessage = "wake word 시작 실패: \(error.localizedDescription)"
                appLog("Wake word start failed: \(error.localizedDescription)")
            }
        }
    }

    private func handleWakeWordDetected() async {
        guard wakeWordEnabled, !voiceLoopEnabled else {
            wakeWordTriggerPending = false
            return
        }

        pendingWakeBufferedQuery = nil
        appLog("Wake word detected — waiting for a fresh post-chime command")
        exportMessage = "헤이 자비스 감지됨 · 신호음 후 명령을 말씀해 주세요"
        stopPassiveWakeFallback()
        stopTTS()
        cancelPhaseTransition()
        voiceLoopPhase = .awaitingCommand
        playWakeAcknowledgementTone()

        do {
            try? await Task.sleep(for: .milliseconds(260))
            let readyForFreshCommand = await nativeRecorder.waitForWakeCommandGap(
                requiredSilence: 0.35,
                timeout: 2.4
            )
            guard readyForFreshCommand else {
                appLog("Wake word follow-up ignored: no silence gap after acknowledgement")
                exportMessage = "연속 발화는 실행하지 않습니다. 신호음 후 다시 말씀해 주세요."
                cancelPhaseTransition()
                voiceLoopPhase = .idle
                return
            }
            exportMessage = "듣고 있습니다"
            startVoiceLoop()
        }

        if wakeWordEnabled && !voiceLoopEnabled {
            await startPassiveWakeFallbackIfAvailable()
        }
        wakeWordTriggerPending = false
    }

    private func handlePassiveWakeTranscript(_ transcript: String) {
        guard wakeWordEnabled, !voiceLoopEnabled else { return }
        guard passiveWakeFallbackEnabled else { return }

        let compact = Self.compactInputText(transcript)
        guard !compact.isEmpty else { return }
        guard Self.isWakePhraseOnly(compact) else {
            if let wakeRemainder = Self.wakePhraseRemainder(in: compact), !wakeRemainder.isEmpty {
                pendingWakeBufferedQuery = nil
                appLog("Ignored inline wake command until post-chime utterance: \(Self.logPreview(for: wakeRemainder))")
            }
            return
        }

        appLog("Passive wake transcript matched exact wake phrase: \(Self.logPreview(for: compact))")
        guard !wakeWordTriggerPending else { return }
        wakeWordTriggerPending = true
        Task { [weak self] in
            await self?.handleWakeWordDetected()
        }
    }

    private func startPassiveWakeFallbackIfAvailable() async {
        guard wakeWordEnabled else { return }
        guard !passiveWakeFallbackEnabled else { return }
        let transcriber = wakePhraseTranscriber
        let authorized = await transcriber.requestAuthorizationIfNeeded()
        guard authorized else {
            passiveWakeFallbackEnabled = false
            passiveWakeFallbackSuppressesBridge = false
            nativeRecorder.onPassiveWakeAudioBuffer = nil
            appLog("Passive wake fallback unavailable: speech authorization denied")
            return
        }
        passiveWakeFallbackEnabled = true
        passiveWakeFallbackSuppressesBridge = true
        nativeRecorder.onPassiveWakeAudioBuffer = { [transcriber] buffer in
            transcriber.append(buffer)
        }
        await transcriber.start()
        appLog("Passive wake fallback started")
    }

    private func stopPassiveWakeFallback() {
        passiveWakeFallbackEnabled = false
        passiveWakeFallbackSuppressesBridge = false
        nativeRecorder.onPassiveWakeAudioBuffer = nil
        wakePhraseTranscriber.stop()
        appLog("Passive wake fallback stopped")
    }

    private func prepareWakeAcknowledgementTone() {
        guard wakeAcknowledgementPlayer == nil else { return }
        do {
            let soundURL = URL(fileURLWithPath: "/System/Library/Sounds/Glass.aiff")
            let player = try AVAudioPlayer(contentsOf: soundURL)
            player.volume = 1.0
            player.prepareToPlay()
            wakeAcknowledgementPlayer = player
            appLog("Wake acknowledgement sound loaded")
        } catch {
            appLog("Wake acknowledgement sound preload failed: \(error.localizedDescription)")
        }
    }

    private func playWakeAcknowledgementTone() {
        AudioServicesPlayAlertSound(kSystemSoundID_UserPreferredAlert)
        NSSound.beep()

        do {
            if let existing = wakeAcknowledgementProcess, existing.isRunning {
                existing.terminate()
            }
            let process = Process()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/afplay")
            process.arguments = ["/System/Library/Sounds/Glass.aiff"]
            try process.run()
            wakeAcknowledgementProcess = process
            appLog("Wake acknowledgement tone played via afplay")
            return
        } catch {
            appLog("Wake acknowledgement afplay fallback failed: \(error.localizedDescription)")
        }

        do {
            let player: AVAudioPlayer
            if let wakeAcknowledgementPlayer {
                player = wakeAcknowledgementPlayer
            } else {
                let soundURL = URL(fileURLWithPath: "/System/Library/Sounds/Glass.aiff")
                let loadedPlayer = try AVAudioPlayer(contentsOf: soundURL)
                loadedPlayer.volume = 1.0
                loadedPlayer.prepareToPlay()
                wakeAcknowledgementPlayer = loadedPlayer
                player = loadedPlayer
                appLog("Wake acknowledgement sound loaded on demand")
            }

            if player.isPlaying {
                player.stop()
            }
            player.currentTime = 0
            guard player.play() else {
                throw NSError(
                    domain: "JarvisMenuBar",
                    code: 7,
                    userInfo: [NSLocalizedDescriptionKey: "wake acknowledgement tone playback failed"]
                )
            }
            appLog("Wake acknowledgement tone played")
        } catch {
            appLog("Wake acknowledgement AVAudioPlayer fallback failed: \(error.localizedDescription)")
            NSSound.beep()
        }
    }

    // MARK: - TTS Playback

    private var audioPlayer: AVAudioPlayer?
    private var speechSynthesizer: AVSpeechSynthesizer?
    private var speechSynthDelegateBox: SpeechSynthDelegateBox?

    private func dismissGuideAfterSpeechIfNeeded() {
        guard !guide.hasClarification else { return }
        guard !guide.autoCloseDisabled else { return }
        guard !guide.finalResponseText.isEmpty else { return }
        clearTransientVoiceUIState()
        if voiceLoopEnabled {
            clearGuideForAmbientSession()
            return
        }
        guide.clear()
    }

    func closeGuidePanel() {
        stopTTS()
        clearTransientVoiceUIState()
        pendingClarificationContext = nil
        endGuideWorkspaceSession()
        if voiceLoopEnabled {
            clearGuideForAmbientSession()
            return
        }
        guide.clear()
    }

    func activateGuideWorkspaceSession(_ sessionID: String) {
        guide.activateWorkspaceSession(sessionID)
    }

    func closeGuideWorkspaceSession(_ sessionID: String) {
        guide.closeWorkspaceSession(sessionID)
        if !guide.hasWorkspaceSessions {
            endGuideWorkspaceSession()
        }
    }

    private func endGuideWorkspaceSession() {
        sourceExplorationSessionActive = false
        sourceExplorationFocus = .files
        documentExplorationSessionActive = false
        documentExplorationFocus = .documents
        guide.selectedExplorationItemID = ""
    }

    private func clearTransientVoiceUIState() {
        queryNormalizationTask?.cancel()
        navigationUpdateTask?.cancel()
        submittedQueryForPendingContext = nil
        query = ""
        if !partialTranscriptionActive && !voiceLoopEnabled && !wakeWordEnabled {
            lastTranscript = ""
        }
    }

    func toggleGuideAutoClose() {
        guide.toggleAutoCloseDisabled()
    }

    /// Speak response text via the Python bridge so menu bar playback uses the
    /// same persona-aware TTS path as the core runtime.
    func speakResponse(_ text: String) {
        let stripped = Self.stripForTTS(text)
        guard !stripped.isEmpty else { return }
        let segments = Self.ttsSegments(for: stripped)

        stopTTS()
        isSpeaking = true
        let ttsStart = monotonicSeconds()
        appLog("TTS source text (\(stripped.count) chars): \(Self.logPreview(for: stripped))")

        let playbackTask = Task(priority: .userInitiated) { [weak self] in
            guard let self else { return }
            do {
                appLog("TTS request started")
                let completed: Bool
                if configuredTTSBackend() == "say" {
                    let directUtterances = Self.directSpeechUtterances(for: segments)
                    completed = try await self.playDirectSpeechUtterances(directUtterances)
                } else if segments.count > 1 {
                    completed = try await self.playSegmentedSpeech(
                        segments,
                        overallStart: ttsStart
                    )
                } else {
                    let speech = try await self.bridge.synthesizeSpeech(text: stripped)
                    completed = try await self.playSpeechFile(
                        speech,
                        startedAt: ttsStart,
                        segmentLabel: nil
                    )
                }
                await MainActor.run {
                    self.isSpeaking = false
                    if completed {
                        self.dismissGuideAfterSpeechIfNeeded()
                    }
                }
                if completed {
                    appLog("TTS playback finished")
                }
            } catch is CancellationError {
                await MainActor.run {
                    self.audioPlayer?.stop()
                    self.audioPlayer = nil
                    self.isSpeaking = false
                }
                appLog("TTS playback cancelled")
            } catch {
                appLog("TTS failed: \(error.localizedDescription)")
                await MainActor.run {
                    self.audioPlayer?.stop()
                    self.audioPlayer = nil
                    self.isSpeaking = false
                }
            }
        }
        ttsPlaybackTask = playbackTask
    }

    @MainActor
    private func directSpeechVoice(
        for text: String,
        preferredLanguage: DirectSpeechLanguage? = nil
    ) -> AVSpeechSynthesisVoice? {
        let env = ProcessInfo.processInfo.environment
        let language = preferredLanguage ?? Self.dominantDirectSpeechLanguage(for: text)
        let exactOverride: String = {
            let scopedKey = language == .korean ? "JARVIS_TTS_VOICE_KO" : "JARVIS_TTS_VOICE_EN"
            let scoped = env[scopedKey]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !scoped.isEmpty {
                return scoped
            }
            return env["JARVIS_TTS_VOICE"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        }()

        let voices = AVSpeechSynthesisVoice.speechVoices()

        func voiceEntries() -> [(id: String, name: String, language: String)] {
            voices.compactMap { identifier in
                let trimmedName = identifier.name.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !trimmedName.isEmpty else {
                    return nil
                }
                return (identifier.identifier, trimmedName, identifier.language)
            }
        }

        let entries = voiceEntries()

        func resolveExact(_ targetName: String) -> AVSpeechSynthesisVoice? {
            let normalizedTarget = targetName.trimmingCharacters(in: .whitespacesAndNewlines)
            for entry in entries where entry.name == normalizedTarget || entry.id == normalizedTarget {
                return AVSpeechSynthesisVoice(identifier: entry.id)
            }
            return nil
        }

        func resolveContaining(_ candidates: [String]) -> AVSpeechSynthesisVoice? {
            let normalizedCandidates = candidates.map { $0.lowercased() }
            for entry in entries {
                let loweredName = entry.name.lowercased()
                let loweredLanguage = entry.language.lowercased()
                if normalizedCandidates.contains(where: { loweredName.contains($0) || loweredLanguage.contains($0) }) {
                    return AVSpeechSynthesisVoice(identifier: entry.id)
                }
            }
            return nil
        }

        if !exactOverride.isEmpty, let identifier = resolveExact(exactOverride) {
            return identifier
        }

        let exactCandidates: [String]
        let partialCandidates: [String]
        switch language {
        case .korean:
            exactCandidates = ["Yuna (Premium)", "Yuna", "Reed (한국어(대한민국))"]
            partialCandidates = ["yuna", "유나", "한국어", "korean", "ko_", "ko-", "ko-kr", "대한민국", "reed"]
        case .english:
            exactCandidates = [
                "Samantha",
                "Shelley (영어(미국))",
                "Sandy (영어(미국))",
                "Flo (영어(미국))",
                "Karen",
                "Moira",
                "Tessa",
                "Sandy (영어(영국))",
                "Shelley (영어(영국))",
            ]
            partialCandidates = [
                "samantha",
                "shelley",
                "sandy",
                "flo",
                "karen",
                "moira",
                "tessa",
                "영어",
                "english",
                "en_",
                "en-",
                "en-us",
                "en-gb",
            ]
        }

        for candidate in exactCandidates {
            if let identifier = resolveExact(candidate) {
                return identifier
            }
        }
        return resolveContaining(partialCandidates)
    }

    @MainActor
    private func playDirectSpeech(
        _ text: String,
        preferredLanguage: DirectSpeechLanguage? = nil
    ) async -> Bool {
        let synthesizer = AVSpeechSynthesizer()
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = directSpeechVoice(for: text, preferredLanguage: preferredLanguage)
        utterance.rate = 0.52
        let completion = SpeechSynthesisCompletionBox()

        return await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                let delegate = SpeechSynthDelegateBox()
                delegate.onFinish = { [weak self, weak synthesizer] finishedSpeaking in
                    Task { @MainActor [weak self] in
                        completion.resolve(finishedSpeaking)
                        guard let self else { return }
                        if self.speechSynthesizer === synthesizer {
                            self.clearDirectSpeechPlaybackState()
                        }
                    }
                }

                completion.install(continuation)
                self.speechSynthDelegateBox = delegate
                self.speechSynthesizer = synthesizer
                synthesizer.delegate = delegate
                synthesizer.speak(utterance)
                appLog("TTS direct playback started")
            }
        } onCancel: { [weak self] in
            Task { @MainActor [weak self] in
                completion.resolve(false)
                self?.speechSynthesizer?.stopSpeaking(at: .immediate)
                self?.clearDirectSpeechPlaybackState()
            }
        }
    }

    @MainActor
    private func playDirectSpeechUtterances(_ utterances: [DirectSpeechUtterance]) async throws -> Bool {
        let normalizedUtterances = utterances.filter {
            !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        guard !normalizedUtterances.isEmpty else { return false }

        for utterance in normalizedUtterances {
            try Task.checkCancellation()
            appLog("TTS direct segment [\(utterance.language == .english ? "en" : "ko")]: \(Self.logPreview(for: utterance.text))")
            let finished = await playDirectSpeech(
                utterance.text,
                preferredLanguage: utterance.language
            )
            try Task.checkCancellation()
            guard finished else { return false }
        }
        return true
    }

    /// Normalize lightweight formatting before TTS.
    /// Backend should provide spoken text; this only removes presentation markup.
    static func sanitizeRecognizedQuery(_ text: String) -> String {
        compactInputText(text)
    }

    static func compactInputText(_ text: String) -> String {
        text
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    static func logPreview(for text: String, limit: Int = 96) -> String {
        let compact = text
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard compact.count > limit else { return compact }
        let endIndex = compact.index(compact.startIndex, offsetBy: limit)
        return String(compact[..<endIndex]) + "..."
    }

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

        let lines = result.components(separatedBy: "\n")
        var kept: [String] = []
        for line in lines {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty { continue }
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

    static func ttsSegments(for text: String) -> [String] {
        let parts = text
            .components(separatedBy: " / ")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? [] : parts
    }

    private static func directSpeechUtterances(for segments: [String]) -> [DirectSpeechUtterance] {
        var utterances: [DirectSpeechUtterance] = []
        for segment in segments {
            let normalized = segment.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !normalized.isEmpty else { continue }
            let chunked = directSpeechUtterances(for: normalized)
            if chunked.isEmpty {
                utterances.append(
                    DirectSpeechUtterance(
                        text: normalized,
                        language: dominantDirectSpeechLanguage(for: normalized)
                    )
                )
            } else {
                utterances.append(contentsOf: chunked)
            }
        }
        return utterances
    }

    private static func directSpeechUtterances(for text: String) -> [DirectSpeechUtterance] {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return [] }

        var utterances: [DirectSpeechUtterance] = []
        var currentLanguage: DirectSpeechLanguage?
        var currentText = ""
        var pendingNeutral = ""

        func appendCurrent() {
            guard let currentLanguage else { return }
            let combined = (currentText + pendingNeutral).trimmingCharacters(in: .whitespacesAndNewlines)
            pendingNeutral = ""
            currentText = ""
            guard !combined.isEmpty else { return }
            if let last = utterances.last, last.language == currentLanguage {
                utterances[utterances.count - 1] = DirectSpeechUtterance(
                    text: last.text + " " + combined,
                    language: currentLanguage
                )
            } else {
                utterances.append(DirectSpeechUtterance(text: combined, language: currentLanguage))
            }
        }

        for character in trimmed {
            switch directSpeechCharacterCategory(for: character) {
            case .english:
                if currentLanguage == .english || currentLanguage == nil {
                    currentText += pendingNeutral + String(character)
                    pendingNeutral = ""
                    currentLanguage = .english
                } else {
                    appendCurrent()
                    currentLanguage = .english
                    currentText = String(character)
                }
            case .korean:
                if currentLanguage == .korean || currentLanguage == nil {
                    currentText += pendingNeutral + String(character)
                    pendingNeutral = ""
                    currentLanguage = .korean
                } else {
                    appendCurrent()
                    currentLanguage = .korean
                    currentText = String(character)
                }
            case .neutral:
                if currentLanguage == nil {
                    currentText += String(character)
                } else {
                    pendingNeutral += String(character)
                }
            }
        }

        appendCurrent()
        let fallback = DirectSpeechUtterance(
            text: trimmed,
            language: dominantDirectSpeechLanguage(for: trimmed)
        )
        if utterances.isEmpty {
            return [fallback]
        }
        if shouldPreferSingleDirectSpeechUtterance(for: trimmed, utterances: utterances) {
            return [fallback]
        }
        return utterances
    }

    private enum DirectSpeechCharacterCategory {
        case korean
        case english
        case neutral
    }

    private static func directSpeechCharacterCategory(for character: Character) -> DirectSpeechCharacterCategory {
        let scalarValues = character.unicodeScalars.map(\.value)
        if scalarValues.contains(where: { (0xAC00...0xD7A3).contains($0) || (0x3131...0x318E).contains($0) }) {
            return .korean
        }
        if scalarValues.contains(where: { (0x0041...0x005A).contains($0) || (0x0061...0x007A).contains($0) }) {
            return .english
        }
        return .neutral
    }

    private static func dominantDirectSpeechLanguage(for text: String) -> DirectSpeechLanguage {
        let counts = directSpeechLanguageCounts(for: text)
        return counts.english > counts.korean ? .english : .korean
    }

    private static func shouldPreferSingleDirectSpeechUtterance(
        for text: String,
        utterances: [DirectSpeechUtterance]
    ) -> Bool {
        guard utterances.count > 1 else { return false }
        let dominantLanguage = dominantDirectSpeechLanguage(for: text)
        let counts = directSpeechLanguageCounts(for: text)
        let dominantCount = dominantLanguage == .english ? counts.english : counts.korean
        let secondaryCount = dominantLanguage == .english ? counts.korean : counts.english

        guard dominantCount > 0 else { return true }
        if utterances.count > 2 {
            return true
        }
        if secondaryCount < 12 {
            return true
        }
        if Double(secondaryCount) / Double(max(1, dominantCount + secondaryCount)) < 0.35 {
            return true
        }

        let longestSecondaryRun = utterances
            .filter { $0.language != dominantLanguage }
            .map { directSpeechContentLength(for: $0.text) }
            .max() ?? 0
        return longestSecondaryRun < 10
    }

    private static func directSpeechLanguageCounts(for text: String) -> (korean: Int, english: Int) {
        var koreanScore = 0
        var englishScore = 0
        for character in text {
            switch directSpeechCharacterCategory(for: character) {
            case .korean:
                koreanScore += 1
            case .english:
                englishScore += 1
            case .neutral:
                continue
            }
        }
        return (korean: koreanScore, english: englishScore)
    }

    private static func directSpeechContentLength(for text: String) -> Int {
        text.reduce(into: 0) { count, character in
            if directSpeechCharacterCategory(for: character) != .neutral {
                count += 1
            }
        }
    }

    private func playSegmentedSpeech(
        _ segments: [String],
        overallStart: Double
    ) async throws -> Bool {
        var speeches: [SpeechResponse] = []
        speeches.reserveCapacity(segments.count)

        for (index, segment) in segments.enumerated() {
            let speech = try await bridge.synthesizeSpeech(text: segment)
            speeches.append(speech)
            try logSpeechReady(
                speech,
                startedAt: overallStart,
                segmentLabel: "\(index + 1)/\(segments.count)"
            )
        }

        let stitchedSpeech = try stitchSpeechFiles(speeches, startedAt: overallStart)
        return try await playSpeechFile(
            stitchedSpeech,
            startedAt: overallStart,
            segmentLabel: nil
        )
    }

    private func logSpeechReady(
        _ speech: SpeechResponse,
        startedAt: Double,
        segmentLabel: String?
    ) throws {
        let audioURL = URL(fileURLWithPath: speech.audioPath)
        let attributes = try FileManager.default.attributesOfItem(atPath: audioURL.path)
        let fileSize = (attributes[.size] as? NSNumber)?.intValue ?? 0
        if let segmentLabel {
            appLog("TTS segment \(segmentLabel) ready in \(formatElapsed(monotonicSeconds() - startedAt)): \(audioURL.path) (\(fileSize) bytes)")
        } else {
            appLog("TTS file ready in \(formatElapsed(monotonicSeconds() - startedAt)): \(audioURL.path) (\(fileSize) bytes)")
        }
    }

    private func stitchSpeechFiles(
        _ speeches: [SpeechResponse],
        startedAt: Double
    ) throws -> SpeechResponse {
        guard let firstSpeech = speeches.first else {
            throw NSError(
                domain: "JarvisMenuBar",
                code: 3,
                userInfo: [NSLocalizedDescriptionKey: "이어붙일 음성 파일이 없습니다."]
            )
        }
        if speeches.count == 1 {
            try logSpeechReady(firstSpeech, startedAt: startedAt, segmentLabel: nil)
            return firstSpeech
        }

        let outputDirectory = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("jarvis_tts", isDirectory: true)
        try FileManager.default.createDirectory(
            at: outputDirectory,
            withIntermediateDirectories: true
        )
        let stitchedURL = outputDirectory.appendingPathComponent(
            "speech_stitched_\(UUID().uuidString).aiff"
        )

        let firstURL = URL(fileURLWithPath: firstSpeech.audioPath)
        let firstFile = try AVAudioFile(forReading: firstURL)
        let outputFile = try AVAudioFile(
            forWriting: stitchedURL,
            settings: firstFile.fileFormat.settings,
            commonFormat: firstFile.processingFormat.commonFormat,
            interleaved: firstFile.processingFormat.isInterleaved
        )

        for speech in speeches {
            let inputURL = URL(fileURLWithPath: speech.audioPath)
            let inputFile = try AVAudioFile(forReading: inputURL)
            let inputFormat = inputFile.processingFormat
            let referenceFormat = firstFile.processingFormat
            guard inputFormat.sampleRate == referenceFormat.sampleRate,
                  inputFormat.channelCount == referenceFormat.channelCount,
                  inputFormat.commonFormat == referenceFormat.commonFormat,
                  inputFormat.isInterleaved == referenceFormat.isInterleaved else {
                throw NSError(
                    domain: "JarvisMenuBar",
                    code: 4,
                    userInfo: [NSLocalizedDescriptionKey: "세그먼트 음성 포맷이 서로 달라 이어붙일 수 없습니다."]
                )
            }

            while true {
                guard let buffer = AVAudioPCMBuffer(
                    pcmFormat: inputFormat,
                    frameCapacity: 4096
                ) else {
                    throw NSError(
                        domain: "JarvisMenuBar",
                        code: 5,
                        userInfo: [NSLocalizedDescriptionKey: "오디오 버퍼를 생성할 수 없습니다."]
                    )
                }
                try inputFile.read(into: buffer)
                if buffer.frameLength == 0 {
                    break
                }
                try outputFile.write(from: buffer)
            }
        }

        let stitchedSpeech = SpeechResponse(audioPath: stitchedURL.path)
        try logSpeechReady(stitchedSpeech, startedAt: startedAt, segmentLabel: nil)
        return stitchedSpeech
    }

    private func playSpeechFile(
        _ speech: SpeechResponse,
        startedAt: Double,
        segmentLabel: String?
    ) async throws -> Bool {
        try Task.checkCancellation()
        let audioURL = URL(fileURLWithPath: speech.audioPath)

        if segmentLabel != nil {
            try logSpeechReady(speech, startedAt: startedAt, segmentLabel: segmentLabel)
        } else if !speech.audioPath.contains("speech_stitched_") {
            try logSpeechReady(speech, startedAt: startedAt, segmentLabel: nil)
        }

        let player = try AVAudioPlayer(contentsOf: audioURL)
        player.prepareToPlay()
        guard player.play() else {
            throw NSError(
                domain: "JarvisMenuBar",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "AVAudioPlayer가 재생을 시작하지 못했습니다."]
            )
        }
        await MainActor.run {
            self.audioPlayer = player
        }
        appLog("TTS playback started")

        while !Task.isCancelled {
            let stillPlaying = await MainActor.run {
                self.audioPlayer === player && player.isPlaying
            }
            if !stillPlaying {
                break
            }
            try? await Task.sleep(for: .milliseconds(150))
        }

        let completed = await MainActor.run {
            let finished = self.audioPlayer === player && !player.isPlaying
            if self.audioPlayer === player {
                self.audioPlayer = nil
            }
            return finished
        }
        return completed
    }

    /// Stop any currently playing TTS.
    func stopTTS() {
        ttsPlaybackTask?.cancel()
        ttsPlaybackTask = nil
        audioPlayer?.stop()
        audioPlayer = nil
        speechSynthesizer?.stopSpeaking(at: .immediate)
        isSpeaking = false
        voiceInputLevel = 0
    }

    @MainActor
    private func clearDirectSpeechPlaybackState() {
        speechSynthesizer = nil
        speechSynthDelegateBox = nil
    }

    private func waitForSpeechPlaybackToFinish() async {
        while isSpeaking {
            try? await Task.sleep(for: .milliseconds(150))
            if Task.isCancelled {
                break
            }
        }
    }

    private func stopWakeWord() {
        wakeWordEnabled = false
        if voiceLoopEnabled {
            stopVoiceLoop(resumeWakeWord: false)
        }
        disarmWakeWordMonitoring()
        stopTTS()
        voiceLoopPhase = .idle
        exportMessage = nil
        appLog("Wake word mode stopped")
    }

    func shutdownBridge() async {
        await bridge.shutdown()
    }

    func refreshHealth() async {
        let runtimeState = await bridge.runtimeState()
        if let payload = runtimeState.health {
            health = payload
            healthMessage = payload.message
            if !payload.knowledgeBasePath.isEmpty {
                activeKnowledgeBaseDirectoryPath = payload.knowledgeBasePath
                if knowledgeBaseDirectoryPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    knowledgeBaseDirectoryPath = payload.knowledgeBasePath
                }
                knowledgeBaseStatusMessage = "샌드박스 범위: \(payload.knowledgeBasePath)"
            }
            updateStartupGuidance(with: payload)
            if !payload.failedChecks.isEmpty {
                appLog("health warning: \(payload.failedChecks.joined(separator: ","))")
                if let modelDetail = payload.details["model"] {
                    appLog("health model detail: \(modelDetail)")
                }
                if let vectorDetail = payload.details["vector_db"] {
                    appLog("health vector_db detail: \(vectorDetail)")
                }
            }
            return
        }

        let errorMessage = runtimeState.errorMessage ?? "알 수 없는 서비스 상태 오류"
        appLog("health failed: \(errorMessage)")
        healthMessage = errorMessage
        knowledgeBaseStatusMessage = "지식기반 확인 실패: \(errorMessage)"
        if runtimeState.startupInProgress,
           !runtimeState.startupMessage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            startupGuidanceMessage = runtimeState.startupMessage
        } else {
            startupGuidanceMessage = "지식기반 상태를 확인할 수 없습니다. 디렉토리 설정을 검토해 주세요."
        }
    }

    private func updateStartupGuidance(with health: HealthResponse) {
        if knowledgeBaseIndexingInProgress {
            startupGuidanceMessage = knowledgeBaseIndexingMessage
            return
        }
        if health.knowledgeBasePath.isEmpty || health.failedChecks.contains("knowledge_base") {
            startupGuidanceMessage = "지식기반 디렉토리를 설정해 주세요. 설정 후 인덱싱이 자동으로 시작됩니다."
            return
        }
        if health.chunkCount == 0 {
            let failureCount = Int(health.details["index_failures"] ?? "") ?? 0
            let watchedFoldersDetail = health.details["watched_folders"] ?? ""
            startupGuidanceMessage = failureCount > 0
                ? "인덱싱 실패 문서가 있습니다. Knowledge Base와 Health 상태를 확인해 주세요."
                : (watchedFoldersDetail.lowercased().contains("ok")
                    ? "선택한 지식기반 폴더에 아직 인덱싱할 자료가 없습니다."
                    : "인덱싱된 지식기반이 아직 없습니다. 디렉토리를 확인하면 인덱싱이 자동으로 진행됩니다.")
            return
        }
        startupGuidanceMessage = nil
    }

    private func startMonitoringKnowledgeBaseSetup() {
        knowledgeBaseProgressTask?.cancel()
        knowledgeBaseIndexingInProgress = true
        knowledgeBaseIndexingMessage = "지식기반 디렉토리를 준비하는 중입니다."
        startupGuidanceMessage = knowledgeBaseIndexingMessage
        knowledgeBaseProgressTask = Task { [weak self] in
            guard let self else { return }
            var sawStartup = false
            var sawProgress = false
            let startedAt = ContinuousClock.now
            while !Task.isCancelled {
                let runtimeState = await self.bridge.runtimeState()
                let inProgress = runtimeState.startupInProgress
                let message = runtimeState.startupMessage
                await MainActor.run {
                    if inProgress {
                        sawStartup = true
                    }
                    self.knowledgeBaseIndexingInProgress = inProgress || !sawStartup
                    if !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        sawProgress = true
                        self.knowledgeBaseIndexingMessage = message
                        self.startupGuidanceMessage = message
                    } else if !inProgress, sawStartup {
                        if sawProgress {
                            self.knowledgeBaseIndexingMessage = ""
                        }
                        self.knowledgeBaseIndexingInProgress = false
                    }
                }
                if !inProgress, sawStartup {
                    break
                }
                if !sawStartup, startedAt.duration(to: ContinuousClock.now) > .seconds(2) {
                    await MainActor.run {
                        self.knowledgeBaseIndexingInProgress = false
                    }
                    break
                }
                try? await Task.sleep(for: .milliseconds(150))
            }
        }
    }

    private func normalizedKnowledgeBaseDirectoryPath(_ rawPath: String) -> String {
        let expanded = (rawPath as NSString).expandingTildeInPath
        return URL(fileURLWithPath: expanded, isDirectory: true).standardizedFileURL.path
    }

    private static func restoreKnowledgeBaseDirectoryURL() -> URL? {
        guard let bookmark = UserDefaults.standard.data(forKey: knowledgeBaseBookmarkDefaultsKey) else {
            return nil
        }
        var isStale = false
        guard let url = try? URL(
            resolvingBookmarkData: bookmark,
            options: [.withSecurityScope],
            relativeTo: nil,
            bookmarkDataIsStale: &isStale
        ) else {
            return nil
        }
        return url.standardizedFileURL
    }

    private func activateKnowledgeBaseSecurityScope(for url: URL) {
        if activeKnowledgeBaseSecurityScopeURL == url {
            return
        }
        if let activeURL = activeKnowledgeBaseSecurityScopeURL {
            activeURL.stopAccessingSecurityScopedResource()
            activeKnowledgeBaseSecurityScopeURL = nil
        }
        if url.startAccessingSecurityScopedResource() {
            activeKnowledgeBaseSecurityScopeURL = url
        }
    }

    private func persistKnowledgeBaseBookmark(for url: URL) {
        guard let bookmark = try? url.bookmarkData(
            options: [.withSecurityScope],
            includingResourceValuesForKeys: nil,
            relativeTo: nil
        ) else {
            return
        }
        UserDefaults.standard.set(bookmark, forKey: Self.knowledgeBaseBookmarkDefaultsKey)
    }

    func chooseKnowledgeBaseDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "지식기반 디렉토리 선택"
        panel.message = "JARVIS가 검색과 인덱싱에 사용할 샌드박스 지식기반 디렉토리를 선택하세요."
        if panel.runModal() == .OK, let url = panel.url {
            activateKnowledgeBaseSecurityScope(for: url)
            persistKnowledgeBaseBookmark(for: url)
            knowledgeBaseDirectoryPath = url.path
            applyKnowledgeBaseDirectorySetting()
        }
    }

    func applyKnowledgeBaseDirectorySetting() {
        let trimmed = knowledgeBaseDirectoryPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = "지식기반 디렉토리 경로를 입력해 주세요."
            knowledgeBaseStatusMessage = "지식기반 디렉토리가 비어 있습니다."
            return
        }

        let normalized = normalizedKnowledgeBaseDirectoryPath(trimmed)
        let normalizedURL = URL(fileURLWithPath: normalized, isDirectory: true)
        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: normalized, isDirectory: &isDirectory), isDirectory.boolValue else {
            errorMessage = "지식기반 디렉토리를 찾을 수 없습니다: \(normalized)"
            knowledgeBaseStatusMessage = "유효한 디렉토리를 지정해 주세요."
            return
        }

        activateKnowledgeBaseSecurityScope(for: normalizedURL)
        knowledgeBaseDirectoryPath = normalized
        activeKnowledgeBaseDirectoryPath = normalized
        knowledgeBaseStatusMessage = "샌드박스 범위: \(normalized)"
        UserDefaults.standard.set(normalized, forKey: Self.knowledgeBaseDirectoryDefaultsKey)
        errorMessage = nil

        Task {
            self.startMonitoringKnowledgeBaseSetup()
            await bridge.updateKnowledgeBasePath(normalized)
            await ttsPrefetchBridge.updateKnowledgeBasePath(normalized)
            await bridge.warmup()
            await refreshHealth()
        }
    }

    func resetKnowledgeBaseDirectorySetting() {
        if let activeURL = activeKnowledgeBaseSecurityScopeURL {
            activeURL.stopAccessingSecurityScopedResource()
            activeKnowledgeBaseSecurityScopeURL = nil
        }
        UserDefaults.standard.removeObject(forKey: Self.knowledgeBaseBookmarkDefaultsKey)
        knowledgeBaseDirectoryPath = BridgeConfiguration.default().defaultKnowledgeBasePath
        applyKnowledgeBaseDirectorySetting()
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
        if wakeWordSession != nil || passiveWakeFallbackEnabled {
            disarmWakeWordMonitoring()
        }
        voiceLoopEnabled = true
        errorMessage = nil
        exportMessage = nil
        voiceLoopPhase = .awaitingCommand
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

    private func stopVoiceLoop(
        resumeWakeWord: Bool = true,
        playSessionTone: Bool = false
    ) {
        let shouldResumeWakeWord = resumeWakeWord && wakeWordEnabled
        voiceLoopEnabled = false
        voiceLoopTask?.cancel()
        voiceLoopTask = nil
        nativeRecorder.cancel()
        stopLiveTranscription()
        stopTTS()
        voiceInputLevel = 0
        pendingClarificationContext = nil
        guide.clear()
        cancelPhaseTransition()
        isLoading = false
        voiceLoopPhase = .stopped
        consecutiveLoopErrors = 0
        if playSessionTone {
            playWakeAcknowledgementTone()
        }
        if shouldResumeWakeWord {
            startWakeWord()
        }
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
            let liveTranscript = await finishLiveTranscription()
            if Task.isCancelled {
                return nil
            }
            cancelPhaseTransition()
            voiceLoopPhase = .transcribing

            let transcriptText: String
            if !liveTranscript.isEmpty {
                transcriptText = liveTranscript
            } else {
                appLog("Voice loop live transcription unavailable; falling back to whisper-cli")
                let transcript = try await bridge.transcribeFile(audioPath: audioURL.path)
                transcriptText = transcript.transcript
            }
            let repairedTranscript = try await repairTranscriptForSubmission(transcriptText)
            if !guideTurnPreparedForCurrentRecording {
                guideTurnPreparedForCurrentRecording = true
            }
            lastTranscript = repairedTranscript.rawText
            query = repairedTranscript.displayText
            refreshNavigationWindow(for: repairedTranscript.displayText)
            guard let resolvedQuery = prepareQueryForSubmission(repairedTranscript.finalQuery) else {
                isLoading = false
                if Task.isCancelled || !voiceLoopEnabled {
                    return nil
                }
                voiceLoopPhase = .cooldown
                return successLoopDelay
            }

            voiceLoopPhase = .answering
            guide.prepareForNewTurn(mode: currentInteractionMode)
            submittedQueryForPendingContext = resolvedQuery
            startTTSPrefetchIfSupported(for: resolvedQuery)
            let payload = try await bridge.ask(resolvedQuery)
            if Task.isCancelled {
                return nil
            }
            applyResponsePayload(payload, rawUserQuery: repairedTranscript.displayText)
            exportMessage = nil
            errorMessage = nil
            consecutiveLoopErrors = 0
            isLoading = false

            // TTS — speak the response
            speakResponse(guide.audibleResponseText)
            await waitForSpeechPlaybackToFinish()

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
        guard guide.latestAskResponse != nil || !guide.exportableResponseText.isEmpty else {
            return
        }
        if exportFilename.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            exportFilename = exportFormat.suggestedFilename
        }
        exportMessage = nil
        showApprovalPanel = true
    }

    func copyResponse() {
        let fullContent: String
        if let path = guide.fullResponsePath, !path.isEmpty,
           let fileContent = try? String(contentsOfFile: path, encoding: .utf8) {
            fullContent = fileContent
        } else {
            fullContent = guide.exportableResponseText
        }
        guard !fullContent.isEmpty else { return }
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
        if let mode = guide.preferredInteractionMode {
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

    var isLiveVoicePreviewActive: Bool {
        partialTranscriptionActive
    }

    var currentExplorationItems: [MenuExplorationItem] {
        guide.currentItems
    }

    var currentSelectedExplorationItem: MenuExplorationItem? {
        guide.currentSelectedItem
    }

    var activeExplorationState: MenuExplorationState? {
        guide.activeExplorationState
    }

    var shouldShowGuidePanel: Bool {
        guide.shouldShowPanel()
    }

    func candidateNumber(for item: MenuExplorationItem) -> Int? {
        guide.candidateNumber(for: item)
    }

    func selectExplorationItem(_ item: MenuExplorationItem) {
        pinNavigationPanel()
        guide.selectArtifact(matching: item)
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
        let compact = Self.compactInputText(rawQuery)
        if (wakeWordEnabled || voiceLoopEnabled) && Self.isWakePhraseOnly(compact) {
            if wakeWordEnabled && !voiceLoopEnabled && !wakeWordTriggerPending {
                wakeWordTriggerPending = true
                Task { [weak self] in
                    await self?.handleWakeWordDetected()
                }
            }
            return nil
        }
        if voiceLoopEnabled && Self.isExitPhraseOnly(compact) {
            _ = processLocalVoiceCommand(rawQuery)
            return nil
        }
        if processLocalVoiceCommand(rawQuery) {
            return nil
        }
        if let mergedClarificationQuery = consumePendingClarificationAnswer(rawQuery) {
            return resolvedSubmissionQuery(mergedClarificationQuery)
        }
        guard sourceExplorationSessionActive || documentExplorationSessionActive else {
            return rawQuery
        }
        return resolvedSubmissionQuery(rawQuery)
    }

    static func isWakePhraseOnly(_ text: String) -> Bool {
        let trimmed = compactInputText(text)
        guard !trimmed.isEmpty else { return false }
        let range = NSRange(trimmed.startIndex..<trimmed.endIndex, in: trimmed)
        return wakePhraseOnlyPattern.firstMatch(in: trimmed, options: [], range: range) != nil
    }

    static func wakePhraseRemainder(in text: String) -> String? {
        let trimmed = compactInputText(text)
        guard !trimmed.isEmpty else { return nil }
        let range = NSRange(trimmed.startIndex..<trimmed.endIndex, in: trimmed)
        guard let match = wakePhrasePrefixPattern.firstMatch(in: trimmed, options: [], range: range) else {
            return nil
        }
        guard match.numberOfRanges > 1,
              let remainderRange = Range(match.range(at: 1), in: trimmed)
        else {
            return ""
        }
        return compactInputText(String(trimmed[remainderRange]))
    }

    static func isExitPhraseOnly(_ text: String) -> Bool {
        let trimmed = compactInputText(text)
        guard !trimmed.isEmpty else { return false }
        let range = NSRange(trimmed.startIndex..<trimmed.endIndex, in: trimmed)
        return exitPhraseOnlyPattern.firstMatch(in: trimmed, options: [], range: range) != nil
    }

    private func resolvedWakeCommand(
        from repairedTranscript: TranscriptRepairPayload
    ) -> TranscriptRepairPayload {
        let bufferedQuery = pendingWakeBufferedQuery.map(Self.compactInputText)
        defer {
            pendingWakeBufferedQuery = nil
        }

        let compactFinalQuery = Self.compactInputText(repairedTranscript.finalQuery)
        let hasCapturedCommand =
            !compactFinalQuery.isEmpty
            && !Self.isWakePhraseOnly(compactFinalQuery)
            && compactFinalQuery.count >= 3
        guard !hasCapturedCommand,
              let bufferedQuery,
              !bufferedQuery.isEmpty
        else {
            return repairedTranscript
        }

        appLog("Using buffered wake fallback query: \(Self.logPreview(for: bufferedQuery))")
        return TranscriptRepairPayload(
            rawText: repairedTranscript.rawText,
            repairedText: bufferedQuery,
            displayText: bufferedQuery,
            finalQuery: bufferedQuery
        )
    }

    private func repairTranscriptForSubmission(_ rawQuery: String) async throws -> TranscriptRepairPayload {
        try await bridge.repairTranscript(rawQuery)
    }

    private func startTTSPrefetchIfSupported(for query: String) {
        let cleaned = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return }
        guard ttsPrefetchEnabled() else { return }
        let prefetchBridge = self.ttsPrefetchBridge
        Task.detached(priority: .background) {
            appLog("TTS prefetch request started")
            do {
                let result = try await prefetchBridge.prefetchQueryTTS(cleaned)
                if result.started {
                    appLog("TTS prefetch queued (\(result.predictedText.count) chars)")
                }
            } catch {
                // Best-effort only; prefetch should never disrupt ask/TTS flow.
            }
        }
    }

    func resolvedSubmissionQuery(_ rawQuery: String) -> String {
        let exploration = guide.activeExplorationState
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
            guide.selectedExplorationItemID = item.id
            return item
        }

        let lowered = rawQuery.lowercased()
        if let item = items.first(where: { item in
            lowered.contains(item.label.lowercased())
                || (!item.path.isEmpty && lowered.contains((item.path as NSString).lastPathComponent.lowercased()))
        }) {
            guide.selectedExplorationItemID = item.id
            return item
        }
        return currentSelectedExplorationItem
    }

    private func processLocalVoiceCommand(_ rawQuery: String) -> Bool {
        let lowered = rawQuery.lowercased()
        if voiceLoopEnabled && Self.isExitPhraseOnly(rawQuery) {
            errorMessage = nil
            exportMessage = nil
            stopVoiceLoop(playSessionTone: true)
            return true
        }
        if processGuideCloseCommand(rawQuery, lowered: lowered) {
            return true
        }
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
            guide.selectedExplorationItemID = ""
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
                guide.selectedExplorationItemID = ""
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

    private func processGuideCloseCommand(_ rawQuery: String, lowered: String) -> Bool {
        let closeIntentTokens = ["닫아", "닫아줘", "닫기", "close", "shut", "꺼줘", "꺼"]
        guard closeIntentTokens.contains(where: lowered.contains) else {
            return false
        }

        let workspaceTokens = [
            "창", "가이드", "workspace", "워크스페이스", "패널", "panel",
            "뷰어", "viewer", "웹", "web", "브라우저", "browser",
            "사이트", "website", "유튜브", "youtube", "문서", "pdf",
            "코드", "source", "video", "비디오"
        ]
        guard workspaceTokens.contains(where: lowered.contains) else {
            return false
        }

        let targetHint = guideCloseTargetHint(from: rawQuery)
        if !targetHint.isEmpty, guide.closeWorkspaceSession(matching: targetHint) {
            errorMessage = nil
            if !guide.hasWorkspaceSessions {
                endGuideWorkspaceSession()
            }
            exportMessage = "\(targetHint) 창을 닫았습니다."
            return true
        }
        guard canCloseGuideWorkspace(matching: targetHint) else {
            errorMessage = nil
            exportMessage = targetHint.isEmpty
                ? "닫을 작업 창이 없습니다."
                : "\(targetHint) 창을 찾지 못했습니다."
            return true
        }

        errorMessage = nil
        closeGuidePanel()
        exportMessage = targetHint.isEmpty
            ? "작업 창을 닫았습니다."
            : "\(targetHint) 창을 닫았습니다."
        return true
    }

    private func guideCloseTargetHint(from rawQuery: String) -> String {
        var cleaned = rawQuery.lowercased()
        let removableTokens = [
            "닫아줘", "닫아", "닫기", "close", "shut", "please", "꺼줘", "꺼",
            "window", "workspace", "viewer", "panel", "guide", "jarvis",
            "창", "워크스페이스", "뷰어", "패널", "가이드",
            "해주세요", "해줘", "좀", "좀요", "please"
        ]
        for token in removableTokens {
            cleaned = cleaned.replacingOccurrences(of: token, with: " ")
        }
        return Self.compactInputText(cleaned)
    }

    private func canCloseGuideWorkspace(matching targetHint: String) -> Bool {
        guard guide.hasRenderableContent
            || sourceExplorationSessionActive
            || documentExplorationSessionActive else {
            return false
        }
        guard !targetHint.isEmpty else {
            return true
        }
        if guide.hasWorkspaceSession(matching: targetHint) {
            return true
        }
        return guideWorkspaceMatchesTarget(targetHint)
    }

    private func guideWorkspaceMatchesTarget(_ targetHint: String) -> Bool {
        let normalizedHint = targetHint.lowercased()
        if normalizedHint.isEmpty {
            return true
        }

        let artifact = guide.currentSelectedArtifact
        let viewerKind = artifact?.viewerKind.lowercased() ?? ""
        let haystacks = [
            artifact?.title.lowercased() ?? "",
            artifact?.subtitle.lowercased() ?? "",
            artifact?.path.lowercased() ?? "",
            artifact?.fullPath.lowercased() ?? "",
            guide.guidePresentation?.title.lowercased() ?? "",
            guide.guidePresentation?.subtitle.lowercased() ?? "",
            guide.finalResponseText.lowercased(),
        ]

        if haystacks.contains(where: { !$0.isEmpty && $0.contains(normalizedHint) }) {
            return true
        }
        if normalizedHint.contains("유튜브") || normalizedHint.contains("youtube") {
            return haystacks.contains(where: { $0.contains("youtube") || $0.contains("youtu.be") || $0.contains("유튜브") })
        }
        if normalizedHint.contains("웹")
            || normalizedHint.contains("브라우저")
            || normalizedHint.contains("사이트")
            || normalizedHint.contains("web")
            || normalizedHint.contains("browser")
            || normalizedHint.contains("website") {
            return viewerKind == "web" || viewerKind == "html"
        }
        if normalizedHint.contains("문서")
            || normalizedHint.contains("pdf")
            || normalizedHint.contains("document") {
            return viewerKind == "document"
        }
        if normalizedHint.contains("코드")
            || normalizedHint.contains("소스")
            || normalizedHint.contains("source")
            || normalizedHint.contains("code") {
            return viewerKind == "code"
        }
        if normalizedHint.contains("비디오")
            || normalizedHint.contains("video") {
            return viewerKind == "video"
        }
        return normalizedHint.contains("가이드")
            || normalizedHint.contains("workspace")
            || normalizedHint.contains("워크스페이스")
            || normalizedHint.contains("창")
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
        let targetFile = guide.activeExplorationState?.targetFile ?? ""

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
        let previousSelection = guide.selectedExplorationItemID
        guide.syncSelection()
        guard let preferred = guide.currentSelectedItem, guide.selectedExplorationItemID != previousSelection else {
            return
        }
        if preferred.kind == "document" {
            documentExplorationSessionActive = true
        } else {
            sourceExplorationSessionActive = true
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
        let destination = exportDestination()
        isLoading = true
        errorMessage = nil
        Task {
            do {
                let fullContent: String
                if let path = guide.fullResponsePath, !path.isEmpty,
                   let fileContent = try? String(contentsOfFile: path, encoding: .utf8) {
                    fullContent = fileContent
                } else {
                    fullContent = guide.exportableResponseText
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
        case .awaitingCommand:
            "wake word acknowledged, waiting for a fresh command"
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
            return "자비스 세션 활성화됨. 명령을 말씀해 주세요."
        case .awaitingCommand:
            return "🔔 신호음 후 새 명령을 말씀해 주세요."
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
        voiceInputLevel = 0

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

        nativeRecorder.onInputLevelChanged = { [weak self] level in
            guard let self else { return }
            let nextLevel = Double(level)
            let smoothing = nextLevel >= self.voiceInputLevel ? 0.64 : 0.2
            self.voiceInputLevel = (self.voiceInputLevel * (1 - smoothing)) + (nextLevel * smoothing)
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
        voiceInputLevel = 0
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
            .background(active ? JarvisTheme.amber.opacity(0.18) : JarvisTheme.panelMuted.opacity(0.92))
            .foregroundStyle(active ? JarvisTheme.amber : JarvisTheme.textSecondary)
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
            .background(
                Capsule(style: .continuous)
                    .fill(color.opacity(0.14))
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(color.opacity(0.2), lineWidth: 1)
            )
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
                    .foregroundStyle(JarvisTheme.textPrimary)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(JarvisTheme.textSecondary)
                }
            }
            content
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(JarvisTheme.panelBackground)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(JarvisTheme.border, lineWidth: 1)
        )
        .shadow(color: JarvisTheme.shadow, radius: 18, x: 0, y: 10)
    }
}

struct ActivityDots: View {
    let activeColor: Color
    let active: Bool

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<4, id: \.self) { index in
                Circle()
                .fill(active ? activeColor.opacity(0.35 + (Double(index) * 0.15)) : JarvisTheme.textMuted.opacity(0.18))
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
            return JarvisTheme.textMuted
        case .awaitingCommand:
            return JarvisTheme.green
        case .recording:
            return JarvisTheme.amber
        case .pauseDetected:
            return JarvisTheme.amber
        case .transcribing:
            return JarvisTheme.cyan
        case .answering:
            return JarvisTheme.blue
        case .cooldown:
            return JarvisTheme.green
        case .error:
            return JarvisTheme.red
        }
    }

    private var label: String {
        switch phase {
        case .idle:
            return "Ready"
        case .awaitingCommand:
            return "Armed"
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
                return JarvisTheme.cyan
            }
            return JarvisTheme.green
        }
        if lowered.contains("disabled") || lowered.contains("fts-only") || lowered.contains("not configured") {
            return JarvisTheme.amber
        }
        return JarvisTheme.red
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
                    .foregroundStyle(JarvisTheme.textSecondary)
            }
            Spacer()
        }
    }
}

enum JarvisSurfaceMode: String, CaseIterable, Identifiable {
    case voice = "voice"
    case chat = "chat"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .voice:
            return "Voice"
        case .chat:
            return "Chat"
        }
    }

    var subtitle: String {
        switch self {
        case .voice:
            return "핸즈프리 대화"
        case .chat:
            return "텍스트 중심 워크플로"
        }
    }
}

struct ConversationBubble: View {
    let title: String
    let text: String
    let tint: Color
    let alignedTrailing: Bool

    var body: some View {
        HStack {
            if alignedTrailing { Spacer(minLength: 40) }
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(tint)
                Text(text)
                    .font(.caption)
                    .foregroundStyle(JarvisTheme.textPrimary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(JarvisTheme.panelMuted.opacity(0.96))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(tint.opacity(0.28), lineWidth: 1)
            )
            if !alignedTrailing { Spacer(minLength: 40) }
        }
    }
}

struct VoiceCoreView: View {
    let phase: VoiceLoopPhase
    let listeningActive: Bool
    let speakingActive: Bool
    let inputLevel: Double

    private var tint: Color {
        if speakingActive { return JarvisTheme.cyan }
        if listeningActive { return JarvisTheme.amber }
        switch phase {
        case .transcribing:
            return JarvisTheme.cyan
        case .answering:
            return JarvisTheme.blue
        case .cooldown:
            return JarvisTheme.green
        case .error:
            return JarvisTheme.red
        default:
            return JarvisTheme.textMuted
        }
    }

    private var centerLabel: String {
        if speakingActive { return "Speaking" }
        if listeningActive { return "Listening" }
        switch phase {
        case .transcribing:
            return "Thinking"
        case .answering:
            return "Answer"
        case .cooldown:
            return "Cooldown"
        case .error:
            return "Error"
        case .stopped:
            return "Stopped"
        default:
            return "Ready"
        }
    }

    private var activeLevel: Double {
        if listeningActive { return 0.18 + min(1, inputLevel) * 0.92 }
        if speakingActive { return 0.88 }
        switch phase {
        case .transcribing, .answering:
            return 0.54
        case .cooldown:
            return 0.34
        case .error:
            return 0.2
        default:
            return 0.14
        }
    }

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 24.0)) { timeline in
            let time = timeline.date.timeIntervalSinceReferenceDate
            ZStack {
                Circle()
                    .stroke(tint.opacity(0.18), lineWidth: 1)
                    .frame(width: 210, height: 210)
                    .scaleEffect(1.0 + activeLevel * 0.03 + (listeningActive ? inputLevel * 0.07 : 0))
                Circle()
                    .stroke(tint.opacity(0.12), lineWidth: 18)
                    .frame(width: 170, height: 170)

                ForEach(0..<44, id: \.self) { index in
                    Capsule(style: .continuous)
                        .fill(tint.opacity(0.78))
                        .frame(width: 4, height: radialBarHeight(index: index, time: time))
                        .offset(y: -106)
                        .rotationEffect(.degrees(Double(index) * (360.0 / 44.0)))
                }

                Circle()
                    .fill(
                        RadialGradient(
                            colors: [
                                tint.opacity(0.46),
                                tint.opacity(0.16),
                                Color.black.opacity(0.02)
                            ],
                            center: .center,
                            startRadius: 8,
                            endRadius: 84
                        )
                    )
                    .frame(
                        width: 132 + (listeningActive ? inputLevel * 24 : activeLevel * 10),
                        height: 132 + (listeningActive ? inputLevel * 24 : activeLevel * 10)
                    )

                VStack(spacing: 6) {
                    Text(centerLabel)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(JarvisTheme.textPrimary)
                    Text(phase.rawValue.replacingOccurrences(of: "_", with: " "))
                        .font(.caption2)
                        .foregroundStyle(JarvisTheme.textSecondary)
                }
            }
            .frame(width: 228, height: 228)
            .background(
                RoundedRectangle(cornerRadius: 34, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [
                                JarvisTheme.panelRaised,
                                JarvisTheme.panel,
                                tint.opacity(0.04)
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
            )
        }
    }

    private func radialBarHeight(index: Int, time: Double) -> CGFloat {
        let phaseOffset = Double(index) * 0.37
        let liveEnergy = listeningActive ? max(0.04, inputLevel) : activeLevel
        let wave = sin((time * (2.6 + liveEnergy * 2.8)) + phaseOffset)
        let shimmer = cos((time * (1.8 + liveEnergy * 1.4)) + Double(index) * 0.18)
        let envelope = max(
            0.08,
            (liveEnergy * 0.92)
                + (wave * (0.14 + liveEnergy * 0.22))
                + (shimmer * (0.06 + liveEnergy * 0.08))
        )
        let maxTravel = listeningActive ? 40.0 : 26.0
        return CGFloat(10.0 + envelope * maxTravel)
    }
}

struct JarvisMenuContentView: View {
    @ObservedObject var viewModel: JarvisMenuBarViewModel
    @State private var surfaceMode: JarvisSurfaceMode = .voice

    private var phaseColor: Color {
        switch viewModel.voiceLoopPhase {
        case .idle, .stopped:
            return JarvisTheme.textMuted
        case .awaitingCommand:
            return JarvisTheme.green
        case .recording:
            return JarvisTheme.amber
        case .pauseDetected:
            return JarvisTheme.amber
        case .transcribing:
            return JarvisTheme.cyan
        case .answering:
            return JarvisTheme.blue
        case .cooldown:
            return JarvisTheme.green
        case .error:
            return JarvisTheme.red
        }
    }

    private var healthColor: Color {
        guard let health = viewModel.health else { return JarvisTheme.textMuted }
        switch health.statusLevel {
        case "healthy":
            return JarvisTheme.green
        case "warning":
            return JarvisTheme.amber
        default:
            return JarvisTheme.red
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
            return JarvisTheme.green
        }
        if lowered.contains("ready") || lowered.contains("lazy-loaded") {
            return JarvisTheme.cyan
        }
        if lowered.contains("disabled") || lowered.contains("fts-only") || lowered.contains("unavailable") {
            return JarvisTheme.amber
        }
        return JarvisTheme.textSecondary
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
                return JarvisTheme.blue
            case .sourceExploration:
                return JarvisTheme.cyan
            case .documentExploration:
                return JarvisTheme.amber
            }
        }
        return JarvisTheme.textMuted
    }

    private var latestAssistantText: String {
        if !viewModel.guide.finalResponseText.isEmpty {
            return viewModel.guide.finalResponseText
        }
        if !viewModel.guide.liveResponseText.isEmpty {
            return viewModel.guide.liveResponseText
        }
        return ""
    }

    private var voiceListeningActive: Bool {
        viewModel.isLiveVoicePreviewActive
            || viewModel.voiceLoopPhase == .recording
            || viewModel.voiceLoopPhase == .pauseDetected
    }

    private var voiceSpeakingActive: Bool {
        viewModel.isSpeaking || viewModel.voiceLoopPhase == .answering
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .center, spacing: 10) {
                    Picker("Surface", selection: $surfaceMode) {
                        ForEach(JarvisSurfaceMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)

                    Spacer()
                    Picker("마이크", selection: $viewModel.selectedInputDeviceID) {
                        Text("시스템 기본 입력").tag("")
                        ForEach(viewModel.availableInputDevices) { device in
                            Text(device.name).tag(device.id)
                        }
                    }
                    .labelsHidden()
                    .pickerStyle(.menu)

                    Button {
                        viewModel.refreshAudioInputDevices()
                    } label: {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 12, weight: .semibold))
                            .frame(width: 28, height: 28)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("마이크 장치 목록 새로고침")
                }

                if surfaceMode == .voice {
                    HStack(alignment: .top, spacing: 16) {
                        VoiceCoreView(
                            phase: viewModel.voiceLoopPhase,
                            listeningActive: voiceListeningActive,
                            speakingActive: voiceSpeakingActive,
                            inputLevel: viewModel.voiceInputLevel
                        )

                        VStack(alignment: .leading, spacing: 12) {
                            HStack(spacing: 6) {
                                ToneBadge(title: viewModel.currentInteractionMode.title, color: interactionModeColor(viewModel.currentInteractionMode))
                            }

                            if !viewModel.lastTranscript.isEmpty {
                                Text(viewModel.lastTranscript)
                                    .font(.body)
                                    .foregroundStyle(JarvisTheme.textPrimary)
                                    .textSelection(.enabled)
                            }

                            if !latestAssistantText.isEmpty {
                                Text(latestAssistantText)
                                    .font(.caption)
                                    .foregroundStyle(JarvisTheme.textPrimary)
                                    .lineLimit(5)
                                    .textSelection(.enabled)
                            }

                            ActivityDots(activeColor: phaseColor, active: viewModel.isLoading || voiceListeningActive || voiceSpeakingActive)

                            HStack(spacing: 8) {
                                Button {
                                    viewModel.recordOnce()
                                } label: {
                                    Label("말하기", systemImage: "mic.fill")
                                }

                                Button(viewModel.voiceLoopEnabled ? "루프 중지" : "라이브 루프") {
                                    viewModel.toggleVoiceLoop()
                                }

                                if viewModel.isSpeaking {
                                    Button("음성 중지") {
                                        viewModel.stopTTS()
                                    }
                                }

                                Spacer()
                            }

                        }
                    }
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 6) {
                            ToneBadge(title: viewModel.currentInteractionMode.title, color: interactionModeColor(viewModel.currentInteractionMode))
                        }

                        ScrollView {
                            VStack(alignment: .leading, spacing: 10) {
                                if !viewModel.lastTranscript.isEmpty {
                                    ConversationBubble(
                                        title: "User",
                                        text: viewModel.lastTranscript,
                                        tint: JarvisTheme.amber,
                                        alignedTrailing: true
                                    )
                                }
                                if !latestAssistantText.isEmpty {
                                    ConversationBubble(
                                        title: "JARVIS",
                                        text: latestAssistantText,
                                        tint: JarvisTheme.cyan,
                                        alignedTrailing: false
                                    )
                                }
                            }
                        }
                        .frame(minHeight: 180, maxHeight: 260)

                        TextField("질문을 입력하세요", text: $viewModel.query)
                            .textFieldStyle(.roundedBorder)
                            .onChange(of: viewModel.query) { _, newValue in
                                if !viewModel.isLiveVoicePreviewActive {
                                    viewModel.refreshNavigationWindow(for: newValue)
                                }
                            }
                            .onSubmit {
                                viewModel.submit()
                            }

                        HStack(spacing: 8) {
                            Button {
                                viewModel.recordOnce()
                            } label: {
                                Label("음성 입력", systemImage: "waveform")
                            }

                            if viewModel.isSpeaking {
                                Button("음성 중지") {
                                    viewModel.stopTTS()
                                }
                            }

                            Spacer()
                        }

                    }
                }
                if let errorMessage = viewModel.errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(JarvisTheme.red)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(JarvisTheme.panelBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(JarvisTheme.border, lineWidth: 1)
            )
            .shadow(color: JarvisTheme.shadow, radius: 18, x: 0, y: 10)
        }
        .padding(14)
        .frame(width: 560)
        .background(
            JarvisTheme.appBackground
        )
        .tint(JarvisTheme.cyan)
        .preferredColorScheme(.dark)
        .overlay {
            if viewModel.showApprovalPanel {
                Color.black.opacity(0.3)
                    .ignoresSafeArea()
                    .onTapGesture { viewModel.declineExport() }
                    .overlay {
                        VStack(alignment: .leading, spacing: 14) {
                            Text("Export Approval")
                                .font(.title3.weight(.bold))
                                .foregroundStyle(JarvisTheme.textPrimary)
                            Text("기술문서 기준 승인형 쓰기 정책을 따릅니다. 파일 쓰기는 명시 승인 후에만 진행됩니다.")
                                .font(.callout)
                                .foregroundStyle(JarvisTheme.textSecondary)
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
                                .foregroundStyle(JarvisTheme.textSecondary)
                                .textSelection(.enabled)
                            if viewModel.exportWillOverwrite {
                                Text("Existing file will be overwritten.")
                                    .font(.caption)
                                    .foregroundStyle(JarvisTheme.amber)
                            }
                            if let msg = viewModel.exportMessage {
                                Text(msg)
                                    .font(.caption)
                                    .foregroundStyle(msg.hasPrefix("Exported") ? JarvisTheme.green : JarvisTheme.textSecondary)
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
                        .background(JarvisTheme.panelBackground, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12)
                                .stroke(JarvisTheme.border, lineWidth: 1)
                        )
                        .shadow(color: JarvisTheme.shadow, radius: 12, x: 0, y: 8)
                    }
            }
        }
    }
}


@main
struct JarvisMenuBarApp: App {
    @StateObject private var viewModel: JarvisMenuBarViewModel
    private let guideController: JarvisGuideController

    init() {
        let model = JarvisMenuBarViewModel()
        _viewModel = StateObject(wrappedValue: model)
        guideController = JarvisGuideController(viewModel: model)
    }

    var body: some Scene {
        return MenuBarExtra("JARVIS", systemImage: "sparkles.rectangle.stack") {
            JarvisMenuContentView(viewModel: viewModel)
        }
        .menuBarExtraStyle(.window)
        .commands {
            CommandGroup(after: .appInfo) {
                Button("Refresh Jarvis Guide") {
                    guideController.refresh()
                }
            }
        }
    }
}
