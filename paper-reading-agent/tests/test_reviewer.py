def test_decide_loop_max_rewrites_1_stops_early():
    from backend.models.state import AgentState, QualityScore
    from backend.agents.reviewer import decide_loop

    state = AgentState()
    state.quality_score = QualityScore(relevance=1, consistency=1, completeness=1)  # total=3
    state.rewrite_count = 0
    assert decide_loop(state, max_rewrites=1) == "rewrite"

    state.rewrite_count = 1
    assert decide_loop(state, max_rewrites=1) == "output"


def test_decide_loop_max_rewrites_default_2():
    from backend.models.state import AgentState, QualityScore
    from backend.agents.reviewer import decide_loop

    state = AgentState()
    state.quality_score = QualityScore(relevance=1, consistency=1, completeness=1)  # total=3
    state.rewrite_count = 1
    assert decide_loop(state) == "rewrite"

    state.rewrite_count = 2
    assert decide_loop(state) == "output"


def test_decide_loop_high_score_outputs():
    from backend.models.state import AgentState, QualityScore
    from backend.agents.reviewer import decide_loop

    state = AgentState()
    state.quality_score = QualityScore(relevance=3, consistency=3, completeness=2)  # total=8
    state.rewrite_count = 0
    assert decide_loop(state) == "output"
