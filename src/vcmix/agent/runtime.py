"""
runtime.py — AgentRuntime core for VCMix AgentPlugin (Phase 22a).

Implements the ReAct (Reason + Act) loop:
  1. Build context (persona + project state + conversation history)
  2. Call LLM with tools
  3. If LLM returns tool_calls → execute via ToolExecutor → append results → loop
  4. If LLM returns text → return AgentResponse
  5. Max MAX_TOOL_ROUNDS iterations to prevent infinite loops
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from vcmix.agent.memory import ShortTermMemory
from vcmix.agent.modelbus import ModelBus, ModelConfig, Message
from vcmix.agent.persona import Persona, BUILTIN_PERSONAS
from vcmix.agent.toolbox import ToolExecutor, AGENT_TOOLS

logger = logging.getLogger("vcmix.agent.runtime")

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
    """Complete response from the AgentRuntime.

    Attributes:
        message: The final text response to show the user.
        actions: List of tool calls executed during this interaction.
        thinking: Optional thinking/reasoning chain for display.
        requires_confirmation: Whether the user needs to confirm pending actions.
    """

    message: str = ""
    actions: list[AgentAction] = field(default_factory=list)
    thinking: str = ""
    requires_confirmation: bool = False


class AgentRuntime:
    """Core Agent runtime with ReAct loop.

    Manages conversation context, LLM interaction, and tool execution
    in a single coherent loop.

    Args:
        model_config: LLM backend configuration.
        api_base: Base URL for the VCMix API server.
        persona_prompt: Optional override system prompt.
        execution_mode: "auto" | "confirm" | "suggest".
    """

    def __init__(
        self,
        model_config: ModelConfig | None = None,
        api_base: str = "http://localhost:8000/api/v1",
        persona_prompt: str | None = None,
        execution_mode: str = "confirm",
    ) -> None:
        self.model_config = model_config or ModelConfig()
        self._model_bus = ModelBus(self.model_config)
        self._tool_executor = ToolExecutor(api_base=api_base)
        self._memory = ShortTermMemory(max_messages=20)

        # Persona setup
        self._persona: Persona | None = None
        self._custom_persona_prompt = persona_prompt
        self._execution_mode = execution_mode

        # Current project binding
        self._project_id: str | None = None
        self._project_state: dict[str, Any] = {}

    def set_project(self, project_id: str) -> None:
        """Bind the Agent to a specific project.

        Args:
            project_id: The VCMix project ID to bind to.
        """
        self._project_id = project_id
        self._project_state = {}
        logger.info("Agent bound to project: %s", project_id)

    def set_persona(self, persona_id: str) -> None:
        """Switch to a built-in persona.

        Args:
            persona_id: One of the keys in BUILTIN_PERSONAS.
        """
        persona = BUILTIN_PERSONAS.get(persona_id)
        if persona:
            self._persona = persona
            self._execution_mode = persona.execution_mode
            logger.info("Agent persona set to: %s (%s)", persona.name, persona_id)

    def configure_model(self, config: ModelConfig) -> None:
        """Reconfigure the LLM backend.

        Args:
            config: New ModelConfig to apply.
        """
        self.model_config = config
        # Close old bus and create new one
        self._model_bus = ModelBus(config)
        logger.info("Agent model reconfigured: %s/%s", config.provider, config.model)

    def get_status(self) -> dict[str, Any]:
        """Return the current Agent status."""
        persona = self._persona
        return {
            "model": f"{self.model_config.provider}/{self.model_config.model}",
            "project_id": self._project_id,
            "persona": persona.id if persona else "default",
            "execution_mode": self._execution_mode,
            "memory_messages": len(self._memory),
        }

    async def chat(self, user_message: str, project_id: str | None = None) -> AgentResponse:
        """Process a user message through the ReAct loop.

        Args:
            user_message: The user's natural language input.
            project_id: Optional project override for this message.

        Returns:
            AgentResponse with the final message, actions taken, and thinking.
        """
        if project_id:
            self.set_project(project_id)

        # Add user message to memory
        self._memory.add_message("user", user_message)

        # Build the full message list for LLM
        messages = self._build_messages()

        # Get tool definitions for LLM
        tool_defs = AGENT_TOOLS

        actions: list[AgentAction] = []
        thinking_parts: list[str] = []

        # ReAct loop
        for round_num in range(MAX_TOOL_ROUNDS):
            try:
                response = await self._model_bus.chat(
                    messages=messages,
                    tools=tool_defs,
                )
                assistant_msg = self._model_bus.extract_assistant_message(response)
            except Exception as e:
                logger.error("LLM call failed: %s", e)
                return AgentResponse(
                    message=f"抱歉，模型调用失败：{e}",
                    actions=actions,
                    thinking="\n".join(thinking_parts),
                )

            # Add assistant message to conversation
            messages.append(assistant_msg.to_dict())
            self._memory.add_message("assistant", assistant_msg.content)

            # Check if LLM wants to call tools
            if assistant_msg.tool_calls:
                for tc in assistant_msg.tool_calls:
                    tool_name = tc.get("name", "")
                    tool_args_str = tc.get("arguments", "{}")
                    tool_call_id = tc.get("id", "")

                    try:
                        tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                    except json.JSONDecodeError:
                        tool_args = {}

                    # Inject project_id if not already in args and Agent has one
                    if self._project_id and "project_id" not in tool_args:
                        # Only inject for tools that take project_id
                        tool_def = next((t for t in AGENT_TOOLS if t["name"] == tool_name), None)
                        if tool_def and "project_id" in tool_def.get("parameters", {}).get("properties", {}):
                            tool_args["project_id"] = self._project_id

                    thinking_parts.append(f"🔧 调用工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

                    # Execute the tool
                    result = await self._tool_executor.execute(tool_name, tool_args)

                    action = AgentAction(
                        tool=tool_name,
                        arguments=tool_args,
                        result=result,
                        timestamp=time.time(),
                    )
                    actions.append(action)

                    # Add tool result to messages for the LLM
                    tool_result_content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": tool_result_content,
                    })
                    self._memory.add_message("tool", f"[{tool_name}] {tool_result_content[:200]}")

                    thinking_parts.append(f"📊 工具结果: {tool_result_content[:100]}")

                # Continue the loop — LLM sees tool results and decides next step
                continue
            else:
                # LLM returned a text response — we're done
                final_message = assistant_msg.content
                self._memory.add_message("assistant", final_message)

                requires_confirmation = (
                    self._execution_mode == "confirm" and len(actions) > 0
                )

                return AgentResponse(
                    message=final_message,
                    actions=actions,
                    thinking="\n".join(thinking_parts),
                    requires_confirmation=requires_confirmation,
                )

        # Exceeded max tool rounds
        return AgentResponse(
            message="我已执行多步操作但尚未得出最终结论。请继续描述你的需求，我会接着处理。",
            actions=actions,
            thinking="\n".join(thinking_parts),
            requires_confirmation=True,
        )

    def _build_messages(self) -> list[dict[str, Any]]:
        """Build the full message list for the LLM.

        Order:
        1. System prompt (from Persona or default)
        2. Project state context
        3. Conversation history (from ShortTermMemory)
        """
        messages: list[dict[str, Any]] = []

        # 1. System prompt
        system_prompt = self._get_system_prompt()
        messages.append({"role": "system", "content": system_prompt})

        # 2. Project state context
        if self._project_id:
            project_context = f"""当前项目状态：
- 项目 ID: {self._project_id}
- 绑定状态: 已绑定
- 可用工具: 分析/效果/轨道/渲染/AI混音/频谱 等 20 个
"""
            messages.append({"role": "system", "content": project_context})

        # 3. Conversation history
        history = self._memory.get_messages()
        messages.extend(history)

        return messages

    def _get_system_prompt(self) -> str:
        """Get the current system prompt from persona or default."""
        if self._custom_persona_prompt:
            return self._custom_persona_prompt
        if self._persona:
            return self._persona.get_system_prompt()
        return self._default_persona()

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

    async def close(self) -> None:
        """Clean up resources."""
        await self._model_bus.close()
        await self._tool_executor.close()
