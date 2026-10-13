// 中文检索分词与哈希——必须与 src/tokenize_zh.py、src/build_index.py 完全一致。
// 任何一处改动都会让浏览器侧的 BM25 打分与 Python 侧对不上，索引必须重建。
//
// 对应用法：index.html 加载 web/data/tokens_golden.js 后，页面启动时会跑一遍
// 一致性自检，不一致就在页面上报警，而不是悄悄给出错的检索结果。

(function (global) {
  'use strict';

  var TOKENIZER_VERSION = 'zh-char-bigram-v1';

  var CJK_RE = /[一-鿿]+/g;
  var ALNUM_RE = /[a-z0-9]+/g;

  function tokenize(text) {
    var s = (text == null ? '' : String(text)).normalize('NFKC').toLowerCase();
    var out = [];
    var cjk = s.match(CJK_RE) || [];
    for (var i = 0; i < cjk.length; i++) {
      var seg = cjk[i];
      for (var j = 0; j < seg.length; j++) out.push(seg[j]);
      for (var k = 0; k + 1 < seg.length; k++) out.push(seg.slice(k, k + 2));
    }
    var alnum = s.match(ALNUM_RE) || [];
    for (var m = 0; m < alnum.length; m++) out.push(alnum[m]);
    return out;
  }

  // FNV-1a 32 位，按 UTF-16 码元；返回有符号 int32，与 Python 的 as_i32 对齐。
  function fnv1a(token) {
    var h = 2166136261;
    for (var i = 0; i < token.length; i++) {
      h ^= token.charCodeAt(i);
      h = Math.imul(h, 16777619) >>> 0;
    }
    return h | 0;
  }

  function termFreq(text) {
    var toks = tokenize(text), tf = Object.create(null);
    for (var i = 0; i < toks.length; i++) {
      tf[toks[i]] = (tf[toks[i]] || 0) + 1;
    }
    return tf;
  }

  // 与 golden 用例比对；返回不一致的条目，供页面启动自检。
  function checkGolden(golden) {
    if (!golden || !golden.cases) return { ok: false, reason: '缺少 golden 用例' };
    var bad = [];
    for (var i = 0; i < golden.cases.length; i++) {
      var c = golden.cases[i];
      var got = tokenize(c.input).join('\u0001');
      if (got !== c.tokens.join('\u0001')) {
        bad.push({ input: c.input, expected: c.tokens, got: tokenize(c.input) });
      }
    }
    return { ok: bad.length === 0, version: TOKENIZER_VERSION, bad: bad };
  }

  global.FinTok = {
    version: TOKENIZER_VERSION,
    tokenize: tokenize,
    fnv1a: fnv1a,
    termFreq: termFreq,
    checkGolden: checkGolden
  };
})(window);
