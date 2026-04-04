"""
Generate a sample T&E policy PDF using reportlab.
Run with: python create_sample_policy.py
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT

OUTPUT = "expense_policy.pdf"


def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
    )
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontSize=20,
        textColor=colors.HexColor("#1a237e"),
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#555555"),
        spaceAfter=20,
        alignment=TA_CENTER,
    )
    h1_style = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=14,
        textColor=colors.HexColor("#1a237e"),
        spaceAfter=6,
        spaceBefore=14,
    )
    h2_style = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.HexColor("#283593"),
        spaceAfter=4,
        spaceBefore=10,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        leading=15,
        spaceAfter=6,
    )
    note_style = ParagraphStyle(
        "Note",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#b71c1c"),
        leading=13,
        spaceAfter=6,
    )

    # ── Title ──────────────────────────────────────────────────────────────────
    story.append(Paragraph("Acme Corp Travel & Expense Policy", title_style))
    story.append(Paragraph("Effective January 1, 2025 | Version 3.2", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 12))

    # ── Section 1 ─────────────────────────────────────────────────────────────
    story.append(Paragraph("1. Purpose and Scope", h1_style))
    story.append(Paragraph(
        "This Travel and Expense (T&amp;E) Policy establishes guidelines for all employees "
        "submitting reimbursement requests for business-related expenses. All claims must be "
        "submitted within 30 days of the expense date. Receipts are required for any single "
        "expense exceeding $25. Non-compliant claims will be rejected without exception.",
        body_style,
    ))

    # ── Section 2: Meal Limits ─────────────────────────────────────────────────
    story.append(Paragraph("2. Meal and Dining Limits (Per Person, Per Meal)", h1_style))
    story.append(Paragraph(
        "Meal expenses must reflect a genuine business purpose. Entertainment meals "
        "require prior written approval from a Vice President. Alcohol is not reimbursable "
        "under any circumstances. Minimum 2 business participants required for team meals.",
        body_style,
    ))

    meal_data = [
        ["City / Region", "Breakfast", "Lunch", "Dinner", "Daily Max"],
        ["New York City (NYC)", "$20", "$35", "$65", "$120"],
        ["San Francisco (SFO)", "$20", "$35", "$65", "$120"],
        ["Chicago", "$15", "$28", "$55", "$98"],
        ["Los Angeles", "$18", "$30", "$60", "$108"],
        ["Boston", "$18", "$30", "$58", "$106"],
        ["Seattle", "$18", "$30", "$58", "$106"],
        ["Austin / Dallas / Houston", "$12", "$22", "$45", "$79"],
        ["Miami / Orlando", "$14", "$25", "$50", "$89"],
        ["Other US Cities", "$12", "$20", "$40", "$72"],
        ["International (Europe)", "$25", "$40", "$80", "$145"],
        ["International (Asia-Pacific)", "$20", "$35", "$70", "$125"],
    ]
    meal_table = Table(meal_data, colWidths=[2.1 * inch, 1 * inch, 1 * inch, 1 * inch, 1 * inch])
    meal_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meal_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "⚠ Note: Tips are reimbursable up to 20% of the pre-tax meal total. "
        "Expenses at bars, nightclubs, or primarily alcohol-serving establishments "
        "are strictly prohibited and will be rejected.",
        note_style,
    ))

    # ── Section 3: Transportation ──────────────────────────────────────────────
    story.append(Paragraph("3. Transportation", h1_style))

    story.append(Paragraph("3.1 Air Travel", h2_style))
    story.append(Paragraph(
        "Economy class is required for all flights under 6 hours. "
        "Business class is permitted for flights over 6 hours with VP approval. "
        "All flights must be booked through the corporate travel portal (Concur). "
        "Personal frequent flyer upgrades are permitted but the company reimburses economy fare only. "
        "Flights must be booked at least 14 days in advance when possible.",
        body_style,
    ))

    story.append(Paragraph("3.2 Ground Transportation", h2_style))
    rideshare_data = [
        ["City", "Airport Transfer Limit", "In-City Per Ride Limit"],
        ["NYC, SF, Boston", "$60", "$35"],
        ["Chicago, LA, Seattle", "$55", "$30"],
        ["Other US Cities", "$45", "$25"],
        ["International Cities", "$80", "$45"],
    ]
    rs_table = Table(rideshare_data, colWidths=[2.5 * inch, 2 * inch, 2 * inch])
    rs_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(rs_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Mileage reimbursement for personal vehicles: $0.67/mile (IRS standard rate 2025). "
        "Parking at client sites is reimbursable with receipt. Airport parking maximum: "
        "$35/day at domestic airports, $50/day at international.",
        body_style,
    ))

    # ── Section 4: Lodging ────────────────────────────────────────────────────
    story.append(Paragraph("4. Hotel and Lodging", h1_style))
    lodging_data = [
        ["City", "Standard Nightly Rate Limit", "Notes"],
        ["New York City", "$325/night", "Tax reimbursable"],
        ["San Francisco", "$300/night", "Tax reimbursable"],
        ["Chicago", "$240/night", "Tax reimbursable"],
        ["Los Angeles", "$265/night", "Tax reimbursable"],
        ["Boston", "$255/night", "Tax reimbursable"],
        ["Seattle", "$245/night", "Tax reimbursable"],
        ["Austin / Dallas", "$195/night", "Tax reimbursable"],
        ["Other US Cities", "$180/night", "Tax reimbursable"],
        ["London / Paris", "$350/night", "Tax reimbursable"],
        ["Other International", "$280/night", "Tax reimbursable"],
    ]
    l_table = Table(lodging_data, colWidths=[2.2 * inch, 2 * inch, 2.4 * inch])
    l_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(l_table)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Room service, minibar, gym fees, and in-room movies are not reimbursable. "
        "Hotel upgrades beyond the standard rate are not covered. "
        "Extended stays beyond the approved trip dates must be pre-approved.",
        body_style,
    ))

    # ── Section 5: Entertainment ───────────────────────────────────────────────
    story.append(Paragraph("5. Client Entertainment", h1_style))
    story.append(Paragraph(
        "Client entertainment expenses require prior approval from a Director or above. "
        "Maximum per-person limit for client entertainment dinners: $150/person. "
        "Maximum for sporting events or shows: $200/person per event. "
        "All entertainment must have a documented business purpose listing all attendees "
        "and their company affiliations. Entertainment on weekends requires VP pre-approval.",
        body_style,
    ))

    # ── Section 6: Software and Office ────────────────────────────────────────
    story.append(Paragraph("6. Software, Subscriptions and Office Supplies", h1_style))
    story.append(Paragraph(
        "Individual software subscriptions under $50/month may be expensed with manager approval. "
        "Subscriptions $50-$200/month require Director approval. "
        "Annual software contracts exceeding $500 must go through Procurement. "
        "Office supplies under $75 per purchase may be expensed with receipt. "
        "Office furniture and ergonomic equipment (chairs, monitors) require HR approval "
        "and are subject to a $400 annual limit per employee.",
        body_style,
    ))

    # ── Section 7: Prohibited ─────────────────────────────────────────────────
    story.append(Paragraph("7. Non-Reimbursable and Prohibited Expenses", h1_style))
    prohibited = [
        "Alcoholic beverages of any kind",
        "Personal grooming, spa, or salon services",
        "Gifts for employees (use the dedicated Gift program)",
        "Traffic violations, parking tickets, or fines",
        "Personal entertainment (movies, streaming, gaming)",
        "First-class airfare without explicit CFO approval",
        "Expenses for spouses, partners, or family members",
        "Political donations or contributions",
        "Tobacco or vaping products",
        "Pet boarding or care",
        "Personal vacation expenses bundled with business travel",
        "Purchases from cannabis retailers",
    ]
    for item in prohibited:
        story.append(Paragraph(f"• {item}", note_style))

    # ── Section 8: Weekend Policy ──────────────────────────────────────────────
    story.append(Paragraph("8. Weekend and Holiday Expenses", h1_style))
    story.append(Paragraph(
        "Expenses incurred on Saturday, Sunday, or public holidays are subject to enhanced review. "
        "All weekend expenses require a written business justification explaining why "
        "the expense could not occur on a business day. "
        "Weekend meal expenses are limited to 75% of the standard city limit. "
        "Weekend hotel stays must be approved in advance and only covered if cheaper "
        "than Saturday night flight cost.",
        body_style,
    ))

    # ── Section 9: Submission ─────────────────────────────────────────────────
    story.append(Paragraph("9. Submission and Approval Thresholds", h1_style))
    threshold_data = [
        ["Expense Amount", "Required Approver"],
        ["Under $100", "Direct Manager (auto-approved if policy-compliant)"],
        ["$100 – $500", "Direct Manager"],
        ["$500 – $2,000", "Director"],
        ["$2,000 – $10,000", "VP of Finance"],
        ["Over $10,000", "CFO approval required"],
    ]
    t_table = Table(threshold_data, colWidths=[2.5 * inch, 4.1 * inch])
    t_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f5f5f5"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t_table)

    # ── Footer note ───────────────────────────────────────────────────────────
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "For questions contact finance-help@acmecorp.com | "
        "This policy supersedes all previous T&amp;E guidelines. | "
        "Violations may result in disciplinary action.",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=8,
                       textColor=colors.HexColor("#888888"), alignment=TA_CENTER),
    ))

    doc.build(story)
    print(f"✅ Policy PDF created: {OUTPUT}")


if __name__ == "__main__":
    build_pdf()
