import XCTest
@testable import JarvisMenuBar

@MainActor
final class GuideAmbientPanelTests: XCTestCase {
    func testAmbientSessionStatusKeepsPanelVisible() {
        let guide = JarvisGuideState()

        guide.updateRuntimeState(
            isLoading: false,
            isStreaming: false,
            isSpeaking: false,
            voiceLoopEnabled: true,
            wakeWordEnabled: true,
            partialTranscriptionActive: false,
            ambientStatusText: "자비스 세션 활성화됨. 명령을 말씀해 주세요."
        )

        XCTAssertTrue(guide.shouldShowPanel())
    }

    func testIdleWakeWordArmingDoesNotShowPanelWithoutAmbientStatus() {
        let guide = JarvisGuideState()

        guide.updateRuntimeState(
            isLoading: false,
            isStreaming: false,
            isSpeaking: false,
            voiceLoopEnabled: false,
            wakeWordEnabled: true,
            partialTranscriptionActive: false,
            ambientStatusText: ""
        )

        XCTAssertFalse(guide.shouldShowPanel())
    }
}
