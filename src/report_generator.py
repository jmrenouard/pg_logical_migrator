import os
import datetime
from jinja2 import Template

class ReportGenerator:
    def __init__(self, project_name="PostgreSQL Logical Migration"):
        self.project_name = project_name
        self.steps = []
        self.start_time = datetime.datetime.now()

    def add_step(self, step_id, name, status, message, details=None, commands=None, outputs=None):
        self.steps.append({
            "id": step_id,
            "name": name,
            "status": status,
            "message": message,
            "details": details,
            "commands": commands or [],
            "outputs": outputs or [],
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    def generate_html(self, output_path="migration_report_last.html"):
        template_str = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ project_name }} - Execution Audit</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #2563eb;
            --primary-dark: #1e40af;
            --success: #10b981;
            --error: #ef4444;
            --warning: #f59e0b;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
        }
        body { 
            font-family: 'Outfit', sans-serif; 
            background: var(--bg); 
            margin: 0; 
            padding: 40px 20px; 
            color: var(--text); 
            line-height: 1.6;
        }
        .container { 
            max-width: 1100px; 
            margin: auto; 
        }
        .header {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 40px;
            border-radius: 20px;
            box-shadow: 0 10px 25px -5px rgba(37, 99, 235, 0.2);
            margin-bottom: 30px;
            position: relative;
            overflow: hidden;
        }
        .header h1 { margin: 0; font-size: 2.5em; font-weight: 700; letter-spacing: -1px; }
        .header p { margin: 10px 0 0; opacity: 0.9; font-size: 1.1em; }
        
        .card { 
            background: var(--card-bg); 
            padding: 30px; 
            border-radius: 20px; 
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            margin-bottom: 30px;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .summary-item {
            padding: 15px;
            background: #f1f5f9;
            border-radius: 12px;
            text-align: center;
        }
        .summary-item span { display: block; font-size: 0.85em; color: #64748b; text-transform: uppercase; font-weight: 600; }
        .summary-item strong { display: block; font-size: 1.25em; margin-top: 5px; }

        table { width: 100%; border-collapse: separate; border-spacing: 0 10px; margin-top: 20px; }
        th { text-align: left; padding: 15px 20px; color: #64748b; font-weight: 600; text-transform: uppercase; font-size: 0.8em; }
        td { 
            background: white; 
            padding: 20px; 
            border-top: 1px solid #f1f5f9;
            border-bottom: 1px solid #f1f5f9;
        }
        td:first-child { border-left: 1px solid #f1f5f9; border-radius: 12px 0 0 12px; }
        td:last-child { border-right: 1px solid #f1f5f9; border-radius: 0 12px 12px 0; }
        
        .badge {
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 0.75em;
            font-weight: 700;
            text-transform: uppercase;
        }
        .badge-ok { background: #dcfce7; color: #166534; }
        .badge-fail { background: #fee2e2; color: #991b1b; }
        .badge-warn { background: #fef3c7; color: #92400e; }

        pre { 
            background: #0f172a; 
            color: #e2e8f0; 
            padding: 15px; 
            border-radius: 12px; 
            font-size: 0.85em; 
            overflow-x: auto;
            margin-top: 10px;
            border-left: 4px solid var(--primary);
        }
        .log-section { margin-top: 15px; border-top: 1px dashed #e2e8f0; padding-top: 10px; }
        .log-header { font-size: 0.8em; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 5px; }
        .command-block { background: #1e293b; color: #38bdf8; border-left: 4px solid #38bdf8; }
        .output-block { background: #0f172a; color: #94a3b8; border-left: 4px solid #64748b; }
        .footer { text-align: center; margin-top: 50px; color: #64748b; font-size: 0.9em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ project_name }}</h1>
            <p>Migration Execution Audit Report</p>
        </div>

        <div class="card">
            <div class="summary-grid">
                <div class="summary-item">
                    <span>Started</span>
                    <strong>{{ start_time }}</strong>
                </div>
                <div class="summary-item">
                    <span>Total Steps</span>
                    <strong>{{ steps|length }}</strong>
                </div>
                <div class="summary-item">
                    <span>Final Status</span>
                    <strong><span class="badge badge-ok">SUCCESS</span></strong>
                </div>
            </div>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th style="width: 80px;">Step</th>
                    <th>Task Description</th>
                    <th style="width: 120px;">Status</th>
                    <th style="width: 180px;">Timestamp</th>
                </tr>
            </thead>
            <tbody>
                {% for step in steps %}
                <tr>
                    <td style="font-weight: 700; color: var(--primary);">#{{ step.id }}</td>
                    <td>
                        <div style="font-weight: 600; font-size: 1.1em;">{{ step.name }}</div>
                        <div style="color: #64748b; font-size: 0.95em;">{{ step.message }}</div>
                        {% if step.details %}
                        <pre>{{ step.details }}</pre>
                        {% endif %}
                        
                        {% if step.commands or step.outputs %}
                        <div class="log-section">
                            <div class="log-header">Execution Logs</div>
                            {% for i in range(step.commands|length if step.commands|length > step.outputs|length else step.outputs|length) %}
                                {% if i < step.commands|length %}
                                <div class="log-header" style="font-size: 0.7em; margin-top: 8px;">Command:</div>
                                <pre class="command-block">{{ step.commands[i] }}</pre>
                                {% endif %}
                                
                                {% if i < step.outputs|length %}
                                <div class="log-header" style="font-size: 0.7em; margin-top: 4px;">Result:</div>
                                <pre class="output-block">{{ step.outputs[i] }}</pre>
                                {% endif %}
                            {% endfor %}
                        </div>
                        {% endif %}
                    </td>
                    <td>
                        <span class="badge badge-{{ 'ok' if step.status == 'OK' else 'fail' if step.status == 'FAIL' else 'warn' }}">
                            {{ step.status }}
                        </span>
                    </td>
                    <td style="color: #64748b; font-size: 0.9em;">{{ step.timestamp }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="footer">
            &copy; 2026 PostgreSQL Logical Migrator - Automated Audit System
        </div>
    </div>
</body>
</html>
"""
        template = Template(template_str)
        html_content = template.render(
            project_name=self.project_name,
            start_time=self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            steps=self.steps
        )
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w") as f:
            f.write(html_content)
        return output_path
