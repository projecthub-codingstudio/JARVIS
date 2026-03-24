import Foundation

struct MenuCitation: Codable, Identifiable {
    let label: String
    let sourcePath: String
    let sourceType: String
    let quote: String
    let state: String
    let relevanceScore: Double

    var id: String { "\(label)-\(sourcePath)" }

    private enum CodingKeys: String, CodingKey {
        case label
        case sourcePath = "source_path"
        case sourceType = "source_type"
        case quote
        case state
        case relevanceScore = "relevance_score"
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

struct MenuResponse: Codable {
    let query: String
    let response: String
    let hasEvidence: Bool
    let citations: [MenuCitation]
    let status: MenuStatus?
    let renderHints: MenuRenderHints?
    let exploration: MenuExplorationState?
    let fullResponsePath: String?

    private enum CodingKeys: String, CodingKey {
        case query
        case response
        case hasEvidence = "has_evidence"
        case citations
        case status
        case renderHints = "render_hints"
        case exploration
        case fullResponsePath = "full_response_path"
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
        case error
        case token
        case score
    }
}

/// Represents a streaming event from the Python bridge server.
enum StreamEvent {
    case token(String)
    case done(MenuResponse?)
    case error(String)
}
