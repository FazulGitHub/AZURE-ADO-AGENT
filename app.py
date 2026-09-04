"""
app.py
------
Flask web application:

  1. User pastes a feature / ADO requirement into a form.
  2. The requirement is sent to Groq (see generator.py) which returns a
     structured JSON backlog: user stories, tasks, acceptance criteria and
     test scenarios.
  3. The result is rendered on the page and can be downloaded as
     Markdown, JSON, or CSV (ADO-import friendly).

Run with:
    export GROQ_API_KEY=gsk-...
    python app.py
Then open http://127.0.0.1:5000
"""

import csv
import io
import json
import os

from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from dotenv import load_dotenv

from generator import generate_artifacts, to_markdown, to_csv_rows, DEFAULT_MODEL

load_dotenv()  # loads GROQ_API_KEY / GROQ_MODEL from a local .env file if present

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# Very small in-memory store so the "download" routes can re-use the last
# generated result without re-calling the API. Fine for a single-user local
# tool; swap for a DB/session store if you need multi-user support.
_LAST_RESULT = {"result": None}


@app.route("/", methods=["GET", "POST"])
def index():
    artifacts_md = None
    error = None
    requirement_value = ""
    context_value = ""

    if request.method == "POST":
        requirement_value = request.form.get("requirement", "").strip()
        context_value = request.form.get("context", "").strip()
        model = request.form.get("model", DEFAULT_MODEL).strip() or DEFAULT_MODEL

        if not requirement_value:
            error = "Please enter a feature / requirement description."
        else:
            try:
                result = generate_artifacts(
                    requirement=requirement_value,
                    extra_context=context_value,
                    model=model,
                )
                if result.error:
                    error = result.error
                else:
                    _LAST_RESULT["result"] = result
                    artifacts_md = to_markdown(result)
            except RuntimeError as exc:
                # Missing API key etc.
                error = str(exc)
            except Exception as exc:  # noqa: BLE001 - surface any API error to the UI
                error = f"Generation failed: {exc}"

    return render_template(
        "index.html",
        artifacts_md=artifacts_md,
        error=error,
        requirement_value=requirement_value,
        context_value=context_value,
        default_model=DEFAULT_MODEL,
        has_result=_LAST_RESULT["result"] is not None,
    )


@app.route("/download/<fmt>")
def download(fmt: str):
    result = _LAST_RESULT["result"]
    if result is None:
        flash("Generate artifacts first before downloading.")
        return redirect(url_for("index"))

    if fmt == "markdown":
        buf = io.BytesIO(to_markdown(result).encode("utf-8"))
        return send_file(
            buf,
            mimetype="text/markdown",
            as_attachment=True,
            download_name="agile_artifacts.md",
        )

    if fmt == "json":
        buf = io.BytesIO(json.dumps(result.raw_json, indent=2).encode("utf-8"))
        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name="agile_artifacts.json",
        )

    if fmt == "csv":
        rows = to_csv_rows(result)
        output = io.StringIO()
        if rows:
            writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        buf = io.BytesIO(output.getvalue().encode("utf-8"))
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name="agile_artifacts_ado_import.csv",
        )

    flash("Unknown export format requested.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug, host="127.0.0.1", port=int(os.environ.get("PORT", 5000)))
