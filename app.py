from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import os
import zipfile

import altair as alt
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from openai import OpenAI


st.set_page_config(page_title="Universal Analytics Dashboard", layout="wide")
load_dotenv()


MODEL_NAME = "gpt-5.4-nano"
BASE_MAX_OUTPUT_TOKENS = 700


@dataclass
class ColumnProfile:
    name: str
    raw_dtype: str
    parsed_as_date: bool
    numeric: bool
    null_pct: float
    unique_count: int
    sample_values: list[str]
    numeric_score: float
    categorical_score: float
    time_score: float
    id_like: bool


@st.cache_resource
def get_openai_client() -> OpenAI:
    api_key = get_openai_api_key()
    if not api_key:
        raise ValueError("OPENAI_API_KEY was not found in Streamlit secrets or the environment.")
    return OpenAI(api_key=api_key)


def get_openai_api_key() -> str | None:
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY")


def load_tabular_file(file) -> pd.DataFrame:
    file_name = getattr(file, "name", "").lower()
    if file_name.endswith(".xlsx") or file_name.endswith(".xlsm"):
        file.seek(0)
        repaired_file = repair_openxml_workbook(file)
        return pd.read_excel(repaired_file, engine="openpyxl")
    if file_name.endswith(".xls"):
        file.seek(0)
        return pd.read_excel(file, engine="xlrd")

    encodings = [None, "utf-8", "ISO-8859-1", "cp1252"]
    last_error = None
    for encoding in encodings:
        try:
            file.seek(0)
            if encoding is None:
                return pd.read_csv(file)
            return pd.read_csv(file, encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise last_error


def repair_openxml_workbook(file) -> BytesIO:
    file.seek(0)
    original_bytes = file.read()

    if not zipfile.is_zipfile(BytesIO(original_bytes)):
        repaired = BytesIO(original_bytes)
        repaired.name = getattr(file, "name", "uploaded.xlsx")
        return repaired

    source_buffer = BytesIO(original_bytes)
    output_buffer = BytesIO()
    with zipfile.ZipFile(source_buffer, "r") as source_zip, zipfile.ZipFile(output_buffer, "w") as output_zip:
        for member in source_zip.infolist():
            content = source_zip.read(member.filename)
            if member.filename.startswith("xl/worksheets/") and member.filename.endswith(".xml"):
                content = content.replace(b"synchVertical", b"syncVertical")
                content = content.replace(b"synchHorizontal", b"syncHorizontal")
            output_zip.writestr(member, content)

    output_buffer.seek(0)
    output_buffer.name = getattr(file, "name", "uploaded.xlsx")
    return output_buffer


def try_parse_dates(series: pd.Series) -> pd.Series | None:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")
    if pd.api.types.is_numeric_dtype(series):
        return None
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed if parsed.notna().mean() >= 0.6 else None


def try_parse_numeric(series: pd.Series) -> pd.Series | None:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    parsed = pd.to_numeric(series, errors="coerce")
    return parsed if parsed.notna().mean() >= 0.75 else None


def profile_dataframe(df: pd.DataFrame) -> list[ColumnProfile]:
    profiles: list[ColumnProfile] = []
    row_count = max(len(df), 1)
    for col in df.columns:
        series = df[col]
        date_candidate = try_parse_dates(series)
        numeric_candidate = try_parse_numeric(series)
        unique_count = int(series.nunique(dropna=True))
        lower_name = col.lower()
        id_like = (
            unique_count / row_count > 0.9
            or lower_name.endswith("id")
            or " id" in lower_name
            or "identifier" in lower_name
        )
        numeric_score = 0.0
        if numeric_candidate is not None and not id_like:
            numeric_score += 1.0
            if numeric_candidate.nunique(dropna=True) > 6:
                numeric_score += 0.5
        categorical_score = 0.0
        if 2 <= unique_count <= min(20, max(5, row_count // 20)):
            categorical_score += 1.0
        if not id_like and not pd.api.types.is_bool_dtype(series):
            categorical_score += 0.25
        time_score = 0.0
        if date_candidate is not None:
            time_score += 1.5
        if any(token in lower_name for token in ["date", "time", "month", "year"]):
            time_score += 0.5
        profiles.append(
            ColumnProfile(
                name=col,
                raw_dtype=str(series.dtype),
                parsed_as_date=date_candidate is not None,
                numeric=numeric_candidate is not None,
                null_pct=float(series.isna().mean()),
                unique_count=unique_count,
                sample_values=[str(value) for value in series.dropna().astype(str).head(3).tolist()],
                numeric_score=numeric_score,
                categorical_score=categorical_score,
                time_score=time_score,
                id_like=id_like,
            )
        )
    return profiles


def build_profile_table(profiles: list[ColumnProfile]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Column": p.name,
                "Dtype": p.raw_dtype,
                "Date?": p.parsed_as_date,
                "Numeric?": p.numeric,
                "Null %": round(p.null_pct * 100, 1),
                "Unique": p.unique_count,
                "ID-like?": p.id_like,
                "Samples": ", ".join(p.sample_values),
            }
            for p in profiles
        ]
    )


def build_dataset_fingerprint(df: pd.DataFrame) -> str:
    payload = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "head": df.head(10).fillna("").astype(str).to_dict(orient="records"),
        "tail": df.tail(10).fillna("").astype(str).to_dict(orient="records"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def build_ai_payload(df: pd.DataFrame, profiles: list[ColumnProfile]) -> str:
    return json.dumps(
        {
            "row_count": len(df),
            "column_count": df.shape[1],
            "profiles": [
                {
                    "name": p.name,
                    "dtype": p.raw_dtype,
                    "date_like": p.parsed_as_date,
                    "numeric": p.numeric,
                    "null_pct": round(p.null_pct * 100, 1),
                    "unique_count": p.unique_count,
                    "id_like": p.id_like,
                    "samples": p.sample_values,
                }
                for p in profiles
            ],
            "head_rows": df.head(10).fillna("").astype(str).to_dict(orient="records"),
            "tail_rows": df.tail(10).fillna("").astype(str).to_dict(orient="records"),
        },
        indent=2,
    )


def extract_response_text(response) -> str:
    direct_text = getattr(response, "output_text", "")
    if direct_text and direct_text.strip():
        return direct_text.strip()
    collected_chunks = []
    for output_item in getattr(response, "output", []) or []:
        for content_item in getattr(output_item, "content", []) or []:
            text_value = getattr(content_item, "text", None)
            if text_value:
                collected_chunks.append(text_value)
    return "\n".join(chunk.strip() for chunk in collected_chunks if chunk and chunk.strip())


def refine_mapping_with_ai(df: pd.DataFrame, profiles: list[ColumnProfile]) -> dict[str, str | None]:
    prompt = f"""
You are helping map an uploaded dataset into a generic analytics dashboard.

Pick the best columns for these roles:
- time_dimension
- category_dimension
- group_dimension
- primary_metric
- secondary_metric

Rules:
- Use null if a role should be left empty.
- Prefer one date-like column for time_dimension.
- If Region, Country, City, or similar columns are present, prioritize them for both category_dimension and group_dimension in that order. If no region-like column exists, prefer the one with fewer unique values.
- Prefer numeric business measures for primary_metric and secondary_metric.
- Avoid ID-like columns unless there is no better choice.
- Return JSON only. No explanation.

Return exactly this shape:
{{
  "time_dimension": "column or null",
  "category_dimension": "column or null",
  "group_dimension": "column or null",
  "primary_metric": "column or null",
  "secondary_metric": "column or null"
}}

Dataset summary:
{build_ai_payload(df, profiles)}
""".strip()

    last_error = None
    for _ in range(2):
        try:
            response = get_openai_client().responses.create(
                model=MODEL_NAME,
                reasoning={"effort": "low"},
                text={"verbosity": "low"},
                max_output_tokens=500,
                input=prompt,
            )
            cleaned = extract_response_text(response).strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                cleaned = cleaned.replace("json\n", "", 1).strip()
            parsed = json.loads(cleaned)
            return {
                "time_dimension": parsed.get("time_dimension"),
                "category_dimension": parsed.get("category_dimension"),
                "group_dimension": parsed.get("group_dimension"),
                "primary_metric": parsed.get("primary_metric"),
                "secondary_metric": parsed.get("secondary_metric"),
            }
        except Exception as exc:
            last_error = exc
    raise ValueError(f"AI mapping failed after one retry: {last_error}")


def sanitize_mapping(mapping: dict[str, str | None], columns: list[str]) -> dict[str, str | None]:
    valid_columns = set(columns)
    return {key: value if value in valid_columns else None for key, value in mapping.items()}


def choose_best_column(profiles: list[ColumnProfile], score_attr: str, exclude: set[str] | None = None) -> str | None:
    exclude = exclude or set()
    ranked = sorted([p for p in profiles if p.name not in exclude], key=lambda p: getattr(p, score_attr), reverse=True)
    best = ranked[0] if ranked and getattr(ranked[0], score_attr) > 0 else None
    return best.name if best else None


def choose_mapping(profiles: list[ColumnProfile]) -> dict[str, str | None]:
    time_dimension = choose_best_column(profiles, "time_score")
    primary_metric = choose_best_column(profiles, "numeric_score")
    secondary_metric = choose_best_column(profiles, "numeric_score", exclude={primary_metric} if primary_metric else set())
    category_dimension = choose_best_column(profiles, "categorical_score", exclude={time_dimension} if time_dimension else set())
    group_dimension = choose_best_column(profiles, "categorical_score", exclude={time_dimension, category_dimension} - {None})
    return {
        "time_dimension": time_dimension,
        "category_dimension": category_dimension,
        "group_dimension": group_dimension,
        "primary_metric": primary_metric,
        "secondary_metric": secondary_metric,
    }


def normalized_frame(df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    frame = df.copy()
    if mapping["time_dimension"]:
        frame["_time"] = pd.to_datetime(frame[mapping["time_dimension"]], errors="coerce")
        frame = frame.dropna(subset=["_time"])
    if mapping["primary_metric"]:
        frame["_metric"] = pd.to_numeric(frame[mapping["primary_metric"]], errors="coerce")
    if mapping["secondary_metric"]:
        frame["_metric_secondary"] = pd.to_numeric(frame[mapping["secondary_metric"]], errors="coerce")
    if mapping["category_dimension"]:
        frame["_category"] = frame[mapping["category_dimension"]].astype(str)
    if mapping["group_dimension"]:
        frame["_group"] = frame[mapping["group_dimension"]].astype(str)
    return frame


def build_time_buckets(frame: pd.DataFrame, time_grain: str) -> pd.DataFrame:
    bucketed = frame.copy()
    if "_time" not in bucketed.columns:
        return bucketed
    if time_grain == "Day":
        bucketed["_time_period"] = bucketed["_time"].dt.floor("D")
        bucketed["_time_label"] = bucketed["_time_period"].dt.strftime("%Y-%m-%d")
    elif time_grain == "Week":
        bucketed["_time_period"] = bucketed["_time"].dt.to_period("W").dt.start_time
        bucketed["_time_label"] = bucketed["_time_period"].dt.strftime("%Y-%m-%d")
    elif time_grain == "Month":
        bucketed["_time_period"] = bucketed["_time"].dt.to_period("M").dt.start_time
        bucketed["_time_label"] = bucketed["_time_period"].dt.strftime("%Y-%m")
    elif time_grain == "Quarter":
        bucketed["_time_period"] = bucketed["_time"].dt.to_period("Q").dt.start_time
        bucketed["_time_label"] = bucketed["_time"].dt.to_period("Q").astype(str).str.replace("Q", "-Q", regex=False)
    else:
        bucketed["_time_period"] = bucketed["_time"].dt.to_period("Y").dt.start_time
        bucketed["_time_label"] = bucketed["_time_period"].dt.strftime("%Y")
    return bucketed


def aggregate_metric(grouped, metric_column: str, aggregation: str) -> pd.DataFrame:
    if aggregation == "Sum":
        return grouped[metric_column].sum().reset_index()
    if aggregation == "Average":
        return grouped[metric_column].mean().reset_index()
    if aggregation == "Median":
        return grouped[metric_column].median().reset_index()
    if aggregation == "Min":
        return grouped[metric_column].min().reset_index()
    if aggregation == "Max":
        return grouped[metric_column].max().reset_index()
    return grouped[metric_column].count().reset_index()


def get_color_scale(values: list[str]):
    fallback_range = ["#2563eb", "#14b8a6", "#f59e0b", "#8b5cf6", "#ef4444", "#06b6d4", "#84cc16", "#f97316"]
    return alt.Scale(domain=values, range=fallback_range[: len(values)])


def build_time_chart_data(frame: pd.DataFrame, group_enabled: bool, time_grain: str, aggregation: str) -> pd.DataFrame:
    bucketed = build_time_buckets(frame, time_grain)
    group_cols = ["_time_label", "_time_period"]
    if group_enabled and "_group" in bucketed.columns:
        group_cols.append("_group")
    grouped = aggregate_metric(bucketed.dropna(subset=["_metric"]).groupby(group_cols), "_metric", aggregation)
    return grouped.sort_values("_time_period")


def build_time_chart(chart_df: pd.DataFrame, metric_label: str, chart_style: str, group_enabled: bool, time_grain: str, aggregation: str):
    if group_enabled and "_group" in chart_df.columns:
        values = sorted(chart_df["_group"].dropna().unique().tolist())
        color = alt.Color("_group:N", title="Group", scale=get_color_scale(values))
    else:
        color = alt.value("#2563eb")
    base = alt.Chart(chart_df).encode(
        x=alt.X("_time_label:N", sort=chart_df["_time_label"].drop_duplicates().tolist(), title=time_grain, axis=alt.Axis(labelAngle=-35)),
        y=alt.Y("_metric:Q", title=f"{aggregation} {metric_label}"),
        color=color,
        tooltip=[alt.Tooltip("_time_label:N", title=time_grain), alt.Tooltip("_metric:Q", title=f"{aggregation} {metric_label}", format=",.2f")]
        + ([alt.Tooltip("_group:N", title="Group")] if group_enabled and "_group" in chart_df.columns else []),
    ).properties(height=360)
    if chart_style == "Line":
        return base.mark_line(point=True)
    if chart_style == "Area":
        return base.mark_area(opacity=0.35)
    return base.mark_bar()


def build_category_chart_data(frame: pd.DataFrame, aggregation: str, top_n: int) -> pd.DataFrame:
    return (
        aggregate_metric(frame.dropna(subset=["_metric", "_category"]).groupby("_category"), "_metric", aggregation)
        .sort_values("_metric", ascending=False)
        .head(top_n)
    )


def build_category_chart(chart_df: pd.DataFrame, metric_label: str, aggregation: str):
    values = chart_df["_category"].dropna().tolist()
    return alt.Chart(chart_df).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
        x=alt.X("_category:N", sort="-y", title="Category", axis=alt.Axis(labelAngle=-35)),
        y=alt.Y("_metric:Q", title=f"{aggregation} {metric_label}"),
        color=alt.Color("_category:N", legend=None, scale=get_color_scale(values)),
        tooltip=[
            alt.Tooltip("_category:N", title="Category"),
            alt.Tooltip("_metric:Q", title=f"{aggregation} {metric_label}", format=",.2f"),
        ],
    ).properties(height=360)


def figure_to_data_url(fig) -> str:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight", dpi=200)
    buffer.seek(0)
    return f"data:image/png;base64,{base64.b64encode(buffer.read()).decode('utf-8')}"


def build_summary_lines(summary_df: pd.DataFrame, label_col: str, metric_name: str) -> str:
    return "\n".join(f"- {row[0]}: {row[1]:,.2f}" for row in summary_df[[label_col, metric_name]].itertuples(index=False))


def analyze_chart_with_gpt(
    image_data_url: str,
    summary_df: pd.DataFrame,
    label_col: str,
    metric_name: str,
    total_value: float,
    aggregation: str,
    chart_name: str,
    grain: str,
    grouping: str,
) -> str:
    prompt = f"""
You are analyzing a generic analytics dashboard chart.

Return clean markdown with:
1. A plain-English explanation of the chart
2. The most important insights
3. A section titled "What the user should do first"

Be concise and specific.

Context:
- Chart: {chart_name}
- Metric: {aggregation} {metric_name}
- Time grain or dimension: {grain}
- Grouping: {grouping}
- Total displayed value: {total_value:,.2f}

Aggregated values:
{build_summary_lines(summary_df, label_col, metric_name)}
""".strip()

    response = get_openai_client().responses.create(
        model=MODEL_NAME,
        reasoning={"effort": "low"},
        text={"verbosity": "low"},
        max_output_tokens=BASE_MAX_OUTPUT_TOKENS,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_data_url},
                ],
            }
        ],
    )
    markdown_text = extract_response_text(response)
    if markdown_text:
        return markdown_text
    raise ValueError("The model returned no displayable text.")


def render_copy_button(markdown_text: str) -> None:
    button_id = f"copy-md-{abs(hash(markdown_text))}"
    text_json = json.dumps(markdown_text)
    components.html(
        f"""
        <div>
            <button id="{button_id}" style="padding: 0.55rem 0.9rem; border-radius: 0.5rem; border: 1px solid #d0d7de; background: white; cursor: pointer;">
                Copy AI chart analysis to clipboard
            </button>
            <span id="{button_id}-status" style="margin-left: 0.75rem; font-family: sans-serif;"></span>
        </div>
        <script>
            const button = document.getElementById({json.dumps(button_id)});
            const status = document.getElementById({json.dumps(button_id + '-status')});
            const markdownText = {text_json};
            button.addEventListener("click", async () => {{
                try {{
                    await navigator.clipboard.writeText(markdownText);
                    status.textContent = "Copied to clipboard.";
                }} catch (error) {{
                    status.textContent = "Copy failed.";
                }}
            }});
        </script>
        """,
        height=50,
    )


def sidebar_pills_filter(label: str, options: list[str]) -> list[str]:
    if not options:
        return []
    return st.sidebar.pills(label, options, default=options, selection_mode="multi")


def build_analysis_cache_key(summary_df: pd.DataFrame, chart_name: str, metric_name: str, grain: str, grouping: str, chart_style: str) -> str:
    raw = json.dumps(
        {
            "chart_name": chart_name,
            "metric": metric_name,
            "grain": grain,
            "grouping": grouping,
            "chart_style": chart_style,
            "summary": summary_df.to_dict(orient="records"),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def save_analysis_result(cache_key: str, title: str, markdown_text: str, source: str) -> None:
    record = {
        "key": cache_key,
        "title": title,
        "label": f"{title} [{cache_key[:6]}]",
        "markdown": markdown_text,
        "source": source,
    }
    st.session_state["chart_analysis_cache"][cache_key] = record
    st.session_state["chart_analysis_history"] = [item for item in st.session_state["chart_analysis_history"] if item["key"] != cache_key]
    st.session_state["chart_analysis_history"].insert(0, record)
    st.session_state["active_chart_analysis_key"] = cache_key


def render_chart_analysis_workspace() -> None:
    st.subheader("AI Chart Analysis & Insights")
    if st.session_state["chart_analysis_error"]:
        st.error(st.session_state["chart_analysis_error"])
    history = st.session_state["chart_analysis_history"]
    if not history:
        st.info("Generate an AI insight from any chart to start building an analysis history.")
        return
    labels = [item["label"] for item in history]
    active_key = st.session_state.get("active_chart_analysis_key", history[0]["key"])
    active_index = next((idx for idx, item in enumerate(history) if item["key"] == active_key), 0)
    selected_label = st.selectbox("Saved analyses", labels, index=active_index)
    selected_record = next(item for item in history if item["label"] == selected_label)
    st.caption(f"Source: `{selected_record['source']}`")
    st.markdown(selected_record["markdown"])
    left, middle, right = st.columns(3)
    with left:
        st.download_button("Download AI chart analysis as markdown", data=selected_record["markdown"], file_name="chart_analysis.md", mime="text/markdown", use_container_width=True)
    with middle:
        render_copy_button(selected_record["markdown"])
    with right:
        if st.button("Clear all analysis history", use_container_width=True):
            st.session_state["chart_analysis_cache"] = {}
            st.session_state["chart_analysis_history"] = []
            st.session_state["active_chart_analysis_key"] = None
            st.rerun()


def generate_or_reuse_analysis(
    chart_name: str,
    summary_df: pd.DataFrame,
    label_col: str,
    figure_builder,
    metric_name: str,
    total_value: float,
    aggregation: str,
    grain: str,
    grouping: str,
    chart_style: str,
) -> None:
    cache_key = build_analysis_cache_key(summary_df, chart_name, metric_name, grain, grouping, chart_style)
    title = f"{chart_name} | {aggregation} {metric_name} | {grain} | {grouping} | {chart_style}"
    if cache_key in st.session_state["chart_analysis_cache"]:
        save_analysis_result(cache_key, title, st.session_state["chart_analysis_cache"][cache_key]["markdown"], "cache")
        st.session_state["chart_analysis_error"] = ""
        return
    fig = figure_builder()
    try:
        markdown_text = analyze_chart_with_gpt(
            image_data_url=figure_to_data_url(fig),
            summary_df=summary_df,
            label_col=label_col,
            metric_name=metric_name,
            total_value=total_value,
            aggregation=aggregation,
            chart_name=chart_name,
            grain=grain,
            grouping=grouping,
        )
    finally:
        plt.close(fig)
    save_analysis_result(cache_key, title, markdown_text, "openai")
    st.session_state["chart_analysis_error"] = ""


def build_time_analysis_figure(chart_df: pd.DataFrame, chart_style: str, group_enabled: bool):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    labels = chart_df["_time_label"].drop_duplicates().tolist()
    if group_enabled and "_group" in chart_df.columns:
        for name, series_df in chart_df.groupby("_group"):
            series_df = series_df.sort_values("_time_period")
            if chart_style == "Area":
                ax.plot(series_df["_time_label"], series_df["_metric"], label=name, linewidth=2)
                ax.fill_between(series_df["_time_label"], series_df["_metric"], alpha=0.2)
            elif chart_style == "Bar":
                ax.plot(series_df["_time_label"], series_df["_metric"], label=name, linewidth=2, marker="o")
            else:
                ax.plot(series_df["_time_label"], series_df["_metric"], label=name, linewidth=2, marker="o")
        ax.legend(title="Group")
    else:
        series_df = chart_df.sort_values("_time_period")
        if chart_style == "Bar":
            ax.bar(series_df["_time_label"], series_df["_metric"], color="#2563eb")
        elif chart_style == "Area":
            ax.plot(series_df["_time_label"], series_df["_metric"], color="#2563eb", linewidth=2)
            ax.fill_between(series_df["_time_label"], series_df["_metric"], color="#2563eb", alpha=0.2)
        else:
            ax.plot(series_df["_time_label"], series_df["_metric"], color="#2563eb", linewidth=2, marker="o")
    ax.tick_params(axis="x", rotation=35)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, ha="right")
    return fig


def build_category_analysis_figure(chart_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.bar(chart_df["_category"], chart_df["_metric"], color="#2563eb")
    ax.tick_params(axis="x", rotation=35)
    return fig


st.session_state.setdefault("chart_analysis_cache", {})
st.session_state.setdefault("chart_analysis_history", [])
st.session_state.setdefault("active_chart_analysis_key", None)
st.session_state.setdefault("chart_analysis_error", "")
st.session_state.setdefault("universal_ai_mapping_cache", {})
st.session_state.setdefault("universal_ai_mapping_error", "")

st.title("Universal Analytics Dashboard")
st.write("Upload a CSV or Excel file, let the app infer a dashboard mapping, and explore charts, transformations, and AI chart insights.")

uploaded = st.file_uploader("Upload a file", type=["csv", "xlsx", "xls", "xlsm"])
if not uploaded:
    st.info("Upload a CSV or Excel file to begin.")
    st.stop()

try:
    raw_df = load_tabular_file(uploaded)
except Exception as exc:
    st.error(f"File load failed: {exc}")
    st.stop()

profiles = profile_dataframe(raw_df)
suggested_mapping = choose_mapping(profiles)
profile_table = build_profile_table(profiles)
dataset_fingerprint = build_dataset_fingerprint(raw_df)
api_key_ready = bool(get_openai_api_key())
cached_ai_mapping = st.session_state["universal_ai_mapping_cache"].get(dataset_fingerprint)

with st.expander("Detected schema profile", expanded=False):
    st.write(f"Rows: **{len(raw_df):,}** | Columns: **{raw_df.shape[1]}**")
    st.dataframe(profile_table, use_container_width=True)

if api_key_ready and not cached_ai_mapping:
    with st.spinner("Generating the default AI mapping..."):
        try:
            refined = sanitize_mapping(refine_mapping_with_ai(raw_df, profiles), raw_df.columns.tolist())
            st.session_state["universal_ai_mapping_cache"][dataset_fingerprint] = refined
            st.session_state["universal_ai_mapping_error"] = ""
            st.rerun()
        except Exception as exc:
            st.session_state["universal_ai_mapping_error"] = f"AI mapping failed: {exc}"

cached_ai_mapping = st.session_state["universal_ai_mapping_cache"].get(dataset_fingerprint)
active_mapping = cached_ai_mapping or suggested_mapping

all_columns = ["None"] + raw_df.columns.tolist()
st.subheader("Suggested Dataset Mapping for Visualization")
if cached_ai_mapping:
    st.caption(f"_mapping generated by_ `{MODEL_NAME}`")
elif not api_key_ready:
    st.caption("No API key detected, so the app is using the built-in rule-based fallback.")
elif st.session_state["universal_ai_mapping_error"]:
    st.caption("AI mapping failed, so the app is using the built-in rule-based fallback.")

control_time, control_group, control_category, control_primary, control_secondary = st.columns(5)
with control_time:
    time_dimension = st.selectbox("Datetime Column", all_columns, index=all_columns.index(active_mapping["time_dimension"]) if active_mapping["time_dimension"] else 0)
with control_group:
    group_dimension = st.selectbox("Time-series Grouping", all_columns, index=all_columns.index(active_mapping["group_dimension"]) if active_mapping["group_dimension"] else 0)
with control_category:
    category_dimension = st.selectbox("Bar Chart Category", all_columns, index=all_columns.index(active_mapping["category_dimension"]) if active_mapping["category_dimension"] else 0)
with control_primary:
    primary_metric = st.selectbox("Primary Metric", all_columns, index=all_columns.index(active_mapping["primary_metric"]) if active_mapping["primary_metric"] else 0)
with control_secondary:
    secondary_metric = st.selectbox("Secondary Metric", all_columns, index=all_columns.index(active_mapping["secondary_metric"]) if active_mapping["secondary_metric"] else 0)

mapping = {
    "time_dimension": None if time_dimension == "None" else time_dimension,
    "category_dimension": None if category_dimension == "None" else category_dimension,
    "group_dimension": None if group_dimension == "None" else group_dimension,
    "primary_metric": None if primary_metric == "None" else primary_metric,
    "secondary_metric": None if secondary_metric == "None" else secondary_metric,
}
if not mapping["primary_metric"]:
    st.warning("A dashboard needs at least one numeric metric. Choose a primary metric to continue.")
    st.stop()

st.sidebar.header("Filters")
filtered_df = raw_df.copy()
filter_mask = pd.Series(True, index=filtered_df.index)

if mapping["time_dimension"]:
    parsed_time = pd.to_datetime(filtered_df[mapping["time_dimension"]], errors="coerce")
    valid_time = parsed_time.dropna()
    if not valid_time.empty:
        min_date = valid_time.min().date()
        max_date = valid_time.max().date()
        start_date, end_date = st.sidebar.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        filter_mask &= parsed_time.dt.date.between(start_date, end_date)

if mapping["group_dimension"]:
    group_options = sorted(filtered_df[mapping["group_dimension"]].dropna().astype(str).unique().tolist())
    selected_groups = sidebar_pills_filter("Time-series filter", group_options)
    if group_options:
        filter_mask &= filtered_df[mapping["group_dimension"]].astype(str).isin(selected_groups)

if mapping["category_dimension"]:
    category_options = sorted(filtered_df[mapping["category_dimension"]].dropna().astype(str).unique().tolist())
    selected_categories = sidebar_pills_filter("Bar chart filter", category_options)
    if category_options:
        filter_mask &= filtered_df[mapping["category_dimension"]].astype(str).isin(selected_categories)

filtered_df = filtered_df.loc[filter_mask].copy()
if filtered_df.empty:
    st.warning("No rows match the current filters.")
    st.stop()

numeric_columns = [col for col in filtered_df.columns if try_parse_numeric(filtered_df[col]) is not None]

with st.expander("Filter or modify data", expanded=False):
    modify_left, modify_middle, modify_right = st.columns(3)
    with modify_left:
        drop_null_columns = st.multiselect("Drop rows with nulls in columns", filtered_df.columns.tolist())
        if drop_null_columns:
            filtered_df = filtered_df.dropna(subset=drop_null_columns)
    with modify_middle:
        drop_zero_columns = st.multiselect("Drop rows with zeros in numeric columns", numeric_columns)
        if drop_zero_columns:
            for col in drop_zero_columns:
                parsed_series = pd.to_numeric(filtered_df[col], errors="coerce")
                filtered_df = filtered_df.loc[parsed_series != 0]
    with modify_right:
        impute_columns = st.multiselect("Impute missing values in columns", filtered_df.columns.tolist())
        impute_method = st.selectbox(
            "Imputation method",
            ["Most frequent", "Median", "Mean", "Zero fill", "Forward fill"],
        )
        if impute_columns:
            for col in impute_columns:
                parsed_numeric = try_parse_numeric(filtered_df[col])
                if impute_method == "Most frequent":
                    mode_series = filtered_df[col].mode(dropna=True)
                    if not mode_series.empty:
                        filtered_df[col] = filtered_df[col].fillna(mode_series.iloc[0])
                elif impute_method == "Median" and parsed_numeric is not None:
                    filtered_df[col] = parsed_numeric.fillna(parsed_numeric.median())
                elif impute_method == "Mean" and parsed_numeric is not None:
                    filtered_df[col] = parsed_numeric.fillna(parsed_numeric.mean())
                elif impute_method == "Zero fill":
                    filtered_df[col] = (parsed_numeric if parsed_numeric is not None else filtered_df[col]).fillna(0)
                elif impute_method == "Forward fill":
                    filtered_df[col] = filtered_df[col].ffill()

    st.caption(
        "Lightweight data prep only: drop null rows, drop zero rows, or impute with mode, median, mean, zero-fill, or forward-fill."
    )

if filtered_df.empty:
    st.warning("No rows remain after data modification.")
    st.stop()

with st.expander("Preview data", expanded=False):
    st.write(f"Rows: **{len(filtered_df):,}** | Columns: **{filtered_df.shape[1]}**")
    st.dataframe(filtered_df.head(20), use_container_width=True)

normalized = normalized_frame(filtered_df, mapping)
metric_options = [mapping["primary_metric"]]
if mapping["secondary_metric"] and mapping["secondary_metric"] != mapping["primary_metric"]:
    metric_options.append(mapping["secondary_metric"])
selected_metric_name = metric_options[0]

normalized_base = normalized.copy()
if mapping["secondary_metric"] and "_metric_secondary" in normalized_base.columns:
    secondary_metric_total = float(normalized_base["_metric_secondary"].dropna().sum())
else:
    secondary_metric_total = None

time_grain = "Month"
metric_aggregation = "Sum"
top_n_categories = 10
chart_style = "Area"
use_group_for_time_chart = group_dimension != "None"

selected_metric_name = metric_options[0]
use_group_for_time_chart = use_group_for_time_chart
normalized = normalized_base.copy()
if selected_metric_name == mapping["secondary_metric"] and "_metric_secondary" in normalized.columns:
    normalized["_metric"] = normalized["_metric_secondary"]

selected_metric_total = float(normalized["_metric"].dropna().sum()) if "_metric" in normalized.columns else 0.0
valid_time = pd.to_datetime(filtered_df[mapping["time_dimension"]], errors="coerce").dropna() if mapping["time_dimension"] else pd.Series(dtype="datetime64[ns]")

summary_left, summary_mid_left, summary_mid_right, summary_right = st.columns(4)
summary_left.metric(f"Total {selected_metric_name}", f"{selected_metric_total:,.2f}")
if mapping["secondary_metric"] and secondary_metric_total is not None:
    summary_mid_left.metric(f"Total {mapping['secondary_metric']}", f"{secondary_metric_total:,.2f}")
else:
    summary_mid_left.metric("Rows", f"{len(filtered_df):,}")
summary_mid_right.metric("Rows", f"{len(filtered_df):,}")
if not valid_time.empty:
    summary_right.metric("Date span", f"{valid_time.min().date()} to {valid_time.max().date()}")
else:
    summary_right.metric("Columns", f"{filtered_df.shape[1]:,}")

insight_col, left, right = st.columns([0.8, 1.35, 1])
with insight_col:
    use_group_for_time_chart = st.checkbox("Group the time-series chart", value=group_dimension != "None")
    selected_metric_name = st.radio("Metric to visualize", metric_options, horizontal=False)
    normalized = normalized_base.copy()
    if selected_metric_name == mapping["secondary_metric"] and "_metric_secondary" in normalized.columns:
        normalized["_metric"] = normalized["_metric_secondary"]

    selected_metric_total = float(normalized["_metric"].dropna().sum()) if "_metric" in normalized.columns else 0.0
    st.subheader("Quick Insights")

    time_chart_df = build_time_chart_data(normalized, use_group_for_time_chart and bool(mapping["group_dimension"]), time_grain, metric_aggregation)
    category_chart_df = build_category_chart_data(normalized, metric_aggregation, top_n_categories)
    quick_insights = []
    if not time_chart_df.empty:
        top_period = time_chart_df.sort_values("_metric", ascending=False).iloc[0]
        quick_insights.append(f"Peak {selected_metric_name.lower()} period: **{top_period['_time_label']}**")
    if not category_chart_df.empty:
        top_category = category_chart_df.iloc[0]
        quick_insights.append(f"Top {mapping['category_dimension'] or 'category'}: **{top_category['_category']}**")
    if mapping["group_dimension"] and use_group_for_time_chart and "_group" in normalized.columns:
        top_group = normalized.dropna(subset=["_metric", "_group"]).groupby("_group")["_metric"].sum().sort_values(ascending=False)
        if not top_group.empty:
            quick_insights.append(f"Top group in time series: **{top_group.index[0]}**")
    quick_insights.append(f"Current {selected_metric_name.lower()} total: **{selected_metric_total:,.2f}**")
    for item in quick_insights:
        st.write("• " + item)

with left:
    st.subheader("Chart 1: Metric Over Time")
    if mapping["time_dimension"]:
        st.caption("Visualization Options")
        time_option_left, time_option_middle, time_option_right = st.columns(3)
        with time_option_left:
            time_grain = st.selectbox("Time grain", ["Day", "Week", "Month", "Quarter", "Year"], index=2)
        with time_option_middle:
            chart_style = st.selectbox("Time-series chart style", ["Line", "Area", "Bar"], index=1)
        with time_option_right:
            metric_aggregation = st.selectbox("Metric aggregation", ["Sum", "Average", "Median", "Min", "Max", "Count"], index=0)
        time_chart_df = build_time_chart_data(normalized, use_group_for_time_chart and bool(mapping["group_dimension"]), time_grain, metric_aggregation)
        st.altair_chart(build_time_chart(time_chart_df, selected_metric_name, chart_style, use_group_for_time_chart and bool(mapping["group_dimension"]), time_grain, metric_aggregation), width="stretch")
        if api_key_ready and st.button("Generate AI Insight for this Chart", key="time_chart_ai", use_container_width=True):
            with st.spinner("Preparing the time-series chart analysis..."):
                try:
                    generate_or_reuse_analysis(
                        chart_name="Time Series",
                        summary_df=time_chart_df[["_time_label", "_metric"]].rename(columns={"_time_label": "Period", "_metric": selected_metric_name}),
                        label_col="Period",
                        figure_builder=lambda: build_time_analysis_figure(time_chart_df, chart_style, use_group_for_time_chart and bool(mapping["group_dimension"])),
                        metric_name=selected_metric_name,
                        total_value=float(time_chart_df["_metric"].sum()),
                        aggregation=metric_aggregation,
                        grain=time_grain,
                        grouping=mapping["group_dimension"] if use_group_for_time_chart and mapping["group_dimension"] else "None",
                        chart_style=chart_style,
                    )
                except Exception as exc:
                    st.session_state["chart_analysis_error"] = f"The chart analysis request failed. Details: {exc}"
                st.rerun()
    else:
        st.info("No time dimension selected.")

with right:
    st.subheader("Chart 2: Metric By Category")
    if mapping["category_dimension"]:
        st.caption("Visualization Options")
        top_n_categories = st.slider("Top categories in bar chart", min_value=3, max_value=25, value=10)
        category_chart_df = build_category_chart_data(normalized, metric_aggregation, top_n_categories)
        st.altair_chart(build_category_chart(category_chart_df, selected_metric_name, metric_aggregation), width="stretch")
        if api_key_ready and st.button("Generate AI Insight for this Chart", key="category_chart_ai", use_container_width=True):
            with st.spinner("Preparing the category chart analysis..."):
                try:
                    generate_or_reuse_analysis(
                        chart_name="Bar Chart Breakdown",
                        summary_df=category_chart_df.rename(columns={"_category": "Category", "_metric": selected_metric_name}),
                        label_col="Category",
                        figure_builder=lambda: build_category_analysis_figure(category_chart_df),
                        metric_name=selected_metric_name,
                        total_value=float(category_chart_df["_metric"].sum()),
                        aggregation=metric_aggregation,
                        grain=mapping["category_dimension"] or "Category",
                        grouping="None",
                        chart_style="Bar",
                    )
                except Exception as exc:
                    st.session_state["chart_analysis_error"] = f"The chart analysis request failed. Details: {exc}"
                st.rerun()
    else:
        st.info("No category dimension selected.")

st.divider()
render_chart_analysis_workspace()

st.divider()
st.download_button(
    "Download modified data as CSV",
    data=normalized.to_csv(index=False).encode("utf-8"),
    file_name="universal_dashboard_data.csv",
    mime="text/csv",
)