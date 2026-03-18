import pytest
from typer.testing import CliRunner
from unittest.mock import patch, MagicMock
from squeeze.cli import app
from pathlib import Path

runner = CliRunner()

def test_scan_automation_triggers():
    """
    Test that 'squeeze scan' with --export, --plot, and --notify 
    triggers the respective components correctly.
    """
    # Mock data discovery
    with patch("squeeze.cli.do_fetch_tickers") as mock_fetch:
        mock_fetch.return_value = ["2330.TW"]
        
        # Mock scanner to return a dummy result
        with patch("squeeze.cli.MarketScanner") as mock_scanner_cls:
            mock_scanner = MagicMock()
            mock_scanner_cls.return_value = mock_scanner
            
            # Setup scanner to return one match for squeeze
            mock_scanner.scan.return_value = [
                {
                    "ticker": "2330.TW",
                    "is_squeezed": True,
                    "energy_level": 3,
                    "momentum": 0.5,
                    "fired": False
                }
            ]
            
            # Mock exporters and notifiers
            with patch("squeeze.cli.ReportExporter") as mock_exporter_cls, \
                 patch("squeeze.cli.plot_ticker") as mock_plot, \
                 patch("squeeze.cli.LineNotifier") as mock_notifier_cls:
                
                mock_exporter = MagicMock()
                mock_exporter_cls.return_value = mock_exporter
                mock_exporter.export.return_value = {"csv": "path/to/csv"}
                
                mock_notifier = MagicMock()
                mock_notifier_cls.return_value = mock_notifier
                mock_notifier.send_summary.return_value = True
                
                # Run the command
                result = runner.invoke(app, [
                    "scan", 
                    "--limit", "1", 
                    "--export", 
                    "--plot", 
                    "--notify"
                ])
                
                # Check output
                assert result.exit_code == 0
                assert "Scanning for squeeze pattern" in result.stdout
                assert "2330.TW" in result.stdout
                assert "Exporting results" in result.stdout
                assert "Generating charts" in result.stdout
                assert "Sending LINE notification" in result.stdout
                assert "LINE notification sent" in result.stdout
                
                # Verify calls
                mock_exporter.export.assert_called_once()
                mock_plot.assert_called_once()
                mock_notifier.send_summary.assert_called_once()
                
                # Verify summary content
                args, _ = mock_notifier.send_summary.call_args
                summary_msg = args[0]
                assert "Squeeze Scan Complete" in summary_msg
                assert "Found 1 matches" in summary_msg
                assert "2330.TW" in summary_msg

def test_scan_houyi_triggers():
    """
    Test that 'squeeze scan --pattern houyi' correctly triggers logic.
    """
    with patch("squeeze.cli.do_fetch_tickers") as mock_fetch:
        mock_fetch.return_value = ["2330.TW"]
        
        with patch("squeeze.cli.MarketScanner") as mock_scanner_cls:
            mock_scanner = MagicMock()
            mock_scanner_cls.return_value = mock_scanner
            mock_scanner.scan.return_value = [
                {
                    "ticker": "2330.TW",
                    "is_houyi": True,
                    "rally_pct": 0.2,
                    "fib_level": 0.5,
                    "squeeze_on": True,
                    "shooting_star": False
                }
            ]
            
            with patch("squeeze.cli.LineNotifier") as mock_notifier_cls:
                mock_notifier = MagicMock()
                mock_notifier_cls.return_value = mock_notifier
                mock_notifier.send_summary.return_value = True
                
                result = runner.invoke(app, [
                    "scan", 
                    "--pattern", "houyi",
                    "--notify"
                ])
                
                assert result.exit_code == 0
                assert "Scanning for houyi pattern" in result.stdout
                assert "2330.TW" in result.stdout
                assert "LINE notification sent" in result.stdout
                
                # Verify summary content
                args, _ = mock_notifier.send_summary.call_args
                summary_msg = args[0]
                assert "Squeeze Scan Complete: houyi" in summary_msg
                assert "20.0%" in summary_msg
