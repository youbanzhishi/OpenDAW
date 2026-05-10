"""
VCMix AgentPlugin Phase 22b — Multi-model + Persona System.

Modules:
    model_provider    — Unified ModelProvider interface (OpenAI, Anthropic, Ollama, vLLM)
    enhanced_modelbus — Enhanced ModelBus with dynamic provider switching
    persona_manager   — Persona management (built-in + custom, persistence)
    enhanced_runtime  — Enhanced AgentRuntime with multi-model + Persona support
    agent_api         — FastAPI endpoints for Agent management

Usage:
    from OpenDAW_Phase22b.enhanced_runtime import EnhancedAgentRuntime, create_runtime

    # Simple creation
    runtime = create_runtime(provider="openai", model="gpt-4o", api_key="sk-...")

    # Or with config
    from OpenDAW_Phase22b.enhanced_modelbus import ProviderConfig
    config = ProviderConfig(provider_type="anthropic", model_id="claude-3.5-sonnet")
    runtime = EnhancedAgentRuntime(provider_config=config, persona_id="mix-engineer")

    # Chat
    response = await runtime.chat("Make the vocals brighter")

    # Switch model at runtime (context preserved!)
    runtime.switch_model(provider_type="ollama", model_id="llama3.3:70b")

    # Continue conversation
    response = await runtime.chat("Now add some reverb")
"""

# Import from local modules (Phase 22b implementation)
from vcmix.agent.phase22b.enhanced_modelbus import (
    EnhancedModelBus,
    MessageContext,
    ProviderConfig,
)
from vcmix.agent.phase22b.model_provider import (
    MODEL_REGISTRY,
    LLMResponse,
    ModelInfo,
    ModelProvider,
    ProviderType,
    create_provider,
    get_available_models,
)
from vcmix.agent.phase22b.persona_manager import (
    Persona,
    PersonaManager,
    get_persona_manager,
)

# Try to import Phase 22a components (for integration)
try:
    from vcmix.agent.memory import ShortTermMemory  # noqa: F401
    from vcmix.agent.toolbox import AGENT_TOOLS, ToolExecutor  # noqa: F401
    _HAS_PHASE22A = True
except ImportError:
    _HAS_PHASE22A = False

# Import enhanced runtime (with fallback stubs)
from vcmix.agent.phase22b.enhanced_runtime import (
    AgentAction,
    AgentResponse,
    EnhancedAgentRuntime,
    create_runtime,
)

__all__ = [
    # Model provider
    "ProviderType",
    "ModelInfo",
    "LLMResponse",
    "ModelProvider",
    "MODEL_REGISTRY",
    "create_provider",
    "get_available_models",

    # Enhanced ModelBus
    "EnhancedModelBus",
    "ProviderConfig",
    "MessageContext",

    # Persona
    "Persona",
    "PersonaManager",
    "get_persona_manager",

    # Enhanced Runtime
    "EnhancedAgentRuntime",
    "AgentAction",
    "AgentResponse",
    "create_runtime",

    # Compatibility
    "_HAS_PHASE22A",
]
