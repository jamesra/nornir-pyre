import logging
import os
import re

import pyre


def ResourcePath() -> str:
    Logger = logging.getLogger("resources")
    rpath = os.path.join(pyre.__path__[0], 'resources')
    Logger.info('Resources path: ' + rpath)
    return rpath


def _strip_rst_for_plain_text(text: str) -> str:
    """Light cleanup so README.rst is readable in a QMessageBox / console."""
    lines_out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) >= 3 and set(stripped) <= set('=~-`^*#'):
            continue
        if stripped.startswith('.. '):
            continue
        lines_out.append(line)
    out = '\n'.join(lines_out)
    out = re.sub(r'`([^`]+)`', r'\1', out)
    return out


CONTROLS_HELP_ANCHOR = "Mouse Controls"

# Section headings that end the mouse/keyboard help block (first match wins).
_CONTROLS_SECTION_END_MARKERS = (
    "Troubleshooting",
    "About",
)


def controls_help_anchor_index(text: str, anchor: str = CONTROLS_HELP_ANCHOR) -> int:
    """Return the line index of ``anchor`` in plain help text, or ``0`` if missing."""
    for index, line in enumerate(text.splitlines()):
        if line.strip() == anchor:
            return index
    return 0


def controls_help_section(text: str) -> str | None:
    """Return the Mouse Controls through Keyboard Controls block, or ``None`` if absent."""
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == CONTROLS_HELP_ANCHOR:
            start = index
            break
    if start is None:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip() in _CONTROLS_SECTION_END_MARKERS:
            end = index
            break

    section_lines = lines[start:end]
    while section_lines and not section_lines[-1].strip():
        section_lines.pop()
    if not section_lines:
        return None
    return "\n".join(section_lines)


def readme_text_with_fallback(relative_to_pyre_package: str = "README.txt") -> str:
    """
    Prefer the packaged in-app help file (``pyre/README.txt``, mouse/keyboard controls),
    then the repository landing ``README.rst`` next to the ``pyre`` package.
    """
    readme_path = os.path.join(pyre.__path__[0], relative_to_pyre_package)
    if os.path.isfile(readme_path):
        with open(readme_path, encoding='utf-8') as h_readme:
            return h_readme.read()

    pkg_root = os.path.dirname(pyre.__path__[0])
    rst_path = os.path.join(pkg_root, 'README.rst')
    if os.path.isfile(rst_path):
        with open(rst_path, encoding='utf-8') as h_rst:
            return _strip_rst_for_plain_text(h_rst.read())

    return (
        "No readme was found at " + readme_path
        + " (and no README.rst at " + rst_path + ")"
    )


def README() -> str:
    """Returns primary user documentation for console startup and help dialogs."""
    return readme_text_with_fallback("README.txt")
