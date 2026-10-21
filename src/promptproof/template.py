"""Minimal ``{{variable}}`` template rendering.

Deliberately tiny: a suite is data, not code, so PromptProof does not pull in
a full templating engine. Supported syntax is exactly ``{{ name }}`` with
optional surrounding whitespace. Unknown variables are an error, so a typo
fails loudly in CI instead of silently sending ``{{review}}`` to a model.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from .errors import TemplateError

_VARIABLE_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def find_variables(template: str) -> list[str]:
    """Return the variable names referenced by *template*, in order."""
    return _VARIABLE_RE.findall(template)


def render_template(template: str, variables: Mapping[str, Any]) -> str:
    """Render *template* by substituting ``{{name}}`` placeholders.

    Raises:
        TemplateError: if the template references a variable that is not
            present in *variables*.
    """

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise TemplateError(
                f"template references unknown variable {name!r}; "
                f"available: {sorted(variables) or '[]'}"
            )
        return str(variables[name])

    return _VARIABLE_RE.sub(_replace, template)
