import XCTest
@testable import JarvisMenuBar

final class WakeCommandSilenceGateTests: XCTestCase {
    func testSilenceMustBeSustainedLongEnough() {
        var gate = WakeCommandSilenceGate(
            silenceThreshold: 0.01,
            requiredDuration: 0.35
        )

        XCTAssertFalse(gate.register(level: 0.009, at: 0.00))
        XCTAssertFalse(gate.register(level: 0.008, at: 0.20))
        XCTAssertTrue(gate.register(level: 0.007, at: 0.36))
    }

    func testSpeechResetsPendingSilenceWindow() {
        var gate = WakeCommandSilenceGate(
            silenceThreshold: 0.01,
            requiredDuration: 0.30
        )

        XCTAssertFalse(gate.register(level: 0.008, at: 0.00))
        XCTAssertFalse(gate.register(level: 0.015, at: 0.18))
        XCTAssertFalse(gate.register(level: 0.009, at: 0.30))
        XCTAssertFalse(gate.register(level: 0.008, at: 0.52))
        XCTAssertTrue(gate.register(level: 0.007, at: 0.63))
    }
}
