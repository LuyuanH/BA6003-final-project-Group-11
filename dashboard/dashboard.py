
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from aml_pipeline.config import DATABASE_PATH
from aml_pipeline.ai_insight import explain_view

load_dotenv(ROOT / '.env')
st.set_page_config(page_title='AMLens | Transaction Monitoring', page_icon='🔎', layout='wide')
st.markdown('''<style>.block-container{padding-top:1.5rem;max-width:1440px}
div[data-testid="stMetric"]{background:#f4f7fb;padding:16px;border-radius:12px}</style>''', unsafe_allow_html=True)

RULE_TEXT = {
    'HIGH_ACTIVITY': 'Sent transactions exceed the 97.5th percentile (114 in this dataset).',
    'FAN_OUT': 'Distinct outgoing entity counterparties exceed the 97.5th percentile (15).',
    'FAN_IN': 'Distinct incoming entity counterparties exceed the 97.5th percentile (12).',
    'CROSS_CURRENCY': 'At least 20 outgoing cross-currency transactions, representing at least 50% of outgoing transactions.',
    'ROUND_TRIP_2_EDGES': 'A → B → A within 120 hours, returning to the original bank account.',
    'CIRCULAR_3_EDGES': 'A → B → C → A within 120 hours, with three distinct entities and a return to the original bank account.',
}


def database_version():
    # SQLite WAL can change independently of the main database file.
    return tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else (0, 0)
                 for p in [DATABASE_PATH, Path(str(DATABASE_PATH) + '-wal')])


@st.cache_data(show_spinner=False)
def read_table(table, version):
    allowed = {'entity_features', 'alerts', 'daily_activity', 'review_status', 'rule_thresholds'}
    if table not in allowed:
        raise ValueError('Unsupported table')
    with sqlite3.connect(DATABASE_PATH) as conn:
        return pd.read_sql_query(f'SELECT * FROM {table}', conn)


def save_review(alert_id, status, conclusion, note):
    now = datetime.now().isoformat(timespec='seconds')
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute('''INSERT INTO review_status(Alert_ID, Status, Conclusion, Note, Updated_At)
            VALUES (?, ?, ?, ?, ?) ON CONFLICT(Alert_ID) DO UPDATE SET
            Status=excluded.Status, Conclusion=excluded.Conclusion,
            Note=excluded.Note, Updated_At=excluded.Updated_At''', (alert_id, status, conclusion, note, now))
        conn.execute('''INSERT INTO review_history(Alert_ID, Status, Conclusion, Note, Changed_At)
            VALUES (?, ?, ?, ?, ?)''', (alert_id, status, conclusion, note, now))
    read_table.clear()


def evaluate(name, selected, labels):
    flagged = labels.index.isin(selected)
    tp = int((labels & flagged).sum())
    fp = int((~labels & flagged).sum())
    return {'Method': name, 'Alerts': int(flagged.sum()), 'Label hits': tp,
            'False positives': fp, 'Missed labels': int(labels.sum()) - tp,
            'Precision': tp / max(tp + fp, 1), 'Recall': tp / max(int(labels.sum()), 1)}


def draw_cycle(steps):
    """The arrows follow actual ordered transactions; the table contains details."""
    n = len(steps)
    points = [(-1, 0), (1, 0)] if n == 2 else [(0, 1), (1, -0.7), (-1, -0.7)]
    fig = go.Figure()
    for i, row in enumerate(steps.itertuples(index=False)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % n]
        # Offset return arrows in a two-node path so both directions are visible.
        offset = .12 if n == 2 and i == 0 else (-.12 if n == 2 else 0)
        fig.add_annotation(x=x1 * .82, y=y1 * .82 + offset, ax=x0 * .82,
                           ay=y0 * .82 + offset, xref='x', yref='y', axref='x', ayref='y',
                           showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor='#267baf')
        fig.add_annotation(x=(x0+x1)/2, y=(y0+y1)/2 + offset + (.2 if n == 2 and i == 0 else -.2),
                           text=f'Step {i+1}', showarrow=False)
    names = [f"{chr(65+i)} · {r['From Entity ID']}" for i, (_, r) in enumerate(steps.iterrows())]
    fig.add_trace(go.Scatter(x=[p[0] for p in points], y=[p[1] for p in points],
                            mode='markers+text', text=names, textposition='top center',
                            marker={'size': 26, 'color': '#113e59'}, hoverinfo='text'))
    fig.update_layout(height=310, margin={'l': 30, 'r': 30, 't': 30, 'b': 20},
                      xaxis={'visible': False, 'range': [-1.5, 1.5]},
                      yaxis={'visible': False, 'range': [-1.3, 1.5]}, showlegend=False)
    return fig


st.title('🔎 AMLens | Transaction Monitoring')
st.caption('Explainable entity alerts • Six monitoring rules • Human review')
if not DATABASE_PATH.exists():
    st.warning('Run the data pipeline before opening the dashboard.')
    st.stop()
try:
    version = database_version()
    entities = read_table('entity_features', version)
    alerts = read_table('alerts', version).merge(read_table('review_status', version), on='Alert_ID', how='left')
    daily = read_table('daily_activity', version)
    thresholds = read_table('rule_thresholds', version)
    if 'Priority_Reason' not in alerts:
        raise ValueError('Run the updated six-rule pipeline first.')
except Exception as exc:
    st.error(f'Dashboard data is not ready: {exc}')
    st.stop()
alerts['Status'] = alerts.Status.fillna('Pending')

with st.sidebar:
    st.header('Entity filters')
    types = sorted(entities.Entity_Type.dropna().unique())
    chosen = st.multiselect('Entity type', types, default=types)
    label_filter = st.selectbox('Dataset label', ['All', 'Positive', 'Negative'])
    minimum = st.number_input('Minimum sent transactions', min_value=0, value=0, step=1)
    st.caption('Entity filters affect the queue and investigation. Performance uses the full dataset.')
    if st.button('Reload data'):
        read_table.clear()
        st.rerun()
filtered = entities[entities.Entity_Type.isin(chosen) & entities.Sent_Transactions.ge(minimum)].copy()
if label_filter != 'All':
    filtered = filtered[filtered.Known_Laundering_Entity.eq(int(label_filter == 'Positive'))]
fa = alerts[alerts.Entity_ID.isin(filtered.Entity_ID)].copy()
overview, queue, investigation, performance = st.tabs(['Overview', 'Alert Queue', 'Investigation', 'Performance & Rules'])

with overview:
    cols = st.columns(4)
    cols[0].metric('Entities in view', f'{len(filtered):,}')
    cols[1].metric('Transactions · full dataset', f'{daily.Transactions.sum():,}')
    cols[2].metric('Alerts in view', f'{len(fa):,}')
    cols[3].metric('Pending reviews', f'{fa.Status.eq("Pending").sum():,}')
    left, right = st.columns([1.5, 1])
    with left:
        st.subheader('Daily transaction activity')
        st.plotly_chart(px.line(daily, x='Date', y='Transactions'), width='stretch')
        st.plotly_chart(px.bar(daily, x='Date', y='Labelled_Transactions', title='Laundering-labelled transactions'), width='stretch')
    with right:
        st.subheader('Review priority')
        counts = fa.Priority.value_counts().reindex(['High', 'Medium', 'Low'], fill_value=0).rename_axis('Priority').reset_index(name='Entities')
        st.plotly_chart(px.bar(counts, x='Priority', y='Entities', color='Priority',
            color_discrete_map={'High': '#b43c39', 'Medium': '#db9a2e', 'Low': '#3b7b9a'}), width='stretch')
        st.caption('Priority is an ordinal review policy, not a probability or a sum of triggered rules.')
    with st.expander('Optional AI explanation'):
        st.write('API setup: enter OPENROUTER_API_KEY in the project .env file, then restart the app. The key is blank by default.')
        st.caption('Only aggregate counts are sent to the configured provider. No account IDs, transaction paths or analyst notes are sent.')
        if st.button('Explain this view'):
            context = f'Entities: {len(filtered)}. Alerts: {len(fa)}. Priority counts: {counts.to_dict(orient="records")}. Priority is not a probability. Explain in English.'
            try:
                with st.spinner('Generating explanation…'):
                    st.write(explain_view(context))
            except Exception as exc:
                st.warning(f'AI explanation unavailable: {exc}')

with queue:
    st.subheader('Alert queue')
    a, b, c = st.columns(3)
    priorities = a.multiselect('Review priority', ['High', 'Medium', 'Low'], default=['High', 'Medium', 'Low'])
    statuses = b.multiselect('Review status', ['Pending', 'In progress', 'Closed'], default=['Pending', 'In progress', 'Closed'])
    rule = c.selectbox('Triggered rule', ['All'] + list(RULE_TEXT))
    visible = fa[fa.Priority.isin(priorities) & fa.Status.isin(statuses)]
    if rule != 'All':
        visible = visible[visible['rule_' + rule].astype(bool)]
    st.caption(f'{len(visible):,} alerts. Rule count is descriptive; it does not determine priority by addition.')
    display = ['Alert_ID', 'Entity_Name', 'Priority', 'Priority_Reason', 'Rule_Count', 'Triggered_Rules', 'Status']
    st.dataframe(visible[display], hide_index=True, width='stretch')
    st.download_button('Download filtered alerts', visible[display].to_csv(index=False), 'amlens_alerts.csv', 'text/csv')

with investigation:
    st.subheader('Entity investigation')
    if fa.empty:
        st.info('No alerts match the entity filters.')
    else:
        path_filter = st.selectbox('Case category', ['All alerts', 'Three-edge cycle', 'Two-edge return'])
        cases = fa
        if path_filter != 'All alerts':
            col = 'rule_CIRCULAR_3_EDGES' if path_filter == 'Three-edge cycle' else 'rule_ROUND_TRIP_2_EDGES'
            cases = cases[cases[col].astype(bool)]
        if cases.empty:
            st.info('No matching cases.')
        else:
            names = cases.set_index('Alert_ID').Entity_Name.to_dict()
            selected = st.selectbox('Select entity alert', cases.Alert_ID.tolist(), format_func=lambda key: f'{names[key]} · {key}')
            case = cases[cases.Alert_ID.eq(selected)].iloc[0]
            left, right = st.columns([1, 2])
            with left:
                st.metric('Review priority', case.Priority)
                st.write(f'**Entity:** {case.Entity_Name} ({case.Entity_ID})')
                st.write(f'**Reason:** {case.Priority_Reason}')
                st.caption('Dataset label is used for retrospective evaluation only.')
            with right:
                triggered = case.Triggered_Rules.split(', ')
                st.dataframe(pd.DataFrame([{'Triggered rule': r, 'Explanation': RULE_TEXT[r]} for r in triggered]), hide_index=True, width='stretch')
            with sqlite3.connect(DATABASE_PATH) as conn:
                paths = pd.read_sql_query('''SELECT p.* FROM cycle_paths p JOIN cycle_members m
                    ON p.Path_ID=m.Path_ID WHERE m.Entity_ID=? ORDER BY p.Edge_Count DESC, p.Start_Time''', conn, params=(case.Entity_ID,))
                recent = pd.read_sql_query('SELECT * FROM alert_evidence WHERE Alert_ID=? ORDER BY Timestamp DESC', conn, params=(selected,))
                history = pd.read_sql_query('SELECT Status, Conclusion, Note, Changed_At FROM review_history WHERE Alert_ID=? ORDER BY History_ID DESC', conn, params=(selected,))
            st.subheader('Closed transaction paths')
            if paths.empty:
                st.info('No two- or three-edge closed path triggered for this entity.')
            else:
                st.caption(f'{len(paths)} complete paths. These are the actual rule-triggering transactions, separate from recent activity below.')
                chosen_path = st.selectbox('Select closed path', paths.Path_ID.tolist())
                path = paths[paths.Path_ID.eq(chosen_path)].iloc[0]
                with sqlite3.connect(DATABASE_PATH) as conn:
                    steps = pd.read_sql_query('SELECT * FROM cycle_transactions WHERE Path_ID=? ORDER BY Step', conn, params=(chosen_path,))
                st.write(f'**{path.Rule}** · {int(path.Edge_Count)} transactions · {path.Duration_Hours:.2f} hours')
                st.plotly_chart(draw_cycle(steps), width='stretch')
                evidence_columns = ['Step', 'Transaction_ID', 'Timestamp', 'From Entity ID', 'From Bank', 'From Account', 'To Entity ID', 'To Bank', 'To Account', 'Amount Paid', 'Payment Currency', 'Amount Received', 'Receiving Currency']
                st.dataframe(steps[evidence_columns], hide_index=True, width='stretch')
                st.download_button('Download path transactions', steps[evidence_columns].to_csv(index=False), f'{chosen_path}.csv', 'text/csv')
                st.caption('Strict time order; same bank/account at each intermediary; local currency matches; outgoing/incoming amount ratio 80–120%. The final transfer returns to the starting bank/account. Candidate links do not establish ownership of the same funds; no FX-normalized return-value or balance test is applied.')
            with st.expander('Recent linked transactions · context, not necessarily rule evidence'):
                st.dataframe(recent.drop(columns=['Alert_ID'], errors='ignore'), hide_index=True, width='stretch')
            with st.form('review_' + selected):
                options = ['Pending', 'In progress', 'Closed']
                status = st.selectbox('Review status', options, index=options.index(case.Status))
                outcomes = ['Not reviewed', 'Needs follow-up', 'No further action', 'Escalated']
                saved = case.get('Conclusion', '')
                conclusion = st.selectbox('Review outcome', outcomes, index=outcomes.index(saved) if saved in outcomes else 0)
                note = st.text_area('Analyst note', value='' if pd.isna(case.get('Note')) else str(case.get('Note', '')))
                if st.form_submit_button('Save review', type='primary'):
                    save_review(selected, status, conclusion, note)
                    st.rerun()
            with st.expander('Review history'):
                st.dataframe(history, hide_index=True, width='stretch')

with performance:
    st.subheader('Retrospective evaluation · full dataset')
    st.caption('Positive entity: participated in at least one transaction with Is Laundering = 1. Labels never enter detection or priority assignment.')
    labels = entities.set_index('Entity_ID').Known_Laundering_Entity.astype(bool)
    old_columns = ['rule_HIGH_ACTIVITY', 'rule_FAN_OUT', 'rule_FAN_IN', 'rule_CROSS_CURRENCY']
    old_ids = set(alerts.loc[alerts[old_columns].astype(bool).any(axis=1), 'Entity_ID'])
    baseline = set(entities.sort_values(['Sent_Transactions', 'Entity_ID'], ascending=[False, True]).head(len(alerts)).Entity_ID)
    comparison = pd.DataFrame([evaluate('Original four rules', old_ids, labels), evaluate('Six rules', set(alerts.Entity_ID), labels), evaluate('Activity baseline · same review volume', baseline, labels)])
    st.dataframe(comparison.style.format({'Precision': '{:.2%}', 'Recall': '{:.2%}'}), hide_index=True, width='stretch')
    st.write('In this synthetic benchmark, an alerted entity without a positive dataset label is counted as a false positive.')
    priority_metrics = pd.DataFrame([evaluate(level, set(alerts.loc[alerts.Priority.eq(level), 'Entity_ID']), labels) for level in ['High', 'Medium', 'Low']])
    st.dataframe(priority_metrics.style.format({'Precision': '{:.2%}', 'Recall': '{:.2%}'}), hide_index=True, width='stretch')
    st.subheader('How review priority is assigned')
    st.markdown('''- **High:** a three-edge cycle, or a two-edge return plus any original rule.
- **Medium:** a two-edge return alone, or both original scale/breadth and currency signals.
- **Low:** one original signal family. Activity and counterparty breadth belong to the same family.

Use the highest matching level. This is a review policy, not an additive score or a calibrated probability. Observed precision need not increase at every level.''')
    st.subheader('Six monitoring rules')
    st.dataframe(pd.DataFrame([{'Rule': k, 'Condition': v} for k, v in RULE_TEXT.items()]), hide_index=True, width='stretch')
    with st.expander('Computed thresholds'):
        st.dataframe(thresholds, hide_index=True, width='stretch')
    st.warning('Development-period retrospective results, not independent validation. The 120-hour cycle window was informed by development-set pattern diagnostics. Only two- and three-edge cycles are searched; longer paths can be missed.')

st.caption('AMLens · Explainable monitoring · Review signals are not findings of misconduct')
