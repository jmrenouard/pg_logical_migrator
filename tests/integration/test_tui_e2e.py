import os
import pytest
from src.tui import MigratorApp
from textual.widgets import Label

@pytest.mark.asyncio
async def test_tui_e2e_connectivity():
    """
    Test End-to-End de la TUI contre les vraies bases de données Docker.
    Vérifie que la TUI parvient à charger la config réelle et à tester les connexions.
    """
    config_path = os.path.join(os.path.dirname(__file__), "..", "test_config.ini")
    
    app = MigratorApp(config_path)

    async with app.run_test() as pilot:
        from textual.widgets import Select, Static
        # Laisse l'UI s'initialiser
        await pilot.pause(0.2)

        # Vérifie qu'on est connecté à la bonne DB selon le test_config.ini
        select_widget = app.query_one("#opt_database", Select)
        assert select_widget.value == "test_migration"
        
        # Ouvre la section Step 1 (Check) pour être sûr qu'elle est affichée
        # en appelant la méthode associée (ou en cliquant si l'ID est visible)
        await pilot.click("#step_1")
        
        # Attend que la connexion s'effectue et que l'interface se mette à jour
        await pilot.pause(1.0)
        
        # La sortie du test de connexion doit afficher "OK" pour la source et la destination
        # On va chercher tous les labels et vérifier que le succès est affiché.
        
        # Pour être robuste, on peut inspecter le panneau principal (main_display)
        log_panel = app.query_one("#main_display", Static)
        
        from rich.console import Console
        console = Console()
        with console.capture() as capture:
            console.print(log_panel.render()._renderable)
        log_text = capture.get()
        
        assert "OK" in log_text or "Success" in log_text or "True" in log_text or "Succès" in log_text, f"Le test de connexion E2E a échoué dans la TUI. Sortie: {log_text}"
