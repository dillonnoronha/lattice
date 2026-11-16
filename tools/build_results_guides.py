"""Build the two printable Lattice handouts with ReportLab (authoring dependency only)."""
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "pdf"

STUDENTS = [
    'Open Lattice and select <b>Start a blank results sheet</b>. Go to <b>Prepare data &gt; Add an observation</b>.',
    'Enter your lab group code, instructor/section, semester, experiment date, and trial number. Use the labels provided by your instructor.',
    'Enter the compound\'s elements and ratios, then select the observed phase and bubble response. Choose <b>not tested</b> if the bubble test was not performed.',
    'Click <b>Build and check compound</b>. Correct any issues, then click <b>Add to project dataset</b>. Add a separate entry for each experiment or repeat trial.',
    'To correct a saved entry, select it and click <b>Edit selected observation</b>. Build and check it again, then click <b>Save changes to observation</b>.',
    'When all results are saved, click <b>Download student submission CSV</b>. Submit that file through the course LMS or your instructor\'s chosen method.',
]
INSTRUCTORS = [
    'Download the student CSV files. In Lattice, open a blank project for a new class dataset or open your existing master project.',
    'Go to <b>Prepare data &gt; Combine submission CSVs</b> and upload the files together. Check <b>Include the whole current project dataset</b> only when appending.',
    'Review validation errors and conflicting submissions. Use <b>Submission coverage</b> to check the experiment counts for each section and lab group.',
    'Click <b>Open combined class results as a new project</b> to view the results, or <b>Download combined class CSV</b> to save the master file.',
]


# Choose fonts for the printable guides, using standard alternatives when needed.
def fonts():
    directory = Path("C:/Windows/Fonts")
    files = [("Body", "calibri.ttf"), ("BodyBold", "calibrib.ttf"),
             ("BodyItalic", "calibrii.ttf"), ("Title", "georgia.ttf")]
    if all((directory / filename).exists() for _, filename in files):
        for name, filename in files:
            pdfmetrics.registerFont(TTFont(name, str(directory / filename)))
        pdfmetrics.registerFontFamily("Body", normal="Body", bold="BodyBold",
                                     italic="BodyItalic", boldItalic="BodyBold")
        return "Body", "BodyBold", "Title"
    return "Helvetica", "Helvetica-Bold", "Times-Roman"


# Build one formatted PDF instruction sheet for the selected audience.
def make(audience, subtitle, color, steps, notes, footer):
    regular, bold, title = fonts()
    ink, gray = HexColor("#2B3033"), HexColor("#646B70")
    body = ParagraphStyle("body", fontName=regular, fontSize=12.2, leading=17, textColor=ink)
    small = ParagraphStyle("small", fontName=regular, fontSize=10.5, leading=14.5, textColor=gray)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"Lattice_{audience}_Results_Guide.pdf"
    page = canvas.Canvas(str(path), pagesize=(612, 792))
    page.setTitle(f"Lattice | Lab results for {audience}")
    page.setAuthor("Lattice - General Chemistry II")

    # Place and wrap a paragraph on the PDF page, then return the next writing position.
    def text(value, x, top, width, style=body):
        paragraph = Paragraph(value, style)
        _, height = paragraph.wrap(width, 700)
        paragraph.drawOn(page, x, top - height)
        return top - height

    page.setFillColor(HexColor("#37566E")); page.setFont(bold, 11)
    page.drawString(54, 748, "Lattice")
    page.setFillColor(gray); page.setFont(regular, 10)
    page.drawRightString(558, 748, "General Chemistry II")
    page.setFillColor(ink); page.setFont(title, 29); page.drawString(54, 707, "Lab results")
    page.setFont(regular, 12); page.setFillColor(gray); page.drawString(55, 684, subtitle)
    page.setStrokeColor(HexColor("#D7DCDE")); page.setLineWidth(.5); page.line(54, 668, 558, 668)
    page.setFillColor(HexColor(color)); page.setFont(bold, 15); page.drawString(54, 637, "For " + audience)
    y = 611
    for number, value in enumerate(steps, 1):
        page.setFillColor(gray); page.setFont(regular, 12); page.drawString(55, y - 12, str(number) + ".")
        y = text(value, 78, y, 480) - 17
    y -= 3
    page.line(54, y, 558, y)
    y -= 19
    for note in notes:
        y = text(note, 54, y, 504, small) - 10
    if y <= 90:
        raise ValueError(f"Content overlaps footer: {audience}")
    page.line(54, 63, 558, 63)
    text(footer, 54, 50, 504, small)
    page.save()
    print(path)


# Generate the separate Student and Instructor PDF instruction guides.
def main():
    make("Students", "Recording and submitting your experiments", "#376558", STUDENTS,
         ["Submit actual observations, not sample data or predictions. Keep experiment IDs unchanged and use group codes instead of student names or emails."],
         "Continuing later? Save <b>Portable project - JSON</b> from Share findings as an editable backup.")
    make("Instructors", "Collecting submissions and building the class dataset", "#37566E", INSTRUCTORS,
         ["Unchanged resubmissions count once; separate trials are preserved. Conflicting versions of the same experiment must be resolved before combining.",
          "Compare Submission coverage with your class roster to identify missing submissions. Lattice does not know which lab groups are expected.",
          "This combines results within Lattice. It does not automatically update an external database."],
         "Keep a backup: save the combined class CSV and <b>Portable project - JSON</b> from Share findings.")


if __name__ == "__main__":
    main()
