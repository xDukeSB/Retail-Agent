"""Reports router — generates PDF and CSV business reports."""
import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.analytics import DailyReport, HourlyCount

router = APIRouter()


@router.get("/data")
async def get_report_data(
    timeframe: str = Query("daily", description="daily | weekly | monthly"),
    days_back: int = Query(30),
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return report data as JSON for the dashboard."""
    date_to = date.today()
    if timeframe == "daily":
        date_from = date_to
    elif timeframe == "weekly":
        date_from = date_to - timedelta(days=7)
    elif timeframe == "monthly":
        date_from = date_to - timedelta(days=30)
    else:
        date_from = date_to - timedelta(days=days_back)

    q = select(DailyReport).where(
        DailyReport.date >= date_from,
        DailyReport.date <= date_to,
    ).order_by(DailyReport.date)
    
    if camera_id:
        q = q.where(DailyReport.camera_id == camera_id)

    result = await db.execute(q)
    rows = result.scalars().all()

    visitors = sum(r.unique_visitors for r in rows)
    entries = sum(r.total_entries for r in rows)
    avg_dwell = sum(r.avg_dwell_seconds for r in rows) / len(rows) if rows else 0
    
    # Calculate overall conversion
    total_conversions = sum((r.conversion_rate or 0) * r.unique_visitors for r in rows)
    conversion_rate = (total_conversions / visitors) if visitors > 0 else 0
    
    # Find overall peak hour (hour with max peak_count)
    peak_hour = None
    if rows:
        peak_row = max(rows, key=lambda x: x.peak_count or 0)
        peak_hour = f"{peak_row.peak_hour}:00" if peak_row.peak_hour is not None else "12:00"

    return {
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "store_name": settings.STORE_NAME,
        "visitors": visitors,
        "conversion_rate": conversion_rate,
        "avg_dwell_time": avg_dwell,
        "peak_hour": peak_hour or "12:00",
        "records": [
            {
                "date": r.date.isoformat(),
                "total_entries": r.total_entries,
                "total_exits": r.total_exits,
                "unique_visitors": r.unique_visitors,
                "avg_dwell_seconds": round(r.avg_dwell_seconds, 1),
                "peak_hour": r.peak_hour,
                "peak_count": r.peak_count,
                "conversion_rate": r.conversion_rate,
            }
            for r in rows
        ]
    }


@router.get("/export/csv")
async def export_csv(
    timeframe: str = Query("daily"),
    days_back: int = Query(30),
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Download daily analytics as CSV."""
    date_to = date.today()
    if timeframe == "daily":
        date_from = date_to
    elif timeframe == "weekly":
        date_from = date_to - timedelta(days=7)
    elif timeframe == "monthly":
        date_from = date_to - timedelta(days=30)
    else:
        date_from = date_to - timedelta(days=days_back)

    q = select(DailyReport).where(
        DailyReport.date >= date_from,
        DailyReport.date <= date_to,
    ).order_by(DailyReport.date)
    if camera_id:
        q = q.where(DailyReport.camera_id == camera_id)

    result = await db.execute(q)
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "date", "total_entries", "total_exits", "unique_visitors",
            "avg_dwell_minutes", "peak_hour", "peak_count", "conversion_rate",
        ],
    )
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "date": r.date.isoformat(),
            "total_entries": r.total_entries,
            "total_exits": r.total_exits,
            "unique_visitors": r.unique_visitors,
            "avg_dwell_minutes": round(r.avg_dwell_seconds / 60, 2),
            "peak_hour": r.peak_hour,
            "peak_count": r.peak_count,
            "conversion_rate": r.conversion_rate,
        })

    output.seek(0)
    filename = f"retailai_report_{date_from}_{date_to}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/pdf")
async def export_pdf(
    timeframe: str = Query("daily"),
    days_back: int = Query(30),
    camera_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a PDF business report."""
    date_to = date.today()
    if timeframe == "daily":
        date_from = date_to
    elif timeframe == "weekly":
        date_from = date_to - timedelta(days=7)
    elif timeframe == "monthly":
        date_from = date_to - timedelta(days=30)
    else:
        date_from = date_to - timedelta(days=days_back)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="reportlab not installed")

    q = select(DailyReport).where(
        DailyReport.date >= date_from,
        DailyReport.date <= date_to,
    ).order_by(DailyReport.date)
    if camera_id:
        q = q.where(DailyReport.camera_id == camera_id)

    result = await db.execute(q)
    rows = result.scalars().all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=20, textColor=colors.HexColor("#1e40af"), spaceAfter=6,
    )
    story.append(Paragraph("RetailAI Agent — Business Report", title_style))
    story.append(Paragraph(f"{settings.STORE_NAME}", styles["Normal"]))
    story.append(Paragraph(f"Period: {date_from} to {date_to}", styles["Normal"]))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Spacer(1, 0.5*cm))

    # Summary table
    total_entries = sum(r.total_entries for r in rows)
    total_visitors = sum(r.unique_visitors for r in rows)
    avg_dwell = round(sum(r.avg_dwell_seconds for r in rows) / len(rows) / 60, 1) if rows else 0

    summary_data = [
        ["Metric", "Value"],
        ["Total Entries", str(total_entries)],
        ["Unique Visitors", str(total_visitors)],
        ["Avg Dwell Time", f"{avg_dwell} min"],
        ["Report Days", str(len(rows))],
    ]
    summary_table = Table(summary_data, colWidths=[8*cm, 8*cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f9ff")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.5*cm))

    # Daily breakdown table
    story.append(Paragraph("Daily Breakdown", styles["Heading2"]))
    table_data = [["Date", "Entries", "Exits", "Visitors", "Avg Dwell", "Peak Hour"]]
    for r in rows:
        table_data.append([
            r.date.isoformat(),
            str(r.total_entries),
            str(r.total_exits),
            str(r.unique_visitors),
            f"{round(r.avg_dwell_seconds/60, 1)} min",
            f"{r.peak_hour}:00" if r.peak_hour is not None else "—",
        ])

    daily_table = Table(table_data, colWidths=[3.5*cm]*6)
    daily_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f9ff")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("PADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(daily_table)

    doc.build(story)
    buffer.seek(0)
    filename = f"retailai_report_{date_from}_{date_to}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
