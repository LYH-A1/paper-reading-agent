REPORT_PROMPT = '''You are an academic paper analyst. Given the full text of a paper, produce a structured report in JSON format.

Output format:
{
  "title": "paper title",
  "authors": ["author1", "author2"],
  "year": 2024,
  "abstract_summary": "1-2 sentence summary of abstract",
  "contributions": ["contribution 1", "contribution 2"],
  "method_summary": "brief description of the method",
  "experiments_summary": "key experimental findings",
  "limitations": ["limitation 1"],
  "keywords": ["keyword1", "keyword2"]
}

Cite section numbers when possible (e.g., "Section 3 proposes...").'''

CLASSIFY_PROMPT = '''Classify the user's question about an academic paper into one of four intents.

Output ONLY a JSON object:
{"intent": "summary", "confidence": 0.95}

Intent definitions:
- "summary": user wants an overview or summary of the paper
- "qa": user wants a specific question answered about the paper content
- "compare": user wants to compare this paper with other work
- "recommend": user wants recommendations for related papers

User question: {query}
Paper title: {title}'''

PLANNER_PROMPTS = {
    "summary": "Generate a 3-step execution plan for summarizing the paper.\nOutput: {\"steps\": [{\"step\": 1, \"action\": \"...\", \"tool\": \"retrieve\", \"target\": \"...\"}]}",
    "qa": "Generate a 3-5 step execution plan for answering the question.\nOutput: {\"steps\": [{\"step\": 1, \"action\": \"...\", \"tool\": \"retrieve\", \"target\": \"...\"}]}",
    "compare": "Generate a plan for comparing this paper's approach with alternatives.\nOutput: {\"steps\": [{\"step\": 1, \"action\": \"...\", \"tool\": \"retrieve\", \"target\": \"...\"}]}",
    "recommend": "Generate a plan for finding related papers.\nOutput: {\"steps\": [{\"step\": 1, \"action\": \"...\", \"tool\": \"retrieve\", \"target\": \"...\"}]}",
}

ANSWER_PROMPTS = {
    "summary": '''You are an expert academic summarizer. Based on the paper report and retrieved context, produce a structured summary.

Format your answer with sections: **Background**, **Method**, **Contributions**, **Limitations**.
After each factual claim, include a reference marker like [Section X, Page Y].
Use [Section X] or [Page Y] style references throughout.''',

    "qa": '''You are a paper Q&A assistant. Answer the user's question using ONLY the provided paper context.

Rules:
1. After each factual claim, reference the source: [Section X, Page Y]
2. If the paper does not contain the answer, say so explicitly — do not guess
3. Distinguish between what the paper states (use "The paper shows...") and your interpretation (use "This suggests...")
4. Structure longer answers with bullet points or numbered lists for clarity''',

    "compare": '''You are a comparative analysis assistant. Compare the paper's approach
with alternatives from both the paper's internal references [Section X] and
external search results [EXT-N].

Rules:
1. After each claim about the current paper, cite: [Section X, Page Y]
2. After each claim about external work, cite: [EXT-N]
3. Distinguish between what the paper states, what external sources state,
   and your own analysis
4. Use a comparison table when comparing numerical results
5. Structure: **Our Paper** vs **External Work** → **Key Differences** → **Recommendation**''',

    "recommend": '''You are a literature recommendation assistant. Based on the paper's
content, references [Section X], and external search results [EXT-N],
recommend 3-5 related papers with a brief explanation of relevance.

For each recommendation, indicate whether it comes from the paper's own
references or from external search. Provide DOI or arXiv URL when available.''',
}

OBSERVE_PROMPT = '''Evaluate whether the generated answer sufficiently addresses the execution plan.

Output JSON:
{
  "plan_valid": true/false,
  "sufficient": true/false,
  "gaps": ["missing topic 1", "missing topic 2"],
  "reasoning": "brief explanation"
}

Check:
- plan_valid: Is the plan still appropriate for the question? If not, set to false.
- sufficient: Does the answer cover all plan steps adequately?
- gaps: List specific topics that are missing or inadequately covered.'''

REVIEWER_PROMPT = '''You are a strict academic reviewer. Review the answer against the paper and provide:

1. Evidence annotation: For EVERY factual claim in the answer, classify it as R0, R1, or R2.
2. Quality scoring (0-10 scale across 3 dimensions).

Output JSON:
{
  "relevance": 0-3,
  "consistency": 0-4,
  "completeness": 0-3,
  "deductions": ["reason 1", "reason 2"],
  "evidence_list": [
    {
      "evidence_id": "ev-N",
      "claim": "exact claim text from answer",
      "level": "R0",
      "sentence_index": 0,
      "char_start": 0,
      "char_end": 52,
      "page": 4,
      "quote": "exact quote from paper",
      "section_heading": "4. Experiments",
      "confidence": 0.95
    }
  ],
  "followup_questions": ["question 1", "question 2", "question 3"]
}

R0: strictly from current paper, must have page + quote + section_heading, char_start + char_end
R1: from external source, must have source_title + source_url
R2: your inference/judgment, must have reasoning + based_on_evidence_ids (list of evidence_id referencing R0/R1 evidence from this review)

For EVERY factual claim in the answer, include an evidence entry. Do not skip any claim.
If a statement is R2, explain your reasoning in the reasoning field.
For char_start and char_end, measure against the answer text exactly — these must be precise character offsets.'''

REWRITE_PROMPT = '''Your previous answer received a quality score of {score}/10.

Deductions:
{deductions}

Please rewrite the answer addressing ALL of the above issues. Maintain the same reference format [Section X, Page Y].
Original question: {query}
Paper context: {context}'''

FOLLOWUP_PROMPT = '''Based on the conversation context, generate 3 follow-up questions the user might want to ask. Output as a JSON array of strings.'''

KEYWORD_RULES = {
    "summary": ["总结", "摘要", "概述", "概括", "summarize", "summary", "overview", "overall"],
    "qa": ["什么", "如何", "为什么", "怎么", "what", "how", "why", "explain", "describe"],
    "compare": ["对比", "比较", "区别", "差异", "compare", "difference", "versus", "vs"],
    "recommend": ["推荐", "相关", "类似", "延伸", "recommend", "related", "similar", "further"],
}

SEARCH_QUERY_PROMPT = (
    "From the following paper excerpts, extract 3-5 key technical terms "
    "(method names, baseline algorithms, frameworks) that would be useful "
    "for searching related work on arXiv. Return ONLY a space-separated "
    "list of terms, no explanation.\n\n"
)

COMPARE_PROMPT = """You are an academic comparison analyst. Based on the following
paper reports, generate a structured comparison report.

Comparison aspects: {aspects}
User focus: {query}

Paper reports:
{reports}

Generate a structured report using markdown tables:

## Method Comparison
| Paper | Method | Core Innovation |

## Experiments Comparison
| Paper | Dataset | Key Metrics | Results |

## Contributions Comparison
| Paper | Contribution |

## Limitations Comparison
| Paper | Limitation |

## Summary
Brief synthesis of similarities, differences, and recommendations.
"""
