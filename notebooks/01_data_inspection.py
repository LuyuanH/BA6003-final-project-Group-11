# %%
from pathlib import Path
import pandas as pd
# %%
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

print("Project root:", PROJECT_ROOT)
print("Raw data folder:", RAW_DATA_DIR)


# %%
print(df_trans_entity.columns.tolist())
# %%
# %% 算出付款交易,钱从哪里出去 Calculate outgoing transactions by entity

df_entity_outgoing = (
    df_trans_entity
    .groupby(
        ["From Entity ID", "From Entity Name"],
        dropna=False
    )
    .size()
    .reset_index(name="Outgoing_Transactions")
)

df_entity_outgoing.head(10)
# %%验证 Outgoing 有没有统计完整
print("Number of entities:", len(df_entity_outgoing))

print(
    "Total outgoing transactions:",
    df_entity_outgoing["Outgoing_Transactions"].sum()
)

df_entity_outgoing.sort_values(
    "Outgoing_Transactions",
    ascending=False
).head(10)


# %%计算 Incoming Transactions，钱去了哪里
df_entity_incoming = (
    df_trans_entity
    .groupby(
        ["To Entity ID", "To Entity Name"],
        dropna=False
    )
    .size()
    .reset_index(name="Incoming_Transactions")
)  
df_entity_incoming.head(10)
         

# %%验证inconming有没有统计完整
print("Number of entities:", len(df_entity_incoming))
print(
    "Total incoming transactions:",
    df_entity_incoming["Incoming_Transactions"].sum()
)
df_entity_incoming.sort_values(
    "Incoming_Transactions",
    ascending=False
).head(10)  

# %% Step 6A:统一表头 Standardize entity column names before merging

df_entity_outgoing_clean = df_entity_outgoing.rename(
    columns={
        "From Entity ID": "Entity_ID",
        "From Entity Name": "Entity_Name"
    }
)

df_entity_incoming_clean = df_entity_incoming.rename(
    columns={
        "To Entity ID": "Entity_ID",
        "To Entity Name": "Entity_Name"
    }
)

print("Outgoing columns:")
print(df_entity_outgoing_clean.columns.tolist())

print("\nIncoming columns:")
print(df_entity_incoming_clean.columns.tolist())

# %% Step 6B: 并表用并集
#Merge outgoing and incoming transaction counts

df_entity_flow = pd.merge(
    df_entity_outgoing_clean,
    df_entity_incoming_clean,
    on=["Entity_ID", "Entity_Name"],
    how="outer"
)

df_entity_flow.head(10)

# %% Step 6C: 看有没有只进不出或只出不进
# Check unmatched entities after outer merge

print("Total entities after merge:", len(df_entity_flow))

print(
    "Entities with no outgoing transactions:",
    df_entity_flow["Outgoing_Transactions"].isna().sum()
)

print(
    "Entities with no incoming transactions:",
    df_entity_flow["Incoming_Transactions"].isna().sum()
)

# %% Step 6D: 确认重复
# Check for duplicate entities

print(
    "Duplicate Entity_IDs:",
    df_entity_flow["Entity_ID"].duplicated().sum()
)


# %% Step 7A:填充缺失值
#  Replace missing transaction counts with zero

df_entity_flow[
    ["Outgoing_Transactions", "Incoming_Transactions"]
] = (
    df_entity_flow[
        ["Outgoing_Transactions", "Incoming_Transactions"]
    ]
    .fillna(0)
    .astype("int64")
)

df_entity_flow.head(10)

# %% Step 7B: 填充后验证
# Validate after filling missing values

print(
    "Missing outgoing values:",
    df_entity_flow["Outgoing_Transactions"].isna().sum()
)

print(
    "Missing incoming values:",
    df_entity_flow["Incoming_Transactions"].isna().sum()
)

print(
    "Total outgoing transactions:",
    df_entity_flow["Outgoing_Transactions"].sum()
)

print(
    "Total incoming transactions:",
    df_entity_flow["Incoming_Transactions"].sum()
)

# %% Step 7C: 账户参与的交易数
# Calculate total transaction involvement

df_entity_flow["Total_Transaction_Involvement"] = (
    df_entity_flow["Outgoing_Transactions"]
    + df_entity_flow["Incoming_Transactions"]
)

df_entity_flow.head(10)

# %%分析一：
# 计算outgoing/incoming ratio
# %% Step 8A: Calculate incoming and outgoing transaction ratios

df_entity_flow["Outgoing_Ratio"] = (
    df_entity_flow["Outgoing_Transactions"]
    / df_entity_flow["Total_Transaction_Involvement"]
)

df_entity_flow["Incoming_Ratio"] = (
    df_entity_flow["Incoming_Transactions"]
    / df_entity_flow["Total_Transaction_Involvement"]
)

df_entity_flow.head(10)

# %% Step 8B: Validate transaction direction ratios

df_entity_flow["Ratio_Sum"] = (
    df_entity_flow["Outgoing_Ratio"]
    + df_entity_flow["Incoming_Ratio"]
)

print(
    "Minimum ratio sum:",
    df_entity_flow["Ratio_Sum"].min()
)

print(
    "Maximum ratio sum:",
    df_entity_flow["Ratio_Sum"].max()
)

print(
    "Missing outgoing ratios:",
    df_entity_flow["Outgoing_Ratio"].isna().sum()
)

print(
    "Missing incoming ratios:",
    df_entity_flow["Incoming_Ratio"].isna().sum()
)

# %% Step 8C: Create percentage columns for easier interpretation

df_entity_flow["Outgoing_Pct"] = (
    df_entity_flow["Outgoing_Ratio"] * 100
).round(2)

df_entity_flow["Incoming_Pct"] = (
    df_entity_flow["Incoming_Ratio"] * 100
).round(2)

df_entity_flow[
    [
        "Entity_ID",
        "Entity_Name",
        "Outgoing_Transactions",
        "Incoming_Transactions",
        "Total_Transaction_Involvement",
        "Outgoing_Pct",
        "Incoming_Pct"
    ]
].head(10)
# %%资金流方向分类

# %% Step 9C: 创建资金流向分类表
# Classify entity transaction flow behavior

def classify_flow_behavior(row):
    
    if row["Outgoing_Transactions"] == 0:
        return "Incoming Only"
    
    elif row["Incoming_Transactions"] == 0:
        return "Outgoing Only"
    
    elif row["Outgoing_Ratio"] >= 0.70:
        return "Mainly Outgoing"
    
    elif row["Incoming_Ratio"] >= 0.70:
        return "Mainly Incoming"
    
    else:
        return "Balanced / Mixed"


df_entity_flow["Flow_Behavior"] = df_entity_flow.apply(
    classify_flow_behavior,
    axis=1
)

df_entity_flow[
    [
        "Entity_ID",
        "Entity_Name",
        "Outgoing_Transactions",
        "Incoming_Transactions",
        "Outgoing_Pct",
        "Incoming_Pct",
        "Flow_Behavior"
    ]
].head(10)


# %% Step 9D: 看看每一类到底有多少 Entity
# Count entities by flow behavior

df_flow_behavior_summary = (
    df_entity_flow["Flow_Behavior"]
    .value_counts()
    .rename_axis("Flow_Behavior")
    .reset_index(name="Entity_Count")
)

df_flow_behavior_summary

# %% Step 9E: Validate flow behavior classification

print(
    "Total entities:",
    len(df_entity_flow)
)

print(
    "Classified entities:",
    df_flow_behavior_summary["Entity_Count"].sum()
)

print(
    "Missing classifications:",
    df_entity_flow["Flow_Behavior"].isna().sum()
)

# %% Step 10A: Check currencies before aggregating transaction amounts

print("Payment currencies:")
print(
    df_trans_entity["Payment Currency"]
    .value_counts(dropna=False)
)

print("\nReceiving currencies:")
print(
    df_trans_entity["Receiving Currency"]
    .value_counts(dropna=False)
)

# %% Step 10B: Count unique currencies

print(
    "Number of payment currencies:",
    df_trans_entity["Payment Currency"].nunique()
)

print(
    "Number of receiving currencies:",
    df_trans_entity["Receiving Currency"].nunique()
)

# %% Step 10C: 检查收款与付款方货币是否一样
# Check same-currency vs cross-currency transactions

df_trans_entity["Same_Currency"] = (
    df_trans_entity["Payment Currency"]
    == df_trans_entity["Receiving Currency"]
)

print(
    df_trans_entity["Same_Currency"].value_counts()
)

print()

print(
    df_trans_entity["Same_Currency"]
    .value_counts(normalize=True)
    .mul(100)
    .round(2)
)
# %%
# %% Restore df_trans_entity after kernel restart

import pandas as pd
from pathlib import Path

TEMP_PKL_PATH = Path(
    "/Users/lu/amlens/data/processed/transactions_with_entities_temp.pkl"
)

df_trans_entity = pd.read_pickle(TEMP_PKL_PATH)

print("df_trans_entity restored successfully.")
print("Shape:", df_trans_entity.shape)

# %% Step 10D: Inspect cross-currency transaction examples

df_cross_currency_sample = df_trans_entity.loc[
    df_trans_entity["Same_Currency"] == False,
    [
        "Timestamp",
        "Amount Paid",
        "Payment Currency",
        "Amount Received",
        "Receiving Currency",
        "From Entity Name",
        "To Entity Name"
    ]
].head(20)

df_cross_currency_sample

# %% Step 10E: Check amount consistency for same-currency transactions

df_same_currency = df_trans_entity[
    df_trans_entity["Same_Currency"] == True
]

same_amount_count = (
    df_same_currency["Amount Paid"]
    == df_same_currency["Amount Received"]
).sum()

different_amount_count = (
    df_same_currency["Amount Paid"]
    != df_same_currency["Amount Received"]
).sum()

print("Same-currency transactions:", len(df_same_currency))
print("Same amount:", same_amount_count)
print("Different amount:", different_amount_count)

print(
    "Same amount percentage:",
    round(
        same_amount_count / len(df_same_currency) * 100,
        2
    ),
    "%"
)

# %% Step 11A: 创建 Cross_Currency
#  Create cross-currency transaction flag

df_trans_entity["Cross_Currency"] = (
    df_trans_entity["Payment Currency"]
    != df_trans_entity["Receiving Currency"]
).astype(int)

print(
    df_trans_entity["Cross_Currency"].value_counts()
)

# %% Step 11B-1: 付款的Cross-Currency
# Count outgoing cross-currency transactions by entity

df_outgoing_cross_currency = (
    df_trans_entity
    .groupby(
        ["From Entity ID", "From Entity Name"],
        dropna=False
    )["Cross_Currency"]
    .sum()
    .reset_index(
        name="Outgoing_Cross_Currency_Transactions"
    )
)

df_outgoing_cross_currency.sort_values(
    "Outgoing_Cross_Currency_Transactions",
    ascending=False
).head(10)

# %% Step 11B-2: Validate outgoing cross-currency counts

print(
    "Total outgoing cross-currency transactions:",
    df_outgoing_cross_currency[
        "Outgoing_Cross_Currency_Transactions"
    ].sum()
)

print(
    "Expected cross-currency transactions:",
    df_trans_entity["Cross_Currency"].sum()
)

# %%Step 11C-1: Count incoming cross-currency transactions by entity

df_incoming_cross_currency = (
    df_trans_entity
    .groupby(
        ["To Entity ID", "To Entity Name"],
        dropna=False
    )["Cross_Currency"]
    .sum()
    .reset_index(
        name="Incoming_Cross_Currency_Transactions"
    )
)

df_incoming_cross_currency.sort_values(
    "Incoming_Cross_Currency_Transactions",
    ascending=False
).head(10)

# %% Step 11C-2: Validate incoming cross-currency counts

print(
    "Total incoming cross-currency transactions:",
    df_incoming_cross_currency[
        "Incoming_Cross_Currency_Transactions"
    ].sum()
)

print(
    "Expected cross-currency transactions:",
    df_trans_entity["Cross_Currency"].sum()
)


# %% Step 11D-1:统一名称 Standardize entity names for cross-currency tables

df_outgoing_cross_currency_clean = (
    df_outgoing_cross_currency.rename(
        columns={
            "From Entity ID": "Entity_ID",
            "From Entity Name": "Entity_Name"
        }
    )
)

df_incoming_cross_currency_clean = (
    df_incoming_cross_currency.rename(
        columns={
            "To Entity ID": "Entity_ID",
            "To Entity Name": "Entity_Name"
        }
    )
)

print(df_outgoing_cross_currency_clean.columns.tolist())
print(df_incoming_cross_currency_clean.columns.tolist())



# %% Step 11D-2: Merge cross-currency features into entity flow table

df_entity_flow = df_entity_flow.merge(
    df_outgoing_cross_currency_clean,
    on=["Entity_ID", "Entity_Name"],
    how="left"
)

df_entity_flow = df_entity_flow.merge(
    df_incoming_cross_currency_clean,
    on=["Entity_ID", "Entity_Name"],
    how="left"
)

df_entity_flow.head()

# %% Step 11D-3: Fill missing cross-currency counts with zero

cross_currency_columns = [
    "Outgoing_Cross_Currency_Transactions",
    "Incoming_Cross_Currency_Transactions"
]

df_entity_flow[cross_currency_columns] = (
    df_entity_flow[cross_currency_columns]
    .fillna(0)
    .astype("int64")
)

# %%
