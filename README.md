<h1>Enterprise Knowledge Base RAG Chatbot</h1>s
Customer Success Managers (CSMs) at OmniCorp Solutions currently spend hours manually searching through hundreds of internal product manuals to answer complex client configuration questions. You have been contracted to build a prototype Retrieval-Augmented Generation (RAG) chatbot that allows CSMs to ask natural language questions and receive accurate, cited answers based strictly on internal documentation.

Your task is to build a full-stack application consisting of a backend API and a frontend chat interface. The backend should ingest a small set of provided text documents (you should create 3-5 mock enterprise knowledge base articles), chunk them, store them in a local or in-memory vector store, and expose a chat endpoint. The frontend must be a web-based UI where users can type questions, view the AI's response, and critically, see the specific document citations used to generate the answer.

As a Lead Engineer, we expect you to focus on system architecture, API design, and operational readiness. You are free to choose the backend language you are most comfortable with (we recommend C# / .NET or Python based on your background). The solution should be easy to run locally (e.g., via Docker Compose), well-structured, and include basic tests. You may use any external LLM provider (e.g., OpenAI, Anthropic, Groq) by allowing the reviewer to supply their own API key via environment variables, or use a local model via Ollama. Do not include any paid API keys in your submission.

<h2>DELIVERABLES</h2>
- A single public GitHub repository (or gist URL) containing your complete solution.
- A backend service (e.g., C#/.NET Core, Python, or Node.js) implementing the document ingestion, RAG pipeline, and API endpoints.
- A frontend UI (e.g., React, Next.js, or Vite in TypeScript) demonstrating the chat workflow and displaying source citations.
- A docker-compose.yml file (or equivalent automated script) that spins up the entire stack seamlessly.
- A README.md explaining your architectural decisions, API design, trade-offs, and instructions on how to run and test the system.

MANDATORY: An export of your AI assistant conversation logs (e.g., Cursor chat history, Copilot export, or Claude transcripts) committed to the repository.

<h2>SUGGESTED TOOLS</h2>

Frontend: React, Next.js, or Vite + TailwindCSS
Backend: ASP.NET Core (C#), FastAPI/Flask (Python), or Express/NestJS (Node.js)
Vector Store: ChromaDB, pgvector (via Docker), or a simple in-memory cosine similarity implementation
AI/RAG: Microsoft Semantic Kernel, LangChain, LlamaIndex, or raw SDKs
LLM: OpenAI API, Anthropic API (Bring Your Own Key), Groq API, or local Ollama

<h2>ON AI ASSISTANTS & FOLLOW-UP</h2>

We expect and encourage you to use AI assistants (GitHub Copilot, ChatGPT, Claude, Cursor, etc.) to accelerate your work.

MANDATORY: You must commit your AI assistant conversation logs to the repository and add a brief note in the README describing which tools were used and for what parts of the codebase. Be prepared to walk us through any block of code you submit. We will ask deep-dive questions on your architectural choices, API design, and trade-offs during the technical interview.
