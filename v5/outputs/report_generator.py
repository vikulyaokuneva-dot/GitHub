"""Report generator – PDF, Excel, etc."""

from pathlib import Path

from domain import MetricsBundle, FactsBundle, CabinetContext


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
        # TODO: Implement PDF generation
        # 1. Create report with charts and tables
        # 2. Include metrics summary
        # 3. Include facts and recommendations
        # 4. Save to reports_dir
        # 5. Return path
        
        raise NotImplementedError("ReportGenerator.generate_pdf() not yet implemented")
    
    def generate_excel(self, metrics: MetricsBundle, facts: FactsBundle) -> Path:
        """
        Generate Excel report with detailed data.
        
        Args:
            metrics: Calculated metrics
            facts: Facts and recommendations
            
        Returns:
            Path to generated Excel file
        """
        # TODO: Implement Excel generation
        # 1. Create Excel workbook
        # 2. Add sheets: Summary, Ads, SKUs, Facts, Recommendations
        # 3. Format cells, add charts
        # 4. Save to reports_dir
        # 5. Return path
        
        raise NotImplementedError("ReportGenerator.generate_excel() not yet implemented")
