from pathlib import Path
from agents.base import BaseLLM, PresentationAgent
from agents.orchestrator import OrchestratorAgent

def create_agent(model_type: str, **kwargs) -> PresentationAgent:
    if model_type == "local":
        llm = BaseLLM(kwargs.get("local_base_url", "http://localhost:5000/v1"), "not-needed")
    elif model_type == "gigachat":
        import os
        api_key = kwargs.get("gigachat_api_key") or os.environ.get("GIGACHAT_API_KEY")
        llm = BaseLLM("https://gigachat.devices.sberbank.ru/api/v1", api_key)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    icons_dir = kwargs.get("icons_dir")
    return OrchestratorAgent(llm, icons_dir)