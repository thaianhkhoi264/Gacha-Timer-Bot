"""
Machine Learning integration module.

This package provides ML-related functionality:
- LLM inference for event extraction from images/text
- Claude API support (Haiku, Sonnet, Opus)
- Local GGUF model fallback
- Vision support for image analysis
"""

from .service import MLService, CLAUDE_MODELS, ModelConfig

__all__ = [
    'MLService',
    'CLAUDE_MODELS',
    'ModelConfig',
]
