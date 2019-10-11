// Disabling tablesorter completely

.addClass('hasFilters')

$('#search').quicksearch('table tbody tr', {
delay: 500,
show: function() {
    $(this).removeClass('filtered');
    $table.trigger('pageSet'); // reset to page 1 & update display
},
hide: function() {
    $(this).hide().addClass('filtered');
    $table.trigger('pageSet'); // reset to page 1 & update display
},
onAfter: function() {
    $table.trigger('update.pager');
}
});
});

(function(b, k, q, r) {
    b.fn.quicksearch = function(l, p) {
        var m, n, h, e, f = "",
            g = this,
            a = b.extend({
                delay: 100,
                selector: null,
                stripeRows: null,
                loader: null,
                noResults: "",
                matchedResultsCount: 0,
                bind: "keyup",
                onBefore: function() {},
                onAfter: function() {},
                show: function() {
                    this.style.display = ""
                },
                hide: function() {
                    this.style.display = "none"
                },
                prepareQuery: function(a) {
                    return a.toLowerCase().split(" ")
                },
                testQuery: function(a, b, d) {
                    for (d = 0; d < a.length; d += 1)
                        if (-1 === b.indexOf(a[d])) return !1;
                    return !0
                }
            }, p);
        this.go = function() {
            for (var c = 0, b =
                    0, d = !0, e = a.prepareQuery(f), g = 0 === f.replace(" ", "").length, c = 0, k = h.length; c < k; c++) g || a.testQuery(e, n[c], h[c]) ? (a.show.apply(h[c]), d = !1, b++) : a.hide.apply(h[c]);
            d ? this.results(!1) : (this.results(!0), this.stripe());
            this.matchedResultsCount = b;
            this.loader(!1);
            a.onAfter();
            return this
        };
        this.search = function(a) {
            f = a;
            g.trigger()
        };
        this.currentMatchedResults = function() {
            return this.matchedResultsCount
        };
        this.stripe = function() {
            if ("object" === typeof a.stripeRows && null !== a.stripeRows) {
                var c = a.stripeRows.join(" "),
                    f = a.stripeRows.length;
                e.not(":hidden").each(function(d) {
                    b(this).removeClass(c).addClass(a.stripeRows[d % f])
                })
            }
            return this
        };
        this.strip_html = function(a) {
            a = a.replace(RegExp("<[^<]+>", "g"), "");
            return a = b.trim(a.toLowerCase())
        };
        this.results = function(c) {
            "string" === typeof a.noResults && "" !== a.noResults && (c ? b(a.noResults).hide() : b(a.noResults).show());
            return this
        };
        this.loader = function(c) {
            "string" === typeof a.loader && "" !== a.loader && (c ? b(a.loader).show() : b(a.loader).hide());
            return this
        };
        this.cache = function() {
            e = b(l);
            "string" === typeof a.noResults &&
                "" !== a.noResults && (e = e.not(a.noResults));
            n = ("string" === typeof a.selector ? e.find(a.selector) : b(l).not(a.noResults)).map(function() {
                return g.strip_html(this.innerHTML)
            });
            h = e.map(function() {
                return this
            });
            f = f || this.val() || "";
            return this.go()
        };
        this.trigger = function() {
            this.loader(!0);
            a.onBefore();
            k.clearTimeout(m);
            m = k.setTimeout(function() {
                g.go()
            }, a.delay);
            return this
        };
        this.cache();
        this.results(!0);
        this.stripe();
        this.loader(!1);
        return this.each(function() {
            b(this).on(a.bind, function() {
                f = b(this).val();
                g.trigger()
            })
        })
    }
})(jQuery,
    this, document);
