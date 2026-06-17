"""CLI entry point for paper reading agent."""
import argparse
import json
import asyncio
from pathlib import Path
from backend.agents.supervisor import run_agent

async def main():
    parser = argparse.ArgumentParser(description="Paper Reading Agent")
    parser.add_argument("--paper", "-p", required=True, help="Path to PDF file")
    parser.add_argument("--query", "-q", required=True, help="Question about the paper")
    args = parser.parse_args()

    pdf_path = Path(args.paper)
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}")
        return 1

    print(f"📄 Loading: {pdf_path.name}")
    print(f"💬 Query: {args.query}")
    print("=" * 60)

    state = await run_agent(str(pdf_path.resolve()), args.query)

    print(f"\n📊 Quality Score: {state.quality_score.total if state.quality_score else 'N/A'}/10")
    print(f"🔀 Trace: {' → '.join(state.trace)}")
    print(f"\n{state.answer}\n")
    if state.error:
        print(f"\n⚠️  {state.error}")
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
