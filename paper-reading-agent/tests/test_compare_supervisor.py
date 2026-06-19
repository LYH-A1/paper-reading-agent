import pytest
from backend.agents.compare_supervisor import build_compare_graph


@pytest.mark.asyncio
async def test_build_compare_graph_compiles():
    """Verify the compare graph compiles without error."""
    graph = await build_compare_graph()
    assert graph is not None
