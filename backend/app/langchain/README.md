# LangChain and chat models

`ModelFactory` is the Mentra-owned entry point for provider model construction. `MentraLLM` is the shared request/invocation component used by chat and structured Student Profile evaluation. Every invocation supplies an internal `PromptSource`; that closed enum selects the relevant prompt module. HTTP input cannot choose a prompt source. Optional response schemas are validated in this same component.

Keep system instructions in a source-specific module under `prompts/`. Each module owns its prompt version; `prompts/registry.py` maps `PromptSource` to both the prompt and version. Add a new source and prompt module together, then route its service through the shared `MentraLLM`. Chat uses `chat`; profile evaluation uses `student_profile_evaluation`; granular learner context is an additional registered source fragment. The `/api/v1/chat` API accepts in-memory conversation history and returns one assistant message; it does not persist or stream the conversation.

Application startup creates one `MentraLLM` instance and injects it into chat and the profile evaluator. Each workflow chooses its source in trusted server code. The common component resolves instructions, constructs ordered LangChain messages, binds structured output when requested, and validates the result. Provider construction remains in `ModelFactory`; evidence validation and persistence remain in Student Profile services.

The current adapter is `openai_compatible`. Configure `AI_MODEL`, `AI_BASE_URL`, and `AI_API_KEY` for the chosen endpoint; changing those values is sufficient to switch among compatible services such as OpenAI, DeepSeek, and Groq. `AI_TEMPERATURE`, `AI_TIMEOUT`, and `AI_MAX_RETRIES` tune request behavior. No provider URL or model name is hard-coded.

DeepSeek uses the same OpenAI-compatible adapter. Add another adapter only when a provider has an actual API incompatibility.

Model configuration is checked when the model is requested and reported separately by readiness. Missing AI credentials do not prevent the backend from starting, so chat requests can return an actionable configuration error. Validation does not make a paid model request; an explicit caller must invoke the model to do that.

Embeddings are a separate RAG component and are not selected by or sent through the chat provider.
