import XCTest
@testable import JarvisMenuBar

@MainActor
final class WakePhraseMatcherTests: XCTestCase {
    func testWakePhraseRequiresExplicitHeyPrefix() {
        XCTAssertTrue(JarvisMenuBarViewModel.isWakePhraseOnly("헤이 자비스"))
        XCTAssertTrue(JarvisMenuBarViewModel.isWakePhraseOnly("hey jarvis"))
        XCTAssertFalse(JarvisMenuBarViewModel.isWakePhraseOnly("자비스"))
        XCTAssertFalse(JarvisMenuBarViewModel.isWakePhraseOnly("오늘 일정 알려줘"))
    }

    func testWakePhraseRemainderOnlyExistsForHeyJarvisPrefix() {
        XCTAssertEqual(
            JarvisMenuBarViewModel.wakePhraseRemainder(in: "헤이 자비스 오늘 일정 알려줘"),
            "오늘 일정 알려줘"
        )
        XCTAssertNil(JarvisMenuBarViewModel.wakePhraseRemainder(in: "자비스 오늘 일정 알려줘"))
    }

    func testExitPhraseRequiresExplicitByePrefix() {
        XCTAssertTrue(JarvisMenuBarViewModel.isExitPhraseOnly("바이 자비스"))
        XCTAssertTrue(JarvisMenuBarViewModel.isExitPhraseOnly("bye jarvis"))
        XCTAssertFalse(JarvisMenuBarViewModel.isExitPhraseOnly("자비스 종료"))
    }
}
