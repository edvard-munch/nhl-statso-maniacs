(function(factory) {
    if (typeof define === 'function' && define.amd) {
        define(['jquery'], factory);
    } else if (typeof module === 'object' && typeof module.exports === 'object') {
        module.exports = factory(require('jquery'));
    } else {
        factory(jQuery);
    }
}(function(jQuery) {

    /*!
     * tablesorter (FORK) pager plugin
     * updated 2018-08-27 (v2.31.0)
     */
    ! function(M) {
        "use strict";
        var T = M.tablesorter;
        M.extend({
            tablesorterPager: new function() {
                this.defaults = {
                    container: null,
                    ajaxUrl: null,
                    customAjaxUrl: function(e, t) {
                        return t
                    },
                    ajaxError: null,
                    ajaxObject: {
                        dataType: "json"
                    },
                    processAjaxOnInit: !0,
                    ajaxProcessing: function(e) {
                        return e
                    },
                    output: "{startRow} to {endRow} of {totalRows} rows",
                    updateArrows: !0,
                    page: 0,
                    pageReset: 0,
                    size: 10,
                    maxOptionSize: 20,
                    savePages: !0,
                    storageKey: "tablesorter-pager",
                    fixedHeight: !1,
                    countChildRows: !1,
                    removeRows: !1,
                    cssFirst: ".first",
                    cssPrev: ".prev",
                    cssNext: ".next",
                    cssLast: ".last",
                    cssGoto: ".gotoPage",
                    cssPageDisplay: ".pagedisplay",
                    cssPageSize: ".pagesize",
                    cssErrorRow: "tablesorter-errorRow",
                    cssDisabled: "disabled",
                    totalRows: 0,
                    totalPages: 0,
                    filteredRows: 0,
                    filteredPages: 0,
                    ajaxCounter: 0,
                    currentFilters: [],
                    startRow: 0,
                    endRow: 0,
                    $size: null,
                    last: {}
                };
                var f = "filterInit filterStart filterEnd sortEnd disablePager enablePager destroyPager updateComplete pageSize pageSet pageAndSize pagerUpdate refreshComplete ",
                    u = this,
                    h = function(e, t, a) {
                        var i, s = "addClass",
                            r = "removeClass",
                            o = t.cssDisabled,
                            n = !!a,
                            l = n || 0 === t.page,
                            g = I(e, t),
                            c = n || t.page === g - 1 || 0 === g;
                        t.updateArrows && ((i = t.$container.find(t.cssFirst + "," + t.cssPrev))[l ? s : r](o), i.each(function() {
                            this.ariaDisabled = l
                        }), (i = t.$container.find(t.cssNext + "," + t.cssLast))[c ? s : r](o), i.each(function() {
                            this.ariaDisabled = c
                        }))
                    },
                    w = function(e, t) {
                        var a, i, s, r = e.config,
                            o = r.$table.hasClass("hasFilters");
                        if (o && !t.ajax)
                            if (T.isEmptyObject(r.cache)) t.filteredRows = t.totalRows = r.$tbodies.eq(0).children("tr").not(t.countChildRows ? "" : "." + r.cssChildRow).length;
                            else
                                for (t.filteredRows = 0, s = (a = r.cache[0].normalized).length, i = 0; i < s; i++) t.filteredRows += t.regexRows.test(a[i][r.columns].$row[0].className) ? 0 : 1;
                        else o || (t.filteredRows = t.totalRows)
                    },
                    y = function(e, n, t) {
                        if (!n.initializing) {
                            var a, i, s, r, o, l, g, c, d = e.config,
                                p = d.namespace + "pager",
                                f = A(n, n.size, "get");
                            if ("all" === f && (f = n.totalRows), n.countChildRows && (i[i.length] = d.cssChildRow), n.totalPages = Math.ceil(n.totalRows / f), d.totalRows = n.totalRows, N(e, n), w(e, n), d.filteredRows = n.filteredRows, n.filteredPages = Math.ceil(n.filteredRows / f) || 0, 0 <= I(e, n)) {
                                if (i = f * n.page > n.filteredRows && t, n.page = i ? n.pageReset || 0 : n.page, n.startRow = i ? f * n.page + 1 : 0 === n.filteredRows ? 0 : f * n.page + 1, n.endRow = Math.min(n.filteredRows, n.totalRows, f * (n.page + 1)), s = n.$container.find(n.cssPageDisplay), a = "function" == typeof n.output ? n.output(e, n) : (c = s.attr("data-pager-output" + (n.filteredRows < n.totalRows ? "-filtered" : "")) || n.output, (n.ajaxData && n.ajaxData.output && n.ajaxData.output || c).replace(/\{page([\-+]\d+)?\}/gi, function(e, t) {
                                        return n.totalPages ? n.page + (t ? parseInt(t, 10) : 1) : 0
                                    }).replace(/\{\w+(\s*:\s*\w+)?\}/gi, function(e) {
                                        var t, a, i = e.replace(/[{}\s]/g, ""),
                                            s = i.split(":"),
                                            r = n.ajaxData,
                                            o = /(rows?|pages?)$/i.test(i) ? 0 : "";
                                        return /(startRow|page)/.test(s[0]) && "input" === s[1] ? (t = ("" + ("page" === s[0] ? n.totalPages : n.totalRows)).length, a = "page" === s[0] ? n.page + 1 : n.startRow, '<input type="text" class="ts-' + s[0] + '" style="max-width:' + t + 'em" value="' + a + '"/>') : 1 < s.length && r && r[s[0]] ? r[s[0]][s[1]] : n[i] || (r ? r[i] : o) || o
                                    })), (r = n.$container.find(n.cssGoto)).length) {
                                    for (i = "", l = (g = b(e, n)).length, o = 0; o < l; o++) i += '<option value="' + g[o] + '">' + g[o] + "</option>";
                                    r.html(i).val(n.page + 1)
                                }
                                s.length && (s["INPUT" === s[0].nodeName ? "val" : "html"](a), s.find(".ts-startRow, .ts-page").unbind("change" + p).bind("change" + p, function() {
                                    var e = M(this).val(),
                                        t = M(this).hasClass("ts-startRow") ? Math.floor(e / f) + 1 : e;
                                    d.$table.triggerHandler("pageSet" + p, [t])
                                }))
                            }
                            h(e, n), R(e, n), n.initialized && !1 !== t && (T.debug(d, "pager") && console.log("Pager >> Triggering pagerComplete"), d.$table.triggerHandler("pagerComplete", n), n.savePages && T.storage && T.storage(e, n.storageKey, {
                                page: n.page,
                                size: f === n.totalRows ? "all" : f
                            }))
                        }
                    },
                    b = function(e, t) {
                        var a, i, s, r, o, n, l = I(e, t) || 1,
                            g = 5 * Math.ceil(l / t.maxOptionSize / 5),
                            c = l > t.maxOptionSize,
                            d = t.page + 1,
                            p = g,
                            f = l - g,
                            u = [1];
                        for (a = c ? g : 1; a <= l;) u[u.length] = a, a += c ? g : 1;
                        if (u[u.length] = l, c) {
                            for (s = [], (p = d - (i = Math.max(Math.floor(t.maxOptionSize / g) - 1, 5))) < 1 && (p = 1), l < (f = d + i) && (f = l), a = p; a <= f; a++) s[s.length] = a;
                            g / 2 < (o = (u = M.grep(u, function(e, t) {
                                return M.inArray(e, u) === t
                            })).length) - (n = s.length) && o + n > t.maxOptionSize && (r = Math.floor(o / 2) - Math.floor(n / 2), Array.prototype.splice.apply(u, [r, n])), u = u.concat(s)
                        }
                        return u = M.grep(u, function(e, t) {
                            return M.inArray(e, u) === t
                        }).sort(function(e, t) {
                            return e - t
                        })
                    },
                    R = function(e, t) {
                        var a, i, s, r = e.config,
                            o = r.$tbodies.eq(0);
                        o.find("tr.pagerSavedHeightSpacer").remove(), t.fixedHeight && !t.isDisabled && (i = M.data(e, "pagerSavedHeight")) && (s = 0, 1 < M(e).css("border-spacing").split(" ").length && (s = M(e).css("border-spacing").split(" ")[1].replace(/[^-\d\.]/g, "")), 5 < (a = i - o.height() + s * t.size - s) && M.data(e, "pagerLastSize") === t.size && o.children("tr:visible").length < ("all" === t.size ? t.totalRows : t.size) && o.append('<tr class="pagerSavedHeightSpacer ' + r.selectorRemove.slice(1) + '" style="height:' + a + 'px;"></tr>'))
                    },
                    z = function(e, t) {
                        var a, i = e.config,
                            s = i.$tbodies.eq(0);
                        s.find("tr.pagerSavedHeightSpacer").remove(), s.children("tr:visible").length || s.append('<tr class="pagerSavedHeightSpacer ' + i.selectorRemove.slice(1) + '"><td>&nbsp</td></tr>'), a = s.children("tr").eq(0).height() * ("all" === t.size ? t.totalRows : t.size), M.data(e, "pagerSavedHeight", a), R(e, t), M.data(e, "pagerLastSize", t.size)
                    },
                    x = function(e, t) {
                        if (!t.ajaxUrl) {
                            var a, i = 0,
                                s = e.config,
                                r = s.$tbodies.eq(0).children("tr"),
                                o = r.length,
                                n = "all" === t.size ? t.totalRows : t.size,
                                l = t.page * n,
                                g = l + n,
                                c = 0,
                                d = 0;
                            for (t.cacheIndex = [], a = 0; a < o; a++) t.regexFiltered.test(r[a].className) || (d === l && r[a].className.match(s.cssChildRow) ? r[a].style.display = "none" : (r[a].style.display = l <= d && d < g ? "" : "none", c !== d && l <= d && d < g && (t.cacheIndex[t.cacheIndex.length] = a, c = d), (d += r[a].className.match(s.cssChildRow + "|" + s.selectorRemove.slice(1)) && !t.countChildRows ? 0 : 1) === g && "none" !== r[a].style.display && r[a].className.match(T.css.cssHasChild) && (i = a)));
                            if (0 < i && r[i].className.match(T.css.cssHasChild))
                                for (; ++i < o && r[i].className.match(s.cssChildRow);) r[i].style.display = ""
                        }
                    },
                    j = function(e, t) {
                        t.size = A(t, t.$container.find(t.cssPageSize).val(), "get"), F(e, t.size, t), h(e, t), t.removeRows || (x(e, t), M(e).bind("sortEnd filterEnd ".split(" ").join(e.config.namespace + "pager "), function() {
                            x(e, t)
                        }))
                    },
                    P = function(e, t, a, i, s, r) {
                        if ("function" == typeof a.ajaxProcessing) {
                            t.config.$tbodies.eq(0).empty();
                            var o, n, l, g, c, d, p, f, u, h, w, b, R, z, x, j = t.config,
                                P = j.$table,
                                v = "",
                                m = a.ajaxProcessing(e, t, i) || [0, []];
                            if (T.showError(t), r) T.debug(j, "pager") && console.error("Pager >> Ajax Error", i, s, r), T.showError(t, i, s, r), j.$tbodies.eq(0).children("tr").detach(), a.totalRows = 0;
                            else {
                                if (M.isArray(m) ? (R = m[(l = isNaN(m[0]) && !isNaN(m[1])) ? 1 : 0], a.totalRows = isNaN(R) ? a.totalRows || 0 : R, j.totalRows = j.filteredRows = a.filteredRows = a.totalRows, w = 0 === a.totalRows ? [] : m[l ? 0 : 1] || [], h = m[2]) : (a.ajaxData = m, j.totalRows = a.totalRows = m.total, j.filteredRows = a.filteredRows = void 0 !== m.filteredRows ? m.filteredRows : m.total, h = m.headers, w = m.rows || []), b = w && w.length, w instanceof M) a.processAjaxOnInit && (j.$tbodies.eq(0).empty(), j.$tbodies.eq(0).append(w));
                                else if (b) {
                                    for (o = 0; o < b; o++) {
                                        for (v += "<tr>", n = 0; n < w[o].length; n++) v += /^\s*<td/.test(w[o][n]) ? M.trim(w[o][n]) : "<td>" + w[o][n] + "</td>";
                                        v += "</tr>"
                                    }
                                    a.processAjaxOnInit && j.$tbodies.eq(0).html(v)
                                }
                                if (a.processAjaxOnInit = !0, h)
                                    for (d = (g = P.hasClass("hasStickyHeaders")) ? j.widgetOptions.$sticky.children("thead:first").children("tr:not(." + j.cssIgnoreRow + ")").children() : "", c = P.find("tfoot tr:first").children(), z = (p = j.$headers.filter("th ")).length, n = 0; n < z; n++)(f = p.eq(n)).find("." + T.css.icon).length ? (u = f.find("." + T.css.icon).clone(!0), f.find("." + T.css.headerIn).html(h[n]).append(u), g && d.length && (u = d.eq(n).find("." + T.css.icon).clone(!0), d.eq(n).find("." + T.css.headerIn).html(h[n]).append(u))) : (f.find("." + T.css.headerIn).html(h[n]), g && d.length && (a.$container = a.$container.add(j.widgetOptions.$sticky), d.eq(n).find("." + T.css.headerIn).html(h[n]))), c.eq(n).html(h[n])
                            }
                            j.showProcessing && T.isProcessing(t), x = A(a, a.size, "get"), a.totalPages = "all" === x ? 1 : Math.ceil(a.totalRows / x), a.last.totalRows = a.totalRows, a.last.currentFilters = a.currentFilters, a.last.sortList = (j.sortList || []).join(","), y(t, a, !1), T.updateCache(j, function() {
                                a.initialized && setTimeout(function() {
                                    T.debug(j, "pager") && console.log("Pager >> Triggering pagerChange"), P.triggerHandler("pagerChange", a), T.applyWidget(t), y(t, a, !0)
                                }, 0)
                            })
                        }
                        a.initialized || q(t, a)
                    },
                    v = function(e, a) {
                        var t, i, s = e.config,
                            r = a.ajaxUrl ? a.ajaxUrl.replace(/\{page([\-+]\d+)?\}/, function(e, t) {
                                return a.page + (t ? parseInt(t, 10) : 0)
                            }).replace(/\{size\}/g, a.size) : "",
                            o = s.sortList,
                            n = a.currentFilters || M(e).data("lastSearch") || [],
                            l = r.match(/\{\s*sort(?:List)?\s*:\s*(\w*)\s*\}/),
                            g = r.match(/\{\s*filter(?:List)?\s*:\s*(\w*)\s*\}/),
                            c = [];
                        if (l) {
                            for (l = l[1], i = o.length, t = 0; t < i; t++) c[c.length] = l + "[" + o[t][0] + "]=" + o[t][1];
                            r = r.replace(/\{\s*sort(?:List)?\s*:\s*(\w*)\s*\}/g, c.length ? c.join("&") : l), c = []
                        }
                        if (g) {
                            for (g = g[1], i = n.length, t = 0; t < i; t++) n[t] && (c[c.length] = g + "[" + t + "]=" + encodeURIComponent(n[t]));
                            r = r.replace(/\{\s*filter(?:List)?\s*:\s*(\w*)\s*\}/g, c.length ? c.join("&") : g), a.currentFilters = n
                        }
                        return "function" == typeof a.customAjaxUrl && (r = a.customAjaxUrl(e, r)), T.debug(s, "pager") && console.log("Pager >> Ajax url = " + r), r
                    },
                    m = function(e, t, a) {
                        var i, s, r, o, n = M(e),
                            l = e.config,
                            g = T.debug(l, "pager"),
                            c = l.$table.hasClass("hasFilters"),
                            d = t && t.length || 0,
                            p = "all" === a.size ? a.totalRows : a.size,
                            f = a.page * p;
                        if (d < 1) g && console.warn("Pager >> No rows for pager to render");
                        else {
                            if (a.page >= a.totalPages && E(e, a), a.cacheIndex = [], a.isDisabled = !1, a.initialized && (g && console.log("Pager >> Triggering pagerChange"), n.triggerHandler("pagerChange", a)), a.removeRows) {
                                for (T.clearTableBody(e), i = T.processTbody(e, l.$tbodies.eq(0), !0), r = s = c ? 0 : f, o = 0; o < p && s < t.length;) c && a.regexFiltered.test(t[s][0].className) || f < ++r && o <= p && (o++, a.cacheIndex[a.cacheIndex.length] = s, i.append(t[s])), s++;
                                T.processTbody(e, i, !1)
                            } else x(e, a);
                            y(e, a), e.isUpdating && (g && console.log("Pager >> Triggering updateComplete"), n.triggerHandler("updateComplete", [e, !0]))
                        }
                    },
                    C = function(e, t) {
                        var a, i, s;
                        for (t.ajax ? h(e, t, !0) : (M.data(e, "pagerLastPage", t.page), M.data(e, "pagerLastSize", t.size), t.page = 0, t.size = t.totalRows, t.totalPages = 1, M(e).addClass("pagerDisabled").removeAttr("aria-describedby").find("tr.pagerSavedHeightSpacer").remove(), m(e, e.config.rowsCopy, t), t.isDisabled = !0, T.applyWidget(e), T.debug(e.config, "pager") && console.log("Pager >> Disabled")), s = (i = t.$container.find(t.cssGoto + "," + t.cssPageSize + ", .ts-startRow, .ts-page")).length, a = 0; a < s; a++) i.eq(a).addClass(t.cssDisabled)[0].disabled = !0, i[a].ariaDisabled = !0
                    },
                    S = function(i) {
                        var s = i.config,
                            r = s.pager;
                        T.updateCache(s, function() {
                            var e, t = [],
                                a = i.config.cache[0].normalized;
                            for (r.totalRows = a.length, e = 0; e < r.totalRows; e++) t[t.length] = a[e][s.columns].$row;
                            s.rowsCopy = t, $(i, r, !0)
                        })
                    },
                    $ = function(e, t, a) {
                        if (!t.isDisabled) {
                            var i, s, r, o, n, l, g, c, d = e.config,
                                p = T.debug(d, "pager"),
                                f = M(e),
                                u = t.last;
                            if (!1 !== a && t.initialized && T.isEmptyObject(d.cache)) return S(e);
                            if (!t.ajax || !T.hasWidget(e, "filter") || d.widgetOptions.filter_initialized)
                                if (N(e, t), w(e, t), u.currentFilters = "" === (u.currentFilters || []).join("") ? [] : u.currentFilters, t.currentFilters = "" === (t.currentFilters || []).join("") ? [] : t.currentFilters, u.page !== t.page || u.size !== t.size || u.totalRows !== t.totalRows || (u.currentFilters || []).join(",") !== (t.currentFilters || []).join(",") || (u.ajaxUrl || "") !== (t.ajaxObject.url || "") || (u.optAjaxUrl || "") !== (t.ajaxUrl || "") || u.sortList !== (d.sortList || []).join(",")) p && console.log("Pager >> Changing to page " + t.page), t.last = {
                                    page: t.page,
                                    size: t.size,
                                    sortList: (d.sortList || []).join(","),
                                    totalRows: t.totalRows,
                                    currentFilters: t.currentFilters || [],
                                    ajaxUrl: t.ajaxObject.url || "",
                                    optAjaxUrl: t.ajaxUrl || ""
                                }, t.ajax ? t.processAjaxOnInit || T.isEmptyObject(t.initialRows) ? (n = v(s = e, r = t), l = M(document), g = s.config, c = g.namespace + "pager", "" !== n && (g.showProcessing && T.isProcessing(s, !0), l.bind("ajaxError" + c, function(e, t, a, i) {
                                    P(null, s, r, t, a, i), l.unbind("ajaxError" + c)
                                }), o = ++r.ajaxCounter, r.last.ajaxUrl = n, r.ajaxObject.url = n, r.ajaxObject.success = function(e, t, a) {
                                    o < r.ajaxCounter || (P(e, s, r, a), l.unbind("ajaxError" + c), "function" == typeof r.oldAjaxSuccess && r.oldAjaxSuccess(e))
                                }, T.debug(g, "pager") && console.log("Pager >> Ajax initialized", r.ajaxObject), M.ajax(r.ajaxObject))) : (t.processAjaxOnInit = !0, i = t.initialRows, t.totalRows = void 0 !== i.total ? i.total : p && console.error("Pager >> No initial total page set!") || 0, t.filteredRows = void 0 !== i.filtered ? i.filtered : p && console.error("Pager >> No initial filtered page set!") || 0, q(e, t)) : t.ajax || m(e, d.rowsCopy, t), M.data(e, "pagerLastPage", t.page), t.initialized && !1 !== a && (p && console.log("Pager >> Triggering pageMoved"), f.triggerHandler("pageMoved", t), T.applyWidget(e), e.isUpdating && (p && console.log("Pager >> Triggering updateComplete"), f.triggerHandler("updateComplete", [e, !0])))
                        }
                    },
                    I = function(e, t) {
                        return T.hasWidget(e, "filter") ? Math.min(t.totalPages, t.filteredPages) : t.totalPages
                    },
                    N = function(e, t) {
                        var a = I(e, t) - 1;
                        return t.page = parseInt(t.page, 10), (t.page < 0 || isNaN(t.page)) && (t.page = 0), t.page > a && 0 <= a && (t.page = a), t.page
                    },
                    A = function(e, t, a) {
                        var i = parseInt(t, 10) || e.size || e.settings.size || 10;
                        return e.initialized && (/all/i.test(i + " " + t) || i === e.totalRows) ? e.$container.find(e.cssPageSize + ' option[value="all"]').length ? "all" : e.totalRows : "get" === a ? i : e.size
                    },
                    F = function(e, t, a) {
                        a.size = A(a, t, "get"), a.$container.find(a.cssPageSize).val(a.size), M.data(e, "pagerLastPage", N(e, a)), M.data(e, "pagerLastSize", a.size), a.totalPages = "all" === a.size ? 1 : Math.ceil(a.totalRows / a.size), a.filteredPages = "all" === a.size ? 1 : Math.ceil(a.filteredRows / a.size)
                    },
                    O = function(e, t) {
                        t.page = 0, $(e, t)
                    },
                    E = function(e, t) {
                        t.page = I(e, t) - 1, $(e, t)
                    },
                    L = function(e, t) {
                        t.page++;
                        var a = I(e, t) - 1;
                        t.page >= a && (t.page = a), $(e, t)
                    },
                    D = function(e, t) {
                        t.page--, t.page <= 0 && (t.page = 0), $(e, t)
                    },
                    q = function(e, t) {
                        t.initialized = !0, t.initializing = !1, T.debug(e.config, "pager") && console.log("Pager >> Triggering pagerInitialized"), M(e).triggerHandler("pagerInitialized", t), T.applyWidget(e), y(e, t)
                    },
                    U = function(e, t, a) {
                        var i, s, r, o = e.config;
                        t.$container.find(t.cssGoto + "," + t.cssPageSize + ",.ts-startRow, .ts-page").removeClass(t.cssDisabled).removeAttr("disabled").each(function() {
                            this.ariaDisabled = !1
                        }), t.isDisabled = !1, t.page = M.data(e, "pagerLastPage") || t.page || 0, s = (r = t.$container.find(t.cssPageSize)).find("option[selected]").val(), t.size = M.data(e, "pagerLastSize") || A(t, s, "get"), t.totalPages = "all" === t.size ? 1 : Math.ceil(I(e, t) / t.size), F(e, t.size, t), e.id && !o.$table.attr("aria-describedby") && ((i = (r = t.$container.find(t.cssPageDisplay)).attr("id")) || (i = e.id + "_pager_info", r.attr("id", i)), o.$table.attr("aria-describedby", i)), z(e, t), a && (T.update(o), F(e, t.size, t), $(e, t), j(e, t), T.debug(o, "pager") && console.log("Pager >> Enabled"))
                    },
                    H = function(o, e) {
                        var t, s, r, a, n = o.config,
                            i = n.widgetOptions,
                            l = T.debug(n, "pager"),
                            g = n.pager = M.extend(!0, {}, M.tablesorterPager.defaults, e),
                            c = n.$table,
                            d = n.namespace + "pager",
                            p = g.$container = M(g.container).addClass("tablesorter-pager").show();
                        g.settings = M.extend(!0, {}, M.tablesorterPager.defaults, e), l && console.log("Pager >> Initializing"), g.oldAjaxSuccess = g.oldAjaxSuccess || g.ajaxObject.success, n.appender = u.appender, g.initializing = !0, g.savePages && T.storage && (t = T.storage(o, g.storageKey) || {}, g.page = isNaN(t.page) ? g.page : t.page, g.size = "all" === t.size ? t.size : (isNaN(t.size) ? g.size : t.size) || g.setSize || 10, F(o, g.size, g)), g.regexRows = new RegExp("(" + (i.filter_filteredRow || "filtered") + "|" + n.selectorRemove.slice(1) + "|" + n.cssChildRow + ")"), g.regexFiltered = new RegExp(i.filter_filteredRow || "filtered"), c.unbind(f.split(" ").join(d + " ").replace(/\s+/g, " ")).bind("filterInit filterStart ".split(" ").join(d + " "), function(e, t) {
                            var a;
                            if (g.currentFilters = M.isArray(t) ? t : n.$table.data("lastSearch"), g.ajax && "filterInit" === e.type) return $(o, g, !1);
                            a = T.filter.equalFilters ? T.filter.equalFilters(n, n.lastSearch, g.currentFilters) : (n.lastSearch || []).join("") !== (g.currentFilters || []).join(""), "filterStart" !== e.type || !1 === g.pageReset || a || (g.page = g.pageReset)
                        }).bind("filterEnd sortEnd ".split(" ").join(d + " "), function() {
                            g.currentFilters = n.$table.data("lastSearch"), (g.initialized || g.initializing) && (n.delayInit && n.rowsCopy && 0 === n.rowsCopy.length && S(o), y(o, g, !1), $(o, g, !1), T.applyWidget(o))
                        }).bind("disablePager" + d, function(e) {
                            e.stopPropagation(), C(o, g)
                        }).bind("enablePager" + d, function(e) {
                            e.stopPropagation(), U(o, g, !0)
                        }).bind("destroyPager" + d, function(e) {
                            var t, a, i, s, r;
                            e.stopPropagation(), a = g, i = (t = o).config, s = i.namespace + "pager", r = [a.cssFirst, a.cssPrev, a.cssNext, a.cssLast, a.cssGoto, a.cssPageSize].join(","), C(t, a), a.$container.hide().find(r).unbind(s), i.appender = null, i.$table.unbind(s), T.storage && T.storage(t, a.storageKey, ""), delete i.pager, delete i.rowsCopy
                        }).bind("resetToLoadState" + d, function(e) {
                            var t, a;
                            e.stopPropagation(), a = g, (t = o).config.pager = M.extend(!0, {}, M.tablesorterPager.defaults, a.settings), H(t, a.settings)
                        }).bind("updateComplete" + d, function(e, t, a) {
                            if (e.stopPropagation(), t && !a && !g.ajax) {
                                var i = n.$tbodies.eq(0).children("tr").not(n.selectorRemove);
                                g.totalRows = i.length - (g.countChildRows ? 0 : i.filter("." + n.cssChildRow).length), g.totalPages = "all" === g.size ? 1 : Math.ceil(g.totalRows / g.size), i.length && n.rowsCopy && 0 === n.rowsCopy.length && S(t), g.page >= g.totalPages && E(t, g), x(t, g), z(t, g), y(t, g, !0)
                            }
                        }).bind("pageSize refreshComplete ".split(" ").join(d + " "), function(e, t) {
                            e.stopPropagation(), F(o, A(g, t, "get"), g), $(o, g), x(o, g), y(o, g, !1)
                        }).bind("pageSet pagerUpdate ".split(" ").join(d + " "), function(e, t) {
                            e.stopPropagation(), "pagerUpdate" === e.type && (t = void 0 === t ? g.page + 1 : t, g.last.page = !0), g.page = (parseInt(t, 10) || 1) - 1, $(o, g, !0), y(o, g, !1)
                        }).bind("pageAndSize" + d, function(e, t, a) {
                            e.stopPropagation(), g.page = (parseInt(t, 10) || 1) - 1, F(o, A(g, a, "get"), g), $(o, g, !0), x(o, g), y(o, g, !1)
                        }), s = [g.cssFirst, g.cssPrev, g.cssNext, g.cssLast], r = [O, D, L, E], l && !p.length && console.warn('Pager >> "container" not found'), p.find(s.join(",")).attr("tabindex", 0).unbind("click" + d).bind("click" + d, function(e) {
                            e.stopPropagation();
                            var t, a = M(this),
                                i = s.length;
                            if (!a.hasClass(g.cssDisabled))
                                for (t = 0; t < i; t++)
                                    if (a.is(s[t])) {
                                        r[t](o, g);
                                        break
                                    }
                        }), (a = p.find(g.cssGoto)).length ? a.unbind("change" + d).bind("change" + d, function() {
                            g.page = M(this).val() - 1, $(o, g, !0), y(o, g, !1)
                        }) : l && console.warn('Pager >> "goto" selector not found'), (a = p.find(g.cssPageSize)).length ? (a.find("option").removeAttr("selected"), a.unbind("change" + d).bind("change" + d, function() {
                            if (!M(this).hasClass(g.cssDisabled)) {
                                var e = M(this).val();
                                F(o, e, g), $(o, g), z(o, g)
                            }
                            return !1
                        })) : l && console.warn('Pager >> "size" selector not found'), g.initialized = !1, c.triggerHandler("pagerBeforeInitialized", g), U(o, g, !1), "string" == typeof g.ajaxUrl ? (g.ajax = !0, n.widgetOptions.filter_serversideFiltering = !0, n.serverSideSorting = !0, $(o, g)) : (g.ajax = !1, T.appendCache(n, !0), j(o, g)), g.ajax || g.initialized || (g.initializing = !1, g.initialized = !0, F(o, g.size, g), $(o, g), l && console.log("Pager >> Triggering pagerInitialized"), n.$table.triggerHandler("pagerInitialized", g), n.widgetOptions.filter_initialized && T.hasWidget(o, "filter") || y(o, g, !1)), n.widgetInit.pager = !0
                    };
                u.appender = function(e, t) {
                    var a = e.config,
                        i = a.pager;
                    i.ajax || (a.rowsCopy = t, i.totalRows = i.countChildRows ? a.$tbodies.eq(0).children("tr").length : t.length, i.size = M.data(e, "pagerLastSize") || i.size || i.settings.size || 10, i.totalPages = "all" === i.size ? 1 : Math.ceil(i.totalRows / i.size), m(e, t, i), y(e, i, !1))
                }, u.construct = function(e) {
                    return this.each(function() {
                        this.config && this.hasInitialized && H(this, e)
                    })
                }
            }
        }), T.showError = function(e, t, a, i) {
            var s = M(e),
                r = s[0].config,
                o = r && r.widgetOptions,
                n = r.pager && r.pager.cssErrorRow || o && o.pager_css && o.pager_css.errorRow || "tablesorter-errorRow",
                l = typeof t,
                g = !0,
                c = "",
                d = function() {
                    r.$table.find("thead").find(r.selectorRemove).remove()
                };
            if (s.length) {
                if ("function" == typeof r.pager.ajaxError) {
                    if (!1 === (g = r.pager.ajaxError(r, t, a, i))) return d();
                    c = g
                } else if ("function" == typeof o.pager_ajaxError) {
                    if (!1 === (g = o.pager_ajaxError(r, t, a, i))) return d();
                    c = g
                }
                if ("" === c)
                    if ("object" === l) c = 0 === t.status ? "Not connected, verify Network" : 404 === t.status ? "Requested page not found [404]" : 500 === t.status ? "Internal Server Error [500]" : "parsererror" === i ? "Requested JSON parse failed" : "timeout" === i ? "Time out error" : "abort" === i ? "Ajax Request aborted" : "Uncaught error: " + t.statusText + " [" + t.status + "]";
                    else {
                        if ("string" !== l) return d();
                        c = t
                    } M(/tr\>/.test(c) ? c : '<tr><td colspan="' + r.columns + '">' + c + "</td></tr>").click(function() {
                    M(this).remove()
                }).appendTo(r.$table.find("thead:first")).addClass(n + " " + r.selectorRemove.slice(1)).attr({
                    role: "alert",
                    "aria-live": "assertive"
                })
            } else console.error("tablesorter showError: no table parameter passed")
        }, M.fn.extend({
            tablesorterPager: M.tablesorterPager.construct
        })
    }(jQuery);
    return jQuery;
}));
