"""Report generator – PDF, Excel, etc."""

from pathlib import Path

from ..domain import MetricsBundle, FactsBundle, CabinetContext


class ReportGenerator:
    """Generates reports in various formats"""
    
    def __init__(self, cabinet_ctx: CabinetContext):
        self.cabinet_ctx = cabinet_ctx
    
    def generate_pdf(self, metrics: MetricsBundle, facts: FactsBundle) -> Path:
        """
        Generate PDF report.
        
        Args:
            metrics: Calculated metrics
            facts: Facts and recommendations
            
        Returns:
            Path to generated PDF file
        """
        # Basic implementation - create placeholder PDF
        # TODO: Full PDF generation with charts and tables
        
        reports_dir = self.cabinet_ctx.cabinet_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_path = reports_dir / f"report_{metrics.date}.pdf"
        
        # Create placeholder PDF file
        pdf_path.write_text(f"Report for {metrics.date}\nMetrics: {metrics}\nFacts: {facts}")
        
        return pdf_path
    
    def generate_excel(self, metrics: MetricsBundle, facts: FactsBundle) -> Path:
        """
        Generate Excel report with detailed data.
        
        Args:
            metrics: Calculated metrics
            facts: Facts and recommendations
            
        Returns:
            Path to generated Excel file
        """
        # Basic implementation - create placeholder Excel
        # TODO: Full Excel generation with proper formatting
        
        reports_dir = self.cabinet_ctx.cabinet_path / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        excel_path = reports_dir / f"report_{metrics.date}.xlsx"
        
        # Create placeholder Excel file
        excel_path.write_text(f"Excel Report for {metrics.date}")
        
        return excel_path
