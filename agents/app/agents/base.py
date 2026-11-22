from typing import Protocol


class Agent(Protocol):
    """Every agent exposes a name, a short description and a version.

    Stage 2 and 3 agents (reader, extractor, researcher, challenger, ...) will follow the same shape:
    one pydantic request, one pydantic response, no hidden state.
    """

    name: str
    description: str
    version: str
