"""Guardrails for input/output safety checks"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings
from app.services.llm.provider import QwenProvider
from app.services.llm.prompts import PromptTemplates

logger = logging.getLogger(__name__)


@dataclass
class SafetyResult:
    """Result of safety check"""
    is_safe: bool
    reason: Optional[str] = None
    categories: dict = None
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = {}


class GuardrailService:
    """
    Pre-LLM and post-LLM safety checks.
    
    Checks:
    - Prompt injection attempts
    - PII leakage
    - Toxic/harmful content
    - System prompt extraction
    """
    
    def __init__(self):
        self.enabled = settings.GUARDRAILS_ENABLED
        self.llm_provider = QwenProvider() if self.enabled else None
        
        # Simple pattern-based detection for common attacks
        self.injection_patterns = [
            "ignore previous",
            "system:",
            "you are now",
            "forget all",
            "bypass",
            "jailbreak",
            "dan ",
            "developer mode",
            "output your instructions",
            "print your prompt",
        ]
    
    async def check_input(self, user_input: str) -> SafetyResult:
        """
        Check user input for safety issues before sending to LLM.
        
        Args:
            user_input: Raw user query
            
        Returns:
            SafetyResult with is_safe flag and reason
        """
        if not self.enabled:
            return SafetyResult(is_safe=True)
        
        # Pattern-based detection (fast)
        pattern_result = self._check_patterns(user_input)
        if not pattern_result.is_safe:
            return pattern_result
        
        # LLM-based detection (slower but more accurate)
        if settings.GUARDRAILS_USE_LLM:
            return await self._llm_safety_check(user_input)
        
        return SafetyResult(is_safe=True)
    
    def _check_patterns(self, user_input: str) -> SafetyResult:
        """Quick pattern-based injection detection"""
        input_lower = user_input.lower()
        
        for pattern in self.injection_patterns:
            if pattern in input_lower:
                logger.warning(f"Detected injection pattern: {pattern}")
                return SafetyResult(
                    is_safe=False,
                    reason=f"Potential prompt injection detected: '{pattern}'",
                    categories={"injection": True}
                )
        
        return SafetyResult(is_safe=True)
    
    async def _llm_safety_check(self, user_input: str) -> SafetyResult:
        """Use LLM to detect sophisticated attacks"""
        try:
            messages = [
                {"role": "user", "content": PromptTemplates.build_safety_prompt(user_input)}
            ]
            
            response = await self.llm_provider.generate_with_retry(
                messages,
                temperature=0.0,  # Deterministic for safety checks
                max_tokens=50,
            )
            
            result_text = response.content.strip().upper()
            
            if result_text.startswith("UNSAFE"):
                reason = result_text[6:].strip() or "Content flagged as unsafe"
                return SafetyResult(
                    is_safe=False,
                    reason=reason,
                    categories={"llm_flagged": True}
                )
            elif result_text.startswith("SAFE"):
                return SafetyResult(is_safe=True)
            else:
                logger.warning(f"Ambiguous safety check result: {result_text}")
                return SafetyResult(is_safe=True)
                
        except Exception as e:
            logger.error(f"Safety check failed: {e}")
            # Fail open - allow request if safety check fails
            return SafetyResult(is_safe=True, reason="Safety check error")
    
    async def check_output(self, generated_text: str) -> SafetyResult:
        """
        Check LLM output for safety issues before returning to user.
        
        Args:
            generated_text: LLM-generated response
            
        Returns:
            SafetyResult with is_safe flag
        """
        if not self.enabled:
            return SafetyResult(is_safe=True)
        
        # Check for PII patterns (simple regex)
        import re
        
        # Email pattern
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', generated_text)
        if emails:
            logger.warning(f"Detected potential email in output: {emails[0]}")
            return SafetyResult(
                is_safe=False,
                reason="Potential PII (email) detected in response",
                categories={"pii": True}
            )
        
        # Phone pattern (US)
        phones = re.findall(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', generated_text)
        if phones:
            logger.warning(f"Detected potential phone number in output")
            return SafetyResult(
                is_safe=False,
                reason="Potential PII (phone number) detected in response",
                categories={"pii": True}
            )
        
        # Could add more checks: toxicity, hate speech, etc.
        
        return SafetyResult(is_safe=True)
    
    def redact_pii(self, text: str) -> str:
        """Redact PII from text"""
        import re
        
        # Redact emails
        text = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '[EMAIL_REDACTED]',
            text
        )
        
        # Redact US phone numbers
        text = re.sub(
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            '[PHONE_REDACTED]',
            text
        )
        
        return text
