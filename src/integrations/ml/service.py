"""
ML Service - Unified interface for LLM inference.

This service provides a unified interface for running LLM inference with
automatic fallback from Claude API to local GGUF models.

Features:
- Claude API support (Haiku, Sonnet, Opus)
- Vision support (image analysis)
- Local GGUF fallback
- Automatic error handling and retry
"""

import os
import asyncio
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("ml_service")


@dataclass
class ModelConfig:
    """Configuration for a Claude model."""
    id: str
    input_cost: float  # $ per 1M tokens
    output_cost: float  # $ per 1M tokens
    description: str


# Available Claude models
CLAUDE_MODELS = {
    "haiku": ModelConfig(
        id="claude-3-5-haiku-20241022",
        input_cost=0.80,
        output_cost=4.00,
        description="Fast, efficient model for simple tasks (RECOMMENDED)"
    ),
    "sonnet": ModelConfig(
        id="claude-3-5-sonnet-20241022",
        input_cost=3.00,
        output_cost=15.00,
        description="Balanced model for complex reasoning"
    ),
    "opus": ModelConfig(
        id="claude-3-opus-20240229",
        input_cost=15.00,
        output_cost=75.00,
        description="Most powerful model for highly complex tasks"
    ),
}


class MLService:
    """
    Unified ML/LLM inference service.

    Provides a consistent interface for running LLM inference across multiple
    backends (Claude API, local GGUF) with automatic fallback.

    Example:
        >>> ml = MLService(default_model="haiku")
        >>> response = await ml.run_inference(
        ...     "Classify this event",
        ...     image_url="https://example.com/image.png"
        ... )
    """

    def __init__(
        self,
        default_model: str = "haiku",
        gguf_model_path: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the ML service.

        Args:
            default_model: Default Claude model ("haiku", "sonnet", "opus")
            gguf_model_path: Path to local GGUF model file
            api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
        """
        self.default_model = default_model.lower()
        self.gguf_model_path = gguf_model_path or "./qwen3-1.7b-q4_k_m.gguf"

        # Initialize Claude API
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.claude_client = None
        self.use_claude = False

        if self.api_key:
            try:
                import anthropic
                self.claude_client = anthropic.AsyncAnthropic(api_key=self.api_key)
                self.use_claude = True
                model_info = CLAUDE_MODELS[self.default_model]
                logger.info(f"Claude API enabled: {self.default_model} ({model_info.id})")
                logger.info(
                    f"Cost: ${model_info.input_cost}/1M input, "
                    f"${model_info.output_cost}/1M output"
                )
            except ImportError:
                logger.warning(
                    "anthropic package not found. Install with: pip install anthropic"
                )
                self.use_claude = False
            except Exception as e:
                logger.error(f"Failed to initialize Claude API: {e}")
                self.use_claude = False
        else:
            logger.info("Claude API not configured, will use local GGUF only")

        # Initialize local GGUF model
        self.llm = None
        self._load_gguf_model()

    def _load_gguf_model(self):
        """Load the local GGUF model."""
        try:
            from llama_cpp import Llama
            self.llm = Llama(
                model_path=self.gguf_model_path,
                n_ctx=1024,
                n_threads=4,
                verbose=False
            )
            logger.info(f"Local GGUF model loaded: {self.gguf_model_path}")
        except ImportError:
            logger.warning(
                "llama-cpp-python not found. Install with: pip install llama-cpp-python"
            )
        except Exception as e:
            logger.error(f"Failed to load GGUF model: {e}")

    async def run_inference(
        self,
        text: str,
        *,
        max_tokens: int = 512,
        image_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """
        Run LLM inference with automatic fallback.

        Tries Claude API first (if available), then falls back to local GGUF.

        Args:
            text: The prompt to send to the LLM
            max_tokens: Maximum tokens to generate
            image_url: Optional image URL for vision analysis (Claude only)
            model: Override default model ("haiku", "sonnet", "opus")
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)

        Returns:
            LLM response text, or None if all methods fail
        """
        model_name = (model or self.default_model).lower()

        logger.debug(
            f"Running inference (model={model_name}, max_tokens={max_tokens}, "
            f"has_image={bool(image_url)})"
        )
        logger.debug(f"Prompt preview: {text[:200]}...")

        # Try Claude API first
        if self.use_claude and self.claude_client:
            try:
                result = await self._claude_inference(
                    text, max_tokens, image_url, model_name, temperature
                )
                if result:
                    return result
            except Exception as e:
                logger.warning(f"Claude API failed: {e}, falling back to GGUF")

        # Fallback to local GGUF
        if self.llm:
            try:
                result = await self._gguf_inference(text, max_tokens)
                if result:
                    return result
            except Exception as e:
                logger.error(f"GGUF inference failed: {e}")

        logger.error("All LLM inference methods failed")
        return None

    async def _claude_inference(
        self,
        text: str,
        max_tokens: int,
        image_url: Optional[str],
        model: str,
        temperature: float,
    ) -> Optional[str]:
        """Run inference using Claude API."""
        if model not in CLAUDE_MODELS:
            logger.warning(f"Unknown model '{model}', using default")
            model = self.default_model

        model_config = CLAUDE_MODELS[model]
        logger.debug(f"Using Claude model: {model_config.id}")

        # Build content - add image if provided
        content = []
        if image_url:
            content.append({
                "type": "image",
                "source": {
                    "type": "url",
                    "url": image_url
                }
            })
            logger.debug("Added image to Claude request (vision enabled)")

        content.append({
            "type": "text",
            "text": text
        })

        # Make API call
        response = await self.claude_client.messages.create(
            model=model_config.id,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "user", "content": content}
            ]
        )

        result = response.content[0].text.strip()
        logger.debug(f"Claude response preview: {result[:200]}...")
        return result

    async def _gguf_inference(self, text: str, max_tokens: int) -> Optional[str]:
        """Run inference using local GGUF model."""
        logger.debug("Using local GGUF model")

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None,
            lambda: self.llm(
                text,
                max_tokens=max_tokens,
                stop=["<|endoftext|>", "\n\n\n"]
            )
        )

        result = output["choices"][0]["text"].strip()
        logger.debug(f"GGUF response preview: {result[:200]}...")
        return result

    def is_available(self) -> bool:
        """Check if any LLM backend is available."""
        return self.use_claude or self.llm is not None

    def get_status(self) -> dict:
        """Get status of all backends."""
        return {
            "claude_available": self.use_claude,
            "claude_model": self.default_model if self.use_claude else None,
            "gguf_available": self.llm is not None,
            "gguf_model_path": self.gguf_model_path if self.llm else None,
        }


__all__ = ['MLService', 'CLAUDE_MODELS', 'ModelConfig']
