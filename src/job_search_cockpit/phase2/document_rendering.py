from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from pypdf import PdfReader
from reportlab.lib import colors  # type: ignore[import-untyped]
from reportlab.lib.enums import TA_CENTER  # type: ignore[import-untyped]
from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # type: ignore[import-untyped]
from reportlab.lib.units import inch  # type: ignore[import-untyped]
from reportlab.platypus import (  # type: ignore[import-untyped]
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from job_search_cockpit.phase2.resume_documents import CanonicalResumeDocument

_NAVY = RGBColor(10, 45, 80)
_GOLD = RGBColor(176, 133, 35)


@dataclass(frozen=True, slots=True)
class RenderedResumeFiles:
    docx_path: Path
    pdf_path: Path


class LocalResumeRenderer:
    def render(
        self,
        *,
        document: CanonicalResumeDocument,
        output_dir: Path,
        stem: str,
        headshot_path: Path,
    ) -> RenderedResumeFiles:
        output_dir.mkdir(parents=True, exist_ok=False)
        docx_path = output_dir / f"{stem}.docx"
        pdf_path = output_dir / f"{stem}.pdf"
        self._render_docx(document, docx_path, headshot_path)
        self._render_pdf(document, pdf_path, headshot_path)
        return RenderedResumeFiles(docx_path=docx_path, pdf_path=pdf_path)

    @staticmethod
    def _render_docx(
        document: CanonicalResumeDocument, output_path: Path, headshot_path: Path
    ) -> None:
        doc = Document()
        section = doc.sections[0]
        section.top_margin = Inches(0.7)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)

        photo = doc.add_paragraph()
        photo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        photo.add_run().add_picture(str(headshot_path), width=Inches(0.9))
        title = doc.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title.add_run(document.title)
        title_run.bold = True
        title_run.font.name = "Arial"
        title_run.font.size = Pt(18)
        title_run.font.color.rgb = _NAVY
        accent = doc.add_paragraph()
        accent.alignment = WD_ALIGN_PARAGRAPH.CENTER
        accent_run = accent.add_run("━")
        accent_run.font.size = Pt(18)
        accent_run.font.color.rgb = _GOLD
        heading = doc.add_paragraph()
        heading_run = heading.add_run(document.section_title)
        heading_run.bold = True
        heading_run.font.name = "Arial"
        heading_run.font.size = Pt(11)
        heading_run.font.color.rgb = _NAVY
        for entry in document.entries:
            paragraph = doc.add_paragraph(style="List Bullet")
            run = paragraph.add_run(entry.safe_wording)
            run.font.name = "Arial"
            run.font.size = Pt(10.5)
        doc.save(str(output_path))

    @staticmethod
    def _render_pdf(
        document: CanonicalResumeDocument, output_path: Path, headshot_path: Path
    ) -> None:
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "resume-title",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0A2D50"),
            spaceAfter=4,
        )
        heading_style = ParagraphStyle(
            "resume-heading",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#0A2D50"),
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "resume-body",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14,
            spaceAfter=5,
        )
        story = [
            Image(str(headshot_path), width=0.9 * inch, height=0.9 * inch),
            Spacer(1, 0.08 * inch),
            Paragraph(document.title, title_style),
            HRFlowable(
                width="30%",
                thickness=1.5,
                color=colors.HexColor("#B08523"),
                spaceBefore=2,
                spaceAfter=10,
                hAlign="CENTER",
            ),
            Paragraph(document.section_title, heading_style),
        ]
        story.extend(Paragraph(entry.safe_wording, body_style) for entry in document.entries)
        SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            leftMargin=0.7 * inch,
            rightMargin=0.7 * inch,
            topMargin=0.7 * inch,
            bottomMargin=0.7 * inch,
        ).build(story)


def extract_docx_text(path: Path) -> str:
    return _normalise_lines(paragraph.text for paragraph in Document(str(path)).paragraphs)


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return _normalise_lines(page.extract_text() or "" for page in reader.pages)


def _normalise_lines(parts: Iterable[str]) -> str:
    lines: list[str] = []
    for part in parts:
        for line in str(part).splitlines():
            normalised = " ".join(line.split())
            if normalised and normalised != "━":
                lines.append(normalised.removeprefix("• "))
    return "\n\n".join(lines)
