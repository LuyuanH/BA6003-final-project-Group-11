// Model text is always escaped. Only validated evidence IDs become navigation controls.
function analysisReportMarkup(entry, features, t) {
  const report=entry.report;
  const refs=item=>`<div class="analysis-refs">${item.transaction_ids.map(id=>`<button type="button" class="analysis-reference" data-analysis-tx="${id}">${esc(t('aiTransaction',{id}))} ↗</button>`).join('')}${item.feature_names.map(name=>`<span class="analysis-feature">${esc(name)}: ${esc(JSON.stringify(features[name]))}</span>`).join('')}</div>`;
  const findings=(title,items)=>`<section class="analysis-section"><h3>${esc(t(title))}</h3>${items.length?items.map(item=>`<div class="analysis-finding"><p>${esc(item.explanation)}</p>${refs(item)}</div>`).join(''):`<p class="analysis-muted">${esc(t('aiNoFindings'))}</p>`}</section>`;
  const list=(title,items)=>`<section class="analysis-section"><h3>${esc(t(title))}</h3>${items.length?`<ul>${items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`:`<p class="analysis-muted">${esc(t('aiNoItems'))}</p>`}</section>`;
  return `<div class="analysis-conclusion"><span class="analysis-verdict">${esc(t('aiAssessment_'+report.assessment))}</span><p>${esc(report.summary)}</p><p class="analysis-muted">${esc(report.reason)}</p></div><div class="analysis-columns">${findings('aiSupporting',report.supporting_evidence)}${findings('aiCounter',report.counter_evidence)}</div><section class="analysis-section analysis-pattern"><h3>${esc(t('aiPattern'))} · ${esc(t('aiPattern_'+report.pattern_assessment.verdict))}</h3><p>${esc(report.pattern_assessment.explanation)}</p>${refs(report.pattern_assessment)}</section><div class="analysis-columns">${list('aiNormal',report.normal_explanations)}${list('aiMissing',report.missing_information)}</div>${list('aiNext',report.next_steps)}`;
}

function overviewReportMarkup(entry, t, pattern) {
  const report=entry.report;
  const names={processed_transactions:'processed',held_transactions:'hold',detected_transactions:'insightDetected',observed_cases:'insightObserved',pending_cases:'pendingCases',investigating_cases:'investigating',reviewed_cases:'reviewed',recent_6h_transactions:'insightRecent',previous_6h_transactions:'insightPrevious'};
  const metricName=key=>{
    if(names[key])return t(names[key]);
    const [family,field]=key.split('.');
    return pattern(family.toUpperCase().replaceAll('_','-'))+' · '+t({active_cases:'insightActiveCases',held_transactions:'hold',detected_transactions:'insightDetected'}[field]);
  };
  const list=(title,items)=>`<section class="analysis-section"><h3>${esc(t(title))}</h3><ul>${items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></section>`;
  const findings=report.findings.map(item=>`<section><h3>${esc(item.title)}</h3><p>${esc(item.explanation)}</p><div class="insight-metrics">${item.metric_refs.map(key=>`<span class="insight-metric">${esc(metricName(key))}: ${esc(num(entry.metrics[key]))}</span>`).join('')}</div></section>`).join('');
  const cases=report.focus_cases.map(item=>`<div class="insight-case"><button class="text-button" type="button" data-insight-case="${esc(item.case_id)}">${esc(caseId(item.case_id))} ↗</button><p>${esc(item.reason)}</p></div>`).join('');
  return `<p>${esc(report.summary)}</p><div class="insight-findings">${findings}</div>${cases?`<section class="insight-focus"><h3>${esc(t('insightFocus'))}</h3>${cases}</section>`:''}<div class="analysis-columns">${list('insightChecks',report.next_steps)}${list('insightLimits',report.limitations)}</div>`;
}
