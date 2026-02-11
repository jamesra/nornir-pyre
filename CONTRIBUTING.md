# Contributing to nornir-pyre

Thank you for your interest in contributing to nornir-pyre! This document provides guidelines and instructions for contributing to the project.

## Development Environment Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/jamesra/nornir-pyre.git
   cd nornir-pyre
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/Mac:
   source venv/bin/activate
   ```

3. Install development dependencies:
   ```bash
   pip install -r requirements-v1.5.2.txt
   ```

## Code Style Guidelines

### Python Style

- Follow PEP 8 style guidelines
- Use 4 spaces for indentation (no tabs)
- Maximum line length of 120 characters
- Use meaningful variable and function names
- Add type hints to function signatures

### Documentation Style

- Use NumPy or Google style docstrings
- Document all public classes, methods, and functions
- Include parameter descriptions, return values, and exceptions
- Provide examples for complex functionality

Example docstring:
```python
def add_context(self, context: QOpenGLContext):
    """
    Add a context to the manager and notify subscribers.

    This method adds the provided OpenGL context to the list of known contexts
    if it's not already present. It then invokes the diagnose_gl_context_sharing
    function to check context sharing and notifies all subscribers about the new context.

    Args:
        context: The OpenGL context to add to the manager

    Returns:
        None
    """
```

## Project Structure

The nornir-pyre package is organized into several key modules:

- **pyre.gl_engine**: OpenGL rendering engine for high-performance image visualization
- **pyre.ui**: User interface components built with PyQt6
- **pyre.views**: View implementations for different visualization modes
- **pyre.state**: State management and controllers
- **pyre.commands**: Command pattern implementations for operations
- **pyre.interfaces**: Interface definitions for dependency injection

## Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting a pull request
- Use the existing test framework

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature-name`)
3. Make your changes
4. Run tests to ensure they pass
5. Update documentation as needed
6. Commit your changes (`git commit -am 'Add some feature'`)
7. Push to the branch (`git push origin feature/your-feature-name`)
8. Create a new Pull Request

## QT Migration

The project is currently migrating from wxPython to PyQt6. If you're working on UI components:

1. Refer to the QT_MIGRATION_README.md file for details on the migration
2. Follow the established patterns for QT implementation
3. Maintain compatibility with the existing architecture
4. Use the naming convention of adding `_qt` suffix to migrated files

## Dependency Injection

The project uses dependency injection for managing dependencies:

1. Define interfaces in the `pyre.interfaces` package
2. Register implementations in the container setup in `launcher.py`
3. Use `@inject` decorator and `Provide` for dependency resolution

## OpenGL Development

When working with OpenGL components:

1. Ensure context sharing is properly maintained
2. Use the GLContextManager for managing OpenGL contexts
3. Follow the established patterns for shader and texture management
4. Test on multiple platforms and graphics hardware when possible
5. **IMPORTANT**: Follow the OpenGL error handling rules in `OPENGL_ERROR_HANDLING_RULES.md`
   - Never add loops that clear errors without reporting them
   - Use `raise_on_error()` for critical operations
   - Use `check_for_error()` for cleanup/error handlers

## Documentation

- Update README.rst when adding new features
- Keep docstrings up-to-date with code changes
- Document complex algorithms and design decisions
- Add examples for new functionality

## License

By contributing to nornir-pyre, you agree that your contributions will be licensed under the project's license.