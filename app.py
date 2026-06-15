import streamlit as st
import pandas as pd
import plotly.express as px
import anthropic
from dotenv import load_dotenv
import os
import io
import json

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def clean_descriptions(descriptions):
    description_list = "\n".join([f"{i+1}. {desc}" for i, desc in enumerate(descriptions)])
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""Extract just the merchant or transaction name from each bank transaction description.
Remove card numbers, dates, transaction type prefixes, and reference codes.
Return ONLY a numbered list with the cleaned merchant names. No explanations.

Examples:
"DEBIT PURCHASE xx-1635 SRI MURUGAN S30/03/26" → "Sri Murugan"
"POS PURCHASE NETS xx-1635 MOHAMED MUSTAFA S" → "Mohamed Mustafa"
"FUND TRANSFER OTHR - util and singtel feb" → "Singtel"
"CASH WITHDRAWAL ATM xx-1635 OCBC-PUNGGOL MRT S" → "ATM Withdrawal"

Transactions:
{description_list}"""
        }]
    )
    cleaned = response.content[0].text.strip().split("\n")
    cleaned = [c.split(". ", 1)[1].strip() for c in cleaned if ". " in c]
    return cleaned

def categorize_transactions(descriptions):
    description_list = "\n".join([f"{i+1}. {desc}" for i, desc in enumerate(descriptions)])
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""Categorize each transaction into one of these categories:
Food & Dining, Transport, Shopping, Bills, Entertainment, Health, Income, Savings, Cash, Groceries, Other.

Note: The following are grocery stores in Singapore and should always be categorized as Groceries:
Mustafa, Sri Murugan, Sheng Siong, Giant, FairPrice, NTUC, Prime, Cold Storage, Kalam Foods.

Return ONLY a numbered list matching the input. No explanations.

Transactions:
{description_list}"""
        }]
    )
    categories = response.content[0].text.strip().split("\n")
    categories = [c.split(". ", 1)[1].strip() for c in categories if ". " in c]
    return categories

def detect_csv_structure(raw_text):
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Analyze this bank statement CSV and return a JSON object with these fields:
- header_row: the row number (0-indexed) where the actual column headers are
- date_col: exact name of the date column
- description_col: exact name of the description column
- amount_col: exact name of a single amount column (null if not present)
- withdrawal_col: exact name of the withdrawal/debit column (null if not present)
- deposit_col: exact name of the deposit/credit column (null if not present)

Return ONLY the JSON, no explanation.

CSV:
{raw_text}"""
        }]
    )
    raw_response = response.content[0].text.strip()
    raw_response = raw_response.replace("```json", "").replace("```", "").strip()
    return json.loads(raw_response)

st.set_page_config(page_title="AI Finance Tracker")
st.title("💰 AI Finance Tracker")
st.markdown("Upload your bank statement and let AI do the rest.")

uploaded_file = st.file_uploader("Upload your bank statement (CSV)", type=["csv"])

if uploaded_file is not None:
    st.success("File uploaded successfully!")

    raw_text = uploaded_file.read().decode("utf-8")
    first_lines = "\n".join(raw_text.splitlines()[:10])

    with st.spinner("🔍 Detecting CSV structure..."):
        structure = detect_csv_structure(first_lines)

    st.write("Detected structure:", structure)  # temporary debug
    st.write("Actual columns:", list(pd.read_csv(io.StringIO(raw_text), skiprows=structure["header_row"]).columns))

    df = pd.read_csv(io.StringIO(raw_text), skiprows=structure["header_row"])

    df = df.rename(columns={
        structure["date_col"]: "Date",
        structure["description_col"]: "Description"
    })

    if structure["amount_col"]:
        df = df.rename(columns={structure["amount_col"]: "Amount"})
    else:
        df["Withdrawals"] = pd.to_numeric(df[structure["withdrawal_col"]].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
        df["Deposits"] = pd.to_numeric(df[structure["deposit_col"]].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
        df["Amount"] = df["Deposits"] - df["Withdrawals"]
        df = df.drop(columns=["Withdrawals", "Deposits"])

    df = df[["Date", "Description", "Amount"]].dropna(subset=["Description"])

    with st.spinner("🤖 Claude is analyzing your transactions..."):
        descriptions = df["Description"].tolist()
        df["Description"] = clean_descriptions(descriptions)
        df["Category"] = categorize_transactions(df["Description"].tolist())

    st.subheader("📄 Raw Data Preview")
    st.dataframe(df.head(20), use_container_width=True)

    income_df = df[df["Amount"] > 0]
    expense_df = df[df["Amount"] < 0]

    total_income = income_df["Amount"].sum()
    total_spending = abs(expense_df["Amount"].sum())
    net_savings = total_income - total_spending

    st.subheader("📊 Summary")
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Income", f"${total_income:,.2f}")
    col2.metric("Total Spending", f"${total_spending:,.2f}")
    col3.metric("Net Savings", f"${net_savings:,.2f}")

    category_summary = expense_df.groupby("Category")["Amount"].sum().abs()
    category_summary = category_summary.sort_values(ascending=False)

    category_df = category_summary.reset_index()
    category_df.columns = ["Category", "Amount"]
    category_df["Amount"] = category_df["Amount"].apply(lambda x: f"${x:,.2f}")

    st.subheader("🗂️ Spending by Category")
    st.dataframe(category_df, use_container_width=True, hide_index=True)

    chart_df = category_summary.reset_index()
    chart_df.columns = ["Category", "Amount"]

    st.subheader("📈 Spending Breakdown")
    fig_pie = px.pie(chart_df, names="Category", values="Amount", title="Spending by Category")
    fig_pie.update_traces(textfont_size=16)
    st.plotly_chart(fig_pie, use_container_width=True)

else:
    st.info("⬆️ Upload a CSV file to get started.")