# Generates images/cover.png: the book cover for MED5652 IES Stats Manual.
# One-off build utility, not sourced by any chapter. Re-run after design changes.

library(ggplot2)
library(tibble)

bg     <- "#F1EFE8"
ink    <- "#1B1F23"
muted  <- "#6B7280"
accent <- "#1E7F72"

# canvas is 8 x 12 (2:3), y increases upward
hex_pts <- function(cx, cy, w, h) {
  tibble(
    x = cx + c(0,  w / 2,  w / 2, 0, -w / 2, -w / 2),
    y = cy + c(h / 2, h / 4, -h / 4, -h / 2, -h / 4, h / 4)
  )
}

hex_cx <- 4
hex_cy <- 7.4
hex_w  <- 4
hex_h  <- hex_w / 0.87

outer_hex <- hex_pts(hex_cx, hex_cy, hex_w, hex_h)
inner_hex <- hex_pts(hex_cx, hex_cy, hex_w * 0.97, hex_h * 0.97)

band <- tibble(
  x = c(2.7, 5.3, 5.3, 2.7),
  y = hex_cy + c(-0.15, 0.5, 0.1, -0.45)
)

crude_line <- tibble(x = c(2.7, 5.3), y = hex_cy + c(-0.7, 0.8))
adjusted_line <- tibble(x = c(2.7, 5.3), y = hex_cy + c(-0.3, 0.3))

# randomly jittered, not hand-placed, so the cloud reads as real data rather
# than points laid neatly along a line. Centred on the adjusted (flatter)
# line's trend, deliberately: the crude line runs steeper than the cloud
# actually supports, which is the whole point of showing both.
set.seed(20260724)
n_pts <- 17
scatter_x <- runif(n_pts, 2.6, 5.4)
adjusted_slope <- diff(adjusted_line$y) / diff(adjusted_line$x)
scatter_trend <- adjusted_line$y[1] + adjusted_slope * (scatter_x - adjusted_line$x[1])
scatter <- tibble(
  x = scatter_x,
  y = pmin(pmax(scatter_trend + rnorm(n_pts, 0, 0.38), hex_cy - 1.05), hex_cy + 1.05),
  size = runif(n_pts, 2.1, 3.1)
)

p <- ggplot() +
  geom_polygon(data = outer_hex, aes(x, y), fill = accent) +
  geom_polygon(data = inner_hex, aes(x, y), fill = bg) +
  geom_polygon(data = band, aes(x, y), fill = accent, alpha = 0.18) +
  geom_line(data = crude_line, aes(x, y), colour = muted, linewidth = 0.9,
            linetype = "22") +
  geom_line(data = adjusted_line, aes(x, y), colour = accent, linewidth = 1.6,
            lineend = "round") +
  geom_point(data = scatter, aes(x, y, size = size), colour = ink, alpha = 0.72) +
  scale_size_identity() +
  # Three lines, smallest to biggest, top to bottom: the course code, the
  # course name (wrapped to two lines, or it runs wider than the canvas),
  # and "Statistics Manual" as the headline the cover's built around, since
  # that's the book's own title now (renamed from "Introduction to
  # Statistics", 2026-09-23; see root CLAUDE.md's Numbering and title
  # conventions section). Y-positions are chosen fresh for this three-line
  # shape, not inherited from the old four-slot layout.
  annotate("text", x = 4, y = 4.35, label = "MED5652",
           colour = accent, size = 4.2, fontface = "bold", family = "sans") +
  annotate("text", x = 4, y = 3.55,
           label = "Introduction to Epidemiology\nand Statistics",
           colour = muted, size = 3.3, family = "sans", lineheight = 1.15) +
  annotate("text", x = 4, y = 2.15, label = "Statistics Manual",
           colour = ink, size = 6.6, fontface = "bold", family = "sans") +
  coord_fixed(ratio = 1, xlim = c(0, 8), ylim = c(0, 12), expand = FALSE) +
  theme_void() +
  theme(
    plot.background = element_rect(fill = bg, colour = NA),
    panel.background = element_rect(fill = bg, colour = NA)
  )

if (!dir.exists("images")) dir.create("images")
ggsave("images/cover.png", p, width = 4, height = 6, dpi = 300, bg = bg)
