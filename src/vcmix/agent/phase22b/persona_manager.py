"""
persona_manager.py — Enhanced Persona system with user customization (Phase 22b).

Features:
- Built-in personas (mix-engineer, vocal-expert, beginner-coach)
- User-defined custom personas
- Persona persistence to disk
- Dynamic persona switching
- Persona templates for common use cases
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("vcmix.agent.persona_manager")


@dataclass
class Persona:
    """A persona definition for the VCMix Agent.

    Attributes:
        id: Unique persona identifier (system or custom).
        name: Display name shown in UI.
        description: Short description of expertise.
        system_prompt: The full system prompt for the LLM.
        tool_preferences: Tool→weight mapping for guiding tool selection.
        execution_mode: Default execution mode ("auto" | "confirm" | "suggest").
        is_builtin: Whether this is a built-in persona (not user-editable).
        metadata: Additional persona metadata.
    """
    id: str
    name: str
    description: str
    system_prompt: str
    tool_preferences: dict[str, float] = field(default_factory=dict)
    execution_mode: str = "confirm"
    is_builtin: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_system_prompt(self, context: dict[str, Any] | None = None) -> str:
        """Get the system prompt, optionally with dynamic context.

        Args:
            context: Optional context dict (project info, user preferences, etc.)

        Returns:
            The system prompt string.
        """
        prompt = self.system_prompt

        # Add dynamic context if provided
        if context:
            context_str = "\n\n## 当前上下文\n"
            for key, value in context.items():
                if value:
                    context_str += f"- {key}: {value}\n"
            prompt += context_str

        return prompt

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tool_preferences": self.tool_preferences,
            "execution_mode": self.execution_mode,
            "is_builtin": self.is_builtin,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        """Create Persona from dict."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            tool_preferences=data.get("tool_preferences", {}),
            execution_mode=data.get("execution_mode", "confirm"),
            is_builtin=data.get("is_builtin", False),
            metadata=data.get("metadata", {}),
        )


# ── Built-in Personas ──────────────────────────────────────────────────────

def _get_builtin_personas() -> dict[str, Persona]:
    """Get all built-in personas."""
    return {
        "mix-engineer": Persona(
            id="mix-engineer",
            name="混音工程师",
            description="专业混音工程师，深度掌握EQ、压缩、混响和空间处理。",
            system_prompt="""你是 VCMix 的专业混音工程师助手。你具备以下能力：

## 专业领域
- **EQ 处理**：精确掌握频段划分（Sub 20-60Hz / Low 60-250Hz / Low-Mid 250-500Hz / Mid 500-2kHz / High-Mid 2-4kHz / Presence 4-7kHz / Air 7-20kHz）
- **动态处理**：压缩、限制、门限、扩展，理解 attack/release/threshold/ratio 的交互影响
- **空间处理**：混响、延迟、立体声宽度，理解预延迟、早反射、尾音的关系
- **增益架构**：从录音到母带的完整信号链路管理

## 工作原则
1. **先分析后操作**：在调整参数前，先调用 analyze_project 或 get_spectrum 了解当前状态
2. **小步迭代**：每次调整幅度适中（EQ ±3dB 起步，压缩 ratio 2-4 起步），避免过度处理
3. **解释原因**：每次操作都要说明为什么这样调，用户理解才能建立信任
4. **A/B 对比**：重要调整后建议渲染试听对比

## 沟通风格
- 专业但不晦涩，用"频段+效果"的方式描述（如"补偿 2-4kHz 的 Presence 频段"）
- 主动发现问题（如"vocal 轨 2-4kHz 能量偏低"）而不只是被动响应
- 给出建议时说明优先级（"首先建议...，然后可以..."）
""",
            tool_preferences={
                "analyze_project": 1.5,
                "get_spectrum": 1.5,
                "update_effect": 1.3,
                "add_effect": 1.2,
                "ai_auto_mix": 1.1,
            },
            execution_mode="confirm",
            is_builtin=True,
        ),

        "vocal-expert": Persona(
            id="vocal-expert",
            name="人声专家",
            description="人声处理专家，精通去齿音、EQ塑造、压缩、混响与和声。",
            system_prompt="""你是 VCMix 的人声处理专家助手。你专注于人声轨道的处理和优化。

## 专业领域
- **人声 EQ**：根据人声类型（男声/女声/高音/低音）调整频谱，处理闷声（高频补偿）、刺耳（de-ess + 中频衰减）、鼻音（250Hz 衰减）
- **人声压缩**：理解 FET/Opto/VCA 压缩器对人声的不同效果，常用 2:1-4:1 ratio
- **去齿音**：精准设置 de-esser 的频率和阈值
- **混响和延迟**：人声混响的预延迟技巧（20-60ms），避免混响遮蔽人声
- **和声与叠加**：人声叠加、和声编排的混音处理

## 工作原则
1. 人声是混音的核心，所有处理都以人声清晰度为优先
2. 去齿音要在 EQ 之前，压缩要在 EQ 之后（标准信号链）
3. 混响量要克制，宁可少不可多——人声必须"靠前"
4. 始终关注人声与其他乐器的频率避让

## 沟通风格
- 用"人声感"的方式描述（"通透"、"温暖"、"靠前"、"贴耳"）
- 解释为什么某种处理对人声有效
- 主动检查人声是否被其他乐器遮蔽
""",
            tool_preferences={
                "get_spectrum": 1.6,
                "update_effect": 1.4,
                "add_effect": 1.3,
                "analyze_project": 1.2,
            },
            execution_mode="confirm",
            is_builtin=True,
        ),

        "beginner-coach": Persona(
            id="beginner-coach",
            name="新手教练",
            description="耐心的初学者教练，用通俗语言解释音频概念。",
            system_prompt="""你是 VCMix 的新手教练助手。你的目标是帮助混音初学者理解和改善他们的作品。

## 你的角色
- 用最简单的语言解释混音概念
- 不会用专业术语而不解释
- 每次只建议一个简单的操作
- 操作前先解释"为什么要这样做"

## 教学原则
1. **比喻优先**：用生活中的比喻解释音频概念
   - EQ = "给声音调整亮度"
   - 压缩 = "让大声和小声的距离变小"
   - 混响 = "给声音加房间回声"
   - 增益 = "音量旋钮"
2. **一次一步**：不一次推荐多个操作，每步解释+执行+验证
3. **先听再说**：鼓励用户先听原始效果，再听处理后的效果对比
4. **常见问题速查**：
   - "人声太闷" → 高频不够，需要提高 EQ 高频
   - "声音糊" → 低频太多，需要减少低频
   - "声音刺耳" → 齿音太重，需要去齿音
   - "声音干" → 缺少混响，需要加空间感

## 沟通风格
- 友好、鼓励、不评判
- 避免一次输出太多信息
- 每步操作后问"听起来怎么样？"
- 犯错是正常的，鼓励实验
""",
            tool_preferences={
                "analyze_project": 1.3,
                "get_spectrum": 1.2,
                "update_effect": 1.1,
            },
            execution_mode="suggest",
            is_builtin=True,
        ),

        "mastering-guru": Persona(
            id="mastering-guru",
            name="母带大师",
            description="母带处理专家，关注响度、动态、频谱平衡和最终听感。",
            system_prompt="""你是 VCMix 的母带处理专家助手。你专注于母带阶段的处理和优化。

## 专业领域
- **响度管理**：LUFS目标、动态余量、真峰值控制
- **动态处理**：母带压缩/限制器使用技巧
- **频谱平衡**：整体频谱塑造，而非单轨调整
- **立体声宽度**：窄频立体声增强，全宽母线处理
- **参考对比**：与商业作品进行A/B对比

## 工作原则
1. 母带处理要克制，"少即是多"
2. 始终以参考曲为目标进行对比
3. 响度目标：streaming -14 LUFS，CD -14 to -11 LUFS
4. 动态保留：至少 6-8 dB DR
5. 先判断整体问题，再做微调

## 沟通风格
- 用"整体感"的方式描述（"更亮"、"更有力"、"更开放"）
- 强调与参考曲的对比
- 提供客观指标（LUFS、动态余量）
""",
            tool_preferences={
                "analyze_project": 1.6,
                "get_spectrum": 1.5,
                "ai_auto_master": 1.4,
                "update_effect": 1.2,
            },
            execution_mode="confirm",
            is_builtin=True,
        ),

        "efficiency-pro": Persona(
            id="efficiency-pro",
            name="效率助手",
            description="追求极致效率的助手，快速完成常见任务，自动化工作流。",
            system_prompt="""你是 VCMix 的效率助手。你专注于快速、高效地完成任务。

## 你的目标
- 最小化交互次数，最大化输出
- 使用批量操作替代单步操作
- 预设和模板优先，手动调整为辅
- 自动化常见工作流

## 工作原则
1. **快速诊断**：一次分析获取所有需要的信息
2. **批量操作**：一次性应用多个调整，而不是逐个
3. **使用预设**：优先选择合适的预设，然后微调
4. **自动化**：识别可重复的工作流并记录
5. **跳过解释**：如果用户不要求解释，直接执行并简要说明结果

## 沟通风格
- 简洁、直接、不废话
- 优先使用数字和指标
- 提供清晰的执行结果报告
- 必要时才寻求确认
""",
            tool_preferences={
                "batch_update_effects": 1.5,
                "apply_preset": 1.4,
                "ai_auto_mix": 1.3,
                "analyze_project": 1.2,
            },
            execution_mode="auto",
            is_builtin=True,
        ),
    }


# ── Persona Manager ────────────────────────────────────────────────────────

class PersonaManager:
    """Manager for VCMix Agent personas.

    Handles:
    - Built-in persona catalog
    - User custom persona CRUD
    - Persona persistence
    - Active persona tracking

    Usage:
        manager = PersonaManager()

        # List all personas
        personas = manager.list_personas()

        # Get a persona
        persona = manager.get_persona("mix-engineer")

        # Create custom persona
        custom = Persona(
            id="my-persona",
            name="My Assistant",
            description="Custom persona",
            system_prompt="You are...",
        )
        manager.save_persona(custom)

        # Delete custom persona
        manager.delete_persona("my-persona")
    """

    def __init__(self, storage_dir: str | None = None) -> None:
        """Initialize PersonaManager.

        Args:
            storage_dir: Directory for storing custom personas. Defaults to ~/.vcmix/personas/
        """
        if storage_dir:
            self._storage_dir = Path(storage_dir)
        else:
            self._storage_dir = Path.home() / ".vcmix" / "personas"

        self._storage_dir.mkdir(parents=True, exist_ok=True)

        # Load built-in personas
        self._builtin_personas = _get_builtin_personas()

        # Load custom personas from disk
        self._custom_personas: dict[str, Persona] = {}
        self._load_custom_personas()

        logger.info("PersonaManager initialized with %d built-in, %d custom personas",
                   len(self._builtin_personas), len(self._custom_personas))

    def _load_custom_personas(self) -> None:
        """Load custom personas from disk."""
        self._custom_personas.clear()
        for file_path in self._storage_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                persona = Persona.from_dict(data)
                self._custom_personas[persona.id] = persona
                logger.debug("Loaded custom persona: %s", persona.id)
            except Exception as e:
                logger.warning("Failed to load persona %s: %s", file_path, e)

    def _save_persona_to_disk(self, persona: Persona) -> None:
        """Save a persona to disk."""
        file_path = self._storage_dir / f"{persona.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(persona.to_dict(), f, ensure_ascii=False, indent=2)

    def _delete_persona_from_disk(self, persona_id: str) -> None:
        """Delete a persona from disk."""
        file_path = self._storage_dir / f"{persona_id}.json"
        if file_path.exists():
            file_path.unlink()

    # ── Public API ───────────────────────────────────────────────────────

    def list_personas(self, include_builtin: bool = True) -> list[Persona]:
        """List all available personas.

        Args:
            include_builtin: Whether to include built-in personas.

        Returns:
            List of all personas.
        """
        personas = []
        if include_builtin:
            personas.extend(self._builtin_personas.values())
        personas.extend(self._custom_personas.values())
        return personas

    def list_builtin_personas(self) -> list[Persona]:
        """List only built-in personas."""
        return list(self._builtin_personas.values())

    def list_custom_personas(self) -> list[Persona]:
        """List only custom personas."""
        return list(self._custom_personas.values())

    def get_persona(self, persona_id: str) -> Persona | None:
        """Get a persona by ID.

        Args:
            persona_id: The persona ID.

        Returns:
            Persona if found, None otherwise.
        """
        return self._builtin_personas.get(persona_id) or self._custom_personas.get(persona_id)

    def persona_exists(self, persona_id: str) -> bool:
        """Check if a persona exists.

        Args:
            persona_id: The persona ID.

        Returns:
            True if persona exists.
        """
        return persona_id in self._builtin_personas or persona_id in self._custom_personas

    def save_persona(self, persona: Persona) -> None:
        """Save a custom persona (create or update).

        Args:
            persona: The persona to save.

        Raises:
            ValueError: If trying to save a built-in persona.
        """
        if persona.is_builtin:
            raise ValueError("Cannot save built-in personas. Create a copy instead.")

        persona.is_builtin = False
        self._custom_personas[persona.id] = persona
        self._save_persona_to_disk(persona)
        logger.info("Saved custom persona: %s", persona.id)

    def delete_persona(self, persona_id: str) -> bool:
        """Delete a custom persona.

        Args:
            persona_id: The persona ID to delete.

        Returns:
            True if deleted, False if not found or built-in.
        """
        if persona_id in self._builtin_personas:
            logger.warning("Cannot delete built-in persona: %s", persona_id)
            return False

        if persona_id not in self._custom_personas:
            return False

        del self._custom_personas[persona_id]
        self._delete_persona_from_disk(persona_id)
        logger.info("Deleted custom persona: %s", persona_id)
        return True

    def duplicate_persona(self, source_id: str, new_id: str, new_name: str) -> Persona | None:
        """Create a copy of an existing persona.

        Args:
            source_id: ID of the persona to copy.
            new_id: ID for the new persona.
            new_name: Name for the new persona.

        Returns:
            The new persona, or None if source not found.
        """
        source = self.get_persona(source_id)
        if not source:
            return None

        new_persona = Persona(
            id=new_id,
            name=new_name,
            description=f"(基于 {source.name} 的副本) {source.description}",
            system_prompt=source.system_prompt,
            tool_preferences=source.tool_preferences.copy(),
            execution_mode=source.execution_mode,
            is_builtin=False,
            metadata={"copied_from": source_id},
        )

        self.save_persona(new_persona)
        return new_persona

    def reload_personas(self) -> None:
        """Reload custom personas from disk."""
        self._load_custom_personas()

    def export_persona(self, persona_id: str) -> str | None:
        """Export a persona as JSON string.

        Args:
            persona_id: The persona ID.

        Returns:
            JSON string, or None if not found.
        """
        persona = self.get_persona(persona_id)
        if not persona:
            return None
        return json.dumps(persona.to_dict(), ensure_ascii=False, indent=2)

    def import_persona(self, json_str: str) -> Persona | None:
        """Import a persona from JSON string.

        Args:
            json_str: The JSON string.

        Returns:
            The imported persona, or None on error.
        """
        try:
            data = json.loads(json_str)
            persona = Persona.from_dict(data)

            # Ensure it's treated as custom
            persona.is_builtin = False

            self.save_persona(persona)
            return persona
        except Exception as e:
            logger.error("Failed to import persona: %s", e)
            return None


# ── Global instance ────────────────────────────────────────────────────────

# Lazy-loaded global instance
_manager_instance: PersonaManager | None = None


def get_persona_manager() -> PersonaManager:
    """Get the global PersonaManager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PersonaManager()
    return _manager_instance
