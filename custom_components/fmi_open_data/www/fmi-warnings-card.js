/*! fmi-warnings-card 4.2.0 | MIT License */
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __decorateClass = (decorators, target, key, kind) => {
  var result = kind > 1 ? void 0 : kind ? __getOwnPropDesc(target, key) : target;
  for (var i7 = decorators.length - 1, decorator; i7 >= 0; i7--)
    if (decorator = decorators[i7])
      result = (kind ? decorator(target, key, result) : decorator(result)) || result;
  if (kind && result) __defProp(target, key, result);
  return result;
};

// node_modules/@lit/reactive-element/css-tag.js
var t = globalThis;
var e = t.ShadowRoot && (void 0 === t.ShadyCSS || t.ShadyCSS.nativeShadow) && "adoptedStyleSheets" in Document.prototype && "replace" in CSSStyleSheet.prototype;
var s = /* @__PURE__ */ Symbol();
var o = /* @__PURE__ */ new WeakMap();
var n = class {
  constructor(t5, e6, o6) {
    if (this._$cssResult$ = true, o6 !== s) throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");
    this.cssText = t5, this.t = e6;
  }
  get styleSheet() {
    let t5 = this.o;
    const s5 = this.t;
    if (e && void 0 === t5) {
      const e6 = void 0 !== s5 && 1 === s5.length;
      e6 && (t5 = o.get(s5)), void 0 === t5 && ((this.o = t5 = new CSSStyleSheet()).replaceSync(this.cssText), e6 && o.set(s5, t5));
    }
    return t5;
  }
  toString() {
    return this.cssText;
  }
};
var r = (t5) => new n("string" == typeof t5 ? t5 : t5 + "", void 0, s);
var i = (t5, ...e6) => {
  const o6 = 1 === t5.length ? t5[0] : e6.reduce((e7, s5, o7) => e7 + ((t6) => {
    if (true === t6._$cssResult$) return t6.cssText;
    if ("number" == typeof t6) return t6;
    throw Error("Value passed to 'css' function must be a 'css' function result: " + t6 + ". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.");
  })(s5) + t5[o7 + 1], t5[0]);
  return new n(o6, t5, s);
};
var S = (s5, o6) => {
  if (e) s5.adoptedStyleSheets = o6.map((t5) => t5 instanceof CSSStyleSheet ? t5 : t5.styleSheet);
  else for (const e6 of o6) {
    const o7 = document.createElement("style"), n5 = t.litNonce;
    void 0 !== n5 && o7.setAttribute("nonce", n5), o7.textContent = e6.cssText, s5.appendChild(o7);
  }
};
var c = e ? (t5) => t5 : (t5) => t5 instanceof CSSStyleSheet ? ((t6) => {
  let e6 = "";
  for (const s5 of t6.cssRules) e6 += s5.cssText;
  return r(e6);
})(t5) : t5;

// node_modules/@lit/reactive-element/reactive-element.js
var { is: i2, defineProperty: e2, getOwnPropertyDescriptor: h, getOwnPropertyNames: r2, getOwnPropertySymbols: o2, getPrototypeOf: n2 } = Object;
var a = globalThis;
var c2 = a.trustedTypes;
var l = c2 ? c2.emptyScript : "";
var p = a.reactiveElementPolyfillSupport;
var d = (t5, s5) => t5;
var u = { toAttribute(t5, s5) {
  switch (s5) {
    case Boolean:
      t5 = t5 ? l : null;
      break;
    case Object:
    case Array:
      t5 = null == t5 ? t5 : JSON.stringify(t5);
  }
  return t5;
}, fromAttribute(t5, s5) {
  let i7 = t5;
  switch (s5) {
    case Boolean:
      i7 = null !== t5;
      break;
    case Number:
      i7 = null === t5 ? null : Number(t5);
      break;
    case Object:
    case Array:
      try {
        i7 = JSON.parse(t5);
      } catch (t6) {
        i7 = null;
      }
  }
  return i7;
} };
var f = (t5, s5) => !i2(t5, s5);
var b = { attribute: true, type: String, converter: u, reflect: false, useDefault: false, hasChanged: f };
Symbol.metadata ?? (Symbol.metadata = /* @__PURE__ */ Symbol("metadata")), a.litPropertyMetadata ?? (a.litPropertyMetadata = /* @__PURE__ */ new WeakMap());
var y = class extends HTMLElement {
  static addInitializer(t5) {
    this._$Ei(), (this.l ?? (this.l = [])).push(t5);
  }
  static get observedAttributes() {
    return this.finalize(), this._$Eh && [...this._$Eh.keys()];
  }
  static createProperty(t5, s5 = b) {
    if (s5.state && (s5.attribute = false), this._$Ei(), this.prototype.hasOwnProperty(t5) && ((s5 = Object.create(s5)).wrapped = true), this.elementProperties.set(t5, s5), !s5.noAccessor) {
      const i7 = /* @__PURE__ */ Symbol(), h4 = this.getPropertyDescriptor(t5, i7, s5);
      void 0 !== h4 && e2(this.prototype, t5, h4);
    }
  }
  static getPropertyDescriptor(t5, s5, i7) {
    const { get: e6, set: r6 } = h(this.prototype, t5) ?? { get() {
      return this[s5];
    }, set(t6) {
      this[s5] = t6;
    } };
    return { get: e6, set(s6) {
      const h4 = e6?.call(this);
      r6?.call(this, s6), this.requestUpdate(t5, h4, i7);
    }, configurable: true, enumerable: true };
  }
  static getPropertyOptions(t5) {
    return this.elementProperties.get(t5) ?? b;
  }
  static _$Ei() {
    if (this.hasOwnProperty(d("elementProperties"))) return;
    const t5 = n2(this);
    t5.finalize(), void 0 !== t5.l && (this.l = [...t5.l]), this.elementProperties = new Map(t5.elementProperties);
  }
  static finalize() {
    if (this.hasOwnProperty(d("finalized"))) return;
    if (this.finalized = true, this._$Ei(), this.hasOwnProperty(d("properties"))) {
      const t6 = this.properties, s5 = [...r2(t6), ...o2(t6)];
      for (const i7 of s5) this.createProperty(i7, t6[i7]);
    }
    const t5 = this[Symbol.metadata];
    if (null !== t5) {
      const s5 = litPropertyMetadata.get(t5);
      if (void 0 !== s5) for (const [t6, i7] of s5) this.elementProperties.set(t6, i7);
    }
    this._$Eh = /* @__PURE__ */ new Map();
    for (const [t6, s5] of this.elementProperties) {
      const i7 = this._$Eu(t6, s5);
      void 0 !== i7 && this._$Eh.set(i7, t6);
    }
    this.elementStyles = this.finalizeStyles(this.styles);
  }
  static finalizeStyles(s5) {
    const i7 = [];
    if (Array.isArray(s5)) {
      const e6 = new Set(s5.flat(1 / 0).reverse());
      for (const s6 of e6) i7.unshift(c(s6));
    } else void 0 !== s5 && i7.push(c(s5));
    return i7;
  }
  static _$Eu(t5, s5) {
    const i7 = s5.attribute;
    return false === i7 ? void 0 : "string" == typeof i7 ? i7 : "string" == typeof t5 ? t5.toLowerCase() : void 0;
  }
  constructor() {
    super(), this._$Ep = void 0, this.isUpdatePending = false, this.hasUpdated = false, this._$Em = null, this._$Ev();
  }
  _$Ev() {
    this._$ES = new Promise((t5) => this.enableUpdating = t5), this._$AL = /* @__PURE__ */ new Map(), this._$E_(), this.requestUpdate(), this.constructor.l?.forEach((t5) => t5(this));
  }
  addController(t5) {
    (this._$EO ?? (this._$EO = /* @__PURE__ */ new Set())).add(t5), void 0 !== this.renderRoot && this.isConnected && t5.hostConnected?.();
  }
  removeController(t5) {
    this._$EO?.delete(t5);
  }
  _$E_() {
    const t5 = /* @__PURE__ */ new Map(), s5 = this.constructor.elementProperties;
    for (const i7 of s5.keys()) this.hasOwnProperty(i7) && (t5.set(i7, this[i7]), delete this[i7]);
    t5.size > 0 && (this._$Ep = t5);
  }
  createRenderRoot() {
    const t5 = this.shadowRoot ?? this.attachShadow(this.constructor.shadowRootOptions);
    return S(t5, this.constructor.elementStyles), t5;
  }
  connectedCallback() {
    this.renderRoot ?? (this.renderRoot = this.createRenderRoot()), this.enableUpdating(true), this._$EO?.forEach((t5) => t5.hostConnected?.());
  }
  enableUpdating(t5) {
  }
  disconnectedCallback() {
    this._$EO?.forEach((t5) => t5.hostDisconnected?.());
  }
  attributeChangedCallback(t5, s5, i7) {
    this._$AK(t5, i7);
  }
  _$ET(t5, s5) {
    const i7 = this.constructor.elementProperties.get(t5), e6 = this.constructor._$Eu(t5, i7);
    if (void 0 !== e6 && true === i7.reflect) {
      const h4 = (void 0 !== i7.converter?.toAttribute ? i7.converter : u).toAttribute(s5, i7.type);
      this._$Em = t5, null == h4 ? this.removeAttribute(e6) : this.setAttribute(e6, h4), this._$Em = null;
    }
  }
  _$AK(t5, s5) {
    const i7 = this.constructor, e6 = i7._$Eh.get(t5);
    if (void 0 !== e6 && this._$Em !== e6) {
      const t6 = i7.getPropertyOptions(e6), h4 = "function" == typeof t6.converter ? { fromAttribute: t6.converter } : void 0 !== t6.converter?.fromAttribute ? t6.converter : u;
      this._$Em = e6;
      const r6 = h4.fromAttribute(s5, t6.type);
      this[e6] = r6 ?? this._$Ej?.get(e6) ?? r6, this._$Em = null;
    }
  }
  requestUpdate(t5, s5, i7, e6 = false, h4) {
    if (void 0 !== t5) {
      const r6 = this.constructor;
      if (false === e6 && (h4 = this[t5]), i7 ?? (i7 = r6.getPropertyOptions(t5)), !((i7.hasChanged ?? f)(h4, s5) || i7.useDefault && i7.reflect && h4 === this._$Ej?.get(t5) && !this.hasAttribute(r6._$Eu(t5, i7)))) return;
      this.C(t5, s5, i7);
    }
    false === this.isUpdatePending && (this._$ES = this._$EP());
  }
  C(t5, s5, { useDefault: i7, reflect: e6, wrapped: h4 }, r6) {
    i7 && !(this._$Ej ?? (this._$Ej = /* @__PURE__ */ new Map())).has(t5) && (this._$Ej.set(t5, r6 ?? s5 ?? this[t5]), true !== h4 || void 0 !== r6) || (this._$AL.has(t5) || (this.hasUpdated || i7 || (s5 = void 0), this._$AL.set(t5, s5)), true === e6 && this._$Em !== t5 && (this._$Eq ?? (this._$Eq = /* @__PURE__ */ new Set())).add(t5));
  }
  async _$EP() {
    this.isUpdatePending = true;
    try {
      await this._$ES;
    } catch (t6) {
      Promise.reject(t6);
    }
    const t5 = this.scheduleUpdate();
    return null != t5 && await t5, !this.isUpdatePending;
  }
  scheduleUpdate() {
    return this.performUpdate();
  }
  performUpdate() {
    if (!this.isUpdatePending) return;
    if (!this.hasUpdated) {
      if (this.renderRoot ?? (this.renderRoot = this.createRenderRoot()), this._$Ep) {
        for (const [t7, s6] of this._$Ep) this[t7] = s6;
        this._$Ep = void 0;
      }
      const t6 = this.constructor.elementProperties;
      if (t6.size > 0) for (const [s6, i7] of t6) {
        const { wrapped: t7 } = i7, e6 = this[s6];
        true !== t7 || this._$AL.has(s6) || void 0 === e6 || this.C(s6, void 0, i7, e6);
      }
    }
    let t5 = false;
    const s5 = this._$AL;
    try {
      t5 = this.shouldUpdate(s5), t5 ? (this.willUpdate(s5), this._$EO?.forEach((t6) => t6.hostUpdate?.()), this.update(s5)) : this._$EM();
    } catch (s6) {
      throw t5 = false, this._$EM(), s6;
    }
    t5 && this._$AE(s5);
  }
  willUpdate(t5) {
  }
  _$AE(t5) {
    this._$EO?.forEach((t6) => t6.hostUpdated?.()), this.hasUpdated || (this.hasUpdated = true, this.firstUpdated(t5)), this.updated(t5);
  }
  _$EM() {
    this._$AL = /* @__PURE__ */ new Map(), this.isUpdatePending = false;
  }
  get updateComplete() {
    return this.getUpdateComplete();
  }
  getUpdateComplete() {
    return this._$ES;
  }
  shouldUpdate(t5) {
    return true;
  }
  update(t5) {
    this._$Eq && (this._$Eq = this._$Eq.forEach((t6) => this._$ET(t6, this[t6]))), this._$EM();
  }
  updated(t5) {
  }
  firstUpdated(t5) {
  }
};
y.elementStyles = [], y.shadowRootOptions = { mode: "open" }, y[d("elementProperties")] = /* @__PURE__ */ new Map(), y[d("finalized")] = /* @__PURE__ */ new Map(), p?.({ ReactiveElement: y }), (a.reactiveElementVersions ?? (a.reactiveElementVersions = [])).push("2.1.2");

// node_modules/lit-html/lit-html.js
var t2 = globalThis;
var i3 = (t5) => t5;
var s2 = t2.trustedTypes;
var e3 = s2 ? s2.createPolicy("lit-html", { createHTML: (t5) => t5 }) : void 0;
var h2 = "$lit$";
var o3 = `lit$${Math.random().toFixed(9).slice(2)}$`;
var n3 = "?" + o3;
var r3 = `<${n3}>`;
var l2 = document;
var c3 = () => l2.createComment("");
var a2 = (t5) => null === t5 || "object" != typeof t5 && "function" != typeof t5;
var u2 = Array.isArray;
var d2 = (t5) => u2(t5) || "function" == typeof t5?.[Symbol.iterator];
var f2 = "[ 	\n\f\r]";
var v = /<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g;
var _ = /-->/g;
var m = />/g;
var p2 = RegExp(`>|${f2}(?:([^\\s"'>=/]+)(${f2}*=${f2}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`, "g");
var g = /'/g;
var $ = /"/g;
var y2 = /^(?:script|style|textarea|title)$/i;
var x = (t5) => (i7, ...s5) => ({ _$litType$: t5, strings: i7, values: s5 });
var b2 = x(1);
var w = x(2);
var T = x(3);
var E = /* @__PURE__ */ Symbol.for("lit-noChange");
var A = /* @__PURE__ */ Symbol.for("lit-nothing");
var C = /* @__PURE__ */ new WeakMap();
var P = l2.createTreeWalker(l2, 129);
function V(t5, i7) {
  if (!u2(t5) || !t5.hasOwnProperty("raw")) throw Error("invalid template strings array");
  return void 0 !== e3 ? e3.createHTML(i7) : i7;
}
var N = (t5, i7) => {
  const s5 = t5.length - 1, e6 = [];
  let n5, l3 = 2 === i7 ? "<svg>" : 3 === i7 ? "<math>" : "", c5 = v;
  for (let i8 = 0; i8 < s5; i8++) {
    const s6 = t5[i8];
    let a3, u5, d3 = -1, f3 = 0;
    for (; f3 < s6.length && (c5.lastIndex = f3, u5 = c5.exec(s6), null !== u5); ) f3 = c5.lastIndex, c5 === v ? "!--" === u5[1] ? c5 = _ : void 0 !== u5[1] ? c5 = m : void 0 !== u5[2] ? (y2.test(u5[2]) && (n5 = RegExp("</" + u5[2], "g")), c5 = p2) : void 0 !== u5[3] && (c5 = p2) : c5 === p2 ? ">" === u5[0] ? (c5 = n5 ?? v, d3 = -1) : void 0 === u5[1] ? d3 = -2 : (d3 = c5.lastIndex - u5[2].length, a3 = u5[1], c5 = void 0 === u5[3] ? p2 : '"' === u5[3] ? $ : g) : c5 === $ || c5 === g ? c5 = p2 : c5 === _ || c5 === m ? c5 = v : (c5 = p2, n5 = void 0);
    const x2 = c5 === p2 && t5[i8 + 1].startsWith("/>") ? " " : "";
    l3 += c5 === v ? s6 + r3 : d3 >= 0 ? (e6.push(a3), s6.slice(0, d3) + h2 + s6.slice(d3) + o3 + x2) : s6 + o3 + (-2 === d3 ? i8 : x2);
  }
  return [V(t5, l3 + (t5[s5] || "<?>") + (2 === i7 ? "</svg>" : 3 === i7 ? "</math>" : "")), e6];
};
var S2 = class _S {
  constructor({ strings: t5, _$litType$: i7 }, e6) {
    let r6;
    this.parts = [];
    let l3 = 0, a3 = 0;
    const u5 = t5.length - 1, d3 = this.parts, [f3, v3] = N(t5, i7);
    if (this.el = _S.createElement(f3, e6), P.currentNode = this.el.content, 2 === i7 || 3 === i7) {
      const t6 = this.el.content.firstChild;
      t6.replaceWith(...t6.childNodes);
    }
    for (; null !== (r6 = P.nextNode()) && d3.length < u5; ) {
      if (1 === r6.nodeType) {
        if (r6.hasAttributes()) for (const t6 of r6.getAttributeNames()) if (t6.endsWith(h2)) {
          const i8 = v3[a3++], s5 = r6.getAttribute(t6).split(o3), e7 = /([.?@])?(.*)/.exec(i8);
          d3.push({ type: 1, index: l3, name: e7[2], strings: s5, ctor: "." === e7[1] ? I : "?" === e7[1] ? L : "@" === e7[1] ? z : H }), r6.removeAttribute(t6);
        } else t6.startsWith(o3) && (d3.push({ type: 6, index: l3 }), r6.removeAttribute(t6));
        if (y2.test(r6.tagName)) {
          const t6 = r6.textContent.split(o3), i8 = t6.length - 1;
          if (i8 > 0) {
            r6.textContent = s2 ? s2.emptyScript : "";
            for (let s5 = 0; s5 < i8; s5++) r6.append(t6[s5], c3()), P.nextNode(), d3.push({ type: 2, index: ++l3 });
            r6.append(t6[i8], c3());
          }
        }
      } else if (8 === r6.nodeType) if (r6.data === n3) d3.push({ type: 2, index: l3 });
      else {
        let t6 = -1;
        for (; -1 !== (t6 = r6.data.indexOf(o3, t6 + 1)); ) d3.push({ type: 7, index: l3 }), t6 += o3.length - 1;
      }
      l3++;
    }
  }
  static createElement(t5, i7) {
    const s5 = l2.createElement("template");
    return s5.innerHTML = t5, s5;
  }
};
function M(t5, i7, s5 = t5, e6) {
  if (i7 === E) return i7;
  let h4 = void 0 !== e6 ? s5._$Co?.[e6] : s5._$Cl;
  const o6 = a2(i7) ? void 0 : i7._$litDirective$;
  return h4?.constructor !== o6 && (h4?._$AO?.(false), void 0 === o6 ? h4 = void 0 : (h4 = new o6(t5), h4._$AT(t5, s5, e6)), void 0 !== e6 ? (s5._$Co ?? (s5._$Co = []))[e6] = h4 : s5._$Cl = h4), void 0 !== h4 && (i7 = M(t5, h4._$AS(t5, i7.values), h4, e6)), i7;
}
var R = class {
  constructor(t5, i7) {
    this._$AV = [], this._$AN = void 0, this._$AD = t5, this._$AM = i7;
  }
  get parentNode() {
    return this._$AM.parentNode;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  u(t5) {
    const { el: { content: i7 }, parts: s5 } = this._$AD, e6 = (t5?.creationScope ?? l2).importNode(i7, true);
    P.currentNode = e6;
    let h4 = P.nextNode(), o6 = 0, n5 = 0, r6 = s5[0];
    for (; void 0 !== r6; ) {
      if (o6 === r6.index) {
        let i8;
        2 === r6.type ? i8 = new k(h4, h4.nextSibling, this, t5) : 1 === r6.type ? i8 = new r6.ctor(h4, r6.name, r6.strings, this, t5) : 6 === r6.type && (i8 = new Z(h4, this, t5)), this._$AV.push(i8), r6 = s5[++n5];
      }
      o6 !== r6?.index && (h4 = P.nextNode(), o6++);
    }
    return P.currentNode = l2, e6;
  }
  p(t5) {
    let i7 = 0;
    for (const s5 of this._$AV) void 0 !== s5 && (void 0 !== s5.strings ? (s5._$AI(t5, s5, i7), i7 += s5.strings.length - 2) : s5._$AI(t5[i7])), i7++;
  }
};
var k = class _k {
  get _$AU() {
    return this._$AM?._$AU ?? this._$Cv;
  }
  constructor(t5, i7, s5, e6) {
    this.type = 2, this._$AH = A, this._$AN = void 0, this._$AA = t5, this._$AB = i7, this._$AM = s5, this.options = e6, this._$Cv = e6?.isConnected ?? true;
  }
  get parentNode() {
    let t5 = this._$AA.parentNode;
    const i7 = this._$AM;
    return void 0 !== i7 && 11 === t5?.nodeType && (t5 = i7.parentNode), t5;
  }
  get startNode() {
    return this._$AA;
  }
  get endNode() {
    return this._$AB;
  }
  _$AI(t5, i7 = this) {
    t5 = M(this, t5, i7), a2(t5) ? t5 === A || null == t5 || "" === t5 ? (this._$AH !== A && this._$AR(), this._$AH = A) : t5 !== this._$AH && t5 !== E && this._(t5) : void 0 !== t5._$litType$ ? this.$(t5) : void 0 !== t5.nodeType ? this.T(t5) : d2(t5) ? this.k(t5) : this._(t5);
  }
  O(t5) {
    return this._$AA.parentNode.insertBefore(t5, this._$AB);
  }
  T(t5) {
    this._$AH !== t5 && (this._$AR(), this._$AH = this.O(t5));
  }
  _(t5) {
    this._$AH !== A && a2(this._$AH) ? this._$AA.nextSibling.data = t5 : this.T(l2.createTextNode(t5)), this._$AH = t5;
  }
  $(t5) {
    const { values: i7, _$litType$: s5 } = t5, e6 = "number" == typeof s5 ? this._$AC(t5) : (void 0 === s5.el && (s5.el = S2.createElement(V(s5.h, s5.h[0]), this.options)), s5);
    if (this._$AH?._$AD === e6) this._$AH.p(i7);
    else {
      const t6 = new R(e6, this), s6 = t6.u(this.options);
      t6.p(i7), this.T(s6), this._$AH = t6;
    }
  }
  _$AC(t5) {
    let i7 = C.get(t5.strings);
    return void 0 === i7 && C.set(t5.strings, i7 = new S2(t5)), i7;
  }
  k(t5) {
    u2(this._$AH) || (this._$AH = [], this._$AR());
    const i7 = this._$AH;
    let s5, e6 = 0;
    for (const h4 of t5) e6 === i7.length ? i7.push(s5 = new _k(this.O(c3()), this.O(c3()), this, this.options)) : s5 = i7[e6], s5._$AI(h4), e6++;
    e6 < i7.length && (this._$AR(s5 && s5._$AB.nextSibling, e6), i7.length = e6);
  }
  _$AR(t5 = this._$AA.nextSibling, s5) {
    for (this._$AP?.(false, true, s5); t5 !== this._$AB; ) {
      const s6 = i3(t5).nextSibling;
      i3(t5).remove(), t5 = s6;
    }
  }
  setConnected(t5) {
    void 0 === this._$AM && (this._$Cv = t5, this._$AP?.(t5));
  }
};
var H = class {
  get tagName() {
    return this.element.tagName;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  constructor(t5, i7, s5, e6, h4) {
    this.type = 1, this._$AH = A, this._$AN = void 0, this.element = t5, this.name = i7, this._$AM = e6, this.options = h4, s5.length > 2 || "" !== s5[0] || "" !== s5[1] ? (this._$AH = Array(s5.length - 1).fill(new String()), this.strings = s5) : this._$AH = A;
  }
  _$AI(t5, i7 = this, s5, e6) {
    const h4 = this.strings;
    let o6 = false;
    if (void 0 === h4) t5 = M(this, t5, i7, 0), o6 = !a2(t5) || t5 !== this._$AH && t5 !== E, o6 && (this._$AH = t5);
    else {
      const e7 = t5;
      let n5, r6;
      for (t5 = h4[0], n5 = 0; n5 < h4.length - 1; n5++) r6 = M(this, e7[s5 + n5], i7, n5), r6 === E && (r6 = this._$AH[n5]), o6 || (o6 = !a2(r6) || r6 !== this._$AH[n5]), r6 === A ? t5 = A : t5 !== A && (t5 += (r6 ?? "") + h4[n5 + 1]), this._$AH[n5] = r6;
    }
    o6 && !e6 && this.j(t5);
  }
  j(t5) {
    t5 === A ? this.element.removeAttribute(this.name) : this.element.setAttribute(this.name, t5 ?? "");
  }
};
var I = class extends H {
  constructor() {
    super(...arguments), this.type = 3;
  }
  j(t5) {
    this.element[this.name] = t5 === A ? void 0 : t5;
  }
};
var L = class extends H {
  constructor() {
    super(...arguments), this.type = 4;
  }
  j(t5) {
    this.element.toggleAttribute(this.name, !!t5 && t5 !== A);
  }
};
var z = class extends H {
  constructor(t5, i7, s5, e6, h4) {
    super(t5, i7, s5, e6, h4), this.type = 5;
  }
  _$AI(t5, i7 = this) {
    if ((t5 = M(this, t5, i7, 0) ?? A) === E) return;
    const s5 = this._$AH, e6 = t5 === A && s5 !== A || t5.capture !== s5.capture || t5.once !== s5.once || t5.passive !== s5.passive, h4 = t5 !== A && (s5 === A || e6);
    e6 && this.element.removeEventListener(this.name, this, s5), h4 && this.element.addEventListener(this.name, this, t5), this._$AH = t5;
  }
  handleEvent(t5) {
    "function" == typeof this._$AH ? this._$AH.call(this.options?.host ?? this.element, t5) : this._$AH.handleEvent(t5);
  }
};
var Z = class {
  constructor(t5, i7, s5) {
    this.element = t5, this.type = 6, this._$AN = void 0, this._$AM = i7, this.options = s5;
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AI(t5) {
    M(this, t5);
  }
};
var j = { M: h2, P: o3, A: n3, C: 1, L: N, R, D: d2, V: M, I: k, H, N: L, U: z, B: I, F: Z };
var B = t2.litHtmlPolyfillSupport;
B?.(S2, k), (t2.litHtmlVersions ?? (t2.litHtmlVersions = [])).push("3.3.3");
var D = (t5, i7, s5) => {
  const e6 = s5?.renderBefore ?? i7;
  let h4 = e6._$litPart$;
  if (void 0 === h4) {
    const t6 = s5?.renderBefore ?? null;
    e6._$litPart$ = h4 = new k(i7.insertBefore(c3(), t6), t6, void 0, s5 ?? {});
  }
  return h4._$AI(t5), h4;
};

// node_modules/lit-element/lit-element.js
var s3 = globalThis;
var i4 = class extends y {
  constructor() {
    super(...arguments), this.renderOptions = { host: this }, this._$Do = void 0;
  }
  createRenderRoot() {
    var _a;
    const t5 = super.createRenderRoot();
    return (_a = this.renderOptions).renderBefore ?? (_a.renderBefore = t5.firstChild), t5;
  }
  update(t5) {
    const r6 = this.render();
    this.hasUpdated || (this.renderOptions.isConnected = this.isConnected), super.update(t5), this._$Do = D(r6, this.renderRoot, this.renderOptions);
  }
  connectedCallback() {
    super.connectedCallback(), this._$Do?.setConnected(true);
  }
  disconnectedCallback() {
    super.disconnectedCallback(), this._$Do?.setConnected(false);
  }
  render() {
    return E;
  }
};
i4._$litElement$ = true, i4["finalized"] = true, s3.litElementHydrateSupport?.({ LitElement: i4 });
var o4 = s3.litElementPolyfillSupport;
o4?.({ LitElement: i4 });
(s3.litElementVersions ?? (s3.litElementVersions = [])).push("4.2.2");

// node_modules/@lit/reactive-element/decorators/property.js
var o5 = { attribute: true, type: String, converter: u, reflect: false, hasChanged: f };
var r4 = (t5 = o5, e6, r6) => {
  const { kind: n5, metadata: i7 } = r6;
  let s5 = globalThis.litPropertyMetadata.get(i7);
  if (void 0 === s5 && globalThis.litPropertyMetadata.set(i7, s5 = /* @__PURE__ */ new Map()), "setter" === n5 && ((t5 = Object.create(t5)).wrapped = true), s5.set(r6.name, t5), "accessor" === n5) {
    const { name: o6 } = r6;
    return { set(r7) {
      const n6 = e6.get.call(this);
      e6.set.call(this, r7), this.requestUpdate(o6, n6, t5, true, r7);
    }, init(e7) {
      return void 0 !== e7 && this.C(o6, void 0, t5, e7), e7;
    } };
  }
  if ("setter" === n5) {
    const { name: o6 } = r6;
    return function(r7) {
      const n6 = this[o6];
      e6.call(this, r7), this.requestUpdate(o6, n6, t5, true, r7);
    };
  }
  throw Error("Unsupported decorator location: " + n5);
};
function n4(t5) {
  return (e6, o6) => "object" == typeof o6 ? r4(t5, e6, o6) : ((t6, e7, o7) => {
    const r6 = e7.hasOwnProperty(o7);
    return e7.constructor.createProperty(o7, t6), r6 ? Object.getOwnPropertyDescriptor(e7, o7) : void 0;
  })(t5, e6, o6);
}

// node_modules/@lit/reactive-element/decorators/state.js
function r5(r6) {
  return n4({ ...r6, state: true, attribute: false });
}

// node_modules/lit-html/directive.js
var t3 = { ATTRIBUTE: 1, CHILD: 2, PROPERTY: 3, BOOLEAN_ATTRIBUTE: 4, EVENT: 5, ELEMENT: 6 };
var e5 = (t5) => (...e6) => ({ _$litDirective$: t5, values: e6 });
var i5 = class {
  constructor(t5) {
  }
  get _$AU() {
    return this._$AM._$AU;
  }
  _$AT(t5, e6, i7) {
    this._$Ct = t5, this._$AM = e6, this._$Ci = i7;
  }
  _$AS(t5, e6) {
    return this.update(t5, e6);
  }
  update(t5, e6) {
    return this.render(...e6);
  }
};

// node_modules/lit-html/directive-helpers.js
var { I: t4 } = j;
var i6 = (o6) => o6;
var s4 = () => document.createComment("");
var v2 = (o6, n5, e6) => {
  const l3 = o6._$AA.parentNode, d3 = void 0 === n5 ? o6._$AB : n5._$AA;
  if (void 0 === e6) {
    const i7 = l3.insertBefore(s4(), d3), n6 = l3.insertBefore(s4(), d3);
    e6 = new t4(i7, n6, o6, o6.options);
  } else {
    const t5 = e6._$AB.nextSibling, n6 = e6._$AM, c5 = n6 !== o6;
    if (c5) {
      let t6;
      e6._$AQ?.(o6), e6._$AM = o6, void 0 !== e6._$AP && (t6 = o6._$AU) !== n6._$AU && e6._$AP(t6);
    }
    if (t5 !== d3 || c5) {
      let o7 = e6._$AA;
      for (; o7 !== t5; ) {
        const t6 = i6(o7).nextSibling;
        i6(l3).insertBefore(o7, d3), o7 = t6;
      }
    }
  }
  return e6;
};
var u3 = (o6, t5, i7 = o6) => (o6._$AI(t5, i7), o6);
var m2 = {};
var p3 = (o6, t5 = m2) => o6._$AH = t5;
var M2 = (o6) => o6._$AH;
var h3 = (o6) => {
  o6._$AR(), o6._$AA.remove();
};

// node_modules/lit-html/directives/repeat.js
var u4 = (e6, s5, t5) => {
  const r6 = /* @__PURE__ */ new Map();
  for (let l3 = s5; l3 <= t5; l3++) r6.set(e6[l3], l3);
  return r6;
};
var c4 = e5(class extends i5 {
  constructor(e6) {
    if (super(e6), e6.type !== t3.CHILD) throw Error("repeat() can only be used in text expressions");
  }
  dt(e6, s5, t5) {
    let r6;
    void 0 === t5 ? t5 = s5 : void 0 !== s5 && (r6 = s5);
    const l3 = [], o6 = [];
    let i7 = 0;
    for (const s6 of e6) l3[i7] = r6 ? r6(s6, i7) : i7, o6[i7] = t5(s6, i7), i7++;
    return { values: o6, keys: l3 };
  }
  render(e6, s5, t5) {
    return this.dt(e6, s5, t5).values;
  }
  update(s5, [t5, r6, c5]) {
    const d3 = M2(s5), { values: p4, keys: a3 } = this.dt(t5, r6, c5);
    if (!Array.isArray(d3)) return this.ut = a3, p4;
    const h4 = this.ut ?? (this.ut = []), v3 = [];
    let m3, y3, x2 = 0, j2 = d3.length - 1, k2 = 0, w2 = p4.length - 1;
    for (; x2 <= j2 && k2 <= w2; ) if (null === d3[x2]) x2++;
    else if (null === d3[j2]) j2--;
    else if (h4[x2] === a3[k2]) v3[k2] = u3(d3[x2], p4[k2]), x2++, k2++;
    else if (h4[j2] === a3[w2]) v3[w2] = u3(d3[j2], p4[w2]), j2--, w2--;
    else if (h4[x2] === a3[w2]) v3[w2] = u3(d3[x2], p4[w2]), v2(s5, v3[w2 + 1], d3[x2]), x2++, w2--;
    else if (h4[j2] === a3[k2]) v3[k2] = u3(d3[j2], p4[k2]), v2(s5, d3[x2], d3[j2]), j2--, k2++;
    else if (void 0 === m3 && (m3 = u4(a3, k2, w2), y3 = u4(h4, x2, j2)), m3.has(h4[x2])) if (m3.has(h4[j2])) {
      const e6 = y3.get(a3[k2]), t6 = void 0 !== e6 ? d3[e6] : null;
      if (null === t6) {
        const e7 = v2(s5, d3[x2]);
        u3(e7, p4[k2]), v3[k2] = e7;
      } else v3[k2] = u3(t6, p4[k2]), v2(s5, d3[x2], t6), d3[e6] = null;
      k2++;
    } else h3(d3[j2]), j2--;
    else h3(d3[x2]), x2++;
    for (; k2 <= w2; ) {
      const e6 = v2(s5, v3[w2 + 1]);
      u3(e6, p4[k2]), v3[k2++] = e6;
    }
    for (; x2 <= j2; ) {
      const e6 = d3[x2++];
      null !== e6 && h3(e6);
    }
    return this.ut = a3, p3(s5, v3), E;
  }
});

// src/const.ts
var CARD_VERSION = "4.2.0";
var TICK_MS = 6e4;
var TIMELINE_DAYS = 3;
var LEVELS = ["yellow", "orange", "red"];
var LEVEL_COLORS = {
  yellow: { background: "var(--fmi-warnings-yellow-color, var(--amber-color, #ffc107))", text: "#000000" },
  orange: { background: "var(--fmi-warnings-orange-color, var(--orange-color, #ff9800))", text: "#000000" },
  red: { background: "var(--fmi-warnings-red-color, var(--red-color, #f44336))", text: "#000000" }
};
var TYPE_ICONS = {
  wind: "mdi:weather-windy",
  seaWind: "mdi:weather-windy",
  thunderstorm: "mdi:weather-lightning",
  seaThunderstorm: "mdi:weather-lightning",
  rain: "mdi:weather-pouring",
  trafficWeather: "mdi:car-traction-control",
  pedestrianSafety: "mdi:walk",
  forestFireWeather: "mdi:pine-tree-fire",
  hotWeather: "mdi:thermometer-high",
  coldWeather: "mdi:snowflake-thermometer",
  uvNote: "mdi:sun-wireless",
  seaWaveHeight: "mdi:waves",
  seaWaterHeight: "mdi:waves-arrow-up",
  seaIcing: "mdi:snowflake-alert"
};
var FALLBACK_ICON = "mdi:alert-outline";

// src/height.ts
var HEIGHT_MODES = ["auto", "fixed", "max"];
var pixels = (value) => value == null || typeof value === "number" && Number.isFinite(value) && value > 0;
function validHeight(config) {
  return (config.height_mode == null || HEIGHT_MODES.includes(config.height_mode)) && pixels(config.height) && pixels(config.max_height);
}
function heightMode(config) {
  return config.height_mode ?? (config.height ? "fixed" : config.max_height ? "max" : "auto");
}
var ROW_HEIGHT = 56;
var ROW_GAP = 8;
function heightStyle(config, layout, minimum = 0) {
  const rows = config.grid_options ? config.grid_options.rows : config.layout_options?.grid_rows;
  if (layout === "grid" && typeof rows === "number") {
    return "height: 100%";
  }
  const mode = heightMode(config);
  if (mode === "fixed" && config.height) {
    return `height: ${Math.max(config.height, minimum)}px`;
  }
  return mode === "max" && config.max_height ? `max-height: ${Math.max(config.max_height, minimum)}px` : "";
}
function gridMinRows(minimum) {
  return Math.max(1, Math.ceil((minimum + ROW_GAP) / (ROW_HEIGHT + ROW_GAP)));
}
function heightCardSize(config, content, minimum = 0) {
  const mode = heightMode(config);
  if (mode === "fixed" && config.height) {
    return Math.max(1, Math.round(Math.max(config.height, minimum) / 50));
  }
  return mode === "max" && config.max_height ? Math.max(1, Math.min(content, Math.round(Math.max(config.max_height, minimum) / 50))) : content;
}
function heightSchema(config, text) {
  const mode = heightMode(config);
  const field = (name) => ({
    name,
    selector: { number: { min: 100, max: 2e3, step: 10, unit_of_measurement: "px", mode: "box" } }
  });
  return [
    {
      name: "height_mode",
      selector: {
        select: { mode: "dropdown", options: HEIGHT_MODES.map((value) => ({ value, label: text(`editor.height_mode_${value}`) })) }
      }
    },
    ...mode === "fixed" ? [field("height")] : mode === "max" ? [field("max_height")] : []
  ];
}
function heightData(config) {
  return { ...config, height_mode: heightMode(config) };
}
function tidyHeight(config) {
  const tidied = { ...config };
  for (const key of ["height", "max_height"]) {
    if (!tidied[key]) {
      delete tidied[key];
    }
  }
  if (!tidied.height_mode || heightMode({ ...tidied, height_mode: void 0 }) === tidied.height_mode) {
    delete tidied.height_mode;
  }
  return tidied;
}

// src/localize/languages/en.json
var en_default = {
  common: {
    name: "FMI warnings",
    description: "The Finnish Meteorological Institute's weather and sea warnings for a chosen place",
    invalid_configuration: "Invalid configuration. Choose a warnings sensor of the fmi integration.",
    invalid_height: "Invalid height. height and max_height must be positive numbers of pixels, and height_mode auto, fixed or max.",
    no_entity: "Entity {entity} not found",
    not_warnings: "{entity} is not a warnings sensor of the fmi integration",
    unavailable: "The warnings are not available right now",
    no_warnings: "No warnings",
    now: "now",
    period: "{start} \u2013 {end}",
    from: "from {start}",
    probability: "Probability {value}%"
  },
  levels: {
    yellow: "Yellow warning",
    orange: "Orange warning",
    red: "Red warning"
  },
  types: {
    wind: "Wind",
    seaWind: "Sea wind",
    thunderstorm: "Thunderstorm",
    seaThunderstorm: "Sea thunderstorm",
    rain: "Heavy rain",
    trafficWeather: "Traffic",
    pedestrianSafety: "Pedestrians",
    forestFireWeather: "Forest fire",
    hotWeather: "Heat",
    coldWeather: "Cold",
    uvNote: "UV",
    seaWaveHeight: "Waves",
    seaWaterHeight: "Sea level",
    seaIcing: "Icing"
  },
  editor: {
    entity: "Warnings sensor",
    entity_helper: "A warnings sensor of the fmi integration",
    title: "Title",
    show_timeline: "Show the timeline",
    show_timeline_helper: "Today and the next two days, a bar for each warning",
    height_mode: "Height",
    height_mode_helper: "A height set in the layout tab of a sections view is used instead.",
    height_mode_auto: "Fits the content",
    height_mode_fixed: "Fixed",
    height_mode_max: "Grows up to a limit",
    height: "Fixed height",
    height_helper: "The card is always this tall, and the timeline and the warnings scroll inside it.",
    max_height: "Maximum height",
    max_height_helper: "The card grows with its content up to this height, and then the timeline and the warnings scroll."
  }
};

// src/localize/languages/fi.json
var fi_default = {
  common: {
    name: "FMI-varoitukset",
    description: "Ilmatieteen laitoksen s\xE4\xE4- ja merivaroitukset valitulle paikalle",
    invalid_configuration: "Virheellinen konfiguraatio. Valitse fmi-integraation varoitusanturi.",
    invalid_height: "Virheellinen korkeus. Korkeuksien (height ja max_height) on oltava positiivisia lukuja pikselein\xE4, ja korkeustilan (height_mode) auto, fixed tai max.",
    no_entity: "Entiteetti\xE4 {entity} ei l\xF6ydy",
    not_warnings: "{entity} ei ole fmi-integraation varoitusanturi",
    unavailable: "Varoitukset eiv\xE4t ole juuri nyt saatavilla",
    no_warnings: "Ei varoituksia",
    now: "nyt",
    period: "{start} \u2013 {end}",
    from: "{start} alkaen",
    probability: "Todenn\xE4k\xF6isyys {value} %"
  },
  levels: {
    yellow: "Keltainen varoitus",
    orange: "Oranssi varoitus",
    red: "Punainen varoitus"
  },
  types: {
    wind: "Tuuli",
    seaWind: "Tuuli merell\xE4",
    thunderstorm: "Rajuilma",
    seaThunderstorm: "Rajuilma merell\xE4",
    rain: "Rankkasade",
    trafficWeather: "Liikenne",
    pedestrianSafety: "Jalankulku",
    forestFireWeather: "Mets\xE4palo",
    hotWeather: "Helle",
    coldWeather: "Pakkanen",
    uvNote: "UV",
    seaWaveHeight: "Aallokko",
    seaWaterHeight: "Vedenkorkeus",
    seaIcing: "J\xE4\xE4t\xE4minen"
  },
  editor: {
    entity: "Varoitusanturi",
    entity_helper: "fmi-integraation varoitusanturi",
    title: "Otsikko",
    show_timeline: "N\xE4yt\xE4 aikajana",
    show_timeline_helper: "T\xE4m\xE4 p\xE4iv\xE4 ja kaksi seuraavaa, palkki kullekin varoitukselle",
    height_mode: "Korkeus",
    height_mode_helper: "Osioihin jaetun n\xE4kym\xE4n asettelu-v\xE4lilehdell\xE4 asetettu korkeus ohittaa t\xE4m\xE4n.",
    height_mode_auto: "Sis\xE4ll\xF6n mukaan",
    height_mode_fixed: "Kiinte\xE4",
    height_mode_max: "Kasvaa rajaan asti",
    height: "Kiinte\xE4 korkeus",
    height_helper: "Kortti on aina n\xE4in korkea, ja aikajana ja varoitukset vieriv\xE4t sen sis\xE4ll\xE4.",
    max_height: "Enimm\xE4iskorkeus",
    max_height_helper: "Kortti kasvaa sis\xE4lt\xF6ns\xE4 mukana t\xE4h\xE4n korkeuteen asti, ja sen j\xE4lkeen aikajana ja varoitukset vieriv\xE4t."
  }
};

// src/localize/localize.ts
var FILES = { "./languages/en.json": en_default, "./languages/fi.json": fi_default };
var LANGUAGES = Object.fromEntries(
  Object.entries(FILES).map(([path, table]) => [path.replace(/^.*\/|\.json$/g, "").toLowerCase(), table])
);
var LANGUAGE_CODES = Object.keys(LANGUAGES).sort();
function translate(language, key) {
  const code = (language ?? "en").split(/[-_]/)[0].toLowerCase();
  return read(LANGUAGES[code], key) ?? read(LANGUAGES.en, key) ?? key;
}
function read(table, key) {
  let value = table;
  for (const part of key.split(".")) {
    if (value === null || typeof value !== "object") {
      return void 0;
    }
    value = value[part];
  }
  return typeof value === "string" ? value : void 0;
}
function browserLanguage() {
  return document.documentElement.lang || navigator.language || "en";
}

// src/warnings.ts
var DAY_MS = 864e5;
var MIN_BAR = 11;
var BAR_GAP = 1;
function isWarningsSensor(entity) {
  return Array.isArray(entity?.attributes?.warnings) && Array.isArray(entity?.attributes?.warning_types);
}
function warningsSensors(hass) {
  return Object.keys(hass.states).filter((id) => isWarningsSensor(hass.states[id])).sort();
}
function visibleWarnings(value, now) {
  const warnings = Array.isArray(value) ? value.filter(isWarning) : [];
  return warnings.filter((warning) => warning.expires === null || Date.parse(warning.expires) > now).map((warning) => ({ warning, active: warning.onset === null || Date.parse(warning.onset) <= now })).sort((a3, b3) => onset(a3.warning) - onset(b3.warning) || LEVELS.indexOf(b3.warning.level) - LEVELS.indexOf(a3.warning.level));
}
function onset(warning) {
  return warning.onset === null ? -Infinity : Date.parse(warning.onset);
}
function isWarning(value) {
  const warning = value;
  const time = (text) => text === null || typeof text === "string" && !Number.isNaN(Date.parse(text));
  return typeof warning === "object" && warning !== null && typeof warning.event === "string" && LEVELS.includes(warning.level) && time(warning.onset) && time(warning.expires);
}
function moment(time, now, language, timeZone, hour12) {
  const at = Date.parse(time);
  const [then, today] = [clock(at, timeZone), clock(now, timeZone)];
  const days = (Date.UTC(then.year, then.month - 1, then.day) - Date.UTC(today.year, today.month - 1, today.day)) / DAY_MS;
  const day = new Intl.DateTimeFormat(language, {
    ...days < 7 ? { weekday: "short" } : { day: "numeric", month: "numeric" },
    timeZone
  }).format(at);
  const cycle = hour12 === void 0 ? {} : hour12 ? { hour12: true } : { hourCycle: "h23" };
  const hours = new Intl.DateTimeFormat(language, { hour: "numeric", minute: "2-digit", ...cycle, timeZone }).format(at);
  return `${day} ${hours}`;
}
function timeline(shown, now, language, timeZone) {
  const starts = Array.from({ length: TIMELINE_DAYS + 1 }, (_2, day) => startOfDay(now, day, timeZone));
  const first = starts[0];
  const last = starts[TIMELINE_DAYS];
  const at = (time) => (time - first) / (last - first) * 100;
  const today = clock(now, timeZone);
  const weekday = new Intl.DateTimeFormat(language, { weekday: "short", timeZone: "UTC" });
  return {
    days: starts.slice(0, -1).map((start, day) => ({
      label: weekday.format(Date.UTC(today.year, today.month - 1, today.day + day)),
      left: at(start)
    })),
    now: at(now),
    ...pack(
      shown.flatMap(({ warning }) => {
        const start = Math.max(warning.onset === null ? first : Date.parse(warning.onset), first);
        const end = Math.min(warning.expires === null ? last : Date.parse(warning.expires), last);
        return end > start ? [{ warning, left: at(start), width: at(end) - at(start) }] : [];
      })
    )
  };
}
function pack(bars) {
  const ends = [];
  const packed = bars.map((bar) => {
    const left = Math.min(bar.left, 100 - MIN_BAR);
    const right = left + Math.max(bar.width, MIN_BAR);
    let lane = ends.findIndex((end) => left >= end + BAR_GAP);
    if (lane === -1) {
      lane = ends.length;
    }
    ends[lane] = right;
    return { ...bar, lane };
  });
  return { bars: packed, lanes: ends.length };
}
function startOfDay(time, days, timeZone) {
  const { year, month, day } = clock(time, timeZone);
  const midnight = Date.UTC(year, month - 1, day + days);
  const guess = midnight - offset(midnight, timeZone);
  return midnight - offset(guess, timeZone);
}
function offset(time, timeZone) {
  const { year, month, day, hour, minute, second } = clock(time, timeZone);
  return Date.UTC(year, month - 1, day, hour, minute, second) - Math.floor(time / 1e3) * 1e3;
}
function clock(time, timeZone) {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    second: "numeric"
  }).formatToParts(time);
  const part = (type) => Number(parts.find((item) => item.type === type)?.value);
  return {
    year: part("year"),
    month: part("month"),
    day: part("day"),
    hour: part("hour"),
    minute: part("minute"),
    second: part("second")
  };
}

// src/editor.ts
var DEFAULTS = {
  show_timeline: true
};
function schema(hass, config, text) {
  return [
    { name: "entity", required: true, selector: { entity: { include_entities: warningsSensors(hass) } } },
    { name: "title", selector: { text: {} } },
    { name: "show_timeline", selector: { boolean: {} } },
    ...heightSchema(config, text)
  ];
}
var FmiWarningsCardEditor = class extends i4 {
  constructor() {
    super(...arguments);
    this.config = { type: "custom:fmi-warnings-card", entity: "" };
  }
  setConfig(config) {
    this.config = { ...config };
  }
  render() {
    if (!this.hass) {
      return A;
    }
    return b2`
            <ha-form
                .hass=${this.hass}
                .data=${{ ...DEFAULTS, ...heightData(this.config) }}
                .schema=${schema(this.hass, this.config, (key) => this.text(key))}
                .computeLabel=${(entry) => this.text(`editor.${entry.name}`)}
                .computeHelper=${(entry) => this.helper(entry.name)}
                @value-changed=${this.valueChanged}
            ></ha-form>
        `;
  }
  valueChanged(event) {
    const config = tidyHeight(event.detail.value);
    if (!config.title) {
      delete config.title;
    }
    for (const [key, value] of Object.entries(DEFAULTS)) {
      if (config[key] === value || config[key] === void 0 || config[key] === null) {
        delete config[key];
      }
    }
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
  }
  text(key) {
    return translate(this.language(), key);
  }
  helper(name) {
    const key = `editor.${name}_helper`;
    const helper = translate(this.language(), key);
    return helper === key ? void 0 : helper;
  }
  language() {
    return this.hass?.locale?.language ?? this.hass?.language ?? browserLanguage();
  }
};
__decorateClass([
  n4({ attribute: false })
], FmiWarningsCardEditor.prototype, "hass", 2);
__decorateClass([
  r5()
], FmiWarningsCardEditor.prototype, "config", 2);
if (!customElements.get("fmi-warnings-card-editor")) {
  customElements.define("fmi-warnings-card-editor", FmiWarningsCardEditor);
}

// src/fade.ts
var fadeStyles = i`
    .fades {
        --fade-length: min(24px, 25%);
        scroll-padding-block: calc(var(--fade-top-offset, 0px) + var(--fade-length, 24px)) var(--fade-length, 24px);
    }

    .fade-top {
        mask-image: linear-gradient(
            to bottom,
            #000 var(--fade-top-offset, 0px),
            transparent var(--fade-top-offset, 0px),
            #000 calc(var(--fade-top-offset, 0px) + var(--fade-length, 24px))
        );
    }

    .fade-bottom {
        mask-image: linear-gradient(to top, transparent, #000 var(--fade-length, 24px));
    }

    .fade-top.fade-bottom {
        mask-image: linear-gradient(
            to bottom,
            #000 var(--fade-top-offset, 0px),
            transparent var(--fade-top-offset, 0px),
            #000 calc(var(--fade-top-offset, 0px) + var(--fade-length, 24px)),
            #000 calc(100% - var(--fade-length, 24px)),
            transparent
        );
    }
`;
function markFade(part) {
  const hidden = part.scrollHeight - part.clientHeight;
  part.classList.toggle("fade-top", hidden > 1 && part.scrollTop > 1);
  part.classList.toggle("fade-bottom", hidden > 1 && hidden - part.scrollTop > 1);
}
var onScroll = (event) => markFade(event.currentTarget);
var ScrollFade = class {
  constructor(host, parts) {
    this.host = host;
    this.parts = parts;
    /** Each followed part with the children whose size it watches. */
    this.followed = /* @__PURE__ */ new Map();
    this.resized = typeof ResizeObserver === "undefined" ? void 0 : new ResizeObserver((entries) => {
      for (const { target } of entries) {
        const part = this.followed.has(target) ? target : target.parentElement;
        if (part && this.followed.has(part)) {
          markFade(part);
        }
      }
    });
    host.addController(this);
  }
  hostConnected() {
    if (this.host.hasUpdated) {
      this.follow();
    }
  }
  hostUpdated() {
    if (this.host.isConnected) {
      this.follow();
    }
  }
  hostDisconnected() {
    for (const part of [...this.followed.keys()]) {
      this.forget(part);
    }
  }
  follow() {
    const now = new Set(this.parts());
    for (const part of [...this.followed.keys()]) {
      if (!now.has(part)) {
        this.forget(part);
      }
    }
    for (const part of now) {
      if (!this.followed.has(part)) {
        part.addEventListener("scroll", onScroll, { passive: true });
        this.resized?.observe(part);
      }
      part.classList.add("fades");
      const before = this.followed.get(part) ?? [];
      const children = [...part.children];
      before.filter((child) => !children.includes(child)).forEach((child) => this.resized?.unobserve(child));
      children.filter((child) => !before.includes(child)).forEach((child) => this.resized?.observe(child));
      this.followed.set(part, children);
      markFade(part);
    }
  }
  forget(part) {
    this.followed.get(part)?.forEach((child) => this.resized?.unobserve(child));
    this.followed.delete(part);
    part.removeEventListener("scroll", onScroll);
    this.resized?.unobserve(part);
    part.classList.remove("fades", "fade-top", "fade-bottom");
  }
};

// src/fmi-warnings-card.ts
var FmiWarningsCard = class extends i4 {
  constructor() {
    super();
    /** The warnings to draw and their rows' keys, worked out once per update. */
    this.list = { now: 0, shown: [], keys: /* @__PURE__ */ new Map() };
    this.tick = 0;
    /** Once a row a tap opened has slid open, scrolls the body or the page just enough to show it. */
    this.opening = (event) => {
      const row = event.currentTarget.closest(".row");
      if (event.propertyName !== "grid-template-rows" || event.target !== event.currentTarget || row?.dataset.key !== this.revealing) {
        return;
      }
      this.revealing = void 0;
      scrollTo(row);
    };
    new ScrollFade(this, () => this.heightStyle() ? this.renderRoot.querySelectorAll(".body") : []);
  }
  static getConfigElement() {
    return document.createElement("fmi-warnings-card-editor");
  }
  /** Offers the first warnings sensor there is when the card is added from the picker. */
  static getStubConfig(hass) {
    return { entity: hass ? warningsSensors(hass)[0] ?? "" : "" };
  }
  setConfig(config) {
    if (!config || typeof config.entity !== "string" || config.entity === "") {
      throw new Error(translate(browserLanguage(), "common.invalid_configuration"));
    }
    if (!validHeight(config)) {
      throw new Error(translate(browserLanguage(), "common.invalid_height"));
    }
    this.config = config;
  }
  /** In units of 50 px, for a masonry view: the title, the timeline and a row per warning, or the height it is held to. */
  getCardSize() {
    const now = Date.now();
    const shown = visibleWarnings(this.hass?.states[this.config?.entity ?? ""]?.attributes.warnings, now);
    const drawn = this.config?.show_timeline !== false && timeline(shown, now, this.language(), this.timeZone()).bars.length > 0;
    const size = (this.config?.title ? 1 : 0) + (drawn ? 2 : 0) + Math.max(1, shown.length);
    return heightCardSize(this.config ?? {}, size, this.minimumHeight());
  }
  /**
   * In a sections view the card takes a whole section by default and is never narrower than two thirds of one, nor
   * lower than its minimum height.
   */
  getGridOptions() {
    return { columns: 12, min_columns: 8, rows: "auto", min_rows: gridMinRows(this.minimumHeight()) };
  }
  /** A warning moves from coming up to in force, and one that has expired goes, between the sensor's updates. */
  connectedCallback() {
    super.connectedCallback();
    this.tick++;
    this.ticker = setInterval(() => this.tick++, TICK_MS);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    clearInterval(this.ticker);
  }
  shouldUpdate(changed) {
    const previous = changed.get("hass");
    if (changed.has("config") || changed.has("layout") || changed.has("opened") || changed.has("tick") || !this.config || !changed.has("hass") || !previous) {
      return true;
    }
    return previous.states[this.config.entity] !== this.hass?.states[this.config.entity];
  }
  /** Works out the rows, and forgets an opened row whose warning has gone, so it can't come back open by itself. */
  willUpdate() {
    const entity = this.config ? this.hass?.states[this.config.entity] : void 0;
    const now = Date.now();
    const shown = isWarningsSensor(entity) ? visibleWarnings(entity.attributes.warnings, now) : [];
    const keys = rowKeys(shown);
    if (this.opened !== void 0 && ![...keys.values()].includes(this.opened)) {
      this.opened = void 0;
    }
    this.list = { now, shown, keys };
  }
  render() {
    if (!this.hass || !this.config) {
      return A;
    }
    return b2`
            <ha-card style=${this.heightStyle()}>
                ${this.config.title ? b2`<h1 class="card-title">${this.config.title}</h1>` : A} ${this.content(this.config.entity)}
            </ha-card>
        `;
  }
  content(entityId) {
    const entity = this.hass?.states[entityId];
    if (!entity) {
      return b2`<div class="message">${this.text("common.no_entity", { entity: entityId })}</div>`;
    }
    if (entity.state === "unavailable" || entity.state === "unknown") {
      return b2`<div class="message">${this.text("common.unavailable")}</div>`;
    }
    if (!isWarningsSensor(entity)) {
      return b2`<div class="message">${this.text("common.not_warnings", { entity: entityId })}</div>`;
    }
    const { now, shown, keys } = this.list;
    if (!shown.length) {
      return b2`<div class="empty">
                <ha-icon icon="mdi:check-circle-outline"></ha-icon><span>${this.text("common.no_warnings")}</span>
            </div>`;
    }
    return b2`
            <div class="body">
                ${this.config?.show_timeline === false ? A : this.timeline(shown, now, keys)}
                <div class="rows">
                    ${c4(
      shown,
      ({ warning }) => keys.get(warning),
      (item) => this.row(item, keys.get(item.warning), now)
    )}
                </div>
            </div>
        `;
  }
  /** Today and the next two days, a bar per warning in lanes they share when they follow each other, and a line at now. */
  timeline(shown, now, keys) {
    const { days, now: at, bars, lanes } = timeline(shown, now, this.language(), this.timeZone());
    if (!bars.length) {
      return A;
    }
    return b2`
            <div class="timeline" aria-hidden="true">
                <div class="now-label" style="left:${at}%">${this.text("common.now")}</div>
                <div class="lanes">
                    ${days.slice(1).map(({ left }) => b2`<span class="midnight" style="left:${left}%"></span>`)}
                    <span class="now" style="left:${at}%"></span>
                    ${Array.from(
      { length: lanes },
      (_2, lane) => b2`<div class="lane">
                                ${bars.filter((bar) => bar.lane === lane).map(({ warning, left, width }) => {
        const colors = LEVEL_COLORS[warning.level];
        return b2`<div
                                            class="bar"
                                            style="left:min(${left}%, calc(100% - 22px));width:${width}%;background:${colors.background};color:${colors.text}"
                                            title="${warning.event}"
                                            @click=${() => this.show(keys.get(warning))}
                                        >
                                            <ha-icon icon="${icon(warning)}"></ha-icon><span class="label">${this.typeName(warning)}</span>
                                        </div>`;
      })}
                            </div>`
    )}
                </div>
                <div class="days">${days.map(({ label, left }) => b2`<span style="left:${left}%">${label}</span>`)}</div>
            </div>
        `;
  }
  /** A warning on one line, its details under it once opened. */
  row({ warning, active }, key, now) {
    const open = this.opened === key;
    const color = LEVEL_COLORS[warning.level].background;
    const level = this.text(`levels.${warning.level}`);
    return b2`
            <div class="row ${active ? "" : "upcoming"}" data-key=${key}>
                <span class="stripe" style="background:${color}"></span>
                <div class="row-body">
                    <button class="summary" aria-expanded="${open}" @click=${() => this.toggle(key)}>
                        <ha-icon icon="${icon(warning)}" style="color:${color}"></ha-icon>
                        <span class="visually-hidden">${level}</span>
                        <span class="text">
                            <span class="name">${warning.event}</span>
                            <span class="time">${this.period(warning, active, now)}</span>
                        </span>
                        <ha-icon class="chevron" icon="mdi:chevron-down"></ha-icon>
                    </button>
                    <div class="expander ${open ? "open" : ""}" ?inert=${!open} @transitionend=${this.opening}>
                        <div class="clip">
                            <div class="details">
                                <div class="level">${level}</div>
                                ${warning.description ? b2`<div>${warning.description}</div>` : A}
                                ${warning.impacts ? b2`<div class="impacts">${warning.impacts}</div>` : A}
                                ${typeof warning.probability === "number" ? b2`<div class="probability">
                                              ${this.text("common.probability", { value: String(warning.probability) })}
                                          </div>` : A}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
  }
  /** "nyt – ti 3.00" for a warning in force, "ti 6.00 – ti 12.00" for one coming up, "from …" for one with no end. */
  period(warning, active, now) {
    const start = active || warning.onset === null ? this.text("common.now") : this.moment(warning.onset, now);
    return warning.expires === null ? this.text("common.from", { start }) : this.text("common.period", { start, end: this.moment(warning.expires, now) });
  }
  moment(time, now) {
    return moment(time, now, this.language(), this.timeZone(), this.hour12());
  }
  /** The user's choice of clock in their profile. "language" leaves it to the language. */
  hour12() {
    switch (this.hass?.locale?.time_format) {
      case "12":
        return true;
      case "24":
        return false;
      case "system":
        return new Intl.DateTimeFormat(void 0, { hour: "numeric" }).resolvedOptions().hour12;
      default:
        return void 0;
    }
  }
  /** A short name for a bar on the timeline. A type FMI adds later has none, and goes by the warning's own name. */
  typeName(warning) {
    const key = `types.${warning.type}`;
    const name = translate(this.language(), key);
    return name === key ? warning.event : name;
  }
  toggle(key) {
    this.opened = this.opened === key ? void 0 : key;
    this.revealing = this.opened;
  }
  /** A bar tapped on the timeline opens its row, which is then brought into view. One already open has no opening to wait for. */
  show(key) {
    if (this.opened !== key) {
      this.toggle(key);
      return;
    }
    scrollTo([...this.renderRoot.querySelectorAll(".row")].find((element) => element.dataset.key === key));
  }
  /**
   * The lowest the card is held to, in pixels: its padding, the title when it has one, a timeline of one lane when it
   * is shown, and one warning row. The padding (with the card's border), the title and the timeline as measured on a
   * full section's width, the row estimated from the styles.
   */
  minimumHeight() {
    const padding = 34;
    const title = 41;
    const timeline2 = 75;
    const row = 40;
    return padding + (this.config?.title ? title : 0) + (this.config?.show_timeline === false ? 0 : timeline2) + row;
  }
  heightStyle() {
    return heightStyle(this.config ?? {}, this.layout, this.minimumHeight());
  }
  timeZone() {
    return this.hass?.locale?.time_zone === "server" ? this.hass.config?.time_zone : void 0;
  }
  /** A text in the viewer's language, with `{name}` in it replaced, so a translation can put the value where it reads right. */
  text(key, values = {}) {
    return translate(this.language(), key).replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
  }
  language() {
    return this.hass?.locale?.language ?? this.hass?.language ?? browserLanguage();
  }
  static get styles() {
    return [
      i`
                :host {
                    display: block;
                    height: 100%;
                }

                /*
                 * The card is the container its layout measures, so it follows its own width, in a sections view or not.
                 * Held to a height, fixed or at most, or by a fixed number of rows in a sections view, the title stays and the
                 * timeline scrolls with the rows, as its lanes follow the warnings and could otherwise leave no room for a
                 * row. The card is never lower than its title, a timeline of one lane and a row. Clipped, not hidden,
                 * which would make the card a scroller that bringing a row into view could scroll out of place.
                 */
                ha-card {
                    overflow: clip;
                    container-type: inline-size;
                    box-sizing: border-box;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    padding: 16px;
                    font-variant-numeric: tabular-nums;
                }

                ha-card > * {
                    flex: none;
                }

                /*
                 * Never sideways, where a turning chevron would otherwise flash a scrollbar for a moment. It reaches out over
                 * the card's padding to the sides, so its clipped edges don't cut what sits at the content's edge, such as the
                 * timeline's "now" label near midnight.
                 */
                ha-card > .body {
                    margin: 0 -16px;
                    padding: 0 16px;
                    flex: 1 1 auto;
                    min-height: 0;
                    overflow-x: hidden;
                    overflow-y: auto;
                    overscroll-behavior: contain;
                    scrollbar-width: thin;
                }

                .card-title {
                    margin: 0 0 12px;
                    font-size: var(--ha-card-header-font-size, 24px);
                    font-weight: var(--ha-font-weight-normal, 400);
                    line-height: 1.2;
                }

                .message {
                    color: var(--secondary-text-color);
                }

                .empty {
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    color: var(--secondary-text-color);
                }

                .empty ha-icon {
                    flex: none;
                    color: var(--success-color, #43a047);
                }

                .timeline {
                    position: relative;
                    margin-bottom: 8px;
                    padding-top: 16px;
                }

                .now-label {
                    position: absolute;
                    top: 0;
                    transform: translateX(-50%);
                    font-size: 11px;
                    line-height: 14px;
                    color: var(--primary-text-color);
                }

                .lanes {
                    position: relative;
                    padding: 2px 0;
                }

                .lane {
                    position: relative;
                    height: 22px;
                    margin: 4px 0;
                }

                .midnight,
                .now {
                    position: absolute;
                    top: 0;
                    bottom: 0;
                }

                .midnight {
                    width: 1px;
                    background: var(--divider-color);
                }

                /* Behind the bars, which come after it. */
                .now {
                    width: 2px;
                    margin-left: -1px;
                    background: var(--primary-text-color);
                    opacity: 0.7;
                }

                .now-label,
                .now {
                    pointer-events: none;
                }

                .bar {
                    position: absolute;
                    cursor: pointer;
                    top: 0;
                    box-sizing: border-box;
                    min-width: 22px;
                    height: 22px;
                    display: flex;
                    flex-wrap: wrap;
                    align-items: center;
                    column-gap: 4px;
                    padding: 0 3px;
                    border-radius: 6px;
                    font-size: 12px;
                    line-height: 22px;
                    white-space: nowrap;
                    overflow: hidden;
                }

                .bar ha-icon {
                    --mdc-icon-size: 16px;
                    flex: none;
                    width: 16px;
                    height: 22px;
                    display: inline-flex;
                    align-items: center;
                }

                /* A label that doesn't fit whole wraps to a second line, which the bar's height hides, leaving the icon alone. */
                .bar .label {
                    flex: none;
                }

                /* Below 400 px inside the padding, the bars are too short to name. The rows below say what each is. */
                @container (max-width: 399px) {
                    .bar .label {
                        display: none;
                    }
                }

                .days {
                    position: relative;
                    height: 16px;
                    border-top: 1px solid var(--divider-color);
                    font-size: 12px;
                    line-height: 16px;
                    color: var(--secondary-text-color);
                }

                .days span {
                    position: absolute;
                    padding-left: 4px;
                }

                .row {
                    display: flex;
                    gap: 10px;
                    border-top: 1px solid var(--divider-color);
                }

                .row:first-child {
                    border-top: none;
                }

                .stripe {
                    flex: none;
                    width: 4px;
                    margin: 8px 0;
                    border-radius: 2px;
                }

                .row-body {
                    flex: 1;
                    min-width: 0;
                }

                /* Drawn inside, where the body's clipped edges can't cut it. */
                .summary:focus-visible {
                    outline-offset: -2px;
                }

                .summary {
                    position: relative;
                    display: grid;
                    grid-template-columns: 24px minmax(0, 1fr) 20px;
                    align-items: center;
                    gap: 10px;
                    width: 100%;
                    padding: 8px 0;
                    border: none;
                    background: none;
                    color: inherit;
                    font: inherit;
                    font-size: 14px;
                    text-align: left;
                    cursor: pointer;
                }

                /* The name and the time on one line while both fit whole; the time moves under the name when they don't. */
                .text {
                    display: flex;
                    flex-wrap: wrap;
                    align-items: baseline;
                    gap: 2px 10px;
                    min-width: 0;
                }

                /* One line, cut short when even a line of its own is too narrow. An opened row shows it whole. */
                .name {
                    flex: 1 1 auto;
                    min-width: 0;
                    overflow: hidden;
                    white-space: nowrap;
                    text-overflow: ellipsis;
                }

                .summary[aria-expanded="true"] .name {
                    white-space: normal;
                    overflow-wrap: anywhere;
                }

                .time {
                    font-size: 13px;
                    color: var(--secondary-text-color);
                }

                .chevron {
                    --mdc-icon-size: 20px;
                    display: flex;
                    color: var(--secondary-text-color);
                    transition: transform 0.2s;
                }

                .summary[aria-expanded="true"] .chevron {
                    transform: rotate(180deg);
                }

                .upcoming .summary ha-icon,
                .upcoming .name {
                    opacity: 0.75;
                }

                /* The details are always there, folded to nothing and inert while the row is closed, so opening can slide. */
                .expander {
                    display: grid;
                    grid-template-rows: 0fr;
                    transition: grid-template-rows 0.2s ease;
                }

                .expander.open {
                    grid-template-rows: 1fr;
                }

                .clip {
                    min-height: 0;
                    overflow: hidden;
                }

                /* Over in a moment rather than not at all, so the row is still brought into view when it ends. */
                @media (prefers-reduced-motion: reduce) {
                    .expander,
                    .chevron {
                        transition-duration: 1ms;
                    }
                }

                .details {
                    display: grid;
                    gap: 4px;
                    padding: 0 0 10px 34px;
                    font-size: 13px;
                    line-height: 1.4;
                    overflow-wrap: anywhere;
                }

                .visually-hidden {
                    position: absolute;
                    width: 1px;
                    height: 1px;
                    overflow: hidden;
                    clip-path: inset(50%);
                    white-space: nowrap;
                }

                .level {
                    font-weight: var(--ha-font-weight-medium, 500);
                }

                .impacts {
                    font-style: italic;
                    color: var(--secondary-text-color);
                }

                .probability {
                    color: var(--secondary-text-color);
                }
            `,
      fadeStyles
    ];
  }
};
__decorateClass([
  n4({ attribute: false })
], FmiWarningsCard.prototype, "hass", 2);
__decorateClass([
  n4({ attribute: false })
], FmiWarningsCard.prototype, "layout", 2);
__decorateClass([
  r5()
], FmiWarningsCard.prototype, "config", 2);
__decorateClass([
  r5()
], FmiWarningsCard.prototype, "opened", 2);
__decorateClass([
  r5()
], FmiWarningsCard.prototype, "tick", 2);
function scrollTo(row) {
  if (!row) {
    return;
  }
  const behavior = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false ? "auto" : "smooth";
  const body = row.closest(".body");
  const padding = body?.classList.contains("fades") ? Math.min(24, body.clientHeight / 4) : 0;
  if (body && row.offsetHeight > body.clientHeight - 2 * padding) {
    body.scrollTo({ top: body.scrollTop + row.getBoundingClientRect().top - body.getBoundingClientRect().top - padding, behavior });
    body.scrollIntoView({ block: "nearest", behavior });
    return;
  }
  row.scrollIntoView({ block: "nearest", behavior });
}
function icon(warning) {
  return TYPE_ICONS[warning.type] ?? FALLBACK_ICON;
}
function rowKeys(shown) {
  const seen = /* @__PURE__ */ new Map();
  return new Map(
    shown.map(({ warning }) => {
      const areas = Array.isArray(warning.areas) ? warning.areas : [];
      const onset2 = warning.onset === null ? "" : Date.parse(warning.onset);
      const key = `${warning.type}|${warning.level}|${onset2}|${areas.join(",")}`;
      const count = seen.get(key) ?? 0;
      seen.set(key, count + 1);
      return [warning, count ? `${key}#${count}` : key];
    })
  );
}
if (!customElements.get("fmi-warnings-card")) {
  console.info(
    `%c  FMI-WARNINGS-CARD 
%c  ${CARD_VERSION}    `,
    "color: orange; font-weight: bold; background: black",
    "color: white; font-weight: bold; background: dimgray"
  );
  const registry = window;
  registry.customCards = registry.customCards ?? [];
  registry.customCards.push({
    type: "fmi-warnings-card",
    name: translate(browserLanguage(), "common.name"),
    description: translate(browserLanguage(), "common.description"),
    documentationURL: "https://github.com/jesmak/fmi#warnings-card",
    preview: true
  });
  customElements.define("fmi-warnings-card", FmiWarningsCard);
}
export {
  FmiWarningsCard
};
