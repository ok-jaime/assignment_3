Interactive Sales Dashboard (use Streamlit and Python)

Goal
Build a Streamlit app that lets a user explore a sales dataset through filters + summary metrics + charts + GAI  Insights

Example Solution: https://superstoresdashboard.streamlit.app/

Dataset
Use the Superstore.csv dataset (CSV file)

Required Features

1) Load + preview data
Prompt user to upload a CSV using st.file_uploader
Have an expandle box/cell to show:
st.dataframe(df.head())
Basic info: number of rows, number of columns

2) Data cleaning / prep (lightweight)
Do at least two of these:
Parse Order Date to datetime
Handle missing values (drop or fill)
Convert numeric columns to numeric (coerce errors)
Create a new column: Month (e.g., df['Order Date'].dt.to_period('M'))

3) Sidebar filters
Add at least three filters in the sidebar (depending on dataset):
Date range filter (start/end)
Region filter (multi-select)
Category filter (multi-select)
Profit > 0 checkbox (optional)

4) KPI metrics row
Show 3–4 KPIs using st.metric, for the filtered data:
Total Sales
Total Profit
Profit Margin (%)
Number of Orders (or rows)

5) Charts (at least 2)
Use Streamlit charts or matplotlib:
Line chart: Sales over time (by month)
Bar chart: Sales (or Profit) by Category or Region
Allow the user to switch between viewing Sales vs Profit
Add a downloadable filtered CSV (st.download_button)
Optional: Scatter plot of Sales vs Profit
Optional: Add a small “anomaly alert”: months with profit margin below 0

6) Simple insight text
Under the charts, add 2–4 bullet points that your code generates, e.g.:
“Top region by sales: West”
“Highest-profit category: Technology”
“Profit margin this period: 12.4%”

7) AI Features
Add a button right below the Line chart: metric over time (by Month). When the user clicks the button. The app will upload the Line chart image to GPT 5.4 model with reasoning and ask the model to explain the chart, then provide insights, and finally what the user should do first. The response from the LL Model should be displayed properly in a pop-up dialog box. The dialog box should have a button allows the user to copy and download the response in markdown format.

Deliverables
app.py
requirements.txt (at least streamlit, pandas, and one plotting lib if used)
README.md as the learning journal:
Document how you use the GAI tools and prompts used 
Reflection of lessons learned