import XCTest
@testable import SayWithV3

final class ContractTests: XCTestCase {
    func testSpeakingCueSeparatesFactsFromIntentionWithoutLosingLegacyText() {
        let cue=SpeakingCue("情境：你唱歌，朋友弹吉他。\n轮到你：向朋友确认分工。")
        XCTAssertEqual(cue.context,"你唱歌，朋友弹吉他。")
        XCTAssertEqual(cue.intention,"向朋友确认分工。")
        XCTAssertEqual(SpeakingCue("提议下午三点见面。").intention,"提议下午三点见面。")
        XCTAssertEqual(SpeakingCue.learnerTitle("确认共同任务（诊断课）"),"确认共同任务")
    }

    func testDictionaryPlacementReservesLoadedHeightNearBottom() {
        let bounds=CGRect(x:0,y:0,width:390,height:844)
        let anchor=CGRect(x:120,y:0,width:55,height:22)
        let insets=UIEdgeInsets(top:47,left:0,bottom:34,right:0)
        for y in [CGFloat(90),420,650,760] {
            let word=anchor.offsetBy(dx:0,dy:y)
            let origin=DictionaryPlacement.origin(anchor:word,bounds:bounds,safeInsets:insets)
            XCTAssertGreaterThanOrEqual(origin.y,55)
            XCTAssertLessThanOrEqual(origin.y+440,806)
            // Both the loading card and the expanded definition use this same origin.
            XCTAssertEqual(CGRect(origin:origin,size:CGSize(width:350,height:120)).minY,
                           CGRect(origin:origin,size:CGSize(width:350,height:440)).minY)
        }
    }

    func testHintParagraphsKeepEveryAlternativeAndExample() {
        let source="把空白换成自己的内容：\nI'm sorry, but I can't make it at ___. Could we do ___ instead?\nThat time doesn't work for me. I'm free at ___."
        let blocks=HintParagraphs.blocks(source)
        XCTAssertEqual(blocks.count,3)
        XCTAssertEqual(blocks[2],"That time doesn't work for me. I'm free at ___.")
        let example=HintParagraphs.blocks("向 Chris 说明十点不方便：\nI'm sorry, but I can't make it at ten. Could we do three instead?\n抱歉，十点不行。三点可以吗？")
        XCTAssertEqual(example.count,3)
        XCTAssertTrue(example[1].hasSuffix("instead?"))
    }
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
