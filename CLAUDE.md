# Memoir Project

Monorepo with two subprojects: `memoirproject-ai-backend/` (FastAPI + Supabase) and `memoirproject-frontend/` (Next.js).

## Current Task: AI Agent for the Memoir Backend

1. Organize memories — Already built. Nothing new needed here.

2. Rephrase memories into "attractive, emotional" versions — New. This means taking the user's raw, plain memory text and asking the AI to rewrite it as flowing, warm narrative prose (like a real memoir reads). Technically: a new LangChain prompt/chain, similar to the existing organizer, that takes one memory's text (or a whole chapter's memories together) and outputs a rewritten version. You'll need to decide: do you overwrite the memory, or keep the original safe and store the AI's version separately (e.g. a new `rewritten_text` column)? I'd strongly recommend keeping the original untouched and storing the AI version separately — memoirs are personal/sensitive, so users should be able to compare and revert.

3. Understand personality and give the memoir a "vibe" — New, and this is really an extension of #2. One AI call reads all the person's memories together and produces a short personality profile (e.g. "warm, humorous, fiercely loyal, loved quiet mornings..."). That profile then gets fed into the rewriting prompt from #2 so every rephrased memory carries a consistent tone matching who this person was — instead of each memory being rewritten in isolation with a random, inconsistent voice.

4. Chat with the AI agent about the memoir — New, and the most different from the others. This isn't just a prompt/output chain — it's a back-and-forth conversation where the AI needs to (a) remember what was said earlier in the chat, and (b) actually be able to do things ("reorganize chapter 3," "make this memory shorter," "why did you group these together?") rather than just talk. That means it needs to call your existing backend functions (chapter edit, reorder, regenerate) as tools, not just generate text.
