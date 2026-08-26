from importlib.util import find_spec


def test_approved_resume_rendering_dependencies_are_runtime_available() -> None:
    assert find_spec("docx") is not None
    assert find_spec("reportlab") is not None
    assert find_spec("pypdf") is not None
