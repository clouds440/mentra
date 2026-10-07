# LangChain and chat models

`ModelFactory` is the Mentra-owned entry point for chat-model construction. Callers should request a model with `model_factory.get_model()` rather than constructing `ChatOpenAI` or a provider SDK client directly.

`ChatService` owns the short Mentra system prompt and maps the current user/assistant turns to LangChain messages. The `/api/v1/chat` API accepts the in-memory conversation history and returns one assistant message; it does not persist the conversation or stream responses.

The current adapter is `openai_compatible`. Configure `AI_MODEL`, `AI_BASE_URL`, and `AI_API_KEY` for the chosen endpoint; changing those values is sufficient to switch among compatible services such as OpenAI, DeepSeek, and Groq. `AI_TEMPERATURE`, `AI_TIMEOUT`, and `AI_MAX_RETRIES` tune request behavior. No provider URL or model name is hard-coded.

DeepSeek uses the same OpenAI-compatible adapter. Add another adapter only when a provider has an actual API incompatibility.

Model configuration is checked when the model is requested and reported separately by readiness. Missing AI credentials do not prevent the backend from starting, so chat requests can return an actionable configuration error. Validation does not make a paid model request; an explicit caller must invoke the model to do that.

Embeddings are a separate RAG component and are not selected by or sent through the chat provider.
