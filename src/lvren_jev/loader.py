from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .definitions import DecisionDefinition
from .errors import DefinitionError


def load_decision_definition(path: str | Path) -> DecisionDefinition:
    """Load one YAML or JSON decision file into a validated definition."""
    definition_path = Path(path)
    if not definition_path.is_file():
        raise DefinitionError(f"decision definition does not exist: {definition_path}")

    try:
        text = definition_path.read_text(encoding="utf-8")
        if definition_path.suffix.lower() == ".json":
            raw: Any = json.loads(text)
        elif definition_path.suffix.lower() in {".yaml", ".yml"}:
            import yaml

            raw = yaml.safe_load(text)
        else:
            raise DefinitionError("decision definition must use .yaml, .yml, or .json")
    except DefinitionError:
        raise
    except Exception as error:
        raise DefinitionError(f"failed to load decision definition {definition_path}: {error}") from error

    try:
        return DecisionDefinition.from_mapping(raw)
    except DefinitionError:
        raise
    except Exception as error:
        raise DefinitionError(f"invalid decision definition {definition_path}: {error}") from error
