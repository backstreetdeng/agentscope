/* 竞品洞察 ③ 即时分析：自包含渲染，风格沿用现有深蓝 token，不污染全局。 */
(function () {
  'use strict';

  const STATUS_TEXT = {
    ok: '可计算',
    partial: '部分可计算',
    empty: '空态',
    insufficient: '样本不足',
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
    return (
      '<header class="bci-a-metric__head">' +
        '<div class="bci-a-metric__title"><h5>' + esc(metric.label) + '</h5>' +
          statusChip(metric.status) + sampleChip(metric.sample_flag) +
        '</div>' +
        '<div class="bci-a-metric__meta">' + [n, answered].filter(Boolean).join(' · ') + '</div>' +
      '</header>'
    );
  }

  function emptyBox(metric) {
    return (
      '<div class="bci-a-empty" role="note">' +
        '<b>空态 · 不计算</b>' +
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
    function column(title, items, total, tone) {
      return '<div class="bci-a-rep bci-a-rep--' + tone + '"><h6>' + title + ' <span>共 ' + esc(total) + ' 条</span></h6>' +
        (items || []).map(function (item) {
          return '<div class="bci-a-rep__row"><span>' + esc(item.label) + '</span><b>' + esc(item.count) + '</b></div>';
        }).join('') + '</div>';
    }
    return '<div class="bci-a-reps">' + column('正向标签', metric.positive, metric.positive_total, 'ok') +
      column('负向标签', metric.negative, metric.negative_total, 'bad') + '</div>' +
      (metric.note ? '<p class="bci-a-note">' + esc(metric.note) + '</p>' : '');
  }

  function renderMetric(metric) {
    const head = metric.kind === 'empty' ? '' : metricHeader(metric);
    let body = '';
    if (metric.status === 'empty') {
      body = emptyBox(metric);
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
      const ranked = ['attention', 'q3_23', 'q3_24_1'].indexOf(metric.key) >= 0;
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

  function renderTile(tile, index) {
    return (
      '<article class="bci-a-tile">' +
        '<header class="bci-a-tile__head">' +
          '<div class="bci-a-tile__mark">' + ['①', '②', '③', '④'][index] + '</div>' +
          '<div class="bci-a-tile__title"><h4>' + esc(tile.title) + '</h4>' +
            '<p>' + esc(tile.subtitle) + '</p></div>' +
          '<div class="bci-a-tile__chips">' + statusChip(tile.status) +
            (tile.n != null ? '<span class="bci-a-chip">n=' + esc(tile.n) + '</span>' : '') + '</div>' +
        '</header>' +
        (tile.banner ? '<p class="bci-a-banner">' + esc(tile.banner) + '</p>' : '') +
        '<div class="bci-a-metrics">' + (tile.metrics || []).map(renderMetric).join('') + '</div>' +
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
      '<div data-bci-analysis-body>' + (state.loading ? '<div class="bci-a-loading">正在按真实库计算四类磁贴…</div>' : '') + '</div>'
    );
  }

  const TILE_ORDER = ['profile', 'attention', 'winloss', 'satisfaction'];
  const TILE_MARK = { profile: '①', attention: '②', winloss: '③', satisfaction: '④' };
  const TILE_HEAD = {
    profile: '用户画像',
    attention: '购车关注',
    winloss: '选择与放弃',
    satisfaction: '满意度',
  };

  function renderEntry(tile, key, isOpen) {
    return (
      '<button type="button" class="bci-a-entry' + (isOpen ? ' is-open' : '') + '"' +
        ' data-bci-analysis-toggle="' + esc(key) + '" aria-pressed="' + (isOpen ? 'true' : 'false') + '"' +
        ' aria-controls="bci-a-panel-' + esc(key) + '">' +
        '<span class="bci-a-entry__mark">' + TILE_MARK[key] + '</span>' +
        '<span class="bci-a-entry__body">' +
          '<span class="bci-a-entry__title">' + esc(TILE_HEAD[key]) + '</span>' +
          '<span class="bci-a-entry__desc">' + esc(tile.subtitle || '') + '</span>' +
        '</span>' +
        '<span class="bci-a-entry__state">' + (isOpen ? '已展开' : '点击展开') + '</span>' +
      '</button>'
    );
  }

  function renderBody(data, expanded) {
    const tiles = data.tiles || {};
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
        return '<div id="bci-a-panel-' + esc(key) + '">' + renderTile(tiles[key], TILE_ORDER.indexOf(key)) + '</div>';
      }).join('') + '</div>' +
      '<p class="bci-a-foot">口径：比例分母为车型定量总样本；题目作答 &lt;10 人不展示比例；' +
        '深访 3–4 人只做逐人原话；口碑为外部评论标签，与问卷满意度不同源。</p>'
    );
  }

  function init(host) {
    if (!host || host.dataset.ready === '1') return;
    host.dataset.ready = '1';
    const state = { models: [], current: '', data: null, loading: false, expanded: ['profile'] };

    function paint() {
      host.innerHTML = renderShell(state);
      const body = host.querySelector('[data-bci-analysis-body]');
      if (body && state.data) body.innerHTML = renderBody(state.data, state.expanded);
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
      });
    }

    function analyze() {
      if (!state.current) return;
      state.loading = true;
      paint();
      return getJSON('/api/bci/analysis/analyze?model=' + encodeURIComponent(state.current))
        .then(function (data) {
          state.loading = false;
          state.data = data;
          paint();
        })
        .catch(fail);
    }

    host.addEventListener('change', function (event) {
      const select = event.target.closest('[data-bci-analysis-model]');
      if (!select) return;
      state.current = select.value;
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
