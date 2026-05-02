import os
from src.report_generator import ReportGenerator


def test_report_generator_add_step():
    rg = ReportGenerator(project_name="Test Project")
    rg.add_step("1", "Connectivity", "OK", "Connected to source and dest",
                commands=["SELECT 1"], outputs=["1"])

    assert len(rg.steps) == 1
    assert rg.steps[0]["id"] == "1"
    assert rg.steps[0]["status"] == "OK"


def test_report_generator_html(tmp_path):
    output_path = tmp_path / "report.html"
    rg = ReportGenerator(project_name="Test Project")
    rg.add_step("1", "Connectivity", "OK", "Connected")

    path = rg.generate_html(str(output_path))

    assert os.path.exists(path)
    with open(path, "r") as f:
        content = f.read()
        assert "Test Project" in content
        assert "Connectivity" in content
        assert "badge-ok" in content
