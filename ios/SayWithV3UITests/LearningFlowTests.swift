import XCTest

final class LearningFlowTests: XCTestCase {
    func testLearningPracticeIndependentFlow() {
        let app=XCUIApplication();app.launch()
        if app.buttons["createAccount"].waitForExistence(timeout:3) {app.buttons["createAccount"].tap()}
        if app.buttons["回到今日学习"].waitForExistence(timeout:3) {app.buttons["回到今日学习"].tap()}
        XCTAssertTrue(app.buttons["startLearning"].waitForExistence(timeout:15))
        app.buttons["startLearning"].tap()
        XCTAssertTrue(app.textFields["personalExpression"].waitForExistence(timeout:30))
        XCTAssertTrue(app.staticTexts["englishExpression"].exists)
        app.textFields["personalExpression"].tap();app.textFields["personalExpression"].typeText("How about Friday?")
        app.buttons["hideAnswer"].tap()
        XCTAssertFalse(app.staticTexts["englishExpression"].exists)
        app.buttons["recordLearning"].tap()
        XCTAssertTrue(app.buttons["nextPhase"].waitForExistence(timeout:5))
        app.buttons["nextPhase"].tap()
        XCTAssertTrue(app.buttons["independentTask"].waitForExistence(timeout:10))
        app.buttons["也可以输入英文练习"].tap()
        let reply=app.descendants(matching:.any)["typedReply"].firstMatch
        XCTAssertTrue(reply.waitForExistence(timeout:3));reply.tap();reply.typeText("How about two?")
        app.buttons["sendReply"].tap()
        sleep(2)
        app.buttons["independentTask"].tap()
        XCTAssertTrue(app.buttons["finishTask"].waitForExistence(timeout:10))
        let independentReply=app.descendants(matching:.any)["typedReply"].firstMatch
        if !independentReply.exists {app.buttons["也可以输入英文练习"].tap()}
        independentReply.tap();independentReply.typeText("How about two?")
        app.buttons["sendReply"].tap();sleep(2)
        app.buttons["finishTask"].tap()
        XCTAssertTrue(app.buttons["回到今日学习"].waitForExistence(timeout:10))
        XCTAssertTrue(app.staticTexts["本次证据不足，暂不更新能力。"].exists)
        app.buttons["回到今日学习"].tap()
    }
    func testAccountScreenIsUsable() {
        let app=XCUIApplication();app.launch()
        if app.buttons["createAccount"].waitForExistence(timeout:5) {
            XCTAssertTrue(app.textFields["backendURL"].exists)
            XCTAssertTrue(app.buttons["createAccount"].isEnabled)
        } else {XCTAssertTrue(app.buttons["startLearning"].exists || app.staticTexts["phaseTitle"].exists)}
        XCTAssertTrue(app.tabBars.buttons["地图"].exists)
        app.tabBars.buttons["进度"].tap()
        XCTAssertTrue(app.navigationBars["学习进度"].exists)
    }
}
