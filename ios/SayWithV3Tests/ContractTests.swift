import XCTest
@testable import SayWithV3

final class ContractTests: XCTestCase {
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
    func testJobTerminalNeedsReview() throws {
        let decoder=JSONDecoder();decoder.keyDecodingStrategy = .convertFromSnakeCase
        let job=try decoder.decode(Job.self,from:Data(#"{"job_id":"j1","state":"needs_review","row_version":2,"error":{"message":"Task quality failed"}}"#.utf8))
        XCTAssertTrue(job.terminal)
        XCTAssertEqual(job.label,"课程需要审核")
    }
}
