# Docker Deployment Guide

Using Docker is the **recommended approach** for running **pg_logical_migrator** in production and development. It provides a consistent environment with all dependencies pre-installed and avoids local Python version conflicts.

### 🐳 Quick Pull & Run
The image is available on both **Docker Hub** and **GitHub Container Registry**.

```bash
docker pull jmrenouard/pg_logical_migrator:latest
# OR
docker pull ghcr.io/jmrenouard/pg_logical_migrator:latest
```

### 🚢 Basic Execution
Mount your local `config_migrator.ini` into the container and execute the desired command.

```bash
docker run --rm -it \
  -v $(pwd)/config_migrator.ini:/app/config_migrator.ini \
  -v $(pwd)/RESULTS:/app/RESULTS \
  jmrenouard/pg_logical_migrator:latest \
  python pg_migrator.py init-replication
```

### 🕸️ Networking Best Practices
When using Docker, networking is the most frequent point of failure.

- **Host-to-Container**: If your databases are local, use your machine's IP (e.g., `192.168.1.10`) or `host.docker.internal` (Mac/Windows).
- **Container-to-Container**: If running everything in `docker compose`, use the service names (e.g., `pg_source`, `pg_target`) as hostnames.
- **NAT Loopback**: The `source_host` parameter in the `[replication]` section of your `.ini` file is critical. It must be an address that the **destination** database container can use to reach the **source** database container.

### 📊 Real-World Docker Compose Example
A typical developer environment would look like this:

```yaml
services:
  pg_source:
    image: postgres:15
    container_name: pg_source
    command: ["postgres", "-c", "wal_level=logical", "-c", "max_replication_slots=10"]
    ports: ["5432:5432"]

  pg_target:
    image: postgres:16
    container_name: pg_target
    command: ["postgres", "-c", "wal_level=logical", "-c", "max_replication_slots=10"]
    ports: ["5433:5432"]

  migrator:
    image: jmrenouard/pg_logical_migrator:latest
    volumes:
      - ./config_migrator.ini:/app/config_migrator.ini
    depends_on:
      - pg_source
      - pg_target
```

### 💡 Advanced Usage
You can run the full-screen Terminal UI (TUI) through Docker by providing a pseudo-TTY (`-it` flags):

```bash
docker run --rm -it \
  -v $(pwd)/config_migrator.ini:/app/config_migrator.ini \
  jmrenouard/pg_logical_migrator:latest \
  python pg_migrator.py tui
```
