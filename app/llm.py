"""
LLM setup and configuration for the Warranty Claims Agent.

Supports Ollama (local), Groq (cloud), Gemini (cloud), and OpenAI (cloud) providers.
Priority: Ollama > Groq > Gemini
"""

import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


class OllamaClient:
    """Ollama local LLM client."""
    
    def __init__(self, model: str = "qwen2.5:1.5b", base_url: str = "http://localhost:11434"):
        import requests
        self.model_name = model
        self.base_url = base_url
        self.requests = requests
        
        # Test connection
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                print(f"[OK] LLM initialized: Ollama/{model} (local)")
            else:
                raise Exception("Ollama not responding")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to Ollama at {base_url}: {e}")
    
    def generate(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> str:
        """Generate a response from Ollama."""
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"
        
        response = self.requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model_name,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            },
            timeout=120
        )
        
        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            raise Exception(f"Ollama error: {response.text}")
    
    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> str:
        """Generate a JSON response."""
        json_instruction = (
            "You must respond with valid JSON only. No markdown, no code blocks, "
            "no explanation text. Just the raw JSON object."
        )
        
        if system_instruction:
            system_instruction = f"{system_instruction}\n\n{json_instruction}"
        else:
            system_instruction = json_instruction
            
        return self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature
        )


class GroqClient:
    """Groq API client for fast LLM inference."""
    
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self.model_name = model
        print(f"[OK] LLM initialized: Groq/{model}")
    
    def generate(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> str:
        """Generate a response from Groq."""
        messages = []
        
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content
    
    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> str:
        """Generate a JSON response."""
        json_instruction = (
            "You must respond with valid JSON only. No markdown, no code blocks, "
            "no explanation text. Just the raw JSON object."
        )
        
        if system_instruction:
            system_instruction = f"{system_instruction}\n\n{json_instruction}"
        else:
            system_instruction = json_instruction
            
        return self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature
        )


class OpenAIClient:
    """OpenAI API client."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model_name = model
        print(f"[OK] LLM initialized: OpenAI/{model}")
    
    def generate(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> str:
        """Generate a response from OpenAI."""
        messages = []
        
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        
        messages.append({"role": "user", "content": prompt})
        
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        return response.choices[0].message.content
    
    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> str:
        """Generate a JSON response."""
        json_instruction = (
            "You must respond with valid JSON only. No markdown, no code blocks, "
            "no explanation text. Just the raw JSON object."
        )
        
        if system_instruction:
            system_instruction = f"{system_instruction}\n\n{json_instruction}"
        else:
            system_instruction = json_instruction
            
        return self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature
        )


class GeminiClient:
    """Google Gemini API client."""
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
        self.model_name = model
        self.genai = genai
        print(f"[OK] LLM initialized: Gemini/{model}")
    
    def generate(
        self, 
        prompt: str, 
        system_instruction: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048
    ) -> str:
        """Generate a response from Gemini."""
        generation_config = self.genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        
        full_prompt = prompt
        if system_instruction:
            full_prompt = f"{system_instruction}\n\n{prompt}"
        
        response = self.model.generate_content(
            full_prompt,
            generation_config=generation_config
        )
        
        return response.text
    
    def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2
    ) -> str:
        """Generate a JSON response."""
        json_instruction = (
            "You must respond with valid JSON only. No markdown, no code blocks, "
            "no explanation text. Just the raw JSON object."
        )
        
        if system_instruction:
            system_instruction = f"{system_instruction}\n\n{json_instruction}"
        else:
            system_instruction = json_instruction
            
        return self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature
        )


# Mock LLM removed to enforce real LLM usage

# Singleton instance
_llm_instance = None
_llm_config = None


def reset_llm():
    """Reset the cached LLM instance."""
    global _llm_instance, _llm_config
    _llm_instance = None
    _llm_config = None


def get_llm(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    force_new: bool = False
):
    """
    Get the singleton LLM client instance.
    Priority (auto): Ollama (local) > Groq (cloud) > Gemini (cloud)
    """
    global _llm_instance, _llm_config

    if provider is None and _llm_config:
        provider = _llm_config.get("provider") or "auto"
        api_key = api_key or _llm_config.get("api_key") or None
        model = model or _llm_config.get("model") or None

    normalized = (provider or "auto").strip().lower()
    config = {
        "provider": normalized,
        "api_key": api_key or "",
        "model": model or ""
    }

    if _llm_instance is not None and not force_new and _llm_config == config:
        return _llm_instance

    _llm_instance = None
    _llm_config = config

    if normalized in ("auto", ""):
        # Try Ollama first (local, no API costs)
        use_ollama = os.getenv("USE_OLLAMA", "true").lower() == "true"
        ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        
        if use_ollama:
            try:
                _llm_instance = OllamaClient(model=ollama_model, base_url=ollama_url)
                return _llm_instance
            except Exception as e:
                print(f"[WARN] Ollama not available: {e}")
        
        # Try Groq second (fast cloud, generous free tier)
        groq_key = os.getenv("GROQ_API_KEY")
        if groq_key:
            try:
                _llm_instance = GroqClient(
                    api_key=groq_key,
                    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
                )
                return _llm_instance
            except Exception as e:
                print(f"[WARN] Groq initialization failed: {e}")
        
        # Fall back to Gemini
        google_key = os.getenv("GOOGLE_API_KEY")
        if google_key:
            try:
                _llm_instance = GeminiClient(
                    api_key=google_key,
                    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
                )
                return _llm_instance
            except Exception as e:
                print(f"[WARN] Gemini initialization failed: {e}")
        
        raise ValueError(
            "No LLM available. Start Ollama, or set GROQ_API_KEY or GOOGLE_API_KEY in your .env file."
        )

    if normalized == "ollama":
        ollama_model = model or os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b")
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        _llm_instance = OllamaClient(model=ollama_model, base_url=ollama_url)
        return _llm_instance

    if normalized == "groq":
        groq_key = api_key or os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY is required for Groq.")
        _llm_instance = GroqClient(
            api_key=groq_key,
            model=model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        )
        return _llm_instance

    if normalized == "gemini":
        google_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not google_key:
            raise ValueError("GOOGLE_API_KEY is required for Gemini.")
        _llm_instance = GeminiClient(
            api_key=google_key,
            model=model or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        )
        return _llm_instance

    if normalized == "openai":
        openai_key = api_key or os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI.")
        _llm_instance = OpenAIClient(
            api_key=openai_key,
            model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        )
        return _llm_instance

    raise ValueError(f"Unknown provider: {provider}")
