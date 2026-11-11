/* 竞品洞察 ③ 即时分析：自包含渲染，风格沿用现有深蓝 token，不污染全局。 */
(function () {
  'use strict';

  const STATUS_TEXT = {
    ok: '可计算',
    partial: '部分可计算',
    empty: '空态',
    insufficient: '样本不足',
  };

  // 仅前端措辞覆盖，后端口径与字段不变。
  const TILE_SUBTITLE_OVERRIDE = {
    attention: '关注什么；16 维多选勾选率（非首选率），可展开看完整明细',
  };
  const METRIC_LABEL_OVERRIDE = {
    attention: '购车关注（16 维多选勾选率，非首选率）',
    first_ranking: '首选率（产品 / 品牌 / 服务 第一排序）',
  };
  const EMPTY_NOTE = {
    first_ranking: '首选率 · 待业务补排序题，不估算、不填 0。',
  };


  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function pct(value) {
    return value == null ? '—' : Number(value).toFixed(1) + '%';
  }

  function num(value) {
    return value == null ? '—' : String(value);
  }

  function sampleChip(flag) {
    if (flag === 'small') return '<span class="bci-a-chip bci-a-chip--warn">小样本</span>';
    if (flag === 'insufficient') return '<span class="bci-a-chip bci-a-chip--bad">样本不足</span>';
    return '';
  }

  function statusChip(status) {
    const text = STATUS_TEXT[status] || status || '可计算';
    const tone = status === 'empty' ? 'bad' : status === 'insufficient' ? 'bad' : status === 'partial' ? 'warn' : 'ok';
    return '<span class="bci-a-chip bci-a-chip--' + tone + '">' + esc(text) + '</span>';
  }

  function ratioText(item) {
    if (item.ratio == null) return esc(item.count) + '/' + esc(item.n) + ' · 不展示比例';
    return esc(item.count) + '/' + esc(item.n) + ' · ' + pct(item.ratio) + ' · n=' + esc(item.n);
  }

  function bar(item, max) {
    const width = item.ratio != null
      ? Math.max(2, Math.min(100, Number(item.ratio)))
      : Math.max(2, Math.min(100, (Number(item.count) / Math.max(1, max)) * 100));
    return (
      '<div class="bci-a-bar"><span class="bci-a-bar__fill" style="width:' + width.toFixed(1) + '%"></span></div>'
    );
  }

  function metricHeader(metric) {
    const n = metric.n != null ? 'n=' + esc(metric.n) : '';
    const answered = metric.answered != null ? '作答=' + esc(metric.answered) : '';
    const label = METRIC_LABEL_OVERRIDE[metric.key] || metric.label;
    return (
      '<header class="bci-a-metric__head">' +
        '<div class="bci-a-metric__title"><h5>' + esc(label) + '</h5>' +
          statusChip(metric.status) + sampleChip(metric.sample_flag) +
        '</div>' +
        '<div class="bci-a-metric__meta">' + [n, answered].filter(Boolean).join(' · ') + '</div>' +
      '</header>'
    );
  }

  function emptyBox(metric) {
    const note = EMPTY_NOTE[metric.key]
      ? '<p class="bci-a-empty__note">' + esc(EMPTY_NOTE[metric.key]) + '</p>'
      : '';
    return (
      '<div class="bci-a-empty" role="note">' +
        '<b>空态 · 不计算</b>' + note +
        '<p>' + esc(metric.reason || '缺少可复算的数据源。') + '</p>' +
      '</div>'
    );
  }

  function distribution(metric, options) {
    const opts = options || {};
    const items = opts.items || metric.top || metric.items || [];
    const max = Math.max.apply(null, items.map(function (item) { return Number(item.count) || 0; }).concat([1]));
    const rows = items.map(function (item) {
      return (
        '<div class="bci-a-row">' +
          '<span class="bci-a-row__label" title="' + esc(item.label) + '">' + esc(item.label) + '</span>' +
          '<div class="bci-a-row__body">' + bar(item, max) +
            '<span class="bci-a-row__meta">' + ratioText(item) + '</span></div>' +
          (item.qual_people != null
            ? '<span class="bci-a-row__qual">定性 ' + esc(item.qual_people) + ' 人</span>'
            : '') +
        '</div>'
      );
    }).join('');
    const details = opts.details && metric.items && metric.items.length > items.length
      ? '<details class="bci-a-details"><summary>查看全部 ' + esc(metric.items.length) + ' 维明细</summary>' +
        '<table class="bci-a-table"><thead><tr><th>维度</th><th>定量</th><th>定性人数</th></tr></thead><tbody>' +
        metric.items.map(function (item) {
          return '<tr><td>' + esc(item.label) + '</td><td>' + ratioText(item) + '</td><td>' +
            (item.qual_people != null ? esc(item.qual_people) + ' 人' : '—') + '</td></tr>';
        }).join('') +
        '</tbody></table></details>'
      : '';
    return rows + details;
  }

  function numericMetric(metric) {
    const items = metric.items || [];
    const max = Math.max.apply(null, items.map(function (item) { return Number(item.count) || 0; }).concat([1]));
    return (
      '<div class="bci-a-median">中位数 <b>' + esc(num(metric.median)) + ' 万</b>' +
        '<span>作答 ' + esc(metric.answered) + '/' + esc(metric.n) + '</span></div>' +
      items.map(function (item) {
        return (
          '<div class="bci-a-row">' +
            '<span class="bci-a-row__label">' + esc(item.label) + '</span>' +
            '<div class="bci-a-row__body">' + bar(item, max) +
              '<span class="bci-a-row__meta">' + ratioText(item) + '</span></div>' +
          '</div>'
        );
      }).join('')
    );
  }

  function qualitative(metric) {
    const chips = (metric.dimension_people || []).map(function (item) {
      return '<span class="bci-a-tag">' + esc(item.label) + ' · ' + esc(item.people) + ' 人</span>';
    }).join('');
    const quotes = (metric.items || []).map(function (item) {
      return (
        '<blockquote class="bci-a-quote">' +
          '<p>' + esc(item.quote) + '</p>' +
          '<footer><span>' + esc(item.respondent_code) + ' · ' + esc(item.question_id) + '</span>' +
            (item.dimensions || []).map(function (tag) {
              return '<span class="bci-a-tag bci-a-tag--soft">' + esc(tag) + '</span>';
            }).join('') +
          '</footer>' +
        '</blockquote>'
      );
    }).join('');
    const unmatched = (metric.unmatched || []).length
      ? '<details class="bci-a-details"><summary>未匹配到 16 维的原话（' +
        esc(metric.unmatched.length) + ' 条）</summary>' +
        metric.unmatched.map(function (item) {
          return '<blockquote class="bci-a-quote bci-a-quote--plain"><p>' + esc(item.quote) + '</p>' +
            '<footer><span>' + esc(item.respondent_code) + ' · ' + esc(item.question_id) + '</span></footer></blockquote>';
        }).join('') + '</details>'
      : '';
    return (
      '<p class="bci-a-note">深访 ' + esc(metric.people) + ' 人 · 有效原话 ' + esc(metric.answered) +
        ' 条；逐人原话，不做比例。</p>' +
      (chips ? '<div class="bci-a-tags">' + chips + '</div>' : '') +
      '<div class="bci-a-quotes">' + quotes + '</div>' + unmatched
    );
  }

  function scoreMetric(metric) {
    return (
      '<div class="bci-a-score"><b>' + esc(num(metric.mean)) + '</b><span>分 · 作答 ' +
        esc(metric.answered) + '/' + esc(metric.n) + '</span></div>' +
      (metric.items && metric.items.length ? distribution(metric, { items: metric.items }) : '') +
      (metric.note ? '<p class="bci-a-note">' + esc(metric.note) + '</p>' : '')
    );
  }

  function scoreList(metric) {
    const top = (metric.top || []).slice(0, 5);
    const bottom = (metric.bottom || []).slice(0, 5);
    function side(title, items, tone) {
      return '<div class="bci-a-side bci-a-side--' + tone + '"><h6>' + title + '</h6>' +
        items.map(function (item) {
          return '<div class="bci-a-scoreline"><span>' + esc(item.label) + '</span><b>' + esc(num(item.mean)) +
            '</b><em>' + esc(item.answered) + ' 人</em></div>';
        }).join('') + '</div>';
    }
    const rows = (metric.items || []).map(function (item) {
      const low = item.low_rate == null ? '—' : esc(item.low_rate) + '%（' + esc(item.low_count) + '/' + esc(item.answered) + '）';
      return '<tr><td>' + esc(item.label) + '</td><td>' + esc(num(item.mean)) + '</td><td>' +
        esc(item.answered) + '</td><td>' + low + '</td></tr>';
    }).join('');
    return '<div class="bci-a-sides">' + side('满意度最高 5 项', top, 'ok') + side('满意度最低 5 项', bottom, 'bad') + '</div>' +
      '<details class="bci-a-details"><summary>查看全部 16 维打分</summary>' +
      '<table class="bci-a-table"><thead><tr><th>维度</th><th>均分</th><th>作答</th><th>低分率（≤6）</th></tr></thead><tbody>' +
      rows + '</tbody></table></details>';
  }

  function reputationMetric(metric) {
    const dens = metric.denominators || {};
    const boundary = metric.boundary || {};
    const rollup = metric.rollup || {};
    function row(label, count, ratio) {
      return '<div class="bci-a-rep__row"><span>' + esc(label) + '</span><b>' + esc(count) + ' 条' +
        (ratio != null ? '<em>' + pct(ratio) + '</em>' : '') + '</b></div>';
    }
    function column(title, items, denom, tone, fallback) {
      const rows = (items || []).map(function (item) {
        return row(item.label, item.count, item.ratio);
      }).join('');
      const thin = denom != null && Number(denom) < 50
        ? '<p class="bci-a-note">样本不足（n=' + esc(denom) + '），以下为实际点，未排名</p>'
        : '';
      // 该方向 L3 全部 <3 条时回退到一级类目，并标明粒度。
      let content = rows;
      if (!content && (fallback || []).length) {
        content = '<p class="bci-a-note">粒度：类目（L3 均不足 3 条，回退到一级类目）</p>' +
          fallback.map(function (item) {
            return row(item.label, item.count, denom ? Math.round(item.count * 1000 / denom) / 10 : null);
          }).join('');
      }
      return '<div class="bci-a-rep bci-a-rep--' + tone + '"><h6>' + title +
        ' <span>分母 ' + (denom == null ? '—' : esc(denom)) + ' 条</span></h6>' + thin +
        (content || '<p class="bci-a-note">无达标点（单点需 ≥3 条）</p>') + '</div>';
    }
    function rollupBlock() {
      const labels = [];
      const seen = {};
      [rollup.positive || [], rollup.negative || []].forEach(function (list) {
        list.forEach(function (item) {
          if (!seen[item.label]) { seen[item.label] = true; labels.push(item.label); }
        });
      });
      if (!labels.length) return '';
      function pick(list, label) {
        const hit = (list || []).filter(function (item) { return item.label === label; })[0];
        return hit ? hit.count : 0;
      }
      const rows = labels.map(function (label) {
        return '<tr><td>' + esc(label) + '</td><td>' + esc(pick(rollup.positive, label)) +
          '</td><td>' + esc(pick(rollup.negative, label)) + '</td></tr>';
      }).join('');
      return '<details class="bci-a-details"><summary>查看类目上卷（16 类，样本不足时兜底）</summary>' +
        '<table class="bci-a-table"><thead><tr><th>类目</th><th>正向条数</th><th>负向条数</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table></details>';
    }
    const model = '当前车型：' + esc(metric.model) + '（n=' + esc(dens.positive == null ? '—' : dens.positive) +
      '，截至 2026-11-04）· 本车自身口碑分布，非竞品份额';
    return '<p class="bci-a-note">' + model + '</p>' +
      '<div class="bci-a-reps">' +
        column('正向关注 TOP5', metric.positive, dens.positive, 'ok', rollup.positive) +
        column('负向关注 TOP5', metric.negative, dens.negative, 'bad', rollup.negative) +
      '</div>' + rollupBlock() +
      '<p class="bci-a-note">仅' + esc(boundary.source || '汽车之家「满意 / 不满意」分栏') +
        '（时间 ' + esc(boundary.window || '2026-01 至 2026-11-04') + '，' + esc(boundary.limit || '每车系最多 200 条') +
        '）；' + esc(boundary.note || '方向按原句情感判定。') + '</p>';
  }

  function lossSplit(metric) {
    const rows = (metric.items || []).map(function (item) {
      const why = (item.reasons || []).map(function (reason) {
        return esc(reason.label) + ' ' + esc(reason.count) + '/' + esc(reason.n) +
          (reason.ratio != null ? '（' + pct(reason.ratio) + '）' : '');
      }).join('、');
      return (
        '<div class="bci-a-loss__row">' +
          '<div class="bci-a-loss__head">' +
            '<span class="bci-a-loss__title">' + esc(item.label) + ' 胜出</span>' +
            '<span class="bci-a-loss__count"><b>' + esc(item.count) + '</b> 人</span>' +
            (item.ratio != null
              ? '<span class="bci-a-loss__ratio">' + pct(item.ratio) + ' · 占对比过 ' + esc(item.n) + ' 人</span>'
              : '<span class="bci-a-loss__ratio is-hidden">' + esc(item.ratio_hidden_reason || '不足 5 人，不给百分比') + '</span>') +
          '</div>' +
          '<p class="bci-a-loss__why">' +
            (why ? '胜出原因（本行 ' + esc(item.count) + ' 人）：' + why : '本行没有 16 维勾选记录') +
          '</p>' +
        '</div>'
      );
    }).join('');
    return (
      '<div class="bci-a-loss">' + rows + '</div>' +
      '<p class="bci-a-basis">依据题号：' + esc(metric.basis) + '</p>' +
      (metric.note ? '<p class="bci-a-note">' + esc(metric.note) + '</p>' : '')
    );
  }

  function renderMetric(metric) {
    const head = metricHeader(metric);
    let body = '';
    if (metric.status === 'empty') {
      body = emptyBox(metric);
    } else if (metric.kind === 'loss_split') {
      body = lossSplit(metric);
    } else if (metric.kind === 'qualitative') {
      body = qualitative(metric);
    } else if (metric.kind === 'numeric') {
      body = numericMetric(metric);
    } else if (metric.kind === 'score') {
      body = scoreMetric(metric);
    } else if (metric.kind === 'score_list') {
      body = scoreList(metric);
    } else if (metric.kind === 'reputation') {
      body = reputationMetric(metric);
    } else {
      const ranked = ['attention', 'q3_23'].indexOf(metric.key) >= 0;
      body = distribution(metric, {
        items: ranked ? (metric.top || []).slice(0, 5) : metric.items,
        details: ranked,
      });
    }
    const reason = metric.status === 'insufficient' && metric.reason
      ? '<p class="bci-a-warn">' + esc(metric.reason) + '</p>' : '';
    const note = metric.note && metric.kind !== 'score' && metric.kind !== 'reputation'
      ? '<p class="bci-a-note">' + esc(metric.note) + '</p>' : '';
    return '<section class="bci-a-metric' + (metric.status === 'empty' ? ' is-empty' : '') + '">' +
      head + body + reason + note + '</section>';
  }

  function aiRow(ai) {
    if (!ai) return '';
    if (ai.source === 'error' || ai.source === 'empty') {
      return (
        '<div class="bci-a-ai is-error">' +
          '<span class="bci-a-ai__tag">AI 结论</span>' +
          '<p class="bci-a-ai__text">' + esc(ai.error || 'AI 结论生成失败') + '</p>' +
        '</div>'
      );
    }
    if (!ai.summary) return '';
    return (
      '<div class="bci-a-ai">' +
        '<span class="bci-a-ai__tag">AI 结论</span>' +
        '<p class="bci-a-ai__text">' + esc(ai.summary) + '</p>' +
        '<em class="bci-a-ai__note">基于本块数据生成</em>' +
      '</div>'
    );
  }

  function renderTile(tile, index, ai) {
    return (
      '<article class="bci-a-tile">' +
        '<header class="bci-a-tile__head">' +
          '<div class="bci-a-tile__mark">' + ['①', '②', '③', '④'][index] + '</div>' +
          '<div class="bci-a-tile__title"><h4>' + esc(tile.title) + '</h4>' +
            '<p>' + esc(TILE_SUBTITLE_OVERRIDE[tile.key] || tile.subtitle) + '</p></div>' +
          '<div class="bci-a-tile__chips">' + statusChip(tile.status) +
            (tile.n != null ? '<span class="bci-a-chip">n=' + esc(tile.n) + '</span>' : '') + '</div>' +
        '</header>' +
        (tile.banner ? '<p class="bci-a-banner">' + esc(tile.banner) + '</p>' : '') +
        '<div class="bci-a-metrics">' + (tile.metrics || []).map(renderMetric).join('') + '</div>' +
        aiRow(ai) +
      '</article>'
    );
  }

  function renderSources(sources) {
    const defs = [
      ['quant', '定量样本', '人'],
      ['interview', '深访', '人'],
      ['reputation', '口碑提及', '条'],
      ['miit', '配置款型', '个'],
    ];
    return defs.map(function (def) {
      const value = sources && sources[def[0]] != null ? sources[def[0]] : 0;
      return '<span class="bci-a-source' + (value ? '' : ' is-missing') + '">' +
        '<em>' + def[1] + '</em><b>' + esc(value) + '</b>' + def[2] + '</span>';
    }).join('');
  }

  const AGENT_SAMPLES = [
    '综合看用户购车关注、战胜战败和满意度，应该如何对标竞品开展营销',
    '对比本品和竞品，用户画像、购车关注有何差异',
  ];

  function agentRefs(refs) {
    return (refs || []).map(function (ref) {
      return '<code class="bci-a-agent__ref">' + esc(ref) + '</code>';
    }).join('');
  }

  function agentItems(items) {
    if (!items || !items.length) return '<p class="bci-a-agent__muted">本次没有可展示的条目。</p>';
    return '<ul class="bci-a-agent__list">' + items.map(function (item) {
      return '<li><span>' + esc(item.text) + '</span>' +
        (item.refs && item.refs.length ? '<span class="bci-a-agent__refs">' + agentRefs(item.refs) + '</span>' : '') +
        '</li>';
    }).join('') + '</ul>';
  }

  function renderAgentResult(agent) {
    if (!agent) return '';
    if (agent.loading) {
      return '<div class="bci-a-agent__status"><span class="bci-a-agent__spinner" aria-hidden="true"></span>' +
        '路由 → 取数 → 合成，通常需要 10–30 秒…</div>';
    }
    if (agent.error) {
      return '<div class="bci-a-empty bci-a-empty--error"><b>分析失败' +
        (agent.error.code ? '（' + esc(agent.error.code) + '）' : '') + '</b><p>' +
        esc(agent.error.message) + '</p></div>';
    }
    const data = agent.result;
    if (!data) {
      return '<p class="bci-a-agent__muted">目标车型取上方当前选中车；竞品由战胜战败数据实时算出。' +
        '每个数字带 n 与分母，小样本只给人数和原话。</p>';
    }
    if (data.status === 'clarify' || data.status === 'unsupported') {
      return '<div class="bci-a-agent__notice"><b>' +
        (data.status === 'clarify' ? '需要再明确一点' : '当前版本范围') + '</b><p>' +
        esc(data.message) + '</p></div>';
    }
    if (data.status === 'no_comparison_sample') {
      const pool = (data.pool || []).map(function (row) {
        return esc(row.model) + '（' + esc(row.people) + ' 人）';
      }).join('、');
      return '<div class="bci-a-agent__notice"><b>该车型与本品无对比样本</b><p>' +
        esc(data.message || '') + '</p>' +
        (pool ? '<p class="bci-a-agent__muted">池内候选：' + pool + '</p>' : '') + '</div>';
    }
    const answer = data.answer || {};
    const template = data.template === 'W2' ? 'W2' : 'W1';
    const title = template === 'W2' ? '双车对标' : '单车型综合诊断';
    let blocks = '';
    if (template === 'W2' && answer.benchmark && answer.benchmark.text) {
      blocks += '<p class="bci-a-agent__benchmark">' + esc(answer.benchmark.text) + '</p>';
    }
    blocks += (answer.sections || []).map(function (section) {
      if (!section || !section.text) return '';
      return '<section class="bci-a-agent__block"><h4>' + esc(section.title || '') + '</h4>' + agentItems([section]) + '</section>';
    }).join('');
    const tools = (data.tools || []).map(function (tool) {
      const caliber = tool.caliber || {};
      return '<li><code>' + esc(tool.tool) + '</code><span>n=' + esc(caliber.n == null ? '—' : caliber.n) +
        ' · 分母=' + esc(caliber.denominator == null ? '—' : caliber.denominator) +
        (caliber.question ? ' · ' + esc(caliber.question) : '') + '</span><em>' + esc(tool.status) + '</em></li>';
    }).join('');
    const warnings = (data.warnings || []).map(function (line) {
      return '<li>' + esc(line) + '</li>';
    }).join('');
    const verification = data.verification || {};
    return '<div class="bci-a-agent__meta">' +
        '<span class="bci-a-chip bci-a-chip--ok">' + title + '</span>' +
        '<b>' + esc(data.model && data.model.label || '') + '</b>' +
        (data.competitor ? '<span>vs ' + esc(data.competitor.label) + '</span>' : '') +
        '<em>数字校验通过' + (verification.attempts ? '（第 ' + esc(verification.attempts) + ' 次）' : '') + '</em>' +
      '</div>' +
      blocks +
      (answer.sample_note ? '<p class="bci-a-agent__note">' + esc(answer.sample_note) + '</p>' : '') +
      (warnings ? '<ul class="bci-a-agent__warnings">' + warnings + '</ul>' : '') +
      (tools ? '<details class="bci-a-agent__tools"><summary>取数明细（n / 分母）</summary><ul>' + tools + '</ul></details>' : '');
  }

  function renderAgent(state) {
    const agent = state.agent || {};
    const samples = AGENT_SAMPLES.map(function (text) {
      return '<button type="button" data-bci-agent-sample="' + esc(text) + '">' + esc(text) + '</button>';
    }).join('');
    return (
      '<section class="bci-a-agent" data-bci-agent>' +
        '<header class="bci-a-agent__head">' +
          '<div><span class="bci-a-eyebrow">智能化分析 · 独立区域</span>' +
          '<h3>用一句话下指令，智能体跨四路数据给结论</h3>' +
          '<p>与上方四个入口互不影响；模型只做意图路由和最终合成，取数与差值由代码完成。</p></div>' +
          '<span class="bci-a-agent__badge">当前车型：' + esc(state.currentLabel || '未选择') + '</span>' +
        '</header>' +
        '<div class="bci-a-agent__query">' +
          '<textarea data-bci-agent-question rows="2" maxlength="300" placeholder="例如：综合看用户购车关注、战胜战败和满意度，应该如何对标竞品开展营销">' +
            esc(agent.question || '') + '</textarea>' +
          '<div class="bci-a-agent__actions"><div class="bci-a-agent__samples">' + samples + '</div>' +
            '<button type="button" class="btn btn--primary" data-bci-agent-run' +
              (agent.loading ? ' disabled' : '') + '>' + (agent.loading ? '分析中…' : '开始分析') + '</button>' +
          '</div>' +
        '</div>' +
        '<div class="bci-a-agent__result">' + renderAgentResult(agent) + '</div>' +
      '</section>'
    );
  }

  function renderShell(state) {
    const models = state.models || [];
    const options = models.map(function (model) {
      const src = model.sources || {};
      return '<option value="' + esc(model.key) + '"' + (model.key === state.current ? ' selected' : '') + '>' +
        esc(model.label) + '（定量 ' + esc(src.quant || 0) + ' / 深访 ' + esc(src.interview || 0) + '）</option>';
    }).join('');
    return (
      '<div class="bci-a-top">' +
        '<div class="bci-a-top__text"><span class="bci-a-eyebrow">即时分析 · 真实库直连</span>' +
          '<h3>选一款车，查看四类可复算结论</h3>' +
          '<p>所有比例同时给分子/分母与样本基数；算不出来的指标显示空态与原因，不用近似值填充。</p></div>' +
        '<div class="bci-a-top__actions"><label class="bci-a-field"><span>车型</span>' +
          '<select data-bci-analysis-model>' + options + '</select></label>' +
          '<button type="button" class="btn btn--ghost" data-bci-analysis-refresh>重新查询</button></div>' +
      '</div>' +
      '<div class="bci-a-sourcebar">' + renderSources(state.data && state.data.sources) + '</div>' +
      renderAgent(state) +
      '<div data-bci-analysis-body>' + (state.loading ? '<div class="bci-a-loading">正在按真实库计算四类磁贴…</div>' : '') + '</div>'
    );
  }

  const TILE_ORDER = ['profile', 'attention', 'winloss', 'satisfaction'];
  const TILE_MARK = { profile: '①', attention: '②', winloss: '③', satisfaction: '④' };
  const TILE_HEAD = {
    profile: '用户画像',
    attention: '购车关注',
    winloss: '战胜战败原因洞察',
    satisfaction: '产品满意度评价',
  };

  function renderEntry(tile, key, isOpen) {
    return (
      '<button type="button" class="bci-a-entry' + (isOpen ? ' is-open' : '') + '"' +
        ' data-bci-analysis-toggle="' + esc(key) + '" aria-pressed="' + (isOpen ? 'true' : 'false') + '"' +
        ' aria-controls="bci-a-panel-' + esc(key) + '">' +
        '<span class="bci-a-entry__mark">' + TILE_MARK[key] + '</span>' +
        '<span class="bci-a-entry__body">' +
          '<span class="bci-a-entry__title">' + esc(TILE_HEAD[key]) + '</span>' +
          '<span class="bci-a-entry__desc">' + esc(TILE_SUBTITLE_OVERRIDE[key] || tile.subtitle || '') + '</span>' +
        '</span>' +
        '<span class="bci-a-entry__state">' + (isOpen ? '已展开' : '点击展开') + '</span>' +
      '</button>'
    );
  }

  function renderBody(data, expanded, ai) {
    const tiles = data.tiles || {};
    const summaries = ai || {};
    const open = (expanded || []).filter(function (key) { return tiles[key]; });
    return (
      '<section class="bci-a-summary"><header><span>综合结论</span>' +
        '<em>由已算出的真实数字确定性拼装，不接自由生成</em></header>' +
        '<ul>' + (data.summary || []).map(function (line) {
          return '<li>' + esc(line) + '</li>';
        }).join('') + '</ul>' +
        '<footer>生成时间 ' + esc((data.generated_at || '').replace('T', ' ')) +
          ' · ' + esc(data.model && data.model.price_note || '') + '</footer>' +
      '</section>' +
      '<section class="bci-a-entries" aria-label="选择要查看的结论块">' +
        '<div class="bci-a-entries__head">' +
          '<span>想看哪一块，点卡片展开；可多选叠加</span>' +
          '<em>已选 ' + open.length + '/' + TILE_ORDER.length + '</em>' +
        '</div>' +
        '<div class="bci-a-entries__grid">' + TILE_ORDER.map(function (key) {
          return tiles[key] ? renderEntry(tiles[key], key, open.indexOf(key) >= 0) : '';
        }).join('') + '</div>' +
      '</section>' +
      '<div class="bci-a-stack">' + open.map(function (key) {
        return '<div id="bci-a-panel-' + esc(key) + '">' +
          renderTile(tiles[key], TILE_ORDER.indexOf(key), summaries[key]) + '</div>';
      }).join('') + '</div>' +
      '<p class="bci-a-foot">口径：比例分母为车型定量总样本；题目作答 &lt;10 人不展示比例；' +
        '战败按实际购车车型分行，行内不足 5 人只给人数；深访 3–4 人只做逐人原话；' +
        '口碑为外部评论标签，与问卷满意度不同源。</p>'
    );
  }

  function init(host) {
    if (!host || host.dataset.ready === '1') return;
    host.dataset.ready = '1';
    const state = {
      models: [], current: '', currentLabel: '', data: null, ai: {}, loading: false, expanded: ['profile'],
      agent: { question: '', loading: false, result: null, error: null },
    };

    function syncCurrentLabel() {
      const hit = (state.models || []).filter(function (model) { return model.key === state.current; })[0];
      state.currentLabel = hit ? hit.label : '';
    }

    function paint() {
      host.innerHTML = renderShell(state);
      const body = host.querySelector('[data-bci-analysis-body]');
      if (body && state.data) body.innerHTML = renderBody(state.data, state.expanded, state.ai);
    }

    function fail(error) {
      state.loading = false;
      state.data = null;
      host.innerHTML = renderShell(state) +
        '<div class="bci-a-empty bci-a-empty--error"><b>查询失败</b><p>' +
        esc(error && error.message ? error.message : '接口不可用，请稍后重试。') +
        '</p><button type="button" class="btn btn--ghost" data-bci-analysis-refresh>重试</button></div>';
    }

    function getJSON(url) {
      return fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
        .then(function (response) {
          return response.json().then(function (payload) {
            if (!response.ok || !payload.ok) {
              const message = payload && payload.error && payload.error.message
                ? payload.error.message : 'HTTP ' + response.status;
              throw new Error(message);
            }
            return payload.data;
          });
        });
    }

    function loadModels() {
      return getJSON('/api/bci/analysis/models').then(function (data) {
        state.models = data.models || [];
        state.current = state.current || data.default_model || (state.models[0] && state.models[0].key) || '';
        syncCurrentLabel();
      });
    }

    function loadSummaries() {
      const model = state.current;
      return getJSON('/api/bci/analysis/summaries?model=' + encodeURIComponent(model))
        .then(function (data) {
          if (model !== state.current) return;
          state.ai = (data && data.tiles) || {};
          paint();
        })
        .catch(function () {
          /* AI 结论失败不阻塞主视图，磁贴仍按确定性数字展示 */
        });
    }

    function analyze() {
      if (!state.current) return;
      const model = state.current;
      state.loading = true;
      state.ai = {};
      paint();
      return getJSON('/api/bci/analysis/analyze?model=' + encodeURIComponent(model))
        .then(function (data) {
          if (model !== state.current) return;
          state.loading = false;
          state.data = data;
          paint();
          loadSummaries();
        })
        .catch(fail);
    }

    function runAgent() {
      const question = (state.agent.question || '').trim();
      if (!question) {
        state.agent.error = { code: 'question_required', message: '请先输入要分析的问题。' };
        paint();
        return;
      }
      if (!state.current || state.agent.loading) return;
      const model = state.current;
      state.agent.loading = true;
      state.agent.error = null;
      state.agent.result = null;
      paint();
      fetch('/api/bci/analysis/agent', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ model: model, question: question }),
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            if (!response.ok || !payload.ok) {
              const error = (payload && payload.error) || {};
              const failure = new Error(error.message || ('HTTP ' + response.status));
              failure.code = error.code || ('HTTP ' + response.status);
              throw failure;
            }
            return payload.data;
          });
        })
        .then(function (data) {
          if (model !== state.current) return;
          state.agent.loading = false;
          state.agent.result = data;
          paint();
        })
        .catch(function (error) {
          if (model !== state.current) return;
          state.agent.loading = false;
          state.agent.error = {
            code: error && error.code ? error.code : '',
            message: error && error.message ? error.message : '接口不可用，请稍后重试。',
          };
          paint();
        });
    }

    host.addEventListener('input', function (event) {
      const input = event.target.closest('[data-bci-agent-question]');
      if (!input) return;
      state.agent.question = input.value;
    });

    host.addEventListener('click', function (event) {
      const sample = event.target.closest('[data-bci-agent-sample]');
      if (sample) {
        state.agent.question = sample.getAttribute('data-bci-agent-sample') || '';
        runAgent();
        return;
      }
      if (event.target.closest('[data-bci-agent-run]')) runAgent();
    });

    host.addEventListener('change', function (event) {
      const select = event.target.closest('[data-bci-analysis-model]');
      if (!select) return;
      state.current = select.value;
      syncCurrentLabel();
      state.agent.result = null;
      state.agent.error = null;
      analyze();
    });

    host.addEventListener('click', function (event) {
      const toggle = event.target.closest('[data-bci-analysis-toggle]');
      if (toggle && state.data) {
        const key = toggle.getAttribute('data-bci-analysis-toggle');
        if (!key) return;
        const index = state.expanded.indexOf(key);
        if (index >= 0) {
          state.expanded.splice(index, 1);
        } else {
          state.expanded.push(key);
        }
        paint();
        return;
      }
      if (!event.target.closest('[data-bci-analysis-refresh]')) return;
      if (!state.models.length) {
        loadModels().then(analyze).catch(fail);
      } else {
        analyze();
      }
    });

    paint();
    loadModels().then(analyze).catch(fail);
  }

  window.BciAnalysis = { init: init };
})();
