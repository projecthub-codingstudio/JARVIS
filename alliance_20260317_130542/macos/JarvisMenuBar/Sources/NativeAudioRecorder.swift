import AVFoundation
import AudioToolbox

/// Records microphone audio to a WAV file using AVAudioEngine.
///
/// AVAudioEngine handles format negotiation with the audio hardware.
/// The engine stays running between recordings to keep the mic warm.
/// `record()` toggles the file-writing flag only.
final class NativeAudioRecorder: @unchecked Sendable {
    private lazy var engine = AVAudioEngine()
    private var audioFile: AVAudioFile?
    private var outputURL: URL?
    private var isWriting = false
    private var recordingContinuation: CheckedContinuation<URL, Error>?
    private var stopTimer: DispatchWorkItem?
    private var currentDeviceID: String?
    private var engineReady = false

    // Two-Stage VAD
    enum VadState { case idle, listening, tentativeEnd, confirmedEnd }
    private var vadState: VadState = .idle
    var onVadStateChanged: ((VadState) -> Void)?

    // Adaptive VAD thresholds
    private var speechThreshold: Float = 0.01
    private var silenceThreshold: Float = 0.005
    private var noiseFloorCalibrated = false
    private var noiseFloorSamples: [Float] = []
    private let calibrationFrames = 10
    private var silenceStartTime: CFAbsoluteTime = 0
    private var recordingStartTime: CFAbsoluteTime = 0
    private let tentativeSilenceSec: Double =
        Double(ProcessInfo.processInfo.environment["JARVIS_VAD_TENTATIVE_SILENCE_SECONDS"] ?? "0.9") ?? 0.9
    private let confirmedSilenceSec: Double =
        Double(ProcessInfo.processInfo.environment["JARVIS_VAD_CONFIRMED_SILENCE_SECONDS"] ?? "1.8") ?? 1.8
    private let minRecordingSec: Double =
        Double(ProcessInfo.processInfo.environment["JARVIS_VAD_MIN_RECORDING_SECONDS"] ?? "1.2") ?? 1.2
    private var totalFramesWritten = 0
    private var noSpeechWarned = false

    /// Callback for guidance messages (e.g., wrong device selected).
    var onGuidanceMessage: ((String) -> Void)?

    /// Callback for live microphone input level normalized to 0...1.
    var onInputLevelChanged: ((Float) -> Void)?

    /// Callback for wake word audio chunks (16kHz mono Int16 PCM, ~80ms each).
    /// Set this to feed audio to the Python wake word detector.
    var onWakeWordAudioChunk: ((Data) -> Void)?

    /// Callback for live partial speech recognition while recording.
    var onLiveAudioBuffer: ((AVAudioPCMBuffer) -> Void)?

    /// Cached downsample ratio (native rate / 16000), set during activate()
    private var _wakeDownsampleRatio: Int = 3  // default 48kHz/16kHz

    var isSessionRunning: Bool { engine.isRunning }

    // MARK: - Activation

    func activate(deviceID: String?) throws {
        let needsReconfigure = !engineReady || currentDeviceID != deviceID
        guard needsReconfigure else { return }


        // Safely tear down previous engine state (only if previously started)
        if engineReady {
            if engine.isRunning { engine.stop() }
            engine.inputNode.removeTap(onBus: 0)
        }

        if let deviceID, !deviceID.isEmpty {
            setInputDevice(uniqueID: deviceID)
        }

        let inputNode = engine.inputNode
        let nativeFormat = inputNode.outputFormat(forBus: 0)
        appLog("Input native format: \(nativeFormat)")

        // Use standard mono format for the tap — engine converts from native.
        // Native format may be deinterleaved/multi-channel which causes issues.
        let tapFormat = AVAudioFormat(standardFormatWithSampleRate: nativeFormat.sampleRate, channels: 1)!
        appLog("Tap format: \(tapFormat)")

        inputNode.installTap(onBus: 0, bufferSize: 4096, format: tapFormat) { [weak self] buffer, _ in
            self?.processAudioBuffer(buffer)
        }

        engine.prepare()
        try engine.start()
        currentDeviceID = deviceID
        engineReady = true
        // Cache downsample ratio for wake word audio
        let nativeRate = engine.inputNode.outputFormat(forBus: 0).sampleRate
        _wakeDownsampleRatio = max(1, Int(nativeRate / 16000))
        appLog("AVAudioEngine started")
    }

    // MARK: - Recording

    func record(deviceID: String?, duration: Double) async throws -> URL {
        try activate(deviceID: deviceID)
        stopTimer?.cancel()

        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".jarvis", isDirectory: true)
            .appendingPathComponent("recordings", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("ptt.wav")
        outputURL = url

        // Write mono WAV at native sample rate. Tap delivers mono interleaved float32.
        // ffmpeg converts to 16kHz after recording.
        let sampleRate = engine.inputNode.outputFormat(forBus: 0).sampleRate
        let wavFormat = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 1)!
        audioFile = try AVAudioFile(forWriting: url, settings: wavFormat.settings)
        appLog("WAV file created: \(sampleRate)Hz mono")

        return try await withCheckedThrowingContinuation { continuation in
            self.recordingContinuation = continuation
            self.totalFramesWritten = 0
            self.vadState = .idle
            self.silenceStartTime = 0
            self.recordingStartTime = CFAbsoluteTimeGetCurrent()
            self.noiseFloorCalibrated = false
            self.noiseFloorSamples = []
            self.speechThreshold = 0.01
            self.silenceThreshold = 0.005
            self.noSpeechWarned = false
            self.isWriting = true

            appLog(
                "Recording armed: max=\(String(format: "%.1f", duration))s, tentativeSilence=\(String(format: "%.1f", self.tentativeSilenceSec))s, confirmedSilence=\(String(format: "%.1f", self.confirmedSilenceSec))s"
            )

            let timer = DispatchWorkItem { [weak self] in
                self?.finishRecording()
            }
            stopTimer = timer
            DispatchQueue.main.asyncAfter(deadline: .now() + duration, execute: timer)
        }
    }

    func cancel() {
        stopTimer?.cancel()
        finishRecording()
    }

    func deactivate() {
        guard engineReady else { return }  // Don't touch engine if never started
        isWriting = false
        engine.inputNode.removeTap(onBus: 0)
        if engine.isRunning { engine.stop() }
        let levelCallback = onInputLevelChanged
        DispatchQueue.main.async { levelCallback?(0) }
        audioFile = nil
        engineReady = false
    }

    // MARK: - Private

    private func finishRecording() {
        stopTimer?.cancel()
        stopTimer = nil
        isWriting = false
        vadState = .idle
        silenceStartTime = 0
        totalFramesWritten = 0
        onVadStateChanged = nil
        onGuidanceMessage = nil
        let levelCallback = onInputLevelChanged
        DispatchQueue.main.async { levelCallback?(0) }
        onInputLevelChanged = nil
        onLiveAudioBuffer = nil
        audioFile = nil  // closes the WAV file

        guard let url = outputURL, let cont = recordingContinuation else { return }
        recordingContinuation = nil
        outputURL = nil

        // Convert to 16kHz mono on a background thread to avoid blocking UI.
        DispatchQueue.global(qos: .userInitiated).async {
            let rawURL = url.deletingPathExtension().appendingPathExtension("raw.wav")
            // Remove stale raw file from previous conversion
            try? FileManager.default.removeItem(at: rawURL)
            do {
                try FileManager.default.moveItem(at: url, to: rawURL)
                let process = Process()
                process.executableURL = URL(fileURLWithPath: "/opt/homebrew/bin/ffmpeg")
                process.arguments = ["-i", rawURL.path, "-ar", "16000", "-ac", "1", "-y", url.path]
                process.standardOutput = FileHandle.nullDevice
                process.standardError = FileHandle.nullDevice
                try process.run()
                process.waitUntilExit()
                if process.terminationStatus == 0 {
                    try? FileManager.default.removeItem(at: rawURL)
                    appLog("Converted to 16kHz mono via ffmpeg")
                } else {
                    try? FileManager.default.moveItem(at: rawURL, to: url)
                    appLog("ffmpeg conversion failed")
                }
            } catch {
                if FileManager.default.fileExists(atPath: rawURL.path) {
                    try? FileManager.default.moveItem(at: rawURL, to: url)
                }
                appLog("finishRecording error: \(error)")
            }
            cont.resume(returning: url)
        }
    }

    private func setInputDevice(uniqueID: String) {
        var propSize: UInt32 = 0
        var devicesAddress = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyDevices,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain
        )
        AudioObjectGetPropertyDataSize(
            AudioObjectID(kAudioObjectSystemObject), &devicesAddress, 0, nil, &propSize
        )
        let deviceCount = Int(propSize) / MemoryLayout<AudioDeviceID>.size
        var deviceIDs = [AudioDeviceID](repeating: 0, count: deviceCount)
        AudioObjectGetPropertyData(
            AudioObjectID(kAudioObjectSystemObject), &devicesAddress, 0, nil, &propSize, &deviceIDs
        )

        for devID in deviceIDs {
            var uidAddress = AudioObjectPropertyAddress(
                mSelector: kAudioDevicePropertyDeviceUID,
                mScope: kAudioObjectPropertyScopeGlobal,
                mElement: kAudioObjectPropertyElementMain
            )
            var uidCF: Unmanaged<CFString>?
            var uidSize = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
            let status = AudioObjectGetPropertyData(devID, &uidAddress, 0, nil, &uidSize, &uidCF)

            guard status == noErr, let uid = uidCF?.takeRetainedValue() as String? else { continue }

            if uid == uniqueID {
                var inputAddress = AudioObjectPropertyAddress(
                    mSelector: kAudioHardwarePropertyDefaultInputDevice,
                    mScope: kAudioObjectPropertyScopeGlobal,
                    mElement: kAudioObjectPropertyElementMain
                )
                var mutableDevID = devID
                AudioObjectSetPropertyData(
                    AudioObjectID(kAudioObjectSystemObject), &inputAddress, 0, nil,
                    UInt32(MemoryLayout<AudioDeviceID>.size), &mutableDevID
                )
                appLog("CoreAudio input set to device ID=\(devID) (UID=\(uniqueID))")
                return
            }
        }
        appLog("CoreAudio device not found for UID: \(uniqueID)")
    }

    /// Called by AVAudioEngine tap — buffer is at native format.
    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) {
        let frameCount = Int(buffer.frameLength)
        guard frameCount > 0, let channelData = buffer.floatChannelData?[0] else { return }

        // --- Wake word audio forwarding (only when NOT recording) ---
        if let wakeCallback = onWakeWordAudioChunk, !isWriting {
            // Downsample float32 to Int16 at ~16kHz (ratio cached on activation)
            let ratio = max(1, _wakeDownsampleRatio)
            let outputCount = frameCount / ratio
            if outputCount > 0 {
                var int16Samples = [Int16](repeating: 0, count: outputCount)
                for i in 0..<outputCount {
                    let idx = i * ratio
                    if idx < frameCount {
                        let sample = max(-1.0, min(1.0, channelData[idx]))
                        int16Samples[i] = Int16(sample * 32767)
                    }
                }
                let pcmData = Data(bytes: &int16Samples, count: outputCount * 2)
                DispatchQueue.global(qos: .utility).async {
                    wakeCallback(pcmData)
                }
            }
            return  // Don't process VAD when in wake word mode
        }

        // --- Recording mode ---
        guard isWriting, let file = audioFile else { return }
        onLiveAudioBuffer?(buffer)

        // --- VAD ---
        var sumSquares: Float = 0
        for i in 0..<frameCount {
            sumSquares += channelData[i] * channelData[i]
        }
        let rms = sqrtf(sumSquares / Float(frameCount))
        let inputLevel = normalizedInputLevel(from: rms)
        if let levelCallback = onInputLevelChanged {
            DispatchQueue.main.async {
                levelCallback(inputLevel)
            }
        }
        totalFramesWritten += 1
        let now = CFAbsoluteTimeGetCurrent()
        let previousState = vadState
        let elapsed = now - recordingStartTime

        if !noiseFloorCalibrated {
            noiseFloorSamples.append(rms)
            if noiseFloorSamples.count >= calibrationFrames {
                let avgNoise = noiseFloorSamples.reduce(0, +) / Float(noiseFloorSamples.count)
                silenceThreshold = max(0.005, avgNoise * 1.3)
                speechThreshold = max(0.01, avgNoise * 2.0)
                noiseFloorCalibrated = true
                appLog("Noise calibrated: floor=\(String(format: "%.4f", avgNoise)) → silence<\(String(format: "%.4f", silenceThreshold)), speech>\(String(format: "%.4f", speechThreshold))")

                if avgNoise < 0.0001 {
                    let msg = "선택한 입력 장치에서 소리가 감지되지 않습니다. 다른 마이크 장치를 선택해 주세요."
                    let callback = onGuidanceMessage
                    DispatchQueue.main.async { callback?(msg) }
                }
            }
            // Debug: log RMS every 50 frames (~1s) to diagnose threshold issues
        } else {
            switch vadState {
            case .idle:
                if rms >= speechThreshold {
                    vadState = .listening; silenceStartTime = 0
                } else if !noSpeechWarned && elapsed >= 10 {
                    noSpeechWarned = true
                    let msg = "10초 동안 음성이 감지되지 않았습니다. 마이크에 가까이 말씀해 주세요."
                    let callback = onGuidanceMessage
                    DispatchQueue.main.async { callback?(msg) }
                }
            case .listening:
                if rms < silenceThreshold {
                    if silenceStartTime == 0 { silenceStartTime = now }
                    if now - silenceStartTime >= tentativeSilenceSec { vadState = .tentativeEnd }
                } else { silenceStartTime = 0 }
            case .tentativeEnd:
                if rms >= speechThreshold {
                    vadState = .listening; silenceStartTime = 0
                } else if now - silenceStartTime >= confirmedSilenceSec && elapsed >= minRecordingSec {
                    vadState = .confirmedEnd
                    stopTimer?.cancel()
                    notifyVadState(.confirmedEnd)
                    DispatchQueue.main.async { [weak self] in self?.finishRecording() }
                    return
                }
            case .confirmedEnd: return
            }
            if vadState != previousState {
                notifyVadState(vadState)
            }
        }

        // --- Write to file ---
        do {
            try file.write(from: buffer)
        } catch {
            appLog("WAV write error: \(error.localizedDescription)")
        }
    }

    private func notifyVadState(_ state: VadState) {
        let callback = onVadStateChanged
        DispatchQueue.main.async { callback?(state) }
    }

    private func normalizedInputLevel(from rms: Float) -> Float {
        let safeRMS = max(rms, 0.000_001)
        let db = 20 * log10f(safeRMS)
        let dbNormalized = max(0, min(1, (db + 52) / 34))

        let thresholdNormalized: Float
        if noiseFloorCalibrated {
            let dynamicRange = max((speechThreshold * 3.2) - silenceThreshold, 0.002)
            thresholdNormalized = max(0, min(1, (rms - silenceThreshold) / dynamicRange))
        } else {
            thresholdNormalized = 0
        }

        return powf(max(dbNormalized, thresholdNormalized), 0.72)
    }
}
