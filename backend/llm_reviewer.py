"""
llm_reviewer.py
----------------
Optional secondary review layer using a locally-running Ollama model.

IMPORTANT SCOPE: this module never makes block/allow decisions. It only
generates a plain-English explanation for a decision the rule engine has
ALREADY made (e.g. "why did this upload get rejected"). This keeps the fast,
deterministic rule/ML layers as the sole authority over pass/fail, while
adding the kind of human-readable reasoning an LLM is actually good at --
consistent with this project's explainable-AI theme elsewhere (loan scoring
factors).

Design choices, worth stating explicitly in a report:
- Runs fully local via Ollama (http://localhost:11434) -- no external API
  calls, no cost, no data leaves the machine. Good fit for a security
  project: you're not shipping applicant documents to a third-party API.
- Not called per-request. Only invoked on the handful of requests per day
  that are already flagged/rejected by the rule engine -- an LLM call per
  request would be far too slow/costly at real traffic volume, and isn't
  the right tool for numeric rate-limiting/anomaly-scoring anyway.
- Fails silently and safely if Ollama isn't running or times out: returns
  None, and callers must treat None as "no explanation available", NOT as
  "content is fine". This matters most in production (Render) where
  Ollama typically isn't installed -- the app must work identically
  with or without it.

Usage:
    from llm_reviewer import explain_income_proof_rejection
    explanation = await explain_income_proof_rejection(extracted_text, reason)
    # explanation is a string, or None if the LLM reviewer is unavailable
"""
import os
import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_TIMEOUT_SECONDS = 45.0  # generous: a cold model load (not yet in memory)
# was observed taking ~25-40s total on this machine before the model responds
# at all. Once warm, Ollama keeps a model loaded in memory for a few minutes
# (its default keep_alive window) and subsequent calls are much faster
# (well under a second of actual generation time) -- so this timeout mostly
# matters for the *first* request after Ollama has been idle. This is real,
# worth-documenting latency: it's a concrete reason a local LLM reviewer
# belongs in an occasional/async review path, not a synchronous per-request
# decision gate.


async def _ask_ollama(prompt: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("response") or "").strip() or None
    except Exception:
        # Ollama not running, model not pulled, network hiccup, timeout, etc.
        # This is expected/normal in production -- fail silently, never raise.
        return None


async def explain_income_proof_rejection(extracted_text: str, reason: str) -> str | None:
    """Returns a short, plain-English explanation of why an uploaded document
    was rejected as an income proof, using what text was actually extracted
    from it. Returns None if the LLM reviewer is unavailable -- callers must
    fall back to the existing rule-based message in that case, unchanged."""
    snippet = (extracted_text or "").strip()[:800]  # keep prompt small/fast
    if not snippet:
        prompt = (
            "A user uploaded a file as proof of income (a salary slip). "
            "No readable text could be extracted from it at all (it may be a "
            "blank page, a photo of something else, or a scanned image with "
            "no OCR available). In one short, friendly sentence, explain this "
            "to the user and suggest what to check. Do not mention regex, "
            "keywords, or internal system details."
        )
    else:
        prompt = (
            "A user uploaded a file as proof of income (a salary slip), but "
            "an automated check flagged it as not looking like a real salary "
            "slip. Here is the text actually extracted from their file:\n\n"
            f"---\n{snippet}\n---\n\n"
            "In one short, friendly sentence, explain to the user why this "
            "likely isn't a valid salary slip and what they should upload "
            "instead. Do not mention regex, keywords, or internal system "
            "details -- speak naturally, like a helpful support agent."
        )
    return await _ask_ollama(prompt)


async def answer_with_faq_grounding(question: str, faq_context: str) -> str | None:
    """Answers a user's question using ONLY the facts in faq_context as
    grounding -- used when the keyword FAQ matcher in assistant.py found no
    match. Deliberately NOT a free-form chatbot prompt: the model is
    instructed to restate/rephrase the given facts, and to say so plainly if
    the question isn't covered, rather than inventing an answer. This matters
    because this bot states specific real numbers (interest rates, scoring
    weights, tenure options) that must stay accurate, and this endpoint is
    public and unauthenticated -- grounding reduces (does not eliminate) both
    hallucination and prompt-injection risk compared to an ungrounded prompt.

    Returns None if Ollama is unavailable -- caller falls back to the
    existing static FALLBACK message, unchanged."""
    prompt = (
        "You are a support assistant for SecureLend, a loan platform. Answer "
        "the user's question using ONLY the facts listed below -- do not add "
        "numbers, rates, or policies that aren't listed here. If the question "
        "genuinely isn't covered by these facts, say plainly that you don't "
        "have that information on this platform, in one short sentence. Keep "
        "your answer to 2-3 sentences, friendly and factual.\n\n"
        f"Known facts about SecureLend:\n{faq_context}\n\n"
        f"User's question: {question}"
    )
    return await _ask_ollama(prompt)