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


def readme_text_with_fallback(relative_to_pyre_package: str = "README.txt") -> str:
    """
    Prefer the repository README.rst next to the installed ``pyre`` package (nornir-pyre/README.rst),
    then fall back to a file under the pyre package (e.g. README.txt).
    """
    pkg_root = os.path.dirname(pyre.__path__[0])
    rst_path = os.path.join(pkg_root, 'README.rst')
    if os.path.isfile(rst_path):
        with open(rst_path, encoding='utf-8') as h_rst:
            return _strip_rst_for_plain_text(h_rst.read())

    readme_path = os.path.join(pyre.__path__[0], relative_to_pyre_package)
    if not os.path.exists(readme_path):
        return "No readme was found at " + readme_path + " (and no README.rst at " + rst_path + ")"

    with open(readme_path, encoding='utf-8') as h_readme:
        return h_readme.read()


def README() -> str:
    """Returns primary user documentation for console startup and help dialogs."""
    return readme_text_with_fallback("README.txt")
