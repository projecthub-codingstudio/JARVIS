import AppKit
import AVKit
import Combine
import PDFKit
import QuickLookUI
import SwiftUI
import WebKit

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

struct JarvisGuideWorkspaceSession: Identifiable {
    let id: String
    let askResponse: ServiceAskResponse?
    let response: MenuResponse?
    let exploration: MenuExplorationState?
    let guide: ServiceGuidePayload?
    let interactionMode: InteractionMode
    let answerText: String
    let title: String
    let subtitle: String
    var selectedExplorationItemID: String
    var selectedArtifactID: String
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
    @Published var ambientStatusText = ""
    @Published var clarificationPrompt = ""
    @Published var clarificationReasons: [String] = []
    @Published var clarificationOptions: [JarvisGuideClarificationOption] = []
    @Published var pinnedByUser = false
    @Published var interactionMode: InteractionMode = .generalQuery
    @Published var selectedExplorationItemID = ""
    @Published var selectedArtifactID = ""
    @Published private(set) var isLoading = false
    @Published private(set) var isStreaming = false
    @Published private(set) var isSpeaking = false
    @Published private(set) var voiceLoopEnabled = false
    @Published private(set) var wakeWordEnabled = false
    @Published private(set) var partialTranscriptionActive = false

    @Published private(set) var workspaceSessions: [JarvisGuideWorkspaceSession] = []
    @Published var activeWorkspaceSessionID = ""
    private var visibleUntil: Date?
    private var hideTask: Task<Void, Never>?
    private let finalHideSeconds: TimeInterval = 20.0

    private var activeWorkspaceSession: JarvisGuideWorkspaceSession? {
        if let selected = workspaceSessions.first(where: { $0.id == activeWorkspaceSessionID }) {
            return selected
        }
        return workspaceSessions.first
    }

    private var stickyWorkspace: JarvisGuideWorkspaceSession? {
        activeWorkspaceSession
    }

    private var assistantRawResponse: MenuResponse? {
        latestAskResponse?.response ?? latestResponse
    }

    private var workspaceRawResponse: MenuResponse? {
        stickyWorkspace?.askResponse?.response ?? stickyWorkspace?.response
    }

    private var contentRawResponse: MenuResponse? {
        workspaceRawResponse ?? assistantRawResponse
    }

    private var contentExplorationState: MenuExplorationState? {
        stickyWorkspace?.exploration ?? exploration
    }

    private var contentGuidePayload: ServiceGuidePayload? {
        stickyWorkspace?.guide ?? backendGuide
    }

    private var contentInteractionMode: InteractionMode {
        stickyWorkspace?.interactionMode ?? interactionMode
    }

    private var hasStickyWorkspace: Bool {
        stickyWorkspace != nil
    }

    var hasWorkspaceSessions: Bool {
        !workspaceSessions.isEmpty
    }

    var workspaceSessionItems: [JarvisGuideWorkspaceSession] {
        workspaceSessions
    }

    var currentItems: [MenuExplorationItem] {
        guard let exploration = contentExplorationState else { return [] }
        return exploration.fileCandidates
            + exploration.documentCandidates
            + exploration.classCandidates
            + exploration.functionCandidates
    }

    private var effectiveSelectedExplorationItemID: String {
        if let selected = activeWorkspaceSession?.selectedExplorationItemID, !selected.isEmpty {
            return selected
        }
        return selectedExplorationItemID
    }

    private var effectiveSelectedArtifactID: String {
        if let selected = activeWorkspaceSession?.selectedArtifactID, !selected.isEmpty {
            return selected
        }
        return selectedArtifactID
    }

    var currentSelectedItem: MenuExplorationItem? {
        currentItems.first(where: { $0.id == effectiveSelectedExplorationItemID })
    }

    var currentArtifacts: [MenuGuideArtifact] {
        if let artifacts = contentGuidePayload?.artifacts, !artifacts.isEmpty {
            return artifacts
        }
        return Self.fallbackArtifacts(response: contentRawResponse, exploration: contentExplorationState)
    }

    var currentSelectedArtifact: MenuGuideArtifact? {
        if let selected = currentArtifacts.first(where: { $0.id == effectiveSelectedArtifactID }) {
            return selected
        }
        if let preferred = guidePresentation?.selectedArtifactID,
           !preferred.isEmpty {
            return currentArtifacts.first(where: { $0.id == preferred })
        }
        return currentArtifacts.first
    }

    private var presentationResponseText: String {
        if !liveResponseText.isEmpty {
            return liveResponseText
        }
        if !finalResponseText.isEmpty {
            return finalResponseText
        }
        return exportableResponseText
    }

    private var workspacePresentationResponseText: String {
        if let answerText = activeWorkspaceSession?.answerText, !answerText.isEmpty {
            return answerText
        }
        if let response = workspaceRawResponse {
            return response.response
        }
        return presentationResponseText
    }

    var guidePresentation: MenuGuidePresentation? {
        if let presentation = contentGuidePayload?.presentation {
            return presentation
        }
        return Self.fallbackPresentation(
            response: contentRawResponse,
            exploration: contentExplorationState,
            interactionMode: contentInteractionMode,
            responseText: hasWorkspaceSessions ? workspacePresentationResponseText : presentationResponseText
        )
    }

    var status: MenuStatus? {
        assistantRawResponse?.status ?? workspaceRawResponse?.status
    }

    var hasExportableResponse: Bool {
        latestAskResponse != nil || !exportableResponseText.isEmpty
    }

    var activeExplorationState: MenuExplorationState? {
        contentExplorationState
    }

    var hasRenderableContent: Bool {
        guidePresentation != nil
            || !currentArtifacts.isEmpty
            || exploration != nil
            || !phaseLabel.isEmpty
            || !summaryText.isEmpty
            || !ambientStatusText.isEmpty
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

    func artifacts(for block: MenuGuideBlock) -> [MenuGuideArtifact] {
        if block.kind == "detail" {
            return currentSelectedArtifact.map { [$0] } ?? []
        }
        let ids = Set(block.artifactIDs)
        return currentArtifacts.filter { ids.contains($0.id) }
    }

    func citations(for block: MenuGuideBlock) -> [MenuCitation] {
        guard !block.citationLabels.isEmpty else { return citations }
        let labels = Set(block.citationLabels)
        return citations.filter { labels.contains($0.label) }
    }

    func explorationItem(for artifactID: String) -> MenuExplorationItem? {
        currentItems.first(where: { Self.legacyArtifactID(for: $0) == artifactID })
    }

    func selectArtifact(_ artifactID: String) {
        guard !artifactID.isEmpty else { return }
        setSelectedArtifactID(artifactID)
        if let matchingItem = explorationItem(for: artifactID) {
            setSelectedExplorationItemID(matchingItem.id)
        }
    }

    func selectArtifact(matching item: MenuExplorationItem) {
        setSelectedExplorationItemID(item.id)
        let artifactID = Self.legacyArtifactID(for: item)
        if currentArtifacts.contains(where: { $0.id == artifactID }) {
            setSelectedArtifactID(artifactID)
        }
    }

    func syncSelection() {
        let items = currentItems
        if items.isEmpty {
            setSelectedExplorationItemID("")
        } else if !items.contains(where: { $0.id == effectiveSelectedExplorationItemID }) {
            if let preferred = items.first(where: { $0.kind == "class" })
                ?? items.first(where: { $0.kind == "document" })
                ?? items.first(where: { $0.kind == "filename" })
                ?? items.first {
                setSelectedExplorationItemID(preferred.id)
            }
        }

        let artifacts = currentArtifacts
        guard !artifacts.isEmpty else {
            setSelectedArtifactID("")
            return
        }

        if let selectedItem = currentSelectedItem {
            let matchingArtifactID = Self.legacyArtifactID(for: selectedItem)
            if artifacts.contains(where: { $0.id == matchingArtifactID }) {
                setSelectedArtifactID(matchingArtifactID)
                return
            }
        }
        if artifacts.contains(where: { $0.id == effectiveSelectedArtifactID }) {
            return
        }
        if let preferred = guidePresentation?.selectedArtifactID,
           artifacts.contains(where: { $0.id == preferred }) {
            setSelectedArtifactID(preferred)
            return
        }
        setSelectedArtifactID(artifacts.first?.id ?? "")
    }

    func activateWorkspaceSession(_ sessionID: String) {
        guard workspaceSessions.contains(where: { $0.id == sessionID }) else { return }
        activeWorkspaceSessionID = sessionID
        if let session = activeWorkspaceSession {
            interactionMode = session.interactionMode
            selectedExplorationItemID = session.selectedExplorationItemID
            selectedArtifactID = session.selectedArtifactID
        }
        clearAutoHide()
        syncSelection()
    }

    func closeWorkspaceSession(_ sessionID: String) {
        let remaining = workspaceSessions.filter { $0.id != sessionID }
        workspaceSessions = remaining
        if remaining.isEmpty {
            activeWorkspaceSessionID = ""
            selectedExplorationItemID = ""
            selectedArtifactID = ""
            if liveResponseText.isEmpty && finalResponseText.isEmpty && !hasClarification {
                clear()
            }
            return
        }
        if activeWorkspaceSessionID == sessionID || !remaining.contains(where: { $0.id == activeWorkspaceSessionID }) {
            activeWorkspaceSessionID = remaining[0].id
        }
        if let session = activeWorkspaceSession {
            selectedExplorationItemID = session.selectedExplorationItemID
            selectedArtifactID = session.selectedArtifactID
        }
        clearAutoHide()
        syncSelection()
    }

    func hasWorkspaceSession(matching targetHint: String) -> Bool {
        matchingWorkspaceSessionID(for: targetHint) != nil
    }

    @discardableResult
    func closeWorkspaceSession(matching targetHint: String) -> Bool {
        guard let sessionID = matchingWorkspaceSessionID(for: targetHint) else { return false }
        closeWorkspaceSession(sessionID)
        return true
    }

    private func setSelectedExplorationItemID(_ id: String) {
        selectedExplorationItemID = id
        guard let activeID = activeWorkspaceSession?.id,
              let index = workspaceSessions.firstIndex(where: { $0.id == activeID }) else { return }
        workspaceSessions[index].selectedExplorationItemID = id
    }

    private func setSelectedArtifactID(_ id: String) {
        selectedArtifactID = id
        guard let activeID = activeWorkspaceSession?.id,
              let index = workspaceSessions.firstIndex(where: { $0.id == activeID }) else { return }
        workspaceSessions[index].selectedArtifactID = id
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
        if !hasStickyWorkspace {
            selectedArtifactID = ""
        }
        clearAutoHide()
    }

    func prepareForNewTurn(mode: InteractionMode) {
        interactionMode = mode
        loopStage = .listening
        latestAskResponse = nil
        latestResponse = nil
        exploration = nil
        backendGuide = nil
        liveResponseText = ""
        finalResponseText = ""
        clearClarification()
        if !hasStickyWorkspace {
            pinnedByUser = false
            selectedExplorationItemID = ""
            selectedArtifactID = ""
        }
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
        if shouldPersistWorkspace(askResponse: askResponse, guide: effectiveGuide, response: response) {
            let session = buildWorkspaceSession(
                askResponse: askResponse,
                response: response,
                guide: effectiveGuide,
                answerText: text
            )
            appendWorkspaceSession(session)
            clearAutoHide()
        } else if hasStickyWorkspace || hasClarification {
            clearAutoHide()
        } else {
            extendVisibility(for: finalHideSeconds)
        }
        syncSelection()
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
            if hasStickyWorkspace {
                clearAutoHide()
            } else {
                extendVisibility(for: finalHideSeconds)
            }
            syncSelection()
            return
        }
        if hasCandidates(fallback) {
            self.exploration = fallback
            phaseLabel = "최종 확정"
            summaryText = summary(for: fallback, final: true)
            syncClarificationState(backendGuide: backendGuide)
            applyLoopStageDirective(backendGuide: backendGuide)
            if hasStickyWorkspace {
                clearAutoHide()
            } else {
                extendVisibility(for: finalHideSeconds)
            }
            syncSelection()
            return
        }
        self.exploration = exploration ?? fallback ?? self.exploration
        phaseLabel = "응답 반영"
        summaryText = "응답은 완료되었지만 확정 후보는 제한적입니다"
        syncClarificationState(backendGuide: backendGuide)
        applyLoopStageDirective(backendGuide: backendGuide)
        if hasStickyWorkspace {
            clearAutoHide()
        } else {
            extendVisibility(for: finalHideSeconds)
        }
        syncSelection()
    }

    func pin() {
        pinnedByUser = true
        clearAutoHide()
    }

    var autoCloseDisabled: Bool {
        pinnedByUser || hasStickyWorkspace
    }

    func toggleAutoCloseDisabled() {
        pinnedByUser.toggle()
        if pinnedByUser {
            clearAutoHide()
        }
    }

    func resetForNewRequest() {
        if !hasStickyWorkspace {
            pinnedByUser = false
        }
        clearAutoHide()
    }

    func clear() {
        clearAutoHide()
        workspaceSessions = []
        activeWorkspaceSessionID = ""
        latestAskResponse = nil
        latestResponse = nil
        exploration = nil
        backendGuide = nil
        loopStage = .idle
        phaseLabel = ""
        summaryText = ""
        liveResponseText = ""
        finalResponseText = ""
        ambientStatusText = ""
        clearClarification()
        pinnedByUser = false
        selectedExplorationItemID = ""
        selectedArtifactID = ""
        interactionMode = .generalQuery
    }

    func shouldShowPanel() -> Bool {
        let hasCandidates = hasCandidates(activeExplorationState)
        let hasWorkspaceContent = guidePresentation != nil || !currentArtifacts.isEmpty
        let hasResponseContent = !liveResponseText.isEmpty || !finalResponseText.isEmpty
        let hasEvidenceContent = !citations.isEmpty || sourcePresentation != nil
        let hasGuideContent = hasCandidates || hasWorkspaceContent || hasEvidenceContent
        let hasClarification = hasClarification
        let hasAmbientStatus = !ambientStatusText.isEmpty
        let hasPresentationState =
            hasGuideContent
            || hasResponseContent
            || hasStickyWorkspace
            || !phaseLabel.isEmpty
            || !summaryText.isEmpty
            || hasAmbientStatus
            || hasClarification
            || !(activeExplorationState?.targetFile ?? "").isEmpty
            || !(activeExplorationState?.targetDocument ?? "").isEmpty
        let shouldShowLoadingState =
            !hasCandidates
            && !hasGuideContent
            && !hasResponseContent
            && !hasClarification
            && interactionMode != .generalQuery
            && (partialTranscriptionActive || isLoading || isStreaming)
        let hasVisibleSession =
            pinnedByUser
            || hasStickyWorkspace
            || hasAmbientStatus
            || hasClarification
            || ((visibleUntil?.timeIntervalSinceNow ?? 0) > 0)
        guard
            hasGuideContent
                || hasResponseContent
                || hasClarification
                || hasAmbientStatus
                || shouldShowLoadingState
                || (hasPresentationState && hasVisibleSession)
        else {
            return false
        }
        if isLoading || voiceLoopEnabled || wakeWordEnabled || partialTranscriptionActive || isStreaming || isSpeaking {
            return true
        }
        if hasClarification {
            return true
        }
        if hasStickyWorkspace || pinnedByUser {
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
        isSpeaking: Bool,
        voiceLoopEnabled: Bool,
        wakeWordEnabled: Bool,
        partialTranscriptionActive: Bool,
        ambientStatusText: String
    ) {
        self.isLoading = isLoading
        self.isStreaming = isStreaming
        self.isSpeaking = isSpeaking
        self.voiceLoopEnabled = voiceLoopEnabled
        self.wakeWordEnabled = wakeWordEnabled
        self.partialTranscriptionActive = partialTranscriptionActive
        self.ambientStatusText = ambientStatusText
        if partialTranscriptionActive {
            loopStage = .listening
        } else if isStreaming || isLoading {
            if finalResponseText.isEmpty {
                loopStage = .reasoning
            }
        } else if let contentGuidePayload,
                  let mapped = Self.mapLoopStage(contentGuidePayload.loopStage) {
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
        if let response = assistantRawResponse {
            return response.response
        }
        if !finalResponseText.isEmpty {
            return finalResponseText
        }
        if let response = workspaceRawResponse {
            return response.response
        }
        return liveResponseText
    }

    var fullResponsePath: String? {
        latestAskResponse?.answer?.fullResponsePath
            ?? assistantRawResponse?.fullResponsePath
            ?? workspaceRawResponse?.fullResponsePath
    }

    var citations: [MenuCitation] {
        contentRawResponse?.citations ?? []
    }

    var sourcePresentation: MenuSourcePresentation? {
        contentRawResponse?.sourcePresentation
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
        if let raw = assistantRawResponse?.renderHints?.interactionMode,
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
        if let spokenText = assistantRawResponse?.spokenResponse ?? nil, !spokenText.isEmpty {
            return spokenText
        }
        if let answerText = latestAskResponse?.answer?.text, !answerText.isEmpty {
            return answerText
        }
        if !finalResponseText.isEmpty {
            return finalResponseText
        }
        if let spokenText = workspaceRawResponse?.spokenResponse, !spokenText.isEmpty {
            return spokenText
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

    private func shouldPersistWorkspace(
        askResponse: ServiceAskResponse?,
        guide: ServiceGuidePayload?,
        response: MenuResponse?
    ) -> Bool {
        if guide?.shouldHold == true,
           guide?.presentation != nil || !(guide?.artifacts ?? []).isEmpty {
            return true
        }
        let artifacts = guide?.artifacts
            ?? Self.fallbackArtifacts(response: response, exploration: response?.exploration)
        let stickyViewerKinds: Set<String> = ["web", "html", "document", "video", "code", "image"]
        return artifacts.contains { artifact in
            stickyViewerKinds.contains(artifact.viewerKind.lowercased())
        }
    }

    private func buildWorkspaceSession(
        askResponse: ServiceAskResponse?,
        response: MenuResponse?,
        guide: ServiceGuidePayload?,
        answerText: String
    ) -> JarvisGuideWorkspaceSession {
        let resolvedInteractionMode = resolveInteractionMode(
            assistantGuide: guide,
            response: response,
            fallback: interactionMode
        )
        let artifacts = guide?.artifacts
            ?? Self.fallbackArtifacts(response: response, exploration: response?.exploration)
        let selectedArtifactID = guide?.presentation?.selectedArtifactID
            ?? artifacts.first?.id
            ?? ""
        let selectedArtifact = artifacts.first(where: { $0.id == selectedArtifactID }) ?? artifacts.first
        let sessionTitle = selectedArtifact?.title
            ?? guide?.presentation?.title
            ?? resolvedInteractionMode.title
        let sessionSubtitle = selectedArtifact?.subtitle
            ?? guide?.presentation?.subtitle
            ?? ""

        return JarvisGuideWorkspaceSession(
            id: UUID().uuidString,
            askResponse: askResponse,
            response: response,
            exploration: response?.exploration ?? exploration,
            guide: guide,
            interactionMode: resolvedInteractionMode,
            answerText: answerText,
            title: sessionTitle,
            subtitle: sessionSubtitle,
            selectedExplorationItemID: selectedExplorationItemID,
            selectedArtifactID: selectedArtifactID
        )
    }

    private func appendWorkspaceSession(_ session: JarvisGuideWorkspaceSession) {
        var updated = workspaceSessions.filter { existing in
            !(existing.title == session.title && existing.subtitle == session.subtitle && existing.selectedArtifactID == session.selectedArtifactID)
        }
        updated.insert(session, at: 0)
        if updated.count > 8 {
            updated = Array(updated.prefix(8))
        }
        workspaceSessions = updated
        activeWorkspaceSessionID = session.id
        interactionMode = session.interactionMode
        selectedExplorationItemID = session.selectedExplorationItemID
        selectedArtifactID = session.selectedArtifactID
    }

    private func resolveInteractionMode(
        assistantGuide: ServiceGuidePayload?,
        response: MenuResponse?,
        fallback: InteractionMode
    ) -> InteractionMode {
        if let raw = assistantGuide?.interactionMode,
           let mode = InteractionMode(rawValue: raw),
           !raw.isEmpty {
            return mode
        }
        if let raw = response?.renderHints?.interactionMode,
           let mode = InteractionMode(rawValue: raw) {
            return mode
        }
        return fallback
    }

    private func matchingWorkspaceSessionID(for targetHint: String) -> String? {
        guard !workspaceSessions.isEmpty else { return nil }
        let normalizedHint = targetHint
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if normalizedHint.isEmpty {
            return activeWorkspaceSession?.id ?? workspaceSessions.first?.id
        }
        if let activeWorkspaceSession,
           workspaceSession(activeWorkspaceSession, matches: normalizedHint) {
            return activeWorkspaceSession.id
        }
        return workspaceSessions.first(where: { workspaceSession($0, matches: normalizedHint) })?.id
    }

    private func workspaceSession(_ session: JarvisGuideWorkspaceSession, matches normalizedHint: String) -> Bool {
        let artifacts = session.guide?.artifacts
            ?? Self.fallbackArtifacts(
                response: session.askResponse?.response ?? session.response,
                exploration: session.exploration
            )
        let selectedArtifact = artifacts.first(where: { $0.id == session.selectedArtifactID }) ?? artifacts.first
        let viewerKind = selectedArtifact?.viewerKind.lowercased() ?? ""
        let haystacks = [
            session.title,
            session.subtitle,
            session.answerText,
            session.guide?.presentation?.title ?? "",
            session.guide?.presentation?.subtitle ?? "",
            selectedArtifact?.title ?? "",
            selectedArtifact?.subtitle ?? "",
            selectedArtifact?.path ?? "",
            selectedArtifact?.fullPath ?? "",
        ]
        .map { $0.lowercased() }

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
        if normalizedHint.contains("이미지")
            || normalizedHint.contains("image")
            || normalizedHint.contains("사진")
            || normalizedHint.contains("photo") {
            return viewerKind == "image"
        }
        return normalizedHint.contains("가이드")
            || normalizedHint.contains("workspace")
            || normalizedHint.contains("워크스페이스")
            || normalizedHint.contains("창")
            || normalizedHint.contains("패널")
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

    private func fallbackArtifacts() -> [MenuGuideArtifact] {
        Self.fallbackArtifacts(response: contentRawResponse, exploration: contentExplorationState)
    }

    private func fallbackPresentation() -> MenuGuidePresentation? {
        let responseText: String
        if !finalResponseText.isEmpty {
            responseText = finalResponseText
        } else if let response = assistantRawResponse {
            responseText = response.response
        } else {
            responseText = liveResponseText
        }
        return Self.fallbackPresentation(
            response: contentRawResponse,
            exploration: contentExplorationState,
            interactionMode: contentInteractionMode,
            responseText: responseText
        )
    }

    private static func fallbackArtifacts(
        response: MenuResponse?,
        exploration: MenuExplorationState?
    ) -> [MenuGuideArtifact] {
        let activeExploration = exploration ?? response?.exploration
        var artifacts: [MenuGuideArtifact] = []
        var seenIDs: Set<String> = []
        var explorationItems: [MenuExplorationItem] = []
        if let activeExploration {
            explorationItems.append(contentsOf: activeExploration.documentCandidates)
            explorationItems.append(contentsOf: activeExploration.fileCandidates)
            explorationItems.append(contentsOf: activeExploration.classCandidates)
            explorationItems.append(contentsOf: activeExploration.functionCandidates)
        }
        for item in explorationItems {
            let artifact = artifact(from: item)
            if seenIDs.insert(artifact.id).inserted {
                artifacts.append(artifact)
            }
        }

        if let sourcePresentation = response?.sourcePresentation {
            let artifact = artifact(from: sourcePresentation)
            if seenIDs.insert(artifact.id).inserted {
                artifacts.append(artifact)
            }
        }

        return artifacts
    }

    private static func fallbackPresentation(
        response: MenuResponse?,
        exploration: MenuExplorationState?,
        interactionMode: InteractionMode,
        responseText: String
    ) -> MenuGuidePresentation? {
        let artifacts = fallbackArtifacts(response: response, exploration: exploration)
        let activeExploration = exploration ?? response?.exploration
        var explorationItems: [MenuExplorationItem] = []
        if let activeExploration {
            explorationItems.append(contentsOf: activeExploration.documentCandidates)
            explorationItems.append(contentsOf: activeExploration.fileCandidates)
            explorationItems.append(contentsOf: activeExploration.classCandidates)
            explorationItems.append(contentsOf: activeExploration.functionCandidates)
        }
        let listArtifactIDs = explorationItems.map { legacyArtifactID(for: $0) }
        let selectedArtifactID =
            response?.sourcePresentation.map { artifact(from: $0).id }
            ?? listArtifactIDs.first
            ?? artifacts.first?.id
            ?? ""

        var blocks: [MenuGuideBlock] = []
        if !responseText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            blocks.append(MenuGuideBlock(
                id: "answer",
                kind: "answer",
                title: "AI 응답",
                subtitle: "현재 요청에 대한 설명",
                artifactIDs: [],
                citationLabels: [],
                emptyState: ""
            ))
        }
        if !listArtifactIDs.isEmpty {
            blocks.append(MenuGuideBlock(
                id: "list",
                kind: "list",
                title: interactionMode == .documentExploration ? "자료 목록" : "소스 목록",
                subtitle: "항목을 선택하면 상세 뷰가 바뀝니다",
                artifactIDs: listArtifactIDs,
                citationLabels: [],
                emptyState: "표시할 후보가 없습니다."
            ))
        }
        if !selectedArtifactID.isEmpty {
            blocks.append(MenuGuideBlock(
                id: "detail",
                kind: "detail",
                title: "상세 보기",
                subtitle: "선택한 항목의 미리보기",
                artifactIDs: [selectedArtifactID],
                citationLabels: [],
                emptyState: "목록에서 항목을 선택하세요."
            ))
        }
        let citationLabels = response?.citations.map(\.label) ?? []
        if !citationLabels.isEmpty {
            blocks.append(MenuGuideBlock(
                id: "evidence",
                kind: "evidence",
                title: "근거 자료",
                subtitle: "응답에 사용된 출처",
                artifactIDs: [],
                citationLabels: citationLabels,
                emptyState: "표시할 근거가 없습니다."
            ))
        }

        guard !blocks.isEmpty else { return nil }

        let selectedType = artifacts.first(where: { $0.id == selectedArtifactID })?.type.lowercased() ?? ""
        let richDetailTypes: Set<String> = ["document", "html", "web", "video"]
        let layout: String
        if !listArtifactIDs.isEmpty
            && !selectedArtifactID.isEmpty
            && !citationLabels.isEmpty
            && richDetailTypes.contains(selectedType) {
            layout = "tabs"
        } else if !listArtifactIDs.isEmpty && !selectedArtifactID.isEmpty {
            layout = "master_detail"
        } else if !selectedArtifactID.isEmpty
            && !citationLabels.isEmpty
            && richDetailTypes.contains(selectedType) {
            layout = "split"
        } else {
            layout = "stack"
        }

        let title: String
        switch interactionMode {
        case .sourceExploration:
            title = "Source Workspace"
        case .documentExploration:
            title = "Document Workspace"
        case .generalQuery:
            title = "Jarvis Workspace"
        }
        let selectedTitle = artifacts.first(where: { $0.id == selectedArtifactID })?.title ?? ""
        let subtitle = [
            "항목 \(artifacts.count)개",
            "근거 \(citationLabels.count)개",
            selectedTitle.isEmpty ? "" : "현재 선택: \(selectedTitle)"
        ]
        .filter { !$0.isEmpty }
        .joined(separator: " · ")

        return MenuGuidePresentation(
            layout: layout,
            title: title,
            subtitle: subtitle,
            selectedArtifactID: selectedArtifactID,
            blocks: blocks
        )
    }

    private static func legacyArtifactID(for item: MenuExplorationItem) -> String {
        "artifact:\(item.kind):\(item.path):\(item.label)"
    }

    private static func artifact(from item: MenuExplorationItem) -> MenuGuideArtifact {
        let type = artifactType(for: item.kind, path: item.path)
        return MenuGuideArtifact(
            id: legacyArtifactID(for: item),
            type: type,
            title: item.label,
            subtitle: artifactSubtitle(for: item.kind),
            path: item.path,
            fullPath: item.path.hasPrefix("/") ? item.path : "",
            preview: item.preview,
            sourceType: item.kind == "document" ? "document" : "code",
            viewerKind: viewerKind(for: type)
        )
    }

    private static func artifact(from source: MenuSourcePresentation) -> MenuGuideArtifact {
        let previewText = source.previewLines.isEmpty ? source.quote : source.previewLines.joined(separator: "\n")
        let stablePath = source.fullSourcePath.isEmpty ? source.sourcePath : source.fullSourcePath
        let type = artifactType(
            for: source.kind,
            path: stablePath,
            sourceType: source.sourceType
        )
        return MenuGuideArtifact(
            id: "artifact:source:\(stablePath):\(source.title)",
            type: type,
            title: source.title.isEmpty ? source.sourcePath : source.title,
            subtitle: source.headingPath.isEmpty ? "주요 근거 미리보기" : source.headingPath,
            path: source.sourcePath,
            fullPath: source.fullSourcePath,
            preview: previewText,
            sourceType: source.sourceType,
            viewerKind: viewerKind(for: type)
        )
    }

    private static func artifactSubtitle(for kind: String) -> String {
        switch kind {
        case "document":
            return "문서 후보"
        case "filename":
            return "파일 후보"
        case "class":
            return "클래스 후보"
        case "function":
            return "함수 후보"
        default:
            return "관련 항목"
        }
    }

    private static func viewerKind(for type: String) -> String {
        switch type {
        case "code_file", "code_symbol":
            return "code"
        case "html", "html_document":
            return "html"
        case "document":
            return "document"
        case "image":
            return "image"
        case "video":
            return "video"
        case "web":
            return "web"
        default:
            return "text"
        }
    }

    private static func artifactType(
        for kind: String,
        path: String,
        sourceType: String = ""
    ) -> String {
        let loweredPath = path.lowercased()
        let loweredSourceType = sourceType.lowercased()
        if loweredPath.hasPrefix("http://") || loweredPath.hasPrefix("https://") {
            return "web"
        }
        if loweredPath.hasSuffix(".html") || loweredPath.hasSuffix(".htm") {
            return "html"
        }
        if loweredPath.hasSuffix(".png")
            || loweredPath.hasSuffix(".jpg")
            || loweredPath.hasSuffix(".jpeg")
            || loweredPath.hasSuffix(".gif")
            || loweredPath.hasSuffix(".webp")
            || loweredPath.hasSuffix(".heic")
            || loweredPath.hasSuffix(".svg") {
            return "image"
        }
        if loweredPath.hasSuffix(".mp4")
            || loweredPath.hasSuffix(".mov")
            || loweredPath.hasSuffix(".m4v")
            || loweredPath.hasSuffix(".webm") {
            return "video"
        }
        if loweredSourceType == "web" {
            return "web"
        }
        if loweredSourceType == "document" || kind == "document" {
            return "document"
        }
        if kind == "class" || kind == "function" || kind == "code_symbol" {
            return "code_symbol"
        }
        if kind == "filename" || loweredSourceType == "code" {
            return "code_file"
        }
        return "text"
    }

    private static func legacyGuidePayload(from response: MenuResponse) -> ServiceGuidePayload? {
        guard let directive = response.guideDirective else {
            return nil
        }
        let reasons = directive.missingSlots.map(Self.humanizeMissingSlot)
        let interactionMode = InteractionMode(rawValue: response.renderHints?.interactionMode ?? "") ?? .generalQuery
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
            targetDocument: response.exploration?.targetDocument ?? "",
            presentation: fallbackPresentation(
                response: response,
                exploration: response.exploration,
                interactionMode: interactionMode,
                responseText: response.response
            ),
            artifacts: fallbackArtifacts(response: response, exploration: response.exploration)
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
    private var refreshScheduled = false
    private unowned let viewModel: JarvisMenuBarViewModel

    init(viewModel: JarvisMenuBarViewModel) {
        self.viewModel = viewModel
        self.host = NSHostingController(
            rootView: JarvisGuideView(
                guide: viewModel.guide,
                onSelect: viewModel.selectExplorationItem,
                onClose: viewModel.closeGuidePanel,
                onToggleAutoClose: viewModel.toggleGuideAutoClose,
                onActivateWorkspaceSession: viewModel.activateGuideWorkspaceSession,
                onCloseWorkspaceSession: viewModel.closeGuideWorkspaceSession
            )
        )
        self.panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 780, height: 760),
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
                self?.scheduleRefresh()
            }
            .store(in: &cancellables)
    }

    private func scheduleRefresh() {
        guard !refreshScheduled else { return }
        refreshScheduled = true
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.refreshScheduled = false
            self.refresh()
        }
    }

    func refresh() {
        host.rootView = JarvisGuideView(
            guide: viewModel.guide,
            onSelect: viewModel.selectExplorationItem,
            onClose: viewModel.closeGuidePanel,
            onToggleAutoClose: viewModel.toggleGuideAutoClose,
            onActivateWorkspaceSession: viewModel.activateGuideWorkspaceSession,
            onCloseWorkspaceSession: viewModel.closeGuideWorkspaceSession
        )
        guard viewModel.shouldShowGuidePanel else {
            panel.orderOut(nil)
            return
        }
        resizePanelToFit()
        positionPanel()
        panel.orderFrontRegardless()
    }

    private func resizePanelToFit() {
        host.view.invalidateIntrinsicContentSize()
        host.view.layoutSubtreeIfNeeded()
        let fitting = host.view.fittingSize
        let targetSize = NSSize(
            width: min(max(fitting.width, 380), 780),
            height: min(max(fitting.height, 120), 820)
        )
        if panel.contentRect(forFrameRect: panel.frame).size != targetSize {
            panel.setContentSize(targetSize)
        }
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
    let onActivateWorkspaceSession: (String) -> Void
    let onCloseWorkspaceSession: (String) -> Void
    @State private var selectedWorkspaceTabID = ""

    private var presentation: MenuGuidePresentation? {
        guide.guidePresentation
    }

    private var workspacePresentation: MenuGuidePresentation? {
        guard let presentation else { return nil }
        let blocks = presentation.blocks.filter { $0.kind != "answer" }
        guard !blocks.isEmpty else { return nil }
        return MenuGuidePresentation(
            layout: presentation.layout,
            title: presentation.title,
            subtitle: presentation.subtitle,
            selectedArtifactID: presentation.selectedArtifactID,
            blocks: blocks
        )
    }

    private var shouldShowAssistantSection: Bool {
        !displayResponseText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var prefersExpandedWorkspaceWidth: Bool {
        workspacePresentation != nil
            || guide.hasWorkspaceSessions
            || !guide.currentArtifacts.isEmpty
            || !guide.citations.isEmpty
            || guide.sourcePresentation != nil
            || guide.hasClarification
    }

    private var showsFooterHint: Bool {
        workspacePresentation != nil
            || guide.hasWorkspaceSessions
            || guide.hasClarification
            || !guide.currentArtifacts.isEmpty
            || !guide.citations.isEmpty
            || guide.sourcePresentation != nil
            || guide.isLoading
            || guide.isStreaming
            || guide.partialTranscriptionActive
    }

    private var panelWidth: CGFloat {
        prefersExpandedWorkspaceWidth ? 760 : 480
    }

    var body: some View {
        Group {
            if guide.hasRenderableContent {
                VStack(alignment: .leading, spacing: 12) {
                    headerSection
                    if shouldShowAssistantSection {
                        assistantSection
                    } else if !guide.summaryText.isEmpty {
                        Text(guide.summaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else if !guide.ambientStatusText.isEmpty {
                        Text(guide.ambientStatusText)
                            .font(.callout)
                            .foregroundStyle(JarvisTheme.textPrimary)
                    }
                    if guide.hasClarification {
                        clarificationSection
                    }
                    if guide.hasWorkspaceSessions {
                        workspaceSessionStrip
                    }
                    if let workspacePresentation {
                        workspaceHeader(workspacePresentation)
                        workspaceSection(workspacePresentation)
                    } else if !guide.hasWorkspaceSessions,
                              guide.isLoading || guide.isStreaming || guide.partialTranscriptionActive {
                        workspaceSection(nil)
                    }
                    if showsFooterHint {
                        footerHint
                    }
                }
                .padding(14)
                .frame(width: panelWidth)
                .background(JarvisTheme.panelBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(JarvisTheme.border, lineWidth: 1)
                )
                .shadow(color: JarvisTheme.shadow, radius: 16, x: 0, y: 12)
            }
        }
        .padding(10)
        .background(JarvisTheme.appBackground)
        .tint(JarvisTheme.cyan)
        .preferredColorScheme(.dark)
    }

    private var headerSection: some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Jarvis Workspace")
                    .font(.headline)
                    .foregroundStyle(JarvisTheme.textPrimary)
                Text("응답, 자료, 근거를 요구사항에 맞게 조합해 표시합니다.")
                    .font(.caption)
                    .foregroundStyle(JarvisTheme.textSecondary)
            }
            Spacer()
            ToneBadge(title: guide.loopStage.title, color: JarvisTheme.cyan)
            if !guide.phaseLabel.isEmpty {
                ToneBadge(title: guide.phaseLabel, color: JarvisTheme.blue)
            }
            ToneBadge(
                title: guide.interactionMode.title,
                color: guide.interactionMode == .documentExploration ? JarvisTheme.amber : JarvisTheme.cyan
            )
            headerActionButton(
                systemName: guide.autoCloseDisabled ? "pin.fill" : "pin",
                tint: guide.autoCloseDisabled ? JarvisTheme.amber : JarvisTheme.textSecondary,
                accessibilityLabel: guide.autoCloseDisabled ? "워크스페이스 고정 해제" : "워크스페이스 고정",
                helpText: guide.autoCloseDisabled ? "현재 자동 닫기가 꺼져 있습니다. 다시 누르면 자동 닫기를 켭니다." : "현재 자동 닫기가 켜져 있습니다. 누르면 워크스페이스를 고정합니다."
            ) {
                onToggleAutoClose()
            }
            headerActionButton(
                systemName: "xmark",
                tint: JarvisTheme.red,
                background: JarvisTheme.red.opacity(0.12),
                accessibilityLabel: "워크스페이스 닫기",
                helpText: "Jarvis Workspace를 즉시 닫습니다."
            ) {
                onClose()
            }
        }
    }

    private func headerActionButton(
        systemName: String,
        tint: Color,
        background: Color = JarvisTheme.panelRaised.opacity(0.96),
        accessibilityLabel: String,
        helpText: String,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 28, height: 28)
                .background(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .fill(background)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 9, style: .continuous)
                        .stroke(tint.opacity(0.18), lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
        .help(helpText)
        .accessibilityLabel(accessibilityLabel)
    }

    private func workspaceHeader(_ presentation: MenuGuidePresentation) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(presentation.title)
                        .font(.title3.weight(.semibold))
                    if !presentation.subtitle.isEmpty {
                        Text(presentation.subtitle)
                            .font(.caption)
                            .foregroundStyle(JarvisTheme.textSecondary)
                    }
                }
                Spacer()
                ToneBadge(title: presentation.layout.replacingOccurrences(of: "_", with: " "), color: JarvisTheme.blue)
                ToneBadge(title: "\(guide.currentArtifacts.count) items", color: JarvisTheme.cyan)
                if !guide.citations.isEmpty {
                    ToneBadge(title: "\(guide.citations.count) evidence", color: JarvisTheme.amber)
                }
            }
            if let selected = guide.currentSelectedArtifact {
                HStack(spacing: 6) {
                    Image(systemName: iconName(for: selected))
                        .font(.caption)
                        .foregroundStyle(JarvisTheme.textSecondary)
                    Text(selected.title)
                        .font(.caption.weight(.semibold))
                    if !selected.subtitle.isEmpty {
                        Text(selected.subtitle)
                            .font(.caption)
                            .foregroundStyle(JarvisTheme.textSecondary)
                    }
                }
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(JarvisTheme.panelRaised.opacity(0.92))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(JarvisTheme.border.opacity(0.8), lineWidth: 1)
        )
    }

    private var assistantSection: some View {
        workspaceCard(title: "Assistant", subtitle: guide.phaseLabel, tint: JarvisTheme.cyan) {
            responseBlock
        }
    }

    private var workspaceSessionStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(guide.workspaceSessionItems) { session in
                    HStack(spacing: 6) {
                        Button {
                            onActivateWorkspaceSession(session.id)
                        } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(session.title)
                                    .font(.caption.weight(.semibold))
                                    .lineLimit(1)
                                if !session.subtitle.isEmpty {
                                    Text(session.subtitle)
                                        .font(.caption2)
                                        .foregroundStyle(JarvisTheme.textSecondary)
                                        .lineLimit(1)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(.plain)

                        Button {
                            onCloseWorkspaceSession(session.id)
                        } label: {
                            Image(systemName: "xmark")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundStyle(JarvisTheme.textSecondary)
                                .frame(width: 16, height: 16)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .frame(width: 190, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(guide.activeWorkspaceSessionID == session.id ? JarvisTheme.selection : JarvisTheme.panelMuted.opacity(0.92))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .stroke((guide.activeWorkspaceSessionID == session.id ? JarvisTheme.cyan : JarvisTheme.border).opacity(0.5), lineWidth: 1)
                    )
                }
            }
        }
    }

    @ViewBuilder
    private func workspaceSection(_ presentation: MenuGuidePresentation?) -> some View {
        if let presentation {
            switch presentation.layout {
            case "master_detail":
                masterDetailLayout(presentation)
            case "tabs":
                tabsLayout(presentation)
            case "gallery":
                galleryLayout(presentation)
            case "split":
                splitLayout(presentation)
            default:
                stackLayout(presentation)
            }
        } else {
            loadingWorkspace
        }
    }

    private var clarificationSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("보완 질문")
                .font(.caption.weight(.semibold))
                .foregroundStyle(JarvisTheme.amber)
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
                                .fill(JarvisTheme.amber.opacity(0.7))
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
                                    .fill(JarvisTheme.amber.opacity(0.12))
                            )
                            .overlay(
                                Capsule(style: .continuous)
                                    .stroke(JarvisTheme.amber.opacity(0.22), lineWidth: 1)
                            )
                    }
                }
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(JarvisTheme.panelMuted.opacity(0.96))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(JarvisTheme.amber.opacity(0.2), lineWidth: 1)
        )
    }

    private var loadingWorkspace: some View {
        HStack(spacing: 10) {
            ProgressView()
                .controlSize(.small)
            Text("실시간 후보와 뷰 구성을 준비하는 중입니다")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 24)
    }

    private var footerHint: some View {
        Text(guide.interactionMode == .documentExploration ? "예: 첫 번째 문서 열어줘, 이 문서 요약해줘, 근거만 보여줘" : "예: Avalon 관련 주요 소스 보여줘, 첫 번째 파일 열어줘, 이 함수 설명해줘")
            .font(.caption2)
            .foregroundStyle(.secondary)
    }

    private func masterDetailLayout(_ presentation: MenuGuidePresentation) -> some View {
        let answerBlock = presentation.blocks.first(where: { $0.kind == "answer" })
        let listBlock = presentation.blocks.first(where: { $0.kind == "list" })
        let detailBlock = presentation.blocks.first(where: { $0.kind == "detail" })
        let evidenceBlock = presentation.blocks.first(where: { $0.kind == "evidence" })

        return VStack(alignment: .leading, spacing: 12) {
            if let answerBlock {
                renderBlock(answerBlock)
            }
            HStack(alignment: .top, spacing: 12) {
                if let listBlock {
                    renderBlock(listBlock)
                        .frame(width: 260)
                }
                VStack(alignment: .leading, spacing: 12) {
                    if let detailBlock {
                        renderBlock(detailBlock)
                    }
                    if let evidenceBlock {
                        renderBlock(evidenceBlock)
                    }
                }
            }
        }
    }

    private func splitLayout(_ presentation: MenuGuidePresentation) -> some View {
        let answerBlock = presentation.blocks.first(where: { $0.kind == "answer" })
        let detailBlock = presentation.blocks.first(where: { $0.kind == "detail" })
        let evidenceBlock = presentation.blocks.first(where: { $0.kind == "evidence" })
        let listBlock = presentation.blocks.first(where: { $0.kind == "list" })

        return VStack(alignment: .leading, spacing: 12) {
            if let answerBlock {
                renderBlock(answerBlock)
            }
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 12) {
                    if let detailBlock {
                        renderBlock(detailBlock)
                    } else if let listBlock {
                        renderBlock(listBlock)
                    }
                }
                if let evidenceBlock {
                    renderBlock(evidenceBlock)
                        .frame(width: 280)
                }
            }
        }
    }

    private func galleryLayout(_ presentation: MenuGuidePresentation) -> some View {
        let answerBlock = presentation.blocks.first(where: { $0.kind == "answer" })
        let listBlock = presentation.blocks.first(where: { $0.kind == "list" })
        let detailBlock = presentation.blocks.first(where: { $0.kind == "detail" })
        let evidenceBlock = presentation.blocks.first(where: { $0.kind == "evidence" })

        return VStack(alignment: .leading, spacing: 12) {
            if let answerBlock {
                renderBlock(answerBlock)
            }
            if let listBlock {
                workspaceCard(title: listBlock.title, subtitle: listBlock.subtitle, tint: JarvisTheme.cyan) {
                    artifactGalleryBlock(listBlock)
                }
            }
            if let detailBlock {
                renderBlock(detailBlock)
            }
            if let evidenceBlock {
                renderBlock(evidenceBlock)
            }
        }
    }

    private func tabsLayout(_ presentation: MenuGuidePresentation) -> some View {
        let answerBlock = presentation.blocks.first(where: { $0.kind == "answer" })
        let tabBlocks = presentation.blocks.filter { $0.kind != "answer" }
        let activeBlock = activeTabBlock(for: presentation)

        return VStack(alignment: .leading, spacing: 12) {
            if let answerBlock {
                renderBlock(answerBlock)
            }
            if let activeBlock {
                workspaceCard(
                    title: activeBlock.title,
                    subtitle: activeBlock.subtitle,
                    tint: blockTint(for: activeBlock)
                ) {
                    VStack(alignment: .leading, spacing: 12) {
                        workspaceTabStrip(blocks: tabBlocks, activeBlockID: activeBlock.id)
                        blockContent(activeBlock)
                    }
                }
            }
        }
    }

    private func stackLayout(_ presentation: MenuGuidePresentation) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(presentation.blocks) { block in
                renderBlock(block)
            }
        }
    }

    @ViewBuilder
    private func renderBlock(_ block: MenuGuideBlock) -> some View {
        if isRenderableBlock(block) {
            workspaceCard(title: block.title, subtitle: block.subtitle, tint: blockTint(for: block)) {
                blockContent(block)
            }
        }
    }

    private func isRenderableBlock(_ block: MenuGuideBlock) -> Bool {
        switch block.kind {
        case "answer", "list", "detail", "evidence":
            return true
        default:
            return false
        }
    }

    private func blockTint(for block: MenuGuideBlock) -> Color {
        switch block.kind {
        case "answer":
            return JarvisTheme.cyan
        case "list":
            return JarvisTheme.blue
        case "detail":
            return JarvisTheme.cyan
        case "evidence":
            return JarvisTheme.amber
        default:
            return JarvisTheme.textMuted
        }
    }

    private func blockIconName(for block: MenuGuideBlock) -> String {
        switch block.kind {
        case "answer":
            return "text.bubble"
        case "list":
            return "square.grid.2x2"
        case "detail":
            return "rectangle.inset.filled.and.person.filled"
        case "evidence":
            return "checklist"
        default:
            return "square.text.square"
        }
    }

    @ViewBuilder
    private func blockContent(_ block: MenuGuideBlock) -> some View {
        switch block.kind {
        case "answer":
            responseBlock
        case "list":
            artifactListBlock(block)
        case "detail":
            artifactDetailBlock(block)
        case "evidence":
            citationBlock(block)
        default:
            EmptyView()
        }
    }

    private func workspaceCard<Content: View>(
        title: String,
        subtitle: String,
        tint: Color,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint)
                if !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.caption2)
                        .foregroundStyle(JarvisTheme.textSecondary)
                }
                Spacer()
            }
            content()
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(JarvisTheme.panelRaised.opacity(0.92))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(tint.opacity(0.22), lineWidth: 1)
        )
    }

    private var responseBlock: some View {
        let metrics = responseLayoutMetrics(for: displayResponseText)
        return Group {
            if metrics.needsScroll {
                ScrollView {
                    responseTextContent
                }
                .frame(height: metrics.height)
            } else {
                responseTextContent
            }
        }
    }

    private var responseTextContent: some View {
        Text(displayResponseText)
            .font(.callout)
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func responseLayoutMetrics(for text: String) -> (height: CGFloat, needsScroll: Bool) {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return (height: 52, needsScroll: false)
        }
        let attributes: [NSAttributedString.Key: Any] = [
            .font: NSFont.preferredFont(forTextStyle: .body)
        ]
        let measureWidth = max(320, panelWidth - 80)
        let bounds = NSAttributedString(string: trimmed, attributes: attributes)
            .boundingRect(
                with: NSSize(width: measureWidth, height: CGFloat.greatestFiniteMagnitude),
                options: [.usesLineFragmentOrigin, .usesFontLeading]
            )
        let measuredHeight = ceil(bounds.height) + 8
        let maxHeight: CGFloat = 220
        let clampedHeight = min(max(measuredHeight, 52), maxHeight)
        return (height: clampedHeight, needsScroll: measuredHeight > maxHeight)
    }

    private var displayResponseText: String {
        if !guide.liveResponseText.isEmpty {
            return guide.liveResponseText
        }
        if !guide.finalResponseText.isEmpty {
            return guide.finalResponseText
        }
        return guide.exportableResponseText
    }

    private func artifactListBlock(_ block: MenuGuideBlock) -> some View {
        let artifacts = guide.artifacts(for: block)
        return ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(artifacts) { artifact in
                    Button {
                        if let item = guide.explorationItem(for: artifact.id) {
                            onSelect(item)
                        } else {
                            guide.selectArtifact(artifact.id)
                        }
                    } label: {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: iconName(for: artifact))
                                .frame(width: 18)
                                .foregroundStyle(JarvisTheme.cyan)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(artifact.title)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.primary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                if !artifact.subtitle.isEmpty {
                                    Text(artifact.subtitle)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                                if !artifact.path.isEmpty {
                                    Text(artifact.path)
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                            Spacer()
                        }
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(guide.currentSelectedArtifact?.id == artifact.id ? JarvisTheme.selection : JarvisTheme.panelMuted.opacity(0.92))
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(minHeight: 220, maxHeight: 420)
    }

    private func artifactGalleryBlock(_ block: MenuGuideBlock) -> some View {
        let artifacts = guide.artifacts(for: block)
        let columns = [
            GridItem(.adaptive(minimum: 132, maximum: 180), spacing: 10)
        ]
        return ScrollView {
            LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
                ForEach(artifacts) { artifact in
                    Button {
                        if let item = guide.explorationItem(for: artifact.id) {
                            onSelect(item)
                        } else {
                            guide.selectArtifact(artifact.id)
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 8) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 10, style: .continuous)
                                    .fill(JarvisTheme.panelMuted.opacity(0.92))
                                if artifact.viewerKind == "image",
                                   let imagePath = resolvedOpenPath(for: artifact),
                                   let image = NSImage(contentsOfFile: imagePath) {
                                    Image(nsImage: image)
                                        .resizable()
                                        .scaledToFill()
                                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                                        .clipped()
                                } else {
                                    Image(systemName: iconName(for: artifact))
                                        .font(.system(size: 24, weight: .semibold))
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .frame(height: 112)
                            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))

                            Text(artifact.title)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.primary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .lineLimit(2)
                        }
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(guide.currentSelectedArtifact?.id == artifact.id ? JarvisTheme.selection : JarvisTheme.panelMuted.opacity(0.92))
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(minHeight: 220, maxHeight: 360)
    }

    @ViewBuilder
    private func artifactDetailBlock(_ block: MenuGuideBlock) -> some View {
        if let artifact = guide.artifacts(for: block).first ?? guide.currentSelectedArtifact {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top, spacing: 10) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(artifact.title)
                            .font(.subheadline.weight(.semibold))
                        if !artifact.subtitle.isEmpty {
                            Text(artifact.subtitle)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    if artifactCanOpen(artifact) {
                        Button(artifact.type == "web" ? "링크 열기" : "열기") {
                            openArtifact(artifact)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                }
                artifactPreview(artifact)
            }
        } else {
            Text(block.emptyState)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, minHeight: 160, alignment: .center)
        }
    }

    private func workspaceTabStrip(
        blocks: [MenuGuideBlock],
        activeBlockID: String
    ) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(blocks) { block in
                    Button {
                        selectedWorkspaceTabID = block.id
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: blockIconName(for: block))
                                .font(.caption2)
                            Text(block.title)
                                .font(.caption.weight(.semibold))
                            if block.kind == "list" {
                                Text("\(guide.artifacts(for: block).count)")
                                    .font(.caption2.weight(.bold))
                                    .foregroundStyle(.secondary)
                            } else if block.kind == "evidence" {
                                Text("\(guide.citations(for: block).count)")
                                    .font(.caption2.weight(.bold))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .background(
                            Capsule(style: .continuous)
                                .fill(activeBlockID == block.id ? blockTint(for: block).opacity(0.18) : JarvisTheme.panelMuted.opacity(0.92))
                        )
                        .overlay(
                            Capsule(style: .continuous)
                                .stroke(activeBlockID == block.id ? blockTint(for: block).opacity(0.32) : JarvisTheme.border.opacity(0.4), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.bottom, 2)
        }
    }

    private func activeTabBlock(for presentation: MenuGuidePresentation) -> MenuGuideBlock? {
        let tabBlocks = presentation.blocks.filter { $0.kind != "answer" }
        if let selected = tabBlocks.first(where: { $0.id == selectedWorkspaceTabID }) {
            return selected
        }
        return defaultTabBlock(from: tabBlocks)
    }

    private func defaultTabBlock(from blocks: [MenuGuideBlock]) -> MenuGuideBlock? {
        blocks.first(where: { $0.kind == "detail" })
            ?? blocks.first(where: { $0.kind == "list" })
            ?? blocks.first(where: { $0.kind == "evidence" })
            ?? blocks.first
    }

    @ViewBuilder
    private func artifactPreview(_ artifact: MenuGuideArtifact) -> some View {
        switch artifact.viewerKind {
        case "image":
            if let imagePath = resolvedOpenPath(for: artifact),
               let image = NSImage(contentsOfFile: imagePath) {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity, maxHeight: 320)
            } else {
                fallbackTextPreview(for: artifact, monospaced: false)
            }
        case "code":
            codePreview(for: artifact)
        case "html":
            htmlPreview(for: artifact)
        case "web":
            webPreview(for: artifact)
        case "video":
            videoPreview(for: artifact)
        case "document":
            documentPreview(for: artifact)
        default:
            fallbackTextPreview(for: artifact, monospaced: artifact.viewerKind == "document")
        }
    }

    private func codePreview(for artifact: MenuGuideArtifact) -> some View {
        ArtifactCodeView(artifact: artifact, lines: codeLines(for: artifact))
    }

    @ViewBuilder
    private func htmlPreview(for artifact: MenuGuideArtifact) -> some View {
        if let source = webContentSource(for: artifact) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "doc.richtext")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("HTML Viewer")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                ArtifactWebView(source: source)
                    .frame(minHeight: 260, maxHeight: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        } else {
            fallbackTextPreview(for: artifact, monospaced: false)
        }
    }

    @ViewBuilder
    private func webPreview(for artifact: MenuGuideArtifact) -> some View {
        if let source = webContentSource(for: artifact) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "globe")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("Web Viewer")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                ArtifactWebView(source: source)
                    .frame(minHeight: 260, maxHeight: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        } else {
            fallbackTextPreview(for: artifact, monospaced: false)
        }
    }

    @ViewBuilder
    private func videoPreview(for artifact: MenuGuideArtifact) -> some View {
        if let url = mediaURL(for: artifact) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "video")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("Video Viewer")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                ArtifactVideoView(url: url)
                    .frame(minHeight: 240, maxHeight: 340)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        } else {
            fallbackTextPreview(for: artifact, monospaced: false)
        }
    }

    @ViewBuilder
    private func documentPreview(for artifact: MenuGuideArtifact) -> some View {
        let ext = fileExtension(for: artifact)
        if ext == "pdf", let fileURL = localFileURL(for: artifact) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "doc.richtext")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("PDF Viewer")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                ArtifactPDFView(url: fileURL)
                    .frame(minHeight: 260, maxHeight: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        } else if isTextDocumentExtension(ext) {
            fallbackTextPreview(for: artifact, monospaced: ext != "rtf")
        } else if let quickLookURL = quickLookFileURL(for: artifact) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "doc.viewfinder")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("Quick Look Viewer")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                ArtifactQuickLookView(url: quickLookURL)
                    .frame(minHeight: 280, maxHeight: 380)
                    .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        } else {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("Document Viewer")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Spacer()
                }
                Text("이 문서 형식은 내장 미리보기가 제한적입니다. 외부 앱으로 열어 전체 내용을 확인할 수 있습니다.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if !artifact.preview.isEmpty {
                    fallbackTextPreview(for: artifact, monospaced: false)
                }
            }
        }
    }

    private func fallbackTextPreview(for artifact: MenuGuideArtifact, monospaced: Bool) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if !artifact.path.isEmpty {
                    Text(artifact.path)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .textSelection(.enabled)
                }
                Text(previewText(for: artifact))
                    .font(monospaced ? .system(.caption, design: .monospaced) : .caption)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(minHeight: 180, maxHeight: 340)
    }

    private func citationBlock(_ block: MenuGuideBlock) -> some View {
        let citations = guide.citations(for: block)
        return ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(citations) { citation in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .top, spacing: 6) {
                            Text(citation.label)
                                .font(.caption.monospacedDigit().weight(.semibold))
                                .foregroundStyle(JarvisTheme.amber)
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
                            .fill(JarvisTheme.panelMuted.opacity(0.96))
                    )
                }
            }
        }
        .frame(minHeight: 120, maxHeight: 260)
    }

    private func previewText(for artifact: MenuGuideArtifact) -> String {
        if !artifact.preview.isEmpty {
            return artifact.preview
        }
        switch artifact.viewerKind {
        case "code":
            return "코드 미리보기를 불러오지 못했습니다."
        case "html":
            return "HTML 미리보기를 불러오지 못했습니다."
        case "document":
            return "문서 미리보기를 불러오지 못했습니다."
        case "video":
            return "비디오 미리보기는 외부 플레이어로 엽니다."
        case "web":
            return "웹 자료는 브라우저에서 열어 확인할 수 있습니다."
        default:
            return "표시 가능한 미리보기가 없습니다."
        }
    }

    private func iconName(for artifact: MenuGuideArtifact) -> String {
        switch artifact.viewerKind {
        case "code":
            return "chevron.left.forwardslash.chevron.right"
        case "html":
            return "doc.richtext"
        case "document":
            return "doc.text"
        case "image":
            return "photo"
        case "video":
            return "video"
        case "web":
            return "globe"
        default:
            return "square.text.square"
        }
    }

    private func artifactCanOpen(_ artifact: MenuGuideArtifact) -> Bool {
        resolvedOpenPath(for: artifact) != nil
    }

    private func resolvedOpenPath(for artifact: MenuGuideArtifact) -> String? {
        let candidate = artifact.fullPath.isEmpty ? artifact.path : artifact.fullPath
        guard !candidate.isEmpty else { return nil }
        if candidate.hasPrefix("http://") || candidate.hasPrefix("https://") {
            return candidate
        }
        if artifact.type == "web" || artifact.sourceType == "web" {
            return candidate
        }
        return candidate.hasPrefix("/") ? candidate : nil
    }

    private func openArtifact(_ artifact: MenuGuideArtifact) {
        guard let target = resolvedOpenPath(for: artifact) else { return }
        openSourcePath(target, sourceType: artifact.sourceType.isEmpty ? artifact.type : artifact.sourceType)
    }

    private func openSourcePath(_ path: String, sourceType: String) {
        guard !path.isEmpty else { return }
        if sourceType == "web" || path.hasPrefix("http://") || path.hasPrefix("https://"),
           let url = URL(string: path) {
            NSWorkspace.shared.open(url)
            return
        }
        NSWorkspace.shared.open(URL(fileURLWithPath: path))
    }

    private func codeLines(for artifact: MenuGuideArtifact) -> [String] {
        let source = previewText(for: artifact)
        let rawLines = source.components(separatedBy: .newlines)
        if rawLines.isEmpty {
            return ["표시 가능한 코드가 없습니다."]
        }
        return Array(rawLines.prefix(120))
    }

    private func webContentSource(for artifact: MenuGuideArtifact) -> ArtifactWebContentSource? {
        if let target = resolvedOpenPath(for: artifact) {
            if target.hasPrefix("http://") || target.hasPrefix("https://"),
               let url = URL(string: target) {
                return .url(url)
            }
            if artifact.viewerKind == "html" {
                let fileURL = URL(fileURLWithPath: target)
                return .file(fileURL)
            }
        }
        if artifact.viewerKind == "html", !artifact.preview.isEmpty {
            return .html(artifact.preview)
        }
        return nil
    }

    private func localFileURL(for artifact: MenuGuideArtifact) -> URL? {
        guard let path = resolvedOpenPath(for: artifact), path.hasPrefix("/") else { return nil }
        return URL(fileURLWithPath: path)
    }

    private func mediaURL(for artifact: MenuGuideArtifact) -> URL? {
        guard let target = resolvedOpenPath(for: artifact) else { return nil }
        if target.hasPrefix("http://") || target.hasPrefix("https://") {
            return URL(string: target)
        }
        return URL(fileURLWithPath: target)
    }

    private func quickLookFileURL(for artifact: MenuGuideArtifact) -> URL? {
        guard let fileURL = localFileURL(for: artifact) else { return nil }
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return nil }
        return fileURL
    }

    private func fileExtension(for artifact: MenuGuideArtifact) -> String {
        let candidate = artifact.fullPath.isEmpty ? artifact.path : artifact.fullPath
        return URL(fileURLWithPath: candidate).pathExtension.lowercased()
    }

    private func isTextDocumentExtension(_ ext: String) -> Bool {
        [
            "md", "markdown", "txt", "rtf", "json", "yaml", "yml", "csv", "tsv", "xml", "log"
        ].contains(ext)
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

private struct ArtifactCodeView: View {
    let artifact: MenuGuideArtifact
    let lines: [String]

    var body: some View {
        ScrollView([.vertical, .horizontal]) {
            VStack(alignment: .leading, spacing: 0) {
                header
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                        ArtifactCodeLineRow(index: index, line: line)
                    }
                }
            }
        }
        .frame(minHeight: 220, maxHeight: 360)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(JarvisTheme.panelMuted.opacity(0.98))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(JarvisTheme.border.opacity(0.5), lineWidth: 1)
        )
    }

    @ViewBuilder
    private var header: some View {
        if !artifact.path.isEmpty {
            HStack(spacing: 6) {
                Image(systemName: "chevron.left.forwardslash.chevron.right")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(artifact.path)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .textSelection(.enabled)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(JarvisTheme.panelRaised.opacity(0.82))
        }
    }
}

private struct ArtifactCodeLineRow: View {
    let index: Int
    let line: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text("\(index + 1)")
                .font(.system(.caption2, design: .monospaced))
                .foregroundStyle(.secondary)
                .frame(width: 34, alignment: .trailing)
            Text(line.isEmpty ? " " : line)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 3)
        .background(index.isMultiple(of: 2) ? JarvisTheme.panelRaised.opacity(0.42) : Color.clear)
    }
}

private struct ArtifactPDFView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> PDFView {
        let pdfView = PDFView()
        pdfView.autoScales = true
        pdfView.displayMode = .singlePageContinuous
        pdfView.displaysPageBreaks = true
        pdfView.backgroundColor = .clear
        return pdfView
    }

    func updateNSView(_ pdfView: PDFView, context: Context) {
        if pdfView.document?.documentURL != url {
            pdfView.document = PDFDocument(url: url)
        }
    }
}

private struct ArtifactQuickLookView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> QLPreviewView {
        let previewView = QLPreviewView(frame: .zero)!
        previewView.shouldCloseWithWindow = true
        previewView.autostarts = false
        return previewView
    }

    func updateNSView(_ previewView: QLPreviewView, context: Context) {
        let currentURL = (previewView.previewItem as? NSURL)?.absoluteURL
        guard currentURL != url else { return }
        previewView.previewItem = url as NSURL
    }

    static func dismantleNSView(_ previewView: QLPreviewView, coordinator: ()) {
        previewView.close()
    }
}

private struct ArtifactVideoView: NSViewRepresentable {
    let url: URL

    func makeNSView(context: Context) -> AVPlayerView {
        let playerView = AVPlayerView()
        playerView.controlsStyle = .floating
        playerView.videoGravity = .resizeAspect
        return playerView
    }

    func updateNSView(_ playerView: AVPlayerView, context: Context) {
        let currentURL = (playerView.player?.currentItem?.asset as? AVURLAsset)?.url
        guard currentURL != url else { return }
        playerView.player = AVPlayer(url: url)
    }
}

private enum ArtifactWebContentSource: Equatable {
    case url(URL)
    case file(URL)
    case html(String)
}

private struct ArtifactWebView: NSViewRepresentable {
    let source: ArtifactWebContentSource

    func makeNSView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.setValue(false, forKey: "drawsBackground")
        webView.allowsMagnification = true
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        switch source {
        case .url(let url):
            if webView.url != url {
                webView.load(URLRequest(url: url))
            }
        case .file(let url):
            if webView.url != url {
                webView.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
            }
        case .html(let html):
            webView.loadHTMLString(html, baseURL: nil)
        }
    }
}
