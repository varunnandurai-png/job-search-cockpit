from pathlib import Path
from docx import Document
from pypdf import PdfReader
from job_search_cockpit.phase2.executive_resume import (
    ExecutiveResumeData,
    generate_executive_docx,
    generate_executive_pdf,
)


def test_executive_resume_generation(tmp_path: Path) -> None:
    data = ExecutiveResumeData()
    docx_path = tmp_path / "test_resume.docx"
    pdf_path = tmp_path / "test_resume.pdf"

    generate_executive_docx(data, docx_path, target_company="Eltropy", target_role="Senior Product Manager")
    generate_executive_pdf(data, pdf_path, target_company="Eltropy", target_role="Senior Product Manager")

    assert docx_path.exists()
    assert pdf_path.exists()

    # Check DOCX content
    doc = Document(docx_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "NANDURI VARUN" in text
    assert "JPMorganChase" in text
    assert "Walmart Global Tech" in text
    assert "Alliance School of Business" in text
    assert "Professional Scrum Product Owner" in text

    # Check PDF content
    reader = PdfReader(pdf_path)
    pdf_text = "\n".join(page.extract_text() for page in reader.pages)
    assert "NANDURI VARUN" in pdf_text
    assert "JPMorganChase" in pdf_text
    assert "Walmart Global Tech" in pdf_text
    assert "Alliance School of Business" in pdf_text
