import AppKit
import Combine
import SwiftUI

enum JarvisGuideLoopStage: String {
    case idle = "idle"
    case listening = "listening"
    case interpreting = "interpreting"
    case clarifying = "clarifying"
    case reasoning = "reasoning"
    case presenting = "presenting"
    case waitingUserReply = "waiting_user_reply"
    case completed = "completed"

    var title: String {
        switch self {
        case .idle:
            return "대기"
        case .listening:
            return "청취"
        case .interpreting:
            return "해석"
        case .clarifying:
            return "보완 질문"
        case .reasoning:
            return "추론"
        case .presenting:
            return "결과 제시"
        case .waitingUserReply:
            return "사용자 응답 대기"
        case .completed:
            return "완료"
        }
    }
}

struct JarvisGuideClarificationOption: Identifiable, Equatable {
    let label: String

    var id: String { label }
}

@MainActor
final class JarvisGuideState: ObservableObject {
    @Published var latestAskResponse: ServiceAskResponse?
    @Published var latestResponse: MenuResponse?
    @Published var exploration: MenuExplorationState?
    @Published var backendGuide: ServiceGuidePayload?
    @Published var loopStage: JarvisGuideLoopStage = .idle
    @Published var phaseLabel = ""
    @Published var summaryText = ""
    @Published var liveResponseText = ""
    @Published var finalResponseText = ""
    @Published var clarificationPrompt = ""
    @Published var clarificationReasons: [String] = []
    @Published var clarificationOptions: [JarvisGuideClarificationOption] = []
    @Published var pinnedByUser = false
    @Published var interactionMode: InteractionMode = .generalQuery
    @Published var selectedExplorationItemID = ""
    @Published private(set) var isLoading = false
    @Published private(set) var isStreaming = false
    @Published private(set) var voiceLoopEnabled = false
    @Published private(set) var wakeWordEnabled = false
    @Published private(set) var partialTranscriptionActive = false

    private var visibleUntil: Date?
    private var hideTask: Task<Void, Never>?
    private let finalHideSeconds: TimeInterval = 20.0

    var currentItems: [MenuExplorationItem] {
        guard let exploration else { return [] }
        return exploration.fileCandidates
            + exploration.documentCandidates
            + exploration.classCandidates
            + exploration.functionCandidates
    }

    var currentSelectedItem: MenuExplorationItem? {
        currentItems.first(where: { $0.id == selectedExplorationItemID })
    }

    private var rawResponse: MenuResponse? {
        latestAskResponse?.response ?? latestResponse
    }

    var status: MenuStatus? {
        rawResponse?.status
    }

    var hasExportableResponse: Bool {
        latestAskResponse != nil || !exportableResponseText.isEmpty
    }

    var activeExplorationState: MenuExplorationState? {
        exploration
    }

    var hasRenderableContent: Bool {
        exploration != nil
            || !phaseLabel.isEmpty
            || !summaryText.isEmpty
            || !liveResponseText.isEmpty
            || !finalResponseText.isEmpty
            || hasClarification
    }

    var hasClarification: Bool {
        !clarificationPrompt.isEmpty
            || !clarificationReasons.isEmpty
            || !clarificationOptions.isEmpty
    }

    func candidateNumber(for item: MenuExplorationItem) -> Int? {
        currentItems.firstIndex(where: { $0.id == item.id }).map { $0 + 1 }
    }

    func syncSelection() {
        let items = currentItems
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
        }
    }

    func showLiveEstimate(mode: InteractionMode) {
        interactionMode = mode
        loopStage = .interpreting
        backendGuide = nil
        clearClarification()
        exploration = MenuExplorationState(
            mode: mode.rawValue,
            targetFile: "",
            targetDocument: "",
            fileCandidates: [],
            documentCandidates: [],
            classCandidates: [],
            functionCandidates: []
        )
        phaseLabel = "실시간 추정"
        summaryText = "음성 입력을 기준으로 후보를 추정하는 중입니다"
        clearAutoHide()
    }

    func prepareForNewTurn(mode: InteractionMode) {
        interactionMode = mode
        loopStage = .listening
        latestAskResponse = nil
        latestResponse = nil
        backendGuide = nil
        liveResponseText = ""
        finalResponseText = ""
        clearClarification()
        pinnedByUser = false
        clearAutoHide()
    }

    func appendStreamingToken(_ token: String) {
        loopStage = .reasoning
        liveResponseText += token
    }

    func presentFinalResponse(_ text: String, askResponse: ServiceAskResponse? = nil) {
        let response = askResponse?.response
        let effectiveGuide = askResponse?.guide ?? response.flatMap(Self.legacyGuidePayload(from:))
        latestAskResponse = askResponse
        latestResponse = response
        self.backendGuide = effectiveGuide
        liveResponseText = ""
        finalResponseText = text
        syncClarificationState(backendGuide: effectiveGuide)
        applyLoopStageDirective(backendGuide: effectiveGuide)
        clearAutoHide()
    }

    func applyExploration(_ exploration: MenuExplorationState, mode: InteractionMode, immediate: Bool) {
        interactionMode = mode
        loopStage = immediate ? .interpreting : .clarifying
        self.exploration = exploration
        phaseLabel = immediate ? "실시간 후보" : "정리된 후보"
        summaryText = summary(for: exploration, final: false)
        if immediate {
            clearClarification()
        } else {
            syncClarificationState(backendGuide: backendGuide)
        }
        clearAutoHide()
        syncSelection()
    }

    func handleUpdateFailure(immediate: Bool) {
        guard exploration != nil else {
            clearAutoHide()
            loopStage = .idle
            phaseLabel = ""
            summaryText = ""
            return
        }
        loopStage = .clarifying
        phaseLabel = immediate ? "실시간 추정" : "후보 유지"
        summaryText = immediate
            ? "실시간 후보 갱신이 지연되고 있습니다"
            : "직전 후보를 유지한 상태로 응답을 기다리는 중입니다"
        if !immediate {
            if backendGuide != nil {
                syncClarificationState(backendGuide: backendGuide)
            } else {
                presentClarification(
                    prompt: fallbackPrompt(for: interactionMode),
                    reasons: ["현재 후보를 유지한 상태로 추가 설명을 기다리고 있습니다."],
                    options: fallbackOptions(for: interactionMode, exploration: exploration)
                )
            }
        }
        clearAutoHide()
    }

    func keepBestExploration(
        _ exploration: MenuExplorationState?,
        fallback: MenuExplorationState?,
        mode: InteractionMode
    ) {
        interactionMode = InteractionMode(rawValue: exploration?.mode ?? fallback?.mode ?? mode.rawValue) ?? mode
        loopStage = .presenting

        if hasCandidates(exploration) {
            self.exploration = exploration
            phaseLabel = "최종 확정"
            summaryText = summary(for: exploration, final: true)
            syncClarificationState(backendGuide: backendGuide)
            applyLoopStageDirective(backendGuide: backendGuide)
            extendVisibility(for: finalHideSeconds)
            syncSelection()
            return
        }
        if hasCandidates(fallback) {
            self.exploration = fallback
            phaseLabel = "최종 확정"
            summaryText = summary(for: fallback, final: true)
            syncClarificationState(backendGuide: backendGuide)
            applyLoopStageDirective(backendGuide: backendGuide)
            extendVisibility(for: finalHideSeconds)
            syncSelection()
            return
        }
        self.exploration = exploration ?? fallback ?? self.exploration
        phaseLabel = "응답 반영"
        summaryText = "응답은 완료되었지만 확정 후보는 제한적입니다"
        syncClarificationState(backendGuide: backendGuide)
        applyLoopStageDirective(backendGuide: backendGuide)
        extendVisibility(for: finalHideSeconds)
        syncSelection()
    }

    func pin() {
        pinnedByUser = true
        clearAutoHide()
    }

    var autoCloseDisabled: Bool {
        pinnedByUser
    }

    func toggleAutoCloseDisabled() {
        pinnedByUser.toggle()
        if pinnedByUser {
            clearAutoHide()
        }
    }

    func resetForNewRequest() {
        pinnedByUser = false
        clearAutoHide()
    }

    func clear() {
        clearAutoHide()
        latestAskResponse = nil
        latestResponse = nil
        exploration = nil
        backendGuide = nil
        loopStage = .idle
        phaseLabel = ""
        summaryText = ""
        liveResponseText = ""
        finalResponseText = ""
        clearClarification()
        pinnedByUser = false
        selectedExplorationItemID = ""
        interactionMode = .generalQuery
    }

    func shouldShowPanel(
        isLoading _: Bool = false,
        voiceLoopEnabled _: Bool = false,
        wakeWordEnabled _: Bool = false,
        partialTranscriptionActive _: Bool = false,
        isStreaming _: Bool = false
    ) -> Bool {
        let hasCandidates = hasCandidates(activeExplorationState)
        let hasResponseContent = !liveResponseText.isEmpty || !finalResponseText.isEmpty
        let hasClarification = hasClarification
        let hasPresentationState =
            !phaseLabel.isEmpty
            || !summaryText.isEmpty
            || hasResponseContent
            || hasClarification
            || !(activeExplorationState?.targetFile ?? "").isEmpty
            || !(activeExplorationState?.targetDocument ?? "").isEmpty
        let shouldShowLoadingState =
            !hasCandidates
            && !hasResponseContent
            && !hasClarification
            && interactionMode != .generalQuery
            && (partialTranscriptionActive || isLoading || isStreaming)
        let hasVisibleSession =
            pinnedByUser
            || hasClarification
            || ((visibleUntil?.timeIntervalSinceNow ?? 0) > 0)
        guard hasCandidates || hasResponseContent || hasClarification || shouldShowLoadingState || (hasPresentationState && hasVisibleSession) else {
            return false
        }
        if isLoading || voiceLoopEnabled || wakeWordEnabled || partialTranscriptionActive || isStreaming {
            return true
        }
        if !finalResponseText.isEmpty {
            return true
        }
        if hasClarification {
            return true
        }
        if pinnedByUser {
            return true
        }
        if let deadline = visibleUntil, deadline > Date() {
            return true
        }
        return false
    }

    func updateRuntimeState(
        isLoading: Bool,
        isStreaming: Bool,
        voiceLoopEnabled: Bool,
        wakeWordEnabled: Bool,
        partialTranscriptionActive: Bool
    ) {
        self.isLoading = isLoading
        self.isStreaming = isStreaming
        self.voiceLoopEnabled = voiceLoopEnabled
        self.wakeWordEnabled = wakeWordEnabled
        self.partialTranscriptionActive = partialTranscriptionActive
        if partialTranscriptionActive {
            loopStage = .listening
        } else if isStreaming || isLoading {
            if finalResponseText.isEmpty {
                loopStage = .reasoning
            }
        } else if let backendGuide,
                  let mapped = Self.mapLoopStage(backendGuide.loopStage) {
            loopStage = mapped
        } else if hasClarification {
            loopStage = .waitingUserReply
        } else if !finalResponseText.isEmpty {
            loopStage = .waitingUserReply
        }
    }

    var exportableResponseText: String {
        if let answerText = latestAskResponse?.answer?.text, !answerText.isEmpty {
            return answerText
        }
        if let response = rawResponse {
            return response.response
        }
        if !finalResponseText.isEmpty {
            return finalResponseText
        }
        return liveResponseText
    }

    var fullResponsePath: String? {
        latestAskResponse?.answer?.fullResponsePath ?? rawResponse?.fullResponsePath
    }

    var citations: [MenuCitation] {
        rawResponse?.citations ?? []
    }

    var sourcePresentation: MenuSourcePresentation? {
        rawResponse?.sourcePresentation
    }

    var preferredInteractionMode: InteractionMode? {
        if let raw = backendGuide?.interactionMode,
           let mode = InteractionMode(rawValue: raw),
           !raw.isEmpty {
            return mode
        }
        if let raw = latestAskResponse?.response.renderHints?.interactionMode,
           let mode = InteractionMode(rawValue: raw) {
            return mode
        }
        if let raw = rawResponse?.renderHints?.interactionMode,
           let mode = InteractionMode(rawValue: raw) {
            return mode
        }
        return nil
    }

    var audibleResponseText: String {
        if !clarificationPrompt.isEmpty {
            return clarificationPrompt
        }
        if let spokenText = latestAskResponse?.answer?.spokenText, !spokenText.isEmpty {
            return spokenText
        }
        if let spokenText = rawResponse?.spokenResponse ?? nil, !spokenText.isEmpty {
            return spokenText
        }
        if let answerText = latestAskResponse?.answer?.text, !answerText.isEmpty {
            return answerText
        }
        if !finalResponseText.isEmpty {
            return finalResponseText
        }
        return liveResponseText
    }

    private func hasCandidates(_ exploration: MenuExplorationState?) -> Bool {
        guard let exploration else { return false }
        return !exploration.fileCandidates.isEmpty
            || !exploration.documentCandidates.isEmpty
            || !exploration.classCandidates.isEmpty
            || !exploration.functionCandidates.isEmpty
    }

    private func presentClarification(
        prompt: String,
        reasons: [String],
        options: [String]
    ) {
        clarificationPrompt = prompt
        clarificationReasons = reasons
        clarificationOptions = options
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .reduce(into: [JarvisGuideClarificationOption]()) { result, label in
                if !result.contains(where: { $0.label == label }) {
                    result.append(JarvisGuideClarificationOption(label: label))
                }
            }
    }

    private func clearClarification() {
        clarificationPrompt = ""
        clarificationReasons = []
        clarificationOptions = []
    }

    private func syncClarificationState(backendGuide: ServiceGuidePayload?) {
        if let backendGuide {
            guard backendGuide.loopStage == JarvisGuideLoopStage.waitingUserReply.rawValue else {
                clearClarification()
                return
            }
            let options = backendGuide.clarificationOptions.isEmpty
                ? fallbackOptions(for: interactionMode, exploration: exploration)
                : backendGuide.clarificationOptions
            let reasons = backendGuide.clarificationReasons.isEmpty
                ? backendGuide.missingSlots.map(Self.humanizeMissingSlot)
                : backendGuide.clarificationReasons
            if !backendGuide.clarificationPrompt.isEmpty || !reasons.isEmpty {
                presentClarification(
                    prompt: backendGuide.clarificationPrompt,
                    reasons: reasons,
                    options: options
                )
                return
            }
            clearClarification()
            return
        }
        clearClarification()
    }

    private func fallbackPrompt(for mode: InteractionMode) -> String {
        switch mode {
        case .documentExploration:
            return "어떤 문서를 기준으로 이어서 볼지 알려주세요."
        case .sourceExploration:
            return "어느 파일, 클래스, 함수 기준으로 이어서 볼지 알려주세요."
        case .generalQuery:
            return "답을 더 정확하게 만들기 위해 필요한 정보를 알려주세요."
        }
    }

    private func fallbackOptions(
        for mode: InteractionMode,
        exploration: MenuExplorationState?
    ) -> [String] {
        let candidateLabels = (exploration?.documentCandidates ?? [])
            .prefix(2)
            .map(\.label)
            + (exploration?.fileCandidates ?? [])
            .prefix(2)
            .map(\.label)
            + (exploration?.classCandidates ?? [])
            .prefix(2)
            .map(\.label)
            + (exploration?.functionCandidates ?? [])
            .prefix(2)
            .map(\.label)
        if !candidateLabels.isEmpty {
            return candidateLabels
        }
        switch mode {
        case .documentExploration:
            return ["첫 번째 문서", "문서 제목으로 지정", "이 문서 요약해줘"]
        case .sourceExploration:
            return ["첫 번째 후보", "파일 이름으로 지정", "이 클래스 설명해줘"]
        case .generalQuery:
            return ["현재 위치 추가", "대상 이름 추가", "조건을 더 구체화"]
        }
    }

    private func applyLoopStageDirective(backendGuide: ServiceGuidePayload? = nil) {
        if let raw = backendGuide?.loopStage, let mapped = Self.mapLoopStage(raw) {
            loopStage = mapped
            return
        }
        loopStage = hasClarification ? .waitingUserReply : .presenting
    }

    private static func legacyGuidePayload(from response: MenuResponse) -> ServiceGuidePayload? {
        guard let directive = response.guideDirective else {
            return nil
        }
        let reasons = directive.missingSlots.map(Self.humanizeMissingSlot)
        return ServiceGuidePayload(
            loopStage: directive.loopStage,
            clarificationPrompt: directive.clarificationPrompt,
            suggestedReplies: directive.suggestedReplies,
            clarificationOptions: directive.suggestedReplies,
            missingSlots: directive.missingSlots,
            clarificationReasons: reasons,
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

    private static func mapLoopStage(_ raw: String) -> JarvisGuideLoopStage? {
        switch raw {
        case "idle":
            return .idle
        case "listening":
            return .listening
        case "interpreting":
            return .interpreting
        case "clarifying":
            return .clarifying
        case "reasoning":
            return .reasoning
        case "presenting":
            return .presenting
        case "waiting_user_reply":
            return .waitingUserReply
        case "completed":
            return .completed
        default:
            return nil
        }
    }

    private static func humanizeMissingSlot(_ slot: String) -> String {
        switch slot {
        case "target_document":
            return "대상 문서가 아직 확정되지 않았습니다."
        case "document_selection":
            return "여러 문서 후보 중 하나를 선택해야 합니다."
        case "target_file":
            return "대상 파일이 아직 확정되지 않았습니다."
        case "source_selection":
            return "파일, 클래스, 함수 후보 중 하나를 더 좁혀야 합니다."
        default:
            return slot.replacingOccurrences(of: "_", with: " ")
        }
    }

    private func summary(for exploration: MenuExplorationState?, final: Bool) -> String {
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

    private func extendVisibility(for seconds: TimeInterval) {
        let deadline = Date().addingTimeInterval(seconds)
        visibleUntil = deadline
        hideTask?.cancel()
        hideTask = Task { @MainActor [weak self] in
            guard let self else { return }
            let remaining = deadline.timeIntervalSinceNow
            if remaining > 0 {
                try? await Task.sleep(for: .milliseconds(Int((remaining * 1000).rounded())))
            }
            guard !Task.isCancelled else { return }
            if let currentDeadline = self.visibleUntil,
               currentDeadline <= Date(),
               !self.pinnedByUser {
                self.clear()
            }
        }
    }

    private func clearAutoHide() {
        visibleUntil = nil
        hideTask?.cancel()
        hideTask = nil
    }
}

@MainActor
final class JarvisGuideController {
    private let panel: NSPanel
    private let host: NSHostingController<JarvisGuideView>
    private var cancellables: Set<AnyCancellable> = []
    private unowned let viewModel: JarvisMenuBarViewModel

    init(viewModel: JarvisMenuBarViewModel) {
        self.viewModel = viewModel
        self.host = NSHostingController(
            rootView: JarvisGuideView(
                guide: viewModel.guide,
                onSelect: viewModel.selectExplorationItem,
                onClose: viewModel.closeGuidePanel,
                onToggleAutoClose: viewModel.toggleGuideAutoClose
            )
        )
        self.panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 520, height: 680),
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

        observeState()
    }

    private func observeState() {
        viewModel.guide.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] in
                DispatchQueue.main.async {
                    self?.refresh()
                }
            }
            .store(in: &cancellables)
    }

    func refresh() {
        host.rootView = JarvisGuideView(
            guide: viewModel.guide,
            onSelect: viewModel.selectExplorationItem,
            onClose: viewModel.closeGuidePanel,
            onToggleAutoClose: viewModel.toggleGuideAutoClose
        )
        guard viewModel.shouldShowGuidePanel else {
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

struct JarvisGuideView: View {
    @ObservedObject var guide: JarvisGuideState
    let onSelect: (MenuExplorationItem) -> Void
    let onClose: () -> Void
    let onToggleAutoClose: () -> Void

    private var exploration: MenuExplorationState? {
        guide.activeExplorationState
    }

    var body: some View {
        Group {
            if guide.hasRenderableContent {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 6) {
                        Text("Jarvis Guide")
                            .font(.headline)
                        Spacer()
                        Button(guide.autoCloseDisabled ? "자동닫기해제" : "자동닫기방지") {
                            onToggleAutoClose()
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        Button("닫기") {
                            onClose()
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        ToneBadge(title: guide.loopStage.title, color: .teal)
                        if !guide.phaseLabel.isEmpty {
                            ToneBadge(title: guide.phaseLabel, color: .blue)
                        }
                        ToneBadge(
                            title: guide.interactionMode.title,
                            color: guide.interactionMode == .documentExploration ? .orange : .mint
                        )
                    }

                    if let exploration, !exploration.targetFile.isEmpty {
                        Text("대상 파일: \(exploration.targetFile)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let exploration, !exploration.targetDocument.isEmpty {
                        Text("대상 문서: \(exploration.targetDocument)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !guide.summaryText.isEmpty {
                        Text(guide.summaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if guide.hasClarification {
                        clarificationSection
                    }

                    if !guide.liveResponseText.isEmpty {
                        responseSection("실시간 응답", text: guide.liveResponseText, tint: .blue)
                    } else if !guide.finalResponseText.isEmpty {
                        responseSection("최종 응답", text: guide.finalResponseText, tint: .teal)
                        if let sourcePresentation = guide.sourcePresentation {
                            sourcePresentationSection(sourcePresentation)
                        }
                        if !guide.citations.isEmpty {
                            citationSection(guide.citations)
                        }
                    }

                    if guide.currentItems.isEmpty && guide.finalResponseText.isEmpty && guide.liveResponseText.isEmpty {
                        HStack(spacing: 10) {
                            ProgressView()
                                .controlSize(.small)
                            Text("실시간 후보를 찾는 중입니다")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 20)
                    } else if let exploration {
                        ScrollView {
                            VStack(alignment: .leading, spacing: 8) {
                                if !exploration.documentCandidates.isEmpty {
                                    guideSection("문서 후보", items: exploration.documentCandidates, tint: .orange)
                                }
                                if !exploration.fileCandidates.isEmpty {
                                    guideSection("파일 후보", items: exploration.fileCandidates, tint: .mint)
                                }
                                if !exploration.classCandidates.isEmpty {
                                    guideSection("클래스 후보", items: exploration.classCandidates, tint: .mint)
                                }
                                if !exploration.functionCandidates.isEmpty {
                                    guideSection("함수 후보", items: exploration.functionCandidates, tint: .mint)
                                }
                            }
                        }
                        .frame(maxHeight: guide.finalResponseText.isEmpty ? 240 : 180)
                    }

                    if let selected = guide.currentSelectedItem,
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
                        .frame(minHeight: 120, maxHeight: 220)
                    }

                    Text(guide.interactionMode == .documentExploration ? "예: 첫 번째, guide.pdf 문서, 이 문서 요약해줘" : "예: 첫 번째, Pipeline 클래스, 이 클래스 설명해줘")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(14)
                .frame(width: 520)
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
    private func responseSection(_ title: String, text: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(tint)
            ScrollView {
                Text(text)
                    .font(.callout)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(minHeight: 180, maxHeight: title == "최종 응답" ? 320 : 220)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(tint.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(tint.opacity(0.16), lineWidth: 1)
        )
    }

    private var clarificationSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("보완 질문")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.orange)
            if !guide.clarificationPrompt.isEmpty {
                Text(guide.clarificationPrompt)
                    .font(.caption.weight(.semibold))
                    .textSelection(.enabled)
            }
            if !guide.clarificationReasons.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(guide.clarificationReasons, id: \.self) { reason in
                        HStack(alignment: .top, spacing: 6) {
                            Circle()
                                .fill(Color.orange.opacity(0.6))
                                .frame(width: 5, height: 5)
                                .padding(.top, 5)
                            Text(reason)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            if !guide.clarificationOptions.isEmpty {
                FlowLayout(spacing: 6) {
                    ForEach(guide.clarificationOptions) { option in
                        Text(option.label)
                            .font(.caption2.weight(.semibold))
                            .padding(.horizontal, 9)
                            .padding(.vertical, 6)
                            .background(
                                Capsule(style: .continuous)
                                    .fill(Color.orange.opacity(0.12))
                            )
                            .overlay(
                                Capsule(style: .continuous)
                                    .stroke(Color.orange.opacity(0.22), lineWidth: 1)
                            )
                    }
                }
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.orange.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.orange.opacity(0.16), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func sourcePresentationSection(_ source: MenuSourcePresentation) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(sourcePresentationHeader(for: source))
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.mint)
                Spacer()
                if !source.fullSourcePath.isEmpty {
                    Button(source.sourceType == "web" ? "링크 열기" : "원문 열기") {
                        openSourcePresentation(source)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
            if !source.title.isEmpty {
                Text(source.title)
                    .font(.caption.weight(.semibold))
            }
            if !source.headingPath.isEmpty {
                Text(source.headingPath)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
            if !source.quote.isEmpty && source.previewLines.isEmpty {
                Text(source.quote)
                    .font(.caption)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if !source.previewLines.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(source.previewLines, id: \.self) { line in
                        Text(line)
                            .font(.caption)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            if !source.sourcePath.isEmpty {
                Text(source.sourcePath)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.mint.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.mint.opacity(0.16), lineWidth: 1)
        )
    }

    private func sourcePresentationHeader(for source: MenuSourcePresentation) -> String {
        switch source.kind {
        case "table_row":
            return "표 미리보기"
        case "web_page":
            return "웹 미리보기"
        case "code_symbol":
            return "코드 미리보기"
        default:
            return "원문 보기"
        }
    }

    private func openSourcePresentation(_ source: MenuSourcePresentation) {
        openSourcePath(source.fullSourcePath, sourceType: source.sourceType)
    }

    private func openSourcePath(_ path: String, sourceType: String) {
        guard !path.isEmpty else { return }
        if sourceType == "web", let url = URL(string: path) {
            NSWorkspace.shared.open(url)
            return
        }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    @ViewBuilder
    private func citationSection(_ citations: [MenuCitation]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("출처")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.teal)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(citations) { citation in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(alignment: .top, spacing: 6) {
                                Text(citation.label)
                                    .font(.caption.monospacedDigit().weight(.semibold))
                                    .foregroundStyle(.teal)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(citation.sourcePath)
                                        .font(.caption.weight(.semibold))
                                    Text("\(citation.sourceType) · \(citation.state)")
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                    if !citation.headingPath.isEmpty {
                                        Text(citation.headingPath)
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                if !citation.fullSourcePath.isEmpty {
                                    Button(citation.sourceType == "web" ? "링크 열기" : "열기") {
                                        openSourcePath(citation.fullSourcePath, sourceType: citation.sourceType)
                                    }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                                }
                            }
                            if !citation.quote.isEmpty {
                                Text(citation.quote)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color.teal.opacity(0.06))
                        )
                    }
                }
            }
            .frame(minHeight: 90, maxHeight: 180)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.teal.opacity(0.08))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.teal.opacity(0.16), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func guideSection(_ title: String, items: [MenuExplorationItem], tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
            ForEach(items) { item in
                HStack(alignment: .top, spacing: 8) {
                    Text("\(guide.candidateNumber(for: item) ?? 0).")
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
                        .fill(guide.currentSelectedItem?.id == item.id ? tint.opacity(0.18) : Color.black.opacity(0.08))
                )
                .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .onTapGesture {
                    onSelect(item)
                }
            }
        }
    }
}

private struct FlowLayout<Content: View>: View {
    let spacing: CGFloat
    @ViewBuilder let content: Content

    init(spacing: CGFloat, @ViewBuilder content: () -> Content) {
        self.spacing = spacing
        self.content = content()
    }

    var body: some View {
        HStack(spacing: spacing) {
            content
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
