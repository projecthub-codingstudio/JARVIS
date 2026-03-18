# tfctl - TaskFlow CLI Tool

A command-line interface for managing TaskFlow projects from your terminal.

## Installation

```bash
pip install tfctl
```

Requires Python 3.11 or later. Tested on macOS and Linux.

## Authentication

Set your API key as an environment variable:

```bash
export TASKFLOW_API_KEY="your-api-key-here"
export TASKFLOW_URL="https://taskflow.example.com"
```

## Usage

### List tasks in the current sprint

```bash
tfctl tasks list --sprint current --status in_progress
```

### Create a new task

```bash
tfctl tasks create --title "Fix login bug" --priority high --assignee @john
```

### View sprint velocity

```bash
tfctl sprint velocity --id SP-42
```

### Export tasks to CSV

```bash
tfctl tasks export --format csv --output tasks.csv
```

## Configuration

tfctl reads configuration from `~/.config/tfctl/config.toml`. You can override
any setting with environment variables prefixed with `TFCTL_`.

## Contributing

Please read CONTRIBUTING.md before submitting pull requests. All code changes
require unit tests and must pass the CI pipeline.

## License

MIT License. See LICENSE for details.
