import AVFoundation
import Foundation
import Speech

final class LiveSpeechTranscriber {
    private let recognizer: SFSpeechRecognizer?
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var isAuthorized = false
    private var latestTranscript = ""

    var onPartialTranscript: (@Sendable (String) -> Void)?

    init(localeIdentifier: String = "ko-KR") {
        recognizer = SFSpeechRecognizer(locale: Locale(identifier: localeIdentifier))
    }

    func requestAuthorizationIfNeeded() async -> Bool {
        if isAuthorized {
            return true
        }

        let status = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { authStatus in
                continuation.resume(returning: authStatus)
            }
        }

        isAuthorized = status == .authorized
        return isAuthorized
    }

    func start() async {
        guard await requestAuthorizationIfNeeded() else {
            return
        }
        guard let recognizer, recognizer.isAvailable else {
            return
        }

        stop()

        latestTranscript = ""
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.shouldReportPartialResults = true
        request.requiresOnDeviceRecognition = false
        self.request = request

        task = recognizer.recognitionTask(with: request) { [weak self] result, _ in
            guard let self, let result else { return }
            let transcript = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !transcript.isEmpty, transcript != self.latestTranscript else { return }
            self.latestTranscript = transcript
            let callback = self.onPartialTranscript
            DispatchQueue.main.async {
                callback?(transcript)
            }
        }
    }

    func append(_ buffer: AVAudioPCMBuffer) {
        request?.append(buffer)
    }

    @MainActor
    func finish() async -> String {
        request?.endAudio()
        try? await Task.sleep(for: .milliseconds(250))
        let transcript = latestTranscript.trimmingCharacters(in: .whitespacesAndNewlines)
        task?.cancel()
        request = nil
        task = nil
        return transcript
    }

    func stop() {
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
    }
}
