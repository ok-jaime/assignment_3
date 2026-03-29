# Universal Analytics Dashboard

Streamlit app for uploading CSV or Excel files, inferring a dashboard mapping, filtering and lightly cleaning the data, visualizing two charts, and generating cached AI chart insights.

## Final Files

- `app.py`: final deployable dashboard
- `requirements.txt`: Python dependencies
- `README.md`: setup, deployment notes, and learning journal
- `project_instructions.md`: assignment prompt

## Features

- Upload `csv`, `xlsx`, `xls`, or `xlsm`
- AI-first dataset mapping with rule-based fallback
- Editable mapping for datetime, grouping, category, and metrics
- Sidebar filters based on the chosen chart fields
- Lightweight data prep:
  - drop null rows by selected columns
  - drop zero rows by selected numeric columns
  - impute missing values using mode, mean, median, zero-fill, or forward-fill
- KPI summary row
- Time-series chart with configurable:
  - time grain
  - chart style
  - aggregation method
- Bar chart with configurable top-category limit
- Quick insights panel
- AI chart analysis with caching and reusable history

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add your API key locally in `.env`:

```bash
OPENAI_API_KEY=your_key_here
```

4. Run the app:

```bash
streamlit run app.py
```

## Deployment

Deploy `app.py` as the entrypoint.

Do not commit `.env` or `.streamlit/secrets.toml`.

For deployment, set `OPENAI_API_KEY` in the host platform's secret manager.

Examples:

- Streamlit Community Cloud: add `OPENAI_API_KEY` in app `Secrets`
- Render / Railway / Hugging Face Spaces: add `OPENAI_API_KEY` as an environment variable

The app checks for `OPENAI_API_KEY` in this order:

1. Streamlit secrets
2. Environment variables loaded from `.env`

If your current key has ever been committed, shared, or exposed publicly, rotate it before deploying.

## Learning Journal

### GAI Tools Used

- ChatGPT / Codex for implementation planning, debugging, refactoring, and UI iteration
- OpenAI API for:
  - automatic dataset-role mapping
  - chart explanation and insight generation

### Prompts Used

- Mapping prompt:
  - asked the model to assign `time_dimension`, `category_dimension`, `group_dimension`, `primary_metric`, and `secondary_metric`
  - provided a compact schema summary plus only `head(10)` and `tail(10)` rows to reduce token use
- Chart insight prompt:
  - asked the model to explain the chart, summarize key insights, and recommend what the user should do first

### Lessons Learned

- A hybrid design works better than pure AI: deterministic profiling and transformations should happen in code, while AI should only assist with ambiguous semantic tasks.
- Caching matters for user experience and cost control. Dataset mapping and chart analyses should not call the API repeatedly for the same state.
- Building experimental sandboxes before merging into the main app reduced regressions and made it easier to validate chart and interaction changes.
