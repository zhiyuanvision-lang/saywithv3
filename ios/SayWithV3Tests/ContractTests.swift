import XCTest
@testable import SayWithV3

final class ContractTests: XCTestCase {
    @MainActor
    func testCancelledRecordingStartNeverOpensMicrophone() async {
        let audio=AudioController()
        let start=Task {try await audio.start()}
        start.cancel()
        do {try await start.value;XCTFail("Cancelled start must not record")}
        catch is CancellationError {}
        catch {XCTFail("Unexpected error: \(error)")}
        XCTAssertFalse(audio.recording)
        XCTAssertNil(audio.lastRecording)
    }
    func testHoldRecordingReleaseAndDuplicateEnd() {
        var gesture=HoldRecordingGesture()
        XCTAssertTrue(gesture.update(verticalTranslation:0))
        XCTAssertFalse(gesture.update(verticalTranslation:-20))
        XCTAssertEqual(gesture.finish(verticalTranslation:-20),.send)
        XCTAssertNil(gesture.finish(verticalTranslation:0))
        XCTAssertFalse(gesture.active)
    }
    func testHoldRecordingSwipeCancellationAndReturnToSend() {
        var gesture=HoldRecordingGesture()
        _ = gesture.update(verticalTranslation:0)
        _ = gesture.update(verticalTranslation:-60)
        XCTAssertTrue(gesture.cancelling)
        XCTAssertEqual(gesture.finish(verticalTranslation:-60),.cancel)
        _ = gesture.update(verticalTranslation:0)
        _ = gesture.update(verticalTranslation:-80)
        _ = gesture.update(verticalTranslation:-30)
        XCTAssertFalse(gesture.cancelling)
        XCTAssertEqual(gesture.finish(verticalTranslation:-30),.send)
    }
    func testInterruptedHoldCannotSubmit() {
        var gesture=HoldRecordingGesture()
        _ = gesture.update(verticalTranslation:0)
        gesture.reset()
        XCTAssertNil(gesture.finish(verticalTranslation:0))
        XCTAssertTrue(gesture.update(verticalTranslation:0))
    }
    func testPrivateFactsHaveNoLearnerViewField() throws {
        let json = #"{"session_id":"s1","lesson_id":"l1","lesson_version":1,"task_id":"t1","phase":"independent_application","instruction":"Arrange","learner_facts":{"available_times":["14:00"]},"available_actions":["speak"],"materials":[],"fixture":false}"#
        let decoder=JSONDecoder();decoder.keyDecodingStrategy = .convertFromSnakeCase
        let view=try decoder.decode(LessonView.self,from:Data(json.utf8))
        XCTAssertEqual(view.learnerFacts["available_times"]?.text,"14:00")
        XCTAssertTrue(view.materials.isEmpty)
    }
    func testServerURLsRejectCredentialsAndQuery() throws {
        XCTAssertThrowsError(try API.validatedURL("https://secret@example.com"))
        XCTAssertThrowsError(try API.validatedURL("https://example.com?token=secret"))
        XCTAssertEqual(try API.validatedURL("https://example.com").host,"example.com")
    }
    func testCloudBasePathAppliesToJSONAndAudio() async throws {
        let base=try API.validatedURL("https://api.saywith.zhiyuanv.com/learning")
        let api=API(base:base,token:nil)
        let profile=try await api.endpoint("v1/profile")
        XCTAssertEqual(profile.path,"/learning/v1/profile")
        let audio=try await api.endpoint("/v1/media/a")
        XCTAssertEqual(audio.path,"/learning/v1/media/a")
        let query=try await api.endpoint("v1/curriculum/targets?stage=A2")
        XCTAssertEqual(query.query,"stage=A2")
        do {_ = try await api.endpoint("../private");XCTFail("Traversal must be rejected")} catch {}
    }
    func testJobTerminalNeedsReview() throws {
        let decoder=JSONDecoder();decoder.keyDecodingStrategy = .convertFromSnakeCase
        let job=try decoder.decode(Job.self,from:Data(#"{"job_id":"j1","state":"needs_review","row_version":2,"error":{"message":"Task quality failed"}}"#.utf8))
        XCTAssertTrue(job.terminal)
        XCTAssertEqual(job.label,"课程需要审核")
    }
    func testDictionaryTokensKeepContractionsPunctuationAndChinese() {
        let text="I'm free at four-thirty. 可以吗？\nDon't worry."
        let tokens=LookupText.tokens(text)
        XCTAssertEqual(tokens.joined(),text)
        XCTAssertTrue(tokens.contains("I'm"));XCTAssertTrue(tokens.contains("four-thirty"))
        XCTAssertTrue(tokens.contains("Don't"));XCTAssertTrue(tokens.contains("\n"))
    }

}
