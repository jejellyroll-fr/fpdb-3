from fpdb_3_legacy.SummaryEverleaf import SummaryParser


def test_summary_parser_extracts_metadata_and_results() -> None:
    parser = SummaryParser()

    parser.feed(
        """
        <meta name="author" content="Everleaf">
        <input name="tid" value="785646">
        <h1>Sunday Special</h1>
        <table>
          <tr><td>Start:</td><td>2026-07-14 18:00</td></tr>
          <tr><td>Game Type:</td><td>Hold'em</td></tr>
        </table>
        <div id="result"><table>
          <tr><td>Won Prize</td></tr>
          <tr><td>1</td><td>Hero</td><td>21:30</td><td>$125.00</td></tr>
        </table></div>
        """
    )

    assert parser.SiteName == "Everleaf"
    assert parser.TourneyId == "785646"
    assert parser.TourneyName == "Sunday Special"
    assert parser.TourneyStartTime == "2026-07-14 18:00"
    assert parser.TourneyGameType == "Hold'em"
    assert parser.Results["Hero"] == {
        "place": "1",
        "winamount": "$125.00",
        "outtime": "21:30",
    }
