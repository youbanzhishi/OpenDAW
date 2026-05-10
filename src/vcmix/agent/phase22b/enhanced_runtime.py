"""
enhanced_runtime.py — Enhanced AgentRuntime with multi-model + Persona (Phase 22b).

Features:
- Seamless model switching without losing conversation context
- Persona system integration with dynamic prompt updates
- Multi-provider support (OpenAI, Anthropic, Ollama, vLLM)
- Conversation history preservation across provider switches
- Unified API matching the Phase 22a interface for compatibility
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from vcmix.agent.phase22b.enhanced_modelbus import EnhancedModelBus, ProviderConfig

# Import Phase 22a components - these are from the existing VCMix agent module
# When used standalone, we'll use mock implementations
try:
    from vcmix.agent.memory import ShortTermMemory
    from vcmix.agent.toolbox import AGENT_TOOLS, ToolExecutor
except ImportError:
    # Standalone mode - create minimal stubs
    from dataclasses import dataclass, field
    from typing import Any

    @dataclass
    class ShortTermMemory:
        def __init__(self, max_messages: int = 20):
            self._messages: list[dict] = []
            self._max = max_messages

        def add_message(self, role: str, content: str) -> None:
            self._messages.append({"role": role, "content": content})
            if len(self._messages) > self._max:
                self._messages.pop(0)

        def get_messages(self) -> list[dict]:
            return self._messages.copy()

        def clear(self) -> None:
            self._messages.clear()

        def __len__(self) -> int:
            return len(self._messages)

    AGENT_TOOLS = []  # Minimal placeholder

    class ToolExecutor:
        def __init__(self, api_base: str = ""):
            self._api_base = api_base
            self._tools = {}

        async def execute(self, tool_name: str, args: dict) -> dict:
            return {"success": True, "tool": tool_name}

        async def close(self) -> None:
            pass

# Import persona from this module (not vcmix)
from vcmix.agent.phase22b.persona_manager import Persona, PersonaManager, get_persona_manager

logger = logging.getLogger("vcmix.agent.enhanced_runtime")

MAX_TOOL_ROUNDS = 5


@dataclass
class AgentAction:
    """A single tool call action taken by the Agent."""
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentResponse:
    """Complete response from the AgentRuntime."""
    message: str = ""
    actions: list[AgentAction] = field(default_factory=list)
    thinking: str = ""
    requires_confirmation: bool = False
    model_used: str = ""


class EnhancedAgentRuntime:
    """Enhanced Agent runtime with multi-model and Persona support.

    Key improvements over Phase 22a AgentRuntime:
    1. **EnhancedModelBus**: Supports multiple LLM providers
    2. **PersonaManager**: Built-in + custom personas with persistence
    3. **Context Preservation**: Switching models/personas keeps conversation
    4. **Dynamic Prompt**: System prompt updates without losing context

    Usage:
        # Initialize with defaults
        runtime = EnhancedAgentRuntime()

        # Or with specific provider
        config = ProviderConfig(provider_type="openai", model_id="gpt-4o", api_key="sk-...")
        runtime = EnhancedAgentRuntime(provider_config=config)

        # Set persona
        runtime.set_persona("mix-engineer")

        # Chat
        response = await runtime.chat("Make the vocals brighter")

        # Switch model at runtime
        runtime.switch_model(provider_type="anthropic", model_id="claude-3.5-sonnet", api_key="sk-ant-...")

        # Continue conversation (context preserved!)
        response = await runtime.chat("Now add some reverb to the vocals")
    """

    def __init__(
        self,
        provider_config: ProviderConfig | None = None,
        api_base: str = "http://localhost:8000/api/v1",
        persona_id: str | None = None,
        persona_manager: PersonaManager | None = None,
    ) -> None:
        """Initialize EnhancedAgentRuntime.

        Args:
            provider_config: Initial provider configuration.
            api_base: Base URL for VCMix API server.
            persona_id: Initial persona to load.
            persona_manager: Optional PersonaManager instance.
        """
        # Initialize components
        self._provider_config = provider_config or ProviderConfig()
        self._model_bus = EnhancedModelBus(self._provider_config)
        self._tool_executor = ToolExecutor(api_base=api_base)
        self._memory = ShortTermMemory(max_messages=20)
        self._persona_manager = persona_manager or get_persona_manager()

        # Persona state
        self._current_persona: Persona | None = None
        self._execution_mode = "confirm"
        self._custom_prompt: str | None = None

        # Project binding
        self._project_id: str | None = None
        self._project_state: dict[str, Any] = {}

        # Load initial persona
        if persona_id:
            self.set_persona(persona_id)

    # ── Model/Provider Management ──────────────────────────────────────

    def switch_model(
        self,
        provider_type: str | None = None,
        model_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Switch to a different LLM model at runtime.

        The conversation context is preserved across the switch.

        Args:
            provider_type: Provider type (openai, anthropic, ollama, vllm).
            model_id: Model identifier (e.g., "gpt-4o", "claude-3.5-sonnet").
            api_key: API key for the new provider.
            base_url: Custom base URL (for proxy/custom deployments).
        """
        # Build new config
        config = ProviderConfig(
            provider_type=provider_type or self._provider_config.provider_type,
            model_id=model_id or self._provider_config.model_id,
            api_key=api_key or self._provider_config.api_key,
            base_url=base_url or self._provider_config.base_url,
        )

        # Update system prompt from current persona
        if self._current_persona:
            prompt = self._current_persona.get_system_prompt(self._get_persona_context())
        elif self._custom_prompt:
            prompt = self._custom_prompt
        else:
            prompt = self._default_persona()

        self._model_bus.set_system_prompt(prompt)

        # Switch provider
        self._model_bus.switch_provider(config)
        self._provider_config = config

        logger.info("Model switched to %s/%s", config.provider_type, config.model_id)

    def get_current_model(self) -> str:
        """Get the current model identifier."""
        return f"{self._provider_config.provider_type}/{self._provider_config.model_id}"

    def add_fallback_provider(self, config: ProviderConfig) -> None:
        """Add a fallback provider for automatic failover."""
        self._model_bus.add_fallback(config)

    # ── Persona Management ──────────────────────────────────────────────

    def set_persona(self, persona_id: str) -> bool:
        """Switch to a different persona.

        Args:
            persona_id: The persona ID to switch to.

        Returns:
            True if successful, False if persona not found.
        """
        persona = self._persona_manager.get_persona(persona_id)
        if not persona:
            logger.warning("Persona not found: %s", persona_id)
            return False

        self._current_persona = persona
        self._execution_mode = persona.execution_mode
        self._custom_prompt = None  # Clear custom prompt

        # Update system prompt in model bus
        prompt = persona.get_system_prompt(self._get_persona_context())
        self._model_bus.set_system_prompt(prompt)

        logger.info("Persona set to: %s (%s)", persona.name, persona_id)
        return True

    def get_persona(self) -> Persona | None:
        """Get the current persona."""
        return self._current_persona

    def set_custom_prompt(self, prompt: str) -> None:
        """Set a custom system prompt (overrides persona).

        Args:
            prompt: Custom system prompt.
        """
        self._current_persona = None
        self._custom_prompt = prompt
        self._model_bus.set_system_prompt(prompt)
        logger.info("Custom prompt set: %d chars", len(prompt))

    def _get_persona_context(self) -> dict[str, Any]:
        """Get context dict for persona prompt."""
        return {
            "project_id": self._project_id or "未绑定",
            "available_tools": len(AGENT_TOOLS),
            "execution_mode": self._execution_mode,
        }

    # ── Project Management ──────────────────────────────────────────────

    def set_project(self, project_id: str) -> None:
        """Bind the Agent to a specific project.

        Args:
            project_id: The VCMix project ID.
        """
        self._project_id = project_id
        self._project_state = {}

        # Update persona context
        if self._current_persona:
            prompt = self._current_persona.get_system_prompt(self._get_persona_context())
            self._model_bus.set_system_prompt(prompt)

        logger.info("Agent bound to project: %s", project_id)

    # ── Chat API ─────────────────────────────────────────────────────────

    async def chat(
        self,
        user_message: str,
        project_id: str | None = None,
        execution_mode: str | None = None,
    ) -> AgentResponse:
        """Process a user message through the ReAct loop.

        Args:
            user_message: The user's natural language input.
            project_id: Optional project override.
            execution_mode: Override execution mode for this message.

        Returns:
            AgentResponse with message, actions, thinking.
        """
        # Bind project if provided
        if project_id:
            self.set_project(project_id)

        # Add user message to memory
        self._memory.add_message("user", user_message)

        # Build messages
        messages = self._build_messages()
        tools = AGENT_TOOLS

        actions: list[AgentAction] = []
        thinking_parts: list[str] = []

        # Determine execution mode for this turn
        mode = execution_mode or self._execution_mode

        # ReAct loop
        for round_num in range(MAX_TOOL_ROUNDS):
            try:
                response = await self._model_bus.chat(
                    messages=messages,
                    tools=tools,
                )
            except Exception as e:
                logger.error("LLM call failed: %s", e)
                return AgentResponse(
                    message=f"抱歉，模型调用失败：{e}",
                    actions=actions,
                    thinking="\n".join(thinking_parts),
                    model_used=self.get_current_model(),
                )

            # Add assistant message to conversation
            messages.append({"role": "assistant", "content": response.content})
            self._memory.add_message("assistant", response.content)

            # Check for tool calls
            if response.has_tool_calls:
                for tc in response.tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args_str = tc.get("arguments", "{}")
                    tool_call_id = tc.get("id", "")

                    try:
                        tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    except json.JSONDecodeError:
                        tool_args = {}

                    # Inject project_id if needed
                    if self._project_id and "project_id" not in tool_args:
                        tool_def = next((t for t in AGENT_TOOLS if t["name"] == tool_name), None)
                        if tool_def and "project_id" in tool_def.get("parameters", {}).get("properties", {}):
                            tool_args["project_id"] = self._project_id

                    thinking_parts.append(f"🔧 调用工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

                    # Execute tool
                    result = await self._tool_executor.execute(tool_name, tool_args)

                    action = AgentAction(
                        tool=tool_name,
                        arguments=tool_args,
                        result=result,
                        timestamp=time.time(),
                    )
                    actions.append(action)

                    # Add tool result to messages
                    tool_result_content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": tool_result_content,
                    })
                    self._memory.add_message("tool", f"[{tool_name}] {tool_result_content[:200]}")

                    thinking_parts.append(f"📊 工具结果: {tool_result_content[:100]}")

                continue
            else:
                # Text response - we're done
                final_message = response.content
                self._memory.add_message("assistant", final_message)

                requires_confirmation = (mode == "confirm" and len(actions) > 0)

                return AgentResponse(
                    message=final_message,
                    actions=actions,
                    thinking="\n".join(thinking_parts),
                    requires_confirmation=requires_confirmation,
                    model_used=self.get_current_model(),
                )

        # Max rounds exceeded
        return AgentResponse(
            message="我已执行多步操作但尚未得出最终结论。请继续描述你的需求，我会接着处理。",
            actions=actions,
            thinking="\n".join(thinking_parts),
            requires_confirmation=True,
            model_used=self.get_current_model(),
        )

    def _build_messages(self) -> list[dict[str, Any]]:
        """Build the full message list for the LLM."""
        messages: list[dict[str, Any]] = []

        # System prompt (already set in model_bus)
        # Project context
        if self._project_id:
            project_context = f"""当前项目状态：
- 项目 ID: {self._project_id}
- 绑定状态: 已绑定
- 可用工具: {len(AGENT_TOOLS)} 个
"""
            messages.append({"role": "system", "content": project_context})

        # Conversation history
        history = self._memory.get_messages()
        messages.extend(history)

        return messages

    @staticmethod
    def _default_persona() -> str:
        """Default VCMix mix assistant persona."""
        return """你是 VCMix 的 AI 混音助手。你可以帮助用户分析和优化音频项目。

## 你的能力
- 分析项目频谱、响度、动态
- 添加/修改/删除效果插件
- 管理轨道（添加/修改/删除）
- AI 自动混音和母带处理
- 渲染和导出

## 工作原则
1. 先分析后操作
2. 小步迭代，避免大幅调整
3. 解释每步操作的原因
4. 尊重用户偏好

请用中文回复，专业但友好。
"""

    # ── Status & Utilities ───────────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Get current runtime status."""
        persona = self._current_persona
        model_status = self._model_bus.get_status()

        return {
            "model": self.get_current_model(),
            "model_info": model_status.get("model_info"),
            "project_id": self._project_id,
            "persona": persona.id if persona else "custom",
            "persona_name": persona.name if persona else "自定义",
            "execution_mode": self._execution_mode,
            "memory_messages": len(self._memory),
            "context_messages": model_status.get("context_size", 0),
        }

    def clear_conversation(self) -> None:
        """Clear conversation history but keep persona/model."""
        self._memory.clear()
        self._model_bus.clear_context()
        logger.info("Conversation cleared")

    async def close(self) -> None:
        """Clean up resources."""
        await self._model_bus.close()
        await self._tool_executor.close()

    # ── Compatibility Layer ──────────────────────────────────────────────

    def configure_model(self, config: dict[str, Any]) -> None:
        """Configure model (Phase 22a compatibility).

        Args:
            config: Dict with provider, model, api_key, etc.
        """
        self.switch_model(
            provider_type=config.get("provider", config.get("provider_type")),
            model_id=config.get("model"),
            api_key=config.get("api_key"),
            base_url=config.get("base_url"),
        )

    def get_available_personas(self) -> list[dict[str, Any]]:
        """Get list of all available personas."""
        personas = self._persona_manager.list_personas()
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "execution_mode": p.execution_mode,
                "is_builtin": p.is_builtin,
            }
            for p in personas
        ]


# ── Convenience Functions ─────────────────────────────────────────────────

def create_runtime(
    provider: str = "openai",
    model: str = "gpt-4o",
    api_key: str = "",
    persona: str | None = None,
    api_base: str = "http://localhost:8000/api/v1",
) -> EnhancedAgentRuntime:
    """Create a configured EnhancedAgentRuntime.

    Convenience function for common configurations.

    Args:
        provider: Provider type (openai, anthropic, ollama).
        model: Model ID.
        api_key: API key.
        persona: Optional persona ID.
        api_base: VCMix API base URL.

    Returns:
        Configured EnhancedAgentRuntime instance.
    """
    config = ProviderConfig(
        provider_type=provider,
        model_id=model,
        api_key=api_key,
    )

    runtime = EnhancedAgentRuntime(
        provider_config=config,
        api_base=api_base,
        persona_id=persona,
    )

    return runtime
