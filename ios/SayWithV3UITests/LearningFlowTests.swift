import XCTest

@MainActor
final class LearningFlowTests:XCTestCase {
    private func launch()->XCUIApplication {
        let app=XCUIApplication();app.launchArguments=["--backend-url","http://localhost:8086"];app.launch()
        if app.buttons["exitLesson"].waitForExistence(timeout:2) {
            app.buttons["更多学习操作"].tap();app.buttons["退出本次任务"].tap();app.buttons["退出本次任务"].tap()
        }
        if app.buttons["createAccount"].waitForExistence(timeout:2) {app.buttons["createAccount"].tap()}
        let home=XCTNSPredicateExpectation(predicate:NSPredicate {_,_ in app.buttons["startLearning"].exists || app.buttons["startReview"].exists},object:app)
        XCTAssertEqual(XCTWaiter.wait(for:[home],timeout:15),.completed)
        return app
    }
    private func ready(_ button:XCUIElement,timeout:TimeInterval=15) {
        XCTAssertTrue(button.waitForExistence(timeout:timeout))
        let wait=XCTNSPredicateExpectation(predicate:NSPredicate(format:"enabled == true"),object:button)
        XCTAssertEqual(XCTWaiter.wait(for:[wait],timeout:timeout),.completed)
    }
    private func shot(_ app:XCUIApplication,_ name:String) {
        let attachment=XCTAttachment(screenshot:app.screenshot());attachment.name=name;attachment.lifetime = .keepAlways;add(attachment)
    }
    private func reply(_ app:XCUIApplication,_ text:String) {
        let field=app.descendants(matching:.any)["typedReply"].firstMatch
        if !field.exists {app.buttons["也可以输入英文练习"].tap()}
        XCTAssertTrue(field.waitForExistence(timeout:3));field.tap();field.typeText(text)
        ready(app.buttons["sendReply"]);app.buttons["sendReply"].tap()
    }
    func testLearningGuidedIndependentFeedback() {
        let app=launch();shot(app,"v6-home");app.buttons["startLearning"].tap()
        XCTAssertTrue(app.descendants(matching:.any)["englishExpression"].firstMatch.waitForExistence(timeout:30))
        ready(app.buttons["recordButton"])
        shot(app,"v6-learning")
        addUIInterruptionMonitor(withDescription:"Microphone") {alert in
            let allowed=alert.buttons.matching(NSPredicate(format:"label CONTAINS 'Allow' OR label CONTAINS '允许' OR label == 'OK' OR label == '好'" )).firstMatch
            if allowed.exists {allowed.tap();return true};return false
        }
        app.buttons["recordButton"].tap()
        XCTAssertTrue(app.staticTexts["audioStatus"].waitForExistence(timeout:3))
        sleep(1);app.buttons["recordButton"].tap()
        ready(app.buttons["nextPhase"])
        XCTAssertTrue(app.buttons["playOwnRecording"].exists)
        app.buttons["playOwnRecording"].tap()
        app.buttons["nextPhase"].tap()
        XCTAssertTrue(app.buttons["hintButton"].waitForExistence(timeout:15))
        shot(app,"v6-guided")
        app.buttons["hintButton"].tap();app.buttons["hint-pattern"].tap()
        XCTAssertTrue(app.descendants(matching:.any)["hintText"].firstMatch.waitForExistence(timeout:5))
        app.buttons["关闭"].tap()
        for i in 0..<3 {
            reply(app,"How about \(15+i)?")
            ready(app.buttons["nextGuidedRound"]);app.buttons["nextGuidedRound"].tap()
        }
        ready(app.buttons["independentTask"]);app.buttons["independentTask"].tap()
        let phase=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label == %@", "独立应用"),object:app.staticTexts["phaseTitle"])
        XCTAssertEqual(XCTWaiter.wait(for:[phase],timeout:10),.completed)
        ready(app.buttons["recordButton"])
        XCTAssertFalse(app.buttons["hintButton"].exists)
        XCTAssertFalse(app.descendants(matching:.any)["englishExpression"].firstMatch.exists)
        shot(app,"v6-independent")
        reply(app,"How about two?")
        ready(app.buttons["finishTask"]);app.buttons["finishTask"].tap()
        ready(app.buttons["finishLearning"])
        XCTAssertTrue(app.buttons["finishLearning"].exists)
        shot(app,"v6-feedback")
        app.buttons["finishLearning"].tap()
    }
    func testReviewStartsWithoutRepeatingLearning() throws {
        let app=launch()
        guard app.buttons["startReview"].exists else {throw XCTSkip("Review UI test requires seeded fixture profile")};shot(app,"v6-home-review");ready(app.buttons["startReview"]);app.buttons["startReview"].tap()
        ready(app.buttons["recordButton"])
        XCTAssertFalse(app.descendants(matching:.any)["englishExpression"].firstMatch.exists)
        XCTAssertFalse(app.buttons["hintButton"].exists)
        shot(app,"v6-review")
        reply(app,"How about two?")
        ready(app.buttons["finishTask"]);app.buttons["finishTask"].tap()
        ready(app.buttons["finishLearning"])
        XCTAssertEqual(app.buttons["finishLearning"].label,"完成复习")
        shot(app,"v6-review-result");app.buttons["finishLearning"].tap()
    }
    func testBackPreservesLearningProgress() {
        let app=launch();app.buttons["startLearning"].tap()
        XCTAssertTrue(app.descendants(matching:.any)["englishExpression"].firstMatch.waitForExistence(timeout:30))
        ready(app.buttons["exitLesson"]);app.buttons["exitLesson"].tap()
        ready(app.buttons["startLearning"]);app.buttons["startLearning"].tap()
        XCTAssertTrue(app.descendants(matching:.any)["englishExpression"].firstMatch.waitForExistence(timeout:10))
    }
    func testGlobalFeedbackSubmissionAndHistory() {
        let app=launch()
        ready(app.buttons["feedbackOrb"]);app.buttons["feedbackOrb"].tap()
        let field=app.descendants(matching:.any)["feedbackContent"].firstMatch
        XCTAssertTrue(field.waitForExistence(timeout:5));field.tap();field.typeText("新版UI反馈闭环验证")
        app.buttons["submitFeedback"].tap()
        XCTAssertTrue(app.staticTexts["feedbackSubmitted"].waitForExistence(timeout:15))
        shot(app,"v6-feedback-composer")
        app.buttons["closeFeedback"].tap()
        app.tabBars.buttons["进展"].tap()
        ready(app.buttons["feedbackOrb"]);app.buttons["feedbackOrb"].tap()
        XCTAssertTrue(app.navigationBars["意见反馈"].waitForExistence(timeout:5))
        app.buttons["closeFeedback"].tap()
        app.tabBars.buttons["学习"].tap();app.buttons["startLearning"].tap()
        XCTAssertTrue(app.descendants(matching:.any)["englishExpression"].firstMatch.waitForExistence(timeout:30))
        ready(app.buttons["feedbackOrb"]);app.buttons["feedbackOrb"].tap()
        XCTAssertTrue(app.navigationBars["意见反馈"].waitForExistence(timeout:5));app.buttons["closeFeedback"].tap()
        let viewport=app.scrollViews["lessonContent"]
        XCTAssertGreaterThan(viewport.frame.height,app.frame.height*0.5)
        shot(app,"v6-compact-learning")
        app.buttons["exitLesson"].tap()
    }
    func testWordLookupNotebookFlow() {
        let app=launch();app.buttons["startLearning"].tap()
        XCTAssertTrue(app.descendants(matching:.any)["englishExpression"].firstMatch.waitForExistence(timeout:30))
        ready(app.buttons["about"].firstMatch);app.buttons["about"].firstMatch.tap()
        XCTAssertTrue(app.buttons["addToNotebook"].waitForExistence(timeout:15))
        let visible=XCTNSPredicateExpectation(predicate:NSPredicate(format:"hittable == true"),object:app.buttons["addToNotebook"])
        XCTAssertEqual(XCTWaiter.wait(for:[visible],timeout:5),.completed)
        shot(app,"word-lookup")
        if !app.buttons["addToNotebook"].label.contains("已在生词本") {ready(app.buttons["addToNotebook"]);app.buttons["addToNotebook"].tap()}
        let saved=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@","已在生词本"),object:app.buttons["addToNotebook"])
        XCTAssertEqual(XCTWaiter.wait(for:[saved],timeout:15),.completed)
        app.buttons["closeDictionary"].tap();app.buttons["exitLesson"].tap()
        app.tabBars.buttons["我的"].tap();app.buttons["notebookEntry"].tap()
        XCTAssertTrue(app.navigationBars["生词本"].waitForExistence(timeout:5))
        ready(app.buttons["notebook-about"]);shot(app,"notebook-list");app.buttons["notebook-about"].tap()
        XCTAssertTrue(app.navigationBars["生词"].waitForExistence(timeout:5));shot(app,"notebook-detail")
        ready(app.buttons["about"].firstMatch);app.buttons["about"].firstMatch.tap()
        XCTAssertTrue(app.buttons["addToNotebook"].waitForExistence(timeout:15))
        let alreadySaved=XCTNSPredicateExpectation(predicate:NSPredicate(format:"label CONTAINS %@","已在生词本"),object:app.buttons["addToNotebook"])
        XCTAssertEqual(XCTWaiter.wait(for:[alreadySaved],timeout:15),.completed);app.buttons["closeDictionary"].tap()
        app.buttons["removeNotebookWord"].tap();XCTAssertTrue(app.buttons["confirmRemoveNotebookWord"].firstMatch.waitForExistence(timeout:5));app.buttons["confirmRemoveNotebookWord"].firstMatch.tap()
        XCTAssertTrue(app.navigationBars["生词本"].waitForExistence(timeout:10))
        let removed=XCTNSPredicateExpectation(predicate:NSPredicate(format:"exists == false"),object:app.buttons["notebook-about"])
        XCTAssertEqual(XCTWaiter.wait(for:[removed],timeout:10),.completed)
    }
    func testHomeNavigation() {
        let app=launch()
        XCTAssertTrue(app.staticTexts["homeTitle"].isHittable)
        shot(app,"v6-home")
        XCTAssertFalse(app.tabBars.buttons["地图"].exists)
        XCTAssertTrue(app.tabBars.buttons["学习"].exists)
        app.tabBars.buttons["进展"].tap()
        XCTAssertTrue(app.navigationBars["学习进展"].exists)
        XCTAssertTrue(app.tabBars.buttons["我的"].exists)
        app.tabBars.buttons["我的"].tap()
        XCTAssertTrue(app.buttons["mineFeedbackEntry"].exists)
        shot(app,"v6-my")
        app.buttons["mineFeedbackEntry"].tap()
        XCTAssertTrue(app.navigationBars["意见反馈"].waitForExistence(timeout:5));app.buttons["closeFeedback"].tap()
        app.buttons["学习设置"].tap()
        XCTAssertTrue(app.navigationBars["学习设置"].waitForExistence(timeout:5))
        ready(app.buttons["feedbackOrb"]);app.buttons["feedbackOrb"].tap()
        XCTAssertTrue(app.navigationBars["意见反馈"].waitForExistence(timeout:5));app.buttons["closeFeedback"].tap()
        XCTAssertTrue(app.navigationBars["学习设置"].exists);app.buttons["关闭"].tap()
    }
}
