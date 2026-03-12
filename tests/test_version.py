from cited_cli import __version__


def test_version_command(runner, cli_app):
    result = runner.invoke(cli_app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_version_json(runner, cli_app):
    result = runner.invoke(cli_app, ["--json", "version"])
    assert result.exit_code == 0
    import json

    data = json.loads(result.output)
    assert data["version"] == __version__
    assert data["name"] == "cited-cli"
