/* A* maze search on a two-layer routing grid, called from router.py via ctypes.
 *
 * Grid cells are indexed c = (layer * H + y) * W + x.  The search state adds the
 * direction of the move that entered the cell (0..7 in 45 degree steps, 8 = none)
 * so bends can be penalised: 45 degree bends cost t45, 90 degree bends t90 and
 * sharper bends are not allowed.  A diagonal move needs both orthogonal
 * neighbours to be passable so the segment cannot clip an obstacle corner.
 * Changing layer costs via_cost and is only allowed where viaok[y * W + x] != 0.
 */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct { float f; int32_t s; } item_t;
typedef struct { item_t *a; long n, cap; } heap_t;

static int hpush(heap_t *h, float f, int32_t s)
{
    if (h->n == h->cap) {
        long cap = h->cap ? 2 * h->cap : 1 << 16;
        item_t *a = realloc(h->a, cap * sizeof(item_t));
        if (!a) return -1;
        h->a = a; h->cap = cap;
    }
    long i = h->n++;
    while (i > 0) {
        long p = (i - 1) / 2;
        if (h->a[p].f <= f) break;
        h->a[i] = h->a[p];
        i = p;
    }
    h->a[i].f = f; h->a[i].s = s;
    return 0;
}

static item_t hpop(heap_t *h)
{
    item_t top = h->a[0], last = h->a[--h->n];
    long i = 0;
    for (;;) {
        long c = 2 * i + 1;
        if (c >= h->n) break;
        if (c + 1 < h->n && h->a[c + 1].f < h->a[c].f) c++;
        if (h->a[c].f >= last.f) break;
        h->a[i] = h->a[c];
        i = c;
    }
    h->a[i] = last;
    return top;
}

static const int DX[8] = {1, 1, 0, -1, -1, -1, 0, 1};
static const int DY[8] = {0, 1, 1, 1, 0, -1, -1, -1};

/* Returns the path length written to out (cells from source to target), 0 if
 * no path was found and -1 on allocation failure. */
int astar(int W, int H, const uint8_t *pass, const uint8_t *viaok, const float *cost,
          const uint8_t *target, const int32_t *src, int nsrc,
          float via_cost, float t45, float t90, float hscale,
          int32_t *out, int maxout, long maxexp)
{
    long ncell = 2L * H * W, nstate = ncell * 9;
    float *g = malloc(nstate * sizeof(float));
    int32_t *par = malloc(nstate * sizeof(int32_t));
    uint8_t *closed = calloc(nstate, 1);
    heap_t h = {0};
    int ret = 0;
    if (!g || !par || !closed) { ret = -1; goto done; }
    for (long i = 0; i < nstate; i++) g[i] = INFINITY;

    int tx0 = W, ty0 = H, tx1 = -1, ty1 = -1;
    for (long c = 0; c < ncell; c++) {
        if (!target[c]) continue;
        int x = c % W, y = (c / W) % H;
        if (x < tx0) tx0 = x;
        if (x > tx1) tx1 = x;
        if (y < ty0) ty0 = y;
        if (y > ty1) ty1 = y;
    }
    if (tx1 < 0) goto done;

#define HEUR(x, y) ({ int _dx = (x) < tx0 ? tx0 - (x) : ((x) > tx1 ? (x) - tx1 : 0); \
                      int _dy = (y) < ty0 ? ty0 - (y) : ((y) > ty1 ? (y) - ty1 : 0); \
                      int _mn = _dx < _dy ? _dx : _dy; \
                      hscale * ((float)(_dx + _dy) - 0.5857864f * _mn); })

    for (int i = 0; i < nsrc; i++) {
        long c = src[i];
        if (c < 0 || c >= ncell || !pass[c]) continue;
        long s = c * 9 + 8;
        int x = c % W, y = (c / W) % H;
        g[s] = 0.0f; par[s] = -1;
        if (hpush(&h, HEUR(x, y), (int32_t)s)) { ret = -1; goto done; }
    }

    long found = -1, nexp = 0;
    while (h.n) {
        item_t it = hpop(&h);
        long s = it.s;
        if (closed[s]) continue;
        closed[s] = 1;
        int d = s % 9;
        long c = s / 9;
        int x = c % W, y = (c / W) % H, l = c / ((long)W * H);
        if (target[c]) { found = s; break; }
        if (++nexp > maxexp) break;
        float gs = g[s];
        for (int k = 0; k < 8; k++) {
            float pen = 0.0f;
            if (d != 8) {
                int t = abs(k - d);
                if (t > 4) t = 8 - t;
                if (t >= 3) continue;
                pen = t == 1 ? t45 : (t == 2 ? t90 : 0.0f);
            }
            int nx = x + DX[k], ny = y + DY[k];
            if (nx < 0 || ny < 0 || nx >= W || ny >= H) continue;
            long nc = ((long)l * H + ny) * W + nx;
            if (!pass[nc]) continue;
            if (k & 1) {
                if (!pass[((long)l * H + y) * W + nx] || !pass[((long)l * H + ny) * W + x]) continue;
            }
            float step = (k & 1) ? 1.41421356f : 1.0f;
            float ng = gs + step + pen + (cost ? cost[nc] * step : 0.0f);
            long ns = nc * 9 + k;
            if (ng < g[ns]) {
                g[ns] = ng; par[ns] = (int32_t)s;
                if (hpush(&h, ng + HEUR(nx, ny), (int32_t)ns)) { ret = -1; goto done; }
            }
        }
        if (viaok[(long)y * W + x]) {
            long nc = ((long)(1 - l) * H + y) * W + x;
            if (pass[nc]) {
                long ns = nc * 9 + 8;
                float ng = gs + via_cost + (cost ? cost[nc] : 0.0f);
                if (ng < g[ns]) {
                    g[ns] = ng; par[ns] = (int32_t)s;
                    if (hpush(&h, ng + HEUR(x, y), (int32_t)ns)) { ret = -1; goto done; }
                }
            }
        }
    }
    if (found >= 0) {
        int n = 0;
        for (long s = found; s >= 0; s = par[s]) n++;
        if (n > maxout) { ret = -1; goto done; }
        int i = n;
        for (long s = found; s >= 0; s = par[s]) out[--i] = (int32_t)(s / 9);
        ret = n;
    }
done:
    free(g); free(par); free(closed); free(h.a);
    return ret;
}
