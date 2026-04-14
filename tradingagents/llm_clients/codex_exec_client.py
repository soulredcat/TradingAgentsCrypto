import json
import os
import shutil
import subprocess
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from .base_client import BaseLLMClient


def _extract_text(content: Any) -> str:
    """Normalize heterogeneous message content into plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
        return "\n".join(p for p in parts if p)
    return str(content)


def _normalize_tool_arg_value(value: Any) -> Any:
    """Clean up common structured-output string artifacts."""
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    while len(cleaned) >= 2 and cleaned[0] in {"'", '"', "`"} and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    if cleaned.endswith(("'", '"', "`")) and cleaned.count(cleaned[-1]) == 1:
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def _message_from_role(role: str, content: Any, raw: Optional[Dict[str, Any]] = None) -> BaseMessage:
    """Convert role/content payload to LangChain message objects."""
    text = _extract_text(content)
    role_lower = role.lower()
    raw = raw or {}

    if role_lower in ("system",):
        return SystemMessage(content=text)
    if role_lower in ("assistant", "ai"):
        return AIMessage(content=text)
    if role_lower in ("tool", "function"):
        return ToolMessage(
            content=text,
            tool_call_id=str(raw.get("tool_call_id") or raw.get("id") or "tool_call"),
        )
    return HumanMessage(content=text)


class CodexExecLLM:
    """LangChain-compatible lightweight adapter backed by `codex exec`."""

    def __init__(
        self,
        model: str,
        codex_bin: str = "codex",
        timeout_seconds: int = 180,
        tools: Optional[Sequence[Any]] = None,
    ):
        self.model = model
        self.codex_bin = self._resolve_codex_bin(codex_bin)
        self.timeout_seconds = timeout_seconds
        self._tools: List[Any] = list(tools or [])

    def _resolve_codex_bin(self, codex_bin: str) -> str:
        """Resolve the Codex executable to a concrete path.

        On Windows, `codex` may coexist with a non-executable shim file named
        `codex`, while the real launcher is `codex.cmd` or `codex.exe`.
        Returning the fully resolved path avoids CreateProcess failures.
        """
        if not codex_bin:
            codex_bin = "codex"

        if os.path.isabs(codex_bin) or any(sep in codex_bin for sep in (os.sep, "/")):
            return codex_bin

        candidates = [codex_bin]
        if os.name == "nt":
            candidates = [f"{codex_bin}.cmd", f"{codex_bin}.exe", f"{codex_bin}.bat", codex_bin]

        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved

        return codex_bin

    def bind_tools(self, tools: Sequence[Any], **_: Any) -> "CodexExecLLM":
        """Return a new adapter instance with bound tools."""
        return CodexExecLLM(
            model=self.model,
            codex_bin=self.codex_bin,
            timeout_seconds=self.timeout_seconds,
            tools=tools,
        )

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> AIMessage:
        """Invoke Codex Exec and return an AIMessage."""
        del config, kwargs
        messages = self._coerce_messages(input)
        if self._tools:
            return self._invoke_with_tools(messages)
        return AIMessage(content=self._invoke_text(messages), tool_calls=[])

    def _coerce_messages(self, input: Any) -> List[BaseMessage]:
        """Normalize any supported input payload to message list."""
        if hasattr(input, "to_messages"):
            return list(input.to_messages())
        if isinstance(input, BaseMessage):
            return [input]
        if isinstance(input, str):
            return [HumanMessage(content=input)]
        if isinstance(input, list):
            converted: List[BaseMessage] = []
            for item in input:
                if isinstance(item, BaseMessage):
                    converted.append(item)
                    continue
                if isinstance(item, dict):
                    converted.append(
                        _message_from_role(
                            str(item.get("role", "user")),
                            item.get("content", ""),
                            raw=item,
                        )
                    )
                    continue
                if isinstance(item, tuple) and len(item) == 2:
                    converted.append(_message_from_role(str(item[0]), item[1]))
                    continue
                converted.append(HumanMessage(content=str(item)))
            return converted
        return [HumanMessage(content=str(input))]

    def _format_transcript(self, messages: List[BaseMessage]) -> str:
        """Render messages to compact plain-text transcript for Codex."""
        lines: List[str] = []
        for msg in messages:
            content = _extract_text(getattr(msg, "content", ""))
            if isinstance(msg, SystemMessage):
                lines.append(f"[system]\n{content}")
            elif isinstance(msg, HumanMessage):
                lines.append(f"[user]\n{content}")
            elif isinstance(msg, ToolMessage):
                tool_name = getattr(msg, "name", None) or "tool"
                lines.append(f"[tool:{tool_name}]\n{content}")
            else:
                lines.append(f"[assistant]\n{content}")
        return "\n\n".join(lines)

    def _build_tool_specs(self) -> List[Dict[str, Any]]:
        """Extract tool metadata to guide structured tool-call generation."""
        specs: List[Dict[str, Any]] = []
        for tool in self._tools:
            name = getattr(tool, "name", None)
            if not name:
                continue
            args = getattr(tool, "args", {})
            description = getattr(tool, "description", "")
            input_schema = None
            get_input_schema = getattr(tool, "get_input_schema", None)
            if callable(get_input_schema):
                try:
                    input_schema = get_input_schema().model_json_schema()
                except Exception:
                    input_schema = None
            specs.append(
                {
                    "name": str(name),
                    "description": str(description or ""),
                    "args": args if isinstance(args, dict) else {},
                    "input_schema": input_schema if isinstance(input_schema, dict) else None,
                }
            )
        return specs

    def _build_tool_args_schema(self, tool_specs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a merged args schema acceptable to OpenAI structured outputs.

        Structured outputs here reject `oneOf` and require `additionalProperties: false`
        on every object. We therefore expose a single strict object containing the union of
        all possible tool argument fields, then validate/filter per tool after generation.
        """
        merged_properties: Dict[str, Any] = {}
        for spec in tool_specs:
            input_schema = spec.get("input_schema") or {}
            properties = input_schema.get("properties")
            if not isinstance(properties, dict):
                raw_args = spec.get("args") or {}
                properties = raw_args if isinstance(raw_args, dict) else {}
            for key, value in properties.items():
                if key not in merged_properties and isinstance(value, dict):
                    property_schema = dict(value)
                    prop_type = property_schema.get("type")
                    if isinstance(prop_type, str):
                        property_schema["type"] = [prop_type, "null"]
                    elif isinstance(prop_type, list):
                        if "null" not in prop_type:
                            property_schema["type"] = list(prop_type) + ["null"]
                    else:
                        property_schema["type"] = ["string", "null"]
                    merged_properties[key] = property_schema

        return {
            "type": "object",
            "properties": merged_properties,
            "required": list(merged_properties.keys()),
            "additionalProperties": False,
        }

    def _run_codex_with_schema(self, prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Run `codex exec` using stdin prompt and JSON schema-constrained output."""
        safe_prompt = prompt.encode("utf-8", errors="replace").decode("utf-8")
        with tempfile.TemporaryDirectory(prefix="codex_exec_") as tmpdir:
            schema_path = os.path.join(tmpdir, "schema.json")
            output_path = os.path.join(tmpdir, "response.json")

            with open(schema_path, "w", encoding="utf-8") as f:
                json.dump(schema, f)

            cmd = [
                self.codex_bin,
                "exec",
                "--ephemeral",
                "--color",
                "never",
                "--output-schema",
                schema_path,
                "--output-last-message",
                output_path,
            ]
            if self.model:
                cmd.extend(["--model", self.model])
            cmd.append("-")

            result = subprocess.run(
                cmd,
                input=safe_prompt,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                stdout = (result.stdout or "").strip()
                raise RuntimeError(
                    "codex exec failed "
                    f"(exit={result.returncode}). stderr={stderr or '<empty>'} stdout={stdout or '<empty>'}"
                )

            if not os.path.exists(output_path):
                raise RuntimeError("codex exec did not produce structured output.")

            raw = ""
            with open(output_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()

            if not raw:
                return {}
            return json.loads(raw)

    def _invoke_text(self, messages: List[BaseMessage]) -> str:
        """Plain text generation path for non-tool nodes."""
        schema = {
            "type": "object",
            "properties": {"final_response": {"type": "string"}},
            "required": ["final_response"],
            "additionalProperties": False,
        }
        prompt = (
            "You are executing as a backend model for an agent graph.\n"
            "Return the best possible answer for the latest user/assistant context.\n"
            "Output must satisfy the JSON schema.\n\n"
            "Conversation transcript:\n"
            f"{self._format_transcript(messages)}"
        )
        payload = self._run_codex_with_schema(prompt, schema)
        return str(payload.get("final_response", "")).strip()

    def _invoke_with_tools(self, messages: List[BaseMessage]) -> AIMessage:
        """Structured tool-calling path used by analyst nodes."""
        tool_specs = self._build_tool_specs()
        if not tool_specs:
            return AIMessage(content=self._invoke_text(messages), tool_calls=[])

        tool_names = [spec["name"] for spec in tool_specs]
        tool_name_to_spec = {spec["name"]: spec for spec in tool_specs}
        args_schema = self._build_tool_args_schema(tool_specs)
        schema = {
            "type": "object",
            "properties": {
                "tool_calls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "enum": tool_names},
                            "args": args_schema,
                        },
                        "required": ["name", "args"],
                        "additionalProperties": False,
                    },
                },
                "final_response": {"type": "string"},
            },
            "required": ["tool_calls", "final_response"],
            "additionalProperties": False,
        }

        prompt = (
            "You are an agent that can either request tool calls or provide a final response.\n"
            "Rules:\n"
            "1) If you still need external data, return tool_calls with valid args and keep final_response empty.\n"
            "2) If you already have enough data from tool outputs, return an empty tool_calls array and fill final_response.\n"
            "3) Use only the listed tools and exact argument names.\n"
            "4) Output must satisfy the JSON schema exactly.\n\n"
            "Available tools (JSON):\n"
            f"{json.dumps(tool_specs, ensure_ascii=True)}\n\n"
            "Conversation transcript:\n"
            f"{self._format_transcript(messages)}"
        )

        payload = self._run_codex_with_schema(prompt, schema)
        raw_calls = payload.get("tool_calls") or []

        tool_calls = []
        for call in raw_calls:
            if not isinstance(call, dict):
                continue
            name = call.get("name")
            args = call.get("args")
            if name not in tool_names or not isinstance(args, dict):
                continue

            spec = tool_name_to_spec.get(name) or {}
            input_schema = spec.get("input_schema") or {}
            properties = input_schema.get("properties")
            if not isinstance(properties, dict):
                raw_args = spec.get("args") or {}
                properties = raw_args if isinstance(raw_args, dict) else {}
            allowed_keys = set(properties.keys())
            filtered_args = {
                k: _normalize_tool_arg_value(v)
                for k, v in args.items()
                if k in allowed_keys and v is not None
            }

            required_keys = input_schema.get("required", [])
            if not isinstance(required_keys, list):
                required_keys = []
            if any(key not in filtered_args for key in required_keys):
                continue

            tool_calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:24]}",
                    "type": "tool_call",
                    "name": name,
                    "args": filtered_args,
                }
            )

        if tool_calls:
            return AIMessage(content="", tool_calls=tool_calls)

        final_response = str(payload.get("final_response", "")).strip()
        if not final_response:
            final_response = self._invoke_text(messages)
        return AIMessage(content=final_response, tool_calls=[])


class CodexExecClient(BaseLLMClient):
    """LLM client backed by local `codex exec` CLI."""

    def get_llm(self) -> Any:
        codex_bin = self.kwargs.get("codex_bin", "codex")
        timeout = int(self.kwargs.get("timeout", 180))
        return CodexExecLLM(
            model=self.model,
            codex_bin=codex_bin,
            timeout_seconds=timeout,
        )

    def validate_model(self) -> bool:
        """Accept any model id supported by local Codex CLI."""
        return True
