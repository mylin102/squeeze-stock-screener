import json
import csv
from pathlib import Path
import pytest
from src.squeeze.report.exporter import ReportExporter

@pytest.fixture
def mock_results():
    return [
        {
            "ticker": "AAPL",
            "close": 150.0,
            "momentum": 0.05,
            "energy": 0.8,
            "squeeze_active": True
        },
        {
            "ticker": "MSFT",
            "close": 300.0,
            "momentum": -0.02,
            "energy": 0.4,
            "squeeze_active": False
        },
        {
            "ticker": "GOOGL",
            "close": 2800.0,
            "momentum": 0.01,
            "energy": 0.6,
            "squeeze_active": False
        }
    ]

@pytest.fixture
def exporter():
    return ReportExporter()

def test_export_creates_directory_structure(exporter, mock_results, tmp_path):
    output_dir = tmp_path / "exports"
    paths = exporter.export(mock_results, output_dir)
    
    # Check if the date directory was created
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    expected_dir = output_dir / date_str
    
    assert expected_dir.exists()
    assert expected_dir.is_dir()
    
    # Check if files exist
    assert paths["csv"].exists()
    assert paths["json"].exists()
    assert paths["markdown"].exists()

def test_to_csv(exporter, mock_results, tmp_path):
    csv_path = tmp_path / "test.csv"
    exporter.to_csv(mock_results, csv_path)
    
    assert csv_path.exists()
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
        assert len(rows) == 3
        assert rows[0]["ticker"] == "AAPL"
        assert float(rows[0]["close"]) == 150.0
        assert rows[0]["squeeze_active"] == "True"

def test_to_json(exporter, mock_results, tmp_path):
    json_path = tmp_path / "test.json"
    exporter.to_json(mock_results, json_path)
    
    assert json_path.exists()
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
        assert "metadata" in data
        assert data["metadata"]["count"] == 3
        assert len(data["results"]) == 3
        assert data["results"][0]["ticker"] == "AAPL"

def test_to_markdown(exporter, mock_results, tmp_path):
    md_path = tmp_path / "test.md"
    exporter.to_markdown(mock_results, md_path)
    
    assert md_path.exists()
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
        assert "# Squeeze Stock Screener - Scan Summary" in content
        assert "AAPL" in content
        assert "MSFT" in content
        assert "GOOGL" in content
        assert "Active" in content
        assert "No" in content

def test_export_empty_results(exporter, tmp_path):
    csv_path = tmp_path / "empty.csv"
    exporter.to_csv([], csv_path)
    
    assert csv_path.exists()
    with open(csv_path, 'r', encoding='utf-8') as f:
        assert f.read() == ""
