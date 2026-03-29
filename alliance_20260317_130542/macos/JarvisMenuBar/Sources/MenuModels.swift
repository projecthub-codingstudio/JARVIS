import Foundation

struct MenuCitation: Codable, Identifiable {
    let label: String
    let sourcePath: String
    let fullSourcePath: String
    let sourceType: String
    let quote: String
    let state: String
    let relevanceScore: Double
    let headingPath: String

    var id: String { "\(label)-\(sourcePath)" }

    private enum CodingKeys: String, CodingKey {
        case label
        case sourcePath = "source_path"
        case fullSourcePath = "full_source_path"
        case sourceType = "source_type"
        case quote
        case state
        case relevanceScore = "relevance_score"
        case headingPath = "heading_path"
    }
}

struct MenuSourcePresentation: Codable {
    let kind: String
    let sourcePath: String
    let fullSourcePath: String
    let sourceType: String
    let headingPath: String
    let quote: String
    let title: String
    let previewLines: [String]

    private enum CodingKeys: String, CodingKey {
        case kind
        case sourcePath = "source_path"
        case fullSourcePath = "full_source_path"
        case sourceType = "source_type"
        case headingPath = "heading_path"
        case quote
        case title
        case previewLines = "preview_lines"
    }
}

struct MenuStatus: Codable {
    let mode: String
    let safeMode: Bool
    let degradedMode: Bool
    let generationBlocked: Bool
    let writeBlocked: Bool
    let rebuildIndexRequired: Bool

    private enum CodingKeys: String, CodingKey {
        case mode
        case safeMode = "safe_mode"
        case degradedMode = "degraded_mode"
        case generationBlocked = "generation_blocked"
        case writeBlocked = "write_blocked"
        case rebuildIndexRequired = "rebuild_index_required"
    }
}

struct MenuRenderHints: Codable {
    let responseType: String
    let primarySourceType: String
    let sourceProfile: String
    let interactionMode: String
    let citationCount: Int
    let truncated: Bool

    private enum CodingKeys: String, CodingKey {
        case responseType = "response_type"
        case primarySourceType = "primary_source_type"
        case sourceProfile = "source_profile"
        case interactionMode = "interaction_mode"
        case citationCount = "citation_count"
        case truncated
    }
}

struct MenuExplorationItem: Codable, Identifiable {
    let label: String
    let kind: String
    let path: String
    let score: Double
    let preview: String

    var id: String { "\(kind)-\(label)-\(path)" }
}

struct MenuExplorationState: Codable {
    let mode: String
    let targetFile: String
    let targetDocument: String
    let fileCandidates: [MenuExplorationItem]
    let documentCandidates: [MenuExplorationItem]
    let classCandidates: [MenuExplorationItem]
    let functionCandidates: [MenuExplorationItem]

    private enum CodingKeys: String, CodingKey {
        case mode
        case targetFile = "target_file"
        case targetDocument = "target_document"
        case fileCandidates = "file_candidates"
        case documentCandidates = "document_candidates"
        case classCandidates = "class_candidates"
        case functionCandidates = "function_candidates"
    }
}

struct MenuGuideDirective: Codable {
    let intent: String
    let skill: String
    let loopStage: String
    let clarificationPrompt: String
    let missingSlots: [String]
    let suggestedReplies: [String]
    let shouldHold: Bool

    private enum CodingKeys: String, CodingKey {
        case intent
        case skill
        case loopStage = "loop_stage"
        case clarificationPrompt = "clarification_prompt"
        case missingSlots = "missing_slots"
        case suggestedReplies = "suggested_replies"
        case shouldHold = "should_hold"
    }
}

struct PendingClarificationContext {
    let originalUserQuery: String
    let clarificationPrompt: String
    let intent: String
    let skill: String
    let missingSlots: [String]
    let suggestedReplies: [String]

    var isActive: Bool {
        !clarificationPrompt.isEmpty || !missingSlots.isEmpty
    }

    func mergedQuery(with answer: String) -> String {
        var components = [originalUserQuery]
        if !clarificationPrompt.isEmpty {
            components.append("보완 질문: \(clarificationPrompt)")
        }
        components.append("사용자 답변: \(answer)")
        if !missingSlots.isEmpty {
            components.append("보완 필요 항목: \(missingSlots.joined(separator: ", "))")
        }
        if !intent.isEmpty {
            components.append("intent: \(intent)")
        }
        if !skill.isEmpty {
            components.append("skill: \(skill)")
        }
        if !suggestedReplies.isEmpty {
            components.append("참고 가능한 응답 예시: \(suggestedReplies.joined(separator: ", "))")
        }
        return components
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: ". ")
    }
}

struct MenuResponse: Codable {
    let query: String
    let response: String
    let spokenResponse: String?
    let hasEvidence: Bool
    let citations: [MenuCitation]
    let status: MenuStatus?
    let renderHints: MenuRenderHints?
    let exploration: MenuExplorationState?
    let guideDirective: MenuGuideDirective?
    let fullResponsePath: String?
    let sourcePresentation: MenuSourcePresentation?

    private enum CodingKeys: String, CodingKey {
        case query
        case response
        case spokenResponse = "spoken_response"
        case hasEvidence = "has_evidence"
        case citations
        case status
        case renderHints = "render_hints"
        case exploration
        case guideDirective = "guide_directive"
        case fullResponsePath = "full_response_path"
        case sourcePresentation = "source_presentation"
    }
}

struct ServiceAnswerPayload: Codable {
    let text: String
    let spokenText: String?
    let hasEvidence: Bool
    let citationCount: Int
    let fullResponsePath: String?

    private enum CodingKeys: String, CodingKey {
        case text
        case spokenText = "spoken_text"
        case hasEvidence = "has_evidence"
        case citationCount = "citation_count"
        case fullResponsePath = "full_response_path"
    }
}

struct ServiceGuidePayload: Codable {
    let loopStage: String
    let clarificationPrompt: String
    let suggestedReplies: [String]
    let clarificationOptions: [String]
    let missingSlots: [String]
    let clarificationReasons: [String]
    let intent: String
    let skill: String
    let shouldHold: Bool
    let hasClarification: Bool
    let interactionMode: String
    let explorationMode: String
    let targetFile: String
    let targetDocument: String

    private enum CodingKeys: String, CodingKey {
        case loopStage = "loop_stage"
        case clarificationPrompt = "clarification_prompt"
        case suggestedReplies = "suggested_replies"
        case clarificationOptions = "clarification_options"
        case missingSlots = "missing_slots"
        case clarificationReasons = "clarification_reasons"
        case intent
        case skill
        case shouldHold = "should_hold"
        case hasClarification = "has_clarification"
        case interactionMode = "interaction_mode"
        case explorationMode = "exploration_mode"
        case targetFile = "target_file"
        case targetDocument = "target_document"
    }
}

struct ServiceAskResponse: Codable {
    let response: MenuResponse
    let answer: ServiceAnswerPayload?
    let guide: ServiceGuidePayload?
}

struct TTSPrefetchResponse: Codable {
    let started: Bool
    let predictedText: String

    private enum CodingKeys: String, CodingKey {
        case started
        case predictedText = "predicted_text"
    }
}

struct ExportResponse: Codable {
    let destination: String
    let approved: Bool
    let success: Bool
    let errorMessage: String

    private enum CodingKeys: String, CodingKey {
        case destination
        case approved
        case success
        case errorMessage = "error_message"
    }
}

struct TranscriptionResponse: Codable {
    let transcript: String
}

struct SpeechResponse: Codable {
    let audioPath: String

    private enum CodingKeys: String, CodingKey {
        case audioPath = "audio_path"
    }
}

struct NormalizationResponse: Codable {
    let normalizedQuery: String

    private enum CodingKeys: String, CodingKey {
        case normalizedQuery = "normalized_query"
    }
}

struct TranscriptRepairPayload: Codable {
    let rawText: String
    let repairedText: String
    let displayText: String
    let finalQuery: String

    private enum CodingKeys: String, CodingKey {
        case rawText = "raw_text"
        case repairedText = "repaired_text"
        case displayText = "display_text"
        case finalQuery = "final_query"
    }
}

struct ProgressResponse: Codable {
    let message: String
}

struct HealthResponse: Codable {
    let healthy: Bool
    let message: String
    let checks: [String: Bool]
    let details: [String: String]
    let failedChecks: [String]
    let statusLevel: String
    let chunkCount: Int
    let knowledgeBasePath: String
    let bridgeMode: String

    private enum CodingKeys: String, CodingKey {
        case healthy
        case message
        case checks
        case details
        case failedChecks = "failed_checks"
        case statusLevel = "status_level"
        case chunkCount = "chunk_count"
        case knowledgeBasePath = "knowledge_base_path"
        case bridgeMode = "bridge_mode"
    }
}

struct CommandEnvelope: Codable {
    let kind: String
    let queryResult: MenuResponse?
    let navigationResult: MenuExplorationState?
    let normalizationResult: NormalizationResponse?
    let exportResult: ExportResponse?
    let transcriptionResult: TranscriptionResponse?
    let speechResult: SpeechResponse?
    let healthResult: HealthResponse?
    let progressResult: ProgressResponse?
    let error: String?
    let token: String?
    let score: Double?

    private enum CodingKeys: String, CodingKey {
        case kind
        case queryResult = "query_result"
        case navigationResult = "navigation_result"
        case normalizationResult = "normalization_result"
        case exportResult = "export_result"
        case transcriptionResult = "transcription_result"
        case speechResult = "speech_result"
        case healthResult = "health_result"
        case progressResult = "progress_result"
        case error
        case token
        case score
    }
}

/// Represents a streaming event from the Python bridge server.
enum StreamEvent {
    case token(String)
    case done(ServiceAskResponse?)
    case error(String)
}
