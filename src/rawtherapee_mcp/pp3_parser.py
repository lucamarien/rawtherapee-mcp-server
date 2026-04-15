"""Custom PP3 profile reader/writer.

RawTherapee PP3 files use INI-style format but with semicolons as value
separators (e.g. Threshold=20;80;2000;1200;) which breaks configparser.
This module provides a simple line-by-line parser that preserves semicolons.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class PP3Profile:
    """Read, write, and manipulate RawTherapee PP3 processing profiles."""

    def __init__(self) -> None:
        self._sections: dict[str, dict[str, str]] = {}

    def load(self, path: Path) -> None:
        """Parse a PP3 file from disk.

        Args:
            path: Path to the PP3 file.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        self.loads(path.read_text(encoding="utf-8"))

    def loads(self, text: str) -> None:
        """Parse PP3 content from a string.

        Args:
            text: PP3 file content as string.
        """
        self._sections.clear()
        current_section = ""

        for line in text.splitlines():
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Section header
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1]
                if current_section not in self._sections:
                    self._sections[current_section] = {}
                continue

            # Key=Value pair (split on first = only, preserving semicolons in values)
            if "=" in stripped and current_section:
                key, value = stripped.split("=", 1)
                self._sections[current_section][key.strip()] = value.strip()

    def save(self, path: Path) -> None:
        """Write the profile to a PP3 file.

        Args:
            path: Path to write the PP3 file.
        """
        path.write_text(self.dumps(), encoding="utf-8")

    def dumps(self) -> str:
        """Serialize the profile to a PP3 string.

        Returns:
            PP3 file content as string.
        """
        lines: list[str] = []
        for section_name, keys in self._sections.items():
            lines.append(f"[{section_name}]")
            for key, value in keys.items():
                lines.append(f"{key}={value if value is not None else ''}")
            lines.append("")
        return "\n".join(lines)

    def set(self, section: str, key: str, value: str) -> None:
        """Set a value, creating the section if needed.

        Args:
            section: Section name (e.g. "Exposure").
            key: Key name (e.g. "Compensation").
            value: Value as string.
        """
        if section not in self._sections:
            self._sections[section] = {}
        self._sections[section][key] = str(value) if value is not None else ""

    def get(self, section: str, key: str, default: str = "") -> str:
        """Get a value with optional default.

        Args:
            section: Section name.
            key: Key name.
            default: Default value if key not found.

        Returns:
            The value as string, or default.
        """
        value = self._sections.get(section, {}).get(key, default)
        if value is None:
            return default if default is not None else ""
        return value

    def has_section(self, section: str) -> bool:
        """Check if a section exists.

        Args:
            section: Section name to check.

        Returns:
            True if the section exists.
        """
        return section in self._sections

    def has_key(self, section: str, key: str) -> bool:
        """Check if a key exists in a section.

        Args:
            section: Section name.
            key: Key name.

        Returns:
            True if the key exists in the section.
        """
        return key in self._sections.get(section, {})

    def sections(self) -> list[str]:
        """Get all section names.

        Returns:
            List of section names.
        """
        return list(self._sections.keys())

    def keys(self, section: str) -> list[str]:
        """Get all keys in a section.

        Args:
            section: Section name.

        Returns:
            List of key names, or empty list if section doesn't exist.
        """
        return list(self._sections.get(section, {}).keys())

    def merge(self, other: PP3Profile) -> None:
        """Merge another profile on top of this one.

        Values from `other` override values in this profile.

        Args:
            other: Profile to merge from.
        """
        for section_name, keys in other._sections.items():
            if section_name not in self._sections:
                self._sections[section_name] = {}
            self._sections[section_name].update(keys)

    def copy(self) -> PP3Profile:
        """Return a deep copy of this profile.

        Returns:
            A new PP3Profile with the same sections and key-value pairs.
        """
        clone = PP3Profile()
        clone._sections = {s: dict(kvs) for s, kvs in self._sections.items()}
        return clone

    def to_dict(self) -> dict[str, dict[str, str]]:
        """Convert to a plain dictionary.

        Returns:
            Nested dict of section -> key -> value.
        """
        return {section: dict(keys) for section, keys in self._sections.items()}

    def diff(self, other: PP3Profile) -> dict[str, Any]:
        """Compare this profile with another and return differences.

        Args:
            other: Profile to compare against.

        Returns:
            Dict with 'only_a', 'only_b', and 'different' keys.
        """
        only_a: dict[str, dict[str, str]] = {}
        only_b: dict[str, dict[str, str]] = {}
        different: dict[str, dict[str, dict[str, str]]] = {}

        all_sections = set(self._sections.keys()) | set(other._sections.keys())

        for section in sorted(all_sections):
            a_keys = self._sections.get(section, {})
            b_keys = other._sections.get(section, {})
            all_keys = set(a_keys.keys()) | set(b_keys.keys())

            for key in sorted(all_keys):
                in_a = key in a_keys
                in_b = key in b_keys

                if in_a and not in_b:
                    if section not in only_a:
                        only_a[section] = {}
                    only_a[section][key] = a_keys[key]
                elif in_b and not in_a:
                    if section not in only_b:
                        only_b[section] = {}
                    only_b[section][key] = b_keys[key]
                elif in_a and in_b and a_keys[key] != b_keys[key]:
                    if section not in different:
                        different[section] = {}
                    different[section][key] = {"a": a_keys[key], "b": b_keys[key]}

        return {"only_a": only_a, "only_b": only_b, "different": different}

    @classmethod
    def interpolate(cls, a: PP3Profile, b: PP3Profile, factor: float) -> PP3Profile:
        """Linearly interpolate between two profiles.

        ``factor=0.0`` returns profile *a*, ``factor=1.0`` returns profile *b*.
        Numeric values are interpolated; non-numeric values (strings, semicolon
        lists) are taken from the nearer profile (a if factor < 0.5, else b).

        Args:
            a: First profile.
            b: Second profile.
            factor: Blend factor in [0.0, 1.0].

        Returns:
            A new PP3Profile with interpolated values.
        """
        factor = max(0.0, min(1.0, factor))
        result = cls()

        all_sections = set(a._sections.keys()) | set(b._sections.keys())

        for section in all_sections:
            a_keys = a._sections.get(section, {})
            b_keys = b._sections.get(section, {})
            all_keys = set(a_keys.keys()) | set(b_keys.keys())

            for key in all_keys:
                a_val = a_keys.get(key)
                b_val = b_keys.get(key)

                if a_val is not None and b_val is not None:
                    # Both profiles have this key — try numeric interpolation
                    if ";" in a_val or ";" in b_val:
                        # Semicolon-delimited lists: pick nearer side
                        result.set(section, key, a_val if factor < 0.5 else b_val)
                    else:
                        try:
                            a_num = float(a_val)
                            b_num = float(b_val)
                            interp = a_num + (b_num - a_num) * factor
                            # Preserve integer formatting when both inputs are ints
                            if "." not in a_val and "." not in b_val:
                                result.set(section, key, str(round(interp)))
                            else:
                                result.set(section, key, f"{interp:.6g}")
                        except ValueError:
                            # Non-numeric: pick nearer side
                            result.set(section, key, a_val if factor < 0.5 else b_val)
                elif a_val is not None:
                    result.set(section, key, a_val)
                elif b_val is not None:
                    result.set(section, key, b_val)

        return result
