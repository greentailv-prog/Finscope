// 浏览器侧检索：BM25（中文 char bigram）+ 向量余弦 + 融合排序。
// 全部离线跑，file:// 双击打开也能用；不依赖 fetch、WASM 或任何外部服务。

(function (global) {
  'use strict';

  // 分片文件会写 window.FINSCOPE_SHARDS["<code>"]，必须先把这个对象建出来，
  // 否则第一个分片一注入就抛 TypeError，整页检索全废。
  global.FINSCOPE_SHARDS = global.FINSCOPE_SHARDS || {};

  var K1 = 1.5, B = 0.75, RRF_K = 60;
  var COMPANY_BOOST = 1.8;   // 与 src/search_py.py 保持一致

  // ---- base64 -> 定型数组 ----
  function decodeTyped(b64, Ctor) {
    if (!b64) return new Ctor(0);
    var bin = atob(b64), n = bin.length;
    var buf = new ArrayBuffer(n);
    var bytes = new Uint8Array(buf);
    for (var i = 0; i < n; i++) bytes[i] = bin.charCodeAt(i);
    var usable = Math.floor(n / Ctor.BYTES_PER_ELEMENT);
    return new Ctor(buf, 0, usable);
  }

  // 把分片里的 base64 索引解成可直接查询的结构，只做一次。
  function prepare(shard) {
    if (shard._ready) return shard;
    var b = shard.bm25;
    shard._termHashes = decodeTyped(b.term_hashes_b64, Int32Array);
    shard._df = decodeTyped(b.df_b64, Uint16Array);
    shard._postDoc = decodeTyped(b.post_doc_b64, Uint16Array);
    shard._postTf = decodeTyped(b.post_tf_b64, Uint8Array);
    shard._docLen = decodeTyped(b.doc_len_b64, Uint16Array);
    // 倒排按 token 分组存放，起始位置由 df 前缀和推出，省一个数组
    var n = shard._df.length;
    shard._offset = new Int32Array(n + 1);
    for (var i = 0; i < n; i++) shard._offset[i + 1] = shard._offset[i] + shard._df[i];
    shard._vec = decodeTyped(shard.vec.b64, Int8Array);
    shard._ready = true;
    return shard;
  }

  function lowerBound(arr, x) {
    var lo = 0, hi = arr.length;
    while (lo < hi) {
      var mid = (lo + hi) >>> 1;
      if (arr[mid] < x) lo = mid + 1; else hi = mid;
    }
    return lo;
  }

  // ---- BM25 ----
  function bm25Scores(shard, queryText) {
    prepare(shard);
    var N = shard.bm25.n_docs, avgdl = shard.bm25.avgdl || 1;
    var scores = new Float32Array(N);
    var tf = FinTok.termFreq(queryText);
    var th = shard._termHashes, df = shard._df, off = shard._offset;
    var pd = shard._postDoc, pt = shard._postTf, dl = shard._docLen;
    for (var term in tf) {
      var h = FinTok.fnv1a(term);
      var i = lowerBound(th, h);
      if (i >= th.length || th[i] !== h) continue;
      var dfq = df[i];
      if (!dfq) continue;
      var idf = Math.log(1 + (N - dfq + 0.5) / (dfq + 0.5));
      for (var p = off[i]; p < off[i] + dfq; p++) {
        var d = pd[p], f = pt[p], len = dl[d] || 1;
        scores[d] += idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * len / avgdl));
      }
    }
    return scores;
  }

  // ---- 向量余弦（query 已是单位向量，点积即余弦）----
  function vecScores(shard, qvec) {
    prepare(shard);
    var n = shard.meta.n_chunks, dim = shard.vec.dim, v = shard._vec;
    var out = new Float32Array(n);
    if (!qvec) return out;
    for (var i = 0; i < n; i++) {
      var s = 0, base = i * dim;
      for (var j = 0; j < dim; j++) s += qvec[j] * v[base + j];
      out[i] = s / 127;
    }
    return out;
  }

  function topK(scores, k) {
    var idx = [];
    for (var i = 0; i < scores.length; i++) if (scores[i] > 0) idx.push(i);
    idx.sort(function (a, b) { return scores[b] - scores[a]; });
    return idx.slice(0, k);
  }

  // ---- 融合 ----
  // RRF 对异构分数量纲不敏感（BM25 无上界、余弦在 [-1,1]），默认用它；
  // 另备归一化加权，便于对比两种融合的召回差异。
  function rrfFuse(rankLists, k) {
    k = k || RRF_K;
    var acc = new Map();
    rankLists.forEach(function (list, li) {
      list.forEach(function (doc, rank) {
        var cur = acc.get(doc) || { doc: doc, score: 0, ranks: {} };
        cur.score += 1 / (k + rank + 1);
        cur.ranks[li] = rank;
        acc.set(doc, cur);
      });
    });
    return Array.from(acc.values()).sort(function (a, b) { return b.score - a.score; });
  }

  function minmax(scores, ids) {
    var lo = Infinity, hi = -Infinity;
    ids.forEach(function (i) { if (scores[i] < lo) lo = scores[i]; if (scores[i] > hi) hi = scores[i]; });
    var span = (hi - lo) || 1;
    return function (i) { return (scores[i] - lo) / span; };
  }

  function weightedFuse(bm, vec, ids, alpha) {
    alpha = (alpha == null) ? 0.5 : alpha;
    var nb = minmax(bm, ids), nv = minmax(vec, ids);
    return ids.map(function (i) {
      return { doc: i, score: alpha * nb(i) + (1 - alpha) * nv(i), ranks: {} };
    }).sort(function (a, b) { return b.score - a.score; });
  }

  // ---- 对外：在单个分片上检索 ----
  // qvec 为 null 时退化为 BM25 单路（静态页对任意自由输入的情况）。
  function searchShard(shard, queryText, qvec, opts) {
    opts = opts || {};
    var pool = opts.pool || 200, topN = opts.topN || 8;
    var mode = opts.mode || 'rrf';
    prepare(shard);

    var bm = bm25Scores(shard, queryText);
    var bmIds = topK(bm, pool);
    var vec = null, vecIds = [];
    if (qvec) {
      vec = vecScores(shard, qvec);
      vecIds = topK(vec, pool);
    }

    var fused;
    if (qvec) {
      fused = (mode === 'weighted')
        ? weightedFuse(bm, vec, Array.from(new Set(bmIds.concat(vecIds))), opts.alpha)
        : rrfFuse([bmIds, vecIds]).map(function (r) {
            return { doc: r.doc, score: r.score, ranks: r.ranks };
          });
    } else {
      fused = bmIds.map(function (d, r) { return { doc: d, score: bm[d], ranks: { 0: r } }; });
    }

    var bmRank = new Map(bmIds.map(function (d, r) { return [d, r + 1]; }));
    var vecRank = new Map(vecIds.map(function (d, r) { return [d, r + 1]; }));

    return fused.slice(0, topN).map(function (r, i) {
      var c = shard.chunks[r.doc];
      return {
        chunk_id: c.chunk_id,
        company_code: shard.meta.code,
        company_name: shard.meta.name,
        section: c.section,
        printed_page: c.printed_page,
        pdf_index: c.pdf_index,
        is_table: c.is_table,
        text: c.text,
        fused_rank: i + 1,
        fused_score: r.score,
        bm25_rank: bmRank.get(r.doc) || null,
        bm25_score: bm[r.doc] || 0,
        vec_score: vec ? vec[r.doc] : null,
        vec_rank: vecRank.get(r.doc) || null
      };
    });
  }

  // ---- 对外：跨全部公司检索 ----
  function searchAll(shards, queryText, qvec, opts) {
    opts = opts || {};
    var topN = opts.topN || 8, pool = opts.pool || 200;
    var bmList = [], vecList = [];
    shards.forEach(function (sh, si) {
      prepare(sh);
      var bm = bm25Scores(sh, queryText);
      topK(bm, pool).forEach(function (d) { bmList.push([si, d, bm[d]]); });
      if (qvec) {
        var v = vecScores(sh, qvec);
        topK(v, pool).forEach(function (d) { vecList.push([si, d, v[d]]); });
      }
    });
    bmList.sort(function (a, b) { return b[2] - a[2]; });
    vecList.sort(function (a, b) { return b[2] - a[2]; });

    var rankBm = new Map(), rankVec = new Map();
    bmList.forEach(function (x, i) { rankBm.set(x[0] + ':' + x[1], i + 1); });
    vecList.forEach(function (x, i) { rankVec.set(x[0] + ':' + x[1], i + 1); });

    var acc = new Map();
    function bump(si, d, rank) {
      var key = si + ':' + d;
      var cur = acc.get(key) || { si: si, d: d, score: 0 };
      cur.score += 1 / (RRF_K + rank + 1);
      acc.set(key, cur);
    }
    bmList.forEach(function (x, i) { bump(x[0], x[1], i); });
    if (qvec) vecList.forEach(function (x, i) { bump(x[0], x[1], i); });

    // 问句里点名了公司就给该公司的块加权：八家年报科目名高度同质，
    // 「比亚迪2025年经营活动现金流」里的「比亚迪」只有三个 bigram，
    // 压不住「经营活动产生的现金流量净额」在另外七家上百次的出现。
    for (var bi = 0; bi < shards.length; bi++) {
      if (shards[bi].meta.name && queryText.indexOf(shards[bi].meta.name) >= 0) {
        acc.forEach(function (v) { if (v.si === bi) v.score *= COMPANY_BOOST; });
      }
    }

    return Array.from(acc.values()).sort(function (a, b) { return b.score - a.score; })
      .slice(0, topN).map(function (r, i) {
        var sh = shards[r.si], c = sh.chunks[r.d], key = r.si + ':' + r.d;
        return {
          chunk_id: c.chunk_id, company_code: sh.meta.code, company_name: sh.meta.name,
          section: c.section, printed_page: c.printed_page, pdf_index: c.pdf_index,
          is_table: c.is_table, text: c.text,
          fused_rank: i + 1, fused_score: r.score,
          bm25_rank: rankBm.get(key) || null, vec_rank: rankVec.get(key) || null
        };
      });
  }

  global.FinSearch = {
    K1: K1, B: B, RRF_K: RRF_K,
    prepare: prepare, decodeTyped: decodeTyped,
    bm25Scores: bm25Scores, vecScores: vecScores, topK: topK,
    rrfFuse: rrfFuse, weightedFuse: weightedFuse,
    searchShard: searchShard, searchAll: searchAll
  };
})(window);
